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
    source_data_entry,
    style_axis,
    styled_subplots,
)
from ea.literature.source_packet_manifest import (
    SourcePacketManifestError,
    confirmed_source_packet_library,
)
from ea.memory import propose_memory_candidate
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
    text = (
        resources.files("ea.ftir")
        .joinpath("assignment_libraries.yml")
        .read_text(encoding="utf-8")
    )
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
        raise FTIRProcessingError(
            f"Unknown built-in FTIR assignment library: {name}. Available libraries: {available}"
        )
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


def _warning(
    code: str, message: str, severity: str = "low", **details: Any
) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message, "severity": severity}
    payload.update(details)
    return payload


def _coerce_int(
    value: Any, default: int, *, minimum: int | None = None
) -> tuple[int, bool]:
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return default, True
    if minimum is not None and coerced < minimum:
        return default, True
    return coerced, False


def _coerce_float(
    value: Any,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> tuple[float, bool]:
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
    looks_like_wavenumber = "cm" in metadata_text or (
        350 <= x_min <= 4500 and 350 <= x_max <= 4500
    )
    looks_like_ftir = (
        "FTIR" in path_text
        or "INFRARED" in path_text
        or "/IR/" in path_text
        or (x_min <= 800 and x_max >= 2500)
    )
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
        raw_candidates = (
            source_packet.get("candidates")
            or source_packet.get("assignments")
            or source_packet.get("suggestions")
            or []
        )
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
            "applicability_notes": [
                "TODO: describe when this window applies and known overlaps."
            ],
            "reference_ids": ["TODO-registered-reference-id"],
            "confidence": "low",
            "caveats": [
                "Template candidate only; fill band window and source metadata before running suggest-assignments."
            ],
        }
    ]


def _candidate_identity(candidate: dict[str, Any]) -> str:
    return str(
        candidate.get("candidate_id")
        or candidate.get("assignment_id")
        or candidate.get("suggestion_id")
        or ""
    ).strip()


def _normalize_assignment_type(value: Any) -> str:
    return (
        str(value or "functional_group")
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )


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
    if (
        assignment_types
        and _normalize_assignment_type(
            candidate.get("assignment_type") or candidate.get("type")
        )
        not in assignment_types
    ):
        return False
    if material_scopes:
        material_scope = str(candidate.get("material_scope") or "").strip().lower()
        if not any(scope in material_scope for scope in material_scopes):
            return False
    return True


def _material_scope_terms(value: Any) -> list[str]:
    terms: list[str] = []
    for item in _coerce_string_list(value):
        for part in str(item).replace(",", ";").split(";"):
            term = part.strip()
            if term:
                terms.append(term)
    return terms


def _candidate_window_overlaps(
    candidate: dict[str, Any], lower: float | None, upper: float | None
) -> bool:
    if lower is None and upper is None:
        return True
    candidate_lower, candidate_upper = _candidate_window(candidate)
    if candidate_lower is None or candidate_upper is None:
        return False
    if lower is not None and candidate_upper < lower:
        return False
    if upper is not None and candidate_lower > upper:
        return False
    return True


def _ftir_discovery_candidate_summary(raw_candidate: dict[str, Any]) -> dict[str, Any]:
    lower, upper = _candidate_window(raw_candidate)
    return {
        "candidate_id": _candidate_identity(raw_candidate),
        "assignment_type": _normalize_assignment_type(
            raw_candidate.get("assignment_type") or raw_candidate.get("type")
        ),
        "assignment_label": str(
            raw_candidate.get("assignment_label")
            or raw_candidate.get("functional_group")
            or raw_candidate.get("band_assignment")
            or ""
        ).strip()
        or None,
        "band_label": str(
            raw_candidate.get("band_label")
            or raw_candidate.get("assignment_label")
            or ""
        ).strip()
        or None,
        "wavenumber_window_cm1": [lower, upper]
        if lower is not None and upper is not None
        else [],
        "expected_feature": _normalize_expected_feature(
            raw_candidate.get("expected_feature")
        ),
        "source_summary": str(
            raw_candidate.get("source_summary")
            or raw_candidate.get("reference_summary")
            or ""
        ).strip(),
        "reference_ids": _coerce_string_list(raw_candidate.get("reference_ids")),
        "applicability_notes": _coerce_string_list(
            raw_candidate.get("applicability_notes")
        ),
        "material_scope": str(raw_candidate.get("material_scope") or "").strip()
        or None,
        "material_scope_terms": _material_scope_terms(
            raw_candidate.get("material_scope")
        ),
        "sample_scope": str(raw_candidate.get("sample_scope") or "").strip() or None,
        "confidence": str(raw_candidate.get("confidence") or "low").strip().lower(),
        "caveats": _coerce_string_list(raw_candidate.get("caveats")),
        "auto_applied": False,
        "requires_user_review": True,
    }


def _ftir_discovery_build_source_command(
    library_id: str, filters: dict[str, Any], candidate_ids: list[str]
) -> str:
    parts = [
        "ea ftir build-assignment-packet /path/to/ea-project --project-id <project-id>",
        "--builtin-library",
        library_id,
    ]
    include_candidates = list(filters["include_candidates"])
    if not include_candidates and (
        filters["wavenumber_min_cm1"] is not None
        or filters["wavenumber_max_cm1"] is not None
    ):
        include_candidates = list(candidate_ids)
    for candidate_id in include_candidates:
        parts.extend(["--include-candidate", candidate_id])
    for assignment_type in filters["assignment_types"]:
        parts.extend(["--assignment-type", assignment_type])
    for material_scope in filters["material_scopes"]:
        parts.extend(["--material-scope", material_scope])
    return " ".join(parts)


def summarize_ftir_assignment_libraries(
    *,
    builtin_libraries: list[str] | None = None,
    include_candidates: list[str] | None = None,
    assignment_types: list[str] | None = None,
    material_scopes: list[str] | None = None,
    wavenumber_min_cm1: float | None = None,
    wavenumber_max_cm1: float | None = None,
) -> dict[str, Any]:
    """Summarize built-in FTIR assignment libraries without creating project artifacts."""

    libraries = _builtin_ftir_assignment_libraries()
    requested_library_ids = [
        str(item).strip() for item in builtin_libraries or [] if str(item).strip()
    ]
    if requested_library_ids:
        unknown = sorted(
            {item for item in requested_library_ids if item not in libraries}
        )
        if unknown:
            available = ", ".join(sorted(libraries)) or "none"
            raise FTIRProcessingError(
                f"Unknown built-in FTIR assignment library: {', '.join(unknown)}. Available libraries: {available}"
            )
        library_ids = sorted(dict.fromkeys(requested_library_ids))
    else:
        library_ids = sorted(libraries)

    range_lower = wavenumber_min_cm1
    range_upper = wavenumber_max_cm1
    if (
        range_lower is not None
        and range_upper is not None
        and range_lower > range_upper
    ):
        range_lower, range_upper = range_upper, range_lower

    include_set = {
        str(item).strip() for item in include_candidates or [] if str(item).strip()
    }
    type_set = {
        _normalize_assignment_type(item)
        for item in assignment_types or []
        if str(item).strip()
    }
    material_set = {
        str(item).strip().lower() for item in material_scopes or [] if str(item).strip()
    }
    filters = {
        "builtin_libraries": library_ids,
        "include_candidates": sorted(include_set),
        "assignment_types": sorted(type_set),
        "material_scopes": sorted(material_set),
        "wavenumber_min_cm1": range_lower,
        "wavenumber_max_cm1": range_upper,
    }

    summaries: list[dict[str, Any]] = []
    total_candidate_count = 0
    matching_candidate_count = 0
    all_assignment_types: set[str] = set()
    all_material_scopes: set[str] = set()
    matching_reference_ids: set[str] = set()
    global_min: float | None = None
    global_max: float | None = None

    for library_id in library_ids:
        library = libraries[library_id]
        raw_candidates = [
            candidate
            for candidate in _ftir_assignment_source_candidates(library)
            if isinstance(candidate, dict)
        ]
        total_candidate_count += len(raw_candidates)
        matching_raw_candidates = [
            candidate
            for candidate in raw_candidates
            if _candidate_matches_filters(
                candidate,
                include_candidates=include_set,
                assignment_types=type_set,
                material_scopes=material_set,
            )
            and _candidate_window_overlaps(candidate, range_lower, range_upper)
        ]
        candidate_summaries = [
            _ftir_discovery_candidate_summary(candidate)
            for candidate in matching_raw_candidates
        ]
        matching_candidate_count += len(candidate_summaries)
        type_counts: dict[str, int] = {}
        library_material_scopes: set[str] = set()
        library_min: float | None = None
        library_max: float | None = None
        for candidate in raw_candidates:
            assignment_type = _normalize_assignment_type(
                candidate.get("assignment_type") or candidate.get("type")
            )
            if assignment_type:
                type_counts[assignment_type] = type_counts.get(assignment_type, 0) + 1
                all_assignment_types.add(assignment_type)
            for scope in _material_scope_terms(candidate.get("material_scope")):
                library_material_scopes.add(scope)
                all_material_scopes.add(scope)
            lower, upper = _candidate_window(candidate)
            if lower is not None and upper is not None:
                library_min = lower if library_min is None else min(library_min, lower)
                library_max = upper if library_max is None else max(library_max, upper)
                global_min = lower if global_min is None else min(global_min, lower)
                global_max = upper if global_max is None else max(global_max, upper)
        candidate_reference_ids = {
            reference_id
            for candidate in matching_raw_candidates
            for reference_id in _coerce_string_list(candidate.get("reference_ids"))
        }
        matching_reference_ids.update(candidate_reference_ids)
        reference_seed_ids = (
            sorted((library.get("reference_seeds") or {}).keys())
            if isinstance(library.get("reference_seeds"), dict)
            else []
        )
        matching_reference_seed_ids = sorted(
            set(reference_seed_ids) & candidate_reference_ids
        )
        summaries.append(
            {
                "library_id": library_id,
                "description": str(library.get("description") or "").strip(),
                "source": str(library.get("source") or "").strip(),
                "total_candidate_count": len(raw_candidates),
                "matching_candidate_count": len(candidate_summaries),
                "assignment_type_counts": dict(sorted(type_counts.items())),
                "material_scopes": sorted(library_material_scopes),
                "wavenumber_range_cm1": [library_min, library_max]
                if library_min is not None and library_max is not None
                else [],
                "reference_seed_count": len(reference_seed_ids),
                "reference_seed_ids": reference_seed_ids,
                "matching_reference_seed_ids": matching_reference_seed_ids,
                "candidate_ids": [
                    candidate["candidate_id"] for candidate in candidate_summaries
                ],
                "candidates": candidate_summaries,
            }
        )

    build_source_commands = [
        _ftir_discovery_build_source_command(
            summary["library_id"], filters, summary["candidate_ids"]
        )
        for summary in summaries
        if summary["matching_candidate_count"] > 0
    ]
    return {
        "schema_version": "0.2",
        "source": "ea.ftir.assignment_library_discovery:v0.2",
        "status": "ready" if matching_candidate_count else "no_matching_candidates",
        "available_builtin_libraries": sorted(libraries),
        "library_count": len(summaries),
        "total_candidate_count": total_candidate_count,
        "matching_candidate_count": matching_candidate_count,
        "available_assignment_types": sorted(all_assignment_types),
        "available_material_scopes": sorted(all_material_scopes),
        "available_wavenumber_range_cm1": [global_min, global_max]
        if global_min is not None and global_max is not None
        else [],
        "matching_reference_ids": sorted(matching_reference_ids),
        "filters": filters,
        "libraries": summaries,
        "next_commands": {
            "build_assignment_packet": build_source_commands,
            "register_reference_seeds": "ea references register-seeds /path/to/ea-project --source-packet suggestions/ftir/source-packets/<source_packet_id>.yml --project-id <project-id>",
            "suggest_assignments": "ea ftir suggest-assignments /path/to/ea-project --metadata processed/sample-001/ftir/<result_id>/ftir_metadata.yml --source-file suggestions/ftir/source-packets/<source_packet_id>.yml --project-id <project-id>",
            "prepare_review": "ea ftir prepare-review /path/to/ea-project --suggestion suggestions/ftir/<suggestion_id>/ftir_assignment_suggestions.yml --project-id <project-id>",
        },
        "boundaries": [
            "This discovery command reads bundled FTIR assignment library metadata only and does not create project files.",
            "It does not run live literature search, operate Zotero or browsers, download/parse full text, register references, create source packets, match bands, create ReviewRecords, inject citations, write memory, or prove composition/functional groups.",
            "Use the listed build-assignment-packet, references register-seeds, suggest-assignments, and prepare-review commands when the user wants traceable project artifacts.",
        ],
    }


def _source_reference_seeds(
    source_library: Any,
    *,
    referenced_ids: set[str],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(source_library, dict):
        return {}
    raw_seeds = source_library.get("reference_seeds") or {}
    if not raw_seeds:
        return {}
    if not isinstance(raw_seeds, dict):
        warnings.append(
            _warning(
                "ftir_assignment_source_reference_seeds_invalid",
                "FTIR assignment source reference_seeds were ignored because they were not a mapping.",
                severity="medium",
            )
        )
        return {}
    seeds: dict[str, Any] = {}
    for raw_seed_id, raw_seed in raw_seeds.items():
        seed_id = str(raw_seed_id).strip()
        if not seed_id or seed_id not in referenced_ids:
            continue
        if not isinstance(raw_seed, dict):
            warnings.append(
                _warning(
                    "ftir_assignment_source_reference_seed_ignored",
                    "An FTIR assignment source reference_seed was skipped because its metadata was not a mapping.",
                    severity="medium",
                    seed_id=seed_id,
                )
            )
            continue
        seeds[seed_id] = deepcopy(raw_seed)
    return seeds


def build_ftir_assignment_source_packet(
    root: Path,
    *,
    project_id: str,
    library_path: Path | None = None,
    builtin_library: str | None = None,
    literature_manifest_path: Path | None = None,
    output_path: Path | None = None,
    include_candidates: list[str] | None = None,
    assignment_types: list[str] | None = None,
    material_scopes: list[str] | None = None,
    template: bool = False,
    created_at: str | None = None,
) -> dict[str, Any]:
    selected_source_count = sum(
        bool(value)
        for value in [library_path, builtin_library, literature_manifest_path, template]
    )
    if selected_source_count > 1:
        raise FTIRProcessingError(
            "Use only one of --library-file, --builtin-library, --literature-manifest, or --write-template for FTIR assignment source-packet generation"
        )
    if not library_path and not literature_manifest_path and not template:
        builtin_library = builtin_library or BUILTIN_FTIR_ASSIGNMENT_LIBRARY_DEFAULT

    template_mode = (
        template
        and library_path is None
        and builtin_library is None
        and literature_manifest_path is None
    )
    builtin_mode = builtin_library is not None
    literature_mode = literature_manifest_path is not None
    day = _created_day(created_at)
    timestamp = created_at or EARecord.now_iso()
    source_packet_id = next_id(root, "ftir_assignment_source_packet", day)
    if output_path is None:
        if template_mode:
            output_path = root / "templates" / "ftir_assignment_source_packet.yml"
        else:
            output_path = (
                root
                / "suggestions"
                / "ftir"
                / "source-packets"
                / f"{source_packet_id}.yml"
            )
    elif not output_path.is_absolute():
        output_path = root / output_path
    assert_not_raw_output_path(root, output_path)

    warnings: list[dict[str, Any]] = []
    library_ref: str | None = None
    library_kind = "template" if template_mode else "local_file"
    reference_seeds: dict[str, Any] = {}
    source_library: dict[str, Any] = {}
    if template_mode:
        raw_candidates = _ftir_assignment_template_candidates()
    elif builtin_mode:
        source_library = _builtin_ftir_assignment_library(str(builtin_library))
        raw_candidates = _ftir_assignment_source_candidates(source_library)
        reference_seeds = deepcopy(source_library.get("reference_seeds") or {})
        library_ref = f"builtin:{builtin_library}"
        library_kind = "built_in"
    elif literature_mode:
        source_path = (
            literature_manifest_path
            if literature_manifest_path and literature_manifest_path.is_absolute()
            else root / literature_manifest_path
            if literature_manifest_path
            else None
        )
        if source_path is None:
            raise FTIRProcessingError("FTIR literature manifest path was not supplied")
        try:
            source_library, manifest_warnings = confirmed_source_packet_library(
                root,
                manifest_path=source_path,
                method="ftir",
                method_aliases={
                    "ftir",
                    "infrared",
                    "ftir_assignment",
                    "ftir_assignment_source_packet",
                },
            )
        except SourcePacketManifestError as exc:
            raise FTIRProcessingError(str(exc)) from exc
        warnings.extend(manifest_warnings)
        raw_candidates = _ftir_assignment_source_candidates(source_library)
        library_ref = _relative_to_root(root, source_path)
        library_kind = "confirmed_literature_manifest"
    else:
        source_path = (
            library_path
            if library_path and library_path.is_absolute()
            else root / library_path
            if library_path
            else None
        )
        if source_path is None or not source_path.exists():
            raise FTIRProcessingError(
                f"FTIR assignment library file not found: {library_path}"
            )
        library_ref = _relative_to_root(root, source_path)
        source_library = read_yaml(source_path)
        raw_candidates = _ftir_assignment_source_candidates(source_library)

    include_set = {
        str(item).strip() for item in include_candidates or [] if str(item).strip()
    }
    type_set = {
        _normalize_assignment_type(item)
        for item in assignment_types or []
        if str(item).strip()
    }
    material_set = {
        str(item).strip().lower() for item in material_scopes or [] if str(item).strip()
    }
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

    reference_ids = sorted(
        {
            reference_id
            for candidate in selected
            for reference_id in _coerce_string_list(candidate.get("reference_ids"))
        }
    )
    if not builtin_mode:
        reference_seeds = _source_reference_seeds(
            source_library,
            referenced_ids=set(reference_ids),
            warnings=warnings,
        )
    packet_ref = _relative_to_root(root, output_path)
    status = (
        "template_requires_user_edit"
        if template_mode
        else ("ready_for_suggest_assignments" if selected else "no_matching_candidates")
    )
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
        "source_manifest_ref": source_library.get("source_manifest_ref")
        if literature_mode
        else None,
        "confirmation_status": source_library.get("confirmation_status")
        if literature_mode
        else None,
        "reference_seeds": reference_seeds,
        "reference_seed_count": len(reference_seeds),
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
            "If this packet uses built-in reference_seeds or local/confirmed-literature reference_seeds, register or replace those references in the project before treating suggestions as report evidence.",
            "Review and edit this packet until every candidate has a wavenumber window, source_summary, applicability_notes, reference_ids, confidence, and caveats.",
            "Run `ea ftir suggest-assignments` with processed FTIR metadata to match candidates against detected bands before using them in reports or memory.",
        ],
        "boundaries": [
            "FTIR assignment source packets are staging artifacts and do not modify processing outputs or confirmed project memory.",
            "This source-packet builder is a deterministic staging step and does not perform unconfirmed live lookup, download articles, or parse full text during the command. Values may originate from built-in generic libraries, user-provided data, local libraries, project literature, or separately confirmed search connectors, and EA may use those sources to prepare assignment candidates.",
            "Confirmed-literature manifests are source-candidate manifests only; they do not register references, inject report citations, apply FTIR assignments, prove composition, or prove functional groups.",
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
            "source_library_kind": library_kind,
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
        "source_library_kind": library_kind,
        "source_library_ref": library_ref,
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
    window = candidate.get(
        "wavenumber_window_cm1",
        candidate.get("wavenumber_window_cm-1", candidate.get("window_cm1")),
    )
    if isinstance(window, list | tuple) and len(window) >= 2:
        lower = _candidate_number({"lower": window[0]}, "lower")
        upper = _candidate_number({"upper": window[1]}, "upper")
    elif isinstance(window, dict):
        lower = _candidate_number(
            window, "min", "lower", "low", "start_cm1", "from_cm1"
        )
        upper = _candidate_number(window, "max", "upper", "high", "end_cm1", "to_cm1")
    else:
        lower = _candidate_number(
            candidate, "wavenumber_min_cm1", "min_cm1", "lower_cm1"
        )
        upper = _candidate_number(
            candidate, "wavenumber_max_cm1", "max_cm1", "upper_cm1"
        )
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


def _match_ftir_bands(
    bands: pd.DataFrame, lower: float, upper: float, expected_feature: str
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    if bands.empty:
        return matches
    for _, row in bands.iterrows():
        try:
            wavenumber = float(row["wavenumber_cm-1"])
        except (KeyError, TypeError, ValueError):
            continue
        band_type = str(row.get("band_type") or "")
        if lower <= wavenumber <= upper and _expected_feature_matches(
            expected_feature, band_type
        ):
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

    candidate_id = str(
        raw_candidate.get("candidate_id")
        or raw_candidate.get("assignment_id")
        or f"{suggestion_id}-cand-{number:03d}"
    )
    assignment_type = _normalize_assignment_type(
        raw_candidate.get("assignment_type") or raw_candidate.get("type")
    )
    assignment_label = str(
        raw_candidate.get("assignment_label")
        or raw_candidate.get("functional_group")
        or raw_candidate.get("band_assignment")
        or ""
    ).strip()
    band_label = str(raw_candidate.get("band_label") or assignment_label).strip()
    reference_ids = _coerce_string_list(raw_candidate.get("reference_ids"))
    applicability_notes = _coerce_string_list(raw_candidate.get("applicability_notes"))
    caveats = _coerce_string_list(raw_candidate.get("caveats"))
    source_summary = str(
        raw_candidate.get("source_summary")
        or raw_candidate.get("reference_summary")
        or ""
    ).strip()
    confidence = str(raw_candidate.get("confidence") or "low").strip().lower()
    expected_feature = _normalize_expected_feature(
        raw_candidate.get("expected_feature")
    )
    lower, upper = _candidate_window(raw_candidate)
    unresolved_reference_ids = [
        reference_id
        for reference_id in reference_ids
        if reference_id not in registered_references
    ]
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

    matches = (
        _match_ftir_bands(bands, lower, upper, expected_feature)
        if lower is not None and upper is not None
        else []
    )
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
        "wavenumber_window_cm1": [lower, upper]
        if lower is not None and upper is not None
        else [],
        "expected_feature": expected_feature,
        "matched_bands": matches,
        "matched_band_ids": [
            match["band_id"] for match in matches if match.get("band_id")
        ],
        "matched_wavenumbers_cm-1": [match["wavenumber_cm-1"] for match in matches],
        "source_summary": source_summary,
        "reference_ids": reference_ids,
        "unresolved_reference_ids": unresolved_reference_ids,
        "applicability_notes": applicability_notes,
        "material_scope": str(raw_candidate.get("material_scope") or "").strip()
        or None,
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
        raise FTIRProcessingError(
            "FTIR metadata does not include outputs.peak_table for assignment matching"
        )
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
            table[column] = table[column].apply(
                lambda value: (
                    "; ".join(str(item) for item in value)
                    if isinstance(value, list)
                    else value
                )
            )

    ready_count = sum(
        1
        for candidate in candidates
        if candidate.get("status") == "ready_for_user_review"
    )
    unresolved_count = sum(
        1
        for candidate in candidates
        if candidate.get("status") == "needs_reference_registration"
    )
    no_match_count = sum(
        1 for candidate in candidates if candidate.get("status") == "no_feature_match"
    )
    invalid_count = sum(
        1
        for candidate in candidates
        if str(candidate.get("status", "")).startswith("invalid")
    )
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
    all_reference_ids = sorted(
        {
            reference_id
            for candidate in candidates
            for reference_id in candidate.get("reference_ids", [])
        }
    )
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
            "This suggestion-record step does not perform unconfirmed live lookup during the command. EA may prepare source packets from built-in libraries, project literature, user-provided sources, or user-confirmed search workflows before this step; this step does not alter processing outputs, prove functional groups/composition, or write confirmed memory.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(table_path, index=False)
    write_yaml(record_path, record)
    provenance_path = write_provenance_entry(
        root,
        workflow="ftir_assignment_suggestion",
        inputs={
            "records": [source_ref, metadata_ref, *related_records],
            "files": [str(peak_table_ref)],
        },
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


def _review_status_counts(candidates: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        status = str(candidate.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _review_group_for_status(status: str) -> str:
    if status == "ready_for_user_review":
        return "ready_for_user_review"
    if status == "needs_reference_registration":
        return "needs_reference_registration"
    if status == "no_feature_match":
        return "no_feature_match"
    if status.startswith("invalid"):
        return "invalid_or_incomplete"
    return "other"


def _review_value(value: Any) -> str:
    if value in (None, "", [], {}):
        return "not recorded"
    if isinstance(value, list | tuple):
        return (
            ", ".join(str(item) for item in value if str(item).strip())
            or "not recorded"
        )
    if isinstance(value, dict):
        parts = [
            f"{key}={item}"
            for key, item in value.items()
            if item not in (None, "", [], {})
        ]
        return "; ".join(parts) or "not recorded"
    return str(value)


def _ftir_review_candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    status = str(candidate.get("status") or "unknown")
    if status == "ready_for_user_review":
        action = "Ask the user to accept, reject, or edit this source-backed assignment before report/memory reuse."
    elif status == "needs_reference_registration":
        action = "Register, replace, or remove unresolved reference_ids before treating this candidate as report evidence."
    elif status == "no_feature_match":
        action = "Keep as a negative/no-match note unless the user changes feature detection or supplies a better spectrum context."
    elif status.startswith("invalid"):
        action = "Fix missing source, window, reference, or applicability metadata before user review."
    else:
        action = "Inspect status and decide whether more source/context work is needed."
    return {
        "candidate_id": str(candidate.get("candidate_id") or ""),
        "review_group": _review_group_for_status(status),
        "status": status,
        "assignment_type": str(candidate.get("assignment_type") or "unknown"),
        "assignment_label": str(candidate.get("assignment_label") or "not recorded"),
        "band_label": str(candidate.get("band_label") or "not recorded"),
        "confidence": str(candidate.get("confidence") or "low"),
        "matched_band_ids": _coerce_string_list(candidate.get("matched_band_ids")),
        "matched_wavenumbers_cm-1": _coerce_string_list(
            candidate.get("matched_wavenumbers_cm-1")
        ),
        "wavenumber_window_cm1": candidate.get("wavenumber_window_cm1") or [],
        "reference_ids": _coerce_string_list(candidate.get("reference_ids")),
        "unresolved_reference_ids": _coerce_string_list(
            candidate.get("unresolved_reference_ids")
        ),
        "missing_fields": _coerce_string_list(candidate.get("missing_fields")),
        "source_summary": str(candidate.get("source_summary") or "not recorded"),
        "applicability_notes": _coerce_string_list(
            candidate.get("applicability_notes")
        ),
        "caveats": _coerce_string_list(candidate.get("caveats")),
        "recommended_action": action,
    }


def _render_ftir_review_package_markdown(package: dict[str, Any]) -> str:
    lines = [
        "# FTIR Assignment Suggestion Review Package",
        "",
        "## Summary",
        f"- review_package_id: `{package.get('review_package_id')}`",
        f"- project_id: `{package.get('project_id')}`",
        f"- suggestion_ref: `{package.get('suggestion_ref')}`",
        f"- selected_candidates: `{package.get('selected_candidate_count')}` / `{package.get('candidate_count')}`",
        f"- status: `{package.get('status')}`",
        "",
        "## Status Counts",
    ]
    for status, count in (package.get("selected_status_counts") or {}).items():
        lines.append(f"- `{status}`: {count}")
    lines.extend(["", "## Candidate Groups"])
    for group in package.get("groups", []):
        lines.append(f"### {group.get('group')}")
        lines.append(f"- candidate_ids: `{_review_value(group.get('candidate_ids'))}`")
        lines.append(f"- recommended_action: {group.get('recommended_action')}")
        lines.append("")
    lines.append("## Candidates")
    for candidate in package.get("candidate_summaries", []):
        lines.extend(
            [
                f"### `{candidate.get('candidate_id')}`",
                f"- group/status: `{candidate.get('review_group')}` / `{candidate.get('status')}`",
                f"- assignment: `{candidate.get('assignment_label')}` (`{candidate.get('assignment_type')}`)",
                f"- matched_band_ids: `{_review_value(candidate.get('matched_band_ids'))}`",
                f"- matched_wavenumbers_cm-1: `{_review_value(candidate.get('matched_wavenumbers_cm-1'))}`",
                f"- references: `{_review_value(candidate.get('reference_ids'))}`",
                f"- unresolved_references: `{_review_value(candidate.get('unresolved_reference_ids'))}`",
                f"- confidence: `{candidate.get('confidence')}`",
                f"- source_summary: {candidate.get('source_summary')}",
                f"- applicability_notes: {_review_value(candidate.get('applicability_notes'))}",
                f"- caveats: {_review_value(candidate.get('caveats'))}",
                f"- recommended_action: {candidate.get('recommended_action')}",
                "",
            ]
        )
    commands = package.get("recommended_commands") or {}
    lines.extend(["## Suggested Commands"])
    for name, command in commands.items():
        lines.append(f"- {name}: `{command}`")
    lines.extend(["", "## Boundaries"])
    for boundary in package.get("boundaries", []):
        lines.append(f"- {boundary}")
    lines.append("")
    return "\n".join(lines)


def prepare_ftir_assignment_review_package(
    root: Path,
    *,
    project_id: str,
    suggestion_path: Path,
    candidate_ids: list[str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    resolved_suggestion_path = (
        suggestion_path if suggestion_path.is_absolute() else root / suggestion_path
    )
    suggestion = read_yaml(resolved_suggestion_path)
    if suggestion.get("source") != "ea.ftir.assignment_suggestions:v0.2":
        raise FTIRProcessingError(
            f"Not an FTIR assignment suggestion record: {suggestion_path}"
        )

    suggestion_ref = _relative_to_root(root, resolved_suggestion_path)
    suggestion_project_id = str(suggestion.get("project_id") or "")
    if suggestion_project_id and project_id and suggestion_project_id != project_id:
        raise FTIRProcessingError(
            f"Project ID mismatch: suggestion has {suggestion_project_id}, request has {project_id}"
        )

    candidates = [
        candidate
        for candidate in suggestion.get("candidates", [])
        if isinstance(candidate, dict)
    ]
    requested_ids = [
        str(candidate_id)
        for candidate_id in candidate_ids or []
        if str(candidate_id).strip()
    ]
    requested_set = set(requested_ids)
    selected = [
        candidate
        for candidate in candidates
        if not requested_set or str(candidate.get("candidate_id")) in requested_set
    ]
    found_ids = {str(candidate.get("candidate_id")) for candidate in selected}
    missing_candidate_ids = [
        candidate_id for candidate_id in requested_ids if candidate_id not in found_ids
    ]
    warnings: list[dict[str, Any]] = [
        _warning(
            "ftir_review_package_candidate_not_found",
            "A requested FTIR assignment suggestion candidate_id was not found in the suggestion record.",
            severity="medium",
            candidate_id=candidate_id,
        )
        for candidate_id in missing_candidate_ids
    ]

    summaries = [_ftir_review_candidate_summary(candidate) for candidate in selected]
    group_actions = {
        "ready_for_user_review": "Review these candidates with the user; create a ReviewRecord only after explicit confirmation.",
        "needs_reference_registration": "Resolve references first with `ea references register-seeds` or `ea references add`, then regenerate suggestions or review with caveats.",
        "no_feature_match": "Treat as no-match context unless spectrum processing or candidate windows are changed.",
        "invalid_or_incomplete": "Fix candidate metadata before asking the user to review.",
        "other": "Inspect manually before downstream use.",
    }
    groups = []
    for group_name in [
        "ready_for_user_review",
        "needs_reference_registration",
        "no_feature_match",
        "invalid_or_incomplete",
        "other",
    ]:
        ids = [
            summary["candidate_id"]
            for summary in summaries
            if summary["review_group"] == group_name
        ]
        if ids:
            groups.append(
                {
                    "group": group_name,
                    "candidate_ids": ids,
                    "recommended_action": group_actions[group_name],
                }
            )

    package_dir = resolved_suggestion_path.parent
    package_path = package_dir / "review_package.yml"
    markdown_path = package_dir / "review_package.md"
    for path in [package_path, markdown_path]:
        assert_not_raw_output_path(root, path)
    package_ref = _relative_to_root(root, package_path)
    markdown_ref = _relative_to_root(root, markdown_path)
    timestamp = created_at or EARecord.now_iso()
    package_id = f"{suggestion.get('suggestion_id') or package_dir.name}-review-package"
    package: dict[str, Any] = {
        "schema_version": "0.2",
        "review_package_id": package_id,
        "project_id": project_id or suggestion_project_id,
        "method": "ftir",
        "source": "ea.ftir.assignment_review_package:v0.2",
        "status": "review_package_prepared" if selected else "no_candidates_selected",
        "created_at": timestamp,
        "updated_at": timestamp,
        "suggestion_id": suggestion.get("suggestion_id"),
        "suggestion_ref": suggestion_ref,
        "table_ref": suggestion.get("table_ref"),
        "source_packet_ref": suggestion.get("source_packet_ref"),
        "feature_table_ref": suggestion.get("feature_table_ref"),
        "review_target_type": "ftir_assignment_suggestions",
        "review_target_ref": suggestion_ref,
        "candidate_count": len(candidates),
        "selected_candidate_count": len(selected),
        "requested_candidate_ids": requested_ids,
        "missing_candidate_ids": missing_candidate_ids,
        "overall_status_counts": _review_status_counts(candidates),
        "selected_status_counts": _review_status_counts(selected),
        "groups": groups,
        "candidate_summaries": summaries,
        "reference_ids": sorted(
            {
                ref
                for candidate in summaries
                for ref in candidate.get("reference_ids", [])
            }
        ),
        "unresolved_reference_ids": sorted(
            {
                ref
                for candidate in summaries
                for ref in candidate.get("unresolved_reference_ids", [])
            }
        ),
        "recommended_commands": {
            "create_review_record": (
                "ea review add /path/to/ea-project --target-type ftir_assignment_suggestions "
                f'--target-ref {suggestion_ref} --user-response "可以，保存" '
                '--reviewed-content "User reviewed the listed FTIR assignment candidates; record accepted/rejected/edited candidate IDs."'
            ),
            "report_with_suggestion": (
                "ea ftir report /path/to/ea-project --metadata <ftir_metadata.yml> "
                f"--assignment-suggestion {suggestion_ref}"
            ),
            "propose_memory_after_review": (
                f"ea ftir propose-memory /path/to/ea-project --suggestion {suggestion_ref} --review-ref <review-id>"
            ),
        },
        "next_steps": [
            "Ask the user to review ready candidates and state which candidate IDs are accepted, rejected, edited, or deferred.",
            "Resolve unresolved references before using candidates as report evidence unless the report explicitly discusses them as unresolved.",
            "After a confirmed ReviewRecord targets this suggestion record, use report or memory commands only for the user-approved candidate set.",
        ],
        "boundaries": [
            "This package prepares review context only; it does not create a ReviewRecord.",
            "It does not apply FTIR assignments, change processing outputs, inject report citations, write confirmed memory, or prove composition/functional groups.",
            "Unresolved or invalid candidates remain visible so the user can decide whether to fix, exclude, or discuss them with caveats.",
        ],
        "warnings": warnings,
    }
    write_yaml(package_path, package)
    markdown_path.write_text(
        _render_ftir_review_package_markdown(package), encoding="utf-8"
    )
    provenance_path = write_provenance_entry(
        root,
        workflow="ftir_assignment_review_package",
        inputs={"records": [suggestion_ref], "files": []},
        outputs={"records": [package_ref, markdown_ref], "files": []},
        parameters={
            "suggestion_id": suggestion.get("suggestion_id"),
            "requested_candidate_ids": requested_ids,
            "selected_candidate_count": len(selected),
            "auto_applied": False,
        },
        warnings=warnings,
        source_refs=package["reference_ids"],
        created_at=created_at,
    )
    package["provenance_ref"] = _relative_to_root(root, provenance_path)
    write_yaml(package_path, package)
    markdown_path.write_text(
        _render_ftir_review_package_markdown(package), encoding="utf-8"
    )
    return {
        "status": package["status"],
        "review_package": str(package_path),
        "review_package_markdown": str(markdown_path),
        "review_package_ref": package_ref,
        "review_package_markdown_ref": markdown_ref,
        "suggestion_id": suggestion.get("suggestion_id"),
        "suggestion_ref": suggestion_ref,
        "candidate_count": len(candidates),
        "selected_candidate_count": len(selected),
        "selected_status_counts": package["selected_status_counts"],
        "missing_candidate_ids": missing_candidate_ids,
        "provenance": str(provenance_path),
        "warnings": warnings,
        "boundaries": package["boundaries"],
    }


def _normalize_review_target_ref(root: Path, value: Any) -> str:
    target = str(value or "").strip()
    if not target:
        return ""
    target_path = Path(target)
    if target_path.is_absolute():
        return _relative_to_root(root, target_path)
    return _relative_to_root(root, root / target_path)


def _candidate_is_valid_for_memory(
    candidate: dict[str, Any], *, allow_non_ready: bool
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    status = str(candidate.get("status") or "")
    if status != "ready_for_user_review":
        reasons.append(f"status:{status or 'missing'}")
    if candidate.get("auto_applied") is not False:
        reasons.append("auto_applied_not_false")
    if candidate.get("unresolved_reference_ids"):
        reasons.append("unresolved_reference_ids")
    if candidate.get("missing_fields"):
        reasons.append("missing_required_metadata")
    if not candidate.get("reference_ids"):
        reasons.append("missing_reference_ids")
    if not candidate.get("matched_band_ids"):
        reasons.append("missing_matched_band_ids")
    if not str(candidate.get("assignment_label") or "").strip():
        reasons.append("missing_assignment_label")
    if not str(candidate.get("source_summary") or "").strip():
        reasons.append("missing_source_summary")

    if not allow_non_ready:
        return not reasons, reasons
    hard_blockers = {
        "auto_applied_not_false",
        "missing_required_metadata",
        "missing_assignment_label",
        "missing_source_summary",
    }
    return not any(
        reason in hard_blockers or reason.startswith("status:invalid")
        for reason in reasons
    ), reasons


def _memory_confidence(value: Any) -> str:
    normalized = str(value or "low").strip().lower()
    if normalized in {"high", "medium", "low", "insufficient"}:
        return normalized
    return "low"


def _format_memory_list(items: list[Any]) -> str:
    values = [str(item) for item in items if str(item).strip()]
    return ", ".join(values) if values else "none recorded"


def _format_ftir_assignment_memory_text(
    candidate: dict[str, Any], *, suggestion_id: str, review_ref: str
) -> str:
    candidate_id = str(candidate.get("candidate_id") or "unknown")
    assignment_label = str(candidate.get("assignment_label") or "unknown assignment")
    assignment_type = str(candidate.get("assignment_type") or "unknown")
    matched_band_ids = _format_memory_list(
        _coerce_string_list(candidate.get("matched_band_ids"))
    )
    matched_wavenumbers = _format_memory_list(
        _coerce_string_list(candidate.get("matched_wavenumbers_cm-1"))
    )
    reference_ids = _format_memory_list(
        _coerce_string_list(candidate.get("reference_ids"))
    )
    applicability = _format_memory_list(
        _coerce_string_list(candidate.get("applicability_notes"))
    )
    caveats = _format_memory_list(_coerce_string_list(candidate.get("caveats")))
    source_summary = str(
        candidate.get("source_summary") or "No source summary recorded."
    ).strip()
    confidence = _memory_confidence(candidate.get("confidence"))
    status = str(candidate.get("status") or "unknown")
    material_scope = str(candidate.get("material_scope") or "not specified").strip()
    sample_scope = str(candidate.get("sample_scope") or "not specified").strip()
    return (
        f"FTIR source-backed assignment candidate `{candidate_id}` from suggestion `{suggestion_id}` was reviewed via `{review_ref}` "
        f"and can be preserved as a draft interpretation memory candidate.\n\n"
        f"- possible assignment: `{assignment_label}` (`{assignment_type}`)\n"
        f"- suggestion status: `{status}`\n"
        f"- matched band IDs: {matched_band_ids}\n"
        f"- matched wavenumbers (cm^-1): {matched_wavenumbers}\n"
        f"- material scope: {material_scope}\n"
        f"- sample scope: {sample_scope}\n"
        f"- confidence: `{confidence}`\n"
        f"- references: {reference_ids}\n"
        f"- source summary: {source_summary}\n"
        f"- applicability notes: {applicability}\n"
        f"- caveats: {caveats}\n\n"
        "Boundary: this is a source-backed FTIR interpretation candidate only. It does not by itself prove chemical composition, "
        "functional-group identity, reaction pathway, or sample functionality; confirmed project memory still requires the standard memory review/commit flow."
    )


def propose_ftir_assignment_memory_candidates(
    root: Path,
    *,
    project_id: str,
    suggestion_path: Path,
    review_ref: str,
    candidate_ids: list[str] | None = None,
    allow_non_ready: bool = False,
    created_at: str | None = None,
) -> dict[str, Any]:
    resolved_suggestion_path = (
        suggestion_path if suggestion_path.is_absolute() else root / suggestion_path
    )
    suggestion = read_yaml(resolved_suggestion_path)
    if suggestion.get("source") != "ea.ftir.assignment_suggestions:v0.2":
        raise FTIRProcessingError(
            f"Not an FTIR assignment suggestion record: {suggestion_path}"
        )

    suggestion_ref = _relative_to_root(root, resolved_suggestion_path)
    suggestion_project_id = str(suggestion.get("project_id") or "")
    if suggestion_project_id and project_id and suggestion_project_id != project_id:
        raise FTIRProcessingError(
            f"Project ID mismatch: suggestion has {suggestion_project_id}, request has {project_id}"
        )

    review = require_confirmed_review(root, review_ref)
    review_target_ref = _normalize_review_target_ref(root, review.get("target_ref"))
    if review_target_ref and review_target_ref != suggestion_ref:
        raise FTIRProcessingError(
            f"ReviewRecord {review_ref} targets {review.get('target_ref')}, not FTIR assignment suggestion {suggestion_ref}"
        )

    candidates = [
        candidate
        for candidate in suggestion.get("candidates", [])
        if isinstance(candidate, dict)
    ]
    requested_ids = [
        str(candidate_id)
        for candidate_id in candidate_ids or []
        if str(candidate_id).strip()
    ]
    requested_set = set(requested_ids)
    selected = [
        candidate
        for candidate in candidates
        if not requested_set or str(candidate.get("candidate_id")) in requested_set
    ]
    found_ids = {str(candidate.get("candidate_id")) for candidate in selected}
    skipped: list[dict[str, Any]] = [
        {"candidate_id": candidate_id, "reason": "candidate_id_not_found"}
        for candidate_id in requested_ids
        if candidate_id not in found_ids
    ]
    warnings: list[dict[str, Any]] = []
    if allow_non_ready and not requested_set:
        warnings.append(
            _warning(
                "ftir_assignment_memory_allow_non_ready_without_selection",
                "--allow-non-ready only applies to explicitly selected --candidate-id values; default selection still uses ready candidates.",
                severity="medium",
            )
        )

    source_refs = [
        suggestion_ref,
        str(suggestion.get("table_ref") or "").strip(),
        str(suggestion.get("source_packet_ref") or "").strip(),
        str(suggestion.get("ftir_metadata_ref") or "").strip(),
        str(suggestion.get("feature_table_ref") or "").strip(),
    ]
    source_refs = [ref for ref in source_refs if ref]
    provenance_refs = [str(suggestion.get("provenance_ref") or "").strip()]
    provenance_refs = [ref for ref in provenance_refs if ref]
    if not provenance_refs:
        raise FTIRProcessingError(
            "FTIR assignment suggestion record lacks provenance_ref"
        )

    proposed: list[dict[str, Any]] = []
    output_refs: list[str] = []
    for candidate in selected:
        candidate_id = str(candidate.get("candidate_id") or "")
        candidate_allow_non_ready = bool(
            allow_non_ready and requested_set and candidate_id in requested_set
        )
        eligible, reasons = _candidate_is_valid_for_memory(
            candidate, allow_non_ready=candidate_allow_non_ready
        )
        if not eligible:
            skipped.append(
                {
                    "candidate_id": candidate_id,
                    "reason": "not_memory_candidate_eligible",
                    "details": reasons,
                }
            )
            continue

        candidate_text = _format_ftir_assignment_memory_text(
            candidate,
            suggestion_id=str(
                suggestion.get("suggestion_id") or resolved_suggestion_path.parent.name
            ),
            review_ref=review_ref,
        )
        rationale = (
            f"Generated from FTIR assignment suggestion `{suggestion_ref}` candidate `{candidate_id}` after confirmed review `{review_ref}`. "
            "This preserves a source-backed interpretation candidate for later user review and commit; it does not create confirmed memory."
        )
        memory_path = propose_memory_candidate(
            root,
            project_id=project_id or suggestion_project_id,
            candidate_text=candidate_text,
            source_refs=source_refs
            + _coerce_string_list(candidate.get("reference_ids")),
            provenance_refs=provenance_refs,
            category="interpretation",
            confidence=_memory_confidence(candidate.get("confidence")),
            rationale=rationale,
            created_at=created_at,
        )
        memory_ref = _relative_to_root(root, memory_path)
        output_refs.append(memory_ref)
        proposed.append(
            {
                "candidate_id": candidate_id,
                "memory_candidate": str(memory_path),
                "memory_candidate_ref": memory_ref,
                "confidence": _memory_confidence(candidate.get("confidence")),
                "source_refs": source_refs,
                "provenance_refs": provenance_refs,
            }
        )

    bridge_provenance = None
    if proposed:
        bridge_provenance_path = write_provenance_entry(
            root,
            workflow="ftir_assignment_memory_candidate_proposal",
            inputs={"records": [suggestion_ref], "files": []},
            outputs={
                "records": output_refs + ["memory/candidates/index.yml"],
                "files": [],
            },
            parameters={
                "suggestion_id": suggestion.get("suggestion_id"),
                "requested_candidate_ids": requested_ids,
                "allow_non_ready": allow_non_ready,
                "proposed_count": len(proposed),
                "skipped_count": len(skipped),
            },
            review_refs=[review_ref],
            source_refs=source_refs,
            warnings=warnings,
            created_at=created_at,
        )
        bridge_provenance = _relative_to_root(root, bridge_provenance_path)

    return {
        "status": "memory_candidates_proposed"
        if proposed
        else "no_memory_candidates_proposed",
        "suggestion_id": suggestion.get("suggestion_id"),
        "suggestion_ref": suggestion_ref,
        "review_ref": review_ref,
        "candidate_count": len(candidates),
        "selected_count": len(selected),
        "proposed_count": len(proposed),
        "skipped_count": len(skipped),
        "memory_candidates": proposed,
        "skipped": skipped,
        "provenance_ref": bridge_provenance,
        "warnings": warnings,
        "boundaries": [
            "This helper writes draft memory candidates only; it does not commit confirmed memory.",
            "Ready candidates are used by default; non-ready candidates require explicit --candidate-id plus --allow-non-ready and remain caveated.",
            "FTIR band matches do not by themselves prove composition, functional-group identity, reaction pathway, or sample functionality.",
        ],
    }


def _confirmed_frame(path: Path, request: FTIRProcessingRequest) -> pd.DataFrame:
    frame, _ = _read_spectrum(path)
    frame.columns = [str(column) for column in frame.columns]
    if request.x_column not in frame.columns or request.y_column not in frame.columns:
        raise FTIRProcessingError(
            "Confirmed x/y columns are not present in the raw file"
        )
    if request.x_unit not in {"cm^-1", "unknown"}:
        raise FTIRProcessingError(
            "FTIR x_unit must be user-confirmed as cm^-1 or unknown"
        )
    if request.signal_mode not in {"absorbance", "transmittance"}:
        raise FTIRProcessingError(
            "FTIR signal_mode must be user-confirmed as absorbance or transmittance"
        )
    data = frame[[request.x_column, request.y_column]].copy()
    data.columns = ["wavenumber_cm-1", "raw_signal"]
    data["wavenumber_cm-1"] = pd.to_numeric(data["wavenumber_cm-1"], errors="coerce")
    data["raw_signal"] = pd.to_numeric(data["raw_signal"], errors="coerce")
    data = data.dropna().sort_values("wavenumber_cm-1").reset_index(drop=True)
    if data.empty:
        raise FTIRProcessingError("Confirmed FTIR columns contain no numeric data")
    return data


def _rolling_quantile_baseline(
    signal: np.ndarray, parameters: dict[str, Any]
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    baseline = parameters.get("baseline_correction", {})
    window_points, window_adjusted = _coerce_int(
        baseline.get("window_points"), 101, minimum=3
    )
    quantile, quantile_adjusted = _coerce_float(
        baseline.get("quantile"), 0.05, minimum=0.0, maximum=1.0
    )
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
        warnings.append(
            _warning(
                "ftir_baseline_skipped",
                "FTIR baseline correction skipped because the spectrum has fewer than three points.",
                severity="medium",
            )
        )
        return np.zeros_like(signal), warnings
    series = pd.Series(signal)
    baseline_values = (
        series.rolling(window_points, center=True, min_periods=1)
        .quantile(quantile)
        .to_numpy(dtype=float)
    )
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
        window_length, window_adjusted = _coerce_int(
            smoothing.get("window_length"), 9, minimum=3
        )
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
            signal = np.asarray(
                savgol_filter(
                    signal,
                    window_length=window_length,
                    polyorder=polyorder,
                    mode="interp",
                ),
                dtype=float,
            )
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
            warnings.append(
                _warning(
                    "ftir_smoothing_skipped",
                    "FTIR smoothing skipped because the spectrum has fewer than three points.",
                    severity="medium",
                )
            )

    if parameters.get("normalization", {}).get("enabled", True):
        max_value = float(np.max(np.abs(signal)))
        if max_value > 0:
            signal = signal / max_value
        warnings.append(
            _warning(
                "ftir_normalization_applied",
                "FTIR signal normalized by processing parameters.",
            )
        )
    processed["processed_signal"] = signal
    return processed, warnings


def _band_family(wavenumber: float, parameters: dict[str, Any]) -> dict[str, str]:
    if not parameters.get("band_assignment", {}).get("enabled", True):
        return {
            "family": "",
            "confidence": "",
            "source": "",
            "notes": "band assignment disabled by processing parameters",
        }
    for window in FTIR_BAND_WINDOWS:
        if float(window["min"]) <= wavenumber <= float(window["max"]):
            return {
                "family": str(window["family"]),
                "confidence": "low",
                "source": str(
                    parameters.get("band_assignment", {}).get("source")
                    or "ea.ftir.builtin_band_windows:v0.2"
                ),
                "notes": str(window["notes"]),
            }
    return {
        "family": "unassigned FTIR band region",
        "confidence": "insufficient",
        "source": str(
            parameters.get("band_assignment", {}).get("source")
            or "ea.ftir.builtin_band_windows:v0.2"
        ),
        "notes": "No built-in broad band window matched this wavenumber.",
    }


def _detect_bands(
    processed: pd.DataFrame, parameters: dict[str, Any], signal_mode: str
) -> pd.DataFrame:
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
    peaks, properties = find_peaks(
        detection_signal, prominence=prominence, distance=distance
    )
    ranked = sorted(
        [
            (int(peak), float(properties["prominences"][index]))
            for index, peak in enumerate(peaks)
        ],
        key=lambda item: item[1],
        reverse=True,
    )[:max_bands]
    ranked.sort(
        key=lambda item: float(processed.iloc[item[0]]["wavenumber_cm-1"]), reverse=True
    )
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
                "band_type": "absorbance_maximum"
                if signal_mode == "absorbance"
                else "transmittance_minimum",
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


_FTIR_CONTEXT_SECTIONS = (
    "instrument_accessory",
    "atmosphere",
    "sample_preparation",
    "background",
    "reference",
)


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


def _context_section(
    params: dict[str, Any], name: str
) -> tuple[dict[str, Any], dict[str, Any] | None]:
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


def _record_context(
    parameters: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
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

    reviewed_fields = [
        name for name, section in sections.items() if _has_context_payload(section)
    ]
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
            "status": "reviewed_context_recorded"
            if has_reviewed_context
            else "enabled_without_reviewed_context",
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


def _analyze_bands(
    bands: pd.DataFrame, context_record: dict[str, Any] | None = None
) -> dict[str, Any]:
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
        for family, family_rows in strongest.groupby(
            "possible_band_family", sort=False
        ):
            evidence = [str(value) for value in family_rows["band_id"].head(3)]
            confidence_values = [
                str(value)
                for value in family_rows["assignment_confidence"]
                if str(value)
            ]
            confidence = "low" if "low" in confidence_values else "insufficient"
            source_values = [
                str(value) for value in family_rows["assignment_source"] if str(value)
            ]
            analysis["possible_interpretations"].append(
                {
                    "text": f"Detected FTIR feature(s) fall in the broad {family} window; treat this as a screening hint, not a definitive chemical assignment.",
                    "confidence": confidence,
                    "evidence": evidence,
                    "assignment_source": source_values[0] if source_values else "",
                }
            )
    if context_record and context_record.get("status") == "reviewed_context_recorded":
        fields = (
            ", ".join(
                str(value)
                for value in context_record.get("reviewed_context_fields", [])
            )
            or "FTIR context"
        )
        analysis["possible_interpretations"].append(
            {
                "text": (
                    f"Reviewed FTIR method/context metadata was recorded for {fields}. Use it to interpret band screening hints, "
                    "but do not treat the metadata record as an automatic correction or a standalone chemical assignment."
                ),
                "confidence": context_record.get("confidence", "low"),
                "evidence": ["context_record"],
                "assignment_source": context_record.get(
                    "assignment_source", "ea.ftir.context_record:v0.2"
                ),
            }
        )
    return analysis


def _created_day(created_at: str | None) -> str | None:
    return created_at[:10] if created_at else None


def _uses_v0_2_project_ids(project_id: str) -> bool:
    return project_id.startswith("prj-")


def _plot_ftir(
    processed: pd.DataFrame,
    bands: pd.DataFrame,
    output: Path,
    signal_mode: str,
    *,
    footer: str | None = None,
) -> None:
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
        for _, band in (
            bands.sort_values("prominence", ascending=False).head(8).iterrows()
        ):
            ax.annotate(
                f"{float(band['wavenumber_cm-1']):.0f}",
                (float(band["wavenumber_cm-1"]), float(band["processed_signal"])),
                textcoords="offset points",
                xytext=(0, 6),
                ha="center",
                fontsize=7,
            )
    ax.invert_xaxis()
    ylabel = (
        "Absorbance (a.u.)" if signal_mode == "absorbance" else "Transmittance (a.u.)"
    )
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
    processed, processing_warnings = _apply_processing(
        _confirmed_frame(raw_path, request), parameters
    )
    bands = _detect_bands(processed, parameters, request.signal_mode)
    context_record, context_warnings = _record_context(parameters)
    band_analysis = _analyze_bands(bands, context_record)
    day = _created_day(created_at)
    project_slug = infer_project_slug(project_id)
    if _uses_v0_2_project_ids(project_id):
        result_id = next_standard_id(
            root, "result", project_slug, method="ftir", day=day
        )
        figure_id = next_standard_id(
            root, "figure", project_slug, method="ftir", day=day
        )
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
        context_ref = context_yml.relative_to(root).as_posix()
        context_record["record_ref"] = context_ref
        write_yaml(context_yml, context_record)
        if band_analysis.get("context_record"):
            band_analysis["context_record"]["record_ref"] = context_ref
    _plot_ftir(
        processed,
        bands,
        figure,
        request.signal_mode,
        footer=figure_footer(figure_id, None) if figure_id else None,
    )

    warnings: list[Any] = []
    if request.x_unit == "unknown":
        warnings.append(
            _warning(
                "ftir_x_unit_unknown",
                "FTIR x unit remains unknown after confirmation.",
                severity="medium",
            )
        )
    warnings.extend(processing_warnings)
    warnings.extend(context_warnings)
    outputs = {
        "figure": figure.relative_to(root).as_posix(),
        "peak_table": bands_csv.relative_to(root).as_posix(),
        "processed_csv": processed_csv.relative_to(root).as_posix(),
        "metadata": result_metadata.relative_to(root).as_posix(),
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
        processed_csv.relative_to(root).as_posix(),
        bands_csv.relative_to(root).as_posix(),
        figure.relative_to(root).as_posix(),
    ]
    if context_ref:
        provenance_files.append(context_ref)
    provenance_path = write_provenance_entry(
        root,
        workflow="ftir_processing",
        inputs={
            "records": [characterization_metadata_path.relative_to(root).as_posix()],
            "files": [metadata["project_raw_path"]],
        },
        outputs={
            "records": [result_metadata.relative_to(root).as_posix()],
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
            path=figure.relative_to(root).as_posix(),
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
                processed_csv.relative_to(root).as_posix(),
                bands_csv.relative_to(root).as_posix(),
            ]
            + ([context_ref] if context_ref else []),
            source_data=[
                source_data_entry(
                    root,
                    processed_csv.relative_to(root).as_posix(),
                    role="primary_plotting_dataset",
                    purpose="Processed FTIR trace plotted in the spectrum figure.",
                    primary=True,
                ),
                source_data_entry(
                    root,
                    bands_csv.relative_to(root).as_posix(),
                    role="feature_table",
                    purpose="Detected FTIR band annotations.",
                ),
            ]
            + (
                [
                    source_data_entry(
                        root,
                        context_ref,
                        role="interpretation_context",
                        purpose="Reviewed context used for broad band-family screening.",
                    )
                ]
                if context_ref
                else []
            ),
        )
    return result_metadata
