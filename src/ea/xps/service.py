from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

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
    return {
        "background_column": "xps_linear_background",
        "corrected_intensity_column": "xps_background_subtracted_intensity",
        "region_id_column": "xps_background_subtraction_region_id",
    }


def _background_subtraction_method_label(method: str) -> str:
    return "Shirley" if method == "reviewed_shirley_background_subtraction" else "linear"


def _background_subtraction_success_status(method: str) -> str:
    if method == "reviewed_shirley_background_subtraction":
        return "reviewed_shirley_background_subtracted"
    return "reviewed_linear_background_subtracted"


def _background_subtraction_region_status(method: str) -> str:
    if method == "reviewed_shirley_background_subtraction":
        return "shirley_background_subtracted"
    return "linear_background_subtracted"


def _is_background_subtraction_success(record: dict[str, Any]) -> bool:
    return record.get("status") in {"reviewed_linear_background_subtracted", "reviewed_shirley_background_subtracted"}


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


def _apply_background_subtraction(processed: pd.DataFrame, parameters: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    params = parameters.get("background_subtraction", {})
    if not isinstance(params, dict) or not params.get("enabled", False):
        return None, []

    warnings: list[dict[str, Any]] = []
    method = str(params.get("method") or "reviewed_linear_background_subtraction")
    supported_methods = {"reviewed_linear_background_subtraction", "reviewed_shirley_background_subtraction"}
    method_label = _background_subtraction_method_label(method)
    defaults = _background_subtraction_defaults(method)
    base_defaults = _background_subtraction_defaults("reviewed_linear_background_subtraction")
    source = str(params.get("source") or "ea.xps.background_subtraction:v0.2")
    input_column = _column_name(params.get("input_intensity_column"), "processed_intensity")
    background_column_input = params.get("background_column")
    corrected_column_input = params.get("corrected_intensity_column")
    if method == "reviewed_shirley_background_subtraction":
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
            "EA v0.2 does not automatically choose endpoints/windows, perform undeclared Tougaard subtraction or peak fitting, assign chemical states, "
            "prove composition, or perform spin-orbit constrained fitting from this record."
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


def _analyze_peaks(
    peaks: pd.DataFrame,
    request: XPSProcessingRequest,
    component_summary: dict[str, Any] | None = None,
    background_record: dict[str, Any] | None = None,
    background_subtraction_record: dict[str, Any] | None = None,
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
                    "text": f"Reviewed {method_label} XPS background subtraction was applied only inside explicit user-confirmed binding-energy regions. Treat the corrected columns as preprocessing artifacts for review, not as Tougaard modeling, definitive composition, chemical-state assignment, or spin-orbit constrained fitting.",
                    "confidence": background_subtraction_record.get("confidence", "low"),
                    "evidence": ["background_subtraction"],
                    "assignment_source": background_subtraction_record.get("assignment_source", "ea.xps.background_subtraction:v0.2"),
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
    peaks = _detect_peaks(processed, parameters, request.x_unit)
    components, component_summary, component_warnings = _apply_component_quantification(processed, parameters)
    background_record, background_warnings = _record_background_model(parameters)
    peak_analysis = _analyze_peaks(peaks, request, component_summary, background_record, background_subtraction_record)
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
    background_yml = output_dir / "xps_background.yml"
    background_subtraction_yml = output_dir / "xps_background_subtraction.yml"
    figure_name = f"{figure_id}.png" if figure_id else "xps_plot.png"
    figure = output_dir / figure_name
    result_metadata = output_dir / "xps_metadata.yml"
    for output in [processed_csv, peaks_csv, components_csv, background_yml, background_subtraction_yml, figure, result_metadata]:
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
    _plot_xps(
        processed,
        peaks,
        components,
        figure,
        background_subtraction=background_subtraction_record,
        footer=figure_footer(figure_id, None) if figure_id else None,
    )

    warnings: list[Any] = []
    if request.x_unit == "unknown":
        warnings.append(_warning("xps_x_unit_unknown", "XPS x unit remains unknown after confirmation.", severity="medium"))
    if not request.calibration_reference:
        warnings.append(_warning("xps_calibration_reference_missing", "No XPS calibration reference text was recorded.", severity="medium"))
    warnings.extend(processing_warnings)
    warnings.extend(background_subtraction_warnings)
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
            caption="XPS spectrum with processed intensity, detected screening peaks, reviewed component/background records, optional reviewed background-subtraction overlays, and traceable calibration/processing parameters.",
            purpose="xps_analysis_report",
            style_profile=NATURE_LIKE_STYLE_PROFILE,
            source_data_refs=[
                value
                for value in [
                    str(processed_csv.relative_to(root)),
                    str(peaks_csv.relative_to(root)),
                    str(components_csv.relative_to(root)),
                    background_ref,
                    background_subtraction_ref,
                ]
                if value
            ],
        )
    return result_metadata
