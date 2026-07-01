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
from scipy.optimize import least_squares
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
from ea.literature.source_packet_manifest import SourcePacketManifestError, confirmed_source_packet_library
from ea.memory import propose_memory_candidate
from ea.provenance import write_provenance_entry
from ea.raman.service import _read_spectrum
from ea.raw_import import assert_not_raw_output_path
from ea.review import require_confirmed_review
from ea.schema import XPSProcessingResult
from ea.schema.models import EARecord
from ea.standards import infer_project_slug
from ea.storage.files import read_yaml, write_yaml
from ea.storage.ids import next_id, next_standard_id


class XPSProcessingError(RuntimeError):
    """Raised when XPS processing would violate review or data boundaries."""


@dataclass(frozen=True)
class XPSInspection:
    path: Path
    file_kind: str
    row_count: int
    columns: list[str]
    x_column_candidate: str | None
    y_column_candidate: str | None
    x_unit: str
    metadata: dict[str, Any]
    warnings: list[str]
    requires_user_confirmation: bool


@dataclass(frozen=True)
class XPSProcessingRequest:
    x_column: str
    y_column: str
    x_unit: str
    energy_shift_eV: float
    calibration_reference: str
    processing_parameters: dict[str, Any]
    column_review_ref: str
    calibration_review_ref: str
    parameter_review_ref: str


XPS_PARAMETER_SUGGESTION_TYPES = {"spin_orbit_constraint", "tougaard_parameter", "binding_energy_candidate"}
XPS_PARAMETER_ORIGINS = {"reported_by_user", "source_suggested", "user_confirmed_source_suggested"}
BUILTIN_XPS_PARAMETER_LIBRARY_DEFAULT = "generic_xps_parameters"


@lru_cache(maxsize=1)
def _builtin_xps_parameter_libraries() -> dict[str, Any]:
    text = resources.files("ea.xps").joinpath("parameter_libraries.yml").read_text(encoding="utf-8")
    loaded = yaml.safe_load(text) or {}
    libraries = loaded.get("libraries")
    if not isinstance(libraries, dict):
        return {}
    return libraries


def builtin_xps_parameter_libraries() -> list[str]:
    return sorted(_builtin_xps_parameter_libraries())


def _builtin_xps_parameter_library(name: str) -> dict[str, Any]:
    libraries = _builtin_xps_parameter_libraries()
    if name not in libraries:
        available = ", ".join(sorted(libraries)) or "none"
        raise XPSProcessingError(f"Unknown built-in XPS parameter library: {name}. Available libraries: {available}")
    return deepcopy(libraries[name])


def default_xps_processing_parameters() -> dict[str, Any]:
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
        "normalization": {"enabled": True, "method": "max_intensity"},
        "peak_detection": {
            "method": "scipy_find_peaks",
            "prominence": "auto",
            "distance": "auto",
            "max_features": 12,
            "source": "ea.xps.peak_detection:v0.2",
        },
        "component_quantification": {
            "enabled": False,
            "method": "reviewed_window_integration",
            "integration_baseline": "local_minimum",
            "min_points": 5,
            "source": "ea.xps.component_quantification:v0.2",
            "components": [],
        },
        "component_fit": {
            "enabled": False,
            "method": "reviewed_component_fit_screening",
            "source": "ea.xps.component_fit:v0.2",
            "input_intensity_column": "processed_intensity",
            "fit_intensity_column": "xps_component_fit_intensity",
            "residual_column": "xps_component_fit_residual",
            "region_id_column": "xps_component_fit_region_id",
            "min_points": 8,
            "max_nfev": 5000,
            "fit_quality_thresholds": {
                "max_rmse": None,
                "min_r_squared": None,
            },
            "spin_orbit_constraints": [],
            "regions": [],
            "reference_ids": [],
            "reviewer_notes": [],
            "caveats": [],
        },
        "region_records": {
            "enabled": False,
            "method": "reviewed_multi_region_project_record",
            "source": "ea.xps.region_records:v0.2",
            "min_points": 3,
            "default_calibration_group_id": None,
            "regions": [],
            "reference_ids": [],
            "reviewer_notes": [],
            "caveats": [],
        },
        "background_model": {
            "enabled": False,
            "method": "reviewed_background_record",
            "source": "ea.xps.background_model:v0.2",
            "regions": [],
            "applied_to_processed_data": False,
            "software": {},
            "reference_ids": [],
            "reviewer_notes": [],
            "caveats": [],
        },
        "background_subtraction": {
            "enabled": False,
            "method": "reviewed_linear_background_subtraction",
            "source": "ea.xps.background_subtraction:v0.2",
            "input_intensity_column": "processed_intensity",
            "background_column": "xps_linear_background",
            "corrected_intensity_column": "xps_background_subtracted_intensity",
            "region_id_column": "xps_background_subtraction_region_id",
            "min_points": 5,
            "tougaard_B": None,
            "tougaard_C_eV2": 1643.0,
            "integration_direction": "toward_higher_binding_energy",
            "regions": [],
            "reference_ids": [],
            "reviewer_notes": [],
            "caveats": [],
        },
    }


def _merge_parameters(parameters: dict[str, Any] | None) -> dict[str, Any]:
    merged = default_xps_processing_parameters()
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


def _relative_to_root(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


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


def _axis_metadata_text(metadata: dict[str, Any]) -> str:
    parts = [
        metadata.get("AxisUnit[1]"),
        metadata.get("AxisLabel[1]"),
        metadata.get("x_unit"),
        metadata.get("x_label"),
        metadata.get("energy_unit"),
        metadata.get("y_unit"),
        metadata.get("y_label"),
    ]
    return " ".join(str(part) for part in parts if part is not None).lower()


def inspect_xps_file(path: Path) -> XPSInspection:
    frame, metadata = _read_spectrum(path)
    columns = [str(column) for column in frame.columns]
    if frame.empty or len(columns) < 2:
        raise XPSProcessingError(f"No two-column numeric XPS data found in {path}")

    x_values = pd.to_numeric(frame.iloc[:, 0], errors="coerce").dropna()
    x_min = float(x_values.min())
    x_max = float(x_values.max())
    metadata_text = _axis_metadata_text(metadata)
    path_text = path.as_posix().lower()
    looks_like_binding_energy = (
        "binding" in metadata_text
        or "binding" in path_text
        or "xps" in path_text
        or "survey" in path_text
        or ("ev" in metadata_text and x_max > 20)
        or (0 <= x_min <= 1500 and 20 <= x_max <= 1600)
    )
    looks_like_xps = (
        "xps" in path_text
        or "survey" in path_text
        or "core" in path_text
        or "binding" in metadata_text
        or "xps" in metadata_text
    )
    file_kind = "xps" if looks_like_binding_energy and looks_like_xps else "unknown"
    x_unit = "eV" if looks_like_binding_energy else "unknown"
    warnings: list[str] = []
    if file_kind == "unknown":
        warnings.append("xps_file_kind_unknown")
    if x_unit != "unknown" and "ev" not in metadata_text:
        warnings.append("xps_unit_inferred_from_range_or_path")

    return XPSInspection(
        path=path,
        file_kind=file_kind,
        row_count=len(frame),
        columns=columns,
        x_column_candidate=columns[0],
        y_column_candidate=columns[1],
        x_unit=x_unit,
        metadata={**metadata, "x_min": x_min, "x_max": x_max},
        warnings=warnings,
        requires_user_confirmation=True,
    )


def _confirmed_frame(path: Path, request: XPSProcessingRequest) -> pd.DataFrame:
    frame, _ = _read_spectrum(path)
    frame.columns = [str(column) for column in frame.columns]
    if request.x_column not in frame.columns or request.y_column not in frame.columns:
        raise XPSProcessingError("Confirmed x/y columns are not present in the raw file")
    if request.x_unit not in {"eV", "unknown"}:
        raise XPSProcessingError("XPS x_unit must be user-confirmed as eV or unknown")
    data = frame[[request.x_column, request.y_column]].copy()
    data.columns = ["binding_energy_raw", "raw_intensity"]
    data["binding_energy_raw"] = pd.to_numeric(data["binding_energy_raw"], errors="coerce")
    data["raw_intensity"] = pd.to_numeric(data["raw_intensity"], errors="coerce")
    data = data.dropna().sort_values("binding_energy_raw").reset_index(drop=True)
    if data.empty:
        raise XPSProcessingError("Confirmed XPS columns contain no numeric data")
    data["binding_energy_eV"] = data["binding_energy_raw"] + float(request.energy_shift_eV)
    return data


def _rolling_quantile_baseline(intensity: np.ndarray, window_points: int, quantile: float) -> np.ndarray:
    series = pd.Series(intensity)
    baseline = series.rolling(window=window_points, center=True, min_periods=max(3, window_points // 5)).quantile(quantile)
    baseline = baseline.bfill().ffill()
    return baseline.to_numpy(dtype=float)


def _apply_processing(data: pd.DataFrame, parameters: dict[str, Any]) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    processed = data.copy()
    warnings: list[dict[str, Any]] = []
    intensity = processed["raw_intensity"].to_numpy(dtype=float)

    baseline = parameters.get("baseline_correction", {})
    if baseline.get("enabled", False):
        window_points, window_adjusted = _coerce_int(baseline.get("window_points"), 101, minimum=5)
        quantile, quantile_adjusted = _coerce_float(baseline.get("quantile"), 0.05, minimum=0.0, maximum=1.0)
        if window_points % 2 == 0:
            window_points += 1
            window_adjusted = True
        if window_points > len(intensity):
            window_points = len(intensity) if len(intensity) % 2 == 1 else max(5, len(intensity) - 1)
            window_adjusted = True
        baseline_signal = _rolling_quantile_baseline(intensity, window_points, quantile)
        processed["baseline_signal"] = baseline_signal
        intensity = intensity - baseline_signal
        warnings.append(
            _warning(
                "xps_baseline_correction_applied",
                "Rolling-quantile baseline correction was applied to XPS intensity.",
                method="rolling_quantile",
                window_points=window_points,
                quantile=quantile,
            )
        )
        if window_adjusted or quantile_adjusted:
            warnings.append(
                _warning(
                    "xps_baseline_parameter_adjusted",
                    "Invalid XPS baseline parameters were adjusted before processing.",
                    severity="medium",
                    window_points=window_points,
                    quantile=quantile,
                )
            )

    smoothing = parameters.get("smoothing", {})
    if smoothing.get("enabled", False):
        window_length, window_adjusted = _coerce_int(smoothing.get("window_length"), 9, minimum=3)
        polyorder, poly_adjusted = _coerce_int(smoothing.get("polyorder"), 2, minimum=1)
        max_window = intensity.size if intensity.size % 2 == 1 else intensity.size - 1
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
        if intensity.size >= 3 and window_length >= 3:
            intensity = np.asarray(savgol_filter(intensity, window_length=window_length, polyorder=polyorder, mode="interp"), dtype=float)
            processed["smoothed_intensity"] = intensity
            warnings.append(
                _warning(
                    "xps_smoothing_applied",
                    "Savitzky-Golay smoothing was applied before XPS normalization and peak detection.",
                    method="savitzky_golay",
                    window_length=window_length,
                    polyorder=polyorder,
                )
            )
        if adjusted:
            warnings.append(
                _warning(
                    "xps_smoothing_parameter_adjusted",
                    "Invalid Savitzky-Golay parameters were adjusted for XPS processing.",
                    severity="medium",
                    window_length=window_length,
                    polyorder=polyorder,
                )
            )

    if parameters.get("normalization", {}).get("enabled", True):
        max_value = float(np.max(np.abs(intensity)))
        if max_value > 0:
            intensity = intensity / max_value
        warnings.append(_warning("xps_normalization_applied", "XPS intensity normalized by processing parameters."))
    processed["processed_intensity"] = intensity
    return processed, warnings


def _detect_peaks(processed: pd.DataFrame, parameters: dict[str, Any], x_unit: str) -> pd.DataFrame:
    intensity = processed["processed_intensity"].to_numpy(dtype=float)
    peak_params = parameters.get("peak_detection", {})
    prominence = peak_params.get("prominence", "auto")
    distance = peak_params.get("distance", "auto")
    max_features, _ = _coerce_int(peak_params.get("max_features"), 12, minimum=1)
    if prominence == "auto":
        prominence = max(float(np.ptp(intensity)) * 0.08, 0.02)
    if distance == "auto":
        distance = max(len(intensity) // 120, 1)
    peaks, properties = find_peaks(intensity, prominence=prominence, distance=distance)
    ranked = sorted(
        [(int(peak), float(properties["prominences"][index])) for index, peak in enumerate(peaks)],
        key=lambda item: item[1],
        reverse=True,
    )[:max_features]
    ranked.sort(key=lambda item: float(processed.iloc[item[0]]["binding_energy_eV"]))
    source = str(peak_params.get("source") or "ea.xps.peak_detection:v0.2")
    rows = []
    for index, (peak_index, peak_prominence) in enumerate(ranked, start=1):
        row = processed.iloc[peak_index]
        rows.append(
            {
                "peak_id": f"xps-peak-{index:03d}",
                "binding_energy_eV": float(row["binding_energy_eV"]),
                "raw_binding_energy": float(row["binding_energy_raw"]),
                "position_unit": x_unit,
                "raw_intensity": float(row["raw_intensity"]),
                "processed_intensity": float(row["processed_intensity"]),
                "prominence": peak_prominence,
                "method": "scipy_find_peaks",
                "component_model": "not_fitted",
                "possible_assignment": "unassigned",
                "assignment_confidence": "insufficient",
                "assignment_source": source,
                "notes": "automatic XPS peak screening; requires calibrated references, fitting model, and user review",
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "peak_id",
            "binding_energy_eV",
            "raw_binding_energy",
            "position_unit",
            "raw_intensity",
            "processed_intensity",
            "prominence",
            "method",
            "component_model",
            "possible_assignment",
            "assignment_confidence",
            "assignment_source",
            "notes",
        ],
    )


def _component_columns() -> list[str]:
    return [
        "component_id",
        "label",
        "element",
        "core_level",
        "binding_energy_min_eV",
        "binding_energy_max_eV",
        "centroid_eV",
        "max_binding_energy_eV",
        "integrated_area",
        "area_unit",
        "relative_area_percent",
        "sensitivity_factor",
        "rsf_corrected_area",
        "relative_atomic_percent_screening",
        "model",
        "background",
        "confidence",
        "assignment_source",
        "status",
        "notes",
    ]


def _component_window(component: dict[str, Any]) -> tuple[float, float] | None:
    value = component.get("binding_energy_window_eV") or component.get("window_eV") or component.get("energy_window_eV")
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        low = float(value[0])
        high = float(value[1])
    except (TypeError, ValueError):
        return None
    return (min(low, high), max(low, high))


def _component_sensitivity_factor(component: dict[str, Any]) -> float | None:
    value = component.get("sensitivity_factor", component.get("rsf"))
    try:
        coerced = float(value)
    except (TypeError, ValueError):
        return None
    return coerced if coerced > 0 else None


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


def _candidate_energy_window(value: Any, *names: str) -> list[float] | None:
    if not isinstance(value, dict):
        return None
    for name in names:
        raw = value.get(name)
        if raw is None:
            continue
        if isinstance(raw, str):
            raw = [part.strip() for part in raw.replace("to", ",").replace("-", ",").split(",")]
        if isinstance(raw, dict):
            low_raw = raw.get("min_eV", raw.get("min", raw.get("low_eV", raw.get("low"))))
            high_raw = raw.get("max_eV", raw.get("max", raw.get("high_eV", raw.get("high"))))
            raw = [low_raw, high_raw]
        if not isinstance(raw, list | tuple) or len(raw) != 2:
            continue
        try:
            low = float(raw[0])
            high = float(raw[1])
        except (TypeError, ValueError):
            continue
        if np.isfinite(low) and np.isfinite(high):
            return [min(low, high), max(low, high)]
    low = _candidate_number(value, "binding_energy_min_eV", "be_min_eV", "window_min_eV", "min_binding_energy_eV")
    high = _candidate_number(value, "binding_energy_max_eV", "be_max_eV", "window_max_eV", "max_binding_energy_eV")
    if low is not None and high is not None:
        return [min(low, high), max(low, high)]
    return None


def _normalize_parameter_origin(value: Any, warnings: list[dict[str, Any]], *, candidate_id: str) -> str:
    origin = str(value or "source_suggested").strip().lower().replace(" ", "_")
    if origin in XPS_PARAMETER_ORIGINS:
        return origin
    warnings.append(
        _warning(
            "xps_parameter_suggestion_origin_normalized",
            "XPS parameter suggestion parameter_origin was not recognized and was recorded as source_suggested.",
            severity="low",
            candidate_id=candidate_id,
            supplied_parameter_origin=origin,
        )
    )
    return "source_suggested"


def _xps_parameter_suggestion_columns() -> list[str]:
    return [
        "candidate_id",
        "suggestion_type",
        "target_parameter_path",
        "status",
        "requires_user_review",
        "auto_applied",
        "parameter_origin",
        "source_summary",
        "reference_ids",
        "unresolved_reference_ids",
        "applicability_notes",
        "confidence",
        "element",
        "core_level",
        "constraint_id",
        "anchor_component_id",
        "dependent_component_id",
        "center_delta_eV",
        "area_ratio",
        "fwhm_ratio",
        "tougaard_B",
        "tougaard_C_eV2",
        "integration_direction",
        "chemical_state_label",
        "expected_binding_energy_eV",
        "binding_energy_window_eV",
        "calibration_reference",
        "charge_reference_assumption",
        "calibration_group_id",
        "overlap_notes",
        "missing_fields",
        "caveats",
    ]


def _normalize_xps_suggestion_type(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _xps_parameter_source_candidates(source_packet: Any) -> list[Any]:
    if isinstance(source_packet, list):
        return source_packet
    if isinstance(source_packet, dict):
        raw_candidates = source_packet.get("candidates") or source_packet.get("parameters") or source_packet.get("suggestions") or []
        return raw_candidates if isinstance(raw_candidates, list) else []
    return []


def _xps_parameter_source_reference_seeds(
    source_packet: Any,
    *,
    referenced_ids: set[str],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(source_packet, dict):
        return {}
    raw_seeds = source_packet.get("reference_seeds") or {}
    if not raw_seeds:
        return {}
    if not isinstance(raw_seeds, dict):
        warnings.append(
            _warning(
                "xps_parameter_source_reference_seeds_invalid",
                "XPS parameter source packet reference_seeds were ignored because they were not a mapping.",
                severity="medium",
            )
        )
        return {}
    reference_seeds: dict[str, Any] = {}
    for raw_seed_id, raw_seed in raw_seeds.items():
        seed_id = str(raw_seed_id).strip()
        if not seed_id:
            warnings.append(
                _warning(
                    "xps_parameter_source_reference_seed_id_invalid",
                    "An XPS parameter source reference_seed was skipped because its seed id was empty.",
                    severity="medium",
                )
            )
            continue
        if seed_id not in referenced_ids:
            continue
        if not isinstance(raw_seed, dict):
            warnings.append(
                _warning(
                    "xps_parameter_source_reference_seed_ignored",
                    "An XPS parameter source reference_seed was skipped because its metadata was not a mapping.",
                    severity="medium",
                    seed_id=seed_id,
                )
            )
            continue
        reference_seeds[seed_id] = deepcopy(raw_seed)
    return reference_seeds


def _xps_parameter_source_template_candidates() -> list[dict[str, Any]]:
    return [
        {
            "candidate_id": "xps-param-template-spin-orbit-001",
            "suggestion_type": "spin_orbit_constraint",
            "element": "TODO",
            "core_level": "TODO",
            "constraint_id": "xps-spin-template-001",
            "anchor_component_id": "TODO-anchor-component-id",
            "dependent_component_id": "TODO-dependent-component-id",
            "center_delta_eV": None,
            "area_ratio": None,
            "fwhm_ratio": None,
            "parameter_origin": "source_suggested",
            "source_summary": "TODO: summarize the source that supports the spin-orbit separation/ratio values.",
            "applicability_notes": [
                "TODO: describe the sample, oxidation/chemical-state assumptions, region, background, and bounds where this candidate applies."
            ],
            "reference_ids": ["TODO-registered-reference-id"],
            "confidence": "low",
            "caveats": ["Template candidate only; fill numeric values and source metadata before running suggest-parameters."],
        },
        {
            "candidate_id": "xps-param-template-tougaard-001",
            "suggestion_type": "tougaard_parameter",
            "tougaard_B": None,
            "tougaard_C_eV2": None,
            "integration_direction": "toward_higher_binding_energy",
            "parameter_origin": "source_suggested",
            "source_summary": "TODO: summarize the source that supports the Tougaard parameter candidate.",
            "applicability_notes": ["TODO: describe the reviewed background region and material/system where this candidate applies."],
            "reference_ids": ["TODO-registered-reference-id"],
            "confidence": "low",
            "caveats": ["Template candidate only; fill numeric values and source metadata before running suggest-parameters."],
        },
        {
            "candidate_id": "xps-param-template-binding-energy-001",
            "suggestion_type": "binding_energy_candidate",
            "element": "TODO",
            "core_level": "TODO",
            "chemical_state_label": "TODO candidate state label",
            "expected_binding_energy_eV": None,
            "binding_energy_window_eV": [None, None],
            "calibration_reference": "TODO: record the BE reference, e.g. user-confirmed C 1s/adventitious carbon/instrument calibration.",
            "charge_reference_assumption": "TODO: record charge-neutralization or charge-reference assumptions; do not silently apply correction.",
            "parameter_origin": "source_suggested",
            "source_summary": "TODO: summarize the source that supports the binding-energy/chemical-state candidate.",
            "applicability_notes": [
                "TODO: describe sample chemistry, calibration state, fitting/background context, and nearby overlapping peaks where this candidate applies."
            ],
            "reference_ids": ["TODO-registered-reference-id"],
            "confidence": "low",
            "caveats": [
                "Template candidate only; fill BE center/window, calibration assumptions, and source metadata before running suggest-parameters.",
                "This candidate may support discussion but does not prove chemical state or composition by itself.",
            ],
        },
    ]


def _candidate_identity(candidate: dict[str, Any]) -> str:
    return str(candidate.get("candidate_id") or candidate.get("suggestion_id") or "").strip()


def _candidate_matches_filters(
    candidate: dict[str, Any],
    *,
    include_candidates: set[str],
    suggestion_types: set[str],
    elements: set[str],
    core_levels: set[str],
) -> bool:
    if include_candidates and _candidate_identity(candidate) not in include_candidates:
        return False
    if suggestion_types and _normalize_xps_suggestion_type(candidate.get("suggestion_type") or candidate.get("parameter_type") or candidate.get("type")) not in suggestion_types:
        return False
    if elements and str(candidate.get("element") or "").strip().lower() not in elements:
        return False
    if core_levels and str(candidate.get("core_level") or "").strip().lower() not in core_levels:
        return False
    return True


def build_xps_parameter_source_packet(
    root: Path,
    *,
    project_id: str,
    library_path: Path | None = None,
    builtin_library: str | None = None,
    literature_manifest_path: Path | None = None,
    output_path: Path | None = None,
    include_candidates: list[str] | None = None,
    suggestion_types: list[str] | None = None,
    elements: list[str] | None = None,
    core_levels: list[str] | None = None,
    template: bool = False,
    created_at: str | None = None,
) -> dict[str, Any]:
    selected_source_count = sum(bool(value) for value in [library_path, builtin_library, literature_manifest_path, template])
    if selected_source_count > 1:
        raise XPSProcessingError(
            "Use only one of --library-file, --builtin-library, --literature-manifest, or --write-template for XPS source-packet generation"
        )

    template_mode = template and library_path is None and literature_manifest_path is None
    literature_mode = literature_manifest_path is not None
    builtin_mode = not template_mode and not literature_mode and library_path is None
    if builtin_mode and not builtin_library:
        builtin_library = BUILTIN_XPS_PARAMETER_LIBRARY_DEFAULT
    day = _created_day(created_at)
    timestamp = created_at or EARecord.now_iso()
    source_packet_id = next_id(root, "xps_source_packet", day)
    if output_path is None:
        if template_mode:
            output_path = root / "templates" / "xps_parameter_source_packet.yml"
        else:
            output_path = root / "suggestions" / "xps" / "source-packets" / f"{source_packet_id}.yml"
    elif not output_path.is_absolute():
        output_path = root / output_path
    assert_not_raw_output_path(root, output_path)

    warnings: list[dict[str, Any]] = []
    library_ref: str | None = None
    library_kind = "template" if template_mode else "local_file"
    source_library: Any = {}
    if template_mode:
        raw_candidates = _xps_parameter_source_template_candidates()
    elif builtin_mode:
        source_library = _builtin_xps_parameter_library(str(builtin_library))
        raw_candidates = _xps_parameter_source_candidates(source_library)
        library_ref = f"builtin:{builtin_library}"
        library_kind = "built_in"
    elif literature_mode:
        source_path = literature_manifest_path if literature_manifest_path and literature_manifest_path.is_absolute() else root / literature_manifest_path if literature_manifest_path else None
        if source_path is None:
            raise XPSProcessingError("XPS literature manifest path was not supplied")
        try:
            source_library, manifest_warnings = confirmed_source_packet_library(
                root,
                manifest_path=source_path,
                method="xps",
                method_aliases={"xps", "xps_parameter", "xps_parameter_source_packet", "surface_spectroscopy"},
            )
        except SourcePacketManifestError as exc:
            raise XPSProcessingError(str(exc)) from exc
        warnings.extend(manifest_warnings)
        raw_candidates = _xps_parameter_source_candidates(source_library)
        library_ref = _relative_to_root(root, source_path)
        library_kind = "confirmed_literature_manifest"
    else:
        source_path = library_path if library_path and library_path.is_absolute() else root / library_path if library_path else None
        if source_path is None or not source_path.exists():
            raise XPSProcessingError(f"XPS parameter library file not found: {library_path}")
        library_ref = _relative_to_root(root, source_path)
        source_library = read_yaml(source_path)
        raw_candidates = _xps_parameter_source_candidates(source_library)

    include_set = {str(item).strip() for item in include_candidates or [] if str(item).strip()}
    type_set = {_normalize_xps_suggestion_type(item) for item in suggestion_types or [] if str(item).strip()}
    element_set = {str(item).strip().lower() for item in elements or [] if str(item).strip()}
    core_level_set = {str(item).strip().lower() for item in core_levels or [] if str(item).strip()}
    selected: list[dict[str, Any]] = []
    for index, raw_candidate in enumerate(raw_candidates, start=1):
        if not isinstance(raw_candidate, dict):
            warnings.append(
                _warning(
                    "xps_parameter_source_candidate_ignored",
                    "An XPS parameter source candidate was not a mapping and was skipped while building the source packet.",
                    severity="medium",
                    candidate_index=index,
                )
            )
            continue
        if not _candidate_matches_filters(
            raw_candidate,
            include_candidates=include_set,
            suggestion_types=type_set,
            elements=element_set,
            core_levels=core_level_set,
        ):
            continue
        candidate = deepcopy(raw_candidate)
        candidate.setdefault("parameter_origin", "source_suggested")
        selected.append(candidate)

    if not raw_candidates:
        warnings.append(
            _warning(
                "xps_parameter_source_library_empty",
                "No XPS parameter candidates were found in the source library.",
                severity="medium",
            )
        )
    if raw_candidates and not selected:
        warnings.append(
            _warning(
                "xps_parameter_source_no_matches",
                "No XPS parameter candidates matched the requested filters.",
                severity="medium",
            )
        )

    candidate_reference_ids = {reference_id for candidate in selected for reference_id in _coerce_string_list(candidate.get("reference_ids"))}
    guidance_reference_ids = (
        _coerce_string_list(source_library.get("guidance_reference_ids")) if isinstance(source_library, dict) else []
    )
    reference_ids = sorted(candidate_reference_ids | set(guidance_reference_ids))
    reference_seeds = _xps_parameter_source_reference_seeds(
        source_library,
        referenced_ids=set(reference_ids),
        warnings=warnings,
    )
    packet_ref = _relative_to_root(root, output_path)
    status = "template_requires_user_edit" if template_mode else ("ready_for_suggest_parameters" if selected else "no_matching_candidates")
    packet = {
        "schema_version": "0.2",
        "source_packet_id": source_packet_id,
        "project_id": project_id,
        "status": status,
        "created_at": timestamp,
        "updated_at": timestamp,
        "source": "ea.xps.parameter_source_packet:v0.2",
        "source_library_kind": library_kind,
        "source_library_ref": library_ref,
        "source_manifest_ref": source_library.get("source_manifest_ref") if literature_mode and isinstance(source_library, dict) else None,
        "confirmation_status": source_library.get("confirmation_status") if literature_mode and isinstance(source_library, dict) else None,
        "reference_seed_count": len(reference_seeds),
        "reference_seeds": reference_seeds,
        "guidance_notes": _coerce_string_list(source_library.get("guidance_notes")) if isinstance(source_library, dict) else [],
        "guidance_reference_ids": guidance_reference_ids,
        "candidate_count": len(selected),
        "candidates": selected,
        "filters": {
            "include_candidates": sorted(include_set),
            "suggestion_types": sorted(type_set),
            "elements": sorted(element_set),
            "core_levels": sorted(core_level_set),
        },
        "reference_ids": reference_ids,
        "warnings": warnings,
        "next_steps": [
            "If this packet includes built-in or local reference_seeds, or confirmed-literature reference_seeds, run `ea references register-seeds` or replace those seed IDs with registered project references before treating suggestions as report evidence.",
            "Review and edit this packet until every candidate has source_summary, applicability_notes, reference_ids, and required numeric or binding-energy/calibration-assumption fields for its suggestion_type.",
            "Run `ea xps suggest-parameters` on this packet to create traceable suggestion records before copying values into processing parameters.",
        ],
        "boundaries": [
            "Source packets are staging artifacts and do not apply values to XPS processing parameters.",
            "reference_seeds are registration hints only; they do not inject report citations, download PDFs, apply XPS parameters, prove chemical states, or calculate composition.",
            "This source-packet builder is a deterministic staging step and does not perform unconfirmed live network lookup or parse full text during the command. Values may originate from user-provided data, local libraries, project literature records, or separately confirmed literature/search connectors, and EA may use those sources to prepare candidates. The packet still does not auto-choose or apply components/backgrounds/bounds/peak shapes, apply fitting, prove chemical states, or calculate composition.",
            "Confirmed-literature manifests are source-candidate manifests only; they do not register references, inject report citations, apply XPS parameters, fit backgrounds/components, prove chemical states, or calculate composition.",
        ],
    }
    write_yaml(output_path, packet)
    provenance_path = write_provenance_entry(
        root,
        workflow="xps_parameter_source_packet",
        inputs={"records": [library_ref] if library_ref else [], "files": []},
        outputs={"records": [packet_ref], "files": []},
        parameters={
            "candidate_count": len(selected),
            "reference_seed_count": len(reference_seeds),
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
        "source_library_kind": library_kind,
        "source_library_ref": library_ref,
        "candidate_count": len(selected),
        "reference_seed_count": len(reference_seeds),
        "reference_ids": reference_ids,
        "warnings": warnings,
        "provenance": str(provenance_path),
    }


def _normalize_xps_parameter_candidate(
    raw_candidate: Any,
    *,
    suggestion_id: str,
    number: int,
    registered_references: set[str],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(raw_candidate, dict):
        candidate_id = f"{suggestion_id}-cand-{number:03d}"
        warnings.append(
            _warning(
                "xps_parameter_suggestion_ignored",
                "An XPS parameter suggestion candidate was not a mapping and was recorded as invalid.",
                severity="medium",
                candidate_id=candidate_id,
            )
        )
        return {
            "candidate_id": candidate_id,
            "suggestion_type": "unknown",
            "status": "invalid_candidate_mapping",
            "requires_user_review": True,
            "auto_applied": False,
            "missing_fields": ["candidate_mapping"],
        }

    candidate_id = str(raw_candidate.get("candidate_id") or raw_candidate.get("suggestion_id") or f"{suggestion_id}-cand-{number:03d}")
    suggestion_type = _normalize_xps_suggestion_type(raw_candidate.get("suggestion_type") or raw_candidate.get("parameter_type") or raw_candidate.get("type"))
    reference_ids = _coerce_string_list(raw_candidate.get("reference_ids"))
    applicability_notes = _coerce_string_list(raw_candidate.get("applicability_notes"))
    caveats = _coerce_string_list(raw_candidate.get("caveats"))
    parameter_origin = _normalize_parameter_origin(raw_candidate.get("parameter_origin"), warnings, candidate_id=candidate_id)
    source_summary = str(raw_candidate.get("source_summary") or raw_candidate.get("reference_summary") or "").strip()
    confidence = str(raw_candidate.get("confidence") or "low").strip().lower()
    unresolved_reference_ids = [reference_id for reference_id in reference_ids if reference_id not in registered_references]
    missing_fields: list[str] = []

    if suggestion_type not in XPS_PARAMETER_SUGGESTION_TYPES:
        missing_fields.append("suggestion_type")
    if not source_summary:
        missing_fields.append("source_summary")
    if not reference_ids:
        missing_fields.append("reference_ids")
    if not applicability_notes:
        missing_fields.append("applicability_notes")

    candidate: dict[str, Any] = {
        "candidate_id": candidate_id,
        "suggestion_type": suggestion_type or "unknown",
        "requires_user_review": True,
        "auto_applied": False,
        "parameter_origin": parameter_origin,
        "source_summary": source_summary,
        "reference_ids": reference_ids,
        "unresolved_reference_ids": unresolved_reference_ids,
        "applicability_notes": applicability_notes,
        "confidence": confidence,
        "element": str(raw_candidate.get("element") or "").strip() or None,
        "core_level": str(raw_candidate.get("core_level") or "").strip() or None,
        "caveats": caveats,
    }

    if suggestion_type == "spin_orbit_constraint":
        center_delta = _candidate_number(raw_candidate, "center_delta_eV", "dependent_center_delta_eV", "center_offset_eV")
        area_ratio = _candidate_number(raw_candidate, "area_ratio", "dependent_area_ratio")
        fwhm_ratio = _candidate_number(raw_candidate, "fwhm_ratio", "dependent_fwhm_ratio")
        if center_delta is None:
            missing_fields.append("center_delta_eV")
        if area_ratio is None:
            missing_fields.append("area_ratio")
        if fwhm_ratio is None:
            missing_fields.append("fwhm_ratio")
        if area_ratio is not None and area_ratio <= 0:
            missing_fields.append("positive_area_ratio")
        if fwhm_ratio is not None and fwhm_ratio <= 0:
            missing_fields.append("positive_fwhm_ratio")
        candidate.update(
            {
                "target_parameter_path": "component_fit.spin_orbit_constraints",
                "constraint_id": str(raw_candidate.get("constraint_id") or candidate_id),
                "anchor_component_id": str(raw_candidate.get("anchor_component_id") or "").strip() or None,
                "dependent_component_id": str(raw_candidate.get("dependent_component_id") or "").strip() or None,
                "center_delta_eV": center_delta,
                "area_ratio": area_ratio,
                "fwhm_ratio": fwhm_ratio,
            }
        )
    elif suggestion_type == "tougaard_parameter":
        tougaard_b = _candidate_number(raw_candidate, "tougaard_B", "B", "b1")
        tougaard_c = _candidate_number(raw_candidate, "tougaard_C_eV2", "C_eV2", "C")
        if tougaard_b is None and tougaard_c is None:
            missing_fields.append("tougaard_B_or_tougaard_C_eV2")
        if tougaard_b is not None and tougaard_b <= 0:
            missing_fields.append("positive_tougaard_B")
        if tougaard_c is not None and tougaard_c <= 0:
            missing_fields.append("positive_tougaard_C_eV2")
        candidate.update(
            {
                "target_parameter_path": "background_subtraction.tougaard",
                "tougaard_B": tougaard_b,
                "tougaard_C_eV2": tougaard_c,
                "integration_direction": str(raw_candidate.get("integration_direction") or "").strip() or None,
            }
        )
    elif suggestion_type == "binding_energy_candidate":
        expected_binding_energy = _candidate_number(
            raw_candidate,
            "expected_binding_energy_eV",
            "binding_energy_eV",
            "center_binding_energy_eV",
            "center_eV",
            "expected_center_eV",
        )
        binding_energy_window = _candidate_energy_window(
            raw_candidate,
            "binding_energy_window_eV",
            "binding_energy_range_eV",
            "be_window_eV",
            "window_eV",
        )
        chemical_state_label = str(
            raw_candidate.get("chemical_state_label")
            or raw_candidate.get("state_label")
            or raw_candidate.get("assignment_label")
            or ""
        ).strip()
        calibration_reference = str(
            raw_candidate.get("calibration_reference")
            or raw_candidate.get("binding_energy_reference")
            or raw_candidate.get("energy_reference")
            or ""
        ).strip()
        charge_reference_assumption = str(
            raw_candidate.get("charge_reference_assumption")
            or raw_candidate.get("charge_reference_notes")
            or raw_candidate.get("referencing_assumption")
            or ""
        ).strip()
        if not chemical_state_label:
            missing_fields.append("chemical_state_label")
        if expected_binding_energy is None and binding_energy_window is None:
            missing_fields.append("expected_binding_energy_eV_or_binding_energy_window_eV")
        if not calibration_reference:
            missing_fields.append("calibration_reference")
        if not charge_reference_assumption:
            missing_fields.append("charge_reference_assumption")
        if expected_binding_energy is not None and binding_energy_window is not None:
            low, high = binding_energy_window
            if expected_binding_energy < low or expected_binding_energy > high:
                missing_fields.append("expected_binding_energy_within_window")
        candidate.update(
            {
                "target_parameter_path": "interpretation.binding_energy_candidates",
                "chemical_state_label": chemical_state_label or None,
                "expected_binding_energy_eV": expected_binding_energy,
                "binding_energy_window_eV": binding_energy_window,
                "binding_energy_min_eV": binding_energy_window[0] if binding_energy_window else None,
                "binding_energy_max_eV": binding_energy_window[1] if binding_energy_window else None,
                "calibration_reference": calibration_reference or None,
                "charge_reference_assumption": charge_reference_assumption or None,
                "calibration_group_id": str(raw_candidate.get("calibration_group_id") or "").strip() or None,
                "overlap_notes": _coerce_string_list(raw_candidate.get("overlap_notes") or raw_candidate.get("overlap_risks")),
            }
        )
    else:
        candidate["target_parameter_path"] = None

    if missing_fields:
        status = "invalid_missing_required_metadata"
    elif unresolved_reference_ids:
        status = "needs_reference_registration"
    else:
        status = "ready_for_user_review"
    candidate["status"] = status
    candidate["missing_fields"] = missing_fields
    if unresolved_reference_ids:
        warnings.append(
            _warning(
                "xps_parameter_suggestion_reference_unresolved",
                "An XPS parameter suggestion cites reference_ids that are not registered in the project reference index.",
                severity="medium",
                candidate_id=candidate_id,
                unresolved_reference_ids=unresolved_reference_ids,
            )
        )
    if missing_fields:
        warnings.append(
            _warning(
                "xps_parameter_suggestion_missing_metadata",
                "An XPS parameter suggestion is missing required source/applicability or parameter metadata.",
                severity="medium",
                candidate_id=candidate_id,
                missing_fields=missing_fields,
            )
        )
    return candidate


def suggest_xps_parameters(
    root: Path,
    *,
    project_id: str,
    source_path: Path,
    related_records: list[str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    source_packet = read_yaml(source_path)
    raw_candidates = _xps_parameter_source_candidates(source_packet)
    day = _created_day(created_at)
    timestamp = created_at or EARecord.now_iso()
    suggestion_id = next_id(root, "suggestion", day)
    output_dir = root / "suggestions" / "xps" / suggestion_id
    record_path = output_dir / "xps_parameter_suggestions.yml"
    table_path = output_dir / "xps_parameter_suggestions.csv"
    for path in [record_path, table_path]:
        assert_not_raw_output_path(root, path)

    warnings: list[dict[str, Any]] = []
    if not raw_candidates:
        warnings.append(
            _warning(
                "xps_parameter_suggestion_empty_source",
                "No XPS parameter candidates were found in the source packet.",
                severity="medium",
            )
        )
    registered_references = _registered_reference_ids(root)
    candidates = [
        _normalize_xps_parameter_candidate(
            candidate,
            suggestion_id=suggestion_id,
            number=index,
            registered_references=registered_references,
            warnings=warnings,
        )
        for index, candidate in enumerate(raw_candidates, start=1)
    ]
    table = pd.DataFrame(candidates, columns=_xps_parameter_suggestion_columns())
    for column in [
        "reference_ids",
        "unresolved_reference_ids",
        "applicability_notes",
        "binding_energy_window_eV",
        "overlap_notes",
        "missing_fields",
        "caveats",
    ]:
        if column in table.columns:
            table[column] = table[column].apply(lambda value: "; ".join(str(item) for item in value) if isinstance(value, list) else value)

    ready_count = sum(1 for candidate in candidates if candidate.get("status") == "ready_for_user_review")
    unresolved_count = sum(1 for candidate in candidates if candidate.get("status") == "needs_reference_registration")
    invalid_count = sum(1 for candidate in candidates if str(candidate.get("status", "")).startswith("invalid"))
    status = "ready_for_user_review" if ready_count else ("needs_reference_registration" if unresolved_count else "needs_source_metadata")
    source_ref = _relative_to_root(root, source_path)
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
        "source": "ea.xps.parameter_suggestions:v0.2",
        "source_packet_ref": source_ref,
        "table_ref": table_ref,
        "candidate_count": len(candidates),
        "ready_for_user_review_count": ready_count,
        "needs_reference_registration_count": unresolved_count,
        "invalid_count": invalid_count,
        "candidates": candidates,
        "related_records": related_records,
        "reference_ids": all_reference_ids,
        "warnings": warnings,
        "next_steps": [
            "Register or correct unresolved reference_ids before using source-backed values.",
            "If no suitable source packet exists, create one from a reviewed local library, project literature record, or user-confirmed literature/search workflow before review.",
            "Ask the user to review ready candidates before copying any values into XPS processing parameters.",
            "When accepted, copy spin-orbit candidates into component_fit.spin_orbit_constraints or Tougaard candidates into background_subtraction parameters with review refs.",
            "When accepted, keep binding-energy candidates in report/memory interpretation context only unless a later reviewed component model explicitly uses them.",
        ],
        "boundaries": [
            "Suggestion records are advisory and auto_applied is always false.",
            "This suggestion-record step is a validation/review-record step and does not perform unconfirmed live network lookup itself. EA may prepare source packets from reviewed local libraries, project literature, user-provided sources, or user-confirmed literature/search workflows before this step; this step validates supplied source packets/reference IDs and does not auto-select or apply components/backgrounds/bounds/peak shapes, apply fitting, silently calibrate spectra, apply charge correction, prove chemical states/composition, or calculate composition.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(table_path, index=False)
    write_yaml(record_path, record)
    provenance_path = write_provenance_entry(
        root,
        workflow="xps_parameter_suggestion",
        inputs={"records": [source_ref, *related_records], "files": []},
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
        "invalid_count": invalid_count,
        "warnings": warnings,
    }


def _normalize_review_target_ref(root: Path, value: Any) -> str:
    target = str(value or "").strip()
    if not target:
        return ""
    target_path = Path(target)
    if target_path.is_absolute():
        return _relative_to_root(root, target_path)
    return _relative_to_root(root, root / target_path)


def _memory_confidence(value: Any) -> str:
    normalized = str(value or "low").strip().lower()
    if normalized in {"high", "medium", "low", "insufficient"}:
        return normalized
    return "low"


def _format_memory_list(items: list[Any]) -> str:
    values = [str(item) for item in items if str(item).strip()]
    return ", ".join(values) if values else "none recorded"


def _xps_candidate_parameter_values_text(candidate: dict[str, Any]) -> str:
    suggestion_type = str(candidate.get("suggestion_type") or "")
    if suggestion_type == "spin_orbit_constraint":
        values = [
            f"constraint_id={candidate.get('constraint_id') or 'not recorded'}",
            f"center_delta_eV={candidate.get('center_delta_eV')}",
            f"area_ratio={candidate.get('area_ratio')}",
            f"fwhm_ratio={candidate.get('fwhm_ratio')}",
            f"anchor_component_id={candidate.get('anchor_component_id') or 'not recorded'}",
            f"dependent_component_id={candidate.get('dependent_component_id') or 'not recorded'}",
        ]
        return "; ".join(values)
    if suggestion_type == "tougaard_parameter":
        values = [
            f"tougaard_B={candidate.get('tougaard_B')}",
            f"tougaard_C_eV2={candidate.get('tougaard_C_eV2')}",
            f"integration_direction={candidate.get('integration_direction') or 'not recorded'}",
        ]
        return "; ".join(values)
    if suggestion_type == "binding_energy_candidate":
        values = [
            f"chemical_state_label={candidate.get('chemical_state_label') or 'not recorded'}",
            f"expected_binding_energy_eV={candidate.get('expected_binding_energy_eV')}",
            f"binding_energy_window_eV={candidate.get('binding_energy_window_eV') or 'not recorded'}",
            f"calibration_reference={candidate.get('calibration_reference') or 'not recorded'}",
            f"charge_reference_assumption={candidate.get('charge_reference_assumption') or 'not recorded'}",
            f"calibration_group_id={candidate.get('calibration_group_id') or 'not recorded'}",
            f"overlap_notes={_format_memory_list(_coerce_string_list(candidate.get('overlap_notes')))}",
        ]
        return "; ".join(values)
    return "no supported XPS parameter values recorded"


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
    if status.startswith("invalid"):
        return "invalid_or_incomplete"
    return "other"


def _review_value(value: Any) -> str:
    if value in (None, "", [], {}):
        return "not recorded"
    if isinstance(value, list | tuple):
        return ", ".join(str(item) for item in value if str(item).strip()) or "not recorded"
    if isinstance(value, dict):
        parts = [f"{key}={item}" for key, item in value.items() if item not in (None, "", [], {})]
        return "; ".join(parts) or "not recorded"
    return str(value)


def _xps_review_candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    status = str(candidate.get("status") or "unknown")
    if status == "ready_for_user_review":
        if candidate.get("suggestion_type") == "binding_energy_candidate":
            action = "Ask the user to accept, reject, or edit this source-backed binding-energy candidate before any report or memory discussion; do not treat it as chemical-state proof."
        else:
            action = "Ask the user to accept, reject, or edit this source-backed parameter candidate before any report/memory/processing reuse."
    elif status == "needs_reference_registration":
        action = "Register, replace, or remove unresolved reference_ids before treating this candidate as report evidence or method memory."
    elif status.startswith("invalid"):
        action = "Fix missing source, parameter, reference, or applicability metadata before user review."
    else:
        action = "Inspect status and decide whether more source/context work is needed."
    return {
        "candidate_id": str(candidate.get("candidate_id") or ""),
        "review_group": _review_group_for_status(status),
        "status": status,
        "suggestion_type": str(candidate.get("suggestion_type") or "unknown"),
        "target_parameter_path": str(candidate.get("target_parameter_path") or "not recorded"),
        "element": str(candidate.get("element") or "not specified"),
        "core_level": str(candidate.get("core_level") or "not specified"),
        "confidence": str(candidate.get("confidence") or "low"),
        "parameter_origin": str(candidate.get("parameter_origin") or "not recorded"),
        "parameter_values": _xps_candidate_parameter_values_text(candidate),
        "chemical_state_label": str(candidate.get("chemical_state_label") or "not recorded"),
        "reference_ids": _coerce_string_list(candidate.get("reference_ids")),
        "unresolved_reference_ids": _coerce_string_list(candidate.get("unresolved_reference_ids")),
        "missing_fields": _coerce_string_list(candidate.get("missing_fields")),
        "source_summary": str(candidate.get("source_summary") or "not recorded"),
        "applicability_notes": _coerce_string_list(candidate.get("applicability_notes")),
        "caveats": _coerce_string_list(candidate.get("caveats")),
        "recommended_action": action,
    }


def _render_xps_review_package_markdown(package: dict[str, Any]) -> str:
    lines = [
        "# XPS Parameter Suggestion Review Package",
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
                f"- suggestion_type: `{candidate.get('suggestion_type')}`",
                f"- target_parameter_path: `{candidate.get('target_parameter_path')}`",
                f"- element/core_level: `{candidate.get('element')}` / `{candidate.get('core_level')}`",
                f"- chemical_state_label: `{candidate.get('chemical_state_label')}`",
                f"- parameter_values: {candidate.get('parameter_values')}",
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


def prepare_xps_parameter_review_package(
    root: Path,
    *,
    project_id: str,
    suggestion_path: Path,
    candidate_ids: list[str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    resolved_suggestion_path = suggestion_path if suggestion_path.is_absolute() else root / suggestion_path
    suggestion = read_yaml(resolved_suggestion_path)
    if suggestion.get("source") != "ea.xps.parameter_suggestions:v0.2":
        raise XPSProcessingError(f"Not an XPS parameter suggestion record: {suggestion_path}")

    suggestion_ref = _relative_to_root(root, resolved_suggestion_path)
    suggestion_project_id = str(suggestion.get("project_id") or "")
    if suggestion_project_id and project_id and suggestion_project_id != project_id:
        raise XPSProcessingError(f"Project ID mismatch: suggestion has {suggestion_project_id}, request has {project_id}")

    candidates = [candidate for candidate in suggestion.get("candidates", []) if isinstance(candidate, dict)]
    requested_ids = [str(candidate_id) for candidate_id in candidate_ids or [] if str(candidate_id).strip()]
    requested_set = set(requested_ids)
    selected = [candidate for candidate in candidates if not requested_set or str(candidate.get("candidate_id")) in requested_set]
    found_ids = {str(candidate.get("candidate_id")) for candidate in selected}
    missing_candidate_ids = [candidate_id for candidate_id in requested_ids if candidate_id not in found_ids]
    warnings: list[dict[str, Any]] = [
        _warning(
            "xps_review_package_candidate_not_found",
            "A requested XPS parameter suggestion candidate_id was not found in the suggestion record.",
            severity="medium",
            candidate_id=candidate_id,
        )
        for candidate_id in missing_candidate_ids
    ]

    summaries = [_xps_review_candidate_summary(candidate) for candidate in selected]
    group_actions = {
        "ready_for_user_review": "Review these candidates with the user; create a ReviewRecord only after explicit confirmation.",
        "needs_reference_registration": "Resolve references first with `ea references register-seeds` or `ea references add`, then regenerate suggestions or review with caveats.",
        "invalid_or_incomplete": "Fix candidate metadata before asking the user to review.",
        "other": "Inspect manually before downstream use.",
    }
    groups = []
    for group_name in ["ready_for_user_review", "needs_reference_registration", "invalid_or_incomplete", "other"]:
        ids = [summary["candidate_id"] for summary in summaries if summary["review_group"] == group_name]
        if ids:
            groups.append({"group": group_name, "candidate_ids": ids, "recommended_action": group_actions[group_name]})

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
        "method": "xps",
        "source": "ea.xps.parameter_review_package:v0.2",
        "status": "review_package_prepared" if selected else "no_candidates_selected",
        "created_at": timestamp,
        "updated_at": timestamp,
        "suggestion_id": suggestion.get("suggestion_id"),
        "suggestion_ref": suggestion_ref,
        "table_ref": suggestion.get("table_ref"),
        "source_packet_ref": suggestion.get("source_packet_ref"),
        "related_records": suggestion.get("related_records") or [],
        "review_target_type": "xps_parameter_suggestions",
        "review_target_ref": suggestion_ref,
        "candidate_count": len(candidates),
        "selected_candidate_count": len(selected),
        "requested_candidate_ids": requested_ids,
        "missing_candidate_ids": missing_candidate_ids,
        "overall_status_counts": _review_status_counts(candidates),
        "selected_status_counts": _review_status_counts(selected),
        "groups": groups,
        "candidate_summaries": summaries,
        "reference_ids": sorted({ref for candidate in summaries for ref in candidate.get("reference_ids", [])}),
        "unresolved_reference_ids": sorted({ref for candidate in summaries for ref in candidate.get("unresolved_reference_ids", [])}),
        "recommended_commands": {
            "create_review_record": (
                "ea review add /path/to/ea-project --target-type xps_parameter_suggestions "
                f"--target-ref {suggestion_ref} --user-response \"可以，保存\" "
                "--reviewed-content \"User reviewed the listed XPS parameter candidates; record accepted/rejected/edited candidate IDs.\""
            ),
            "report_with_suggestion": (
                "ea xps report /path/to/ea-project --metadata <xps_metadata.yml> "
                f"--parameter-suggestion {suggestion_ref}"
            ),
            "propose_memory_after_review": (
                f"ea xps propose-memory /path/to/ea-project --suggestion {suggestion_ref} --review-ref <review-id>"
            ),
        },
        "next_steps": [
            "Ask the user to review ready candidates and state which candidate IDs are accepted, rejected, edited, or deferred.",
            "Resolve unresolved references before using candidates as report evidence unless the report explicitly discusses them as unresolved.",
            "After a confirmed ReviewRecord targets this suggestion record, copy values into processing parameters only through a separate reviewed processing step.",
        ],
        "boundaries": [
            "This package prepares review context only; it does not create a ReviewRecord.",
            "It does not apply XPS parameters, run fitting/background subtraction, inject report citations, write confirmed memory, prove chemical state, or calculate composition.",
            "Unresolved or invalid candidates remain visible so the user can decide whether to fix, exclude, or discuss them with caveats.",
        ],
        "warnings": warnings,
    }
    write_yaml(package_path, package)
    markdown_path.write_text(_render_xps_review_package_markdown(package), encoding="utf-8")
    provenance_path = write_provenance_entry(
        root,
        workflow="xps_parameter_review_package",
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
    markdown_path.write_text(_render_xps_review_package_markdown(package), encoding="utf-8")
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


def _xps_candidate_is_valid_for_memory(candidate: dict[str, Any], *, allow_non_ready: bool) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    status = str(candidate.get("status") or "")
    suggestion_type = str(candidate.get("suggestion_type") or "")
    if status != "ready_for_user_review":
        reasons.append(f"status:{status or 'missing'}")
    if candidate.get("auto_applied") is not False:
        reasons.append("auto_applied_not_false")
    if suggestion_type not in XPS_PARAMETER_SUGGESTION_TYPES:
        reasons.append("unsupported_suggestion_type")
    if candidate.get("unresolved_reference_ids"):
        reasons.append("unresolved_reference_ids")
    if candidate.get("missing_fields"):
        reasons.append("missing_required_metadata")
    if not candidate.get("reference_ids"):
        reasons.append("missing_reference_ids")
    if not str(candidate.get("source_summary") or "").strip():
        reasons.append("missing_source_summary")
    if not _coerce_string_list(candidate.get("applicability_notes")):
        reasons.append("missing_applicability_notes")
    if not str(candidate.get("target_parameter_path") or "").strip():
        reasons.append("missing_target_parameter_path")
    if suggestion_type == "spin_orbit_constraint":
        for field in ["center_delta_eV", "area_ratio", "fwhm_ratio"]:
            if candidate.get(field) is None:
                reasons.append(f"missing_{field}")
    elif suggestion_type == "tougaard_parameter":
        if candidate.get("tougaard_B") is None and candidate.get("tougaard_C_eV2") is None:
            reasons.append("missing_tougaard_B_or_tougaard_C_eV2")
    elif suggestion_type == "binding_energy_candidate":
        if not str(candidate.get("chemical_state_label") or "").strip():
            reasons.append("missing_chemical_state_label")
        if candidate.get("expected_binding_energy_eV") is None and not candidate.get("binding_energy_window_eV"):
            reasons.append("missing_expected_binding_energy_eV_or_binding_energy_window_eV")
        if not str(candidate.get("calibration_reference") or "").strip():
            reasons.append("missing_calibration_reference")
        if not str(candidate.get("charge_reference_assumption") or "").strip():
            reasons.append("missing_charge_reference_assumption")

    if not allow_non_ready:
        return not reasons, reasons
    hard_blockers = {
        "auto_applied_not_false",
        "unsupported_suggestion_type",
        "missing_required_metadata",
        "missing_source_summary",
        "missing_applicability_notes",
        "missing_target_parameter_path",
        "missing_chemical_state_label",
        "missing_expected_binding_energy_eV_or_binding_energy_window_eV",
        "missing_calibration_reference",
        "missing_charge_reference_assumption",
    }
    return not any(reason in hard_blockers or reason.startswith("status:invalid") for reason in reasons), reasons


def _format_xps_parameter_memory_text(candidate: dict[str, Any], *, suggestion_id: str, review_ref: str) -> str:
    candidate_id = str(candidate.get("candidate_id") or "unknown")
    suggestion_type = str(candidate.get("suggestion_type") or "unknown")
    target_path = str(candidate.get("target_parameter_path") or "not recorded")
    element = str(candidate.get("element") or "not specified")
    core_level = str(candidate.get("core_level") or "not specified")
    status = str(candidate.get("status") or "unknown")
    confidence = _memory_confidence(candidate.get("confidence"))
    parameter_origin = str(candidate.get("parameter_origin") or "not recorded")
    reference_ids = _format_memory_list(_coerce_string_list(candidate.get("reference_ids")))
    applicability = _format_memory_list(_coerce_string_list(candidate.get("applicability_notes")))
    caveats = _format_memory_list(_coerce_string_list(candidate.get("caveats")))
    unresolved = _format_memory_list(_coerce_string_list(candidate.get("unresolved_reference_ids")))
    source_summary = str(candidate.get("source_summary") or "No source summary recorded.").strip()
    parameter_values = _xps_candidate_parameter_values_text(candidate)
    memory_kind = "interpretation" if suggestion_type == "binding_energy_candidate" else "method-note"
    return (
        f"XPS source-backed parameter candidate `{candidate_id}` from suggestion `{suggestion_id}` was reviewed via `{review_ref}` "
        f"and can be preserved as a draft {memory_kind} memory candidate.\n\n"
        f"- suggestion type: `{suggestion_type}`\n"
        f"- target parameter path: `{target_path}`\n"
        f"- suggestion status: `{status}`\n"
        f"- element/core level: {element} {core_level}\n"
        f"- chemical-state label: {candidate.get('chemical_state_label') or 'not recorded'}\n"
        f"- confidence: `{confidence}`\n"
        f"- parameter origin: `{parameter_origin}`\n"
        f"- parameter values: {parameter_values}\n"
        f"- references: {reference_ids}\n"
        f"- unresolved references: {unresolved}\n"
        f"- source summary: {source_summary}\n"
        f"- applicability notes: {applicability}\n"
        f"- caveats: {caveats}\n\n"
        "Boundary: this is a source-backed XPS parameter candidate only. It does not copy values into processing parameters, "
        "silently calibrate spectra, apply charge correction, perform fitting or background subtraction, prove chemical state/composition, calculate composition, or replace the standard memory review/commit flow."
    )


def propose_xps_parameter_memory_candidates(
    root: Path,
    *,
    project_id: str,
    suggestion_path: Path,
    review_ref: str,
    candidate_ids: list[str] | None = None,
    allow_non_ready: bool = False,
    created_at: str | None = None,
) -> dict[str, Any]:
    resolved_suggestion_path = suggestion_path if suggestion_path.is_absolute() else root / suggestion_path
    suggestion = read_yaml(resolved_suggestion_path)
    if suggestion.get("source") != "ea.xps.parameter_suggestions:v0.2":
        raise XPSProcessingError(f"Not an XPS parameter suggestion record: {suggestion_path}")

    suggestion_ref = _relative_to_root(root, resolved_suggestion_path)
    suggestion_project_id = str(suggestion.get("project_id") or "")
    if suggestion_project_id and project_id and suggestion_project_id != project_id:
        raise XPSProcessingError(f"Project ID mismatch: suggestion has {suggestion_project_id}, request has {project_id}")

    review = require_confirmed_review(root, review_ref)
    review_target_ref = _normalize_review_target_ref(root, review.get("target_ref"))
    if review_target_ref and review_target_ref != suggestion_ref:
        raise XPSProcessingError(
            f"ReviewRecord {review_ref} targets {review.get('target_ref')}, not XPS parameter suggestion {suggestion_ref}"
        )

    candidates = [candidate for candidate in suggestion.get("candidates", []) if isinstance(candidate, dict)]
    requested_ids = [str(candidate_id) for candidate_id in candidate_ids or [] if str(candidate_id).strip()]
    requested_set = set(requested_ids)
    selected = [candidate for candidate in candidates if not requested_set or str(candidate.get("candidate_id")) in requested_set]
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
                "xps_parameter_memory_allow_non_ready_without_selection",
                "--allow-non-ready only applies to explicitly selected --candidate-id values; default selection still uses ready candidates.",
                severity="medium",
            )
        )

    source_refs = [
        suggestion_ref,
        str(suggestion.get("table_ref") or "").strip(),
        str(suggestion.get("source_packet_ref") or "").strip(),
        *[str(ref).strip() for ref in suggestion.get("related_records", []) or []],
    ]
    source_refs = [ref for ref in source_refs if ref]
    provenance_refs = [str(suggestion.get("provenance_ref") or "").strip()]
    provenance_refs = [ref for ref in provenance_refs if ref]
    if not provenance_refs:
        raise XPSProcessingError("XPS parameter suggestion record lacks provenance_ref")

    proposed: list[dict[str, Any]] = []
    output_refs: list[str] = []
    for candidate in selected:
        candidate_id = str(candidate.get("candidate_id") or "")
        candidate_allow_non_ready = bool(allow_non_ready and requested_set and candidate_id in requested_set)
        eligible, reasons = _xps_candidate_is_valid_for_memory(candidate, allow_non_ready=candidate_allow_non_ready)
        if not eligible:
            skipped.append({"candidate_id": candidate_id, "reason": "not_memory_candidate_eligible", "details": reasons})
            continue

        candidate_text = _format_xps_parameter_memory_text(
            candidate,
            suggestion_id=str(suggestion.get("suggestion_id") or resolved_suggestion_path.parent.name),
            review_ref=review_ref,
        )
        suggestion_type = str(candidate.get("suggestion_type") or "")
        memory_category = "interpretation" if suggestion_type == "binding_energy_candidate" else "method_note"
        rationale = (
            f"Generated from XPS parameter suggestion `{suggestion_ref}` candidate `{candidate_id}` after confirmed review `{review_ref}`. "
            f"This preserves a source-backed {memory_category.replace('_', ' ')} candidate for later user review and commit; it does not create confirmed memory, apply parameters, apply charge correction, or prove chemistry."
        )
        memory_path = propose_memory_candidate(
            root,
            project_id=project_id or suggestion_project_id,
            candidate_text=candidate_text,
            source_refs=source_refs + _coerce_string_list(candidate.get("reference_ids")),
            provenance_refs=provenance_refs,
            category=memory_category,
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
                "category": memory_category,
                "confidence": _memory_confidence(candidate.get("confidence")),
                "source_refs": source_refs,
                "provenance_refs": provenance_refs,
            }
        )

    bridge_provenance = None
    if proposed:
        bridge_provenance_path = write_provenance_entry(
            root,
            workflow="xps_parameter_memory_candidate_proposal",
            inputs={"records": [suggestion_ref], "files": []},
            outputs={"records": output_refs + ["memory/candidates/index.yml"], "files": []},
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
        "status": "memory_candidates_proposed" if proposed else "no_memory_candidates_proposed",
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
            "Ready XPS parameter candidates are used by default; non-ready candidates require explicit --candidate-id plus --allow-non-ready and remain caveated.",
            "XPS parameter suggestions do not by themselves apply processing/fitting/background parameters, silently calibrate spectra, apply charge correction, prove chemical state/composition, calculate composition, or replace user review.",
        ],
    }


def _has_record_payload(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_has_record_payload(item) for item in value.values())
    if isinstance(value, list | tuple):
        return any(_has_record_payload(item) for item in value)
    return True


def _background_window(region: dict[str, Any]) -> tuple[float | None, float | None]:
    value = region.get("binding_energy_window_eV") or region.get("window_eV") or region.get("energy_window_eV")
    if isinstance(value, list | tuple) and len(value) >= 2:
        low, high = value[0], value[1]
    else:
        low = region.get("binding_energy_min_eV")
        high = region.get("binding_energy_max_eV")
    try:
        low_value = float(low)
        high_value = float(high)
    except (TypeError, ValueError):
        return None, None
    return min(low_value, high_value), max(low_value, high_value)


def _reviewed_background_region(
    region: dict[str, Any],
    *,
    number: int,
    source: str,
    default_applied: bool,
    default_software: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    region_id = str(region.get("region_id") or region.get("id") or f"xps-background-region-{number:03d}")
    background_type = str(region.get("background_type") or region.get("model_type") or region.get("model") or "unspecified").strip().lower().replace(" ", "_")
    allowed = {"shirley", "tougaard", "linear", "local_minimum", "rolling_quantile", "instrument_applied", "other", "unspecified"}
    if background_type not in allowed:
        warnings.append(
            _warning(
                "xps_background_model_type_unrecognized",
                "A reviewed XPS background model type was preserved but is not one of the built-in vocabulary values.",
                severity="low",
                region_id=region_id,
                background_type=background_type,
            )
        )
    low, high = _background_window(region)
    applied = bool(region.get("applied_to_processed_data", default_applied))
    confidence = str(region.get("confidence") or "low").strip().lower()
    if confidence not in {"high", "medium", "low", "insufficient"}:
        warnings.append(
            _warning(
                "xps_background_confidence_normalized",
                "XPS background model confidence was not one of high/medium/low/insufficient and was normalized to low.",
                severity="low",
                region_id=region_id,
                supplied_confidence=confidence,
            )
        )
        confidence = "low"
    return (
        {
            "region_id": region_id,
            "label": str(region.get("label") or region_id),
            "background_type": background_type,
            "binding_energy_min_eV": low,
            "binding_energy_max_eV": high,
            "applied_to_processed_data": applied,
            "parameters": deepcopy(region.get("parameters") or region.get("model_parameters") or {}),
            "software": deepcopy(region.get("software") or default_software),
            "reference_ids": _coerce_string_list(region.get("reference_ids")),
            "reviewer_notes": _coerce_string_list(region.get("reviewer_notes") or region.get("notes")),
            "caveats": _coerce_string_list(region.get("caveats")),
            "confidence": confidence,
            "status": "reviewed_background_region_recorded",
            "assignment_source": source,
            "boundary": (
                "This XPS background region records a user-reviewed background model choice and provenance only; "
                "EA v0.2 does not automatically apply Shirley/Tougaard subtraction or prove chemical-state/composition claims from this record."
            ),
        },
        warnings,
    )


def _record_background_model(parameters: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    params = parameters.get("background_model", {})
    if not isinstance(params, dict) or not params.get("enabled", False):
        return None, []
    warnings: list[dict[str, Any]] = []
    method = str(params.get("method") or "reviewed_background_record")
    source = str(params.get("source") or "ea.xps.background_model:v0.2")
    record: dict[str, Any] = {
        "enabled": True,
        "method": method,
        "assignment_source": source,
        "confidence": "insufficient",
        "region_count": 0,
        "regions": [],
        "reference_ids": [],
        "boundary": (
            "XPS background model records preserve user-reviewed model/provenance choices only. EA v0.2 does not automatically perform "
            "Shirley/Tougaard background subtraction, spin-orbit constrained fitting, formal composition, or chemical-state proof from this record."
        ),
    }
    if method != "reviewed_background_record":
        warning = _warning("xps_background_model_method_unsupported", "XPS background model method is not supported by EA v0.2.", severity="medium", method=method)
        warnings.append(warning)
        record.update({"status": "skipped_unsupported_method", "warnings": warnings})
        return record, warnings

    raw_regions = params.get("regions", [])
    if not isinstance(raw_regions, list):
        raw_regions = []
        warnings.append(
            _warning(
                "xps_background_regions_ignored",
                "XPS background_model regions were ignored because they were not supplied as a list.",
                severity="medium",
            )
        )
    if not raw_regions and _has_record_payload(params.get("background_type") or params.get("model_type") or params.get("model")):
        raw_regions = [params]
    if not raw_regions:
        warning = _warning("xps_background_regions_missing", "background_model was enabled, but no reviewed background regions were supplied.", severity="medium")
        warnings.append(warning)
        record.update({"status": "enabled_without_reviewed_regions", "warnings": warnings})
        return record, warnings

    default_software = deepcopy(params.get("software") or {})
    default_applied = bool(params.get("applied_to_processed_data", False))
    regions: list[dict[str, Any]] = []
    for number, region in enumerate(raw_regions, start=1):
        if not isinstance(region, dict):
            warnings.append(
                _warning(
                    "xps_background_region_ignored",
                    "A reviewed XPS background region was ignored because it was not a mapping.",
                    severity="medium",
                    region_number=number,
                )
            )
            continue
        background_region, region_warnings = _reviewed_background_region(
            region,
            number=number,
            source=source,
            default_applied=default_applied,
            default_software=default_software,
        )
        regions.append(background_region)
        warnings.extend(region_warnings)

    reference_ids = sorted({reference_id for region in regions for reference_id in region.get("reference_ids", [])})
    record.update(
        {
            "status": "reviewed_background_model_recorded" if regions else "no_background_regions_recorded",
            "confidence": "low" if regions else "insufficient",
            "region_count": len(regions),
            "regions": regions,
            "reference_ids": reference_ids,
            "reviewer_notes": _coerce_string_list(params.get("reviewer_notes") or params.get("notes")),
            "caveats": _coerce_string_list(params.get("caveats")),
            "warnings": warnings,
        }
    )
    return record, warnings


def _column_name(value: Any, default: str) -> str:
    name = str(value or default).strip()
    return name or default


def _background_subtraction_defaults(method: str) -> dict[str, str]:
    if method == "reviewed_shirley_background_subtraction":
        return {
            "background_column": "xps_shirley_background",
            "corrected_intensity_column": "xps_shirley_subtracted_intensity",
            "region_id_column": "xps_background_subtraction_region_id",
        }
    if method == "reviewed_tougaard_u2_background_subtraction":
        return {
            "background_column": "xps_tougaard_u2_background",
            "corrected_intensity_column": "xps_tougaard_u2_subtracted_intensity",
            "region_id_column": "xps_background_subtraction_region_id",
        }
    return {
        "background_column": "xps_linear_background",
        "corrected_intensity_column": "xps_background_subtracted_intensity",
        "region_id_column": "xps_background_subtraction_region_id",
    }


def _background_subtraction_method_label(method: str) -> str:
    if method == "reviewed_shirley_background_subtraction":
        return "Shirley"
    if method == "reviewed_tougaard_u2_background_subtraction":
        return "Tougaard U2"
    return "linear"


def _background_subtraction_success_status(method: str) -> str:
    if method == "reviewed_shirley_background_subtraction":
        return "reviewed_shirley_background_subtracted"
    if method == "reviewed_tougaard_u2_background_subtraction":
        return "reviewed_tougaard_u2_background_subtracted"
    return "reviewed_linear_background_subtracted"


def _background_subtraction_region_status(method: str) -> str:
    if method == "reviewed_shirley_background_subtraction":
        return "shirley_background_subtracted"
    if method == "reviewed_tougaard_u2_background_subtraction":
        return "tougaard_u2_background_subtracted"
    return "linear_background_subtracted"


def _is_background_subtraction_success(record: dict[str, Any]) -> bool:
    return record.get("status") in {
        "reviewed_linear_background_subtracted",
        "reviewed_shirley_background_subtracted",
        "reviewed_tougaard_u2_background_subtracted",
    }


def _anchor_window(region: dict[str, Any], side: str) -> tuple[float, float] | None:
    value = region.get(f"{side}_anchor_window_eV") or region.get(f"{side}_endpoint_window_eV")
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        low = float(value[0])
        high = float(value[1])
    except (TypeError, ValueError):
        return None
    return min(low, high), max(low, high)


def _anchor_point(region: dict[str, Any], side: str) -> float | None:
    for key in (f"{side}_anchor_eV", f"{side}_endpoint_eV"):
        if key not in region or region.get(key) is None:
            continue
        try:
            return float(region.get(key))
        except (TypeError, ValueError):
            return None
    return None


def _background_anchor(
    processed: pd.DataFrame,
    *,
    input_column: str,
    region: dict[str, Any],
    side: str,
    region_id: str,
    warnings: list[dict[str, Any]],
) -> dict[str, Any] | None:
    x = processed["binding_energy_eV"].to_numpy(dtype=float)
    y = pd.to_numeric(processed[input_column], errors="coerce").to_numpy(dtype=float)
    window = _anchor_window(region, side)
    if window is not None:
        low, high = window
        mask = (x >= low) & (x <= high) & np.isfinite(y)
        if int(mask.sum()) == 0:
            warnings.append(
                _warning(
                    "xps_background_subtraction_anchor_empty",
                    "A reviewed XPS background-subtraction anchor window contained no usable points.",
                    severity="medium",
                    region_id=region_id,
                    side=side,
                    anchor_window_eV=[low, high],
                )
            )
            return None
        return {
            "mode": "window_mean",
            "window_eV": [low, high],
            "binding_energy_eV": float(np.nanmean(x[mask])),
            "intensity": float(np.nanmean(y[mask])),
            "point_count": int(mask.sum()),
        }

    point = _anchor_point(region, side)
    if point is not None:
        finite = np.isfinite(x) & np.isfinite(y)
        if not finite.any():
            warnings.append(
                _warning(
                    "xps_background_subtraction_anchor_missing_data",
                    "A reviewed XPS background-subtraction anchor point could not be evaluated because the input column has no finite values.",
                    severity="medium",
                    region_id=region_id,
                    side=side,
                )
            )
            return None
        finite_indices = np.flatnonzero(finite)
        nearest = finite_indices[int(np.nanargmin(np.abs(x[finite] - point)))]
        return {
            "mode": "nearest_point",
            "requested_binding_energy_eV": point,
            "binding_energy_eV": float(x[nearest]),
            "intensity": float(y[nearest]),
            "point_count": 1,
        }

    warnings.append(
        _warning(
            "xps_background_subtraction_anchor_missing",
            "A reviewed XPS background-subtraction region is missing a required left/right anchor point or anchor window.",
            severity="medium",
            region_id=region_id,
            side=side,
        )
    )
    return None


def _linear_background_from_anchors(x: np.ndarray, *, x_left: float, y_left: float, x_right: float, y_right: float) -> tuple[np.ndarray, float]:
    slope = (y_right - y_left) / (x_right - x_left)
    return y_left + slope * (x - x_left), float(slope)


def _trapezoid_cumulative(y: np.ndarray, x: np.ndarray) -> np.ndarray:
    if len(y) < 2:
        return np.zeros_like(y, dtype=float)
    increments = (y[:-1] + y[1:]) * 0.5 * np.diff(x)
    return np.concatenate([[0.0], np.cumsum(increments)])


def _shirley_background_from_anchors(
    x: np.ndarray,
    y: np.ndarray,
    *,
    x_left: float,
    y_left: float,
    x_right: float,
    y_right: float,
    max_iterations: int,
    tolerance: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    linear_background, slope = _linear_background_from_anchors(x, x_left=x_left, y_left=y_left, x_right=x_right, y_right=y_right)
    background = linear_background.copy()
    endpoint_low = float(linear_background[0])
    endpoint_high = float(linear_background[-1])
    final_delta = 0.0
    residual_area = 0.0
    converged = False
    iterations = 0

    for iteration in range(1, max_iterations + 1):
        residual = np.clip(y - background, a_min=0.0, a_max=None)
        residual_area = float(np.trapezoid(residual, x))
        if residual_area <= 1e-15:
            final_delta = 0.0
            iterations = iteration
            converged = True
            break
        normalized = _trapezoid_cumulative(residual, x) / residual_area
        next_background = endpoint_low + (endpoint_high - endpoint_low) * normalized
        final_delta = float(np.nanmax(np.abs(next_background - background)))
        background = next_background
        iterations = iteration
        if final_delta <= tolerance:
            converged = True
            break

    return background, {
        "algorithm": "iterative_shirley_background",
        "linear_endpoint_slope_intensity_per_eV": float(slope),
        "endpoint_low_intensity": endpoint_low,
        "endpoint_high_intensity": endpoint_high,
        "max_iterations": int(max_iterations),
        "iterations": int(iterations),
        "tolerance": float(tolerance),
        "final_delta": float(final_delta),
        "residual_area": float(residual_area),
        "converged": bool(converged),
    }


def _first_config_value(region: dict[str, Any], params: dict[str, Any], keys: tuple[str, ...], default: Any = None) -> Any:
    for container in (region, params):
        for key in keys:
            if key in container and container.get(key) is not None:
                return container.get(key)
    return default


def _positive_float(value: Any) -> float | None:
    try:
        coerced = float(value)
    except (TypeError, ValueError):
        return None
    return coerced if coerced > 0 else None


def _tougaard_region_parameters(
    region: dict[str, Any],
    params: dict[str, Any],
    *,
    default_c_eV2: float,
    default_direction: str,
    region_id: str,
    warnings: list[dict[str, Any]],
) -> tuple[float | None, float, str]:
    raw_b = _first_config_value(region, params, ("tougaard_B", "B", "b1", "B1"))
    b_value = _positive_float(raw_b)
    if b_value is None:
        warnings.append(
            _warning(
                "xps_background_subtraction_tougaard_B_missing",
                "A reviewed XPS Tougaard U2 background_subtraction region is missing a positive user-reviewed B parameter.",
                severity="medium",
                region_id=region_id,
            )
        )

    raw_c = _first_config_value(region, params, ("tougaard_C_eV2", "C_eV2", "C"), default_c_eV2)
    c_value, adjusted_c = _coerce_float(raw_c, default_c_eV2, minimum=1e-12)
    if adjusted_c:
        warnings.append(
            _warning(
                "xps_background_subtraction_tougaard_C_adjusted",
                "Invalid XPS Tougaard U2 C_eV2 parameter was adjusted before processing.",
                severity="medium",
                region_id=region_id,
                tougaard_C_eV2=c_value,
            )
        )

    direction = str(
        _first_config_value(
            region,
            params,
            ("integration_direction", "tougaard_integration_direction"),
            default_direction,
        )
    ).strip()
    allowed_directions = {"toward_higher_binding_energy", "toward_lower_binding_energy"}
    if direction not in allowed_directions:
        warnings.append(
            _warning(
                "xps_background_subtraction_tougaard_direction_adjusted",
                "Invalid XPS Tougaard U2 integration_direction was adjusted before processing.",
                severity="medium",
                region_id=region_id,
                supplied_integration_direction=direction,
            )
        )
        direction = default_direction
    return b_value, c_value, direction


def _tougaard_u2_background_from_anchors(
    x: np.ndarray,
    y: np.ndarray,
    *,
    x_left: float,
    y_left: float,
    x_right: float,
    y_right: float,
    tougaard_B: float,
    tougaard_C_eV2: float,
    integration_direction: str,
) -> tuple[np.ndarray, dict[str, Any]]:
    linear_background, slope = _linear_background_from_anchors(x, x_left=x_left, y_left=y_left, x_right=x_right, y_right=y_right)
    residual = np.clip(y - linear_background, a_min=0.0, a_max=None)
    integrals = np.zeros_like(x, dtype=float)
    for index, x_value in enumerate(x):
        if integration_direction == "toward_lower_binding_energy":
            segment_x = x[: index + 1]
            segment_residual = residual[: index + 1]
            delta = x_value - segment_x
        else:
            segment_x = x[index:]
            segment_residual = residual[index:]
            delta = segment_x - x_value
        if len(segment_x) < 2:
            continue
        kernel = delta / np.square(tougaard_C_eV2 + np.square(delta))
        integrals[index] = float(np.trapezoid(segment_residual * kernel, segment_x))

    background = linear_background + float(tougaard_B) * integrals
    return background, {
        "algorithm": "reviewed_tougaard_u2_kernel",
        "kernel": "delta_E/(C_eV2+delta_E^2)^2",
        "linear_endpoint_slope_intensity_per_eV": float(slope),
        "endpoint_low_intensity": float(linear_background[0]),
        "endpoint_high_intensity": float(linear_background[-1]),
        "tougaard_B": float(tougaard_B),
        "tougaard_C_eV2": float(tougaard_C_eV2),
        "integration_direction": integration_direction,
        "residual_area_after_linear_endpoint_baseline": float(np.trapezoid(residual, x)),
        "tougaard_integral_max": float(np.nanmax(integrals)) if integrals.size else 0.0,
    }


def _apply_background_subtraction(processed: pd.DataFrame, parameters: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    params = parameters.get("background_subtraction", {})
    if not isinstance(params, dict) or not params.get("enabled", False):
        return None, []

    warnings: list[dict[str, Any]] = []
    method = str(params.get("method") or "reviewed_linear_background_subtraction")
    supported_methods = {
        "reviewed_linear_background_subtraction",
        "reviewed_shirley_background_subtraction",
        "reviewed_tougaard_u2_background_subtraction",
    }
    method_label = _background_subtraction_method_label(method)
    defaults = _background_subtraction_defaults(method)
    base_defaults = _background_subtraction_defaults("reviewed_linear_background_subtraction")
    source = str(params.get("source") or "ea.xps.background_subtraction:v0.2")
    input_column = _column_name(params.get("input_intensity_column"), "processed_intensity")
    background_column_input = params.get("background_column")
    corrected_column_input = params.get("corrected_intensity_column")
    if method in {"reviewed_shirley_background_subtraction", "reviewed_tougaard_u2_background_subtraction"}:
        if background_column_input == base_defaults["background_column"]:
            background_column_input = None
        if corrected_column_input == base_defaults["corrected_intensity_column"]:
            corrected_column_input = None
    background_column = _column_name(background_column_input, defaults["background_column"])
    corrected_column = _column_name(corrected_column_input, defaults["corrected_intensity_column"])
    region_id_column = _column_name(params.get("region_id_column"), defaults["region_id_column"])
    min_points, adjusted_min_points = _coerce_int(params.get("min_points"), 5, minimum=2)
    max_iterations, adjusted_max_iterations = _coerce_int(params.get("max_iterations"), 100, minimum=2)
    tolerance, adjusted_tolerance = _coerce_float(params.get("tolerance"), 1e-6, minimum=1e-12)
    global_tougaard_b = _positive_float(_first_config_value({}, params, ("tougaard_B", "B", "b1", "B1")))
    tougaard_c_eV2, adjusted_tougaard_c = _coerce_float(params.get("tougaard_C_eV2", params.get("C_eV2", 1643.0)), 1643.0, minimum=1e-12)
    integration_direction = str(params.get("integration_direction") or "toward_higher_binding_energy").strip()
    adjusted_integration_direction = False
    if integration_direction not in {"toward_higher_binding_energy", "toward_lower_binding_energy"}:
        integration_direction = "toward_higher_binding_energy"
        adjusted_integration_direction = True
    record: dict[str, Any] = {
        "enabled": True,
        "method": method,
        "assignment_source": source,
        "input_intensity_column": input_column,
        "background_column": background_column,
        "corrected_intensity_column": corrected_column,
        "region_id_column": region_id_column,
        "min_points": min_points,
        "max_iterations": max_iterations if method == "reviewed_shirley_background_subtraction" else None,
        "tolerance": tolerance if method == "reviewed_shirley_background_subtraction" else None,
        "tougaard_B": global_tougaard_b if method == "reviewed_tougaard_u2_background_subtraction" else None,
        "tougaard_C_eV2": tougaard_c_eV2 if method == "reviewed_tougaard_u2_background_subtraction" else None,
        "integration_direction": integration_direction if method == "reviewed_tougaard_u2_background_subtraction" else None,
        "status": "not_applied",
        "confidence": "insufficient",
        "region_count": 0,
        "corrected_region_count": 0,
        "regions": [],
        "reference_ids": _coerce_string_list(params.get("reference_ids")),
        "reviewer_notes": _coerce_string_list(params.get("reviewer_notes") or params.get("notes")),
        "caveats": _coerce_string_list(params.get("caveats")),
        "boundary": (
            "XPS background_subtraction applies only user-reviewed numeric preprocessing inside explicit binding-energy regions. "
            "EA v0.2 may suggest source-backed endpoints/windows or Tougaard parameters through traceable records, but this record does not silently choose or apply them, "
            "fit Tougaard parameters, run QUASES/depth-profile modeling or peak fitting, assign chemical states, prove composition, or perform spin-orbit constrained fitting."
        ),
    }
    if method not in supported_methods:
        warnings.append(
            _warning(
                "xps_background_subtraction_method_unsupported",
                "XPS background_subtraction method is not supported by EA v0.2.",
                severity="medium",
                method=method,
                supported_methods=sorted(supported_methods),
            )
        )
        record.update({"status": "skipped_unsupported_method", "warnings": warnings})
        return record, warnings
    if adjusted_min_points:
        warnings.append(
            _warning(
                "xps_background_subtraction_min_points_adjusted",
                "Invalid XPS background_subtraction min_points was adjusted before processing.",
                severity="medium",
                min_points=min_points,
            )
        )
    if method == "reviewed_shirley_background_subtraction" and (adjusted_max_iterations or adjusted_tolerance):
        warnings.append(
            _warning(
                "xps_background_subtraction_shirley_parameter_adjusted",
                "Invalid XPS Shirley background_subtraction iteration parameters were adjusted before processing.",
                severity="medium",
                max_iterations=max_iterations,
                tolerance=tolerance,
            )
        )
    if method == "reviewed_tougaard_u2_background_subtraction" and (adjusted_tougaard_c or adjusted_integration_direction):
        warnings.append(
            _warning(
                "xps_background_subtraction_tougaard_parameter_adjusted",
                "Invalid XPS Tougaard U2 background_subtraction parameters were adjusted before processing.",
                severity="medium",
                tougaard_C_eV2=tougaard_c_eV2,
                integration_direction=integration_direction,
            )
        )
    if input_column not in processed.columns:
        warnings.append(
            _warning(
                "xps_background_subtraction_input_missing",
                "XPS background_subtraction input intensity column was not present in the processed table.",
                severity="medium",
                input_intensity_column=input_column,
            )
        )
        record.update({"status": "skipped_missing_input_column", "warnings": warnings})
        return record, warnings
    if len({input_column, background_column, corrected_column, region_id_column}) != 4:
        warnings.append(
            _warning(
                "xps_background_subtraction_column_collision",
                "XPS background_subtraction column names must be distinct and must not overwrite the input intensity column.",
                severity="medium",
                input_intensity_column=input_column,
                background_column=background_column,
                corrected_intensity_column=corrected_column,
                region_id_column=region_id_column,
            )
        )
        record.update({"status": "skipped_column_collision", "warnings": warnings})
        return record, warnings
    existing_output_columns = [column for column in [background_column, corrected_column, region_id_column] if column in processed.columns]
    if existing_output_columns:
        warnings.append(
            _warning(
                "xps_background_subtraction_output_column_exists",
                "XPS background_subtraction output columns must not overwrite existing processed table columns.",
                severity="medium",
                existing_output_columns=existing_output_columns,
            )
        )
        record.update({"status": "skipped_existing_output_column", "warnings": warnings})
        return record, warnings

    raw_regions = params.get("regions", [])
    if not isinstance(raw_regions, list):
        raw_regions = []
        warnings.append(
            _warning(
                "xps_background_subtraction_regions_ignored",
                "XPS background_subtraction regions were ignored because they were not supplied as a list.",
                severity="medium",
            )
        )
    if not raw_regions:
        warnings.append(
            _warning(
                "xps_background_subtraction_regions_missing",
                "background_subtraction was enabled, but no reviewed subtraction regions were supplied.",
                severity="medium",
            )
        )
        record.update({"status": "enabled_without_reviewed_regions", "warnings": warnings})
        return record, warnings

    processed[background_column] = np.nan
    processed[corrected_column] = np.nan
    processed[region_id_column] = pd.Series(pd.NA, index=processed.index, dtype="object")
    x = processed["binding_energy_eV"].to_numpy(dtype=float)
    y = pd.to_numeric(processed[input_column], errors="coerce").to_numpy(dtype=float)
    regions: list[dict[str, Any]] = []
    corrected_count = 0
    all_reference_ids = set(record["reference_ids"])

    for number, region in enumerate(raw_regions, start=1):
        if not isinstance(region, dict):
            warnings.append(
                _warning(
                    "xps_background_subtraction_region_ignored",
                    "A reviewed XPS background_subtraction region was ignored because it was not a mapping.",
                    severity="medium",
                    region_number=number,
                )
            )
            continue
        region_id = str(region.get("region_id") or region.get("id") or f"xps-background-subtraction-region-{number:03d}")
        low, high = _background_window(region)
        region_record: dict[str, Any] = {
            "region_id": region_id,
            "label": str(region.get("label") or region_id),
            "binding_energy_min_eV": low,
            "binding_energy_max_eV": high,
            "left_anchor": None,
            "right_anchor": None,
            "point_count": 0,
            "status": "invalid_region_window",
            "reference_ids": _coerce_string_list(region.get("reference_ids")),
            "reviewer_notes": _coerce_string_list(region.get("reviewer_notes") or region.get("notes")),
            "caveats": _coerce_string_list(region.get("caveats")),
            "confidence": str(region.get("confidence") or "low").strip().lower(),
            "assignment_source": source,
        }
        all_reference_ids.update(region_record["reference_ids"])
        tougaard_b: float | None = None
        region_tougaard_c = tougaard_c_eV2
        region_integration_direction = integration_direction
        if method == "reviewed_tougaard_u2_background_subtraction":
            tougaard_b, region_tougaard_c, region_integration_direction = _tougaard_region_parameters(
                region,
                params,
                default_c_eV2=tougaard_c_eV2,
                default_direction=integration_direction,
                region_id=region_id,
                warnings=warnings,
            )
            region_record.update(
                {
                    "tougaard_B": tougaard_b,
                    "tougaard_C_eV2": region_tougaard_c,
                    "integration_direction": region_integration_direction,
                }
            )
        if low is None or high is None:
            warnings.append(
                _warning(
                    "xps_background_subtraction_invalid_window",
                    "A reviewed XPS background_subtraction region has an invalid binding-energy window.",
                    severity="medium",
                    region_id=region_id,
                )
            )
            regions.append(region_record)
            continue

        mask = (x >= low) & (x <= high) & np.isfinite(y)
        point_count = int(mask.sum())
        region_record["point_count"] = point_count
        if point_count < min_points:
            region_record["status"] = "insufficient_region_points"
            warnings.append(
                _warning(
                    "xps_background_subtraction_insufficient_points",
                    f"A reviewed XPS background_subtraction region had too few points for {method_label} subtraction.",
                    severity="medium",
                    region_id=region_id,
                    point_count=point_count,
                    min_points=min_points,
                )
            )
            regions.append(region_record)
            continue

        if method == "reviewed_tougaard_u2_background_subtraction" and tougaard_b is None:
            region_record["status"] = "missing_reviewed_tougaard_B"
            regions.append(region_record)
            continue

        left_anchor = _background_anchor(processed, input_column=input_column, region=region, side="left", region_id=region_id, warnings=warnings)
        right_anchor = _background_anchor(processed, input_column=input_column, region=region, side="right", region_id=region_id, warnings=warnings)
        region_record["left_anchor"] = left_anchor
        region_record["right_anchor"] = right_anchor
        if left_anchor is None or right_anchor is None:
            region_record["status"] = "missing_reviewed_anchor"
            regions.append(region_record)
            continue

        x_left = float(left_anchor["binding_energy_eV"])
        x_right = float(right_anchor["binding_energy_eV"])
        y_left = float(left_anchor["intensity"])
        y_right = float(right_anchor["intensity"])
        if x_left == x_right:
            region_record["status"] = "invalid_anchor_geometry"
            warnings.append(
                _warning(
                    "xps_background_subtraction_anchor_geometry_invalid",
                    "A reviewed XPS background_subtraction region has identical left/right anchor positions.",
                    severity="medium",
                    region_id=region_id,
                    anchor_eV=x_left,
                )
            )
            regions.append(region_record)
            continue

        if processed.loc[mask, background_column].notna().any():
            warnings.append(
                _warning(
                    "xps_background_subtraction_region_overlap",
                    "A reviewed XPS background_subtraction region overlaps a previously corrected region; later region values were written for the overlap.",
                    severity="low",
                    region_id=region_id,
                )
            )
        if method == "reviewed_shirley_background_subtraction":
            background, subtraction_details = _shirley_background_from_anchors(
                x[mask],
                y[mask],
                x_left=x_left,
                y_left=y_left,
                x_right=x_right,
                y_right=y_right,
                max_iterations=max_iterations,
                tolerance=tolerance,
            )
            if not subtraction_details["converged"]:
                warnings.append(
                    _warning(
                        "xps_background_subtraction_shirley_not_converged",
                        "A reviewed XPS Shirley background_subtraction region did not converge within the reviewed iteration limit.",
                        severity="medium",
                        region_id=region_id,
                        iterations=subtraction_details["iterations"],
                        final_delta=subtraction_details["final_delta"],
                        tolerance=tolerance,
                    )
                )
        elif method == "reviewed_tougaard_u2_background_subtraction":
            background, subtraction_details = _tougaard_u2_background_from_anchors(
                x[mask],
                y[mask],
                x_left=x_left,
                y_left=y_left,
                x_right=x_right,
                y_right=y_right,
                tougaard_B=float(tougaard_b),
                tougaard_C_eV2=region_tougaard_c,
                integration_direction=region_integration_direction,
            )
        else:
            background, slope = _linear_background_from_anchors(x[mask], x_left=x_left, y_left=y_left, x_right=x_right, y_right=y_right)
            subtraction_details = {
                "algorithm": "linear_anchor_interpolation",
                "slope_intensity_per_eV": float(slope),
            }
        corrected = y[mask] - background
        processed.loc[mask, background_column] = background
        processed.loc[mask, corrected_column] = corrected
        processed.loc[mask, region_id_column] = region_id
        region_record.update(
            {
                "status": _background_subtraction_region_status(method),
                **subtraction_details,
                "background_min": float(np.nanmin(background)),
                "background_max": float(np.nanmax(background)),
                "corrected_min": float(np.nanmin(corrected)),
                "corrected_max": float(np.nanmax(corrected)),
                "output_columns": [background_column, corrected_column, region_id_column],
            }
        )
        corrected_count += 1
        regions.append(region_record)

    record.update(
        {
            "status": _background_subtraction_success_status(method) if corrected_count else "no_regions_corrected",
            "confidence": "low" if corrected_count else "insufficient",
            "region_count": len(regions),
            "corrected_region_count": corrected_count,
            "regions": regions,
            "reference_ids": sorted(all_reference_ids),
            "warnings": warnings,
        }
    )
    return record, warnings


def _apply_component_quantification(
    processed: pd.DataFrame, parameters: dict[str, Any]
) -> tuple[pd.DataFrame, dict[str, Any], list[dict[str, Any]]]:
    params = parameters.get("component_quantification", {})
    source = str(params.get("source") or "ea.xps.component_quantification:v0.2")
    summary: dict[str, Any] = {
        "enabled": bool(params.get("enabled", False)),
        "method": str(params.get("method") or "reviewed_window_integration"),
        "assignment_source": source,
        "status": "disabled",
        "component_count": 0,
        "quantified_component_count": 0,
        "rsf_complete": False,
        "boundary": "XPS component quantification is screening-only and requires user-reviewed windows, background/model choices, sensitivity factors, calibration, and references before durable chemical-state or composition conclusions.",
    }
    warnings: list[dict[str, Any]] = []
    if not params.get("enabled", False):
        return pd.DataFrame(columns=_component_columns()), summary, warnings

    components = params.get("components") or []
    if not isinstance(components, list) or not components:
        summary["status"] = "no_reviewed_components"
        warnings.append(
            _warning(
                "xps_component_quantification_no_components",
                "XPS component quantification was enabled but no reviewed component windows were supplied.",
                severity="medium",
            )
        )
        return pd.DataFrame(columns=_component_columns()), summary, warnings

    min_points, adjusted_min_points = _coerce_int(params.get("min_points"), 5, minimum=2)
    baseline_mode = str(params.get("integration_baseline") or "local_minimum")
    if baseline_mode not in {"local_minimum", "zero"}:
        baseline_mode = "local_minimum"
        warnings.append(
            _warning(
                "xps_component_baseline_mode_adjusted",
                "Invalid XPS component integration baseline mode was adjusted to local_minimum.",
                severity="medium",
            )
        )
    if adjusted_min_points:
        warnings.append(
            _warning(
                "xps_component_min_points_adjusted",
                "Invalid XPS component min_points was adjusted before component screening.",
                severity="medium",
                min_points=min_points,
            )
        )

    rows: list[dict[str, Any]] = []
    x = processed["binding_energy_eV"].to_numpy(dtype=float)
    y = processed["processed_intensity"].to_numpy(dtype=float)
    for index, component in enumerate(components, start=1):
        if not isinstance(component, dict):
            continue
        component_id = str(component.get("component_id") or component.get("id") or f"xps-component-{index:03d}")
        label = str(component.get("label") or component_id)
        element = str(component.get("element") or "")
        core_level = str(component.get("core_level") or component.get("orbital") or "")
        window = _component_window(component)
        row: dict[str, Any] = {
            "component_id": component_id,
            "label": label,
            "element": element,
            "core_level": core_level,
            "binding_energy_min_eV": np.nan,
            "binding_energy_max_eV": np.nan,
            "centroid_eV": np.nan,
            "max_binding_energy_eV": np.nan,
            "integrated_area": np.nan,
            "area_unit": "eV*a.u.",
            "relative_area_percent": np.nan,
            "sensitivity_factor": np.nan,
            "rsf_corrected_area": np.nan,
            "relative_atomic_percent_screening": np.nan,
            "model": str(component.get("model") or "reviewed_window"),
            "background": str(component.get("background") or baseline_mode),
            "confidence": "insufficient",
            "assignment_source": source,
            "status": "invalid_window",
            "notes": str(component.get("notes") or "reviewed XPS component window; screening only"),
        }
        if window is None:
            rows.append(row)
            warnings.append(
                _warning(
                    "xps_component_invalid_window",
                    "A reviewed XPS component window could not be parsed and was not quantified.",
                    severity="medium",
                    component_id=component_id,
                )
            )
            continue

        low, high = window
        row["binding_energy_min_eV"] = low
        row["binding_energy_max_eV"] = high
        mask = (x >= low) & (x <= high)
        if int(mask.sum()) < min_points:
            row["status"] = "insufficient_points"
            rows.append(row)
            warnings.append(
                _warning(
                    "xps_component_insufficient_points",
                    "A reviewed XPS component window had too few points for integration.",
                    severity="medium",
                    component_id=component_id,
                    point_count=int(mask.sum()),
                    min_points=min_points,
                )
            )
            continue

        window_x = x[mask]
        window_y = y[mask]
        local_y = window_y - float(np.nanmin(window_y)) if baseline_mode == "local_minimum" else window_y.copy()
        local_y = np.clip(local_y, a_min=0.0, a_max=None)
        area = float(np.trapezoid(local_y, window_x))
        if area <= 0:
            row["status"] = "nonpositive_area"
            rows.append(row)
            warnings.append(
                _warning(
                    "xps_component_nonpositive_area",
                    "A reviewed XPS component window produced nonpositive integrated area.",
                    severity="medium",
                    component_id=component_id,
                )
            )
            continue

        max_index = int(np.nanargmax(window_y))
        weight_sum = float(np.sum(local_y))
        centroid = float(np.sum(window_x * local_y) / weight_sum) if weight_sum > 0 else float(window_x[max_index])
        rsf = _component_sensitivity_factor(component)
        row.update(
            {
                "centroid_eV": centroid,
                "max_binding_energy_eV": float(window_x[max_index]),
                "integrated_area": area,
                "sensitivity_factor": rsf if rsf is not None else np.nan,
                "rsf_corrected_area": area / rsf if rsf is not None else np.nan,
                "confidence": "low",
                "status": "integrated",
            }
        )
        rows.append(row)

    table = pd.DataFrame(rows, columns=_component_columns())
    integrated_mask = table["status"].astype(str) == "integrated" if not table.empty else pd.Series(dtype=bool)
    if integrated_mask.any():
        area_total = float(pd.to_numeric(table.loc[integrated_mask, "integrated_area"], errors="coerce").sum())
        if area_total > 0:
            table.loc[integrated_mask, "relative_area_percent"] = (
                pd.to_numeric(table.loc[integrated_mask, "integrated_area"], errors="coerce") / area_total * 100.0
            )
        included = table.loc[integrated_mask].copy()
        rsf_complete = bool(pd.to_numeric(included["sensitivity_factor"], errors="coerce").notna().all())
        summary["rsf_complete"] = rsf_complete
        if rsf_complete:
            corrected_total = float(pd.to_numeric(included["rsf_corrected_area"], errors="coerce").sum())
            if corrected_total > 0:
                table.loc[integrated_mask, "relative_atomic_percent_screening"] = (
                    pd.to_numeric(table.loc[integrated_mask, "rsf_corrected_area"], errors="coerce") / corrected_total * 100.0
                )
                summary["status"] = "rsf_normalized_screening"
            else:
                summary["status"] = "rsf_corrected_area_nonpositive"
        else:
            summary["status"] = "area_screening_without_complete_rsf"
            warnings.append(
                _warning(
                    "xps_component_rsf_incomplete",
                    "XPS component areas were integrated, but at least one included component lacks a positive sensitivity factor; atomic percent screening was not calculated for all components.",
                    severity="medium",
                )
            )
    else:
        summary["status"] = "no_integrated_components"

    summary["component_count"] = int(len(table))
    summary["quantified_component_count"] = int(integrated_mask.sum()) if not table.empty else 0
    summary["integration_baseline"] = baseline_mode
    summary["min_points"] = min_points
    if summary["quantified_component_count"]:
        summary["components"] = [
            {
                "component_id": str(row["component_id"]),
                "label": str(row["label"]),
                "element": str(row["element"]),
                "core_level": str(row["core_level"]),
                "centroid_eV": float(row["centroid_eV"]) if pd.notna(row["centroid_eV"]) else None,
                "relative_area_percent": float(row["relative_area_percent"]) if pd.notna(row["relative_area_percent"]) else None,
                "relative_atomic_percent_screening": float(row["relative_atomic_percent_screening"])
                if pd.notna(row["relative_atomic_percent_screening"])
                else None,
                "confidence": str(row["confidence"]),
                "status": str(row["status"]),
                "assignment_source": str(row["assignment_source"]),
            }
            for _, row in table.loc[integrated_mask].iterrows()
        ]
    return table, summary, warnings


def _component_fit_columns() -> list[str]:
    return [
        "component_id",
        "region_id",
        "label",
        "element",
        "core_level",
        "peak_shape",
        "spin_orbit_group_id",
        "spin_orbit_role",
        "spin_orbit_constraint_id",
        "spin_orbit_anchor_component_id",
        "spin_orbit_dependent_component_id",
        "spin_orbit_center_delta_eV",
        "spin_orbit_area_ratio",
        "spin_orbit_fwhm_ratio",
        "spin_orbit_constraint_status",
        "spin_orbit_parameter_origin",
        "spin_orbit_source_summary",
        "spin_orbit_applicability_notes",
        "initial_center_eV",
        "fitted_center_eV",
        "initial_amplitude",
        "fitted_amplitude",
        "initial_fwhm_eV",
        "fitted_fwhm_eV",
        "initial_mixing",
        "fitted_mixing",
        "fitted_area",
        "relative_fit_area_percent",
        "fit_rmse",
        "fit_r_squared",
        "confidence",
        "assignment_source",
        "status",
        "notes",
    ]


def _component_fit_optional_float(value: Any, field: str) -> tuple[float | None, dict[str, Any] | None]:
    if value is None or value == "":
        return None, None
    try:
        return float(value), None
    except (TypeError, ValueError):
        return (
            None,
            _warning(
                "xps_component_fit_parameter_ignored",
                "XPS component-fit optional numeric parameter could not be parsed and was ignored.",
                severity="medium",
                field=field,
            ),
        )


def _component_fit_required_float(component: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        if key in component and component.get(key) is not None:
            try:
                return float(component.get(key))
            except (TypeError, ValueError):
                return None
    return None


def _component_fit_bounds(component: dict[str, Any], keys: tuple[str, ...]) -> tuple[float, float] | None:
    value = None
    for key in keys:
        if key in component and component.get(key) is not None:
            value = component.get(key)
            break
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        low = float(value[0])
        high = float(value[1])
    except (TypeError, ValueError):
        return None
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        return None
    return low, high


def _component_fit_profile(x: np.ndarray, amplitude: float, center: float, fwhm: float, mixing: float, shape: str) -> np.ndarray:
    width = max(float(fwhm), 1e-12)
    gaussian = np.exp(-4.0 * np.log(2.0) * np.square((x - float(center)) / width))
    lorentzian = 1.0 / (1.0 + 4.0 * np.square((x - float(center)) / width))
    if shape == "gaussian":
        profile = gaussian
    elif shape == "lorentzian":
        profile = lorentzian
    else:
        mix = min(max(float(mixing), 0.0), 1.0)
        profile = (1.0 - mix) * gaussian + mix * lorentzian
    return float(amplitude) * profile


def _component_fit_area(amplitude: float, fwhm: float, mixing: float, shape: str) -> float:
    width = max(float(fwhm), 1e-12)
    gaussian_sigma = width / (2.0 * np.sqrt(2.0 * np.log(2.0)))
    gaussian_area = float(amplitude) * gaussian_sigma * np.sqrt(2.0 * np.pi)
    lorentzian_area = float(amplitude) * np.pi * width * 0.5
    if shape == "gaussian":
        return float(gaussian_area)
    if shape == "lorentzian":
        return float(lorentzian_area)
    mix = min(max(float(mixing), 0.0), 1.0)
    return float((1.0 - mix) * gaussian_area + mix * lorentzian_area)


def _component_fit_quality(observed: np.ndarray, fitted: np.ndarray, parameter_count: int) -> dict[str, float | None]:
    residual = observed - fitted
    rss = float(np.sum(residual**2))
    sst = float(np.sum((observed - float(np.mean(observed))) ** 2))
    dof = max(int(observed.size - parameter_count), 1)
    return {
        "point_count": int(observed.size),
        "parameter_count": int(parameter_count),
        "residual_sum_squares": rss,
        "rmse": float(np.sqrt(rss / max(observed.size, 1))),
        "mae": float(np.mean(np.abs(residual))) if observed.size else None,
        "reduced_chi_square": float(rss / dof),
        "r_squared": float(1.0 - rss / sst) if sst > 0 else None,
        "max_abs_residual": float(np.max(np.abs(residual))) if observed.size else None,
    }


def _component_fit_thresholds(params: dict[str, Any]) -> tuple[dict[str, float | None], list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    thresholds = params.get("fit_quality_thresholds", {})
    if not isinstance(thresholds, dict):
        return (
            {"max_rmse": None, "min_r_squared": None},
            [
                _warning(
                    "xps_component_fit_thresholds_ignored",
                    "XPS component-fit quality thresholds were ignored because they were not a mapping.",
                    severity="medium",
                )
            ],
        )
    parsed: dict[str, float | None] = {}
    for name in ["max_rmse", "min_r_squared"]:
        parsed[name], warning = _component_fit_optional_float(thresholds.get(name), f"fit_quality_thresholds.{name}")
        if warning:
            warnings.append(warning)
    return parsed, warnings


def _component_fit_quality_checks(metrics: dict[str, float | None], thresholds: dict[str, float | None]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    checks: dict[str, Any] = {}
    warnings: list[dict[str, Any]] = []
    max_rmse = thresholds.get("max_rmse")
    if max_rmse is not None:
        value = metrics.get("rmse")
        passed = value is not None and float(value) <= float(max_rmse)
        checks["max_rmse"] = {"threshold": max_rmse, "value": value, "passed": bool(passed)}
        if not passed:
            warnings.append(
                _warning(
                    "xps_component_fit_quality_threshold_failed",
                    "XPS component-fit RMSE exceeded the reviewed threshold.",
                    severity="medium",
                    metric="rmse",
                    value=value,
                    threshold=max_rmse,
                )
            )
    min_r2 = thresholds.get("min_r_squared")
    if min_r2 is not None:
        value = metrics.get("r_squared")
        passed = value is not None and float(value) >= float(min_r2)
        checks["min_r_squared"] = {"threshold": min_r2, "value": value, "passed": bool(passed)}
        if not passed:
            warnings.append(
                _warning(
                    "xps_component_fit_quality_threshold_failed",
                    "XPS component-fit R-squared was below the reviewed threshold.",
                    severity="medium",
                    metric="r_squared",
                    value=value,
                    threshold=min_r2,
                )
            )
    return checks, warnings


def _component_fit_component_spec(
    component: dict[str, Any],
    *,
    region_id: str,
    number: int,
    source: str,
    warnings: list[dict[str, Any]],
) -> dict[str, Any] | None:
    component_id = str(component.get("component_id") or component.get("id") or f"xps-fit-component-{number:03d}")
    shape = str(component.get("peak_shape") or component.get("shape") or "pseudo_voigt").strip().lower().replace("-", "_")
    if shape not in {"gaussian", "lorentzian", "pseudo_voigt"}:
        warnings.append(
            _warning(
                "xps_component_fit_shape_unsupported",
                "A reviewed XPS component-fit peak shape was not supported.",
                severity="medium",
                region_id=region_id,
                component_id=component_id,
                peak_shape=shape,
            )
        )
        return None

    center = _component_fit_required_float(component, ("initial_center_eV", "center_eV", "initial_center"))
    amplitude = _component_fit_required_float(component, ("initial_amplitude", "amplitude"))
    fwhm = _component_fit_required_float(component, ("initial_fwhm_eV", "fwhm_eV", "initial_width_eV"))
    center_bounds = _component_fit_bounds(component, ("center_bounds_eV", "center_bounds"))
    amplitude_bounds = _component_fit_bounds(component, ("amplitude_bounds",))
    fwhm_bounds = _component_fit_bounds(component, ("fwhm_bounds_eV", "fwhm_bounds", "width_bounds_eV"))
    mixing = 0.0
    mixing_bounds = None
    if shape == "pseudo_voigt":
        mixing = _component_fit_required_float(component, ("initial_mixing", "mixing"))
        mixing_bounds = _component_fit_bounds(component, ("mixing_bounds",))

    missing = []
    if center is None:
        missing.append("initial_center_eV")
    if amplitude is None:
        missing.append("initial_amplitude")
    if fwhm is None:
        missing.append("initial_fwhm_eV")
    if center_bounds is None:
        missing.append("center_bounds_eV")
    if amplitude_bounds is None:
        missing.append("amplitude_bounds")
    if fwhm_bounds is None:
        missing.append("fwhm_bounds_eV")
    if shape == "pseudo_voigt" and mixing is None:
        missing.append("initial_mixing")
    if shape == "pseudo_voigt" and mixing_bounds is None:
        missing.append("mixing_bounds")
    if missing:
        warnings.append(
            _warning(
                "xps_component_fit_reviewed_parameters_missing",
                "XPS component-fit was skipped for a component because reviewed initial values or bounds were missing.",
                severity="medium",
                region_id=region_id,
                component_id=component_id,
                missing_fields=missing,
            )
        )
        return None
    if amplitude <= 0 or fwhm <= 0 or (shape == "pseudo_voigt" and not 0.0 <= float(mixing) <= 1.0):
        warnings.append(
            _warning(
                "xps_component_fit_initial_value_invalid",
                "XPS component-fit was skipped for a component because reviewed initial values were outside physical screening bounds.",
                severity="medium",
                region_id=region_id,
                component_id=component_id,
            )
        )
        return None

    specs = [
        ("center_eV", center, center_bounds),
        ("amplitude", amplitude, amplitude_bounds),
        ("fwhm_eV", fwhm, fwhm_bounds),
    ]
    if shape == "pseudo_voigt":
        specs.append(("mixing", float(mixing), mixing_bounds))
    for name, initial, bounds in specs:
        low, high = bounds
        if initial < low or initial > high:
            warnings.append(
                _warning(
                    "xps_component_fit_bounds_invalid",
                    "XPS component-fit was skipped because a reviewed initial value was outside reviewed bounds.",
                    severity="medium",
                    region_id=region_id,
                    component_id=component_id,
                    parameter=name,
                    initial_value=initial,
                    lower_bound=low,
                    upper_bound=high,
                )
            )
            return None

    return {
        "component_id": component_id,
        "label": str(component.get("label") or component_id),
        "region_id": region_id,
        "element": str(component.get("element") or ""),
        "core_level": str(component.get("core_level") or component.get("orbital") or ""),
        "peak_shape": shape,
        "spin_orbit_group_id": str(component.get("spin_orbit_group_id") or "") or None,
        "spin_orbit_role": str(component.get("spin_orbit_role") or "") or None,
        "initial_center_eV": float(center),
        "initial_amplitude": float(amplitude),
        "initial_fwhm_eV": float(fwhm),
        "initial_mixing": float(mixing) if shape == "pseudo_voigt" else None,
        "bounds": {
            "center_eV": list(center_bounds),
            "amplitude": list(amplitude_bounds),
            "fwhm_eV": list(fwhm_bounds),
            "mixing": list(mixing_bounds) if mixing_bounds is not None else None,
        },
        "reference_ids": _coerce_string_list(component.get("reference_ids")),
        "reviewer_notes": _coerce_string_list(component.get("reviewer_notes") or component.get("notes")),
        "caveats": _coerce_string_list(component.get("caveats")),
        "confidence": str(component.get("confidence") or "low").strip().lower(),
        "assignment_source": str(component.get("source") or component.get("assignment_source") or source),
        "notes": str(component.get("notes") or "reviewed XPS component fit; screening only"),
    }


def _component_fit_constraint_number(constraint: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        if key in constraint and constraint.get(key) is not None:
            try:
                value = float(constraint.get(key))
            except (TypeError, ValueError):
                return None
            return value if np.isfinite(value) else None
    return None


def _component_fit_intersect_bounds(current: tuple[float, float], candidate: tuple[float, float]) -> tuple[float, float] | None:
    low = max(float(current[0]), float(candidate[0]))
    high = min(float(current[1]), float(candidate[1]))
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        return None
    return low, high


def _component_fit_spin_orbit_constraints(
    specs: list[dict[str, Any]],
    raw_constraints: list[Any],
    *,
    region_id: str,
    warnings: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[int, dict[str, tuple[float, float]]], set[int], bool]:
    effective_bounds: dict[int, dict[str, tuple[float, float]]] = {
        index: {
            "center_eV": tuple(spec["bounds"]["center_eV"]),
            "amplitude": tuple(spec["bounds"]["amplitude"]),
            "fwhm_eV": tuple(spec["bounds"]["fwhm_eV"]),
            "mixing": tuple(spec["bounds"]["mixing"]) if spec["bounds"].get("mixing") is not None else (0.0, 1.0),
        }
        for index, spec in enumerate(specs)
    }
    if not raw_constraints:
        return [], effective_bounds, set(), False

    spec_by_id = {str(spec["component_id"]): index for index, spec in enumerate(specs)}
    constraints: list[dict[str, Any]] = []
    anchor_indices: set[int] = set()
    dependent_indices: set[int] = set()
    fatal = False

    for number, constraint in enumerate(raw_constraints, start=1):
        if not isinstance(constraint, dict):
            warnings.append(
                _warning(
                    "xps_component_fit_spin_orbit_constraint_ignored",
                    "A reviewed XPS spin-orbit constraint was ignored because it was not a mapping.",
                    severity="medium",
                    region_id=region_id,
                    constraint_number=number,
                )
            )
            fatal = True
            continue
        constraint_id = str(constraint.get("constraint_id") or constraint.get("group_id") or f"xps-spin-orbit-constraint-{number:03d}")
        group_id = str(constraint.get("group_id") or constraint_id)
        anchor_id = str(constraint.get("anchor_component_id") or constraint.get("parent_component_id") or "")
        dependent_id = str(constraint.get("dependent_component_id") or constraint.get("child_component_id") or "")
        center_delta = _component_fit_constraint_number(constraint, ("center_delta_eV", "dependent_center_delta_eV", "center_offset_eV"))
        area_ratio = _component_fit_constraint_number(constraint, ("area_ratio", "dependent_area_ratio"))
        fwhm_ratio = _component_fit_constraint_number(constraint, ("fwhm_ratio", "dependent_fwhm_ratio"))
        reference_ids = _coerce_string_list(constraint.get("reference_ids"))
        parameter_origin = str(
            constraint.get("parameter_origin")
            or constraint.get("constraint_origin")
            or constraint.get("source_type")
            or "reported_by_user"
        ).strip().lower().replace(" ", "_")
        allowed_origins = {"reported_by_user", "source_suggested", "user_confirmed_source_suggested"}
        if parameter_origin not in allowed_origins:
            warnings.append(
                _warning(
                    "xps_component_fit_spin_orbit_parameter_origin_normalized",
                    "XPS spin-orbit constraint parameter_origin was not recognized and was recorded as reported_by_user.",
                    severity="low",
                    region_id=region_id,
                    constraint_id=constraint_id,
                    supplied_parameter_origin=parameter_origin,
                )
            )
            parameter_origin = "reported_by_user"
        if parameter_origin in {"source_suggested", "user_confirmed_source_suggested"} and not reference_ids:
            warnings.append(
                _warning(
                    "xps_component_fit_spin_orbit_source_reference_missing",
                    "XPS source-backed spin-orbit constraints require reference_ids before constrained fitting can be applied.",
                    severity="medium",
                    region_id=region_id,
                    constraint_id=constraint_id,
                    parameter_origin=parameter_origin,
                )
            )
            fatal = True
            continue
        missing = []
        if not anchor_id:
            missing.append("anchor_component_id")
        if not dependent_id:
            missing.append("dependent_component_id")
        if center_delta is None:
            missing.append("center_delta_eV")
        if area_ratio is None:
            missing.append("area_ratio")
        if fwhm_ratio is None:
            missing.append("fwhm_ratio")
        if missing:
            warnings.append(
                _warning(
                    "xps_component_fit_spin_orbit_constraint_missing",
                    "XPS spin-orbit constrained component-fit was skipped because reviewed constraint fields were missing.",
                    severity="medium",
                    region_id=region_id,
                    constraint_id=constraint_id,
                    missing_fields=missing,
                )
            )
            fatal = True
            continue
        if area_ratio <= 0 or fwhm_ratio <= 0:
            warnings.append(
                _warning(
                    "xps_component_fit_spin_orbit_constraint_invalid",
                    "XPS spin-orbit constrained component-fit was skipped because area_ratio or fwhm_ratio was not positive.",
                    severity="medium",
                    region_id=region_id,
                    constraint_id=constraint_id,
                    area_ratio=area_ratio,
                    fwhm_ratio=fwhm_ratio,
                )
            )
            fatal = True
            continue
        if anchor_id not in spec_by_id or dependent_id not in spec_by_id or anchor_id == dependent_id:
            warnings.append(
                _warning(
                    "xps_component_fit_spin_orbit_component_missing",
                    "XPS spin-orbit constrained component-fit was skipped because reviewed anchor/dependent components were not valid.",
                    severity="medium",
                    region_id=region_id,
                    constraint_id=constraint_id,
                    anchor_component_id=anchor_id,
                    dependent_component_id=dependent_id,
                )
            )
            fatal = True
            continue
        anchor_index = spec_by_id[anchor_id]
        dependent_index = spec_by_id[dependent_id]
        anchor = specs[anchor_index]
        dependent = specs[dependent_index]
        if dependent_index in dependent_indices:
            warnings.append(
                _warning(
                    "xps_component_fit_spin_orbit_duplicate_dependent",
                    "XPS spin-orbit constrained component-fit was skipped because one dependent component had multiple constraints.",
                    severity="medium",
                    region_id=region_id,
                    constraint_id=constraint_id,
                    dependent_component_id=dependent_id,
                )
            )
            fatal = True
            continue
        if anchor_index in dependent_indices or dependent_index in anchor_indices:
            warnings.append(
                _warning(
                    "xps_component_fit_spin_orbit_chained_constraint",
                    "XPS spin-orbit constrained component-fit was skipped because chained or cyclic constraints are not supported in EA v0.2.",
                    severity="medium",
                    region_id=region_id,
                    constraint_id=constraint_id,
                    anchor_component_id=anchor_id,
                    dependent_component_id=dependent_id,
                )
            )
            fatal = True
            continue
        if anchor["peak_shape"] != dependent["peak_shape"]:
            warnings.append(
                _warning(
                    "xps_component_fit_spin_orbit_shape_mismatch",
                    "XPS spin-orbit constrained component-fit was skipped because constrained components used different peak shapes.",
                    severity="medium",
                    region_id=region_id,
                    constraint_id=constraint_id,
                    anchor_peak_shape=anchor["peak_shape"],
                    dependent_peak_shape=dependent["peak_shape"],
                )
            )
            fatal = True
            continue

        amplitude_factor = float(area_ratio) / float(fwhm_ratio)
        bound_candidates = {
            "center_eV": (float(dependent["bounds"]["center_eV"][0]) - float(center_delta), float(dependent["bounds"]["center_eV"][1]) - float(center_delta)),
            "fwhm_eV": (float(dependent["bounds"]["fwhm_eV"][0]) / float(fwhm_ratio), float(dependent["bounds"]["fwhm_eV"][1]) / float(fwhm_ratio)),
            "amplitude": (float(dependent["bounds"]["amplitude"][0]) / amplitude_factor, float(dependent["bounds"]["amplitude"][1]) / amplitude_factor),
        }
        if anchor["peak_shape"] == "pseudo_voigt" and dependent["bounds"].get("mixing") is not None:
            bound_candidates["mixing"] = tuple(dependent["bounds"]["mixing"])
        adjusted_bounds = dict(effective_bounds[anchor_index])
        for name, candidate_bounds in bound_candidates.items():
            intersected = _component_fit_intersect_bounds(adjusted_bounds[name], candidate_bounds)
            if intersected is None:
                warnings.append(
                    _warning(
                        "xps_component_fit_spin_orbit_bounds_conflict",
                        "XPS spin-orbit constrained component-fit was skipped because reviewed spin-orbit constraints conflicted with component bounds.",
                        severity="medium",
                        region_id=region_id,
                        constraint_id=constraint_id,
                        parameter=name,
                    )
                )
                fatal = True
                break
            adjusted_bounds[name] = intersected
        if fatal:
            continue
        effective_bounds[anchor_index] = adjusted_bounds
        anchor_indices.add(anchor_index)
        dependent_indices.add(dependent_index)
        constraints.append(
            {
                "constraint_id": constraint_id,
                "group_id": group_id,
                "anchor_component_id": anchor_id,
                "dependent_component_id": dependent_id,
                "anchor_index": anchor_index,
                "dependent_index": dependent_index,
                "center_delta_eV": float(center_delta),
                "area_ratio": float(area_ratio),
                "fwhm_ratio": float(fwhm_ratio),
                "amplitude_factor": amplitude_factor,
                "parameter_origin": parameter_origin,
                "source_summary": str(constraint.get("source_summary") or constraint.get("reference_summary") or "").strip(),
                "applicability_notes": _coerce_string_list(constraint.get("applicability_notes")),
                "reference_ids": reference_ids,
                "reviewer_notes": _coerce_string_list(constraint.get("reviewer_notes") or constraint.get("notes")),
                "caveats": _coerce_string_list(constraint.get("caveats")),
                "confidence": str(constraint.get("confidence") or "low").strip().lower(),
                "status": "applied",
            }
        )

    for spec_index, spec in enumerate(specs):
        if spec_index in dependent_indices:
            continue
        for name, initial_key in [
            ("center_eV", "initial_center_eV"),
            ("amplitude", "initial_amplitude"),
            ("fwhm_eV", "initial_fwhm_eV"),
        ]:
            low, high = effective_bounds[spec_index][name]
            initial = float(spec[initial_key])
            if initial < low or initial > high:
                warnings.append(
                    _warning(
                        "xps_component_fit_spin_orbit_initial_outside_effective_bounds",
                        "XPS spin-orbit constrained component-fit was skipped because a reviewed anchor initial value was outside effective constrained bounds.",
                        severity="medium",
                        region_id=region_id,
                        component_id=spec["component_id"],
                        parameter=name,
                        initial_value=initial,
                        lower_bound=low,
                        upper_bound=high,
                    )
                )
                fatal = True
        if spec["peak_shape"] == "pseudo_voigt":
            low, high = effective_bounds[spec_index]["mixing"]
            initial = float(spec["initial_mixing"])
            if initial < low or initial > high:
                warnings.append(
                    _warning(
                        "xps_component_fit_spin_orbit_initial_outside_effective_bounds",
                        "XPS spin-orbit constrained component-fit was skipped because a reviewed anchor initial mixing value was outside effective constrained bounds.",
                        severity="medium",
                        region_id=region_id,
                        component_id=spec["component_id"],
                        parameter="mixing",
                        initial_value=initial,
                        lower_bound=low,
                        upper_bound=high,
                    )
                )
                fatal = True
    return constraints, effective_bounds, dependent_indices, fatal


def _apply_component_fit(processed: pd.DataFrame, parameters: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any] | None, list[dict[str, Any]]]:
    params = parameters.get("component_fit", {})
    if not isinstance(params, dict) or not params.get("enabled", False):
        return pd.DataFrame(columns=_component_fit_columns()), None, []

    warnings: list[dict[str, Any]] = []
    method = str(params.get("method") or "reviewed_component_fit_screening")
    source = str(params.get("source") or "ea.xps.component_fit:v0.2")
    if method != "reviewed_component_fit_screening":
        warnings.append(
            _warning(
                "xps_component_fit_method_unsupported",
                "Only reviewed_component_fit_screening is supported for XPS component_fit in EA v0.2.",
                severity="medium",
                requested_method=method,
            )
        )
        method = "reviewed_component_fit_screening"

    input_column = _column_name(params.get("input_intensity_column"), "processed_intensity")
    fit_column = _column_name(params.get("fit_intensity_column"), "xps_component_fit_intensity")
    residual_column = _column_name(params.get("residual_column"), "xps_component_fit_residual")
    region_id_column = _column_name(params.get("region_id_column"), "xps_component_fit_region_id")
    min_points, min_adjusted = _coerce_int(params.get("min_points"), 8, minimum=4)
    max_nfev, max_adjusted = _coerce_int(params.get("max_nfev"), 5000, minimum=100)
    thresholds, threshold_warnings = _component_fit_thresholds(params)
    warnings.extend(threshold_warnings)
    if min_adjusted:
        warnings.append(
            _warning(
                "xps_component_fit_min_points_adjusted",
                "Invalid XPS component_fit min_points was adjusted before processing.",
                severity="medium",
                min_points=min_points,
            )
        )
    if max_adjusted:
        warnings.append(
            _warning(
                "xps_component_fit_max_nfev_adjusted",
                "Invalid XPS component_fit max_nfev was adjusted before processing.",
                severity="medium",
                max_nfev=max_nfev,
            )
        )

    record: dict[str, Any] = {
        "enabled": True,
        "method": method,
        "assignment_source": source,
        "input_intensity_column": input_column,
        "fit_intensity_column": fit_column,
        "residual_column": residual_column,
        "region_id_column": region_id_column,
        "min_points": min_points,
        "max_nfev": max_nfev,
        "fit_quality_thresholds": thresholds,
        "status": "not_applied",
        "confidence": "insufficient",
        "region_count": 0,
        "fitted_region_count": 0,
        "component_count": 0,
        "fitted_component_count": 0,
        "spin_orbit_constraint_count": 0,
        "constrained_component_count": 0,
        "regions": [],
        "reference_ids": _coerce_string_list(params.get("reference_ids")),
        "reviewer_notes": _coerce_string_list(params.get("reviewer_notes") or params.get("notes")),
        "caveats": _coerce_string_list(params.get("caveats")),
        "boundary": (
            "XPS component_fit is reviewed screening-level numerical modeling only. EA v0.2 may use reviewed user-provided or source-backed "
            "component/background/bounds/peak-shape candidates, but this record does not silently choose them, use unsourced spin-orbit constants, "
            "or prove chemical states or definitive composition."
        ),
    }

    if input_column not in processed.columns:
        warnings.append(
            _warning(
                "xps_component_fit_input_missing",
                "XPS component_fit input intensity column was not present in the processed table.",
                severity="medium",
                input_intensity_column=input_column,
            )
        )
        record.update({"status": "skipped_missing_input_column", "warnings": warnings})
        return pd.DataFrame(columns=_component_fit_columns()), record, warnings
    if len({input_column, fit_column, residual_column, region_id_column}) != 4:
        warnings.append(
            _warning(
                "xps_component_fit_column_collision",
                "XPS component_fit column names must be distinct and must not overwrite the input intensity column.",
                severity="medium",
                input_intensity_column=input_column,
                fit_intensity_column=fit_column,
                residual_column=residual_column,
                region_id_column=region_id_column,
            )
        )
        record.update({"status": "skipped_column_collision", "warnings": warnings})
        return pd.DataFrame(columns=_component_fit_columns()), record, warnings
    existing_output_columns = [column for column in [fit_column, residual_column, region_id_column] if column in processed.columns]
    if existing_output_columns:
        warnings.append(
            _warning(
                "xps_component_fit_output_column_exists",
                "XPS component_fit output columns must not overwrite existing processed table columns.",
                severity="medium",
                existing_output_columns=existing_output_columns,
            )
        )
        record.update({"status": "skipped_existing_output_column", "warnings": warnings})
        return pd.DataFrame(columns=_component_fit_columns()), record, warnings

    raw_regions = params.get("regions", [])
    if not isinstance(raw_regions, list):
        raw_regions = []
        warnings.append(
            _warning(
                "xps_component_fit_regions_ignored",
                "XPS component_fit regions were ignored because they were not supplied as a list.",
                severity="medium",
            )
        )
    if not raw_regions:
        warnings.append(
            _warning(
                "xps_component_fit_regions_missing",
                "component_fit was enabled, but no reviewed fit regions were supplied.",
                severity="medium",
            )
        )
        record.update({"status": "enabled_without_reviewed_regions", "warnings": warnings})
        return pd.DataFrame(columns=_component_fit_columns()), record, warnings

    processed[fit_column] = np.nan
    processed[residual_column] = np.nan
    processed[region_id_column] = pd.Series(pd.NA, index=processed.index, dtype="object")
    x = processed["binding_energy_eV"].to_numpy(dtype=float)
    y = pd.to_numeric(processed[input_column], errors="coerce").to_numpy(dtype=float)
    regions: list[dict[str, Any]] = []
    component_rows: list[dict[str, Any]] = []
    fitted_regions = 0
    all_reference_ids = set(record["reference_ids"])

    for number, region in enumerate(raw_regions, start=1):
        if not isinstance(region, dict):
            warnings.append(
                _warning(
                    "xps_component_fit_region_ignored",
                    "A reviewed XPS component_fit region was ignored because it was not a mapping.",
                    severity="medium",
                    region_number=number,
                )
            )
            continue
        region_id = str(region.get("region_id") or region.get("id") or f"xps-component-fit-region-{number:03d}")
        low, high = _background_window(region)
        region_references = _coerce_string_list(region.get("reference_ids"))
        all_reference_ids.update(region_references)
        region_record: dict[str, Any] = {
            "region_id": region_id,
            "label": str(region.get("label") or region_id),
            "binding_energy_min_eV": low,
            "binding_energy_max_eV": high,
            "input_intensity_column": str(region.get("input_intensity_column") or input_column),
            "background_source": str(region.get("background_source") or params.get("background_source") or "input_column_already_reviewed"),
            "background_column": region.get("background_column") or params.get("background_column"),
            "point_count": 0,
            "status": "invalid_region_window",
            "component_count": 0,
            "fitted_component_count": 0,
            "reference_ids": region_references,
            "reviewer_notes": _coerce_string_list(region.get("reviewer_notes") or region.get("notes")),
            "caveats": _coerce_string_list(region.get("caveats")),
            "confidence": str(region.get("confidence") or "low").strip().lower(),
            "assignment_source": source,
        }
        if low is None or high is None:
            warnings.append(
                _warning(
                    "xps_component_fit_invalid_window",
                    "A reviewed XPS component_fit region has an invalid binding-energy window.",
                    severity="medium",
                    region_id=region_id,
                )
            )
            regions.append(region_record)
            continue

        region_input_column = str(region_record["input_intensity_column"])
        if region_input_column != input_column:
            if region_input_column not in processed.columns:
                warnings.append(
                    _warning(
                        "xps_component_fit_region_input_missing",
                        "A reviewed XPS component_fit region input column was not present in the processed table.",
                        severity="medium",
                        region_id=region_id,
                        input_intensity_column=region_input_column,
                    )
                )
                regions.append(region_record)
                continue
            region_y_all = pd.to_numeric(processed[region_input_column], errors="coerce").to_numpy(dtype=float)
        else:
            region_y_all = y

        background_column = region_record.get("background_column")
        if background_column:
            background_column = str(background_column)
            if background_column not in processed.columns:
                warnings.append(
                    _warning(
                        "xps_component_fit_background_column_missing",
                        "A reviewed XPS component_fit background column was not present in the processed table.",
                        severity="medium",
                        region_id=region_id,
                        background_column=background_column,
                    )
                )
                regions.append(region_record)
                continue
            background_values = pd.to_numeric(processed[background_column], errors="coerce").to_numpy(dtype=float)
            target_y_all = region_y_all - background_values
            region_record["background_source"] = "reviewed_background_column_subtracted"
        else:
            target_y_all = region_y_all

        mask = (x >= low) & (x <= high) & np.isfinite(target_y_all)
        point_count = int(mask.sum())
        region_record["point_count"] = point_count
        if point_count < min_points:
            region_record["status"] = "insufficient_region_points"
            warnings.append(
                _warning(
                    "xps_component_fit_insufficient_points",
                    "A reviewed XPS component_fit region had too few points for fitting.",
                    severity="medium",
                    region_id=region_id,
                    point_count=point_count,
                    min_points=min_points,
                )
            )
            regions.append(region_record)
            continue

        raw_components = region.get("components") or []
        if not isinstance(raw_components, list) or not raw_components:
            region_record["status"] = "no_reviewed_components"
            warnings.append(
                _warning(
                    "xps_component_fit_components_missing",
                    "A reviewed XPS component_fit region did not provide reviewed components.",
                    severity="medium",
                    region_id=region_id,
                )
            )
            regions.append(region_record)
            continue

        specs: list[dict[str, Any]] = []
        for component_number, component in enumerate(raw_components, start=1):
            if not isinstance(component, dict):
                warnings.append(
                    _warning(
                        "xps_component_fit_component_ignored",
                        "A reviewed XPS component_fit component was ignored because it was not a mapping.",
                        severity="medium",
                        region_id=region_id,
                        component_number=component_number,
                    )
                )
                continue
            spec = _component_fit_component_spec(component, region_id=region_id, number=component_number, source=source, warnings=warnings)
            if spec is not None:
                specs.append(spec)
                all_reference_ids.update(spec.get("reference_ids", []))
        region_record["component_count"] = len(specs)
        if not specs:
            region_record["status"] = "no_valid_reviewed_components"
            regions.append(region_record)
            continue

        raw_spin_orbit_constraints: list[Any] = []
        spin_constraint_inputs_invalid = False
        for constraint_source in [params.get("spin_orbit_constraints"), region.get("spin_orbit_constraints")]:
            if constraint_source is None:
                continue
            if isinstance(constraint_source, list):
                raw_spin_orbit_constraints.extend(constraint_source)
            else:
                spin_constraint_inputs_invalid = True
        if spin_constraint_inputs_invalid:
            warnings.append(
                _warning(
                    "xps_component_fit_spin_orbit_constraints_ignored",
                    "XPS component_fit spin_orbit_constraints must be supplied as a list.",
                    severity="medium",
                    region_id=region_id,
                )
            )
            region_record["status"] = "invalid_spin_orbit_constraints"
            regions.append(region_record)
            continue
        spin_constraints, effective_bounds, dependent_indices, spin_constraints_invalid = _component_fit_spin_orbit_constraints(
            specs,
            raw_spin_orbit_constraints,
            region_id=region_id,
            warnings=warnings,
        )
        if spin_constraints_invalid:
            region_record.update(
                {
                    "status": "invalid_spin_orbit_constraints",
                    "spin_orbit_constraints": [
                        {key: value for key, value in constraint.items() if not key.endswith("_index")}
                        for constraint in spin_constraints
                    ],
                }
            )
            regions.append(region_record)
            continue
        for constraint in spin_constraints:
            all_reference_ids.update(constraint.get("reference_ids", []))

        x_region = x[mask]
        observed = target_y_all[mask]
        parameter_map: list[tuple[int, str]] = []
        x0: list[float] = []
        lower_bounds: list[float] = []
        upper_bounds: list[float] = []
        for spec_index, spec in enumerate(specs):
            if spec_index in dependent_indices:
                continue
            for name, initial_key in [
                ("center_eV", "initial_center_eV"),
                ("amplitude", "initial_amplitude"),
                ("fwhm_eV", "initial_fwhm_eV"),
            ]:
                parameter_map.append((spec_index, name))
                x0.append(float(spec[initial_key]))
                low_bound, high_bound = effective_bounds[spec_index][name]
                lower_bounds.append(float(low_bound))
                upper_bounds.append(float(high_bound))
            if spec["peak_shape"] == "pseudo_voigt":
                parameter_map.append((spec_index, "mixing"))
                x0.append(float(spec["initial_mixing"]))
                low_bound, high_bound = effective_bounds[spec_index]["mixing"]
                lower_bounds.append(float(low_bound))
                upper_bounds.append(float(high_bound))

        def unpack(values: np.ndarray) -> list[dict[str, float]]:
            fitted_specs: list[dict[str, float]] = []
            for spec in specs:
                fitted_specs.append(
                    {
                        "center_eV": float(spec["initial_center_eV"]),
                        "amplitude": float(spec["initial_amplitude"]),
                        "fwhm_eV": float(spec["initial_fwhm_eV"]),
                        "mixing": float(spec["initial_mixing"] or 0.0),
                    }
                )
            for value, (spec_index, name) in zip(values, parameter_map, strict=True):
                fitted_specs[spec_index][name] = float(value)
            for constraint in spin_constraints:
                anchor = fitted_specs[int(constraint["anchor_index"])]
                dependent = fitted_specs[int(constraint["dependent_index"])]
                dependent["center_eV"] = float(anchor["center_eV"]) + float(constraint["center_delta_eV"])
                dependent["fwhm_eV"] = float(anchor["fwhm_eV"]) * float(constraint["fwhm_ratio"])
                dependent["amplitude"] = float(anchor["amplitude"]) * float(constraint["amplitude_factor"])
                if specs[int(constraint["dependent_index"])]["peak_shape"] == "pseudo_voigt":
                    dependent["mixing"] = float(anchor["mixing"])
            return fitted_specs

        def model(values: np.ndarray) -> np.ndarray:
            fitted_specs = unpack(values)
            total = np.zeros_like(x_region, dtype=float)
            for spec, fitted_spec in zip(specs, fitted_specs, strict=True):
                total += _component_fit_profile(
                    x_region,
                    fitted_spec["amplitude"],
                    fitted_spec["center_eV"],
                    fitted_spec["fwhm_eV"],
                    fitted_spec["mixing"],
                    spec["peak_shape"],
                )
            return total

        try:
            result = least_squares(
                lambda values: model(values) - observed,
                np.asarray(x0, dtype=float),
                bounds=(np.asarray(lower_bounds, dtype=float), np.asarray(upper_bounds, dtype=float)),
                max_nfev=max_nfev,
            )
        except ValueError as exc:
            warnings.append(
                _warning(
                    "xps_component_fit_optimizer_failed",
                    "XPS component-fit optimizer failed before producing reviewed fit parameters.",
                    severity="medium",
                    region_id=region_id,
                    error=str(exc),
                )
            )
            region_record["status"] = "optimizer_failed"
            regions.append(region_record)
            continue

        fitted_signal = model(result.x)
        fit_metrics = _component_fit_quality(observed, fitted_signal, len(parameter_map))
        quality_checks, quality_warnings = _component_fit_quality_checks(fit_metrics, thresholds)
        warnings.extend(quality_warnings)
        optimizer_status = {
            "success": bool(result.success),
            "status": int(result.status),
            "message": str(result.message),
            "nfev": int(result.nfev),
            "cost": float(result.cost),
        }
        if not result.success:
            warnings.append(
                _warning(
                    "xps_component_fit_not_converged",
                    "XPS component-fit optimizer did not converge for a reviewed region.",
                    severity="medium",
                    region_id=region_id,
                    optimizer_status=optimizer_status,
                )
            )
            region_record.update({"status": "optimizer_not_converged", "optimizer_status": optimizer_status, "fit_quality": fit_metrics})
            regions.append(region_record)
            continue

        if processed.loc[mask, fit_column].notna().any():
            warnings.append(
                _warning(
                    "xps_component_fit_region_overlap",
                    "A reviewed XPS component_fit region overlaps a previously fitted region; later region values were written for the overlap.",
                    severity="low",
                    region_id=region_id,
                )
            )
        residual = observed - fitted_signal
        processed.loc[mask, fit_column] = fitted_signal
        processed.loc[mask, residual_column] = residual
        processed.loc[mask, region_id_column] = region_id

        fitted_specs = unpack(result.x)
        fitted_components: list[dict[str, Any]] = []
        fitted_areas: list[float] = []
        spin_constraint_by_component: dict[int, dict[str, Any]] = {}
        for constraint in spin_constraints:
            anchor_index = int(constraint["anchor_index"])
            dependent_index = int(constraint["dependent_index"])
            spin_constraint_by_component[anchor_index] = {**constraint, "constraint_role": "anchor"}
            spin_constraint_by_component[dependent_index] = {**constraint, "constraint_role": "dependent"}
        for spec_index, (spec, fitted_spec) in enumerate(zip(specs, fitted_specs, strict=True)):
            spin_constraint = spin_constraint_by_component.get(spec_index)
            area = _component_fit_area(
                fitted_spec["amplitude"],
                fitted_spec["fwhm_eV"],
                fitted_spec["mixing"],
                spec["peak_shape"],
            )
            fitted_areas.append(area)
            fitted_component = {
                "component_id": spec["component_id"],
                "region_id": region_id,
                "label": spec["label"],
                "element": spec["element"],
                "core_level": spec["core_level"],
                "peak_shape": spec["peak_shape"],
                "spin_orbit_group_id": spec.get("spin_orbit_group_id"),
                "spin_orbit_role": (spin_constraint.get("constraint_role") if spin_constraint else spec.get("spin_orbit_role")),
                "spin_orbit_constraint_id": spin_constraint.get("constraint_id") if spin_constraint else None,
                "spin_orbit_anchor_component_id": spin_constraint.get("anchor_component_id") if spin_constraint else None,
                "spin_orbit_dependent_component_id": spin_constraint.get("dependent_component_id") if spin_constraint else None,
                "spin_orbit_center_delta_eV": spin_constraint.get("center_delta_eV") if spin_constraint else None,
                "spin_orbit_area_ratio": spin_constraint.get("area_ratio") if spin_constraint else None,
                "spin_orbit_fwhm_ratio": spin_constraint.get("fwhm_ratio") if spin_constraint else None,
                "spin_orbit_constraint_status": spin_constraint.get("status") if spin_constraint else None,
                "spin_orbit_parameter_origin": spin_constraint.get("parameter_origin") if spin_constraint else None,
                "spin_orbit_source_summary": spin_constraint.get("source_summary") if spin_constraint else None,
                "spin_orbit_applicability_notes": "; ".join(spin_constraint.get("applicability_notes") or []) if spin_constraint else None,
                "initial_center_eV": spec["initial_center_eV"],
                "fitted_center_eV": fitted_spec["center_eV"],
                "initial_amplitude": spec["initial_amplitude"],
                "fitted_amplitude": fitted_spec["amplitude"],
                "initial_fwhm_eV": spec["initial_fwhm_eV"],
                "fitted_fwhm_eV": fitted_spec["fwhm_eV"],
                "initial_mixing": spec.get("initial_mixing"),
                "fitted_mixing": fitted_spec["mixing"] if spec["peak_shape"] == "pseudo_voigt" else None,
                "fitted_area": area,
                "relative_fit_area_percent": np.nan,
                "fit_rmse": fit_metrics["rmse"],
                "fit_r_squared": fit_metrics["r_squared"],
                "confidence": spec.get("confidence", "low"),
                "assignment_source": spec.get("assignment_source", source),
                "status": "fitted",
                "notes": spec.get("notes", "reviewed XPS component fit; screening only"),
                "bounds": spec["bounds"],
                "reference_ids": spec.get("reference_ids", []),
                "reviewer_notes": spec.get("reviewer_notes", []),
                "caveats": spec.get("caveats", []),
            }
            fitted_components.append(fitted_component)

        area_total = float(np.sum(fitted_areas))
        if area_total > 0:
            for fitted_component in fitted_components:
                fitted_component["relative_fit_area_percent"] = float(fitted_component["fitted_area"] / area_total * 100.0)

        for fitted_component in fitted_components:
            row = {key: fitted_component.get(key, np.nan) for key in _component_fit_columns()}
            component_rows.append(row)

        region_record.update(
            {
                "status": "reviewed_component_fit_screening",
                "fitted_component_count": len(fitted_components),
                "fit_quality": fit_metrics,
                "fit_quality_checks": quality_checks,
                "optimizer_status": optimizer_status,
                "components": fitted_components,
                "output_columns": [fit_column, residual_column, region_id_column],
                "spin_orbit_constraint_count": len(spin_constraints),
                "constrained_component_count": len(dependent_indices),
                "spin_orbit_constraints": [
                    {key: value for key, value in constraint.items() if not key.endswith("_index") and key != "amplitude_factor"}
                    for constraint in spin_constraints
                ],
            }
        )
        fitted_regions += 1
        regions.append(region_record)

    table = pd.DataFrame(component_rows, columns=_component_fit_columns())
    fitted_component_count = int((table["status"].astype(str) == "fitted").sum()) if not table.empty else 0
    record.update(
        {
            "status": "reviewed_component_fit_screening" if fitted_regions else "no_regions_fitted",
            "confidence": "low" if fitted_regions else "insufficient",
            "region_count": len(regions),
            "fitted_region_count": fitted_regions,
            "component_count": int(sum(int(region.get("component_count", 0)) for region in regions)),
            "fitted_component_count": fitted_component_count,
            "spin_orbit_constraint_count": int(sum(int(region.get("spin_orbit_constraint_count", 0)) for region in regions)),
            "constrained_component_count": int(sum(int(region.get("constrained_component_count", 0)) for region in regions)),
            "regions": regions,
            "reference_ids": sorted(all_reference_ids),
            "warnings": warnings,
        }
    )
    return table, record, warnings


def _region_record_columns() -> list[str]:
    return [
        "region_id",
        "label",
        "region_role",
        "element",
        "core_level",
        "binding_energy_min_eV",
        "binding_energy_max_eV",
        "point_count",
        "calibration_group_id",
        "linked_output_refs",
        "reference_ids",
        "confidence",
        "status",
    ]


def _region_record_refs(region: dict[str, Any], linked_outputs: dict[str, str | None]) -> list[str]:
    refs: list[str] = []
    for key in [
        "background_model_ref",
        "background_subtraction_ref",
        "component_quantification_ref",
        "component_fit_ref",
        "component_fit_table_ref",
        "processed_csv_ref",
        "peak_table_ref",
    ]:
        value = region.get(key)
        if isinstance(value, str) and value.strip():
            refs.append(value.strip())
    for key in [
        "background_model",
        "background_subtraction",
        "component_table",
        "component_fit",
        "component_fit_table",
        "processed_csv",
        "peak_table",
    ]:
        value = linked_outputs.get(key)
        if value:
            refs.append(str(value))
    return sorted(dict.fromkeys(refs))


def _apply_region_records(
    processed: pd.DataFrame,
    parameters: dict[str, Any],
    *,
    linked_outputs: dict[str, str | None],
) -> tuple[pd.DataFrame, dict[str, Any] | None, list[dict[str, Any]]]:
    params = parameters.get("region_records", {})
    if not isinstance(params, dict) or not params.get("enabled", False):
        return pd.DataFrame(columns=_region_record_columns()), None, []

    warnings: list[dict[str, Any]] = []
    method = str(params.get("method") or "reviewed_multi_region_project_record")
    source = str(params.get("source") or "ea.xps.region_records:v0.2")
    if method != "reviewed_multi_region_project_record":
        warnings.append(
            _warning(
                "xps_region_records_method_unsupported",
                "Only reviewed_multi_region_project_record is supported for XPS region_records in EA v0.2.",
                severity="medium",
                requested_method=method,
            )
        )
        method = "reviewed_multi_region_project_record"
    min_points, min_adjusted = _coerce_int(params.get("min_points"), 3, minimum=1)
    if min_adjusted:
        warnings.append(
            _warning(
                "xps_region_records_min_points_adjusted",
                "Invalid XPS region_records min_points was adjusted before processing.",
                severity="medium",
                min_points=min_points,
            )
        )

    record: dict[str, Any] = {
        "enabled": True,
        "method": method,
        "assignment_source": source,
        "min_points": min_points,
        "status": "not_applied",
        "confidence": "insufficient",
        "region_count": 0,
        "reviewed_region_count": 0,
        "regions": [],
        "linked_output_refs": sorted(str(value) for value in linked_outputs.values() if value),
        "reference_ids": _coerce_string_list(params.get("reference_ids")),
        "reviewer_notes": _coerce_string_list(params.get("reviewer_notes") or params.get("notes")),
        "caveats": _coerce_string_list(params.get("caveats")),
        "boundary": (
            "XPS region_records are reviewed project-organization and provenance records only. EA v0.2 does not share charge correction "
            "or align survey/core-level spectra without review/provenance, assign chemical states, calculate formal multi-region composition, or rank samples."
        ),
    }

    raw_regions = params.get("regions", [])
    if not isinstance(raw_regions, list):
        raw_regions = []
        warnings.append(
            _warning(
                "xps_region_records_regions_ignored",
                "XPS region_records regions were ignored because they were not supplied as a list.",
                severity="medium",
            )
        )
    if not raw_regions:
        warnings.append(
            _warning(
                "xps_region_records_regions_missing",
                "region_records was enabled, but no reviewed XPS regions were supplied.",
                severity="medium",
            )
        )
        record.update({"status": "enabled_without_reviewed_regions", "warnings": warnings})
        return pd.DataFrame(columns=_region_record_columns()), record, warnings

    x = processed["binding_energy_eV"].to_numpy(dtype=float)
    regions: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    all_reference_ids = set(record["reference_ids"])
    reviewed_count = 0
    default_calibration_group = params.get("default_calibration_group_id") or params.get("calibration_group_id")

    for number, region in enumerate(raw_regions, start=1):
        if not isinstance(region, dict):
            warnings.append(
                _warning(
                    "xps_region_record_ignored",
                    "A reviewed XPS region record was ignored because it was not a mapping.",
                    severity="medium",
                    region_number=number,
                )
            )
            continue
        region_id = str(region.get("region_id") or region.get("id") or f"xps-region-record-{number:03d}")
        role = str(region.get("region_role") or region.get("role") or "core_level").strip().lower()
        if role not in {"survey", "core_level", "valence", "auger", "other"}:
            warnings.append(
                _warning(
                    "xps_region_record_role_unsupported",
                    "A reviewed XPS region role was not recognized and was recorded as other.",
                    severity="low",
                    region_id=region_id,
                    requested_role=role,
                )
            )
            role = "other"
        low, high = _background_window(region)
        reference_ids = _coerce_string_list(region.get("reference_ids"))
        all_reference_ids.update(reference_ids)
        linked_refs = _region_record_refs(region, linked_outputs)
        region_record: dict[str, Any] = {
            "region_id": region_id,
            "label": str(region.get("label") or region_id),
            "region_role": role,
            "element": str(region.get("element") or ""),
            "core_level": str(region.get("core_level") or region.get("orbital") or ""),
            "binding_energy_min_eV": low,
            "binding_energy_max_eV": high,
            "calibration_group_id": str(region.get("calibration_group_id") or default_calibration_group or "") or None,
            "point_count": 0,
            "linked_output_refs": linked_refs,
            "reference_ids": reference_ids,
            "reviewer_notes": _coerce_string_list(region.get("reviewer_notes") or region.get("notes")),
            "caveats": _coerce_string_list(region.get("caveats")),
            "confidence": str(region.get("confidence") or "low").strip().lower(),
            "assignment_source": str(region.get("source") or region.get("assignment_source") or source),
            "status": "invalid_region_window",
        }
        if low is None or high is None:
            warnings.append(
                _warning(
                    "xps_region_record_invalid_window",
                    "A reviewed XPS region record has an invalid binding-energy window.",
                    severity="medium",
                    region_id=region_id,
                )
            )
        else:
            mask = (x >= low) & (x <= high)
            point_count = int(mask.sum())
            region_record["point_count"] = point_count
            if point_count < min_points:
                region_record["status"] = "insufficient_region_points"
                warnings.append(
                    _warning(
                        "xps_region_record_insufficient_points",
                        "A reviewed XPS region record had too few points in the processed table.",
                        severity="medium",
                        region_id=region_id,
                        point_count=point_count,
                        min_points=min_points,
                    )
                )
            else:
                region_record["status"] = "reviewed_multi_region_project_record"
                reviewed_count += 1
        regions.append(region_record)
        row = {key: region_record.get(key, np.nan) for key in _region_record_columns()}
        rows.append(row)

    table = pd.DataFrame(rows, columns=_region_record_columns())
    record.update(
        {
            "status": "reviewed_multi_region_project_record" if reviewed_count else "no_regions_recorded",
            "confidence": "low" if reviewed_count else "insufficient",
            "region_count": len(regions),
            "reviewed_region_count": reviewed_count,
            "regions": regions,
            "reference_ids": sorted(all_reference_ids),
            "warnings": warnings,
        }
    )
    return table, record, warnings


def _analyze_peaks(
    peaks: pd.DataFrame,
    request: XPSProcessingRequest,
    component_summary: dict[str, Any] | None = None,
    background_record: dict[str, Any] | None = None,
    background_subtraction_record: dict[str, Any] | None = None,
    component_fit_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    analysis: dict[str, Any] = {
        "peak_count": int(len(peaks)),
        "strongest_peaks": [],
        "calibration": {
            "energy_shift_eV": float(request.energy_shift_eV),
            "calibration_reference": request.calibration_reference,
            "confidence": "low" if request.calibration_reference else "insufficient",
        },
        "possible_interpretations": [],
    }
    if peaks.empty:
        analysis["possible_interpretations"].append(
            {
                "text": "No stable XPS peak was detected by the current automatic settings.",
                "confidence": "insufficient",
                "evidence": [],
            }
        )
    else:
        strongest = peaks.sort_values("prominence", ascending=False).head(8)
        analysis["strongest_peaks"] = [
            {
                "peak_id": str(row["peak_id"]),
                "binding_energy_eV": float(row["binding_energy_eV"]),
                "assignment_source": str(row["assignment_source"]),
            }
            for _, row in strongest.iterrows()
        ]
        evidence = [str(value) for value in strongest["peak_id"].head(5)]
        analysis["possible_interpretations"].append(
            {
                "text": "Detected XPS peak(s) indicate photoelectron spectral structure in the reviewed binding-energy window; treat them as screening evidence only until calibration, background model, component fitting, and references are user-confirmed.",
                "confidence": "low",
                "evidence": evidence,
                "assignment_source": str(strongest.iloc[0]["assignment_source"]),
            }
        )
    if not request.calibration_reference:
        analysis["possible_interpretations"].append(
            {
                "text": "No calibration reference text was recorded; binding-energy positions should not be used for chemical-state assignments until the user confirms charge correction or instrument calibration context.",
                "confidence": "insufficient",
                "evidence": ["calibration"],
            }
        )
    if component_summary:
        analysis["component_quantification"] = component_summary
        if component_summary.get("enabled"):
            status = component_summary.get("status", "unknown")
            evidence = [item.get("component_id") for item in component_summary.get("components", []) if item.get("component_id")]
            analysis["possible_interpretations"].append(
                {
                    "text": "Reviewed XPS component windows were integrated to produce screening-level component areas and, when all sensitivity factors are present, RSF-normalized relative atomic percent estimates. These values are not definitive composition or chemical-state assignments.",
                    "confidence": "low" if component_summary.get("quantified_component_count", 0) else "insufficient",
                    "evidence": evidence,
                    "assignment_source": component_summary.get("assignment_source", "ea.xps.component_quantification:v0.2"),
                    "component_quantification_status": status,
                }
            )
    if background_record:
        analysis["background_model"] = background_record
        if background_record.get("status") == "reviewed_background_model_recorded":
            analysis["possible_interpretations"].append(
                {
                    "text": "Reviewed XPS background model records were saved for the relevant binding-energy region(s). Use them to interpret component screening and future fitting, but do not treat the record as automatic Shirley/Tougaard subtraction, spin-orbit constrained fitting, composition, or chemical-state proof.",
                    "confidence": background_record.get("confidence", "low"),
                    "evidence": ["background_model"],
                    "assignment_source": background_record.get("assignment_source", "ea.xps.background_model:v0.2"),
                }
            )
    if background_subtraction_record:
        analysis["background_subtraction"] = background_subtraction_record
        if _is_background_subtraction_success(background_subtraction_record):
            method_label = _background_subtraction_method_label(str(background_subtraction_record.get("method") or "reviewed_linear_background_subtraction"))
            analysis["possible_interpretations"].append(
                {
                    "text": f"Reviewed {method_label} XPS background subtraction was applied only inside explicit user-confirmed binding-energy regions. Treat the corrected columns as preprocessing artifacts for review, not as QUASES/depth-profile modeling, definitive composition, chemical-state assignment, or spin-orbit constrained fitting.",
                    "confidence": background_subtraction_record.get("confidence", "low"),
                    "evidence": ["background_subtraction"],
                    "assignment_source": background_subtraction_record.get("assignment_source", "ea.xps.background_subtraction:v0.2"),
                }
            )
    if component_fit_record:
        analysis["component_fit"] = component_fit_record
        if component_fit_record.get("status") == "reviewed_component_fit_screening":
            evidence = [
                component.get("component_id")
                for region in component_fit_record.get("regions", [])
                if isinstance(region, dict)
                for component in region.get("components", [])
                if isinstance(component, dict) and component.get("component_id")
            ]
            constraint_count = int(component_fit_record.get("spin_orbit_constraint_count", 0) or 0)
            constraint_note = (
                " Reviewed spin-orbit constraints were applied from recorded signed deltas/ratios/bounds with parameter origins and references preserved when supplied."
                if constraint_count
                else " No automatic spin-orbit constrained fitting was performed."
            )
            analysis["possible_interpretations"].append(
                {
                    "text": (
                        "Reviewed XPS component-fit screening produced fitted component positions, widths, amplitudes, and areas inside explicit "
                        "user-confirmed regions. Treat these values as numerical screening artifacts, not as chemical-state proof or definitive composition."
                        f"{constraint_note}"
                    ),
                    "confidence": component_fit_record.get("confidence", "low"),
                    "evidence": ["component_fit", *evidence] if evidence else ["component_fit"],
                    "assignment_source": component_fit_record.get("assignment_source", "ea.xps.component_fit:v0.2"),
                    "component_fit_status": component_fit_record.get("status", "unknown"),
                }
            )
    return analysis


def _created_day(created_at: str | None) -> str | None:
    return created_at[:10] if created_at else None


def _uses_v0_2_project_ids(project_id: str) -> bool:
    return project_id.startswith("prj-")


def _plot_xps(
    processed: pd.DataFrame,
    peaks: pd.DataFrame,
    components: pd.DataFrame,
    output: Path,
    *,
    background_subtraction: dict[str, Any] | None = None,
    component_fit: dict[str, Any] | None = None,
    footer: str | None = None,
) -> None:
    fig, ax = styled_subplots(figsize=(6.0, 4.0))
    ax.plot(processed["binding_energy_eV"], processed["processed_intensity"], color=NATURE_LIKE_COLORS["blue"], linewidth=1.2, label="Processed intensity")
    if background_subtraction and _is_background_subtraction_success(background_subtraction):
        method_label = _background_subtraction_method_label(str(background_subtraction.get("method") or "reviewed_linear_background_subtraction"))
        background_column = str(background_subtraction.get("background_column") or "xps_linear_background")
        corrected_column = str(background_subtraction.get("corrected_intensity_column") or "xps_background_subtracted_intensity")
        if background_column in processed.columns:
            background_mask = pd.to_numeric(processed[background_column], errors="coerce").notna()
            if bool(background_mask.any()):
                ax.plot(
                    processed.loc[background_mask, "binding_energy_eV"],
                    processed.loc[background_mask, background_column],
                    color=NATURE_LIKE_COLORS["gray"],
                    linewidth=1.0,
                    linestyle="--",
                    label=f"Reviewed {method_label} background",
                )
        if corrected_column in processed.columns:
            corrected_mask = pd.to_numeric(processed[corrected_column], errors="coerce").notna()
            if bool(corrected_mask.any()):
                ax.plot(
                    processed.loc[corrected_mask, "binding_energy_eV"],
                    processed.loc[corrected_mask, corrected_column],
                    color=NATURE_LIKE_COLORS["orange"],
                    linewidth=1.0,
                    label="Background-subtracted intensity",
                )
    if component_fit and component_fit.get("status") == "reviewed_component_fit_screening":
        fit_column = str(component_fit.get("fit_intensity_column") or "xps_component_fit_intensity")
        if fit_column in processed.columns:
            fit_mask = pd.to_numeric(processed[fit_column], errors="coerce").notna()
            if bool(fit_mask.any()):
                ax.plot(
                    processed.loc[fit_mask, "binding_energy_eV"],
                    processed.loc[fit_mask, fit_column],
                    color=NATURE_LIKE_COLORS["pink"],
                    linewidth=1.0,
                    linestyle="-.",
                    label="Reviewed component fit",
                )
    if not components.empty:
        for _, component in components[components["status"].astype(str) == "integrated"].head(8).iterrows():
            low = float(component["binding_energy_min_eV"])
            high = float(component["binding_energy_max_eV"])
            ax.axvspan(low, high, color=NATURE_LIKE_COLORS["green"], alpha=0.12, linewidth=0)
            centroid = component.get("centroid_eV")
            if pd.notna(centroid):
                ax.annotate(
                    str(component["component_id"]),
                    (float(centroid), float(processed["processed_intensity"].max()) * 0.86),
                    textcoords="offset points",
                    xytext=(0, 0),
                    ha="center",
                    fontsize=6,
                    color=NATURE_LIKE_COLORS["green"],
                )
    if not peaks.empty:
        ax.scatter(peaks["binding_energy_eV"], peaks["processed_intensity"], color=NATURE_LIKE_COLORS["black"], s=18, label="Detected peaks", zorder=3)
        for _, peak in peaks.sort_values("prominence", ascending=False).head(8).iterrows():
            ax.annotate(
                f"{float(peak['binding_energy_eV']):.1f}",
                (float(peak["binding_energy_eV"]), float(peak["processed_intensity"])),
                textcoords="offset points",
                xytext=(0, 6),
                ha="center",
                fontsize=7,
            )
    ax.invert_xaxis()
    style_axis(ax, title="XPS spectrum", xlabel="Binding energy (eV)", ylabel="Normalized intensity (a.u.)")
    save_styled_figure(fig, output, footer=footer)


def process_xps_result(
    root: Path,
    *,
    characterization_metadata_path: Path,
    project_id: str,
    sample_refs: list[str],
    request: XPSProcessingRequest,
    created_at: str | None = None,
) -> Path:
    metadata = read_yaml(characterization_metadata_path)
    require_confirmed_review(root, request.column_review_ref)
    require_confirmed_review(root, request.calibration_review_ref)
    require_confirmed_review(root, request.parameter_review_ref)
    raw_path = root / metadata["project_raw_path"]
    inspection = inspect_xps_file(raw_path)
    if inspection.file_kind != "xps":
        raise XPSProcessingError(f"File is {inspection.file_kind}, not XPS")

    parameters = _merge_parameters(request.processing_parameters)
    processed, processing_warnings = _apply_processing(_confirmed_frame(raw_path, request), parameters)
    background_subtraction_record, background_subtraction_warnings = _apply_background_subtraction(processed, parameters)
    component_fit_table, component_fit_record, component_fit_warnings = _apply_component_fit(processed, parameters)
    peaks = _detect_peaks(processed, parameters, request.x_unit)
    components, component_summary, component_warnings = _apply_component_quantification(processed, parameters)
    background_record, background_warnings = _record_background_model(parameters)
    peak_analysis = _analyze_peaks(peaks, request, component_summary, background_record, background_subtraction_record, component_fit_record)
    day = _created_day(created_at)
    project_slug = infer_project_slug(project_id)
    if _uses_v0_2_project_ids(project_id):
        result_id = next_standard_id(root, "result", project_slug, method="xps", day=day)
        figure_id = next_standard_id(root, "figure", project_slug, method="xps", day=day)
    else:
        result_id = next_id(root, "xps_result", day)
        figure_id = None
    sample_dir = sample_refs[0] if sample_refs else "unmapped-sample"
    output_dir = root / "processed" / sample_dir / "xps" / result_id
    processed_csv = output_dir / "xps_processed.csv"
    peaks_csv = output_dir / "xps_peaks.csv"
    components_csv = output_dir / "xps_components.csv"
    component_fit_csv = output_dir / "xps_component_fit.csv"
    component_fit_yml = output_dir / "xps_component_fit.yml"
    region_records_csv = output_dir / "xps_region_records.csv"
    region_records_yml = output_dir / "xps_region_records.yml"
    background_yml = output_dir / "xps_background.yml"
    background_subtraction_yml = output_dir / "xps_background_subtraction.yml"
    figure_name = f"{figure_id}.png" if figure_id else "xps_plot.png"
    figure = output_dir / figure_name
    result_metadata = output_dir / "xps_metadata.yml"
    for output in [
        processed_csv,
        peaks_csv,
        components_csv,
        component_fit_csv,
        component_fit_yml,
        region_records_csv,
        region_records_yml,
        background_yml,
        background_subtraction_yml,
        figure,
        result_metadata,
    ]:
        assert_not_raw_output_path(root, output)

    output_dir.mkdir(parents=True, exist_ok=True)
    processed.to_csv(processed_csv, index=False)
    peaks.to_csv(peaks_csv, index=False)
    components.to_csv(components_csv, index=False)
    background_ref: str | None = None
    if background_record is not None:
        background_ref = str(background_yml.relative_to(root))
        background_record["record_ref"] = background_ref
        write_yaml(background_yml, background_record)
        if peak_analysis.get("background_model"):
            peak_analysis["background_model"]["record_ref"] = background_ref
        for item in peak_analysis.get("possible_interpretations", []):
            evidence = item.get("evidence")
            if isinstance(evidence, list):
                item["evidence"] = [background_ref if value == "background_model" else value for value in evidence]
    background_subtraction_ref: str | None = None
    if background_subtraction_record is not None:
        background_subtraction_ref = str(background_subtraction_yml.relative_to(root))
        background_subtraction_record["record_ref"] = background_subtraction_ref
        write_yaml(background_subtraction_yml, background_subtraction_record)
        if peak_analysis.get("background_subtraction"):
            peak_analysis["background_subtraction"]["record_ref"] = background_subtraction_ref
        for item in peak_analysis.get("possible_interpretations", []):
            evidence = item.get("evidence")
            if isinstance(evidence, list):
                item["evidence"] = [background_subtraction_ref if value == "background_subtraction" else value for value in evidence]
    component_fit_table_ref: str | None = None
    component_fit_ref: str | None = None
    if component_fit_record is not None:
        component_fit_table_ref = str(component_fit_csv.relative_to(root))
        component_fit_ref = str(component_fit_yml.relative_to(root))
        component_fit_record["record_ref"] = component_fit_ref
        component_fit_record["component_table_ref"] = component_fit_table_ref
        component_fit_table.to_csv(component_fit_csv, index=False)
        write_yaml(component_fit_yml, component_fit_record)
        if peak_analysis.get("component_fit"):
            peak_analysis["component_fit"]["record_ref"] = component_fit_ref
            peak_analysis["component_fit"]["component_table_ref"] = component_fit_table_ref
        for item in peak_analysis.get("possible_interpretations", []):
            evidence = item.get("evidence")
            if isinstance(evidence, list):
                item["evidence"] = [component_fit_ref if value == "component_fit" else value for value in evidence]
    region_records_table_ref: str | None = None
    region_records_ref: str | None = None
    region_records_table, region_records_record, region_records_warnings = _apply_region_records(
        processed,
        parameters,
        linked_outputs={
            "processed_csv": str(processed_csv.relative_to(root)),
            "peak_table": str(peaks_csv.relative_to(root)),
            "component_table": str(components_csv.relative_to(root)),
            "background_model": background_ref,
            "background_subtraction": background_subtraction_ref,
            "component_fit": component_fit_ref,
            "component_fit_table": component_fit_table_ref,
        },
    )
    if region_records_record is not None:
        region_records_table_ref = str(region_records_csv.relative_to(root))
        region_records_ref = str(region_records_yml.relative_to(root))
        region_records_record["record_ref"] = region_records_ref
        region_records_record["region_table_ref"] = region_records_table_ref
        region_records_table.to_csv(region_records_csv, index=False)
        write_yaml(region_records_yml, region_records_record)
        peak_analysis["region_records"] = region_records_record
    _plot_xps(
        processed,
        peaks,
        components,
        figure,
        background_subtraction=background_subtraction_record,
        component_fit=component_fit_record,
        footer=figure_footer(figure_id, None) if figure_id else None,
    )

    warnings: list[Any] = []
    if request.x_unit == "unknown":
        warnings.append(_warning("xps_x_unit_unknown", "XPS x unit remains unknown after confirmation.", severity="medium"))
    if not request.calibration_reference:
        warnings.append(_warning("xps_calibration_reference_missing", "No XPS calibration reference text was recorded.", severity="medium"))
    warnings.extend(processing_warnings)
    warnings.extend(background_subtraction_warnings)
    warnings.extend(component_fit_warnings)
    warnings.extend(region_records_warnings)
    warnings.extend(component_warnings)
    warnings.extend(background_warnings)
    outputs = {
        "figure": str(figure.relative_to(root)),
        "peak_table": str(peaks_csv.relative_to(root)),
        "component_table": str(components_csv.relative_to(root)),
        "processed_csv": str(processed_csv.relative_to(root)),
        "metadata": str(result_metadata.relative_to(root)),
    }
    if background_ref:
        outputs["background_model"] = background_ref
    if background_subtraction_ref:
        outputs["background_subtraction"] = background_subtraction_ref
    if component_fit_ref:
        outputs["component_fit"] = component_fit_ref
    if component_fit_table_ref:
        outputs["component_fit_table"] = component_fit_table_ref
    if region_records_ref:
        outputs["region_records"] = region_records_ref
    if region_records_table_ref:
        outputs["region_records_table"] = region_records_table_ref
    result = XPSProcessingResult(
        xps_result_id=result_id,
        result_id=result_id,
        project_id=project_id,
        characterization_file_ref=metadata["characterization_id"],
        sample_refs=sample_refs,
        status="warning" if warnings else "success",
        x_column=request.x_column,
        y_column=request.y_column,
        x_unit=request.x_unit,  # type: ignore[arg-type]
        energy_shift_eV=float(request.energy_shift_eV),
        calibration_reference=request.calibration_reference,
        processing_parameters=parameters,
        outputs=outputs,
        peak_analysis=peak_analysis,
        figure_id=figure_id,
        warnings=warnings,
        review_refs=[request.column_review_ref, request.calibration_review_ref, request.parameter_review_ref],
        created_at=created_at or EARecord.now_iso(),
        updated_at=created_at or EARecord.now_iso(),
    )
    write_yaml(result_metadata, result.model_dump(exclude_none=True))
    provenance_path = write_provenance_entry(
        root,
        workflow="xps_processing",
        inputs={
            "records": [str(characterization_metadata_path.relative_to(root))],
            "files": [metadata["project_raw_path"]],
        },
        outputs={
            "records": [str(result_metadata.relative_to(root))],
            "files": [
                value
                for value in [
                    str(processed_csv.relative_to(root)),
                    str(peaks_csv.relative_to(root)),
                    str(components_csv.relative_to(root)),
                    component_fit_table_ref,
                    component_fit_ref,
                    region_records_table_ref,
                    region_records_ref,
                    background_ref,
                    background_subtraction_ref,
                    str(figure.relative_to(root)),
                ]
                if value
            ],
        },
        parameters={
            "x_column": request.x_column,
            "y_column": request.y_column,
            "x_unit": request.x_unit,
            "energy_shift_eV": float(request.energy_shift_eV),
            "calibration_reference": request.calibration_reference,
            "processing_parameters": parameters,
        },
        review_refs=[request.column_review_ref, request.calibration_review_ref, request.parameter_review_ref],
        warnings=warnings,
        scripts=[{"path": "src/ea/xps/service.py", "version": "0.2.0"}],
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
                "script": "src/ea/xps/service.py",
                "parameters": {
                    "x_column": request.x_column,
                    "y_column": request.y_column,
                    "x_unit": request.x_unit,
                    "energy_shift_eV": float(request.energy_shift_eV),
                    "calibration_reference": request.calibration_reference,
                    "processing_parameters": parameters,
                },
            },
            caption="XPS spectrum with processed intensity, detected screening peaks, reviewed component/background/region records, optional reviewed background-subtraction overlays, and traceable calibration/processing parameters.",
            purpose="xps_analysis_report",
            style_profile=NATURE_LIKE_STYLE_PROFILE,
            source_data_refs=[
                value
                for value in [
                    str(processed_csv.relative_to(root)),
                    str(peaks_csv.relative_to(root)),
                    str(components_csv.relative_to(root)),
                    component_fit_table_ref,
                    component_fit_ref,
                    region_records_table_ref,
                    region_records_ref,
                    background_ref,
                    background_subtraction_ref,
                ]
                if value
            ],
        )
    return result_metadata
