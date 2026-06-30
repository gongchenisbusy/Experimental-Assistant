from __future__ import annotations

import copy
import math
import re
from functools import lru_cache
from importlib import resources
from typing import Any, Iterable, Mapping

import yaml


def _normalise_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


@lru_cache(maxsize=1)
def _library() -> dict[str, Any]:
    text = resources.files("ea.materials").joinpath("assignments.yml").read_text(encoding="utf-8")
    loaded = yaml.safe_load(text) or {}
    loaded.setdefault("materials", {})
    return loaded


def available_materials() -> list[dict[str, Any]]:
    library = _library()
    records = []
    for material_id, profile in sorted(library["materials"].items()):
        records.append(
            {
                "material_id": material_id,
                "display_name": profile.get("display_name", material_id),
                "formula": profile.get("formula"),
                "aliases": list(profile.get("aliases", [])),
                "methods": sorted((profile.get("methods") or {}).keys()),
            }
        )
    return records


def resolve_material_id(material: str) -> str | None:
    query = _normalise_key(material)
    for material_id, profile in _library()["materials"].items():
        candidates = [material_id, profile.get("display_name", ""), profile.get("formula", "")]
        candidates.extend(profile.get("aliases", []))
        if query in {_normalise_key(str(candidate)) for candidate in candidates if candidate}:
            return str(material_id)
    return None


def infer_material_from_text(text: str) -> str | None:
    normalized_text = _normalise_key(text)
    for material_id, profile in _library()["materials"].items():
        candidates = [material_id, profile.get("display_name", ""), profile.get("formula", "")]
        candidates.extend(profile.get("aliases", []))
        if any(_normalise_key(str(candidate)) in normalized_text for candidate in candidates if candidate):
            return str(material_id)
    return None


def get_material_profile(material: str) -> dict[str, Any]:
    material_id = resolve_material_id(material)
    if not material_id:
        raise KeyError(f"Unknown material assignment profile: {material}")
    profile = copy.deepcopy(_library()["materials"][material_id])
    profile["material_id"] = material_id
    profile["library_version"] = _library().get("library_version", "unknown")
    return profile


def assignment_candidates(material: str, method: str | None = None) -> dict[str, Any]:
    profile = get_material_profile(material)
    methods = profile.get("methods") or {}
    if method is None:
        return {
            "material_id": profile["material_id"],
            "display_name": profile.get("display_name"),
            "library_version": profile.get("library_version"),
            "methods": copy.deepcopy(methods),
            "caveats": profile.get("caveats", []),
            "reference_hints": profile.get("reference_hints", []),
        }
    if method not in methods:
        raise KeyError(f"No {method} assignment profile for material: {material}")
    result = copy.deepcopy(methods[method])
    result["material_id"] = profile["material_id"]
    result["display_name"] = profile.get("display_name")
    result["method"] = method
    result["library_version"] = profile.get("library_version")
    result["caveats"] = profile.get("caveats", [])
    result["reference_hints"] = [
        ref for ref in profile.get("reference_hints", []) if method in ref.get("methods", [])
    ]
    return result


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _peak_position(row: Mapping[str, Any], preferred_keys: Iterable[str]) -> float | None:
    for key in preferred_keys:
        value = _finite_float(row.get(key))
        if value is not None:
            return value
    return None


def _peak_id(row: Mapping[str, Any], fallback: int) -> str:
    value = row.get("peak_id")
    return str(value) if value is not None else f"peak-{fallback:03d}"


def _confidence_from_delta(delta: float, medium_delta: float) -> str:
    return "medium" if abs(delta) <= medium_delta else "low"


def _base_analysis(material: str, method: str) -> tuple[dict[str, Any], dict[str, Any]]:
    method_profile = assignment_candidates(material, method)
    analysis = {
        "material_id": method_profile["material_id"],
        "material_display_name": method_profile.get("display_name"),
        "method": method,
        "library_version": method_profile.get("library_version"),
        "assignment_source": method_profile.get("assignment_source"),
        "assigned_features": [],
        "possible_interpretations": [],
        "library_caveats": method_profile.get("caveats", []),
        "reference_hints": method_profile.get("reference_hints", []),
        "peak_updates": [],
    }
    return method_profile, analysis


def match_raman_peaks(material: str, peaks: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    peak_rows = list(peaks)
    method_profile, analysis = _base_analysis(material, "raman")
    analysis["peak_count"] = len(peak_rows)
    if not peak_rows:
        analysis["possible_interpretations"].append(
            {
                "text": "No stable Raman peaks were detected by the current automatic settings.",
                "confidence": "insufficient",
                "evidence": [],
            }
        )
        return analysis

    assigned: dict[str, dict[str, Any]] = {}
    used_peak_ids: set[str] = set()
    for rule in method_profile.get("feature_rules", []):
        target = float(rule["target_cm_minus_1"])
        tolerance = float(rule["tolerance_cm_minus_1"])
        medium_delta = float(rule.get("medium_delta_cm_minus_1", tolerance / 2.0))
        best: tuple[float, Mapping[str, Any], float, str] | None = None
        for index, row in enumerate(peak_rows, start=1):
            peak_id = _peak_id(row, index)
            if peak_id in used_peak_ids:
                continue
            observed = _peak_position(row, ["fit_center_cm-1", "position_cm-1", "position"])
            if observed is None:
                continue
            delta = observed - target
            distance = abs(delta)
            if distance <= tolerance and (best is None or distance < best[0]):
                best = (distance, row, delta, peak_id)
        if best is None:
            continue
        _, row, delta, peak_id = best
        observed = _peak_position(row, ["fit_center_cm-1", "position_cm-1", "position"])
        confidence = _confidence_from_delta(delta, medium_delta)
        feature = {
            "feature": rule["feature"],
            "label": rule["label"],
            "target_cm-1": target,
            "observed_cm-1": observed,
            "delta_cm-1": delta,
            "peak_id": peak_id,
            "confidence": confidence,
            "assignment_source": method_profile.get("assignment_source"),
        }
        analysis["assigned_features"].append(feature)
        analysis["peak_updates"].append(
            {
                "peak_id": peak_id,
                "assignment": rule["label"],
                "assignment_confidence": confidence,
                "assignment_delta_cm-1": delta,
                "assignment_feature": rule["feature"],
                "assignment_source": method_profile.get("assignment_source"),
            }
        )
        assigned[rule["feature"]] = feature
        used_peak_ids.add(peak_id)

    pair_rule = (method_profile.get("pair_rules") or [{}])[0]
    required = pair_rule.get("required_features", [])
    if required and all(feature in assigned for feature in required):
        first = assigned[required[0]]
        second = assigned[required[1]]
        separation = float(second["observed_cm-1"] - first["observed_cm-1"])
        windows = pair_rule.get("separation_cm_minus_1", {})
        thin_min, thin_max = windows.get("thin_layer_window", [18.0, 22.5])
        multi_min, multi_max = windows.get("multilayer_bulk_like_window", [22.5, 27.0])
        if float(thin_min) <= separation <= float(thin_max):
            confidence = "medium"
            text = pair_rule.get("thin_layer_text")
        elif float(multi_min) < separation <= float(multi_max):
            confidence = "medium"
            text = pair_rule.get("multilayer_text")
        else:
            confidence = "low"
            text = pair_rule.get("outside_text")
        analysis["mode_separation_cm-1"] = separation
        analysis["possible_interpretations"].append(
            {
                "text": text,
                "confidence": confidence,
                "evidence": [first["peak_id"], second["peak_id"]],
                "mode_separation_cm-1": separation,
                "rule": pair_rule.get("rule"),
                "assignment_source": method_profile.get("assignment_source"),
            }
        )
    elif assigned:
        feature = next(iter(assigned.values()))
        analysis["possible_interpretations"].append(
            {
                "text": method_profile.get("single_feature_text"),
                "confidence": "insufficient",
                "evidence": [feature["peak_id"]],
                "assignment_source": method_profile.get("assignment_source"),
            }
        )
    else:
        analysis["possible_interpretations"].append(
            {
                "text": method_profile.get("no_match_text"),
                "confidence": "insufficient",
                "evidence": [],
                "assignment_source": method_profile.get("assignment_source"),
            }
        )
    return analysis


def match_pl_peaks(material: str, peaks: Iterable[Mapping[str, Any]], *, x_unit: str) -> dict[str, Any]:
    peak_rows = list(peaks)
    method_profile, analysis = _base_analysis(material, "pl")
    analysis["peak_count"] = len(peak_rows)
    analysis["dominant_peak"] = None
    if not peak_rows:
        analysis["possible_interpretations"].append(
            {
                "text": "No stable PL peak was detected by the current automatic settings.",
                "confidence": "insufficient",
                "evidence": [],
            }
        )
        return analysis

    dominant_index, dominant = max(
        enumerate(peak_rows, start=1),
        key=lambda item: _finite_float(item[1].get("prominence")) or 0.0,
    )
    peak_id = _peak_id(dominant, dominant_index)
    position = _peak_position(dominant, ["position"])
    position_e_v = _peak_position(dominant, ["position_eV"])
    wavelength = _peak_position(dominant, ["wavelength_nm"])
    if position_e_v is None and x_unit == "eV":
        position_e_v = position
    if position_e_v is None and x_unit == "nm" and wavelength:
        position_e_v = 1239.841984 / wavelength
    dominant_peak = {
        "peak_id": peak_id,
        "position": position,
        "position_unit": str(dominant.get("position_unit") or x_unit),
        "position_eV": position_e_v,
        "wavelength_nm": wavelength,
    }
    analysis["dominant_peak"] = dominant_peak

    rule = (method_profile.get("feature_rules") or [{}])[0]
    if position_e_v is None:
        text = method_profile.get("missing_energy_text")
        confidence = "low"
    else:
        low, high = rule.get("energy_eV_range", [1.75, 1.95])
        if float(low) <= position_e_v <= float(high):
            text = method_profile.get("in_range_text")
            confidence = "medium"
            feature = {
                "feature": rule.get("feature"),
                "label": rule.get("label"),
                "energy_eV_range": [float(low), float(high)],
                "observed_eV": position_e_v,
                "peak_id": peak_id,
                "confidence": confidence,
                "assignment_source": method_profile.get("assignment_source"),
            }
            analysis["assigned_features"].append(feature)
            analysis["peak_updates"].append(
                {
                    "peak_id": peak_id,
                    "assignment": rule.get("label"),
                    "assignment_confidence": confidence,
                    "assignment_feature": rule.get("feature"),
                    "assignment_source": method_profile.get("assignment_source"),
                }
            )
        else:
            text = method_profile.get("out_of_range_text")
            confidence = "low"
    analysis["possible_interpretations"].append(
        {
            "text": text,
            "confidence": confidence,
            "evidence": [peak_id],
            "dominant_peak": dominant_peak,
            "assignment_source": method_profile.get("assignment_source"),
        }
    )
    return analysis


def match_xrd_peaks(material: str, peaks: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    peak_rows = list(peaks)
    method_profile, analysis = _base_analysis(material, "xrd")
    analysis["peak_count"] = len(peak_rows)
    analysis["strongest_peaks"] = []
    if not peak_rows:
        analysis["possible_interpretations"].append(
            {
                "text": "No stable XRD peak was detected by the current automatic settings.",
                "confidence": "insufficient",
                "evidence": [],
            }
        )
        return analysis

    strongest = sorted(peak_rows, key=lambda row: _finite_float(row.get("prominence")) or 0.0, reverse=True)[:6]
    analysis["strongest_peaks"] = [
        {
            "peak_id": _peak_id(row, index),
            "two_theta_deg": _peak_position(row, ["two_theta_deg", "two_theta"]),
            "d_spacing_angstrom": _peak_position(row, ["d_spacing_angstrom"]),
        }
        for index, row in enumerate(strongest, start=1)
    ]

    rule = (method_profile.get("feature_rules") or [{}])[0]
    low, high = rule.get("two_theta_deg_range", [13.5, 15.5])
    matched: list[dict[str, Any]] = []
    for index, row in enumerate(peak_rows, start=1):
        two_theta = _peak_position(row, ["two_theta_deg", "two_theta"])
        if two_theta is None or not (float(low) <= two_theta <= float(high)):
            continue
        peak_id = _peak_id(row, index)
        d_spacing = _peak_position(row, ["d_spacing_angstrom"])
        feature = {
            "feature": rule.get("feature"),
            "label": rule.get("label"),
            "two_theta_deg_range": [float(low), float(high)],
            "observed_two_theta_deg": two_theta,
            "observed_d_spacing_angstrom": d_spacing,
            "peak_id": peak_id,
            "confidence": "medium",
            "assignment_source": method_profile.get("assignment_source"),
        }
        matched.append(feature)
        analysis["peak_updates"].append(
            {
                "peak_id": peak_id,
                "possible_phase": rule.get("label"),
                "assignment_confidence": "medium",
                "assignment_feature": rule.get("feature"),
                "assignment_source": method_profile.get("assignment_source"),
            }
        )

    if matched:
        evidence = [feature["peak_id"] for feature in matched[:3]]
        analysis["assigned_features"].extend(matched)
        text = method_profile.get("in_range_text")
        confidence = "medium"
    else:
        evidence = [analysis["strongest_peaks"][0]["peak_id"]]
        text = method_profile.get("out_of_range_text")
        confidence = "low"
    analysis["possible_interpretations"].append(
        {
            "text": text,
            "confidence": confidence,
            "evidence": evidence,
            "assignment_source": method_profile.get("assignment_source"),
        }
    )
    return analysis
