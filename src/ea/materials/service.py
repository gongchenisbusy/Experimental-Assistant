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


def audit_assignment_library(
    *,
    materials: list[str] | None = None,
    methods: list[str] | None = None,
) -> dict[str, Any]:
    """Audit bundled assignment-library coverage without creating project artifacts."""

    library = _library()
    material_filters = [value for value in (materials or []) if value]
    method_filters = [value for value in (methods or []) if value]
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

    allowed_methods = {"raman", "pl", "xrd"}
    normalized_methods = sorted({_normalise_key(method) for method in method_filters})
    unknown_methods = [method for method in normalized_methods if method not in allowed_methods]
    if unknown_methods:
        raise KeyError(f"Unknown assignment-library method filter: {', '.join(unknown_methods)}. Available methods: raman, pl, xrd")

    method_counts: dict[str, dict[str, Any]] = {}
    material_records: list[dict[str, Any]] = []
    missing_reference_candidates: list[dict[str, Any]] = []
    source_backed_candidate_ids: list[str] = []
    reference_hint_index: dict[str, dict[str, Any]] = {}
    total_candidate_count = 0

    for material_id, profile in sorted(library["materials"].items()):
        if resolved_materials and material_id not in resolved_materials:
            continue
        material_methods = profile.get("methods") or {}
        method_records: list[dict[str, Any]] = []
        for method, method_profile in sorted(material_methods.items()):
            if method not in allowed_methods:
                continue
            if normalized_methods and method not in normalized_methods:
                continue
            reference_hints = _reference_hints_for_method(profile, method)
            reference_hint_keys = [hint.get("key") for hint in reference_hints if hint.get("key")]
            for hint in reference_hints:
                key = hint.get("key")
                if key:
                    reference_hint_index[str(key)] = hint
            candidate_records: list[dict[str, Any]] = []
            method_candidate_count = 0
            method_source_backed_count = 0
            method_missing_count = 0
            for rule in method_profile.get("feature_rules", []):
                feature = str(rule.get("feature") or "")
                candidate_id = f"{method}-builtin-{material_id}-{feature}"
                source_backed = bool(reference_hint_keys)
                candidate = {
                    "candidate_id": candidate_id,
                    "material_id": material_id,
                    "method": method,
                    "feature": feature,
                    "label": rule.get("label"),
                    "assignment_source": method_profile.get("assignment_source"),
                    "reference_hint_keys": reference_hint_keys,
                    "source_backed": source_backed,
                    "requires_user_review": True,
                }
                candidate_records.append(candidate)
                total_candidate_count += 1
                method_candidate_count += 1
                if source_backed:
                    source_backed_candidate_ids.append(candidate_id)
                    method_source_backed_count += 1
                else:
                    missing_reference_candidates.append(candidate)
                    method_missing_count += 1

            method_summary = method_counts.setdefault(
                method,
                {
                    "method": method,
                    "material_profile_count": 0,
                    "candidate_count": 0,
                    "source_backed_candidate_count": 0,
                    "missing_reference_candidate_count": 0,
                    "reference_hint_keys": set(),
                },
            )
            method_summary["material_profile_count"] += 1
            method_summary["candidate_count"] += method_candidate_count
            method_summary["source_backed_candidate_count"] += method_source_backed_count
            method_summary["missing_reference_candidate_count"] += method_missing_count
            method_summary["reference_hint_keys"].update(reference_hint_keys)

            method_records.append(
                {
                    "method": method,
                    "assignment_source": method_profile.get("assignment_source"),
                    "candidate_count": method_candidate_count,
                    "source_backed_candidate_count": method_source_backed_count,
                    "missing_reference_candidate_count": method_missing_count,
                    "reference_hint_keys": reference_hint_keys,
                    "candidates": candidate_records,
                }
            )

        if method_records:
            material_records.append(
                {
                    "material_id": material_id,
                    "display_name": profile.get("display_name", material_id),
                    "formula": profile.get("formula"),
                    "method_count": len(method_records),
                    "candidate_count": sum(record["candidate_count"] for record in method_records),
                    "source_backed_candidate_count": sum(record["source_backed_candidate_count"] for record in method_records),
                    "missing_reference_candidate_count": sum(record["missing_reference_candidate_count"] for record in method_records),
                    "methods": method_records,
                }
            )

    source_backed_count = len(source_backed_candidate_ids)
    missing_count = len(missing_reference_candidates)
    audited_methods = [
        {
            **{key: value for key, value in summary.items() if key != "reference_hint_keys"},
            "reference_hint_keys": sorted(summary["reference_hint_keys"]),
        }
        for _, summary in sorted(method_counts.items())
    ]

    return {
        "schema_version": "0.2",
        "source": "ea.materials.assignment_library_audit:v0.2",
        "status": "no_matching_candidates" if total_candidate_count == 0 else ("ready" if missing_count == 0 else "ready_with_reference_gaps"),
        "library_id": "builtin_material_assignments",
        "library_ref": f"builtin:ea.materials.assignments:{library.get('library_version', 'unknown')}",
        "library_version": library.get("library_version", "unknown"),
        "filters": {
            "materials": material_filters,
            "resolved_materials": resolved_materials,
            "methods": method_filters,
            "normalized_methods": normalized_methods,
        },
        "material_profile_count": len(material_records),
        "method_profile_count": sum(len(record["methods"]) for record in material_records),
        "candidate_count": total_candidate_count,
        "source_backed_candidate_count": source_backed_count,
        "missing_reference_candidate_count": missing_count,
        "reference_hint_count": len(reference_hint_index),
        "methods": audited_methods,
        "materials": material_records,
        "source_backed_candidate_ids": sorted(source_backed_candidate_ids),
        "missing_reference_candidates": missing_reference_candidates,
        "reference_hints": [reference_hint_index[key] for key in sorted(reference_hint_index)],
        "recommended_discovery_commands": {
            "raman": "ea raman list-assignment-libraries",
            "pl": "ea pl list-assignment-libraries",
            "xrd": "ea xrd list-assignment-libraries",
        },
        "recommended_next_actions": [
            "Use method-specific discovery commands to inspect windows and candidate caveats before interpretation.",
            "Register project references before citing assignment candidates in reports.",
            "If a future audit reports missing-reference candidates, treat those candidates as local screening metadata until the library is enriched or project-specific references are registered.",
        ],
        "boundaries": [
            "This audit reads bundled material-assignment metadata only and does not create project files.",
            "It does not run live literature search, operate Zotero or browsers, download or parse articles, register references, inject report citations, create ReviewRecords, write memory, process spectra or diffraction patterns, match peaks, or apply assignments.",
            "Assignment-library coverage and reference hints remain audit metadata; they do not prove material identity, phase identity, PL mechanism, layer number, crystallinity, texture, strain, doping, calibration, or sample quality without project context, registered references, and user review.",
        ],
    }


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


def _pl_energy_window(rule: Mapping[str, Any]) -> list[float] | None:
    values = rule.get("energy_eV_range")
    if not isinstance(values, list) or len(values) != 2:
        return None
    lower = _finite_float(values[0])
    upper = _finite_float(values[1])
    if lower is None or upper is None:
        return None
    return [min(lower, upper), max(lower, upper)]


def _energy_window_to_wavelength_window(window: list[float] | None) -> list[float] | None:
    if window is None or window[0] <= 0 or window[1] <= 0:
        return None
    low_nm = 1239.841984 / window[1]
    high_nm = 1239.841984 / window[0]
    return [low_nm, high_nm]


def _pl_candidate_summary(
    *,
    material_id: str,
    profile: Mapping[str, Any],
    method_profile: Mapping[str, Any],
    rule: Mapping[str, Any],
    reference_hints: list[dict[str, Any]],
) -> dict[str, Any]:
    energy_window = _pl_energy_window(rule)
    wavelength_window = _energy_window_to_wavelength_window(energy_window)
    return {
        "candidate_id": f"pl-builtin-{material_id}-{rule.get('feature')}",
        "material_id": material_id,
        "material_display_name": profile.get("display_name", material_id),
        "feature": rule.get("feature"),
        "label": rule.get("label"),
        "energy_window_eV": energy_window,
        "wavelength_window_nm": wavelength_window,
        "assignment_source": method_profile.get("assignment_source"),
        "reference_hint_keys": [hint.get("key") for hint in reference_hints if hint.get("key")],
        "source_backed": bool(reference_hints),
        "auto_applied": False,
        "requires_user_review": True,
        "notes": rule.get("notes"),
    }


def summarize_pl_assignment_libraries(
    *,
    materials: list[str] | None = None,
    features: list[str] | None = None,
    energy_min_eV: float | None = None,
    energy_max_eV: float | None = None,
    wavelength_min_nm: float | None = None,
    wavelength_max_nm: float | None = None,
) -> dict[str, Any]:
    """Summarize built-in PL assignment profiles without creating project artifacts."""

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
    available_energy_windows: list[list[float]] = []
    available_wavelength_windows: list[list[float]] = []

    for material_id, profile in sorted(library["materials"].items()):
        methods = profile.get("methods") or {}
        method_profile = methods.get("pl")
        if not method_profile:
            continue
        if resolved_materials and material_id not in resolved_materials:
            continue
        reference_hints = _reference_hints_for_method(profile, "pl")
        matching_candidates: list[dict[str, Any]] = []
        for rule in method_profile.get("feature_rules", []):
            feature = str(rule.get("feature") or "")
            label = str(rule.get("label") or "")
            available_features.add(feature)
            energy_window = _pl_energy_window(rule)
            wavelength_window = _energy_window_to_wavelength_window(energy_window)
            if energy_window is not None:
                available_energy_windows.append(energy_window)
            if wavelength_window is not None:
                available_wavelength_windows.append(wavelength_window)
            candidate = _pl_candidate_summary(
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
            if not _window_overlaps(energy_window, energy_min_eV, energy_max_eV):
                continue
            if not _window_overlaps(wavelength_window, wavelength_min_nm, wavelength_max_nm):
                continue
            matching_candidates.append(candidate)
            matching_reference_keys.update(candidate["reference_hint_keys"])

        if not matching_candidates:
            continue

        matching_profiles.append(
            {
                "material_id": material_id,
                "display_name": profile.get("display_name", material_id),
                "formula": profile.get("formula"),
                "assignment_source": method_profile.get("assignment_source"),
                "candidate_count": len(method_profile.get("feature_rules", [])),
                "matching_candidate_count": len(matching_candidates),
                "axis_units": list(method_profile.get("axis_units", [])),
                "reference_hints": reference_hints,
                "caveats": list(profile.get("caveats", [])),
                "candidates": matching_candidates,
            }
        )

    total_count = len(all_candidates)
    matching_count = sum(len(profile["candidates"]) for profile in matching_profiles)
    available_energy_range = None
    if available_energy_windows:
        available_energy_range = [
            min(window[0] for window in available_energy_windows),
            max(window[1] for window in available_energy_windows),
        ]
    available_wavelength_range = None
    if available_wavelength_windows:
        available_wavelength_range = [
            min(window[0] for window in available_wavelength_windows),
            max(window[1] for window in available_wavelength_windows),
        ]

    next_commands: dict[str, Any] = {
        "inspect_material_profile": [
            f"ea materials assignments {profile['material_id']} --method pl" for profile in matching_profiles
        ],
        "process_pl": "ea pl process /path/to/ea-project --metadata raw/pl/<characterization_id>/metadata.yml --x-column <x> --y-column <y> --x-unit eV --column-review-ref <review-id> --parameter-review-ref <review-id>",
        "generate_report": "ea pl report /path/to/ea-project --metadata processed/sample-001/pl/<result_id>/pl_metadata.yml --reference-id <registered-reference-id>",
        "register_references": "ea references add /path/to/ea-project --citation <citation> --doi <doi> --source-type manual",
    }
    if matching_count == 0:
        next_commands["inspect_material_profile"] = []

    return {
        "schema_version": "0.2",
        "source": "ea.materials.pl_assignment_library_discovery:v0.2",
        "status": "ready" if matching_count else "no_matching_candidates",
        "method": "pl",
        "available_builtin_libraries": ["builtin_material_assignments"],
        "library_version": library.get("library_version", "unknown"),
        "material_count": len(matching_profiles),
        "total_candidate_count": total_count,
        "matching_candidate_count": matching_count,
        "available_materials": [record for record in available_materials() if "pl" in record.get("methods", [])],
        "available_features": sorted(feature for feature in available_features if feature),
        "available_energy_range_eV": available_energy_range,
        "available_wavelength_range_nm": available_wavelength_range,
        "matching_reference_hint_keys": sorted(key for key in matching_reference_keys if key),
        "filters": {
            "materials": material_filters,
            "resolved_materials": resolved_materials,
            "features": feature_filters,
            "energy_min_eV": energy_min_eV,
            "energy_max_eV": energy_max_eV,
            "wavelength_min_nm": wavelength_min_nm,
            "wavelength_max_nm": wavelength_max_nm,
        },
        "libraries": [
            {
                "library_id": "builtin_material_assignments",
                "library_ref": f"builtin:ea.materials.assignments:{library.get('library_version', 'unknown')}",
                "method": "pl",
                "candidate_count": total_count,
                "matching_candidate_count": matching_count,
                "material_profiles": matching_profiles,
            }
        ],
        "next_commands": next_commands,
        "boundaries": [
            "This discovery command reads bundled PL material-assignment metadata only and does not create project files.",
            "It does not run live literature search, operate Zotero or browsers, download or parse articles, register references, inject report citations, create ReviewRecords, write memory, process spectra, match peaks, or apply assignments.",
            "Source-backed PL candidates remain screening aids; they do not prove excitonic mechanism, material identity, layer number, defect origin, strain, doping, substrate effect, calibration, or sample quality without project context, registered references, and user review.",
        ],
    }


def _xrd_range_window(rule: Mapping[str, Any], key: str) -> list[float] | None:
    values = rule.get(key)
    if not isinstance(values, list) or len(values) != 2:
        return None
    lower = _finite_float(values[0])
    upper = _finite_float(values[1])
    if lower is None or upper is None:
        return None
    return [min(lower, upper), max(lower, upper)]


def _xrd_candidate_summary(
    *,
    material_id: str,
    profile: Mapping[str, Any],
    method_profile: Mapping[str, Any],
    rule: Mapping[str, Any],
    reference_hints: list[dict[str, Any]],
) -> dict[str, Any]:
    two_theta_window = _xrd_range_window(rule, "two_theta_deg_range")
    d_spacing_window = _xrd_range_window(rule, "d_spacing_angstrom_range")
    return {
        "candidate_id": f"xrd-builtin-{material_id}-{rule.get('feature')}",
        "material_id": material_id,
        "material_display_name": profile.get("display_name", material_id),
        "feature": rule.get("feature"),
        "label": rule.get("label"),
        "two_theta_window_deg": two_theta_window,
        "d_spacing_window_angstrom": d_spacing_window,
        "assignment_source": method_profile.get("assignment_source"),
        "reference_hint_keys": [hint.get("key") for hint in reference_hints if hint.get("key")],
        "source_backed": bool(reference_hints),
        "auto_applied": False,
        "requires_user_review": True,
        "notes": rule.get("notes"),
    }


def summarize_xrd_assignment_libraries(
    *,
    materials: list[str] | None = None,
    features: list[str] | None = None,
    two_theta_min_deg: float | None = None,
    two_theta_max_deg: float | None = None,
    d_spacing_min_angstrom: float | None = None,
    d_spacing_max_angstrom: float | None = None,
) -> dict[str, Any]:
    """Summarize built-in XRD assignment profiles without creating project artifacts."""

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
    available_two_theta_windows: list[list[float]] = []
    available_d_spacing_windows: list[list[float]] = []

    for material_id, profile in sorted(library["materials"].items()):
        methods = profile.get("methods") or {}
        method_profile = methods.get("xrd")
        if not method_profile:
            continue
        if resolved_materials and material_id not in resolved_materials:
            continue
        reference_hints = _reference_hints_for_method(profile, "xrd")
        matching_candidates: list[dict[str, Any]] = []
        for rule in method_profile.get("feature_rules", []):
            feature = str(rule.get("feature") or "")
            label = str(rule.get("label") or "")
            available_features.add(feature)
            two_theta_window = _xrd_range_window(rule, "two_theta_deg_range")
            d_spacing_window = _xrd_range_window(rule, "d_spacing_angstrom_range")
            if two_theta_window is not None:
                available_two_theta_windows.append(two_theta_window)
            if d_spacing_window is not None:
                available_d_spacing_windows.append(d_spacing_window)
            candidate = _xrd_candidate_summary(
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
            if not _window_overlaps(two_theta_window, two_theta_min_deg, two_theta_max_deg):
                continue
            if not _window_overlaps(d_spacing_window, d_spacing_min_angstrom, d_spacing_max_angstrom):
                continue
            matching_candidates.append(candidate)
            matching_reference_keys.update(candidate["reference_hint_keys"])

        if not matching_candidates:
            continue

        matching_profiles.append(
            {
                "material_id": material_id,
                "display_name": profile.get("display_name", material_id),
                "formula": profile.get("formula"),
                "assignment_source": method_profile.get("assignment_source"),
                "candidate_count": len(method_profile.get("feature_rules", [])),
                "matching_candidate_count": len(matching_candidates),
                "axis_unit": method_profile.get("axis_unit"),
                "reference_hints": reference_hints,
                "caveats": list(profile.get("caveats", [])),
                "candidates": matching_candidates,
            }
        )

    total_count = len(all_candidates)
    matching_count = sum(len(profile["candidates"]) for profile in matching_profiles)
    available_two_theta_range = None
    if available_two_theta_windows:
        available_two_theta_range = [
            min(window[0] for window in available_two_theta_windows),
            max(window[1] for window in available_two_theta_windows),
        ]
    available_d_spacing_range = None
    if available_d_spacing_windows:
        available_d_spacing_range = [
            min(window[0] for window in available_d_spacing_windows),
            max(window[1] for window in available_d_spacing_windows),
        ]

    next_commands: dict[str, Any] = {
        "inspect_material_profile": [
            f"ea materials assignments {profile['material_id']} --method xrd" for profile in matching_profiles
        ],
        "process_xrd": "ea xrd process /path/to/ea-project --metadata raw/xrd/<characterization_id>/metadata.yml --x-column <x> --y-column <y> --x-unit 2theta_deg --column-review-ref <review-id> --parameter-review-ref <review-id>",
        "generate_report": "ea xrd report /path/to/ea-project --metadata processed/sample-001/xrd/<result_id>/xrd_metadata.yml --reference-id <registered-reference-id>",
        "register_references": "ea references add /path/to/ea-project --citation <citation> --doi <doi> --source-type manual",
    }
    if matching_count == 0:
        next_commands["inspect_material_profile"] = []

    return {
        "schema_version": "0.2",
        "source": "ea.materials.xrd_assignment_library_discovery:v0.2",
        "status": "ready" if matching_count else "no_matching_candidates",
        "method": "xrd",
        "available_builtin_libraries": ["builtin_material_assignments"],
        "library_version": library.get("library_version", "unknown"),
        "material_count": len(matching_profiles),
        "total_candidate_count": total_count,
        "matching_candidate_count": matching_count,
        "available_materials": [record for record in available_materials() if "xrd" in record.get("methods", [])],
        "available_features": sorted(feature for feature in available_features if feature),
        "available_two_theta_range_deg": available_two_theta_range,
        "available_d_spacing_range_angstrom": available_d_spacing_range,
        "matching_reference_hint_keys": sorted(key for key in matching_reference_keys if key),
        "filters": {
            "materials": material_filters,
            "resolved_materials": resolved_materials,
            "features": feature_filters,
            "two_theta_min_deg": two_theta_min_deg,
            "two_theta_max_deg": two_theta_max_deg,
            "d_spacing_min_angstrom": d_spacing_min_angstrom,
            "d_spacing_max_angstrom": d_spacing_max_angstrom,
        },
        "libraries": [
            {
                "library_id": "builtin_material_assignments",
                "library_ref": f"builtin:ea.materials.assignments:{library.get('library_version', 'unknown')}",
                "method": "xrd",
                "candidate_count": total_count,
                "matching_candidate_count": matching_count,
                "material_profiles": matching_profiles,
            }
        ],
        "next_commands": next_commands,
        "boundaries": [
            "This discovery command reads bundled XRD material-assignment metadata only and does not create project files.",
            "It does not run live literature search, operate Zotero or browsers, download or parse articles, register references, inject report citations, create ReviewRecords, write memory, process diffraction patterns, match peaks, or apply assignments.",
            "XRD discovery candidates and any source-backed hints remain screening aids; they do not prove phase identity, material identity, crystallinity, texture, strain, lattice parameters, instrument calibration, or sample quality without project context, registered references, and user review.",
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
