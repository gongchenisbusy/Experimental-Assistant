from __future__ import annotations

import copy
import math
import re
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from ea.storage import read_markdown_record


def _normalise_key(value: str) -> str:
    return re.sub(r"[_\W]+", "", value.lower())


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
        normalized_candidates = [_normalise_key(str(candidate)) for candidate in candidates if candidate]
        if any(len(candidate) >= 3 and candidate in normalized_text for candidate in normalized_candidates):
            return str(material_id)
    return None


def infer_material_from_project(root: Path, project_id: str, *extra_context: str) -> str | None:
    parts = [project_id, *extra_context]
    project_path = root / "EA_PROJECT.md"
    if project_path.exists():
        frontmatter, body = read_markdown_record(project_path)
        for key in ["material_system", "material", "materials"]:
            material_id = resolve_material_id(str(frontmatter.get(key, "")))
            if material_id:
                return material_id
        for key in ["project_id", "name", "project_name", "direction", "experiment_type"]:
            value = frontmatter.get(key)
            if value:
                parts.append(str(value))
        if body:
            parts.append(body[:2000])
    return infer_material_from_text(" ".join(part for part in parts if part))


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


def _raman_feature_window(rule: Mapping[str, Any]) -> list[float] | None:
    target = _finite_float(rule.get("target_cm_minus_1"))
    tolerance = _finite_float(rule.get("tolerance_cm_minus_1"))
    if target is None or tolerance is None:
        return None
    return [target - tolerance, target + tolerance]


def _window_overlaps(window: list[float] | None, lower: float | None, upper: float | None) -> bool:
    if window is None:
        return lower is None and upper is None
    if lower is not None and window[1] < lower:
        return False
    if upper is not None and window[0] > upper:
        return False
    return True


def _reference_hints_for_method(profile: Mapping[str, Any], method: str) -> list[dict[str, Any]]:
    hints = []
    for hint in profile.get("reference_hints", []):
        if method not in hint.get("methods", []):
            continue
        record = copy.deepcopy(hint)
        doi = record.get("doi")
        if doi and "url" not in record:
            record["url"] = f"https://doi.org/{doi}"
        hints.append(record)
    return hints


def _raman_candidate_summary(
    *,
    material_id: str,
    profile: Mapping[str, Any],
    method_profile: Mapping[str, Any],
    rule: Mapping[str, Any],
    reference_hints: list[dict[str, Any]],
) -> dict[str, Any]:
    window = _raman_feature_window(rule)
    target = _finite_float(rule.get("target_cm_minus_1"))
    tolerance = _finite_float(rule.get("tolerance_cm_minus_1"))
    return {
        "candidate_id": f"raman-builtin-{material_id}-{rule.get('feature')}",
        "material_id": material_id,
        "material_display_name": profile.get("display_name", material_id),
        "feature": rule.get("feature"),
        "label": rule.get("label"),
        "target_cm-1": target,
        "tolerance_cm-1": tolerance,
        "window_cm-1": window,
        "assignment_source": method_profile.get("assignment_source"),
        "reference_hint_keys": [hint.get("key") for hint in reference_hints if hint.get("key")],
        "source_backed": bool(reference_hints),
        "auto_applied": False,
        "requires_user_review": True,
        "notes": rule.get("notes"),
    }


def summarize_raman_assignment_libraries(
    *,
    materials: list[str] | None = None,
    features: list[str] | None = None,
    shift_min_cm1: float | None = None,
    shift_max_cm1: float | None = None,
) -> dict[str, Any]:
    """Summarize built-in Raman assignment profiles without creating project artifacts."""

    library = _library()
    material_filters = [value for value in (materials or []) if value]
    feature_filters = [value for value in (features or []) if value]
    resolved_materials: list[str] = []
    if material_filters:
        unknown: list[str] = []
        for material in material_filters:
            resolved = resolve_material_id(material)
            if resolved:
                resolved_materials.append(resolved)
            else:
                unknown.append(material)
        if unknown:
            available = ", ".join(record["material_id"] for record in available_materials())
            raise KeyError(f"Unknown material assignment profile: {', '.join(unknown)}. Available materials: {available}")
    feature_filter_keys = {_normalise_key(feature) for feature in feature_filters}

    all_candidates: list[dict[str, Any]] = []
    matching_profiles: list[dict[str, Any]] = []
    matching_reference_keys: set[str] = set()
    available_features: set[str] = set()
    available_windows: list[list[float]] = []

    for material_id, profile in sorted(library["materials"].items()):
        methods = profile.get("methods") or {}
        method_profile = methods.get("raman")
        if not method_profile:
            continue
        if resolved_materials and material_id not in resolved_materials:
            continue
        reference_hints = _reference_hints_for_method(profile, "raman")
        matching_candidates: list[dict[str, Any]] = []
        matching_feature_ids: set[str] = set()
        for rule in method_profile.get("feature_rules", []):
            feature = str(rule.get("feature") or "")
            label = str(rule.get("label") or "")
            available_features.add(feature)
            window = _raman_feature_window(rule)
            if window is not None:
                available_windows.append(window)
            candidate = _raman_candidate_summary(
                material_id=material_id,
                profile=profile,
                method_profile=method_profile,
                rule=rule,
                reference_hints=reference_hints,
            )
            all_candidates.append(candidate)

            if feature_filter_keys and not (
                _normalise_key(feature) in feature_filter_keys
                or any(key and key in _normalise_key(feature) for key in feature_filter_keys)
                or any(key and key in _normalise_key(label) for key in feature_filter_keys)
            ):
                continue
            if not _window_overlaps(window, shift_min_cm1, shift_max_cm1):
                continue
            matching_candidates.append(candidate)
            matching_feature_ids.add(feature)
            matching_reference_keys.update(candidate["reference_hint_keys"])

        if not matching_candidates:
            continue

        pair_rules = []
        for pair_rule in method_profile.get("pair_rules", []):
            required = list(pair_rule.get("required_features", []))
            if feature_filter_keys and not any(feature in matching_feature_ids for feature in required):
                continue
            pair_rules.append(
                {
                    "rule": pair_rule.get("rule"),
                    "required_features": required,
                    "matching_required_features": [feature for feature in required if feature in matching_feature_ids],
                    "fully_covered_by_matching_features": all(feature in matching_feature_ids for feature in required),
                    "separation_cm-1": pair_rule.get("separation_cm_minus_1"),
                }
            )

        matching_profiles.append(
            {
                "material_id": material_id,
                "display_name": profile.get("display_name", material_id),
                "formula": profile.get("formula"),
                "assignment_source": method_profile.get("assignment_source"),
                "candidate_count": len(method_profile.get("feature_rules", [])),
                "matching_candidate_count": len(matching_candidates),
                "reference_hints": reference_hints,
                "caveats": list(profile.get("caveats", [])),
                "pair_rules": pair_rules,
                "candidates": matching_candidates,
            }
        )

    total_count = len(all_candidates)
    matching_count = sum(len(profile["candidates"]) for profile in matching_profiles)
    if available_windows:
        available_shift_range = [min(window[0] for window in available_windows), max(window[1] for window in available_windows)]
    else:
        available_shift_range = None

    next_commands: dict[str, Any] = {
        "inspect_material_profile": [
            f"ea materials assignments {profile['material_id']} --method raman" for profile in matching_profiles
        ],
        "process_raman": "ea raman process /path/to/ea-project --metadata raw/raman/<characterization_id>/metadata.yml --x-column <x> --y-column <y> --x-unit cm^-1 --column-review-ref <review-id> --parameter-review-ref <review-id>",
        "generate_report": "ea raman report /path/to/ea-project --metadata processed/sample-001/raman/<result_id>/raman_metadata.yml --reference-id <registered-reference-id>",
        "register_references": "ea references add /path/to/ea-project --citation <citation> --doi <doi> --source-type manual",
    }
    if matching_count == 0:
        next_commands["inspect_material_profile"] = []

    return {
        "schema_version": "0.2",
        "source": "ea.materials.raman_assignment_library_discovery:v0.2",
        "status": "ready" if matching_count else "no_matching_candidates",
        "method": "raman",
        "available_builtin_libraries": ["builtin_material_assignments"],
        "library_version": library.get("library_version", "unknown"),
        "material_count": len(matching_profiles),
        "total_candidate_count": total_count,
        "matching_candidate_count": matching_count,
        "available_materials": [record for record in available_materials() if "raman" in record.get("methods", [])],
        "available_features": sorted(feature for feature in available_features if feature),
        "available_shift_range_cm-1": available_shift_range,
        "matching_reference_hint_keys": sorted(key for key in matching_reference_keys if key),
        "filters": {
            "materials": material_filters,
            "resolved_materials": resolved_materials,
            "features": feature_filters,
            "shift_min_cm-1": shift_min_cm1,
            "shift_max_cm-1": shift_max_cm1,
        },
        "libraries": [
            {
                "library_id": "builtin_material_assignments",
                "library_ref": f"builtin:ea.materials.assignments:{library.get('library_version', 'unknown')}",
                "method": "raman",
                "candidate_count": total_count,
                "matching_candidate_count": matching_count,
                "material_profiles": matching_profiles,
            }
        ],
        "next_commands": next_commands,
        "boundaries": [
            "This discovery command reads bundled Raman material-assignment metadata only and does not create project files.",
            "It does not run live literature search, operate Zotero or browsers, download or parse articles, register references, inject report citations, create ReviewRecords, write memory, process spectra, match peaks, or apply assignments.",
            "Source-backed Raman candidates remain screening aids; they do not prove material identity, phase identity, layer number, strain, doping, calibration, or sample quality without project context, registered references, and user review.",
        ],
    }


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
        feature_ids = [feature["peak_id"] for feature in assigned.values()]
        if not required and method_profile.get("matched_text"):
            analysis["possible_interpretations"].append(
                {
                    "text": method_profile.get("matched_text"),
                    "confidence": method_profile.get("matched_confidence", "medium"),
                    "evidence": feature_ids,
                    "assignment_source": method_profile.get("assignment_source"),
                }
            )
            return analysis
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
