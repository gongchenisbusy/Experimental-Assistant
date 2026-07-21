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
    source_data_entry,
    style_axis,
    styled_subplots,
)
from ea.provenance import write_provenance_entry
from ea.report_messages import ensure_interpretation_message_contract
from ea.raman.service import _read_spectrum
from ea.raw_import import assert_not_raw_output_path
from ea.review import require_confirmed_review
from ea.schema import ThermalAnalysisProcessingResult
from ea.schema.models import EARecord
from ea.standards import infer_project_slug
from ea.storage.files import read_yaml, write_yaml
from ea.storage.ids import next_id, next_standard_id


class ThermalAnalysisProcessingError(RuntimeError):
    """Raised when thermal analysis processing violates review or data boundaries."""


@dataclass(frozen=True)
class ThermalAnalysisInspection:
    path: Path
    file_kind: str
    row_count: int
    columns: list[str]
    temperature_column_candidate: str | None
    signal_column_candidate: str | None
    temperature_unit_candidate: str
    signal_unit_candidate: str
    measurement_mode_candidate: str
    metadata: dict[str, Any]
    warnings: list[str]
    requires_user_confirmation: bool


@dataclass(frozen=True)
class ThermalAnalysisProcessingRequest:
    temperature_column: str
    signal_column: str
    temperature_unit: str
    signal_unit: str
    measurement_mode: str
    context_summary: str
    processing_parameters: dict[str, Any]
    column_review_ref: str
    context_review_ref: str
    parameter_review_ref: str


THERMAL_FEATURE_COLUMNS = [
    "event_id",
    "event_type",
    "temperature_C",
    "signal_value",
    "mass_percent",
    "mass_derivative_percent_per_C",
    "heat_flow",
    "dtg_signal",
    "prominence",
    "method",
    "assignment_confidence",
    "assignment_source",
    "notes",
]


THERMAL_TRANSITION_COLUMNS = [
    "transition_id",
    "transition_type",
    "label",
    "status",
    "window_start_C",
    "window_end_C",
    "estimated_temperature_C",
    "metric",
    "signal_value",
    "area_signal_C",
    "step_delta",
    "point_count",
    "method",
    "assignment_confidence",
    "assignment_source",
    "notes",
]


def default_thermal_processing_parameters() -> dict[str, Any]:
    return {
        "smoothing": {
            "enabled": False,
            "method": "savitzky_golay",
            "window_length": 9,
            "polyorder": 2,
        },
        "derivative": {
            "enabled": True,
            "method": "numpy_gradient",
            "source": "ea.thermal.derivative:v0.2",
        },
        "feature_detection": {
            "enabled": True,
            "method": "scipy_find_peaks",
            "prominence": "auto",
            "distance": "auto",
            "max_features": 12,
            "source": "ea.thermal.feature_detection:v0.2",
        },
        "threshold_summary": {
            "enabled": True,
            "method": "mass_loss_fraction",
            "fractions": [0.05, 0.10],
            "source": "ea.thermal.threshold_summary:v0.2",
        },
        "baseline_correction": {
            "enabled": False,
            "method": "linear_two_point",
            "source": "ea.thermal.baseline_correction:v0.2",
            "anchor_strategy": "trace_edges",
            "anchor_temperatures_C": [],
        },
        "transition_analysis": {
            "enabled": False,
            "method": "reviewed_window_screening",
            "source": "ea.thermal.transition_analysis:v0.2",
            "transitions": [],
        },
        "transition_assignment": {
            "enabled": False,
            "method": "user_confirmed_transition_assignments",
            "source": "ea.thermal.transition_assignment:v0.2",
            "assignments": [],
        },
        "context_record": {
            "enabled": False,
            "method": "reviewed_metadata_record",
            "source": "ea.thermal.context_record:v0.2",
            "dsc_sign_convention": {},
            "baseline_reference": {},
            "sample_context": {},
            "atmosphere_program": {},
            "correction_notes": [],
        },
    }


def _merge_parameters(parameters: dict[str, Any] | None) -> dict[str, Any]:
    merged = default_thermal_processing_parameters()
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


def _as_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(number):
        return None
    return number


def _metadata_text(columns: list[str], metadata: dict[str, Any], path: Path) -> str:
    parts = list(columns) + [path.as_posix()]
    parts.extend(str(value) for value in metadata.values())
    return " ".join(parts).lower()


def _mode_candidate(text: str) -> str:
    if "dtg" in text or "derivative thermograv" in text:
        return "dtg"
    if "dsc" in text or "heat flow" in text or "heatflow" in text:
        return "dsc"
    if (
        "tga" in text
        or "tg " in f" {text} "
        or "thermograv" in text
        or "mass" in text
        or "weight" in text
    ):
        return "tga"
    return "unknown"


def _temperature_unit_candidate(text: str, x_min: float, x_max: float) -> str:
    if "temperature_k" in text or " kelvin" in text or " k " in f" {text} ":
        return "K"
    if (
        "temperature_c" in text
        or "degc" in text
        or " c " in f" {text} "
        or "celsius" in text
    ):
        return "C"
    if -100.0 <= x_min <= 1500.0 and -100.0 <= x_max <= 1600.0:
        return "C"
    return "unknown"


def _signal_unit_candidate(text: str) -> str:
    if "mw/mg" in text:
        return "mW/mg"
    if "w/g" in text:
        return "W/g"
    if "mw" in text or "heat flow" in text or "heatflow" in text:
        return "mW"
    if "%" in text or "percent" in text or "mass_pct" in text or "mass_percent" in text:
        return "%"
    if "mg" in text:
        return "mg"
    return "unknown"


def inspect_thermal_file(path: Path) -> ThermalAnalysisInspection:
    frame, metadata = _read_spectrum(path)
    columns = [str(column) for column in frame.columns]
    if frame.empty or len(columns) < 2:
        raise ThermalAnalysisProcessingError(
            f"No two-column numeric thermal data found in {path}"
        )
    x_values = pd.to_numeric(frame.iloc[:, 0], errors="coerce").dropna()
    y_values = pd.to_numeric(frame.iloc[:, 1], errors="coerce").dropna()
    x_min = float(x_values.min())
    x_max = float(x_values.max())
    y_min = float(y_values.min())
    y_max = float(y_values.max())
    text = _metadata_text(columns, metadata, path)
    mode = _mode_candidate(text)
    temperature_unit = _temperature_unit_candidate(text, x_min, x_max)
    signal_unit = _signal_unit_candidate(text)
    looks_like_thermal = (
        mode != "unknown"
        or "thermal" in text
        or ("temperature" in text and ("mass" in text or "heat" in text))
    )
    file_kind = "thermal_analysis" if looks_like_thermal else "unknown"
    warnings: list[str] = []
    if file_kind == "unknown":
        warnings.append("thermal_file_kind_unknown")
    if temperature_unit == "unknown":
        warnings.append("thermal_temperature_unit_unknown")
    if signal_unit == "unknown":
        warnings.append("thermal_signal_unit_unknown")
    return ThermalAnalysisInspection(
        path=path,
        file_kind=file_kind,
        row_count=len(frame),
        columns=columns,
        temperature_column_candidate=columns[0],
        signal_column_candidate=columns[1],
        temperature_unit_candidate=temperature_unit,
        signal_unit_candidate=signal_unit,
        measurement_mode_candidate=mode,
        metadata={
            **metadata,
            "x_min": x_min,
            "x_max": x_max,
            "y_min": y_min,
            "y_max": y_max,
        },
        warnings=warnings,
        requires_user_confirmation=True,
    )


def _confirmed_frame(
    path: Path, request: ThermalAnalysisProcessingRequest
) -> pd.DataFrame:
    frame, _ = _read_spectrum(path)
    frame.columns = [str(column) for column in frame.columns]
    if (
        request.temperature_column not in frame.columns
        or request.signal_column not in frame.columns
    ):
        raise ThermalAnalysisProcessingError(
            "Confirmed temperature/signal columns are not present in the raw file"
        )
    if request.temperature_unit not in {"C", "K", "unknown"}:
        raise ThermalAnalysisProcessingError(
            "Thermal temperature_unit must be user-confirmed as C, K, or unknown"
        )
    if request.signal_unit not in {"%", "mg", "mW", "W/g", "mW/mg", "unknown"}:
        raise ThermalAnalysisProcessingError(
            "Thermal signal_unit must be %, mg, mW, W/g, mW/mg, or unknown"
        )
    if request.measurement_mode not in {"tga", "dsc", "dtg", "unknown"}:
        raise ThermalAnalysisProcessingError(
            "Thermal measurement_mode must be tga, dsc, dtg, or unknown"
        )
    data = frame[[request.temperature_column, request.signal_column]].copy()
    data.columns = ["temperature_raw", "signal_raw"]
    data["temperature_raw"] = pd.to_numeric(data["temperature_raw"], errors="coerce")
    data["signal_raw"] = pd.to_numeric(data["signal_raw"], errors="coerce")
    data = data.dropna().reset_index(drop=True)
    if data.empty:
        raise ThermalAnalysisProcessingError(
            "Confirmed thermal columns contain no numeric data"
        )
    if request.temperature_unit == "K":
        data["temperature_C"] = data["temperature_raw"] - 273.15
    else:
        data["temperature_C"] = data["temperature_raw"]
    return data


def _nearest_signal_anchor(
    temperature: np.ndarray, signal: np.ndarray, requested_temperature: float | None
) -> dict[str, Any]:
    if requested_temperature is None:
        index = 0
    else:
        index = int(np.nanargmin(np.abs(temperature - requested_temperature)))
    return {
        "requested_temperature_C": requested_temperature,
        "actual_temperature_C": float(temperature[index]),
        "signal_value": float(signal[index]),
        "row_index": index,
    }


def _baseline_anchors(
    processed: pd.DataFrame, signal: np.ndarray, params: dict[str, Any]
) -> tuple[list[dict[str, Any]], str, list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    temperature = processed["temperature_C"].to_numpy(dtype=float)
    raw_anchors = params.get("anchor_temperatures_C", [])
    anchors: list[dict[str, Any]]
    strategy = str(params.get("anchor_strategy") or "trace_edges")
    if isinstance(raw_anchors, list | tuple) and len(raw_anchors) >= 2:
        numeric: list[float] = []
        for value in raw_anchors:
            coerced = _as_float(value)
            if coerced is not None:
                numeric.append(coerced)
        if len(numeric) >= 2:
            numeric = sorted(numeric)
            if len(numeric) > 2:
                warnings.append(
                    _warning(
                        "thermal_baseline_extra_anchors_ignored",
                        "Thermal linear baseline correction used the first and last reviewed anchor temperatures.",
                        severity="low",
                        anchor_count=len(numeric),
                    )
                )
            anchors = [
                _nearest_signal_anchor(temperature, signal, numeric[0]),
                _nearest_signal_anchor(temperature, signal, numeric[-1]),
            ]
            return anchors, "reviewed_anchor_temperatures_C", warnings
        warnings.append(
            _warning(
                "thermal_baseline_anchor_temperatures_invalid",
                "Thermal baseline anchor temperatures were invalid; trace-edge anchors were used instead.",
                severity="medium",
            )
        )
    elif raw_anchors:
        warnings.append(
            _warning(
                "thermal_baseline_anchor_temperatures_ignored",
                "Thermal baseline anchor temperatures were ignored because at least two numeric values are required.",
                severity="medium",
            )
        )
    anchors = [
        _nearest_signal_anchor(temperature, signal, None),
        {
            "requested_temperature_C": None,
            "actual_temperature_C": float(temperature[-1]),
            "signal_value": float(signal[-1]),
            "row_index": int(len(signal) - 1),
        },
    ]
    return anchors, strategy, warnings


def _apply_baseline_correction(
    processed: pd.DataFrame,
    signal: np.ndarray,
    request: ThermalAnalysisProcessingRequest,
    parameters: dict[str, Any],
) -> tuple[np.ndarray, dict[str, Any] | None, list[dict[str, Any]]]:
    params = parameters.get("baseline_correction", {})
    if not isinstance(params, dict) or not params.get("enabled", False):
        return signal, None, []
    source = str(params.get("source") or "ea.thermal.baseline_correction:v0.2")
    method = str(params.get("method") or "linear_two_point")
    warnings: list[dict[str, Any]] = []
    record: dict[str, Any] = {
        "enabled": True,
        "method": method,
        "assignment_source": source,
        "applied": False,
        "measurement_mode": request.measurement_mode,
        "confidence": "insufficient",
        "boundary": (
            "Thermal baseline correction is a numeric processing step only; it does not assign Tg/Tm/Tc, "
            "fit kinetic models, rank thermal stability, or prove decomposition, melting, crystallization, or mechanism claims."
        ),
    }
    if method != "linear_two_point":
        warning = _warning(
            "thermal_baseline_method_unsupported",
            "Thermal baseline correction method is not supported by Experimental Assistant v1.1.0.",
            severity="medium",
            method=method,
        )
        warnings.append(warning)
        record.update({"status": "skipped_unsupported_method", "warnings": warnings})
        return signal, record, warnings
    if request.measurement_mode not in {"dsc", "dtg"}:
        warning = _warning(
            "thermal_baseline_mode_unsupported",
            "Thermal baseline correction was skipped because it is currently supported only for reviewed DSC/DTG traces.",
            severity="medium",
            measurement_mode=request.measurement_mode,
        )
        warnings.append(warning)
        record.update({"status": "skipped_unsupported_mode", "warnings": warnings})
        return signal, record, warnings
    if len(signal) < 2:
        warning = _warning(
            "thermal_baseline_insufficient_points",
            "Thermal baseline correction requires at least two numeric data points.",
            severity="medium",
        )
        warnings.append(warning)
        record.update({"status": "skipped_insufficient_points", "warnings": warnings})
        return signal, record, warnings

    anchors, anchor_strategy, anchor_warnings = _baseline_anchors(
        processed, signal, params
    )
    warnings.extend(anchor_warnings)
    left, right = anchors[0], anchors[-1]
    x1 = float(left["actual_temperature_C"])
    x2 = float(right["actual_temperature_C"])
    if abs(x2 - x1) < 1e-12:
        warning = _warning(
            "thermal_baseline_degenerate_anchors",
            "Thermal baseline correction was skipped because reviewed anchors collapse to the same temperature.",
            severity="medium",
            anchor_temperature_C=x1,
        )
        warnings.append(warning)
        record.update(
            {
                "status": "skipped_degenerate_anchors",
                "anchor_points": anchors,
                "warnings": warnings,
            }
        )
        return signal, record, warnings

    temperature = processed["temperature_C"].to_numpy(dtype=float)
    baseline = np.interp(
        temperature,
        [x1, x2],
        [float(left["signal_value"]), float(right["signal_value"])],
    )
    corrected = signal - baseline
    processed["baseline_estimate"] = baseline
    processed["baseline_corrected_signal"] = corrected
    record.update(
        {
            "status": "applied_linear_baseline",
            "applied": True,
            "confidence": "medium",
            "anchor_strategy": anchor_strategy,
            "anchor_points": anchors,
            "baseline_column": "baseline_estimate",
            "corrected_column": "baseline_corrected_signal",
            "warnings": warnings,
        }
    )
    return corrected, record, warnings


def _apply_processing(
    data: pd.DataFrame,
    request: ThermalAnalysisProcessingRequest,
    parameters: dict[str, Any],
) -> tuple[pd.DataFrame, list[dict[str, Any]], dict[str, Any] | None]:
    processed = data.copy()
    warnings: list[dict[str, Any]] = []
    signal = processed["signal_raw"].to_numpy(dtype=float)
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
            warnings.append(
                _warning(
                    "thermal_smoothing_applied",
                    "Savitzky-Golay smoothing was applied before thermal feature detection.",
                    window_length=window_length,
                    polyorder=polyorder,
                )
            )
        if adjusted:
            warnings.append(
                _warning(
                    "thermal_smoothing_parameter_adjusted",
                    "Invalid Savitzky-Golay parameters were adjusted for thermal processing.",
                    severity="medium",
                    window_length=window_length,
                    polyorder=polyorder,
                )
            )
    signal, baseline_record, baseline_warnings = _apply_baseline_correction(
        processed, signal, request, parameters
    )
    warnings.extend(baseline_warnings)
    processed["processed_signal"] = signal
    if request.measurement_mode == "tga" or (
        request.measurement_mode == "unknown" and request.signal_unit in {"%", "mg"}
    ):
        if request.signal_unit == "%":
            mass_percent = signal
        elif request.signal_unit == "mg" and abs(float(signal[0])) > 1e-12:
            mass_percent = signal / float(signal[0]) * 100.0
        else:
            mass_percent = signal
        processed["processed_mass_percent"] = mass_percent
        if (
            parameters.get("derivative", {}).get("enabled", True)
            and len(processed) >= 3
        ):
            temperature = processed["temperature_C"].to_numpy(dtype=float)
            processed["mass_derivative_percent_per_C"] = np.gradient(
                mass_percent, temperature
            )
    elif request.measurement_mode == "dtg":
        processed["processed_dtg_signal"] = signal
    else:
        processed["processed_heat_flow"] = signal
    return processed, warnings, baseline_record


def _feature_row(
    event_id: str,
    event_type: str,
    row: pd.Series,
    *,
    value_column: str,
    prominence: float | None,
    source: str,
    method: str,
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "event_type": event_type,
        "temperature_C": float(row["temperature_C"]),
        "signal_value": _as_float(row.get(value_column)),
        "mass_percent": _as_float(row.get("processed_mass_percent")),
        "mass_derivative_percent_per_C": _as_float(
            row.get("mass_derivative_percent_per_C")
        ),
        "heat_flow": _as_float(row.get("processed_heat_flow")),
        "dtg_signal": _as_float(row.get("processed_dtg_signal")),
        "prominence": float(prominence) if prominence is not None else None,
        "method": method,
        "assignment_confidence": "low",
        "assignment_source": source,
        "notes": "automatic thermal-analysis summary feature; requires temperature program, atmosphere, baseline, replicates, and user review",
    }


def _auto_prominence(values: np.ndarray) -> float:
    return max(float(np.nanmax(values) - np.nanmin(values)) * 0.08, 0.001)


def _detect_features(
    processed: pd.DataFrame,
    parameters: dict[str, Any],
    request: ThermalAnalysisProcessingRequest,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    feature_params = parameters.get("feature_detection", {})
    source = str(feature_params.get("source") or "ea.thermal.feature_detection:v0.2")
    if not feature_params.get("enabled", True) or len(processed) < 3:
        return pd.DataFrame(rows, columns=THERMAL_FEATURE_COLUMNS)
    max_features, _ = _coerce_int(feature_params.get("max_features"), 12, minimum=1)
    distance = feature_params.get("distance", "auto")
    if distance == "auto":
        distance = max(len(processed) // 120, 1)

    ranked: list[tuple[int, float, str, str]] = []
    if "mass_derivative_percent_per_C" in processed.columns:
        derivative = processed["mass_derivative_percent_per_C"].to_numpy(dtype=float)
        prominence = feature_params.get("prominence", "auto")
        if prominence == "auto":
            prominence = _auto_prominence(derivative)
        indices, props = find_peaks(
            -derivative, prominence=prominence, distance=distance
        )
        ranked.extend(
            (
                int(index),
                float(props["prominences"][offset]),
                "mass_loss_rate_peak",
                "mass_derivative_percent_per_C",
            )
            for offset, index in enumerate(indices)
        )
    elif "processed_heat_flow" in processed.columns:
        heat_flow = processed["processed_heat_flow"].to_numpy(dtype=float)
        prominence = feature_params.get("prominence", "auto")
        if prominence == "auto":
            prominence = _auto_prominence(heat_flow)
        positive, positive_props = find_peaks(
            heat_flow, prominence=prominence, distance=distance
        )
        negative, negative_props = find_peaks(
            -heat_flow, prominence=prominence, distance=distance
        )
        ranked.extend(
            (
                int(index),
                float(positive_props["prominences"][offset]),
                "heat_flow_positive_peak",
                "processed_heat_flow",
            )
            for offset, index in enumerate(positive)
        )
        ranked.extend(
            (
                int(index),
                float(negative_props["prominences"][offset]),
                "heat_flow_negative_peak",
                "processed_heat_flow",
            )
            for offset, index in enumerate(negative)
        )
    elif "processed_dtg_signal" in processed.columns:
        dtg = processed["processed_dtg_signal"].to_numpy(dtype=float)
        prominence = feature_params.get("prominence", "auto")
        if prominence == "auto":
            prominence = _auto_prominence(dtg)
        positive, positive_props = find_peaks(
            dtg, prominence=prominence, distance=distance
        )
        negative, negative_props = find_peaks(
            -dtg, prominence=prominence, distance=distance
        )
        ranked.extend(
            (
                int(index),
                float(positive_props["prominences"][offset]),
                "dtg_positive_peak",
                "processed_dtg_signal",
            )
            for offset, index in enumerate(positive)
        )
        ranked.extend(
            (
                int(index),
                float(negative_props["prominences"][offset]),
                "dtg_negative_peak",
                "processed_dtg_signal",
            )
            for offset, index in enumerate(negative)
        )

    ranked = sorted(ranked, key=lambda item: item[1], reverse=True)[:max_features]
    ranked.sort(key=lambda item: float(processed.iloc[item[0]]["temperature_C"]))
    for number, (index, prominence, event_type, column) in enumerate(ranked, start=1):
        rows.append(
            _feature_row(
                f"thermal-event-{number:03d}",
                event_type,
                processed.iloc[index],
                value_column=column,
                prominence=prominence,
                source=source,
                method="scipy_find_peaks",
            )
        )

    threshold_params = parameters.get("threshold_summary", {})
    if (
        threshold_params.get("enabled", True)
        and "processed_mass_percent" in processed.columns
    ):
        mass = processed["processed_mass_percent"].to_numpy(dtype=float)
        start = float(mass[0])
        threshold_source = str(
            threshold_params.get("source") or "ea.thermal.threshold_summary:v0.2"
        )
        for fraction in threshold_params.get("fractions", [0.05, 0.10]):
            try:
                fraction_float = float(fraction)
            except (TypeError, ValueError):
                continue
            target = start - abs(start) * fraction_float
            candidates = np.where(mass <= target)[0]
            if candidates.size:
                percent = int(round(fraction_float * 100))
                rows.append(
                    _feature_row(
                        f"thermal-mass-loss-{percent:02d}",
                        f"mass_loss_{percent}_percent_threshold",
                        processed.iloc[int(candidates[0])],
                        value_column="processed_mass_percent",
                        prominence=None,
                        source=threshold_source,
                        method="mass_loss_fraction",
                    )
                )
    return pd.DataFrame(rows, columns=THERMAL_FEATURE_COLUMNS)


_TG_TYPES = {"tg", "glass_transition", "glass-transition", "glass transition"}
_PEAK_POSITIVE_DIRECTIONS = {
    "peak_positive",
    "positive",
    "up",
    "exotherm_up",
    "max",
    "maximum",
}
_PEAK_NEGATIVE_DIRECTIONS = {
    "peak_negative",
    "negative",
    "down",
    "endotherm_down",
    "min",
    "minimum",
}


def _normalized_transition_type(value: Any) -> str:
    text = str(value or "other").strip().lower().replace(" ", "_").replace("-", "_")
    if text in {"tm", "melting", "melting_peak"}:
        return "Tm"
    if text in {
        "tc",
        "crystallization",
        "crystallisation",
        "crystallization_peak",
        "crystallisation_peak",
    }:
        return "Tc"
    if text in {"tg", "glass_transition", "glass_transition_midpoint"}:
        return "Tg"
    return str(value or "other").strip() or "other"


def _transition_window(spec: dict[str, Any]) -> tuple[float | None, float | None]:
    raw_window = spec.get("temperature_window_C")
    if isinstance(raw_window, list | tuple) and len(raw_window) >= 2:
        low = _as_float(raw_window[0])
        high = _as_float(raw_window[1])
    else:
        low = _as_float(spec.get("window_start_C"))
        high = _as_float(spec.get("window_end_C"))
    if low is None or high is None:
        return None, None
    return (min(low, high), max(low, high))


def _transition_row(
    *,
    transition_id: str,
    transition_type: str,
    label: str,
    status: str,
    window_start: float | None,
    window_end: float | None,
    estimated_temperature: float | None,
    metric: str,
    signal_value: float | None,
    area: float | None,
    step_delta: float | None,
    point_count: int,
    method: str,
    confidence: str,
    source: str,
    notes: str,
) -> dict[str, Any]:
    return {
        "transition_id": transition_id,
        "transition_type": transition_type,
        "label": label,
        "status": status,
        "window_start_C": window_start,
        "window_end_C": window_end,
        "estimated_temperature_C": estimated_temperature,
        "metric": metric,
        "signal_value": signal_value,
        "area_signal_C": area,
        "step_delta": step_delta,
        "point_count": point_count,
        "method": method,
        "assignment_confidence": confidence,
        "assignment_source": source,
        "notes": notes,
    }


def _transition_candidate(
    spec: dict[str, Any],
    processed: pd.DataFrame,
    *,
    number: int,
    method: str,
    source: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    transition_id = str(spec.get("transition_id") or f"thermal-transition-{number:03d}")
    transition_type = _normalized_transition_type(
        spec.get("transition_type") or spec.get("type")
    )
    label = str(spec.get("label") or transition_type)
    window_start, window_end = _transition_window(spec)
    if window_start is None or window_end is None:
        return (
            _transition_row(
                transition_id=transition_id,
                transition_type=transition_type,
                label=label,
                status="skipped_invalid_window",
                window_start=window_start,
                window_end=window_end,
                estimated_temperature=None,
                metric="invalid_window",
                signal_value=None,
                area=None,
                step_delta=None,
                point_count=0,
                method=method,
                confidence="insufficient",
                source=source,
                notes="transition window was missing or not numeric; no candidate metric was extracted",
            ),
            _warning(
                "thermal_transition_window_invalid",
                "Thermal transition window was ignored because it was missing or not numeric.",
                severity="medium",
                transition_id=transition_id,
            ),
        )

    window = processed[
        (processed["temperature_C"] >= window_start)
        & (processed["temperature_C"] <= window_end)
    ].copy()
    if len(window) < 3:
        return (
            _transition_row(
                transition_id=transition_id,
                transition_type=transition_type,
                label=label,
                status="skipped_insufficient_points",
                window_start=window_start,
                window_end=window_end,
                estimated_temperature=None,
                metric="insufficient_points",
                signal_value=None,
                area=None,
                step_delta=None,
                point_count=int(len(window)),
                method=method,
                confidence="insufficient",
                source=source,
                notes="transition window contains fewer than three points; no candidate metric was extracted",
            ),
            _warning(
                "thermal_transition_window_too_sparse",
                "Thermal transition window contains fewer than three points.",
                severity="medium",
                transition_id=transition_id,
                point_count=int(len(window)),
            ),
        )

    x = window["temperature_C"].to_numpy(dtype=float)
    y = window["processed_signal"].to_numpy(dtype=float)
    direction = (
        str(spec.get("signal_direction") or "auto")
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
    )
    transition_key = transition_type.strip().lower().replace(" ", "_").replace("-", "_")
    if transition_key in _TG_TYPES:
        derivative = np.gradient(y, x)
        if direction in _PEAK_POSITIVE_DIRECTIONS:
            local_index = int(np.nanargmax(derivative))
            metric = "derivative_maximum"
        elif direction in _PEAK_NEGATIVE_DIRECTIONS:
            local_index = int(np.nanargmin(derivative))
            metric = "derivative_minimum"
        else:
            local_index = int(np.nanargmax(np.abs(derivative)))
            metric = "derivative_absolute_extremum"
    elif direction in _PEAK_POSITIVE_DIRECTIONS:
        local_index = int(np.nanargmax(y))
        metric = "signal_maximum"
    elif direction in _PEAK_NEGATIVE_DIRECTIONS:
        local_index = int(np.nanargmin(y))
        metric = "signal_minimum"
    else:
        edge_baseline = np.interp(
            x, [float(x[0]), float(x[-1])], [float(y[0]), float(y[-1])]
        )
        local_index = int(np.nanargmax(np.abs(y - edge_baseline)))
        metric = "signal_deviation_extremum"
    area = (
        float(np.trapezoid(y, x)) if hasattr(np, "trapezoid") else float(np.trapz(y, x))
    )
    step_delta = float(y[-1] - y[0])
    return (
        _transition_row(
            transition_id=transition_id,
            transition_type=transition_type,
            label=label,
            status="candidate_extracted",
            window_start=window_start,
            window_end=window_end,
            estimated_temperature=float(x[local_index]),
            metric=metric,
            signal_value=float(y[local_index]),
            area=area,
            step_delta=step_delta,
            point_count=int(len(window)),
            method=method,
            confidence="medium",
            source=source,
            notes="reviewed-window thermal transition candidate; requires user interpretation, replicates, method context, and references before formal assignment",
        ),
        None,
    )


def _analyze_transitions(
    processed: pd.DataFrame,
    parameters: dict[str, Any],
    request: ThermalAnalysisProcessingRequest,
) -> tuple[pd.DataFrame, dict[str, Any] | None, list[dict[str, Any]]]:
    params = parameters.get("transition_analysis", {})
    if not isinstance(params, dict) or not params.get("enabled", False):
        return pd.DataFrame(columns=THERMAL_TRANSITION_COLUMNS), None, []
    warnings: list[dict[str, Any]] = []
    method = str(params.get("method") or "reviewed_window_screening")
    source = str(params.get("source") or "ea.thermal.transition_analysis:v0.2")
    record: dict[str, Any] = {
        "enabled": True,
        "method": method,
        "assignment_source": source,
        "measurement_mode": request.measurement_mode,
        "confidence": "insufficient",
        "transition_count": 0,
        "boundary": (
            "Thermal transition screening extracts candidate metrics from user-reviewed windows only; it does not make formal Tg/Tm/Tc assignments, "
            "fit kinetic models, rank thermal stability, or prove decomposition, melting, crystallization, or mechanism claims."
        ),
    }
    if method != "reviewed_window_screening":
        warning = _warning(
            "thermal_transition_method_unsupported",
            "Thermal transition analysis method is not supported by Experimental Assistant v1.1.0.",
            severity="medium",
            method=method,
        )
        warnings.append(warning)
        record.update({"status": "skipped_unsupported_method", "warnings": warnings})
        return pd.DataFrame(columns=THERMAL_TRANSITION_COLUMNS), record, warnings
    if request.measurement_mode != "dsc":
        warning = _warning(
            "thermal_transition_mode_unsupported",
            "Thermal transition screening was skipped because Tg/Tm/Tc-style windows are currently supported only for reviewed DSC traces.",
            severity="medium",
            measurement_mode=request.measurement_mode,
        )
        warnings.append(warning)
        record.update({"status": "skipped_unsupported_mode", "warnings": warnings})
        return pd.DataFrame(columns=THERMAL_TRANSITION_COLUMNS), record, warnings
    specs = params.get("transitions", [])
    if not isinstance(specs, list) or not specs:
        warning = _warning(
            "thermal_transition_windows_missing",
            "Thermal transition_analysis was enabled, but no reviewed transition windows were supplied.",
            severity="medium",
        )
        warnings.append(warning)
        record.update(
            {"status": "enabled_without_reviewed_windows", "warnings": warnings}
        )
        return pd.DataFrame(columns=THERMAL_TRANSITION_COLUMNS), record, warnings

    rows: list[dict[str, Any]] = []
    for number, spec in enumerate(specs, start=1):
        if not isinstance(spec, dict):
            warning = _warning(
                "thermal_transition_spec_ignored",
                "A thermal transition spec was ignored because it was not a mapping.",
                severity="medium",
                transition_number=number,
            )
            warnings.append(warning)
            continue
        row, warning = _transition_candidate(
            spec, processed, number=number, method=method, source=source
        )
        rows.append(row)
        if warning:
            warnings.append(warning)
    table = pd.DataFrame(rows, columns=THERMAL_TRANSITION_COLUMNS)
    extracted = (
        int((table["status"] == "candidate_extracted").sum()) if not table.empty else 0
    )
    record.update(
        {
            "status": "reviewed_transition_candidates_recorded"
            if extracted
            else "no_transition_candidates_extracted",
            "transition_count": extracted,
            "confidence": "medium" if extracted else "insufficient",
            "warnings": warnings,
        }
    )
    return table, record, warnings


_THERMAL_CONTEXT_SECTIONS = (
    "dsc_sign_convention",
    "baseline_reference",
    "sample_context",
    "atmosphere_program",
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


def _coerce_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list | tuple):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _transition_candidate_lookup(
    transitions: pd.DataFrame,
) -> dict[str, dict[str, Any]]:
    if transitions.empty or "transition_id" not in transitions.columns:
        return {}
    candidates: dict[str, dict[str, Any]] = {}
    for _, row in transitions.iterrows():
        transition_id = str(row.get("transition_id") or "").strip()
        if not transition_id:
            continue
        candidates[transition_id] = {
            "transition_type": row.get("transition_type"),
            "estimated_temperature_C": row.get("estimated_temperature_C"),
            "metric": row.get("metric"),
            "status": row.get("status"),
        }
    return candidates


def _reviewed_transition_assignment(
    spec: dict[str, Any],
    *,
    number: int,
    source: str,
    candidates: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    assignment_id = str(
        spec.get("assignment_id") or f"thermal-transition-assignment-{number:03d}"
    )
    transition_id = str(
        spec.get("transition_id") or spec.get("candidate_transition_id") or ""
    ).strip()
    assigned_type = _normalized_transition_type(
        spec.get("assigned_transition_type")
        or spec.get("transition_type")
        or spec.get("type")
        or "other"
    )
    assigned_label = str(
        spec.get("assigned_label") or spec.get("label") or assigned_type
    )
    confidence = (
        str(spec.get("confidence") or spec.get("assignment_confidence") or "low")
        .strip()
        .lower()
    )
    if confidence not in {"high", "medium", "low", "insufficient"}:
        warnings.append(
            _warning(
                "thermal_transition_assignment_confidence_normalized",
                "Thermal transition assignment confidence was not one of high/medium/low/insufficient and was normalized to low.",
                severity="low",
                assignment_id=assignment_id,
                supplied_confidence=confidence,
            )
        )
        confidence = "low"
    candidate = candidates.get(transition_id) if transition_id else None
    candidate_temperature = _as_float(spec.get("candidate_temperature_C"))
    candidate_metric = str(spec.get("candidate_metric") or "")
    candidate_link_status = "not_linked"
    if transition_id:
        if candidate:
            candidate_link_status = "linked_to_screening_candidate"
            candidate_temperature = (
                candidate_temperature
                if candidate_temperature is not None
                else _as_float(candidate.get("estimated_temperature_C"))
            )
            candidate_metric = candidate_metric or str(candidate.get("metric") or "")
        else:
            candidate_link_status = "candidate_not_found"
            warnings.append(
                _warning(
                    "thermal_transition_assignment_candidate_missing",
                    "A user-confirmed transition assignment refers to a transition_id that was not found in the current screening table.",
                    severity="medium",
                    assignment_id=assignment_id,
                    transition_id=transition_id,
                )
            )
    assigned_temperature = _as_float(
        spec.get("assigned_temperature_C") or spec.get("temperature_C")
    )
    if assigned_temperature is None:
        assigned_temperature = candidate_temperature
    status = "user_confirmed_assignment_recorded"
    if not transition_id and not _has_context_payload(assigned_label):
        status = "skipped_missing_assignment_target"
        warnings.append(
            _warning(
                "thermal_transition_assignment_missing_target",
                "A transition assignment was skipped because no transition_id or label was supplied.",
                severity="medium",
                assignment_id=assignment_id,
            )
        )
    return (
        {
            "assignment_id": assignment_id,
            "transition_id": transition_id,
            "assigned_transition_type": assigned_type,
            "assigned_label": assigned_label,
            "assigned_temperature_C": assigned_temperature,
            "candidate_temperature_C": candidate_temperature,
            "candidate_metric": candidate_metric,
            "candidate_link_status": candidate_link_status,
            "review_status": str(spec.get("review_status") or "user_confirmed"),
            "confidence": confidence,
            "evidence_refs": _coerce_string_list(
                spec.get("evidence_refs") or spec.get("evidence")
            ),
            "reference_ids": _coerce_string_list(spec.get("reference_ids")),
            "reviewer_notes": _coerce_string_list(
                spec.get("reviewer_notes") or spec.get("notes")
            ),
            "caveats": _coerce_string_list(spec.get("caveats")),
            "status": status,
            "assignment_source": source,
            "boundary": (
                "This thermal transition assignment is a user-confirmed interpretation record linked to reviewed evidence; "
                "it is not an automatic transition assignment, kinetic fit, thermal-stability ranking, or mechanism proof."
            ),
        },
        warnings,
    )


def _record_transition_assignments(
    parameters: dict[str, Any],
    request: ThermalAnalysisProcessingRequest,
    transitions: pd.DataFrame,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    params = parameters.get("transition_assignment", {})
    if not isinstance(params, dict) or not params.get("enabled", False):
        return None, []
    warnings: list[dict[str, Any]] = []
    method = str(params.get("method") or "user_confirmed_transition_assignments")
    source = str(params.get("source") or "ea.thermal.transition_assignment:v0.2")
    record: dict[str, Any] = {
        "enabled": True,
        "method": method,
        "assignment_source": source,
        "measurement_mode": request.measurement_mode,
        "confidence": "insufficient",
        "assignment_count": 0,
        "assignments": [],
        "boundary": (
            "Thermal transition assignment records store user-confirmed interpretation and provenance only. EA does not infer formal Tg/Tm/Tc "
            "labels automatically from screening metrics, fit kinetic models, rank thermal stability, or prove decomposition, melting, crystallization, or mechanism claims."
        ),
    }
    if method != "user_confirmed_transition_assignments":
        warning = _warning(
            "thermal_transition_assignment_method_unsupported",
            "Thermal transition assignment method is not supported by Experimental Assistant v1.1.0.",
            severity="medium",
            method=method,
        )
        warnings.append(warning)
        record.update({"status": "skipped_unsupported_method", "warnings": warnings})
        return record, warnings
    if request.measurement_mode != "dsc":
        warning = _warning(
            "thermal_transition_assignment_mode_unsupported",
            "Thermal transition assignments are currently supported only for reviewed DSC traces.",
            severity="medium",
            measurement_mode=request.measurement_mode,
        )
        warnings.append(warning)
        record.update({"status": "skipped_unsupported_mode", "warnings": warnings})
        return record, warnings
    specs = params.get("assignments", [])
    if not isinstance(specs, list) or not specs:
        warning = _warning(
            "thermal_transition_assignments_missing",
            "transition_assignment was enabled, but no reviewed assignments were supplied.",
            severity="medium",
        )
        warnings.append(warning)
        record.update(
            {"status": "enabled_without_reviewed_assignments", "warnings": warnings}
        )
        return record, warnings

    candidates = _transition_candidate_lookup(transitions)
    assignments: list[dict[str, Any]] = []
    for number, spec in enumerate(specs, start=1):
        if not isinstance(spec, dict):
            warnings.append(
                _warning(
                    "thermal_transition_assignment_ignored",
                    "A transition assignment was ignored because it was not a mapping.",
                    severity="medium",
                    assignment_number=number,
                )
            )
            continue
        assignment, assignment_warnings = _reviewed_transition_assignment(
            spec, number=number, source=source, candidates=candidates
        )
        assignments.append(assignment)
        warnings.extend(assignment_warnings)
    recorded = [
        item
        for item in assignments
        if item.get("status") == "user_confirmed_assignment_recorded"
    ]
    reference_ids = sorted(
        {
            reference_id
            for item in recorded
            for reference_id in item.get("reference_ids", [])
        }
    )
    record.update(
        {
            "status": "reviewed_transition_assignments_recorded"
            if recorded
            else "no_transition_assignments_recorded",
            "assignment_count": len(recorded),
            "assignments": assignments,
            "reference_ids": reference_ids,
            "confidence": "low" if recorded else "insufficient",
            "warnings": warnings,
        }
    )
    return record, warnings


def _context_section(
    params: dict[str, Any], name: str
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    value = params.get(name, {})
    if isinstance(value, dict):
        return deepcopy(value), None
    return (
        {},
        _warning(
            "thermal_context_section_ignored",
            "A thermal context-record section was ignored because it was not a mapping.",
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
            "thermal_context_notes_ignored",
            "Thermal context notes were ignored because they were not a list or non-empty string.",
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
    for name in _THERMAL_CONTEXT_SECTIONS:
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
                "thermal_context_record_empty",
                "Thermal context_record was enabled, but no reviewed method/context metadata was supplied.",
                severity="medium",
            )
        )
    source = str(params.get("source") or "ea.thermal.context_record:v0.2")
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
            "boundary": (
                "Thermal context record is metadata/provenance only; no automatic DSC sign inversion, "
                "baseline/reference correction, Tg/Tm/Tc assignment, kinetic fitting, or thermal mechanism assignment was applied."
            ),
        },
        warnings,
    )


def _append_context_interpretation(
    analysis: dict[str, Any], context_record: dict[str, Any] | None
) -> dict[str, Any]:
    if not context_record:
        return analysis
    analysis["context_record"] = context_record
    if context_record.get("status") == "reviewed_context_recorded":
        fields = (
            ", ".join(
                str(value)
                for value in context_record.get("reviewed_context_fields", [])
            )
            or "thermal context"
        )
        analysis["possible_interpretations"].append(
            {
                "text": (
                    f"Reviewed thermal method/context metadata was recorded for {fields}. Use it to interpret screening events, "
                    "but do not treat the metadata record as an automatic DSC sign inversion, baseline correction, transition assignment, kinetic fit, or mechanism conclusion."
                ),
                "confidence": context_record.get("confidence", "low"),
                "evidence": ["context_record"],
                "assignment_source": context_record.get(
                    "assignment_source", "ea.thermal.context_record:v0.2"
                ),
            }
        )
    return analysis


def _append_baseline_interpretation(
    analysis: dict[str, Any], baseline_record: dict[str, Any] | None
) -> dict[str, Any]:
    if not baseline_record:
        return analysis
    analysis["baseline_correction"] = baseline_record
    if baseline_record.get("status") == "applied_linear_baseline":
        anchors = baseline_record.get("anchor_points") or []
        evidence = ["baseline_correction"]
        evidence.extend(
            f"{float(anchor['actual_temperature_C']):.1f}C"
            for anchor in anchors
            if isinstance(anchor, dict) and "actual_temperature_C" in anchor
        )
        analysis["possible_interpretations"].append(
            {
                "text": (
                    "Reviewed linear thermal baseline correction was applied before feature detection. Use the corrected trace for screening-event review, "
                    "but do not treat baseline correction as a standalone transition assignment, kinetic fit, stability ranking, or mechanism conclusion."
                ),
                "confidence": baseline_record.get("confidence", "medium"),
                "evidence": evidence,
                "assignment_source": baseline_record.get(
                    "assignment_source", "ea.thermal.baseline_correction:v0.2"
                ),
            }
        )
    return analysis


def _append_transition_interpretation(
    analysis: dict[str, Any], transition_record: dict[str, Any] | None
) -> dict[str, Any]:
    if not transition_record:
        return analysis
    analysis["transition_analysis"] = transition_record
    if transition_record.get("status") == "reviewed_transition_candidates_recorded":
        table_ref = transition_record.get("table_ref", "transition_table")
        analysis["possible_interpretations"].append(
            {
                "text": (
                    "Reviewed thermal transition windows were screened for candidate Tg/Tm/Tc-style metrics. Treat these as candidate metrics for user review, "
                    "not formal transition assignments or mechanism conclusions."
                ),
                "confidence": transition_record.get("confidence", "medium"),
                "evidence": ["transition_analysis", table_ref],
                "assignment_source": transition_record.get(
                    "assignment_source", "ea.thermal.transition_analysis:v0.2"
                ),
            }
        )
    return analysis


def _append_transition_assignment_interpretation(
    analysis: dict[str, Any], assignment_record: dict[str, Any] | None
) -> dict[str, Any]:
    if not assignment_record:
        return analysis
    analysis["transition_assignment"] = assignment_record
    if assignment_record.get("status") == "reviewed_transition_assignments_recorded":
        assignment_count = int(assignment_record.get("assignment_count") or 0)
        analysis["possible_interpretations"].append(
            {
                "text": (
                    f"User-confirmed thermal transition assignment records were saved for {assignment_count} reviewed transition(s). "
                    "Treat these records as reviewed interpretation with provenance, not as automatic transition assignment, kinetic fitting, stability ranking, or mechanism proof."
                ),
                "confidence": assignment_record.get("confidence", "low"),
                "evidence": ["transition_assignment", "transition_assignment_record"],
                "assignment_source": assignment_record.get(
                    "assignment_source", "ea.thermal.transition_assignment:v0.2"
                ),
            }
        )
    return analysis


def _summary(
    processed: pd.DataFrame,
    features: pd.DataFrame,
    request: ThermalAnalysisProcessingRequest,
    context_record: dict[str, Any] | None = None,
    baseline_record: dict[str, Any] | None = None,
    transition_record: dict[str, Any] | None = None,
    transition_assignment_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    temperature = processed["temperature_C"].to_numpy(dtype=float)
    signal = processed["processed_signal"].to_numpy(dtype=float)
    analysis: dict[str, Any] = {
        "measurement_mode": request.measurement_mode,
        "context_summary": request.context_summary,
        "feature_count": int(len(features)),
        "temperature_summary": {
            "min_temperature_C": float(np.nanmin(temperature)),
            "max_temperature_C": float(np.nanmax(temperature)),
        },
        "signal_summary": {
            "start_signal": float(signal[0]),
            "end_signal": float(signal[-1]),
            "min_signal": float(np.nanmin(signal)),
            "max_signal": float(np.nanmax(signal)),
            "signal_unit": request.signal_unit,
        },
        "possible_interpretations": [],
    }
    if "processed_mass_percent" in processed.columns:
        mass = processed["processed_mass_percent"].to_numpy(dtype=float)
        analysis["mass_summary"] = {
            "start_mass_percent": float(mass[0]),
            "end_mass_percent": float(mass[-1]),
            "total_mass_loss_percent": float(mass[0] - mass[-1]),
            "min_mass_percent": float(np.nanmin(mass)),
        }
    if not features.empty:
        evidence = [str(value) for value in features["event_id"].head(6)]
        analysis["possible_interpretations"].append(
            {
                "text": "Detected thermal event(s) summarize changes in the reviewed trace; treat them as screening evidence until temperature program, atmosphere, baseline handling, sample mass, replicates, and literature context are reviewed.",
                "confidence": "low",
                "evidence": evidence,
                "assignment_source": str(features.iloc[0]["assignment_source"]),
            }
        )
    else:
        analysis["possible_interpretations"].append(
            {
                "text": "No stable automatic thermal event was detected by the current settings.",
                "confidence": "insufficient",
                "evidence": [],
            }
        )
    analysis = _append_context_interpretation(analysis, context_record)
    analysis = _append_baseline_interpretation(analysis, baseline_record)
    analysis = _append_transition_interpretation(analysis, transition_record)
    return _append_transition_assignment_interpretation(
        analysis, transition_assignment_record
    )


def _created_day(created_at: str | None) -> str | None:
    return created_at[:10] if created_at else None


def _uses_v0_2_project_ids(project_id: str) -> bool:
    return project_id.startswith("prj-")


def _plot_thermal(
    processed: pd.DataFrame,
    features: pd.DataFrame,
    output: Path,
    request: ThermalAnalysisProcessingRequest,
    *,
    transitions: pd.DataFrame | None = None,
    footer: str | None = None,
) -> None:
    fig, ax = styled_subplots(figsize=(6.0, 4.0))
    x = processed["temperature_C"]
    if "processed_mass_percent" in processed.columns:
        y_column = "processed_mass_percent"
        ylabel = "Mass (%)"
        title = "Thermal TGA trace"
        feature_y = "mass_percent"
    elif "processed_heat_flow" in processed.columns:
        y_column = "processed_heat_flow"
        ylabel = (
            f"Heat flow ({request.signal_unit})"
            if request.signal_unit != "unknown"
            else "Heat flow"
        )
        title = "Thermal DSC trace"
        feature_y = "heat_flow"
    else:
        y_column = "processed_dtg_signal"
        ylabel = (
            f"DTG signal ({request.signal_unit})"
            if request.signal_unit != "unknown"
            else "DTG signal"
        )
        title = "Thermal DTG trace"
        feature_y = "dtg_signal"
    ax.plot(
        x,
        processed[y_column],
        color=NATURE_LIKE_COLORS["blue"],
        linewidth=1.2,
        label="Processed signal",
    )
    if not features.empty:
        feature_values = (
            features[feature_y]
            if feature_y in features.columns
            else features["signal_value"]
        )
        usable = features[pd.notna(feature_values)]
        if not usable.empty:
            ax.scatter(
                usable["temperature_C"],
                usable[feature_y],
                color=NATURE_LIKE_COLORS["black"],
                s=18,
                label="Detected events",
                zorder=3,
            )
            for _, event in usable.head(8).iterrows():
                ax.annotate(
                    str(event["event_id"]).replace("thermal-", ""),
                    (float(event["temperature_C"]), float(event[feature_y])),
                    textcoords="offset points",
                    xytext=(0, 6),
                    ha="center",
                    fontsize=7,
                )
    if (
        transitions is not None
        and not transitions.empty
        and "estimated_temperature_C" in transitions.columns
    ):
        plotted = transitions[pd.notna(transitions["estimated_temperature_C"])]
        for _, transition in plotted.head(6).iterrows():
            temperature = float(transition["estimated_temperature_C"])
            ax.axvline(
                temperature,
                color=NATURE_LIKE_COLORS["orange"],
                linewidth=0.8,
                alpha=0.72,
            )
            ax.annotate(
                str(transition["transition_id"]),
                (temperature, float(processed[y_column].median())),
                textcoords="offset points",
                xytext=(3, 0),
                rotation=90,
                va="center",
                fontsize=6.5,
                color=NATURE_LIKE_COLORS["orange"],
            )
    style_axis(ax, title=title, xlabel="Temperature (C)", ylabel=ylabel)
    save_styled_figure(fig, output, footer=footer)


def process_thermal_result(
    root: Path,
    *,
    characterization_metadata_path: Path,
    project_id: str,
    sample_refs: list[str],
    request: ThermalAnalysisProcessingRequest,
    created_at: str | None = None,
) -> Path:
    metadata = read_yaml(characterization_metadata_path)
    require_confirmed_review(root, request.column_review_ref)
    require_confirmed_review(root, request.context_review_ref)
    require_confirmed_review(root, request.parameter_review_ref)
    raw_path = root / metadata["project_raw_path"]
    inspection = inspect_thermal_file(raw_path)
    if inspection.file_kind != "thermal_analysis":
        raise ThermalAnalysisProcessingError(
            f"File is {inspection.file_kind}, not thermal_analysis"
        )

    parameters = _merge_parameters(request.processing_parameters)
    processed, processing_warnings, baseline_record = _apply_processing(
        _confirmed_frame(raw_path, request), request, parameters
    )
    features = _detect_features(processed, parameters, request)
    transitions, transition_record, transition_warnings = _analyze_transitions(
        processed, parameters, request
    )
    transition_assignment_record, transition_assignment_warnings = (
        _record_transition_assignments(parameters, request, transitions)
    )
    context_record, context_warnings = _record_context(parameters)
    analysis = _summary(
        processed,
        features,
        request,
        context_record,
        baseline_record,
        transition_record,
        transition_assignment_record,
    )
    day = _created_day(created_at)
    project_slug = infer_project_slug(project_id)
    if _uses_v0_2_project_ids(project_id):
        result_id = next_standard_id(
            root, "result", project_slug, method="thermal_analysis", day=day
        )
        figure_id = next_standard_id(
            root, "figure", project_slug, method="thermal_analysis", day=day
        )
    else:
        result_id = next_id(root, "thermal_result", day)
        figure_id = None
    sample_dir = sample_refs[0] if sample_refs else "unmapped-sample"
    output_dir = root / "processed" / sample_dir / "thermal_analysis" / result_id
    processed_csv = output_dir / "thermal_processed.csv"
    features_csv = output_dir / "thermal_features.csv"
    transitions_csv = output_dir / "thermal_transitions.csv"
    baseline_yml = output_dir / "thermal_baseline.yml"
    transitions_yml = output_dir / "thermal_transitions.yml"
    transition_assignments_yml = output_dir / "thermal_transition_assignments.yml"
    context_yml = output_dir / "thermal_context.yml"
    figure_name = f"{figure_id}.png" if figure_id else "thermal_plot.png"
    figure = output_dir / figure_name
    result_metadata = output_dir / "thermal_metadata.yml"
    for output in [
        processed_csv,
        features_csv,
        transitions_csv,
        baseline_yml,
        transitions_yml,
        transition_assignments_yml,
        context_yml,
        figure,
        result_metadata,
    ]:
        assert_not_raw_output_path(root, output)

    output_dir.mkdir(parents=True, exist_ok=True)
    processed.to_csv(processed_csv, index=False)
    features.to_csv(features_csv, index=False)
    transition_table_ref: str | None = None
    transition_record_ref: str | None = None
    if transition_record is not None:
        transition_table_ref = transitions_csv.relative_to(root).as_posix()
        transition_record_ref = transitions_yml.relative_to(root).as_posix()
        transitions.to_csv(transitions_csv, index=False)
        transition_record["table_ref"] = transition_table_ref
        transition_record["record_ref"] = transition_record_ref
        write_yaml(transitions_yml, transition_record)
        if analysis.get("transition_analysis"):
            analysis["transition_analysis"]["table_ref"] = transition_table_ref
            analysis["transition_analysis"]["record_ref"] = transition_record_ref
        for item in analysis.get("possible_interpretations", []):
            evidence = item.get("evidence")
            if isinstance(evidence, list):
                item["evidence"] = [
                    transition_table_ref if value == "transition_table" else value
                    for value in evidence
                ]
    transition_assignment_ref: str | None = None
    if transition_assignment_record is not None:
        transition_assignment_ref = transition_assignments_yml.relative_to(
            root
        ).as_posix()
        transition_assignment_record["record_ref"] = transition_assignment_ref
        write_yaml(transition_assignments_yml, transition_assignment_record)
        if analysis.get("transition_assignment"):
            analysis["transition_assignment"]["record_ref"] = transition_assignment_ref
        for item in analysis.get("possible_interpretations", []):
            evidence = item.get("evidence")
            if isinstance(evidence, list):
                item["evidence"] = [
                    transition_assignment_ref
                    if value == "transition_assignment_record"
                    else value
                    for value in evidence
                ]
    baseline_ref: str | None = None
    if baseline_record is not None:
        baseline_ref = baseline_yml.relative_to(root).as_posix()
        baseline_record["record_ref"] = baseline_ref
        write_yaml(baseline_yml, baseline_record)
        if analysis.get("baseline_correction"):
            analysis["baseline_correction"]["record_ref"] = baseline_ref
    context_ref: str | None = None
    if context_record is not None:
        context_ref = context_yml.relative_to(root).as_posix()
        context_record["record_ref"] = context_ref
        write_yaml(context_yml, context_record)
        if analysis.get("context_record"):
            analysis["context_record"]["record_ref"] = context_ref
    _plot_thermal(
        processed,
        features,
        figure,
        request,
        transitions=transitions,
        footer=figure_footer(figure_id, None) if figure_id else None,
    )

    warnings: list[Any] = []
    if request.temperature_unit == "unknown":
        warnings.append(
            _warning(
                "thermal_temperature_unit_unknown",
                "Thermal temperature unit remains unknown after confirmation.",
                severity="medium",
            )
        )
    if request.signal_unit == "unknown":
        warnings.append(
            _warning(
                "thermal_signal_unit_unknown",
                "Thermal signal unit remains unknown after confirmation.",
                severity="medium",
            )
        )
    if not request.context_summary:
        warnings.append(
            _warning(
                "thermal_context_missing",
                "Thermal temperature-program/sample/atmosphere context summary is empty.",
                severity="medium",
            )
        )
    warnings.extend(processing_warnings)
    warnings.extend(transition_warnings)
    warnings.extend(transition_assignment_warnings)
    warnings.extend(context_warnings)
    outputs = {
        "figure": figure.relative_to(root).as_posix(),
        "feature_table": features_csv.relative_to(root).as_posix(),
        "peak_table": features_csv.relative_to(root).as_posix(),
        "processed_csv": processed_csv.relative_to(root).as_posix(),
        "metadata": result_metadata.relative_to(root).as_posix(),
    }
    if baseline_ref:
        outputs["baseline_correction"] = baseline_ref
    if transition_table_ref:
        outputs["transition_table"] = transition_table_ref
    if transition_record_ref:
        outputs["transition_record"] = transition_record_ref
    if transition_assignment_ref:
        outputs["transition_assignment"] = transition_assignment_ref
    if context_ref:
        outputs["context_record"] = context_ref
    result = ThermalAnalysisProcessingResult(
        thermal_result_id=result_id,
        result_id=result_id,
        project_id=project_id,
        characterization_file_ref=metadata["characterization_id"],
        sample_refs=sample_refs,
        status="warning" if warnings else "success",
        temperature_column=request.temperature_column,
        signal_column=request.signal_column,
        temperature_unit=request.temperature_unit,  # type: ignore[arg-type]
        signal_unit=request.signal_unit,  # type: ignore[arg-type]
        measurement_mode=request.measurement_mode,  # type: ignore[arg-type]
        context_summary=request.context_summary,
        processing_parameters=parameters,
        outputs=outputs,
        peak_analysis=ensure_interpretation_message_contract(analysis, "thermal"),
        figure_id=figure_id,
        warnings=warnings,
        review_refs=[
            request.column_review_ref,
            request.context_review_ref,
            request.parameter_review_ref,
        ],
        created_at=created_at or EARecord.now_iso(),
        updated_at=created_at or EARecord.now_iso(),
    )
    write_yaml(result_metadata, result.model_dump(exclude_none=True))
    provenance_files = [
        processed_csv.relative_to(root).as_posix(),
        features_csv.relative_to(root).as_posix(),
        figure.relative_to(root).as_posix(),
    ]
    if context_ref:
        provenance_files.append(context_ref)
    if baseline_ref:
        provenance_files.append(baseline_ref)
    if transition_table_ref:
        provenance_files.append(transition_table_ref)
    if transition_record_ref:
        provenance_files.append(transition_record_ref)
    if transition_assignment_ref:
        provenance_files.append(transition_assignment_ref)
    provenance_path = write_provenance_entry(
        root,
        workflow="thermal_analysis_processing",
        inputs={
            "records": [characterization_metadata_path.relative_to(root).as_posix()],
            "files": [metadata["project_raw_path"]],
        },
        outputs={
            "records": [result_metadata.relative_to(root).as_posix()],
            "files": provenance_files,
        },
        parameters={
            "temperature_column": request.temperature_column,
            "signal_column": request.signal_column,
            "temperature_unit": request.temperature_unit,
            "signal_unit": request.signal_unit,
            "measurement_mode": request.measurement_mode,
            "context_summary": request.context_summary,
            "processing_parameters": parameters,
        },
        review_refs=[
            request.column_review_ref,
            request.context_review_ref,
            request.parameter_review_ref,
        ],
        warnings=warnings,
        scripts=[{"path": "src/ea/thermal/service.py", "version": "0.2.0"}],
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
                "script": "src/ea/thermal/service.py",
                "parameters": {
                    "temperature_column": request.temperature_column,
                    "signal_column": request.signal_column,
                    "temperature_unit": request.temperature_unit,
                    "signal_unit": request.signal_unit,
                    "measurement_mode": request.measurement_mode,
                    "context_summary": request.context_summary,
                    "processing_parameters": parameters,
                },
            },
            caption="Thermal analysis trace with processed signal, screening events, reviewed context, and traceable processing parameters.",
            purpose="thermal_analysis_report",
            style_profile=NATURE_LIKE_STYLE_PROFILE,
            source_data_refs=[
                value
                for value in [
                    processed_csv.relative_to(root).as_posix(),
                    features_csv.relative_to(root).as_posix(),
                    baseline_ref,
                    transition_table_ref,
                    transition_record_ref,
                    transition_assignment_ref,
                    context_ref,
                ]
                if value
            ],
            source_data=[
                source_data_entry(
                    root,
                    processed_csv.relative_to(root).as_posix(),
                    role="primary_plotting_dataset",
                    purpose="Processed thermal trace plotted in the figure.",
                    primary=True,
                ),
                source_data_entry(
                    root,
                    features_csv.relative_to(root).as_posix(),
                    role="feature_table",
                    purpose="Screening events annotated in the thermal figure.",
                ),
            ]
            + (
                [
                    source_data_entry(
                        root,
                        baseline_ref,
                        role="correction_record",
                        purpose="Reviewed baseline correction.",
                    )
                ]
                if baseline_ref
                else []
            )
            + (
                [
                    source_data_entry(
                        root,
                        transition_table_ref,
                        role="transition_table",
                        purpose="Thermal transition values.",
                    )
                ]
                if transition_table_ref
                else []
            )
            + (
                [
                    source_data_entry(
                        root,
                        transition_record_ref,
                        role="transition_record",
                        purpose="Reviewed transition record.",
                    )
                ]
                if transition_record_ref
                else []
            )
            + (
                [
                    source_data_entry(
                        root,
                        transition_assignment_ref,
                        role="assignment_record",
                        purpose="Reviewed thermal transition assignment.",
                    )
                ]
                if transition_assignment_ref
                else []
            )
            + (
                [
                    source_data_entry(
                        root,
                        context_ref,
                        role="interpretation_context",
                        purpose="Reviewed thermal context.",
                    )
                ]
                if context_ref
                else []
            ),
        )
    return result_metadata
