from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

import matplotlib
import yaml

matplotlib.use("Agg")

import numpy as np
import pandas as pd
from scipy.signal import find_peaks, savgol_filter

from ea.figures import (
    NATURE_LIKE_COLORS,
    NATURE_LIKE_STYLE_PROFILE,
    figure_footer,
    register_figure,
    save_styled_figure,
    style_axis,
    styled_subplots,
)
from ea.provenance import write_provenance_entry
from ea.raman.service import _read_spectrum
from ea.raw_import import assert_not_raw_output_path
from ea.review import require_confirmed_review
from ea.schema import FTIRProcessingResult
from ea.schema.models import EARecord
from ea.standards import infer_project_slug
from ea.storage.files import read_yaml, write_yaml
from ea.storage.ids import next_id, next_standard_id


class FTIRProcessingError(RuntimeError):
    """Raised when FTIR processing would violate review or data boundaries."""


@dataclass(frozen=True)
class FTIRInspection:
    path: Path
    file_kind: str
    row_count: int
    columns: list[str]
    x_column_candidate: str | None
    y_column_candidate: str | None
    x_unit: str
    signal_mode_candidate: str
    metadata: dict[str, Any]
    warnings: list[str]
    requires_user_confirmation: bool


@dataclass(frozen=True)
class FTIRProcessingRequest:
    x_column: str
    y_column: str
    x_unit: str
    signal_mode: str
    processing_parameters: dict[str, Any]
    column_review_ref: str
    parameter_review_ref: str


BUILTIN_FTIR_ASSIGNMENT_LIBRARY_DEFAULT = "generic_materials"


@lru_cache(maxsize=1)
def _builtin_ftir_assignment_libraries() -> dict[str, Any]:
    text = resources.files("ea.ftir").joinpath("assignment_libraries.yml").read_text(encoding="utf-8")
    loaded = yaml.safe_load(text) or {}
    libraries = loaded.get("libraries")
    if not isinstance(libraries, dict):
        return {}
    return libraries


def builtin_ftir_assignment_libraries() -> list[str]:
    return sorted(_builtin_ftir_assignment_libraries())


def _builtin_ftir_assignment_library(name: str) -> dict[str, Any]:
    libraries = _builtin_ftir_assignment_libraries()
    if name not in libraries:
        available = ", ".join(sorted(libraries)) or "none"
        raise FTIRProcessingError(f"Unknown built-in FTIR assignment library: {name}. Available libraries: {available}")
    return deepcopy(libraries[name])


FTIR_BAND_WINDOWS = [
    {
        "min": 3200.0,
        "max": 3600.0,
        "family": "O-H / N-H stretching region",
        "notes": "Broad bands in this region often require humidity, adsorbate, or sample-preparation review.",
    },
    {
        "min": 3000.0,
        "max": 3100.0,
        "family": "aromatic or alkene C-H stretching region",
        "notes": "Use only as a screening hint unless supported by project chemistry and references.",
    },
    {
        "min": 2800.0,
        "max": 3000.0,
        "family": "aliphatic C-H stretching region",
        "notes": "Can indicate organic residues, ligands, binders, or sample contamination depending on context.",
    },
    {
        "min": 2250.0,
        "max": 2400.0,
        "family": "CO2/background or triple-bond region",
        "notes": "Atmospheric CO2 and instrument background should be checked before interpretation.",
    },
    {
        "min": 1650.0,
        "max": 1800.0,
        "family": "C=O, C=C, amide, or water-bending-adjacent region",
        "notes": "Multiple functional groups overlap here; assignment needs sample and literature context.",
    },
    {
        "min": 1500.0,
        "max": 1650.0,
        "family": "aromatic C=C, amide II, or water bending region",
        "notes": "This is an overlapping region and should not be used alone for chemical identification.",
    },
    {
        "min": 1200.0,
        "max": 1500.0,
        "family": "C-H bending / C-O / C-N mixed fingerprint region",
        "notes": "Fingerprint-region hints need comparison to reference spectra.",
    },
    {
        "min": 900.0,
        "max": 1200.0,
        "family": "C-O, C-O-C, Si-O, or fingerprint region",
        "notes": "Common in oxides, silicates, polymers, and oxygen-containing groups; confirm with context.",
    },
    {
        "min": 650.0,
        "max": 900.0,
        "family": "out-of-plane bending or fingerprint region",
        "notes": "Often diagnostic only when compared with a reviewed reference spectrum.",
    },
    {
        "min": 400.0,
        "max": 650.0,
        "family": "metal-oxygen or low-wavenumber fingerprint region",
        "notes": "Relevant to many inorganic materials but strongly system-dependent.",
    },
]


def default_ftir_processing_parameters() -> dict[str, Any]:
    return {
        "baseline_correction": {
            "enabled": False,
            "method": "rolling_quantile",
            "window_points": 101,
            "quantile": 0.05,
        },
        "smoothing": {
            "enabled": False,
            "method": "savitzky_golay",
            "window_length": 9,
            "polyorder": 2,
        },
        "normalization": {"enabled": True, "method": "max_abs"},
        "peak_detection": {
            "method": "scipy_find_peaks",
            "prominence": "auto",
            "distance": "auto",
            "max_bands": 12,
        },
        "band_assignment": {
            "enabled": True,
            "source": "ea.ftir.builtin_band_windows:v0.2",
        },
        "context_record": {
            "enabled": False,
            "method": "reviewed_metadata_record",
            "source": "ea.ftir.context_record:v0.2",
            "instrument_accessory": {},
            "atmosphere": {},
            "sample_preparation": {},
            "background": {},
            "reference": {},
            "correction_notes": [],
        },
    }


def _merge_parameters(parameters: dict[str, Any] | None) -> dict[str, Any]:
    merged = default_ftir_processing_parameters()
    if not parameters:
        return merged
    for key, value in parameters.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(deepcopy(value))
        else:
            merged[key] = deepcopy(value)
    return merged


def _warning(code: str, message: str, severity: str = "low", **details: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message, "severity": severity}
    payload.update(details)
    return payload


def _coerce_int(value: Any, default: int, *, minimum: int | None = None) -> tuple[int, bool]:
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return default, True
    if minimum is not None and coerced < minimum:
        return default, True
    return coerced, False


def _coerce_float(value: Any, default: float, *, minimum: float | None = None, maximum: float | None = None) -> tuple[float, bool]:
    try:
        coerced = float(value)
    except (TypeError, ValueError):
        return default, True
    if minimum is not None and coerced < minimum:
        return default, True
    if maximum is not None and coerced > maximum:
        return default, True
    return coerced, False


def _relative_to_root(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _coerce_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list | tuple):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _registered_reference_ids(root: Path) -> set[str]:
    index_path = root / "literature" / "references" / "index.yml"
    if not index_path.exists():
        return set()
    index = read_yaml(index_path)
    references = index.get("references")
    if not isinstance(references, dict):
        return set()
    return {str(reference_id) for reference_id in references}


def _candidate_number(value: Any, *names: str) -> float | None:
    for name in names:
        if not isinstance(value, dict) or value.get(name) is None:
            continue
        try:
            number = float(value.get(name))
        except (TypeError, ValueError):
            continue
        if np.isfinite(number):
            return number
    return None


def _axis_metadata_text(metadata: dict[str, Any]) -> str:
    parts = [
        metadata.get("AxisUnit[1]"),
        metadata.get("AxisLabel[1]"),
        metadata.get("x_unit"),
        metadata.get("x_label"),
        metadata.get("y_unit"),
        metadata.get("y_label"),
    ]
    return " ".join(str(part) for part in parts if part is not None).lower()


def _signal_mode_candidate(columns: list[str], metadata: dict[str, Any]) -> str:
    text = " ".join(columns + [_axis_metadata_text(metadata)]).lower()
    if "trans" in text or "%t" in text:
        return "transmittance"
    if "abs" in text:
        return "absorbance"
    return "absorbance"


def inspect_ftir_file(path: Path) -> FTIRInspection:
    frame, metadata = _read_spectrum(path)
    columns = [str(column) for column in frame.columns]
    if frame.empty or len(columns) < 2:
        raise FTIRProcessingError(f"No two-column numeric FTIR data found in {path}")

    x_values = pd.to_numeric(frame.iloc[:, 0], errors="coerce").dropna()
    x_min = float(x_values.min())
    x_max = float(x_values.max())
    metadata_text = _axis_metadata_text(metadata)
    path_text = path.as_posix().upper()
    looks_like_wavenumber = "cm" in metadata_text or (350 <= x_min <= 4500 and 350 <= x_max <= 4500)
    looks_like_ftir = "FTIR" in path_text or "INFRARED" in path_text or "/IR/" in path_text or (x_min <= 800 and x_max >= 2500)
    file_kind = "ftir" if looks_like_wavenumber and looks_like_ftir else "unknown"
    x_unit = "cm^-1" if "cm" in metadata_text or looks_like_wavenumber else "unknown"
    warnings: list[str] = []
    if file_kind == "unknown":
        warnings.append("ftir_file_kind_unknown")
    if x_unit == "cm^-1" and "cm" not in metadata_text:
        warnings.append("ftir_unit_inferred_from_range_or_path")

    return FTIRInspection(
        path=path,
        file_kind=file_kind,
        row_count=len(frame),
        columns=columns,
        x_column_candidate=columns[0],
        y_column_candidate=columns[1],
        x_unit=x_unit,
        signal_mode_candidate=_signal_mode_candidate(columns, metadata),
        metadata={**metadata, "x_min": x_min, "x_max": x_max},
        warnings=warnings,
        requires_user_confirmation=True,
    )


def _ftir_assignment_source_candidates(source_packet: Any) -> list[Any]:
    if isinstance(source_packet, list):
        return source_packet
    if isinstance(source_packet, dict):
        raw_candidates = source_packet.get("candidates") or source_packet.get("assignments") or source_packet.get("suggestions") or []
        return raw_candidates if isinstance(raw_candidates, list) else []
    return []


def _ftir_assignment_template_candidates() -> list[dict[str, Any]]:
    return [
        {
            "candidate_id": "ftir-assignment-template-001",
            "assignment_type": "functional_group",
            "assignment_label": "TODO: e.g. ester/carbonyl C=O stretching",
            "band_label": "TODO: descriptive band label",
            "material_scope": "TODO: polymer/oxide/surface-functionalized material scope",
            "sample_scope": "TODO: sample forms or preparation conditions where this applies",
            "wavenumber_window_cm1": [None, None],
            "expected_feature": "absorbance_maximum",
            "source_summary": "TODO: summarize the reference spectrum, table, or literature source for this band window.",
            "applicability_notes": ["TODO: describe when this window applies and known overlaps."],
            "reference_ids": ["TODO-registered-reference-id"],
            "confidence": "low",
            "caveats": ["Template candidate only; fill band window and source metadata before running suggest-assignments."],
        }
    ]


def _candidate_identity(candidate: dict[str, Any]) -> str:
    return str(candidate.get("candidate_id") or candidate.get("assignment_id") or candidate.get("suggestion_id") or "").strip()


def _normalize_assignment_type(value: Any) -> str:
    return str(value or "functional_group").strip().lower().replace("-", "_").replace(" ", "_")


def _normalize_expected_feature(value: Any) -> str:
    normalized = str(value or "any").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "peak": "any",
        "band": "any",
        "detected_band": "any",
        "absorbance_peak": "absorbance_maximum",
        "absorbance": "absorbance_maximum",
        "maximum": "absorbance_maximum",
        "valley": "transmittance_minimum",
        "minimum": "transmittance_minimum",
        "transmittance": "transmittance_minimum",
        "transmittance_valley": "transmittance_minimum",
    }
    return aliases.get(normalized, normalized)


def _candidate_matches_filters(
    candidate: dict[str, Any],
    *,
    include_candidates: set[str],
    assignment_types: set[str],
    material_scopes: set[str],
) -> bool:
    if include_candidates and _candidate_identity(candidate) not in include_candidates:
        return False
    if assignment_types and _normalize_assignment_type(candidate.get("assignment_type") or candidate.get("type")) not in assignment_types:
        return False
    if material_scopes:
        material_scope = str(candidate.get("material_scope") or "").strip().lower()
        if not any(scope in material_scope for scope in material_scopes):
            return False
    return True


def build_ftir_assignment_source_packet(
    root: Path,
    *,
    project_id: str,
    library_path: Path | None = None,
    builtin_library: str | None = None,
    output_path: Path | None = None,
    include_candidates: list[str] | None = None,
    assignment_types: list[str] | None = None,
    material_scopes: list[str] | None = None,
    template: bool = False,
    created_at: str | None = None,
) -> dict[str, Any]:
    if library_path and builtin_library:
        raise FTIRProcessingError("Use either --library-file or --builtin-library for FTIR assignment source-packet generation, not both")
    if template and builtin_library:
        raise FTIRProcessingError("Use either --write-template or --builtin-library for FTIR assignment source-packet generation, not both")
    if not library_path and not template:
        builtin_library = builtin_library or BUILTIN_FTIR_ASSIGNMENT_LIBRARY_DEFAULT

    template_mode = template and library_path is None and builtin_library is None
    builtin_mode = builtin_library is not None
    day = _created_day(created_at)
    timestamp = created_at or EARecord.now_iso()
    source_packet_id = next_id(root, "ftir_assignment_source_packet", day)
    if output_path is None:
        if template_mode:
            output_path = root / "templates" / "ftir_assignment_source_packet.yml"
        else:
            output_path = root / "suggestions" / "ftir" / "source-packets" / f"{source_packet_id}.yml"
    elif not output_path.is_absolute():
        output_path = root / output_path
    assert_not_raw_output_path(root, output_path)

    warnings: list[dict[str, Any]] = []
    library_ref: str | None = None
    library_kind = "template" if template_mode else "local_file"
    reference_seeds: dict[str, Any] = {}
    if template_mode:
        raw_candidates = _ftir_assignment_template_candidates()
    elif builtin_mode:
        library = _builtin_ftir_assignment_library(str(builtin_library))
        raw_candidates = _ftir_assignment_source_candidates(library)
        reference_seeds = deepcopy(library.get("reference_seeds") or {})
        library_ref = f"builtin:{builtin_library}"
        library_kind = "built_in"
    else:
        source_path = library_path if library_path and library_path.is_absolute() else root / library_path if library_path else None
        if source_path is None or not source_path.exists():
            raise FTIRProcessingError(f"FTIR assignment library file not found: {library_path}")
        library_ref = _relative_to_root(root, source_path)
        raw_candidates = _ftir_assignment_source_candidates(read_yaml(source_path))

    include_set = {str(item).strip() for item in include_candidates or [] if str(item).strip()}
    type_set = {_normalize_assignment_type(item) for item in assignment_types or [] if str(item).strip()}
    material_set = {str(item).strip().lower() for item in material_scopes or [] if str(item).strip()}
    selected: list[dict[str, Any]] = []
    for index, raw_candidate in enumerate(raw_candidates, start=1):
        if not isinstance(raw_candidate, dict):
            warnings.append(
                _warning(
                    "ftir_assignment_source_candidate_ignored",
                    "An FTIR assignment source candidate was not a mapping and was skipped while building the source packet.",
                    severity="medium",
                    candidate_index=index,
                )
            )
            continue
        if not _candidate_matches_filters(
            raw_candidate,
            include_candidates=include_set,
            assignment_types=type_set,
            material_scopes=material_set,
        ):
            continue
        selected.append(deepcopy(raw_candidate))

    if not raw_candidates:
        warnings.append(
            _warning(
                "ftir_assignment_source_library_empty",
                "No FTIR assignment candidates were found in the source library.",
                severity="medium",
            )
        )
    if raw_candidates and not selected:
        warnings.append(
            _warning(
                "ftir_assignment_source_no_matches",
                "No FTIR assignment candidates matched the requested filters.",
                severity="medium",
            )
        )

    reference_ids = sorted({reference_id for candidate in selected for reference_id in _coerce_string_list(candidate.get("reference_ids"))})
    packet_ref = _relative_to_root(root, output_path)
    status = "template_requires_user_edit" if template_mode else ("ready_for_suggest_assignments" if selected else "no_matching_candidates")
    packet = {
        "schema_version": "0.2",
        "source_packet_id": source_packet_id,
        "project_id": project_id,
        "status": status,
        "created_at": timestamp,
        "updated_at": timestamp,
        "source": "ea.ftir.assignment_source_packet:v0.2",
        "source_library_kind": library_kind,
        "source_library_ref": library_ref,
        "reference_seeds": reference_seeds,
        "candidate_count": len(selected),
        "candidates": selected,
        "filters": {
            "include_candidates": sorted(include_set),
            "assignment_types": sorted(type_set),
            "material_scopes": sorted(material_set),
        },
        "reference_ids": reference_ids,
        "warnings": warnings,
        "next_steps": [
            "If this packet uses built-in reference_seeds, register or replace those references in the project before treating suggestions as report evidence.",
            "Review and edit this packet until every candidate has a wavenumber window, source_summary, applicability_notes, reference_ids, confidence, and caveats.",
            "Run `ea ftir suggest-assignments` with processed FTIR metadata to match candidates against detected bands before using them in reports or memory.",
        ],
        "boundaries": [
            "FTIR assignment source packets are staging artifacts and do not modify processing outputs or confirmed project memory.",
            "This source-packet builder does not run live lookup or parse full text itself; values may originate from built-in generic libraries, user-provided data, local libraries, project literature, or separately confirmed search connectors.",
        ],
    }
    write_yaml(output_path, packet)
    provenance_path = write_provenance_entry(
        root,
        workflow="ftir_assignment_source_packet",
        inputs={"records": [library_ref] if library_ref else [], "files": []},
        outputs={"records": [packet_ref], "files": []},
        parameters={
            "candidate_count": len(selected),
            "template": template_mode,
            "builtin_library": builtin_library if builtin_mode else None,
            "filters": packet["filters"],
            "auto_applied": False,
        },
        warnings=warnings,
        source_refs=reference_ids,
        created_at=created_at,
    )
    packet["provenance_ref"] = _relative_to_root(root, provenance_path)
    write_yaml(output_path, packet)
    return {
        "source_packet": str(output_path),
        "source_packet_id": source_packet_id,
        "status": status,
        "candidate_count": len(selected),
        "reference_ids": reference_ids,
        "reference_seed_count": len(reference_seeds),
        "warnings": warnings,
        "provenance": str(provenance_path),
    }


def _ftir_assignment_columns() -> list[str]:
    return [
        "candidate_id",
        "assignment_type",
        "assignment_label",
        "band_label",
        "status",
        "requires_user_review",
        "auto_applied",
        "wavenumber_window_cm1",
        "expected_feature",
        "matched_band_ids",
        "matched_wavenumbers_cm-1",
        "source_summary",
        "reference_ids",
        "unresolved_reference_ids",
        "applicability_notes",
        "material_scope",
        "sample_scope",
        "confidence",
        "missing_fields",
        "caveats",
    ]


def _candidate_window(candidate: dict[str, Any]) -> tuple[float | None, float | None]:
    window = candidate.get("wavenumber_window_cm1", candidate.get("wavenumber_window_cm-1", candidate.get("window_cm1")))
    if isinstance(window, list | tuple) and len(window) >= 2:
        lower = _candidate_number({"lower": window[0]}, "lower")
        upper = _candidate_number({"upper": window[1]}, "upper")
    elif isinstance(window, dict):
        lower = _candidate_number(window, "min", "lower", "low", "start_cm1", "from_cm1")
        upper = _candidate_number(window, "max", "upper", "high", "end_cm1", "to_cm1")
    else:
        lower = _candidate_number(candidate, "wavenumber_min_cm1", "min_cm1", "lower_cm1")
        upper = _candidate_number(candidate, "wavenumber_max_cm1", "max_cm1", "upper_cm1")
    if lower is None or upper is None:
        return None, None
    return (min(lower, upper), max(lower, upper))


def _expected_feature_matches(expected_feature: str, band_type: str) -> bool:
    if expected_feature in {"", "any"}:
        return True
    if expected_feature == "absorbance_maximum":
        return band_type == "absorbance_maximum"
    if expected_feature == "transmittance_minimum":
        return band_type == "transmittance_minimum"
    return False


def _match_ftir_bands(bands: pd.DataFrame, lower: float, upper: float, expected_feature: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    if bands.empty:
        return matches
    for _, row in bands.iterrows():
        try:
            wavenumber = float(row["wavenumber_cm-1"])
        except (KeyError, TypeError, ValueError):
            continue
        band_type = str(row.get("band_type") or "")
        if lower <= wavenumber <= upper and _expected_feature_matches(expected_feature, band_type):
            matches.append(
                {
                    "band_id": str(row.get("band_id") or ""),
                    "wavenumber_cm-1": wavenumber,
                    "prominence": float(row.get("prominence", 0.0)),
                    "band_type": band_type,
                    "possible_band_family": str(row.get("possible_band_family") or ""),
                }
            )
    return matches


def _normalize_ftir_assignment_candidate(
    raw_candidate: Any,
    *,
    suggestion_id: str,
    number: int,
    bands: pd.DataFrame,
    registered_references: set[str],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(raw_candidate, dict):
        candidate_id = f"{suggestion_id}-cand-{number:03d}"
        warnings.append(
            _warning(
                "ftir_assignment_suggestion_ignored",
                "An FTIR assignment suggestion candidate was not a mapping and was recorded as invalid.",
                severity="medium",
                candidate_id=candidate_id,
            )
        )
        return {
            "candidate_id": candidate_id,
            "assignment_type": "unknown",
            "status": "invalid_candidate_mapping",
            "requires_user_review": True,
            "auto_applied": False,
            "missing_fields": ["candidate_mapping"],
        }

    candidate_id = str(raw_candidate.get("candidate_id") or raw_candidate.get("assignment_id") or f"{suggestion_id}-cand-{number:03d}")
    assignment_type = _normalize_assignment_type(raw_candidate.get("assignment_type") or raw_candidate.get("type"))
    assignment_label = str(raw_candidate.get("assignment_label") or raw_candidate.get("functional_group") or raw_candidate.get("band_assignment") or "").strip()
    band_label = str(raw_candidate.get("band_label") or assignment_label).strip()
    reference_ids = _coerce_string_list(raw_candidate.get("reference_ids"))
    applicability_notes = _coerce_string_list(raw_candidate.get("applicability_notes"))
    caveats = _coerce_string_list(raw_candidate.get("caveats"))
    source_summary = str(raw_candidate.get("source_summary") or raw_candidate.get("reference_summary") or "").strip()
    confidence = str(raw_candidate.get("confidence") or "low").strip().lower()
    expected_feature = _normalize_expected_feature(raw_candidate.get("expected_feature"))
    lower, upper = _candidate_window(raw_candidate)
    unresolved_reference_ids = [reference_id for reference_id in reference_ids if reference_id not in registered_references]
    missing_fields: list[str] = []
    if not assignment_label:
        missing_fields.append("assignment_label")
    if lower is None or upper is None:
        missing_fields.append("wavenumber_window_cm1")
    if not source_summary:
        missing_fields.append("source_summary")
    if not reference_ids:
        missing_fields.append("reference_ids")
    if not applicability_notes:
        missing_fields.append("applicability_notes")
    if expected_feature not in {"any", "absorbance_maximum", "transmittance_minimum"}:
        missing_fields.append("expected_feature")

    matches = _match_ftir_bands(bands, lower, upper, expected_feature) if lower is not None and upper is not None else []
    if missing_fields:
        status = "invalid_missing_required_metadata"
    elif unresolved_reference_ids:
        status = "needs_reference_registration"
    elif not matches:
        status = "no_feature_match"
    else:
        status = "ready_for_user_review"

    candidate: dict[str, Any] = {
        "candidate_id": candidate_id,
        "assignment_type": assignment_type,
        "assignment_label": assignment_label,
        "band_label": band_label,
        "status": status,
        "requires_user_review": True,
        "auto_applied": False,
        "wavenumber_window_cm1": [lower, upper] if lower is not None and upper is not None else [],
        "expected_feature": expected_feature,
        "matched_bands": matches,
        "matched_band_ids": [match["band_id"] for match in matches if match.get("band_id")],
        "matched_wavenumbers_cm-1": [match["wavenumber_cm-1"] for match in matches],
        "source_summary": source_summary,
        "reference_ids": reference_ids,
        "unresolved_reference_ids": unresolved_reference_ids,
        "applicability_notes": applicability_notes,
        "material_scope": str(raw_candidate.get("material_scope") or "").strip() or None,
        "sample_scope": str(raw_candidate.get("sample_scope") or "").strip() or None,
        "confidence": confidence,
        "missing_fields": missing_fields,
        "caveats": caveats,
    }
    if unresolved_reference_ids:
        warnings.append(
            _warning(
                "ftir_assignment_suggestion_reference_unresolved",
                "An FTIR assignment suggestion cites reference_ids that are not registered in the project reference index.",
                severity="medium",
                candidate_id=candidate_id,
                unresolved_reference_ids=unresolved_reference_ids,
            )
        )
    if missing_fields:
        warnings.append(
            _warning(
                "ftir_assignment_suggestion_missing_metadata",
                "An FTIR assignment suggestion is missing required source, band-window, or applicability metadata.",
                severity="medium",
                candidate_id=candidate_id,
                missing_fields=missing_fields,
            )
        )
    if status == "no_feature_match":
        warnings.append(
            _warning(
                "ftir_assignment_suggestion_no_feature_match",
                "An FTIR assignment candidate did not match any detected FTIR band in the processed feature table.",
                severity="low",
                candidate_id=candidate_id,
                wavenumber_window_cm1=candidate["wavenumber_window_cm1"],
            )
        )
    return candidate


def suggest_ftir_assignments(
    root: Path,
    *,
    project_id: str,
    ftir_metadata_path: Path,
    source_path: Path,
    related_records: list[str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    source_packet = read_yaml(source_path)
    raw_candidates = _ftir_assignment_source_candidates(source_packet)
    ftir_metadata = read_yaml(ftir_metadata_path)
    peak_table_ref = ftir_metadata.get("outputs", {}).get("peak_table")
    if not peak_table_ref:
        raise FTIRProcessingError("FTIR metadata does not include outputs.peak_table for assignment matching")
    peak_table_path = root / str(peak_table_ref)
    if not peak_table_path.exists():
        raise FTIRProcessingError(f"FTIR peak table not found: {peak_table_ref}")
    bands = pd.read_csv(peak_table_path)

    day = _created_day(created_at)
    timestamp = created_at or EARecord.now_iso()
    suggestion_id = next_id(root, "suggestion", day)
    output_dir = root / "suggestions" / "ftir" / suggestion_id
    record_path = output_dir / "ftir_assignment_suggestions.yml"
    table_path = output_dir / "ftir_assignment_suggestions.csv"
    for path in [record_path, table_path]:
        assert_not_raw_output_path(root, path)

    warnings: list[dict[str, Any]] = []
    if not raw_candidates:
        warnings.append(
            _warning(
                "ftir_assignment_suggestion_empty_source",
                "No FTIR assignment candidates were found in the source packet.",
                severity="medium",
            )
        )
    registered_references = _registered_reference_ids(root)
    candidates = [
        _normalize_ftir_assignment_candidate(
            candidate,
            suggestion_id=suggestion_id,
            number=index,
            bands=bands,
            registered_references=registered_references,
            warnings=warnings,
        )
        for index, candidate in enumerate(raw_candidates, start=1)
    ]
    table = pd.DataFrame(candidates, columns=_ftir_assignment_columns())
    for column in [
        "wavenumber_window_cm1",
        "matched_band_ids",
        "matched_wavenumbers_cm-1",
        "reference_ids",
        "unresolved_reference_ids",
        "applicability_notes",
        "missing_fields",
        "caveats",
    ]:
        if column in table.columns:
            table[column] = table[column].apply(lambda value: "; ".join(str(item) for item in value) if isinstance(value, list) else value)

    ready_count = sum(1 for candidate in candidates if candidate.get("status") == "ready_for_user_review")
    unresolved_count = sum(1 for candidate in candidates if candidate.get("status") == "needs_reference_registration")
    no_match_count = sum(1 for candidate in candidates if candidate.get("status") == "no_feature_match")
    invalid_count = sum(1 for candidate in candidates if str(candidate.get("status", "")).startswith("invalid"))
    if ready_count:
        status = "ready_for_user_review"
    elif unresolved_count:
        status = "needs_reference_registration"
    elif no_match_count:
        status = "no_feature_match"
    else:
        status = "needs_source_metadata"

    source_ref = _relative_to_root(root, source_path)
    metadata_ref = _relative_to_root(root, ftir_metadata_path)
    record_ref = _relative_to_root(root, record_path)
    table_ref = _relative_to_root(root, table_path)
    related_records = related_records or []
    all_reference_ids = sorted({reference_id for candidate in candidates for reference_id in candidate.get("reference_ids", [])})
    record = {
        "schema_version": "0.2",
        "suggestion_id": suggestion_id,
        "project_id": project_id,
        "status": status,
        "created_at": timestamp,
        "updated_at": timestamp,
        "source": "ea.ftir.assignment_suggestions:v0.2",
        "source_packet_ref": source_ref,
        "ftir_metadata_ref": metadata_ref,
        "feature_table_ref": str(peak_table_ref),
        "table_ref": table_ref,
        "candidate_count": len(candidates),
        "ready_for_user_review_count": ready_count,
        "needs_reference_registration_count": unresolved_count,
        "no_feature_match_count": no_match_count,
        "invalid_count": invalid_count,
        "candidates": candidates,
        "related_records": related_records,
        "reference_ids": all_reference_ids,
        "warnings": warnings,
        "next_steps": [
            "Register or correct unresolved reference_ids before using source-backed assignment suggestions.",
            "Ask the user to review ready FTIR candidates before citing them as report interpretations or memory candidates.",
            "Use matched band IDs and source/applicability notes when discussing possible functional groups; do not treat a band match alone as composition proof.",
        ],
        "boundaries": [
            "FTIR assignment suggestions are advisory and auto_applied is always false.",
            "This suggestion-record step does not run live lookup, alter processing outputs, prove functional groups/composition, or write confirmed memory.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(table_path, index=False)
    write_yaml(record_path, record)
    provenance_path = write_provenance_entry(
        root,
        workflow="ftir_assignment_suggestion",
        inputs={"records": [source_ref, metadata_ref, *related_records], "files": [str(peak_table_ref)]},
        outputs={"records": [record_ref, table_ref], "files": []},
        parameters={"candidate_count": len(candidates), "auto_applied": False},
        warnings=warnings,
        source_refs=all_reference_ids,
        created_at=created_at,
    )
    record["provenance_ref"] = _relative_to_root(root, provenance_path)
    write_yaml(record_path, record)
    return {
        "suggestion_id": suggestion_id,
        "record": str(record_path),
        "table": str(table_path),
        "status": status,
        "candidate_count": len(candidates),
        "ready_for_user_review_count": ready_count,
        "needs_reference_registration_count": unresolved_count,
        "no_feature_match_count": no_match_count,
        "invalid_count": invalid_count,
        "warnings": warnings,
    }


def _confirmed_frame(path: Path, request: FTIRProcessingRequest) -> pd.DataFrame:
    frame, _ = _read_spectrum(path)
    frame.columns = [str(column) for column in frame.columns]
    if request.x_column not in frame.columns or request.y_column not in frame.columns:
        raise FTIRProcessingError("Confirmed x/y columns are not present in the raw file")
    if request.x_unit not in {"cm^-1", "unknown"}:
        raise FTIRProcessingError("FTIR x_unit must be user-confirmed as cm^-1 or unknown")
    if request.signal_mode not in {"absorbance", "transmittance"}:
        raise FTIRProcessingError("FTIR signal_mode must be user-confirmed as absorbance or transmittance")
    data = frame[[request.x_column, request.y_column]].copy()
    data.columns = ["wavenumber_cm-1", "raw_signal"]
    data["wavenumber_cm-1"] = pd.to_numeric(data["wavenumber_cm-1"], errors="coerce")
    data["raw_signal"] = pd.to_numeric(data["raw_signal"], errors="coerce")
    data = data.dropna().sort_values("wavenumber_cm-1").reset_index(drop=True)
    if data.empty:
        raise FTIRProcessingError("Confirmed FTIR columns contain no numeric data")
    return data


def _rolling_quantile_baseline(signal: np.ndarray, parameters: dict[str, Any]) -> tuple[np.ndarray, list[dict[str, Any]]]:
    baseline = parameters.get("baseline_correction", {})
    window_points, window_adjusted = _coerce_int(baseline.get("window_points"), 101, minimum=3)
    quantile, quantile_adjusted = _coerce_float(baseline.get("quantile"), 0.05, minimum=0.0, maximum=1.0)
    adjusted = window_adjusted or quantile_adjusted
    if window_points > signal.size:
        window_points = signal.size
        adjusted = True
    if window_points % 2 == 0:
        window_points = max(3, window_points - 1)
        adjusted = True
    warnings: list[dict[str, Any]] = []
    if adjusted:
        warnings.append(
            _warning(
                "ftir_baseline_parameter_adjusted",
                "Invalid FTIR rolling-quantile baseline parameters were adjusted.",
                window_points=window_points,
                quantile=quantile,
            )
        )
    if signal.size < 3:
        warnings.append(_warning("ftir_baseline_skipped", "FTIR baseline correction skipped because the spectrum has fewer than three points.", severity="medium"))
        return np.zeros_like(signal), warnings
    series = pd.Series(signal)
    baseline_values = series.rolling(window_points, center=True, min_periods=1).quantile(quantile).to_numpy(dtype=float)
    warnings.append(
        _warning(
            "ftir_baseline_applied",
            "Rolling-quantile baseline correction was applied before FTIR peak detection.",
            method="rolling_quantile",
            window_points=window_points,
            quantile=quantile,
        )
    )
    return baseline_values, warnings


def _apply_processing(
    data: pd.DataFrame,
    parameters: dict[str, Any],
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    processed = data.copy()
    warnings: list[dict[str, Any]] = []
    signal = processed["raw_signal"].to_numpy(dtype=float)
    processed["baseline_signal"] = np.nan

    if parameters.get("baseline_correction", {}).get("enabled", False):
        baseline, baseline_warnings = _rolling_quantile_baseline(signal, parameters)
        signal = signal - baseline
        processed["baseline_signal"] = baseline
        warnings.extend(baseline_warnings)

    smoothing = parameters.get("smoothing", {})
    if smoothing.get("enabled", False):
        window_length, window_adjusted = _coerce_int(smoothing.get("window_length"), 9, minimum=3)
        polyorder, poly_adjusted = _coerce_int(smoothing.get("polyorder"), 2, minimum=1)
        max_window = signal.size if signal.size % 2 == 1 else signal.size - 1
        adjusted = window_adjusted or poly_adjusted
        if window_length > max_window:
            window_length = max_window
            adjusted = True
        if window_length % 2 == 0:
            window_length += 1
            if window_length > max_window:
                window_length = max_window
            adjusted = True
        if polyorder >= window_length:
            polyorder = max(1, window_length - 1)
            adjusted = True
        if adjusted:
            warnings.append(
                _warning(
                    "ftir_smoothing_parameter_adjusted",
                    "Invalid Savitzky-Golay parameters were adjusted for FTIR processing.",
                    window_length=window_length,
                    polyorder=polyorder,
                )
            )
        if signal.size >= 3 and window_length >= 3:
            signal = np.asarray(savgol_filter(signal, window_length=window_length, polyorder=polyorder, mode="interp"), dtype=float)
            processed["smoothed_signal"] = signal
            warnings.append(
                _warning(
                    "ftir_smoothing_applied",
                    "Savitzky-Golay smoothing was applied before FTIR normalization and peak detection.",
                    method="savitzky_golay",
                    window_length=window_length,
                    polyorder=polyorder,
                )
            )
        else:
            warnings.append(_warning("ftir_smoothing_skipped", "FTIR smoothing skipped because the spectrum has fewer than three points.", severity="medium"))

    if parameters.get("normalization", {}).get("enabled", True):
        max_value = float(np.max(np.abs(signal)))
        if max_value > 0:
            signal = signal / max_value
        warnings.append(_warning("ftir_normalization_applied", "FTIR signal normalized by processing parameters."))
    processed["processed_signal"] = signal
    return processed, warnings


def _band_family(wavenumber: float, parameters: dict[str, Any]) -> dict[str, str]:
    if not parameters.get("band_assignment", {}).get("enabled", True):
        return {"family": "", "confidence": "", "source": "", "notes": "band assignment disabled by processing parameters"}
    for window in FTIR_BAND_WINDOWS:
        if float(window["min"]) <= wavenumber <= float(window["max"]):
            return {
                "family": str(window["family"]),
                "confidence": "low",
                "source": str(parameters.get("band_assignment", {}).get("source") or "ea.ftir.builtin_band_windows:v0.2"),
                "notes": str(window["notes"]),
            }
    return {
        "family": "unassigned FTIR band region",
        "confidence": "insufficient",
        "source": str(parameters.get("band_assignment", {}).get("source") or "ea.ftir.builtin_band_windows:v0.2"),
        "notes": "No built-in broad band window matched this wavenumber.",
    }


def _detect_bands(processed: pd.DataFrame, parameters: dict[str, Any], signal_mode: str) -> pd.DataFrame:
    y = processed["processed_signal"].to_numpy(dtype=float)
    detection_signal = y if signal_mode == "absorbance" else -y
    peak_params = parameters.get("peak_detection", {})
    prominence = peak_params.get("prominence", "auto")
    distance = peak_params.get("distance", "auto")
    max_bands, _ = _coerce_int(peak_params.get("max_bands"), 12, minimum=1)
    if prominence == "auto":
        prominence = max(float(np.ptp(detection_signal)) * 0.08, 0.02)
    if distance == "auto":
        distance = max(len(detection_signal) // 100, 1)
    peaks, properties = find_peaks(detection_signal, prominence=prominence, distance=distance)
    ranked = sorted(
        [(int(peak), float(properties["prominences"][index])) for index, peak in enumerate(peaks)],
        key=lambda item: item[1],
        reverse=True,
    )[:max_bands]
    ranked.sort(key=lambda item: float(processed.iloc[item[0]]["wavenumber_cm-1"]), reverse=True)
    rows = []
    for index, (peak_index, peak_prominence) in enumerate(ranked, start=1):
        row = processed.iloc[peak_index]
        wavenumber = float(row["wavenumber_cm-1"])
        family = _band_family(wavenumber, parameters)
        rows.append(
            {
                "band_id": f"ftir-band-{index:03d}",
                "wavenumber_cm-1": wavenumber,
                "raw_signal": float(row["raw_signal"]),
                "processed_signal": float(row["processed_signal"]),
                "detection_height": float(detection_signal[peak_index]),
                "prominence": peak_prominence,
                "method": "scipy_find_peaks",
                "signal_mode": signal_mode,
                "band_type": "absorbance_maximum" if signal_mode == "absorbance" else "transmittance_minimum",
                "possible_band_family": family["family"],
                "assignment_confidence": family["confidence"],
                "assignment_source": family["source"],
                "notes": family["notes"],
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "band_id",
            "wavenumber_cm-1",
            "raw_signal",
            "processed_signal",
            "detection_height",
            "prominence",
            "method",
            "signal_mode",
            "band_type",
            "possible_band_family",
            "assignment_confidence",
            "assignment_source",
            "notes",
        ],
    )


_FTIR_CONTEXT_SECTIONS = ("instrument_accessory", "atmosphere", "sample_preparation", "background", "reference")


def _has_context_payload(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_has_context_payload(item) for item in value.values())
    if isinstance(value, list | tuple):
        return any(_has_context_payload(item) for item in value)
    return True


def _context_section(params: dict[str, Any], name: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    value = params.get(name, {})
    if isinstance(value, dict):
        return deepcopy(value), None
    return (
        {},
        _warning(
            "ftir_context_section_ignored",
            "An FTIR context-record section was ignored because it was not a mapping.",
            severity="medium",
            section=name,
        ),
    )


def _context_notes(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any] | None]:
    notes = params.get("correction_notes", [])
    if isinstance(notes, list):
        return deepcopy(notes), None
    if isinstance(notes, tuple):
        return list(notes), None
    if isinstance(notes, str) and notes.strip():
        return [notes], None
    return (
        [],
        _warning(
            "ftir_context_notes_ignored",
            "FTIR context notes were ignored because they were not a list or non-empty string.",
            severity="medium",
        ),
    )


def _record_context(parameters: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    params = parameters.get("context_record", {})
    if not isinstance(params, dict) or not params.get("enabled", False):
        return None, []
    warnings: list[dict[str, Any]] = []
    sections: dict[str, dict[str, Any]] = {}
    for name in _FTIR_CONTEXT_SECTIONS:
        section, warning = _context_section(params, name)
        sections[name] = section
        if warning:
            warnings.append(warning)
    notes, notes_warning = _context_notes(params)
    if notes_warning:
        warnings.append(notes_warning)

    reviewed_fields = [name for name, section in sections.items() if _has_context_payload(section)]
    if _has_context_payload(notes):
        reviewed_fields.append("correction_notes")
    has_reviewed_context = bool(reviewed_fields)
    if not has_reviewed_context:
        warnings.append(
            _warning(
                "ftir_context_record_empty",
                "FTIR context_record was enabled, but no reviewed method/context metadata was supplied.",
                severity="medium",
            )
        )
    source = str(params.get("source") or "ea.ftir.context_record:v0.2")
    return (
        {
            "enabled": True,
            "status": "reviewed_context_recorded" if has_reviewed_context else "enabled_without_reviewed_context",
            "method": str(params.get("method") or "reviewed_metadata_record"),
            "assignment_source": source,
            "confidence": "low" if has_reviewed_context else "insufficient",
            "reviewed_context_fields": reviewed_fields,
            **sections,
            "correction_notes": notes,
            "warnings": warnings,
            "boundary": "FTIR context record is metadata/provenance only; no automatic background, reference, ATR, or atmosphere correction was applied.",
        },
        warnings,
    )


def _analyze_bands(bands: pd.DataFrame, context_record: dict[str, Any] | None = None) -> dict[str, Any]:
    analysis: dict[str, Any] = {
        "band_count": int(len(bands)),
        "strongest_bands": [],
        "context_record": context_record,
        "possible_interpretations": [],
    }
    if bands.empty:
        analysis["possible_interpretations"].append(
            {
                "text": "No stable FTIR band was detected by the current automatic settings.",
                "confidence": "insufficient",
                "evidence": [],
            }
        )
    else:
        strongest = bands.sort_values("prominence", ascending=False).head(6)
        analysis["strongest_bands"] = [
            {
                "band_id": str(row["band_id"]),
                "wavenumber_cm-1": float(row["wavenumber_cm-1"]),
                "possible_band_family": str(row["possible_band_family"]),
                "assignment_confidence": str(row["assignment_confidence"]),
                "assignment_source": str(row["assignment_source"]),
            }
            for _, row in strongest.iterrows()
        ]
        for family, family_rows in strongest.groupby("possible_band_family", sort=False):
            evidence = [str(value) for value in family_rows["band_id"].head(3)]
            confidence_values = [str(value) for value in family_rows["assignment_confidence"] if str(value)]
            confidence = "low" if "low" in confidence_values else "insufficient"
            source_values = [str(value) for value in family_rows["assignment_source"] if str(value)]
            analysis["possible_interpretations"].append(
                {
                    "text": f"Detected FTIR feature(s) fall in the broad {family} window; treat this as a screening hint, not a definitive chemical assignment.",
                    "confidence": confidence,
                    "evidence": evidence,
                    "assignment_source": source_values[0] if source_values else "",
                }
            )
    if context_record and context_record.get("status") == "reviewed_context_recorded":
        fields = ", ".join(str(value) for value in context_record.get("reviewed_context_fields", [])) or "FTIR context"
        analysis["possible_interpretations"].append(
            {
                "text": (
                    f"Reviewed FTIR method/context metadata was recorded for {fields}. Use it to interpret band screening hints, "
                    "but do not treat the metadata record as an automatic correction or a standalone chemical assignment."
                ),
                "confidence": context_record.get("confidence", "low"),
                "evidence": ["context_record"],
                "assignment_source": context_record.get("assignment_source", "ea.ftir.context_record:v0.2"),
            }
        )
    return analysis


def _created_day(created_at: str | None) -> str | None:
    return created_at[:10] if created_at else None


def _uses_v0_2_project_ids(project_id: str) -> bool:
    return project_id.startswith("prj-")


def _plot_ftir(processed: pd.DataFrame, bands: pd.DataFrame, output: Path, signal_mode: str, *, footer: str | None = None) -> None:
    fig, ax = styled_subplots(figsize=(6.0, 4.0))
    ax.plot(
        processed["wavenumber_cm-1"],
        processed["processed_signal"],
        color=NATURE_LIKE_COLORS["blue"],
        linewidth=1.2,
        label="Processed signal",
    )
    if not bands.empty:
        ax.scatter(
            bands["wavenumber_cm-1"],
            bands["processed_signal"],
            color=NATURE_LIKE_COLORS["black"],
            s=18,
            label="Detected bands",
            zorder=3,
        )
        for _, band in bands.sort_values("prominence", ascending=False).head(8).iterrows():
            ax.annotate(
                f"{float(band['wavenumber_cm-1']):.0f}",
                (float(band["wavenumber_cm-1"]), float(band["processed_signal"])),
                textcoords="offset points",
                xytext=(0, 6),
                ha="center",
                fontsize=7,
            )
    ax.invert_xaxis()
    ylabel = "Absorbance (a.u.)" if signal_mode == "absorbance" else "Transmittance (a.u.)"
    style_axis(
        ax,
        title="FTIR spectrum",
        xlabel="Wavenumber (cm^-1)",
        ylabel=ylabel,
    )
    save_styled_figure(fig, output, footer=footer)


def process_ftir_result(
    root: Path,
    *,
    characterization_metadata_path: Path,
    project_id: str,
    sample_refs: list[str],
    request: FTIRProcessingRequest,
    created_at: str | None = None,
) -> Path:
    metadata = read_yaml(characterization_metadata_path)
    require_confirmed_review(root, request.column_review_ref)
    require_confirmed_review(root, request.parameter_review_ref)
    raw_path = root / metadata["project_raw_path"]
    inspection = inspect_ftir_file(raw_path)
    if inspection.file_kind != "ftir":
        raise FTIRProcessingError(f"File is {inspection.file_kind}, not FTIR")

    parameters = _merge_parameters(request.processing_parameters)
    processed, processing_warnings = _apply_processing(_confirmed_frame(raw_path, request), parameters)
    bands = _detect_bands(processed, parameters, request.signal_mode)
    context_record, context_warnings = _record_context(parameters)
    band_analysis = _analyze_bands(bands, context_record)
    day = _created_day(created_at)
    project_slug = infer_project_slug(project_id)
    if _uses_v0_2_project_ids(project_id):
        result_id = next_standard_id(root, "result", project_slug, method="ftir", day=day)
        figure_id = next_standard_id(root, "figure", project_slug, method="ftir", day=day)
    else:
        result_id = next_id(root, "ftir_result", day)
        figure_id = None
    sample_dir = sample_refs[0] if sample_refs else "unmapped-sample"
    output_dir = root / "processed" / sample_dir / "ftir" / result_id
    processed_csv = output_dir / "ftir_processed.csv"
    bands_csv = output_dir / "ftir_bands.csv"
    context_yml = output_dir / "ftir_context.yml"
    figure_name = f"{figure_id}.png" if figure_id else "ftir_plot.png"
    figure = output_dir / figure_name
    result_metadata = output_dir / "ftir_metadata.yml"
    for output in [processed_csv, bands_csv, context_yml, figure, result_metadata]:
        assert_not_raw_output_path(root, output)

    output_dir.mkdir(parents=True, exist_ok=True)
    processed.to_csv(processed_csv, index=False)
    bands.to_csv(bands_csv, index=False)
    context_ref: str | None = None
    if context_record is not None:
        context_ref = str(context_yml.relative_to(root))
        context_record["record_ref"] = context_ref
        write_yaml(context_yml, context_record)
        if band_analysis.get("context_record"):
            band_analysis["context_record"]["record_ref"] = context_ref
    _plot_ftir(processed, bands, figure, request.signal_mode, footer=figure_footer(figure_id, None) if figure_id else None)

    warnings: list[Any] = []
    if request.x_unit == "unknown":
        warnings.append(_warning("ftir_x_unit_unknown", "FTIR x unit remains unknown after confirmation.", severity="medium"))
    warnings.extend(processing_warnings)
    warnings.extend(context_warnings)
    outputs = {
        "figure": str(figure.relative_to(root)),
        "peak_table": str(bands_csv.relative_to(root)),
        "processed_csv": str(processed_csv.relative_to(root)),
        "metadata": str(result_metadata.relative_to(root)),
    }
    if context_ref:
        outputs["context_record"] = context_ref
    result = FTIRProcessingResult(
        ftir_result_id=result_id,
        result_id=result_id,
        project_id=project_id,
        characterization_file_ref=metadata["characterization_id"],
        sample_refs=sample_refs,
        status="warning" if warnings else "success",
        x_column=request.x_column,
        y_column=request.y_column,
        x_unit=request.x_unit,  # type: ignore[arg-type]
        signal_mode=request.signal_mode,  # type: ignore[arg-type]
        processing_parameters=parameters,
        outputs=outputs,
        peak_analysis=band_analysis,
        figure_id=figure_id,
        warnings=warnings,
        review_refs=[request.column_review_ref, request.parameter_review_ref],
        created_at=created_at or EARecord.now_iso(),
        updated_at=created_at or EARecord.now_iso(),
    )
    write_yaml(result_metadata, result.model_dump(exclude_none=True))
    provenance_files = [
        str(processed_csv.relative_to(root)),
        str(bands_csv.relative_to(root)),
        str(figure.relative_to(root)),
    ]
    if context_ref:
        provenance_files.append(context_ref)
    provenance_path = write_provenance_entry(
        root,
        workflow="ftir_processing",
        inputs={
            "records": [str(characterization_metadata_path.relative_to(root))],
            "files": [metadata["project_raw_path"]],
        },
        outputs={
            "records": [str(result_metadata.relative_to(root))],
            "files": provenance_files,
        },
        parameters={
            "x_column": request.x_column,
            "y_column": request.y_column,
            "x_unit": request.x_unit,
            "signal_mode": request.signal_mode,
            "processing_parameters": parameters,
        },
        review_refs=[request.column_review_ref, request.parameter_review_ref],
        warnings=warnings,
        scripts=[{"path": "src/ea/ftir/service.py", "version": "0.2.0"}],
        created_at=created_at,
    )
    result_data = read_yaml(result_metadata)
    result_data["provenance_refs"] = [provenance_path.stem]
    write_yaml(result_metadata, result_data)
    if figure_id:
        register_figure(
            root,
            figure_id=figure_id,
            path=str(figure.relative_to(root)),
            report_id=None,
            result_id=result_id,
            raw_data_ids=[metadata["characterization_id"]],
            sample_ids=sample_refs,
            experiment_ids=metadata.get("experiment_refs", []),
            generation={
                "style_profile": NATURE_LIKE_STYLE_PROFILE,
                "script": "src/ea/ftir/service.py",
                "parameters": {
                    "x_column": request.x_column,
                    "y_column": request.y_column,
                    "x_unit": request.x_unit,
                    "signal_mode": request.signal_mode,
                    "processing_parameters": parameters,
                },
            },
            caption="FTIR spectrum with processed signal, detected bands, and broad band-family screening hints.",
            purpose="ftir_analysis_report",
            style_profile=NATURE_LIKE_STYLE_PROFILE,
            source_data_refs=[
                str(processed_csv.relative_to(root)),
                str(bands_csv.relative_to(root)),
            ]
            + ([context_ref] if context_ref else []),
        )
    return result_metadata
