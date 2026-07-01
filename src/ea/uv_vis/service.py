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
from ea.literature.source_packet_manifest import SourcePacketManifestError, confirmed_source_packet_library
from ea.memory import propose_memory_candidate
from ea.provenance import write_provenance_entry
from ea.raman.service import _read_spectrum
from ea.raw_import import assert_not_raw_output_path
from ea.review import require_confirmed_review
from ea.schema import UVVisProcessingResult
from ea.schema.models import EARecord
from ea.standards import infer_project_slug
from ea.storage.files import read_yaml, write_yaml
from ea.storage.ids import next_id, next_standard_id


HC_EV_NM = 1239.841984


class UVVisProcessingError(RuntimeError):
    """Raised when UV-Vis processing would violate review or data boundaries."""


@dataclass(frozen=True)
class UVVisInspection:
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
class UVVisProcessingRequest:
    x_column: str
    y_column: str
    x_unit: str
    signal_mode: str
    processing_parameters: dict[str, Any]
    column_review_ref: str
    parameter_review_ref: str


def default_uv_vis_processing_parameters() -> dict[str, Any]:
    return {
        "smoothing": {
            "enabled": False,
            "method": "savitzky_golay",
            "window_length": 9,
            "polyorder": 2,
        },
        "normalization": {"enabled": True, "method": "max_abs"},
        "feature_detection": {
            "method": "scipy_find_peaks",
            "prominence": "auto",
            "distance": "auto",
            "max_features": 10,
            "source": "ea.uv_vis.feature_detection:v0.2",
        },
        "edge_estimate": {
            "enabled": True,
            "method": "normalized_threshold",
            "threshold_fraction": 0.5,
            "source": "ea.uv_vis.edge_threshold:v0.2",
        },
        "tauc_analysis": {
            "enabled": False,
            "method": "linear_window",
            "transform": "absorbance",
            "transition": "direct_allowed",
            "exponent": 2.0,
            "fit_window_eV": [],
            "min_points": 8,
            "min_r2_for_low_confidence": 0.9,
            "source": "ea.uv_vis.tauc_screening:v0.2",
        },
        "derivative_analysis": {
            "enabled": False,
            "method": "numpy_gradient",
            "axis": "auto",
            "min_points": 8,
            "source": "ea.uv_vis.derivative_screening:v0.2",
        },
        "correction_context": {
            "enabled": False,
            "method": "reviewed_metadata_record",
            "source": "ea.uv_vis.correction_context:v0.2",
            "sample_geometry": {},
            "substrate": {},
            "reference": {},
            "background": {},
            "diffuse_reflectance": {},
            "correction_notes": [],
        },
    }


def _merge_parameters(parameters: dict[str, Any] | None) -> dict[str, Any]:
    merged = default_uv_vis_processing_parameters()
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


def _coerce_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list | tuple | set):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


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
        metadata.get("y_unit"),
        metadata.get("y_label"),
    ]
    return " ".join(str(part) for part in parts if part is not None).lower()


def _signal_mode_candidate(columns: list[str], metadata: dict[str, Any]) -> str:
    text = " ".join(columns + [_axis_metadata_text(metadata)]).lower()
    if "reflect" in text or "%r" in text:
        return "reflectance"
    if "trans" in text or "%t" in text:
        return "transmittance"
    return "absorbance"


def inspect_uv_vis_file(path: Path) -> UVVisInspection:
    frame, metadata = _read_spectrum(path)
    columns = [str(column) for column in frame.columns]
    if frame.empty or len(columns) < 2:
        raise UVVisProcessingError(f"No two-column numeric UV-Vis data found in {path}")

    x_values = pd.to_numeric(frame.iloc[:, 0], errors="coerce").dropna()
    x_min = float(x_values.min())
    x_max = float(x_values.max())
    metadata_text = _axis_metadata_text(metadata)
    path_text = path.as_posix().upper()
    looks_like_nm = "nm" in metadata_text or (150 <= x_min <= 1200 and 180 <= x_max <= 2500)
    looks_like_ev = "ev" in metadata_text or (0.5 <= x_min <= 8 and 0.5 <= x_max <= 8)
    looks_like_uv_vis = (
        "UV" in path_text
        or "VIS" in path_text
        or "ABS" in path_text
        or "TRANSMIT" in path_text
        or (looks_like_nm and x_min <= 450 and x_max >= 500)
    )
    file_kind = "uv_vis" if (looks_like_nm or looks_like_ev) and looks_like_uv_vis else "unknown"
    if looks_like_nm:
        x_unit = "nm"
    elif looks_like_ev:
        x_unit = "eV"
    else:
        x_unit = "unknown"
    warnings: list[str] = []
    if file_kind == "unknown":
        warnings.append("uv_vis_file_kind_unknown")
    if x_unit != "unknown" and ("nm" not in metadata_text and "ev" not in metadata_text):
        warnings.append("uv_vis_unit_inferred_from_range_or_path")

    return UVVisInspection(
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


def _confirmed_frame(path: Path, request: UVVisProcessingRequest) -> pd.DataFrame:
    frame, _ = _read_spectrum(path)
    frame.columns = [str(column) for column in frame.columns]
    if request.x_column not in frame.columns or request.y_column not in frame.columns:
        raise UVVisProcessingError("Confirmed x/y columns are not present in the raw file")
    if request.x_unit not in {"nm", "eV", "unknown"}:
        raise UVVisProcessingError("UV-Vis x_unit must be user-confirmed as nm, eV, or unknown")
    if request.signal_mode not in {"absorbance", "transmittance", "reflectance"}:
        raise UVVisProcessingError("UV-Vis signal_mode must be user-confirmed as absorbance, transmittance, or reflectance")
    data = frame[[request.x_column, request.y_column]].copy()
    data.columns = ["uv_vis_axis", "raw_signal"]
    data["uv_vis_axis"] = pd.to_numeric(data["uv_vis_axis"], errors="coerce")
    data["raw_signal"] = pd.to_numeric(data["raw_signal"], errors="coerce")
    data = data.dropna().sort_values("uv_vis_axis").reset_index(drop=True)
    if data.empty:
        raise UVVisProcessingError("Confirmed UV-Vis columns contain no numeric data")
    if request.x_unit == "nm":
        data["wavelength_nm"] = data["uv_vis_axis"]
        with np.errstate(divide="ignore", invalid="ignore"):
            data["energy_eV"] = HC_EV_NM / data["uv_vis_axis"].to_numpy(dtype=float)
    elif request.x_unit == "eV":
        data["energy_eV"] = data["uv_vis_axis"]
        with np.errstate(divide="ignore", invalid="ignore"):
            data["wavelength_nm"] = HC_EV_NM / data["uv_vis_axis"].to_numpy(dtype=float)
    return data


def _apply_processing(data: pd.DataFrame, parameters: dict[str, Any]) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    processed = data.copy()
    warnings: list[dict[str, Any]] = []
    signal = processed["raw_signal"].to_numpy(dtype=float)

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
                    "uv_vis_smoothing_parameter_adjusted",
                    "Invalid Savitzky-Golay parameters were adjusted for UV-Vis processing.",
                    window_length=window_length,
                    polyorder=polyorder,
                )
            )
        if signal.size >= 3 and window_length >= 3:
            signal = np.asarray(savgol_filter(signal, window_length=window_length, polyorder=polyorder, mode="interp"), dtype=float)
            processed["smoothed_signal"] = signal
            warnings.append(
                _warning(
                    "uv_vis_smoothing_applied",
                    "Savitzky-Golay smoothing was applied before UV-Vis normalization and feature detection.",
                    method="savitzky_golay",
                    window_length=window_length,
                    polyorder=polyorder,
                )
            )
        else:
            warnings.append(_warning("uv_vis_smoothing_skipped", "UV-Vis smoothing skipped because the spectrum has fewer than three points.", severity="medium"))

    if parameters.get("normalization", {}).get("enabled", True):
        max_value = float(np.max(np.abs(signal)))
        if max_value > 0:
            signal = signal / max_value
        warnings.append(_warning("uv_vis_normalization_applied", "UV-Vis signal normalized by processing parameters."))
    processed["processed_signal"] = signal
    return processed, warnings


def _detection_signal(processed: pd.DataFrame, signal_mode: str) -> np.ndarray:
    y = processed["processed_signal"].to_numpy(dtype=float)
    return y if signal_mode == "absorbance" else -y


def _detect_features(processed: pd.DataFrame, parameters: dict[str, Any], signal_mode: str, x_unit: str) -> pd.DataFrame:
    detection_signal = _detection_signal(processed, signal_mode)
    feature_params = parameters.get("feature_detection", {})
    prominence = feature_params.get("prominence", "auto")
    distance = feature_params.get("distance", "auto")
    max_features, _ = _coerce_int(feature_params.get("max_features"), 10, minimum=1)
    if prominence == "auto":
        prominence = max(float(np.ptp(detection_signal)) * 0.08, 0.02)
    if distance == "auto":
        distance = max(len(detection_signal) // 100, 1)
    peaks, properties = find_peaks(detection_signal, prominence=prominence, distance=distance)
    ranked = sorted(
        [(int(peak), float(properties["prominences"][index])) for index, peak in enumerate(peaks)],
        key=lambda item: item[1],
        reverse=True,
    )[:max_features]
    ranked.sort(key=lambda item: float(processed.iloc[item[0]]["uv_vis_axis"]))
    source = str(feature_params.get("source") or "ea.uv_vis.feature_detection:v0.2")
    feature_type = {
        "absorbance": "absorbance_maximum",
        "transmittance": "transmittance_minimum",
        "reflectance": "reflectance_minimum",
    }[signal_mode]
    rows = []
    for index, (feature_index, feature_prominence) in enumerate(ranked, start=1):
        row = processed.iloc[feature_index]
        wavelength = row.get("wavelength_nm", np.nan)
        energy = row.get("energy_eV", np.nan)
        rows.append(
            {
                "feature_id": f"uvvis-feature-{index:03d}",
                "position": float(row["uv_vis_axis"]),
                "position_unit": x_unit,
                "wavelength_nm": float(wavelength) if pd.notna(wavelength) else np.nan,
                "energy_eV": float(energy) if pd.notna(energy) else np.nan,
                "raw_signal": float(row["raw_signal"]),
                "processed_signal": float(row["processed_signal"]),
                "detection_height": float(detection_signal[feature_index]),
                "prominence": feature_prominence,
                "method": "scipy_find_peaks",
                "signal_mode": signal_mode,
                "feature_type": feature_type,
                "assignment_confidence": "low",
                "assignment_source": source,
                "notes": "automatic optical-feature screening; requires method and literature review",
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "feature_id",
            "position",
            "position_unit",
            "wavelength_nm",
            "energy_eV",
            "raw_signal",
            "processed_signal",
            "detection_height",
            "prominence",
            "method",
            "signal_mode",
            "feature_type",
            "assignment_confidence",
            "assignment_source",
            "notes",
        ],
    )


def _estimate_edge(processed: pd.DataFrame, parameters: dict[str, Any], signal_mode: str) -> dict[str, Any] | None:
    edge_params = parameters.get("edge_estimate", {})
    if not edge_params.get("enabled", True) or "wavelength_nm" not in processed.columns:
        return None
    threshold, adjusted = _coerce_float(edge_params.get("threshold_fraction"), 0.5, minimum=0.01, maximum=0.99)
    detection_signal = _detection_signal(processed, signal_mode)
    minimum = float(np.nanmin(detection_signal))
    span = float(np.nanmax(detection_signal) - minimum)
    if span <= 0:
        return None
    normalized = (detection_signal - minimum) / span
    candidates = processed.loc[normalized >= threshold, "wavelength_nm"].dropna()
    if candidates.empty:
        return None
    wavelength = float(candidates.max())
    edge = {
        "method": "normalized_threshold",
        "threshold_fraction": threshold,
        "wavelength_nm": wavelength,
        "energy_eV": float(HC_EV_NM / wavelength) if wavelength > 0 else None,
        "confidence": "low",
        "assignment_source": str(edge_params.get("source") or "ea.uv_vis.edge_threshold:v0.2"),
    }
    if adjusted:
        edge["parameter_adjusted"] = True
    return edge


def _fit_window(params: dict[str, Any]) -> tuple[float, float] | None:
    window = params.get("fit_window_eV")
    if not isinstance(window, list | tuple) or len(window) != 2:
        return None
    low, low_adjusted = _coerce_float(window[0], 0.0)
    high, high_adjusted = _coerce_float(window[1], 0.0)
    if low_adjusted or high_adjusted or low <= 0 or high <= 0 or low >= high:
        return None
    return low, high


def _transition_exponent(params: dict[str, Any]) -> tuple[float, str]:
    transition = str(params.get("transition") or "direct_allowed")
    exponent_map = {
        "direct_allowed": 2.0,
        "indirect_allowed": 0.5,
        "direct_forbidden": 1.5,
        "indirect_forbidden": 3.0,
    }
    if transition == "custom":
        exponent, adjusted = _coerce_float(params.get("exponent"), 2.0, minimum=0.05, maximum=6.0)
        return exponent, "custom" if not adjusted else "custom_adjusted_to_default"
    return exponent_map.get(transition, 2.0), transition if transition in exponent_map else "direct_allowed_defaulted"


def _tauc_alpha_proxy(processed: pd.DataFrame, signal_mode: str, params: dict[str, Any]) -> tuple[np.ndarray | None, list[dict[str, Any]], str]:
    warnings: list[dict[str, Any]] = []
    transform = str(params.get("transform") or "absorbance")
    raw = processed["raw_signal"].to_numpy(dtype=float)
    if transform == "kubelka_munk":
        if signal_mode != "reflectance":
            warnings.append(
                _warning(
                    "uv_vis_tauc_kubelka_munk_signal_mismatch",
                    "Kubelka-Munk transform was requested for a non-reflectance UV-Vis signal; no Tauc fit was performed.",
                    severity="medium",
                    signal_mode=signal_mode,
                )
            )
            return None, warnings, "kubelka_munk"
        reflectance = raw.copy()
        unit_assumption = "fraction_reflectance"
        finite = reflectance[np.isfinite(reflectance)]
        if finite.size and float(np.nanmax(finite)) > 1.5:
            reflectance = reflectance / 100.0
            unit_assumption = "percent_reflectance_converted_to_fraction"
        invalid = ~np.isfinite(reflectance) | (reflectance <= 0)
        reflectance = np.where(invalid, np.nan, reflectance)
        clipped = np.isfinite(reflectance) & (reflectance >= 1.0)
        if np.any(clipped):
            reflectance = np.where(clipped, 0.999999, reflectance)
            warnings.append(
                _warning(
                    "uv_vis_tauc_reflectance_clipped",
                    "Reflectance values at or above 1 were clipped for Kubelka-Munk screening.",
                    severity="medium",
                    unit_assumption=unit_assumption,
                )
            )
        alpha = ((1.0 - reflectance) ** 2) / (2.0 * reflectance)
        return alpha, warnings, f"kubelka_munk:{unit_assumption}"
    if transform != "absorbance":
        warnings.append(
            _warning(
                "uv_vis_tauc_transform_defaulted",
                "Unknown Tauc transform was defaulted to absorbance proxy.",
                severity="medium",
                requested_transform=transform,
            )
        )
    if signal_mode != "absorbance":
        warnings.append(
            _warning(
                "uv_vis_tauc_absorbance_signal_mismatch",
                "Absorbance Tauc transform was requested for a non-absorbance signal; no Tauc fit was performed.",
                severity="medium",
                signal_mode=signal_mode,
            )
        )
        return None, warnings, "absorbance"
    alpha = np.where(np.isfinite(raw) & (raw > 0), raw, np.nan)
    return alpha, warnings, "absorbance"


def _run_tauc_analysis(
    processed: pd.DataFrame,
    parameters: dict[str, Any],
    signal_mode: str,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    params = parameters.get("tauc_analysis", {})
    if not params.get("enabled", False):
        return None, []
    warnings: list[dict[str, Any]] = []
    source = str(params.get("source") or "ea.uv_vis.tauc_screening:v0.2")
    transition_exponent, transition = _transition_exponent(params)
    transform = str(params.get("transform") or "absorbance")
    fit_window = _fit_window(params)
    if fit_window is None:
        warning = _warning(
            "uv_vis_tauc_fit_window_missing",
            "Tauc analysis was enabled, but no valid user-reviewed fit_window_eV was supplied.",
            severity="medium",
        )
        return (
            {
                "status": "insufficient_fit_window",
                "method": "linear_window",
                "transform": transform,
                "transition": transition,
                "exponent": transition_exponent,
                "confidence": "insufficient",
                "assignment_source": source,
                "warnings": [warning],
            },
            [warning],
        )
    if "energy_eV" not in processed.columns:
        warning = _warning(
            "uv_vis_tauc_energy_axis_missing",
            "Tauc analysis requires a reviewed nm or eV axis so photon energy can be computed.",
            severity="medium",
        )
        return (
            {
                "status": "insufficient_energy_axis",
                "method": "linear_window",
                "transform": transform,
                "transition": transition,
                "exponent": transition_exponent,
                "fit_window_eV": list(fit_window),
                "confidence": "insufficient",
                "assignment_source": source,
                "warnings": [warning],
            },
            [warning],
        )
    alpha, alpha_warnings, transform_used = _tauc_alpha_proxy(processed, signal_mode, params)
    warnings.extend(alpha_warnings)
    if alpha is None:
        return (
            {
                "status": "insufficient_transform",
                "method": "linear_window",
                "transform": transform_used,
                "transition": transition,
                "exponent": transition_exponent,
                "fit_window_eV": list(fit_window),
                "confidence": "insufficient",
                "assignment_source": source,
                "warnings": alpha_warnings,
            },
            warnings,
        )
    energy = processed["energy_eV"].to_numpy(dtype=float)
    with np.errstate(invalid="ignore"):
        tauc_y = np.power(alpha * energy, transition_exponent)
    fit_mask = np.isfinite(energy) & np.isfinite(tauc_y) & (energy >= fit_window[0]) & (energy <= fit_window[1])
    processed["tauc_energy_eV"] = energy
    processed["tauc_alpha_proxy"] = alpha
    processed["tauc_y"] = tauc_y
    processed["tauc_fit_window"] = fit_mask
    min_points, _ = _coerce_int(params.get("min_points"), 8, minimum=3)
    fit_points = int(np.count_nonzero(fit_mask))
    base = {
        "status": "insufficient_fit_points",
        "method": "linear_window",
        "transform": transform_used,
        "transition": transition,
        "exponent": transition_exponent,
        "fit_window_eV": list(fit_window),
        "fit_point_count": fit_points,
        "min_points": min_points,
        "confidence": "insufficient",
        "assignment_source": source,
    }
    if fit_points < min_points:
        warning = _warning(
            "uv_vis_tauc_insufficient_fit_points",
            "Tauc fit window contains too few finite points for a linear screening fit.",
            severity="medium",
            fit_points=fit_points,
            min_points=min_points,
        )
        warnings.append(warning)
        return ({**base, "warnings": warnings}, warnings)
    fit_frame = pd.DataFrame({"energy": energy[fit_mask], "tauc_y": tauc_y[fit_mask]}).sort_values("energy")
    x = fit_frame["energy"].to_numpy(dtype=float)
    y = fit_frame["tauc_y"].to_numpy(dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    predicted = slope * x + intercept
    ss_res = float(np.sum((y - predicted) ** 2))
    ss_tot = float(np.sum((y - float(np.mean(y))) ** 2))
    r2 = 1.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot
    intercept_energy = float(-intercept / slope) if slope else None
    min_r2, _ = _coerce_float(params.get("min_r2_for_low_confidence"), 0.9, minimum=0.0, maximum=1.0)
    plausible_intercept = intercept_energy is not None and 0.1 <= intercept_energy <= 10.0
    confidence = "low" if r2 >= min_r2 and plausible_intercept else "insufficient"
    if confidence == "insufficient":
        warnings.append(
            _warning(
                "uv_vis_tauc_fit_low_confidence",
                "Tauc screening fit did not meet the configured low-confidence quality checks.",
                severity="medium",
                r2=r2,
                intercept_energy_eV=intercept_energy,
                min_r2=min_r2,
            )
        )
    return (
        {
            **base,
            "status": "screening_fit_recorded",
            "slope": float(slope),
            "intercept": float(intercept),
            "r2": float(r2),
            "intercept_energy_eV": intercept_energy,
            "confidence": confidence,
            "warnings": warnings,
            "boundary": "Screening Tauc/Kubelka-Munk fit only; not a definitive band-gap assignment.",
        },
        warnings,
    )


def _derivative_axis(processed: pd.DataFrame, params: dict[str, Any]) -> tuple[str | None, str | None, list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    requested = str(params.get("axis") or "auto")
    if requested == "auto":
        if "energy_eV" in processed.columns:
            return "energy_eV", "eV", warnings
        return "uv_vis_axis", "reviewed_axis", warnings
    axis_units = {
        "energy_eV": "eV",
        "wavelength_nm": "nm",
        "uv_vis_axis": "reviewed_axis",
    }
    if requested not in axis_units or requested not in processed.columns:
        warnings.append(
            _warning(
                "uv_vis_derivative_axis_unavailable",
                "Requested UV-Vis derivative axis is unavailable; derivative analysis was not performed.",
                severity="medium",
                requested_axis=requested,
            )
        )
        return None, None, warnings
    return requested, axis_units[requested], warnings


def _finite_summary_value(row: pd.Series, column: str) -> float | None:
    value = row.get(column)
    return float(value) if pd.notna(value) else None


def _derivative_point(row: pd.Series, axis_column: str, axis_unit: str) -> dict[str, Any]:
    return {
        "axis": axis_column,
        "axis_unit": axis_unit,
        "axis_value": _finite_summary_value(row, "derivative_axis"),
        "wavelength_nm": _finite_summary_value(row, "wavelength_nm"),
        "energy_eV": _finite_summary_value(row, "energy_eV"),
        "processed_signal": _finite_summary_value(row, "processed_signal"),
        "first_derivative": _finite_summary_value(row, "first_derivative"),
        "second_derivative": _finite_summary_value(row, "second_derivative"),
    }


def _run_derivative_analysis(
    processed: pd.DataFrame,
    parameters: dict[str, Any],
) -> tuple[pd.DataFrame | None, dict[str, Any] | None, list[dict[str, Any]]]:
    params = parameters.get("derivative_analysis", {})
    if not params.get("enabled", False):
        return None, None, []
    source = str(params.get("source") or "ea.uv_vis.derivative_screening:v0.2")
    warnings: list[dict[str, Any]] = []
    axis_column, axis_unit, axis_warnings = _derivative_axis(processed, params)
    warnings.extend(axis_warnings)
    base = {
        "enabled": True,
        "method": str(params.get("method") or "numpy_gradient"),
        "axis": axis_column or str(params.get("axis") or "auto"),
        "axis_unit": axis_unit or "unknown",
        "assignment_source": source,
        "confidence": "insufficient",
        "boundary": "UV-Vis derivative extrema and inflection hints are screening-only; they are not definitive band-gap, transition-type, defect-state, thickness, or mechanism assignments.",
    }
    if axis_column is None or axis_unit is None:
        return None, {**base, "status": "axis_unavailable", "warnings": warnings}, warnings

    min_points, adjusted = _coerce_int(params.get("min_points"), 8, minimum=3)
    if adjusted:
        warnings.append(
            _warning(
                "uv_vis_derivative_min_points_adjusted",
                "Invalid UV-Vis derivative min_points was adjusted before screening.",
                severity="medium",
                min_points=min_points,
            )
        )
    frame = processed.copy()
    axis = pd.to_numeric(frame[axis_column], errors="coerce").to_numpy(dtype=float)
    signal = pd.to_numeric(frame["processed_signal"], errors="coerce").to_numpy(dtype=float)
    finite_mask = np.isfinite(axis) & np.isfinite(signal)
    if int(np.count_nonzero(finite_mask)) < min_points:
        warning = _warning(
            "uv_vis_derivative_insufficient_points",
            "UV-Vis derivative analysis had too few finite points for gradient screening.",
            severity="medium",
            finite_points=int(np.count_nonzero(finite_mask)),
            min_points=min_points,
        )
        warnings.append(warning)
        return None, {**base, "status": "insufficient_points", "point_count": int(np.count_nonzero(finite_mask)), "warnings": warnings}, warnings
    finite_axis = axis[finite_mask]
    if np.unique(finite_axis).size < min_points:
        warning = _warning(
            "uv_vis_derivative_duplicate_axis",
            "UV-Vis derivative analysis requires enough unique axis values.",
            severity="medium",
            unique_axis_count=int(np.unique(finite_axis).size),
            min_points=min_points,
        )
        warnings.append(warning)
        return None, {**base, "status": "duplicate_axis_values", "warnings": warnings}, warnings

    table = pd.DataFrame(
        {
            "derivative_axis": axis,
            "axis_unit": axis_unit,
            "wavelength_nm": frame["wavelength_nm"] if "wavelength_nm" in frame.columns else np.nan,
            "energy_eV": frame["energy_eV"] if "energy_eV" in frame.columns else np.nan,
            "processed_signal": signal,
        }
    )
    first = np.full_like(signal, np.nan, dtype=float)
    second = np.full_like(signal, np.nan, dtype=float)
    finite_signal = signal[finite_mask]
    first_values = np.gradient(finite_signal, finite_axis)
    second_values = np.gradient(first_values, finite_axis)
    first[finite_mask] = first_values
    second[finite_mask] = second_values
    table["first_derivative"] = first
    table["second_derivative"] = second
    table["method"] = "numpy_gradient"
    table["assignment_source"] = source

    finite_derivative = np.isfinite(first)
    if not np.any(finite_derivative):
        warning = _warning(
            "uv_vis_derivative_no_finite_gradient",
            "UV-Vis derivative analysis produced no finite first-derivative values.",
            severity="medium",
        )
        warnings.append(warning)
        return table, {**base, "status": "no_finite_gradient", "point_count": int(np.count_nonzero(finite_mask)), "warnings": warnings}, warnings

    derivative_series = pd.Series(first)
    max_positive_idx = int(derivative_series.idxmax())
    min_negative_idx = int(derivative_series.idxmin())
    max_abs_idx = int(pd.Series(np.abs(first)).idxmax())
    zero_crossings = int(np.count_nonzero(np.diff(np.signbit(first[finite_derivative]))))
    summary = {
        **base,
        "status": "screening_derivative_recorded",
        "point_count": int(np.count_nonzero(finite_mask)),
        "zero_crossing_count": zero_crossings,
        "max_positive_slope": _derivative_point(table.iloc[max_positive_idx], axis_column, axis_unit),
        "min_negative_slope": _derivative_point(table.iloc[min_negative_idx], axis_column, axis_unit),
        "max_abs_slope": _derivative_point(table.iloc[max_abs_idx], axis_column, axis_unit),
        "confidence": "low",
        "warnings": warnings,
    }
    return table, summary, warnings


_CORRECTION_CONTEXT_SECTIONS = ("sample_geometry", "substrate", "reference", "background", "diffuse_reflectance")


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
            "uv_vis_correction_context_section_ignored",
            "A UV-Vis correction-context section was ignored because it was not a mapping.",
            severity="medium",
            section=name,
        ),
    )


def _correction_notes(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any] | None]:
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
            "uv_vis_correction_notes_ignored",
            "UV-Vis correction notes were ignored because they were not a list or non-empty string.",
            severity="medium",
        ),
    )


def _record_correction_context(parameters: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    params = parameters.get("correction_context", {})
    if not isinstance(params, dict) or not params.get("enabled", False):
        return None, []
    warnings: list[dict[str, Any]] = []
    sections: dict[str, dict[str, Any]] = {}
    for name in _CORRECTION_CONTEXT_SECTIONS:
        section, warning = _context_section(params, name)
        sections[name] = section
        if warning:
            warnings.append(warning)
    notes, notes_warning = _correction_notes(params)
    if notes_warning:
        warnings.append(notes_warning)

    reviewed_fields = [name for name, section in sections.items() if _has_context_payload(section)]
    if _has_context_payload(notes):
        reviewed_fields.append("correction_notes")
    has_reviewed_context = bool(reviewed_fields)
    if not has_reviewed_context:
        warnings.append(
            _warning(
                "uv_vis_correction_context_empty",
                "UV-Vis correction_context was enabled, but no reviewed correction metadata was supplied.",
                severity="medium",
            )
        )
    source = str(params.get("source") or "ea.uv_vis.correction_context:v0.2")
    return (
        {
            "enabled": True,
            "status": "reviewed_correction_context_recorded" if has_reviewed_context else "enabled_without_reviewed_context",
            "method": str(params.get("method") or "reviewed_metadata_record"),
            "assignment_source": source,
            "confidence": "low" if has_reviewed_context else "insufficient",
            "reviewed_context_fields": reviewed_fields,
            **sections,
            "correction_notes": notes,
            "warnings": warnings,
            "boundary": "UV-Vis correction context is a metadata/provenance record only; no automatic substrate, reference, background, or diffuse-reflectance numeric correction was applied.",
        },
        warnings,
    )


def _analyze_features(
    features: pd.DataFrame,
    edge: dict[str, Any] | None,
    tauc: dict[str, Any] | None = None,
    derivative: dict[str, Any] | None = None,
    correction_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    analysis: dict[str, Any] = {
        "feature_count": int(len(features)),
        "strongest_features": [],
        "edge_estimate": edge,
        "tauc_analysis": tauc,
        "derivative_analysis": derivative,
        "correction_context": correction_context,
        "possible_interpretations": [],
    }
    if features.empty:
        analysis["possible_interpretations"].append(
            {
                "text": "No stable UV-Vis optical feature was detected by the current automatic settings.",
                "confidence": "insufficient",
                "evidence": [],
            }
        )
    else:
        strongest = features.sort_values("prominence", ascending=False).head(6)
        analysis["strongest_features"] = [
            {
                "feature_id": str(row["feature_id"]),
                "position": float(row["position"]),
                "position_unit": str(row["position_unit"]),
                "wavelength_nm": float(row["wavelength_nm"]) if pd.notna(row["wavelength_nm"]) else None,
                "energy_eV": float(row["energy_eV"]) if pd.notna(row["energy_eV"]) else None,
                "assignment_source": str(row["assignment_source"]),
            }
            for _, row in strongest.iterrows()
        ]
        evidence = [str(value) for value in strongest["feature_id"].head(4)]
        source_values = [str(value) for value in strongest["assignment_source"] if str(value)]
        analysis["possible_interpretations"].append(
            {
                "text": "Detected UV-Vis feature(s) are consistent with optical absorption/attenuation structure in the reviewed spectrum; treat them as screening evidence, not a band-gap or mechanism claim.",
                "confidence": "low",
                "evidence": evidence,
                "assignment_source": source_values[0] if source_values else "ea.uv_vis.feature_detection:v0.2",
            }
        )
    if edge:
        analysis["possible_interpretations"].append(
            {
                "text": "A threshold-based optical edge estimate was recorded for orientation only; formal band-gap analysis requires user-confirmed method context such as Tauc model, sample geometry, and references.",
                "confidence": edge.get("confidence", "low"),
                "evidence": ["edge_estimate"],
                "assignment_source": edge.get("assignment_source", "ea.uv_vis.edge_threshold:v0.2"),
            }
        )
    if tauc and tauc.get("status") == "screening_fit_recorded":
        value = tauc.get("intercept_energy_eV")
        value_text = f"{float(value):.3f} eV" if value is not None else "not available"
        analysis["possible_interpretations"].append(
            {
                "text": (
                    f"A screening {tauc.get('transform')} Tauc/Kubelka-Munk linear-window intercept was recorded at "
                    f"{value_text}. Treat this as reviewed-model screening evidence only, not a definitive optical band gap."
                ),
                "confidence": tauc.get("confidence", "low"),
                "evidence": ["tauc_analysis"],
                "assignment_source": tauc.get("assignment_source", "ea.uv_vis.tauc_screening:v0.2"),
            }
        )
    if derivative and derivative.get("status") == "screening_derivative_recorded":
        strongest = derivative.get("max_abs_slope", {})
        axis_value = strongest.get("axis_value")
        axis_unit = strongest.get("axis_unit", "unknown")
        axis_text = f"{float(axis_value):.4g} {axis_unit}" if axis_value is not None else "not available"
        analysis["possible_interpretations"].append(
            {
                "text": (
                    f"A UV-Vis derivative screening table was recorded; the strongest first-derivative magnitude occurs near "
                    f"{axis_text}. Treat derivative extrema as shoulder/edge orientation only, not a definitive optical transition or band-gap conclusion."
                ),
                "confidence": derivative.get("confidence", "low"),
                "evidence": ["derivative_analysis"],
                "assignment_source": derivative.get("assignment_source", "ea.uv_vis.derivative_screening:v0.2"),
            }
        )
    if correction_context and correction_context.get("status") == "reviewed_correction_context_recorded":
        fields = ", ".join(str(value) for value in correction_context.get("reviewed_context_fields", [])) or "correction context"
        analysis["possible_interpretations"].append(
            {
                "text": (
                    f"Reviewed UV-Vis correction context was recorded for {fields}. Use it to interpret optical features and "
                    "screening fits, but do not treat the metadata record as a numeric correction or a standalone mechanism claim."
                ),
                "confidence": correction_context.get("confidence", "low"),
                "evidence": ["correction_context"],
                "assignment_source": correction_context.get("assignment_source", "ea.uv_vis.correction_context:v0.2"),
            }
        )
    return analysis


def _uv_vis_source_candidates(source_packet: Any) -> list[Any]:
    if isinstance(source_packet, list):
        return source_packet
    if isinstance(source_packet, dict):
        raw_candidates = source_packet.get("candidates") or source_packet.get("source_candidates") or source_packet.get("suggestions") or []
        return raw_candidates if isinstance(raw_candidates, list) else []
    return []


def _normalize_uv_vis_candidate_type(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _uv_vis_candidate_identity(candidate: dict[str, Any]) -> str:
    return str(candidate.get("candidate_id") or candidate.get("suggestion_id") or "").strip()


def _uv_vis_candidate_matches_filters(
    candidate: dict[str, Any],
    *,
    include_candidates: set[str],
    candidate_types: set[str],
    optical_targets: set[str],
) -> bool:
    if include_candidates and _uv_vis_candidate_identity(candidate) not in include_candidates:
        return False
    candidate_type = _normalize_uv_vis_candidate_type(candidate.get("candidate_type") or candidate.get("type"))
    if candidate_types and candidate_type not in candidate_types:
        return False
    if optical_targets:
        target_text = " ".join(
            str(candidate.get(key) or "")
            for key in ["optical_target", "target", "feature_label", "transition_model", "correction_context_type"]
        ).lower()
        if not any(target in target_text for target in optical_targets):
            return False
    return True


def _uv_vis_source_reference_seeds(
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
                "uv_vis_source_reference_seeds_invalid",
                "UV-Vis source packet reference_seeds were ignored because they were not a mapping.",
                severity="medium",
            )
        )
        return {}
    seeds: dict[str, Any] = {}
    for raw_seed_id, raw_seed in raw_seeds.items():
        seed_id = str(raw_seed_id).strip()
        if not seed_id:
            warnings.append(
                _warning(
                    "uv_vis_source_reference_seed_id_invalid",
                    "A UV-Vis source reference_seed was skipped because its seed id was empty.",
                    severity="medium",
                )
            )
            continue
        if referenced_ids and seed_id not in referenced_ids:
            continue
        if not isinstance(raw_seed, dict):
            warnings.append(
                _warning(
                    "uv_vis_source_reference_seed_ignored",
                    "A UV-Vis source reference_seed was skipped because its metadata was not a mapping.",
                    severity="medium",
                    seed_id=seed_id,
                )
            )
            continue
        seeds[seed_id] = deepcopy(raw_seed)
    return seeds


def _uv_vis_source_packet_template_candidates() -> list[dict[str, Any]]:
    return [
        {
            "candidate_id": "uvvis-template-optical-transition-model",
            "candidate_type": "optical_transition_model",
            "optical_target": "TODO: target sample/material and spectral regime",
            "transition_model": "TODO: e.g. direct_allowed, indirect_allowed, Kubelka-Munk context, or source-specific model",
            "transition_assumption": "TODO: summarize the source-backed model assumption and when it applies.",
            "tauc_transform": "TODO: absorbance, absorption_coefficient_proxy, Kubelka-Munk, or not_applicable",
            "source_summary": "TODO: summarize the reference that supports this UV-Vis model context.",
            "applicability_notes": ["TODO: describe sample geometry, film thickness/scattering/substrate assumptions, and signal mode."],
            "reference_ids": ["TODO-registered-reference-id"],
            "confidence": "low",
            "caveats": ["Template candidate only; fill source metadata and model assumptions before using in future UV-Vis suggestions."],
        },
        {
            "candidate_id": "uvvis-template-optical-gap-candidate",
            "candidate_type": "optical_gap_candidate",
            "optical_target": "TODO: absorption edge or material phase/context",
            "reported_energy_eV": None,
            "energy_window_eV": [None, None],
            "transition_assumption": "TODO: source-backed transition assumption for the reported gap/window.",
            "source_summary": "TODO: summarize the source that reports or justifies this optical-gap candidate.",
            "applicability_notes": ["TODO: describe comparable material, processing, thickness, substrate/background, and measurement mode."],
            "reference_ids": ["TODO-registered-reference-id"],
            "confidence": "low",
            "caveats": ["Template candidate only; do not treat the gap/window as a project result without reviewed data and references."],
        },
        {
            "candidate_id": "uvvis-template-optical-feature-assignment",
            "candidate_type": "optical_feature_assignment",
            "optical_target": "TODO: excitonic/defect/charge-transfer/absorption feature label",
            "feature_label": "TODO: descriptive feature label",
            "reported_energy_eV": None,
            "wavelength_window_nm": [None, None],
            "expected_feature": "TODO: absorbance_maximum, shoulder, reflectance_minimum, derivative_extremum, etc.",
            "source_summary": "TODO: summarize the source that supports this feature assignment candidate.",
            "applicability_notes": ["TODO: describe material state, sample form, and overlapping feature/correction risks."],
            "reference_ids": ["TODO-registered-reference-id"],
            "confidence": "low",
            "caveats": ["Template candidate only; a spectral feature match alone does not prove mechanism or material state."],
        },
        {
            "candidate_id": "uvvis-template-correction-context",
            "candidate_type": "correction_context_candidate",
            "optical_target": "TODO: substrate/reference/background/diffuse-reflectance correction context",
            "correction_context_type": "TODO: substrate, baseline, reference, scattering, diffuse_reflectance, or background",
            "correction_method": "TODO: source-backed correction or interpretation context; no automatic correction is applied here",
            "source_summary": "TODO: summarize the source that supports this correction-context candidate.",
            "applicability_notes": ["TODO: describe when this context applies and what user confirmation is required."],
            "reference_ids": ["TODO-registered-reference-id"],
            "confidence": "low",
            "caveats": ["Template candidate only; this packet does not apply numeric corrections or prove correction validity."],
        },
    ]


def build_uv_vis_source_packet(
    root: Path,
    *,
    project_id: str,
    library_path: Path | None = None,
    literature_manifest_path: Path | None = None,
    output_path: Path | None = None,
    include_candidates: list[str] | None = None,
    candidate_types: list[str] | None = None,
    optical_targets: list[str] | None = None,
    template: bool = False,
    created_at: str | None = None,
) -> dict[str, Any]:
    selected_source_count = sum(bool(value) for value in [library_path, literature_manifest_path, template])
    if selected_source_count != 1:
        raise UVVisProcessingError(
            "Use exactly one of --library-file, --literature-manifest, or --write-template for UV-Vis source-packet generation"
        )

    template_mode = template and library_path is None and literature_manifest_path is None
    literature_mode = literature_manifest_path is not None
    day = _created_day(created_at)
    timestamp = created_at or EARecord.now_iso()
    source_packet_id = next_id(root, "uv_vis_source_packet", day)
    if output_path is None:
        if template_mode:
            output_path = root / "templates" / "uv_vis_source_packet.yml"
        else:
            output_path = root / "suggestions" / "uv_vis" / "source-packets" / f"{source_packet_id}.yml"
    elif not output_path.is_absolute():
        output_path = root / output_path
    assert_not_raw_output_path(root, output_path)

    warnings: list[dict[str, Any]] = []
    library_ref: str | None = None
    library_kind = "template" if template_mode else "local_file"
    source_library: Any = {}
    if template_mode:
        raw_candidates = _uv_vis_source_packet_template_candidates()
    elif literature_mode:
        source_path = literature_manifest_path if literature_manifest_path and literature_manifest_path.is_absolute() else root / literature_manifest_path if literature_manifest_path else None
        if source_path is None:
            raise UVVisProcessingError("UV-Vis literature manifest path was not supplied")
        try:
            source_library, manifest_warnings = confirmed_source_packet_library(
                root,
                manifest_path=source_path,
                method="uv_vis",
                method_aliases={
                    "uv_vis",
                    "uv-vis",
                    "uvvis",
                    "uv_visible",
                    "optical_absorption",
                    "uv_vis_source_packet",
                    "uv_vis_optical_source_packet",
                },
            )
        except SourcePacketManifestError as exc:
            raise UVVisProcessingError(str(exc)) from exc
        warnings.extend(manifest_warnings)
        raw_candidates = _uv_vis_source_candidates(source_library)
        library_ref = _relative_to_root(root, source_path)
        library_kind = "confirmed_literature_manifest"
    else:
        source_path = library_path if library_path and library_path.is_absolute() else root / library_path if library_path else None
        if source_path is None or not source_path.exists():
            raise UVVisProcessingError(f"UV-Vis source library file not found: {library_path}")
        library_ref = _relative_to_root(root, source_path)
        source_library = read_yaml(source_path)
        raw_candidates = _uv_vis_source_candidates(source_library)

    include_set = {str(item).strip() for item in include_candidates or [] if str(item).strip()}
    type_set = {_normalize_uv_vis_candidate_type(item) for item in candidate_types or [] if str(item).strip()}
    target_set = {str(item).strip().lower() for item in optical_targets or [] if str(item).strip()}
    selected: list[dict[str, Any]] = []
    for index, raw_candidate in enumerate(raw_candidates, start=1):
        if not isinstance(raw_candidate, dict):
            warnings.append(
                _warning(
                    "uv_vis_source_candidate_ignored",
                    "A UV-Vis source candidate was not a mapping and was skipped while building the source packet.",
                    severity="medium",
                    candidate_index=index,
                )
            )
            continue
        if not _uv_vis_candidate_matches_filters(
            raw_candidate,
            include_candidates=include_set,
            candidate_types=type_set,
            optical_targets=target_set,
        ):
            continue
        candidate = deepcopy(raw_candidate)
        normalized_type = _normalize_uv_vis_candidate_type(candidate.get("candidate_type") or candidate.get("type"))
        if normalized_type:
            candidate["candidate_type"] = normalized_type
        selected.append(candidate)

    if not raw_candidates:
        warnings.append(
            _warning(
                "uv_vis_source_library_empty",
                "No UV-Vis source candidates were found in the source library.",
                severity="medium",
            )
        )
    if raw_candidates and not selected:
        warnings.append(
            _warning(
                "uv_vis_source_no_matches",
                "No UV-Vis source candidates matched the requested filters.",
                severity="medium",
            )
        )

    candidate_reference_ids = {reference_id for candidate in selected for reference_id in _coerce_string_list(candidate.get("reference_ids"))}
    guidance_reference_ids = _coerce_string_list(source_library.get("guidance_reference_ids")) if isinstance(source_library, dict) else []
    reference_ids = sorted(candidate_reference_ids | set(guidance_reference_ids))
    reference_seeds = _uv_vis_source_reference_seeds(
        source_library,
        referenced_ids=set(reference_ids),
        warnings=warnings,
    )
    packet_ref = _relative_to_root(root, output_path)
    status = "template_requires_user_edit" if template_mode else ("staged_for_future_uv_vis_suggestions" if selected else "no_matching_candidates")
    packet = {
        "schema_version": "0.2",
        "source_packet_id": source_packet_id,
        "project_id": project_id,
        "status": status,
        "created_at": timestamp,
        "updated_at": timestamp,
        "source": "ea.uv_vis.source_packet:v0.2",
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
            "candidate_types": sorted(type_set),
            "optical_targets": sorted(target_set),
        },
        "reference_ids": reference_ids,
        "warnings": warnings,
        "next_steps": [
            "Register or replace reference_seeds before treating any UV-Vis source candidate as report evidence.",
            "Review and edit this packet until every candidate has source_summary, applicability_notes, reference_ids, confidence, caveats, and the candidate-specific optical target/model/gap/feature/correction fields.",
            "Use this packet as staging for a future UV-Vis suggestion/review/report workflow when that workflow is implemented.",
        ],
        "boundaries": [
            "UV-Vis source packets are staging artifacts and do not modify processed spectra, figures, reports, or confirmed project memory.",
            "reference_seeds are registration hints only; they do not inject report citations, download PDFs, parse full text, apply optical models, or prove optical assignments.",
            "This source-packet builder is deterministic and does not perform live lookup, article download, full-text parsing, report citation injection, suggestion generation, optical-model or correction auto-application, band-gap proof, transition-mechanism proof, feature-assignment proof, or memory commit.",
            "A confirmed-literature manifest is a source-candidate manifest only; it does not register references, prove band gaps or transition models, apply Tauc/Kubelka-Munk/correction settings, or validate mechanisms by itself.",
        ],
    }
    write_yaml(output_path, packet)
    provenance_path = write_provenance_entry(
        root,
        workflow="uv_vis_source_packet",
        inputs={"records": [library_ref] if library_ref else [], "files": []},
        outputs={"records": [packet_ref], "files": []},
        parameters={
            "candidate_count": len(selected),
            "reference_seed_count": len(reference_seeds),
            "template": template_mode,
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
    if not isinstance(value, dict):
        return None
    for name in names:
        if value.get(name) is None:
            continue
        try:
            number = float(value.get(name))
        except (TypeError, ValueError):
            continue
        if np.isfinite(number):
            return number
    return None


def _candidate_window(value: Any, *names: str) -> list[float] | None:
    if not isinstance(value, dict):
        return None
    for name in names:
        raw = value.get(name)
        if raw is None:
            continue
        if isinstance(raw, str):
            raw = [part.strip() for part in raw.replace(" to ", ",").replace("-", ",").split(",")]
        if isinstance(raw, dict):
            low_raw = raw.get("min", raw.get("lower", raw.get("low", raw.get("start"))))
            high_raw = raw.get("max", raw.get("upper", raw.get("high", raw.get("end"))))
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
    return None


def _value_in_window(value: Any, window: list[float] | None) -> bool:
    if window is None or len(window) != 2:
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return np.isfinite(number) and window[0] <= number <= window[1]


def _normalize_uv_vis_expected_feature(value: Any) -> str:
    normalized = str(value or "any").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "peak": "any",
        "band": "any",
        "feature": "any",
        "absorbance": "absorbance_maximum",
        "absorbance_peak": "absorbance_maximum",
        "maximum": "absorbance_maximum",
        "transmittance": "transmittance_minimum",
        "transmittance_valley": "transmittance_minimum",
        "reflectance": "reflectance_minimum",
        "reflectance_valley": "reflectance_minimum",
        "minimum": "any",
        "shoulder": "any",
        "derivative_extremum": "any",
    }
    return aliases.get(normalized, normalized)


def _feature_type_matches(expected_feature: str, feature_type: str) -> bool:
    if expected_feature in {"", "any"}:
        return True
    return expected_feature == str(feature_type or "").strip().lower().replace("-", "_").replace(" ", "_")


def _match_uv_vis_features(
    features: pd.DataFrame,
    *,
    energy_window: list[float] | None,
    wavelength_window: list[float] | None,
    expected_feature: str,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    if features.empty:
        return matches
    for _, row in features.iterrows():
        energy = row.get("energy_eV")
        wavelength = row.get("wavelength_nm")
        feature_type = str(row.get("feature_type") or "")
        if energy_window is not None and not _value_in_window(energy, energy_window):
            continue
        if wavelength_window is not None and not _value_in_window(wavelength, wavelength_window):
            continue
        if energy_window is None and wavelength_window is None:
            continue
        if not _feature_type_matches(expected_feature, feature_type):
            continue
        matches.append(
            {
                "feature_id": str(row.get("feature_id") or ""),
                "energy_eV": float(energy) if pd.notna(energy) else None,
                "wavelength_nm": float(wavelength) if pd.notna(wavelength) else None,
                "prominence": float(row.get("prominence", 0.0)) if pd.notna(row.get("prominence", np.nan)) else None,
                "feature_type": feature_type,
                "assignment_source": str(row.get("assignment_source") or ""),
            }
        )
    return matches


def _uv_vis_interpretation_suggestion_columns() -> list[str]:
    return [
        "candidate_id",
        "candidate_type",
        "status",
        "requires_user_review",
        "auto_applied",
        "optical_target",
        "evidence_status",
        "evidence_refs",
        "matched_feature_ids",
        "matched_energies_eV",
        "matched_wavelengths_nm",
        "reported_energy_eV",
        "energy_window_eV",
        "wavelength_window_nm",
        "transition_model",
        "transition_assumption",
        "tauc_transform",
        "feature_label",
        "expected_feature",
        "correction_context_type",
        "correction_method",
        "source_summary",
        "reference_ids",
        "unresolved_reference_ids",
        "applicability_notes",
        "confidence",
        "missing_fields",
        "caveats",
    ]


def _uv_vis_gap_evidence(
    metadata: dict[str, Any],
    features: pd.DataFrame,
    *,
    energy_window: list[float] | None,
    expected_feature: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidence: list[dict[str, Any]] = []
    peak_analysis = metadata.get("peak_analysis") if isinstance(metadata.get("peak_analysis"), dict) else {}
    tauc = peak_analysis.get("tauc_analysis") if isinstance(peak_analysis.get("tauc_analysis"), dict) else {}
    intercept = tauc.get("intercept_energy_eV")
    if _value_in_window(intercept, energy_window):
        evidence.append(
            {
                "evidence_type": "tauc_analysis",
                "evidence_ref": tauc.get("table_ref") or "tauc_analysis",
                "energy_eV": float(intercept),
                "status": tauc.get("status"),
                "confidence": tauc.get("confidence"),
            }
        )
    edge = peak_analysis.get("edge_estimate") if isinstance(peak_analysis.get("edge_estimate"), dict) else {}
    edge_energy = edge.get("energy_eV")
    if _value_in_window(edge_energy, energy_window):
        evidence.append(
            {
                "evidence_type": "edge_estimate",
                "evidence_ref": "edge_estimate",
                "energy_eV": float(edge_energy),
                "confidence": edge.get("confidence"),
            }
        )
    feature_matches = _match_uv_vis_features(
        features,
        energy_window=energy_window,
        wavelength_window=None,
        expected_feature=expected_feature,
    )
    for match in feature_matches:
        evidence.append(
            {
                "evidence_type": "detected_feature",
                "evidence_ref": match.get("feature_id"),
                "energy_eV": match.get("energy_eV"),
                "wavelength_nm": match.get("wavelength_nm"),
                "feature_type": match.get("feature_type"),
            }
        )
    derivative = peak_analysis.get("derivative_analysis") if isinstance(peak_analysis.get("derivative_analysis"), dict) else {}
    max_slope = derivative.get("max_abs_slope") if isinstance(derivative.get("max_abs_slope"), dict) else {}
    derivative_energy = max_slope.get("energy_eV")
    if _value_in_window(derivative_energy, energy_window):
        evidence.append(
            {
                "evidence_type": "derivative_analysis",
                "evidence_ref": derivative.get("table_ref") or "derivative_analysis",
                "energy_eV": float(derivative_energy),
                "confidence": derivative.get("confidence"),
            }
        )
    return evidence, feature_matches


def _uv_vis_transition_evidence(metadata: dict[str, Any], transition_model: str) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    peak_analysis = metadata.get("peak_analysis") if isinstance(metadata.get("peak_analysis"), dict) else {}
    tauc = peak_analysis.get("tauc_analysis") if isinstance(peak_analysis.get("tauc_analysis"), dict) else {}
    if tauc:
        tauc_transition = str(tauc.get("transition") or "").strip().lower().replace("-", "_")
        relation = "matching_tauc_transition" if transition_model and transition_model == tauc_transition else "available_tauc_analysis"
        evidence.append(
            {
                "evidence_type": "tauc_analysis",
                "evidence_ref": tauc.get("table_ref") or "tauc_analysis",
                "relation": relation,
                "transition": tauc.get("transition"),
                "transform": tauc.get("transform"),
                "confidence": tauc.get("confidence"),
            }
        )
    return evidence


def _uv_vis_correction_evidence(metadata: dict[str, Any], correction_context_type: str) -> list[dict[str, Any]]:
    peak_analysis = metadata.get("peak_analysis") if isinstance(metadata.get("peak_analysis"), dict) else {}
    correction = peak_analysis.get("correction_context") if isinstance(peak_analysis.get("correction_context"), dict) else {}
    if not correction:
        return []
    reviewed_fields = [str(item).strip().lower() for item in correction.get("reviewed_context_fields", [])]
    normalized_type = correction_context_type.strip().lower().replace("-", "_").replace(" ", "_")
    relation = "matching_correction_context" if normalized_type and normalized_type in reviewed_fields else "available_correction_context"
    return [
        {
            "evidence_type": "correction_context",
            "evidence_ref": correction.get("record_ref") or "correction_context",
            "relation": relation,
            "reviewed_context_fields": correction.get("reviewed_context_fields", []),
            "confidence": correction.get("confidence"),
        }
    ]


def _normalize_uv_vis_interpretation_candidate(
    raw_candidate: Any,
    *,
    suggestion_id: str,
    number: int,
    metadata: dict[str, Any],
    features: pd.DataFrame,
    registered_references: set[str],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(raw_candidate, dict):
        candidate_id = f"{suggestion_id}-cand-{number:03d}"
        warnings.append(
            _warning(
                "uv_vis_interpretation_suggestion_ignored",
                "A UV-Vis interpretation suggestion candidate was not a mapping and was recorded as invalid.",
                severity="medium",
                candidate_id=candidate_id,
            )
        )
        return {
            "candidate_id": candidate_id,
            "candidate_type": "unknown",
            "status": "invalid_candidate_mapping",
            "requires_user_review": True,
            "auto_applied": False,
            "missing_fields": ["candidate_mapping"],
        }

    candidate_id = str(raw_candidate.get("candidate_id") or raw_candidate.get("suggestion_id") or f"{suggestion_id}-cand-{number:03d}")
    candidate_type = _normalize_uv_vis_candidate_type(raw_candidate.get("candidate_type") or raw_candidate.get("type"))
    reference_ids = _coerce_string_list(raw_candidate.get("reference_ids"))
    applicability_notes = _coerce_string_list(raw_candidate.get("applicability_notes"))
    caveats = _coerce_string_list(raw_candidate.get("caveats"))
    source_summary = str(raw_candidate.get("source_summary") or raw_candidate.get("reference_summary") or "").strip()
    confidence = str(raw_candidate.get("confidence") or "low").strip().lower()
    unresolved_reference_ids = [reference_id for reference_id in reference_ids if reference_id not in registered_references]
    optical_target = str(raw_candidate.get("optical_target") or raw_candidate.get("target") or "").strip()
    reported_energy = _candidate_number(raw_candidate, "reported_energy_eV", "expected_energy_eV", "energy_eV")
    energy_window = _candidate_window(raw_candidate, "energy_window_eV", "reported_energy_window_eV", "gap_window_eV")
    wavelength_window = _candidate_window(raw_candidate, "wavelength_window_nm", "reported_wavelength_window_nm", "window_nm")
    transition_model = str(raw_candidate.get("transition_model") or "").strip().lower().replace("-", "_").replace(" ", "_")
    transition_assumption = str(raw_candidate.get("transition_assumption") or raw_candidate.get("model_assumption") or "").strip()
    tauc_transform = str(raw_candidate.get("tauc_transform") or raw_candidate.get("transform") or "").strip() or None
    feature_label = str(raw_candidate.get("feature_label") or raw_candidate.get("assignment_label") or "").strip()
    expected_feature = _normalize_uv_vis_expected_feature(raw_candidate.get("expected_feature"))
    correction_context_type = str(raw_candidate.get("correction_context_type") or raw_candidate.get("correction_type") or "").strip()
    correction_method = str(raw_candidate.get("correction_method") or raw_candidate.get("method") or "").strip()

    missing_fields: list[str] = []
    if candidate_type not in {
        "optical_transition_model",
        "optical_gap_candidate",
        "optical_feature_assignment",
        "correction_context_candidate",
    }:
        missing_fields.append("candidate_type")
    if not source_summary:
        missing_fields.append("source_summary")
    if not reference_ids:
        missing_fields.append("reference_ids")
    if not applicability_notes:
        missing_fields.append("applicability_notes")

    evidence_matches: list[dict[str, Any]] = []
    matched_features: list[dict[str, Any]] = []
    requires_direct_match = False

    if candidate_type == "optical_transition_model":
        if not transition_model and not transition_assumption:
            missing_fields.append("transition_model_or_assumption")
        evidence_matches = _uv_vis_transition_evidence(metadata, transition_model)
    elif candidate_type == "optical_gap_candidate":
        requires_direct_match = True
        if not optical_target:
            missing_fields.append("optical_target")
        if reported_energy is None and energy_window is None:
            missing_fields.append("reported_energy_eV_or_energy_window_eV")
        if not transition_assumption:
            missing_fields.append("transition_assumption")
        evidence_matches, matched_features = _uv_vis_gap_evidence(
            metadata,
            features,
            energy_window=energy_window,
            expected_feature=expected_feature,
        )
    elif candidate_type == "optical_feature_assignment":
        requires_direct_match = True
        if not optical_target and not feature_label:
            missing_fields.append("optical_target_or_feature_label")
        if energy_window is None and wavelength_window is None and reported_energy is None:
            missing_fields.append("energy_or_wavelength_window")
        matched_features = _match_uv_vis_features(
            features,
            energy_window=energy_window,
            wavelength_window=wavelength_window,
            expected_feature=expected_feature,
        )
        evidence_matches = [
            {
                "evidence_type": "detected_feature",
                "evidence_ref": match.get("feature_id"),
                "energy_eV": match.get("energy_eV"),
                "wavelength_nm": match.get("wavelength_nm"),
                "feature_type": match.get("feature_type"),
            }
            for match in matched_features
        ]
    elif candidate_type == "correction_context_candidate":
        if not optical_target:
            missing_fields.append("optical_target")
        if not correction_context_type and not correction_method:
            missing_fields.append("correction_context_type_or_method")
        evidence_matches = _uv_vis_correction_evidence(metadata, correction_context_type)

    if missing_fields:
        status = "invalid_missing_required_metadata"
    elif unresolved_reference_ids:
        status = "needs_reference_registration"
    elif requires_direct_match and not evidence_matches:
        status = "no_evidence_match"
    else:
        status = "ready_for_user_review"

    evidence_refs = [str(item.get("evidence_ref")) for item in evidence_matches if item.get("evidence_ref")]
    candidate = {
        "candidate_id": candidate_id,
        "candidate_type": candidate_type or "unknown",
        "status": status,
        "requires_user_review": True,
        "auto_applied": False,
        "optical_target": optical_target or None,
        "evidence_status": "matched_processed_evidence" if evidence_matches else "source_context_only",
        "evidence_matches": evidence_matches,
        "evidence_refs": evidence_refs,
        "matched_feature_ids": [match["feature_id"] for match in matched_features if match.get("feature_id")],
        "matched_energies_eV": [match["energy_eV"] for match in matched_features if match.get("energy_eV") is not None],
        "matched_wavelengths_nm": [match["wavelength_nm"] for match in matched_features if match.get("wavelength_nm") is not None],
        "reported_energy_eV": reported_energy,
        "energy_window_eV": energy_window,
        "wavelength_window_nm": wavelength_window,
        "transition_model": transition_model or None,
        "transition_assumption": transition_assumption or None,
        "tauc_transform": tauc_transform,
        "feature_label": feature_label or None,
        "expected_feature": expected_feature,
        "correction_context_type": correction_context_type or None,
        "correction_method": correction_method or None,
        "source_summary": source_summary,
        "reference_ids": reference_ids,
        "unresolved_reference_ids": unresolved_reference_ids,
        "applicability_notes": applicability_notes,
        "confidence": confidence,
        "missing_fields": missing_fields,
        "caveats": caveats,
    }
    if unresolved_reference_ids:
        warnings.append(
            _warning(
                "uv_vis_interpretation_suggestion_reference_unresolved",
                "A UV-Vis interpretation suggestion cites reference_ids that are not registered in the project reference index.",
                severity="medium",
                candidate_id=candidate_id,
                unresolved_reference_ids=unresolved_reference_ids,
            )
        )
    if missing_fields:
        warnings.append(
            _warning(
                "uv_vis_interpretation_suggestion_missing_metadata",
                "A UV-Vis interpretation suggestion is missing required source, applicability, or candidate metadata.",
                severity="medium",
                candidate_id=candidate_id,
                missing_fields=missing_fields,
            )
        )
    if status == "no_evidence_match":
        warnings.append(
            _warning(
                "uv_vis_interpretation_suggestion_no_evidence_match",
                "A UV-Vis source-backed candidate did not match current processed UV-Vis feature/gap evidence.",
                severity="low",
                candidate_id=candidate_id,
                candidate_type=candidate_type,
            )
        )
    return candidate


def suggest_uv_vis_interpretations(
    root: Path,
    *,
    project_id: str,
    uv_vis_metadata_path: Path,
    source_path: Path,
    related_records: list[str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    resolved_metadata_path = uv_vis_metadata_path if uv_vis_metadata_path.is_absolute() else root / uv_vis_metadata_path
    resolved_source_path = source_path if source_path.is_absolute() else root / source_path
    uv_vis_metadata = read_yaml(resolved_metadata_path)
    source_packet = read_yaml(resolved_source_path)
    metadata_project_id = str(uv_vis_metadata.get("project_id") or "").strip()
    source_project_id = str(source_packet.get("project_id") or "").strip() if isinstance(source_packet, dict) else ""
    if metadata_project_id and project_id and metadata_project_id != project_id:
        raise UVVisProcessingError(f"Project ID mismatch: UV-Vis metadata has {metadata_project_id}, request has {project_id}")
    if source_project_id and project_id and source_project_id != project_id:
        raise UVVisProcessingError(f"Project ID mismatch: UV-Vis source packet has {source_project_id}, request has {project_id}")

    raw_candidates = _uv_vis_source_candidates(source_packet)
    peak_table_ref = uv_vis_metadata.get("outputs", {}).get("peak_table") if isinstance(uv_vis_metadata.get("outputs"), dict) else None
    features = pd.DataFrame()
    warnings: list[dict[str, Any]] = []
    if peak_table_ref:
        peak_table_path = root / str(peak_table_ref)
        if peak_table_path.exists():
            features = pd.read_csv(peak_table_path)
        else:
            warnings.append(
                _warning(
                    "uv_vis_interpretation_feature_table_missing",
                    "UV-Vis metadata references a feature table that does not exist; feature assignment matching was skipped.",
                    severity="medium",
                    feature_table_ref=str(peak_table_ref),
                )
            )
    else:
        warnings.append(
            _warning(
                "uv_vis_interpretation_feature_table_not_recorded",
                "UV-Vis metadata does not include outputs.peak_table; feature assignment matching was skipped.",
                severity="medium",
            )
        )
    if not raw_candidates:
        warnings.append(
            _warning(
                "uv_vis_interpretation_suggestion_empty_source",
                "No UV-Vis interpretation candidates were found in the source packet.",
                severity="medium",
            )
        )

    day = _created_day(created_at)
    timestamp = created_at or EARecord.now_iso()
    suggestion_id = next_id(root, "suggestion", day)
    output_dir = root / "suggestions" / "uv_vis" / suggestion_id
    record_path = output_dir / "uv_vis_interpretation_suggestions.yml"
    table_path = output_dir / "uv_vis_interpretation_suggestions.csv"
    for path in [record_path, table_path]:
        assert_not_raw_output_path(root, path)

    registered_references = _registered_reference_ids(root)
    candidates = [
        _normalize_uv_vis_interpretation_candidate(
            candidate,
            suggestion_id=suggestion_id,
            number=index,
            metadata=uv_vis_metadata,
            features=features,
            registered_references=registered_references,
            warnings=warnings,
        )
        for index, candidate in enumerate(raw_candidates, start=1)
    ]
    table = pd.DataFrame(candidates, columns=_uv_vis_interpretation_suggestion_columns())
    for column in [
        "evidence_refs",
        "matched_feature_ids",
        "matched_energies_eV",
        "matched_wavelengths_nm",
        "energy_window_eV",
        "wavelength_window_nm",
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
    no_match_count = sum(1 for candidate in candidates if candidate.get("status") == "no_evidence_match")
    invalid_count = sum(1 for candidate in candidates if str(candidate.get("status", "")).startswith("invalid"))
    if ready_count:
        status = "ready_for_user_review"
    elif unresolved_count:
        status = "needs_reference_registration"
    elif no_match_count:
        status = "no_evidence_match"
    else:
        status = "needs_source_metadata"

    source_ref = _relative_to_root(root, resolved_source_path)
    metadata_ref = _relative_to_root(root, resolved_metadata_path)
    record_ref = _relative_to_root(root, record_path)
    table_ref = _relative_to_root(root, table_path)
    related_records = related_records or []
    output_refs = uv_vis_metadata.get("outputs") if isinstance(uv_vis_metadata.get("outputs"), dict) else {}
    evidence_files = [
        str(ref)
        for ref in [
            peak_table_ref,
            output_refs.get("tauc_table"),
            output_refs.get("derivative_table"),
            output_refs.get("correction_context"),
        ]
        if ref
    ]
    all_reference_ids = sorted({reference_id for candidate in candidates for reference_id in candidate.get("reference_ids", [])})
    record = {
        "schema_version": "0.2",
        "suggestion_id": suggestion_id,
        "project_id": project_id,
        "method": "uv_vis",
        "status": status,
        "created_at": timestamp,
        "updated_at": timestamp,
        "source": "ea.uv_vis.interpretation_suggestions:v0.2",
        "source_packet_ref": source_ref,
        "uv_vis_metadata_ref": metadata_ref,
        "feature_table_ref": str(peak_table_ref) if peak_table_ref else None,
        "table_ref": table_ref,
        "candidate_count": len(candidates),
        "ready_for_user_review_count": ready_count,
        "needs_reference_registration_count": unresolved_count,
        "no_evidence_match_count": no_match_count,
        "invalid_count": invalid_count,
        "candidates": candidates,
        "related_records": related_records,
        "reference_ids": all_reference_ids,
        "warnings": warnings,
        "next_steps": [
            "Register or correct unresolved reference_ids before using source-backed UV-Vis suggestions as report evidence.",
            "Ask the user to review ready candidates before discussing them as project interpretations.",
            "Use evidence_refs, matched_feature_ids, source_summary, applicability_notes, confidence, and caveats when discussing possible optical models, gaps, features, or correction context.",
            "A later review-package/report/memory workflow must consume this suggestion record explicitly; this command does not create those artifacts.",
        ],
        "boundaries": [
            "UV-Vis interpretation suggestions are advisory and auto_applied is always false.",
            "This suggestion-record step is deterministic local analysis of supplied project artifacts. It does not perform live lookup, does not download or parse full text, does not register references, does not inject report citations, does not create review packages, does not alter processed UV-Vis outputs, does not apply optical models/corrections, does not prove band gaps/transition mechanisms/feature assignments/corrections, and does not write confirmed memory.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(table_path, index=False)
    write_yaml(record_path, record)
    provenance_path = write_provenance_entry(
        root,
        workflow="uv_vis_interpretation_suggestion",
        inputs={"records": [source_ref, metadata_ref, *related_records], "files": evidence_files},
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
        "no_evidence_match_count": no_match_count,
        "invalid_count": invalid_count,
        "warnings": warnings,
        "provenance": str(provenance_path),
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
    if status == "no_evidence_match":
        return "no_evidence_match"
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


def _uv_vis_candidate_parameter_values_text(candidate: dict[str, Any]) -> str:
    fields = [
        ("reported_energy_eV", candidate.get("reported_energy_eV")),
        ("energy_window_eV", candidate.get("energy_window_eV")),
        ("wavelength_window_nm", candidate.get("wavelength_window_nm")),
        ("transition_model", candidate.get("transition_model")),
        ("transition_assumption", candidate.get("transition_assumption")),
        ("tauc_transform", candidate.get("tauc_transform")),
        ("expected_feature", candidate.get("expected_feature")),
        ("correction_context_type", candidate.get("correction_context_type")),
        ("correction_method", candidate.get("correction_method")),
    ]
    parts = [f"{name}={_review_value(value)}" for name, value in fields if value not in (None, "", [], {})]
    return "; ".join(parts) if parts else "no supported UV-Vis interpretation values recorded"


def _memory_confidence(value: Any) -> str:
    normalized = str(value or "low").strip().lower()
    if normalized in {"high", "medium", "low", "insufficient"}:
        return normalized
    return "low"


def _format_memory_list(items: list[Any]) -> str:
    values = [str(item) for item in items if str(item).strip()]
    return ", ".join(values) if values else "none recorded"


def _normalize_review_target_ref(root: Path, value: Any) -> str:
    target = str(value or "").strip()
    if not target:
        return ""
    target_path = Path(target)
    if target_path.is_absolute():
        return _relative_to_root(root, target_path)
    return _relative_to_root(root, root / target_path)


def _uv_vis_candidate_is_valid_for_memory(candidate: dict[str, Any], *, allow_non_ready: bool) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    status = str(candidate.get("status") or "")
    candidate_type = str(candidate.get("candidate_type") or "")
    if status != "ready_for_user_review":
        reasons.append(f"status:{status or 'missing'}")
    if candidate.get("auto_applied") is not False:
        reasons.append("auto_applied_not_false")
    if candidate_type not in {
        "optical_transition_model",
        "optical_gap_candidate",
        "optical_feature_assignment",
        "correction_context_candidate",
    }:
        reasons.append("unsupported_candidate_type")
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
    if not str(candidate.get("optical_target") or candidate.get("feature_label") or "").strip():
        reasons.append("missing_optical_target_or_feature_label")
    if candidate_type in {"optical_gap_candidate", "optical_feature_assignment"} and not _coerce_string_list(candidate.get("evidence_refs")):
        reasons.append("missing_evidence_refs")

    if not allow_non_ready:
        return not reasons, reasons
    hard_blockers = {
        "auto_applied_not_false",
        "unsupported_candidate_type",
        "missing_required_metadata",
        "missing_source_summary",
        "missing_applicability_notes",
        "missing_optical_target_or_feature_label",
    }
    return not any(reason in hard_blockers or reason.startswith("status:invalid") for reason in reasons), reasons


def _format_uv_vis_interpretation_memory_text(candidate: dict[str, Any], *, suggestion_id: str, review_ref: str) -> str:
    candidate_id = str(candidate.get("candidate_id") or "unknown")
    candidate_type = str(candidate.get("candidate_type") or "unknown")
    status = str(candidate.get("status") or "unknown")
    optical_target = str(candidate.get("optical_target") or "not recorded")
    feature_label = str(candidate.get("feature_label") or "not recorded")
    evidence_refs = _format_memory_list(_coerce_string_list(candidate.get("evidence_refs")))
    matched_feature_ids = _format_memory_list(_coerce_string_list(candidate.get("matched_feature_ids")))
    matched_energies = _format_memory_list(_coerce_string_list(candidate.get("matched_energies_eV")))
    matched_wavelengths = _format_memory_list(_coerce_string_list(candidate.get("matched_wavelengths_nm")))
    reference_ids = _format_memory_list(_coerce_string_list(candidate.get("reference_ids")))
    applicability = _format_memory_list(_coerce_string_list(candidate.get("applicability_notes")))
    caveats = _format_memory_list(_coerce_string_list(candidate.get("caveats")))
    unresolved = _format_memory_list(_coerce_string_list(candidate.get("unresolved_reference_ids")))
    source_summary = str(candidate.get("source_summary") or "No source summary recorded.").strip()
    confidence = _memory_confidence(candidate.get("confidence"))
    parameter_values = _uv_vis_candidate_parameter_values_text(candidate)
    return (
        f"UV-Vis source-backed interpretation candidate `{candidate_id}` from suggestion `{suggestion_id}` was reviewed via `{review_ref}` "
        "and can be preserved as a draft interpretation memory candidate.\n\n"
        f"- candidate type: `{candidate_type}`\n"
        f"- suggestion status: `{status}`\n"
        f"- optical target: {optical_target}\n"
        f"- feature label: {feature_label}\n"
        f"- confidence: `{confidence}`\n"
        f"- parameter values: {parameter_values}\n"
        f"- evidence refs: {evidence_refs}\n"
        f"- matched feature IDs: {matched_feature_ids}\n"
        f"- matched energies (eV): {matched_energies}\n"
        f"- matched wavelengths (nm): {matched_wavelengths}\n"
        f"- references: {reference_ids}\n"
        f"- unresolved references: {unresolved}\n"
        f"- source summary: {source_summary}\n"
        f"- applicability notes: {applicability}\n"
        f"- caveats: {caveats}\n\n"
        "Boundary: this is a source-backed UV-Vis interpretation candidate only. It does not apply optical models or corrections, "
        "mutate processed spectra, prove a band gap, transition mechanism, feature assignment, material state, or correction validity, "
        "or replace the standard memory review/commit flow."
    )


def propose_uv_vis_interpretation_memory_candidates(
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
    if suggestion.get("source") != "ea.uv_vis.interpretation_suggestions:v0.2":
        raise UVVisProcessingError(f"Not a UV-Vis interpretation suggestion record: {suggestion_path}")

    suggestion_ref = _relative_to_root(root, resolved_suggestion_path)
    suggestion_project_id = str(suggestion.get("project_id") or "")
    if suggestion_project_id and project_id and suggestion_project_id != project_id:
        raise UVVisProcessingError(f"Project ID mismatch: suggestion has {suggestion_project_id}, request has {project_id}")

    review = require_confirmed_review(root, review_ref)
    review_target_ref = _normalize_review_target_ref(root, review.get("target_ref"))
    if review_target_ref and review_target_ref != suggestion_ref:
        raise UVVisProcessingError(
            f"ReviewRecord {review_ref} targets {review.get('target_ref')}, not UV-Vis interpretation suggestion {suggestion_ref}"
        )
    review_target_type = str(review.get("target_type") or "")
    if review_target_type and review_target_type != "uv_vis_interpretation_suggestions":
        raise UVVisProcessingError(
            f"ReviewRecord {review_ref} target_type is {review_target_type}, not uv_vis_interpretation_suggestions"
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
                "uv_vis_interpretation_memory_allow_non_ready_without_selection",
                "--allow-non-ready only applies to explicitly selected --candidate-id values; default selection still uses ready candidates.",
                severity="medium",
            )
        )

    source_refs = [
        suggestion_ref,
        str(suggestion.get("table_ref") or "").strip(),
        str(suggestion.get("source_packet_ref") or "").strip(),
        str(suggestion.get("uv_vis_metadata_ref") or "").strip(),
        str(suggestion.get("feature_table_ref") or "").strip(),
        *[str(ref).strip() for ref in suggestion.get("related_records", []) or []],
    ]
    source_refs = [ref for ref in source_refs if ref]
    provenance_refs = [str(suggestion.get("provenance_ref") or "").strip()]
    provenance_refs = [ref for ref in provenance_refs if ref]
    if not provenance_refs:
        raise UVVisProcessingError("UV-Vis interpretation suggestion record lacks provenance_ref")

    proposed: list[dict[str, Any]] = []
    output_refs: list[str] = []
    for candidate in selected:
        candidate_id = str(candidate.get("candidate_id") or "")
        candidate_allow_non_ready = bool(allow_non_ready and requested_set and candidate_id in requested_set)
        eligible, reasons = _uv_vis_candidate_is_valid_for_memory(candidate, allow_non_ready=candidate_allow_non_ready)
        if not eligible:
            skipped.append({"candidate_id": candidate_id, "reason": "not_memory_candidate_eligible", "details": reasons})
            continue

        candidate_text = _format_uv_vis_interpretation_memory_text(
            candidate,
            suggestion_id=str(suggestion.get("suggestion_id") or resolved_suggestion_path.parent.name),
            review_ref=review_ref,
        )
        rationale = (
            f"Generated from UV-Vis interpretation suggestion `{suggestion_ref}` candidate `{candidate_id}` after confirmed review `{review_ref}`. "
            "This preserves a source-backed optical interpretation candidate for later user review and commit; it does not create confirmed memory, apply models/corrections, or prove optical claims."
        )
        memory_path = propose_memory_candidate(
            root,
            project_id=project_id or suggestion_project_id,
            candidate_text=candidate_text,
            source_refs=source_refs + _coerce_string_list(candidate.get("reference_ids")),
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
                "category": "interpretation",
                "confidence": _memory_confidence(candidate.get("confidence")),
                "source_refs": source_refs,
                "provenance_refs": provenance_refs,
            }
        )

    bridge_provenance = None
    if proposed:
        bridge_provenance_path = write_provenance_entry(
            root,
            workflow="uv_vis_interpretation_memory_candidate_proposal",
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
            "Ready UV-Vis interpretation candidates are used by default; non-ready candidates require explicit --candidate-id plus --allow-non-ready and remain caveated.",
            "UV-Vis interpretation suggestions do not by themselves apply optical models/corrections, mutate processed spectra, prove band gaps, transition mechanisms, feature assignments, material state, correction validity, or replace user review.",
        ],
    }


def _uv_vis_review_candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    status = str(candidate.get("status") or "unknown")
    candidate_type = str(candidate.get("candidate_type") or "unknown")
    if status == "ready_for_user_review":
        action = (
            "Ask the user to accept, reject, or edit this source-backed UV-Vis interpretation candidate before any report "
            "or memory reuse; keep it as an interpretation candidate, not proof."
        )
    elif status == "needs_reference_registration":
        action = "Register, replace, or remove unresolved reference_ids before treating this candidate as report evidence."
    elif status == "no_evidence_match":
        action = (
            "Treat as no-match context unless the user changes processed UV-Vis evidence, feature detection, or the source "
            "candidate window/model."
        )
    elif status.startswith("invalid"):
        action = "Fix missing source, applicability, candidate, or reference metadata before user review."
    else:
        action = "Inspect status and decide whether more source/context work is needed."
    return {
        "candidate_id": str(candidate.get("candidate_id") or ""),
        "review_group": _review_group_for_status(status),
        "status": status,
        "candidate_type": candidate_type,
        "optical_target": str(candidate.get("optical_target") or "not recorded"),
        "feature_label": str(candidate.get("feature_label") or "not recorded"),
        "confidence": str(candidate.get("confidence") or "low"),
        "evidence_status": str(candidate.get("evidence_status") or "not recorded"),
        "evidence_refs": _coerce_string_list(candidate.get("evidence_refs")),
        "matched_feature_ids": _coerce_string_list(candidate.get("matched_feature_ids")),
        "matched_energies_eV": _coerce_string_list(candidate.get("matched_energies_eV")),
        "matched_wavelengths_nm": _coerce_string_list(candidate.get("matched_wavelengths_nm")),
        "parameter_values": _uv_vis_candidate_parameter_values_text(candidate),
        "reference_ids": _coerce_string_list(candidate.get("reference_ids")),
        "unresolved_reference_ids": _coerce_string_list(candidate.get("unresolved_reference_ids")),
        "missing_fields": _coerce_string_list(candidate.get("missing_fields")),
        "source_summary": str(candidate.get("source_summary") or "not recorded"),
        "applicability_notes": _coerce_string_list(candidate.get("applicability_notes")),
        "caveats": _coerce_string_list(candidate.get("caveats")),
        "recommended_action": action,
    }


def _render_uv_vis_review_package_markdown(package: dict[str, Any]) -> str:
    lines = [
        "# UV-Vis Interpretation Suggestion Review Package",
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
                f"- candidate_type: `{candidate.get('candidate_type')}`",
                f"- optical_target: `{candidate.get('optical_target')}`",
                f"- feature_label: `{candidate.get('feature_label')}`",
                f"- parameter_values: {candidate.get('parameter_values')}",
                f"- evidence_status: `{candidate.get('evidence_status')}`",
                f"- evidence_refs: `{_review_value(candidate.get('evidence_refs'))}`",
                f"- matched_feature_ids: `{_review_value(candidate.get('matched_feature_ids'))}`",
                f"- matched_energies_eV: `{_review_value(candidate.get('matched_energies_eV'))}`",
                f"- matched_wavelengths_nm: `{_review_value(candidate.get('matched_wavelengths_nm'))}`",
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


def prepare_uv_vis_interpretation_review_package(
    root: Path,
    *,
    project_id: str,
    suggestion_path: Path,
    candidate_ids: list[str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    resolved_suggestion_path = suggestion_path if suggestion_path.is_absolute() else root / suggestion_path
    suggestion = read_yaml(resolved_suggestion_path)
    if suggestion.get("source") != "ea.uv_vis.interpretation_suggestions:v0.2":
        raise UVVisProcessingError(f"Not a UV-Vis interpretation suggestion record: {suggestion_path}")

    suggestion_ref = _relative_to_root(root, resolved_suggestion_path)
    suggestion_project_id = str(suggestion.get("project_id") or "")
    if suggestion_project_id and project_id and suggestion_project_id != project_id:
        raise UVVisProcessingError(f"Project ID mismatch: suggestion has {suggestion_project_id}, request has {project_id}")

    candidates = [candidate for candidate in suggestion.get("candidates", []) if isinstance(candidate, dict)]
    requested_ids = [str(candidate_id) for candidate_id in candidate_ids or [] if str(candidate_id).strip()]
    requested_set = set(requested_ids)
    selected = [candidate for candidate in candidates if not requested_set or str(candidate.get("candidate_id")) in requested_set]
    found_ids = {str(candidate.get("candidate_id")) for candidate in selected}
    missing_candidate_ids = [candidate_id for candidate_id in requested_ids if candidate_id not in found_ids]
    warnings: list[dict[str, Any]] = [
        _warning(
            "uv_vis_review_package_candidate_not_found",
            "A requested UV-Vis interpretation suggestion candidate_id was not found in the suggestion record.",
            severity="medium",
            candidate_id=candidate_id,
        )
        for candidate_id in missing_candidate_ids
    ]

    summaries = [_uv_vis_review_candidate_summary(candidate) for candidate in selected]
    group_actions = {
        "ready_for_user_review": "Review these candidates with the user; create a ReviewRecord only after explicit confirmation.",
        "needs_reference_registration": "Resolve references first with `ea references register-seeds` or `ea references add`, then regenerate suggestions or review with caveats.",
        "no_evidence_match": "Treat as no-match context unless processed evidence or source candidate windows/models are changed.",
        "invalid_or_incomplete": "Fix candidate metadata before asking the user to review.",
        "other": "Inspect manually before downstream use.",
    }
    groups = []
    for group_name in ["ready_for_user_review", "needs_reference_registration", "no_evidence_match", "invalid_or_incomplete", "other"]:
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
        "method": "uv_vis",
        "source": "ea.uv_vis.interpretation_review_package:v0.2",
        "status": "review_package_prepared" if selected else "no_candidates_selected",
        "created_at": timestamp,
        "updated_at": timestamp,
        "suggestion_id": suggestion.get("suggestion_id"),
        "suggestion_ref": suggestion_ref,
        "table_ref": suggestion.get("table_ref"),
        "source_packet_ref": suggestion.get("source_packet_ref"),
        "uv_vis_metadata_ref": suggestion.get("uv_vis_metadata_ref"),
        "feature_table_ref": suggestion.get("feature_table_ref"),
        "related_records": suggestion.get("related_records") or [],
        "review_target_type": "uv_vis_interpretation_suggestions",
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
                "ea review add /path/to/ea-project --target-type uv_vis_interpretation_suggestions "
                f"--target-ref {suggestion_ref} --user-response \"可以，保存\" "
                "--reviewed-content \"User reviewed the listed UV-Vis interpretation candidates; record accepted/rejected/edited candidate IDs.\""
            ),
            "rerun_after_reference_registration": (
                "ea uv-vis suggest-interpretations /path/to/ea-project --metadata <uv_vis_metadata.yml> "
                f"--source-file {suggestion.get('source_packet_ref') or '<uv_vis_source_packet.yml>'}"
            ),
            "propose_memory_after_review": (
                f"ea uv-vis propose-memory /path/to/ea-project --suggestion {suggestion_ref} --review-ref <review-id>"
            ),
        },
        "next_steps": [
            "Ask the user to review ready candidates and state which candidate IDs are accepted, rejected, edited, or deferred.",
            "Resolve unresolved references before using candidates as report evidence unless a later report explicitly discusses them as unresolved.",
            "After a confirmed ReviewRecord targets this suggestion record, a later report/memory workflow may consume only the user-approved candidate set.",
        ],
        "boundaries": [
            "This package prepares review context only; it does not create a ReviewRecord.",
            "It does not apply UV-Vis optical models or corrections, alter processed UV-Vis outputs, inject report citations, write confirmed memory, or prove band gaps/transition mechanisms/feature assignments/corrections.",
            "Unresolved, no-match, or invalid candidates remain visible so the user can decide whether to fix, exclude, or discuss them with caveats.",
        ],
        "warnings": warnings,
    }
    write_yaml(package_path, package)
    markdown_path.write_text(_render_uv_vis_review_package_markdown(package), encoding="utf-8")
    provenance_path = write_provenance_entry(
        root,
        workflow="uv_vis_interpretation_review_package",
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
    markdown_path.write_text(_render_uv_vis_review_package_markdown(package), encoding="utf-8")
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
    }


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _warning_codes(values: Any) -> list[str]:
    codes: list[str] = []
    if not isinstance(values, list):
        return codes
    for item in values:
        if isinstance(item, dict):
            code = str(item.get("code") or "").strip()
            if code:
                codes.append(code)
        elif str(item).strip():
            codes.append(str(item))
    return codes


def _read_uv_vis_feature_table(
    root: Path,
    *,
    metadata: dict[str, Any],
    metadata_ref: str,
    warnings: list[dict[str, Any]],
) -> pd.DataFrame:
    outputs = metadata.get("outputs") if isinstance(metadata.get("outputs"), dict) else {}
    peak_table_ref = outputs.get("peak_table")
    if not peak_table_ref:
        warnings.append(
            _warning(
                "uv_vis_comparison_feature_table_not_recorded",
                "UV-Vis comparison could not read feature positions because outputs.peak_table was not recorded.",
                severity="medium",
                metadata_ref=metadata_ref,
            )
        )
        return pd.DataFrame()
    peak_table_path = root / str(peak_table_ref)
    if not peak_table_path.exists():
        warnings.append(
            _warning(
                "uv_vis_comparison_feature_table_missing",
                "UV-Vis comparison could not read feature positions because the referenced peak table is missing.",
                severity="medium",
                metadata_ref=metadata_ref,
                peak_table_ref=str(peak_table_ref),
            )
        )
        return pd.DataFrame()
    try:
        return pd.read_csv(peak_table_path)
    except Exception as exc:  # pragma: no cover - defensive guard for malformed user CSVs
        warnings.append(
            _warning(
                "uv_vis_comparison_feature_table_unreadable",
                "UV-Vis comparison could not read the referenced feature table.",
                severity="medium",
                metadata_ref=metadata_ref,
                peak_table_ref=str(peak_table_ref),
                error=str(exc),
            )
        )
        return pd.DataFrame()


def _feature_values(features: pd.DataFrame, column: str) -> list[float]:
    if features.empty or column not in features.columns:
        return []
    values: list[float] = []
    for value in features[column].tolist():
        number = _finite_float(value)
        if number is not None:
            values.append(number)
    return values


def _feature_ids(features: pd.DataFrame) -> list[str]:
    if features.empty or "feature_id" not in features.columns:
        return []
    return [str(value) for value in features["feature_id"].tolist() if str(value).strip()]


def _feature_records(features: pd.DataFrame) -> list[dict[str, Any]]:
    if features.empty:
        return []
    records: list[dict[str, Any]] = []
    for index, (_, feature) in enumerate(features.iterrows(), start=1):
        feature_id = str(feature.get("feature_id") or f"feature-{index:03d}").strip()
        records.append(
            {
                "feature_index": index,
                "feature_id": feature_id,
                "energy_eV": _finite_float(feature.get("energy_eV")),
                "wavelength_nm": _finite_float(feature.get("wavelength_nm")),
            }
        )
    return records


def _uv_vis_comparison_entry(
    root: Path,
    *,
    metadata_path: Path,
    metadata_ref: str,
    project_id: str,
    index: int,
    warnings: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    metadata = read_yaml(metadata_path)
    metadata_project_id = str(metadata.get("project_id") or "").strip()
    if metadata_project_id and project_id and metadata_project_id != project_id:
        raise UVVisProcessingError(f"Project ID mismatch: UV-Vis metadata {metadata_ref} has {metadata_project_id}, request has {project_id}")
    if not metadata.get("uv_vis_result_id") and not metadata.get("result_id"):
        raise UVVisProcessingError(f"Not a UV-Vis processed metadata record: {metadata_ref}")

    outputs = metadata.get("outputs") if isinstance(metadata.get("outputs"), dict) else {}
    peak_analysis = metadata.get("peak_analysis") if isinstance(metadata.get("peak_analysis"), dict) else {}
    edge = peak_analysis.get("edge_estimate") if isinstance(peak_analysis.get("edge_estimate"), dict) else {}
    tauc = peak_analysis.get("tauc_analysis") if isinstance(peak_analysis.get("tauc_analysis"), dict) else {}
    derivative = peak_analysis.get("derivative_analysis") if isinstance(peak_analysis.get("derivative_analysis"), dict) else {}
    correction = peak_analysis.get("correction_context") if isinstance(peak_analysis.get("correction_context"), dict) else {}
    processing_parameters = metadata.get("processing_parameters") if isinstance(metadata.get("processing_parameters"), dict) else {}
    feature_parameters = processing_parameters.get("feature_detection") if isinstance(processing_parameters.get("feature_detection"), dict) else {}
    features = _read_uv_vis_feature_table(root, metadata=metadata, metadata_ref=metadata_ref, warnings=warnings)
    feature_count = metadata.get("peak_analysis", {}).get("feature_count") if isinstance(metadata.get("peak_analysis"), dict) else None
    try:
        feature_count_value = int(feature_count) if feature_count is not None else int(len(features))
    except (TypeError, ValueError):
        feature_count_value = int(len(features))

    data_refs = [
        str(value)
        for value in [
            outputs.get("peak_table"),
            outputs.get("processed_csv"),
            outputs.get("tauc_table"),
            outputs.get("derivative_table"),
            outputs.get("correction_context"),
        ]
        if value
    ]
    entry = {
        "entry_index": index,
        "metadata_ref": metadata_ref,
        "result_id": str(metadata.get("result_id") or ""),
        "uv_vis_result_id": str(metadata.get("uv_vis_result_id") or metadata.get("result_id") or ""),
        "characterization_file_ref": str(metadata.get("characterization_file_ref") or ""),
        "sample_refs": _coerce_string_list(metadata.get("sample_refs")),
        "status": str(metadata.get("status") or "unknown"),
        "x_unit": str(metadata.get("x_unit") or "unknown"),
        "signal_mode": str(metadata.get("signal_mode") or "unknown"),
        "feature_detection_method": str(feature_parameters.get("method") or "unknown"),
        "feature_count": feature_count_value,
        "feature_ids": _feature_ids(features),
        "feature_positions_eV": _feature_values(features, "energy_eV"),
        "feature_positions_nm": _feature_values(features, "wavelength_nm"),
        "features": _feature_records(features),
        "edge_energy_eV": _finite_float(edge.get("energy_eV")),
        "edge_wavelength_nm": _finite_float(edge.get("wavelength_nm")),
        "edge_confidence": str(edge.get("confidence") or "not_recorded"),
        "tauc_status": str(tauc.get("status") or "not_recorded"),
        "tauc_intercept_energy_eV": _finite_float(tauc.get("intercept_energy_eV")),
        "tauc_transition": str(tauc.get("transition") or "not_recorded"),
        "tauc_transform": str(tauc.get("transform") or "not_recorded"),
        "tauc_confidence": str(tauc.get("confidence") or "not_recorded"),
        "derivative_available": bool(outputs.get("derivative_table") or derivative),
        "derivative_status": str(derivative.get("status") or "not_recorded"),
        "correction_context_available": bool(outputs.get("correction_context") or correction),
        "correction_context_status": str(correction.get("status") or "not_recorded"),
        "warning_codes": _warning_codes(metadata.get("warnings")),
        "review_refs": _coerce_string_list(metadata.get("review_refs")),
        "provenance_refs": _coerce_string_list(metadata.get("provenance_refs")),
        "source_refs": _coerce_string_list(metadata.get("source_refs")),
        "associated_output_refs": data_refs,
    }
    return entry, data_refs


def _csv_join(value: Any) -> Any:
    if isinstance(value, list | tuple):
        return "; ".join(str(item) for item in value)
    return value


def _basis_values(entries: list[dict[str, Any]], value_key: str, basis_keys: list[str]) -> list[dict[str, Any]]:
    basis: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for entry in entries:
        if entry.get(value_key) is None:
            continue
        key = tuple(str(entry.get(basis_key) or "unknown") for basis_key in basis_keys)
        if key in seen:
            continue
        seen.add(key)
        basis.append({basis_key: key[index] for index, basis_key in enumerate(basis_keys)})
    return basis


def _numeric_missing_data(entries: list[dict[str, Any]], value_key: str, metric: str) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    for entry in entries:
        if entry.get(value_key) is not None:
            continue
        missing.append(
            {
                "metadata_ref": str(entry.get("metadata_ref") or ""),
                "result_id": str(entry.get("result_id") or ""),
                "reason": f"{metric}_missing_or_non_numeric",
            }
        )
    return missing


def _descriptive_statistics(
    entries: list[dict[str, Any]],
    *,
    metric: str,
    value_key: str,
    basis_keys: list[str],
) -> dict[str, Any]:
    values = [_finite_float(entry.get(value_key)) for entry in entries]
    values = [value for value in values if value is not None]
    missing = _numeric_missing_data(entries, value_key, metric)
    basis = _basis_values(entries, value_key, basis_keys)
    if not values:
        return {
            "metric": metric,
            "status": "no_numeric_values",
            "count": 0,
            "basis_keys": basis_keys,
            "basis_values": basis,
            "missing_data": missing,
        }
    if len(basis) > 1:
        return {
            "metric": metric,
            "status": "not_comparable",
            "count": len(values),
            "basis_keys": basis_keys,
            "basis_values": basis,
            "missing_data": missing,
            "reason": "Numeric values were present, but comparison basis values differ.",
        }
    array = np.asarray(values, dtype=float)
    return {
        "metric": metric,
        "status": "descriptive_statistics_recorded",
        "count": int(array.size),
        "mean": float(np.mean(array)),
        "std_population": float(np.std(array, ddof=0)),
        "min": float(np.min(array)),
        "max": float(np.max(array)),
        "basis_keys": basis_keys,
        "basis_values": basis,
        "missing_data": missing,
        "boundary": "Descriptive statistics only; not a proof of band gap, transition type, optical mechanism, sample ranking, or replicate equivalence.",
    }


def _positive_match_tolerance(value: float | None, label: str) -> float | None:
    if value is None:
        return None
    number = _finite_float(value)
    if number is None or number <= 0:
        raise UVVisProcessingError(f"{label} must be a positive finite number when feature matching is requested")
    return number


def _feature_group_statistics(values: list[float]) -> dict[str, Any]:
    array = np.asarray(values, dtype=float)
    return {
        "count": int(array.size),
        "mean": float(np.mean(array)),
        "std_population": float(np.std(array, ddof=0)),
        "min": float(np.min(array)),
        "max": float(np.max(array)),
    }


def _feature_match_members(entries: list[dict[str, Any]], axis_key: str) -> list[dict[str, Any]]:
    members: list[dict[str, Any]] = []
    for entry in entries:
        for feature in entry.get("features", []):
            axis_value = _finite_float(feature.get(axis_key))
            if axis_value is None:
                continue
            members.append(
                {
                    "metadata_ref": str(entry.get("metadata_ref") or ""),
                    "result_id": str(entry.get("result_id") or ""),
                    "uv_vis_result_id": str(entry.get("uv_vis_result_id") or ""),
                    "sample_refs": _coerce_string_list(entry.get("sample_refs")),
                    "feature_id": str(feature.get("feature_id") or ""),
                    "feature_index": feature.get("feature_index"),
                    "axis_value": axis_value,
                    "energy_eV": _finite_float(feature.get("energy_eV")),
                    "wavelength_nm": _finite_float(feature.get("wavelength_nm")),
                }
            )
    return sorted(members, key=lambda item: item["axis_value"])


def _feature_match_group_record(
    *,
    group_id: str,
    axis_key: str,
    members: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    values = [float(member["axis_value"]) for member in members]
    metadata_refs = sorted({str(member.get("metadata_ref") or "") for member in members if member.get("metadata_ref")})
    result_ids = sorted({str(member.get("result_id") or "") for member in members if member.get("result_id")})
    sample_refs = sorted({sample_ref for member in members for sample_ref in _coerce_string_list(member.get("sample_refs"))})
    duplicate_metadata_refs = sorted(
        {
            metadata_ref
            for metadata_ref in metadata_refs
            if sum(1 for member in members if member.get("metadata_ref") == metadata_ref) > 1
        }
    )
    if duplicate_metadata_refs:
        warnings.append(
            _warning(
                "uv_vis_feature_matching_duplicate_record_member",
                "A reviewed UV-Vis feature-match group contains more than one feature from the same metadata record.",
                severity="medium",
                group_id=group_id,
                metadata_refs=duplicate_metadata_refs,
            )
        )
    distinct_record_count = len(metadata_refs)
    status = "multi_record_candidate_match" if distinct_record_count >= 2 else "single_record_context"
    confidence = "low" if distinct_record_count >= 2 else "insufficient_replicate_context"
    return {
        "group_id": group_id,
        "axis_key": axis_key,
        "status": status,
        "confidence": confidence,
        "confidence_reason": "Grouped by reviewed numeric tolerance only; not an optical feature assignment or transition proof.",
        "feature_ids": [str(member.get("feature_id") or "") for member in members if member.get("feature_id")],
        "metadata_refs": metadata_refs,
        "result_ids": result_ids,
        "sample_refs": sample_refs,
        "duplicate_metadata_refs": duplicate_metadata_refs,
        "members": members,
        "statistics": _feature_group_statistics(values),
        "boundary": "Reviewed tolerance grouping only; this does not prove common optical origin, band gap, transition mechanism, correction validity, sample ranking, or replicate equivalence.",
    }


def _feature_match_axis_groups(
    entries: list[dict[str, Any]],
    *,
    axis_key: str,
    tolerance: float,
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    members = _feature_match_members(entries, axis_key)
    if not members:
        return {
            "status": "no_matchable_features",
            "axis_key": axis_key,
            "tolerance": tolerance,
            "confidence": "insufficient_data",
            "group_count": 0,
            "multi_record_group_count": 0,
            "groups": [],
        }

    pending_groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_center: float | None = None
    for member in members:
        axis_value = float(member["axis_value"])
        if not current:
            current = [member]
            current_center = axis_value
            continue
        if current_center is not None and abs(axis_value - current_center) <= tolerance:
            current.append(member)
            current_center = float(np.mean([float(item["axis_value"]) for item in current]))
        else:
            pending_groups.append(current)
            current = [member]
            current_center = axis_value
    if current:
        pending_groups.append(current)

    axis_slug = axis_key.replace("_", "-")
    groups = [
        _feature_match_group_record(
            group_id=f"uvvis-feature-match-{axis_slug}-{index:03d}",
            axis_key=axis_key,
            members=group_members,
            warnings=warnings,
        )
        for index, group_members in enumerate(pending_groups, start=1)
    ]
    return {
        "status": "feature_match_groups_recorded",
        "axis_key": axis_key,
        "tolerance": tolerance,
        "grouping_method": "sorted_greedy_center_with_reviewed_tolerance",
        "confidence": "low",
        "confidence_reason": "Feature grouping uses a user-reviewed numeric tolerance and existing feature tables only.",
        "member_count": len(members),
        "group_count": len(groups),
        "multi_record_group_count": sum(1 for group in groups if group["status"] == "multi_record_candidate_match"),
        "groups": groups,
        "boundary": "Axis-specific feature grouping is advisory and does not assign optical transitions or prove band gaps.",
    }


def _build_feature_matching_record(
    entries: list[dict[str, Any]],
    *,
    energy_tolerance_eV: float | None,
    wavelength_tolerance_nm: float | None,
    review_ref: str | None,
    review: dict[str, Any] | None,
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    if energy_tolerance_eV is None and wavelength_tolerance_nm is None:
        return {
            "enabled": False,
            "status": "disabled",
            "reason": "No reviewed feature-match tolerance was provided; feature positions remain listed per record only.",
        }

    axes: dict[str, Any] = {}
    if energy_tolerance_eV is not None:
        axes["energy_eV"] = _feature_match_axis_groups(entries, axis_key="energy_eV", tolerance=energy_tolerance_eV, warnings=warnings)
    if wavelength_tolerance_nm is not None:
        axes["wavelength_nm"] = _feature_match_axis_groups(
            entries,
            axis_key="wavelength_nm",
            tolerance=wavelength_tolerance_nm,
            warnings=warnings,
        )
    group_count = sum(int(axis.get("group_count") or 0) for axis in axes.values())
    status = "reviewed_feature_matching_recorded" if group_count else "no_matchable_features"
    return {
        "enabled": True,
        "status": status,
        "review_ref": review_ref,
        "review_target_type": str((review or {}).get("target_type") or ""),
        "review_target_ref": str((review or {}).get("target_ref") or ""),
        "tolerances": {
            "energy_eV": energy_tolerance_eV,
            "wavelength_nm": wavelength_tolerance_nm,
        },
        "axes": axes,
        "group_count": group_count,
        "multi_record_group_count": sum(int(axis.get("multi_record_group_count") or 0) for axis in axes.values()),
        "confidence": "low",
        "confidence_reason": "Feature matching is based on explicit reviewed tolerance parameters and existing feature tables.",
        "boundaries": [
            "Reviewed feature matching reads existing UV-Vis feature tables only.",
            "It does not reprocess raw data, silently group peaks, apply optical models or corrections, inject citations, create ReviewRecords, write memory, rank samples, or prove optical assignments.",
            "Groups are candidate alignment aids for discussion and traceability; scientific conclusions require source-backed interpretation and user review.",
        ],
    }


def compare_uv_vis_replicates(
    root: Path,
    *,
    project_id: str,
    metadata_paths: list[Path],
    comparison_label: str | None = None,
    feature_match_tolerance_eV: float | None = None,
    feature_match_tolerance_nm: float | None = None,
    feature_match_review_ref: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    if len(metadata_paths) < 2:
        raise UVVisProcessingError("UV-Vis replicate comparison requires at least two --metadata records")

    energy_tolerance_eV = _positive_match_tolerance(feature_match_tolerance_eV, "feature_match_tolerance_eV")
    wavelength_tolerance_nm = _positive_match_tolerance(feature_match_tolerance_nm, "feature_match_tolerance_nm")
    feature_matching_requested = energy_tolerance_eV is not None or wavelength_tolerance_nm is not None
    feature_match_review: dict[str, Any] | None = None
    if feature_matching_requested:
        if not feature_match_review_ref:
            raise UVVisProcessingError("Reviewed UV-Vis feature matching requires --feature-match-review-ref")
        feature_match_review = require_confirmed_review(root, feature_match_review_ref)
        review_target_type = str(feature_match_review.get("target_type") or "")
        if review_target_type and review_target_type not in {"uv_vis_feature_matching", "uv_vis_replicate_feature_matching"}:
            raise UVVisProcessingError(
                f"ReviewRecord {feature_match_review_ref} target_type is {review_target_type}, not uv_vis_feature_matching"
            )
    elif feature_match_review_ref:
        raise UVVisProcessingError("--feature-match-review-ref was provided, but no feature-match tolerance was set")

    day = _created_day(created_at)
    timestamp = created_at or EARecord.now_iso()
    comparison_id = next_id(root, "uv_vis_comparison", day)
    output_dir = root / "processed" / "comparisons" / "uv_vis" / comparison_id
    record_path = output_dir / "uv_vis_comparison.yml"
    table_path = output_dir / "uv_vis_comparison.csv"
    for path in [record_path, table_path]:
        assert_not_raw_output_path(root, path)

    warnings: list[dict[str, Any]] = []
    entries: list[dict[str, Any]] = []
    input_metadata_refs: list[str] = []
    input_files: list[str] = []
    seen_metadata_refs: set[str] = set()
    for index, metadata_path in enumerate(metadata_paths, start=1):
        resolved_path = metadata_path if metadata_path.is_absolute() else root / metadata_path
        metadata_ref = _relative_to_root(root, resolved_path)
        if metadata_ref in seen_metadata_refs:
            warnings.append(
                _warning(
                    "uv_vis_comparison_duplicate_metadata",
                    "The same UV-Vis metadata record was supplied more than once.",
                    severity="medium",
                    metadata_ref=metadata_ref,
                )
            )
        seen_metadata_refs.add(metadata_ref)
        input_metadata_refs.append(metadata_ref)
        entry, data_refs = _uv_vis_comparison_entry(
            root,
            metadata_path=resolved_path,
            metadata_ref=metadata_ref,
            project_id=project_id,
            index=index,
            warnings=warnings,
        )
        entries.append(entry)
        input_files.extend(data_refs)

    feature_matching = _build_feature_matching_record(
        entries,
        energy_tolerance_eV=energy_tolerance_eV,
        wavelength_tolerance_nm=wavelength_tolerance_nm,
        review_ref=feature_match_review_ref,
        review=feature_match_review,
        warnings=warnings,
    )
    statistics = {
        "edge_energy_eV": _descriptive_statistics(entries, metric="edge_energy_eV", value_key="edge_energy_eV", basis_keys=["signal_mode"]),
        "edge_wavelength_nm": _descriptive_statistics(entries, metric="edge_wavelength_nm", value_key="edge_wavelength_nm", basis_keys=["signal_mode"]),
        "tauc_intercept_energy_eV": _descriptive_statistics(
            entries,
            metric="tauc_intercept_energy_eV",
            value_key="tauc_intercept_energy_eV",
            basis_keys=["signal_mode", "tauc_transition", "tauc_transform"],
        ),
        "feature_count": _descriptive_statistics(
            entries,
            metric="feature_count",
            value_key="feature_count",
            basis_keys=["signal_mode", "feature_detection_method"],
        ),
        "feature_positions": {
            "status": "reviewed_feature_matching_recorded" if feature_matching["enabled"] else "not_statistically_matched",
            "review_ref": feature_match_review_ref,
            "axes": sorted(feature_matching.get("axes", {}).keys()) if feature_matching["enabled"] else [],
            "group_count": feature_matching.get("group_count", 0),
            "reason": (
                "Detected feature positions were grouped only on axes with explicit reviewed tolerances."
                if feature_matching["enabled"]
                else "Detected feature positions are listed per record but are not averaged because no reviewed matching tolerance was provided."
            ),
            "boundary": "Feature-position groups are advisory tolerance records, not optical assignments, transition proofs, sample rankings, or replicate-equivalence proofs.",
        },
    }
    missing_data = {
        "edge_energy_eV": statistics["edge_energy_eV"]["missing_data"],
        "edge_wavelength_nm": statistics["edge_wavelength_nm"]["missing_data"],
        "tauc_intercept_energy_eV": statistics["tauc_intercept_energy_eV"]["missing_data"],
        "feature_count": statistics["feature_count"]["missing_data"],
    }
    table_rows = [
        {
            "entry_index": entry["entry_index"],
            "metadata_ref": entry["metadata_ref"],
            "result_id": entry["result_id"],
            "sample_refs": _csv_join(entry["sample_refs"]),
            "status": entry["status"],
            "x_unit": entry["x_unit"],
            "signal_mode": entry["signal_mode"],
            "feature_detection_method": entry["feature_detection_method"],
            "feature_count": entry["feature_count"],
            "feature_ids": _csv_join(entry["feature_ids"]),
            "feature_positions_eV": _csv_join(entry["feature_positions_eV"]),
            "feature_positions_nm": _csv_join(entry["feature_positions_nm"]),
            "edge_energy_eV": entry["edge_energy_eV"],
            "edge_wavelength_nm": entry["edge_wavelength_nm"],
            "edge_confidence": entry["edge_confidence"],
            "tauc_intercept_energy_eV": entry["tauc_intercept_energy_eV"],
            "tauc_transition": entry["tauc_transition"],
            "tauc_transform": entry["tauc_transform"],
            "tauc_confidence": entry["tauc_confidence"],
            "derivative_available": entry["derivative_available"],
            "derivative_status": entry["derivative_status"],
            "correction_context_available": entry["correction_context_available"],
            "correction_context_status": entry["correction_context_status"],
            "warning_codes": _csv_join(entry["warning_codes"]),
            "review_refs": _csv_join(entry["review_refs"]),
            "provenance_refs": _csv_join(entry["provenance_refs"]),
        }
        for entry in entries
    ]

    output_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(table_rows).to_csv(table_path, index=False)
    record_ref = _relative_to_root(root, record_path)
    table_ref = _relative_to_root(root, table_path)
    review_refs = sorted({review_ref for entry in entries for review_ref in entry.get("review_refs", [])})
    source_refs = sorted({source_ref for entry in entries for source_ref in entry.get("source_refs", [])})
    comparison_record = {
        "schema_version": "0.2",
        "comparison_id": comparison_id,
        "project_id": project_id,
        "method": "uv_vis",
        "status": "comparison_with_warnings" if warnings else "comparison_recorded",
        "created_at": timestamp,
        "updated_at": timestamp,
        "source": "ea.uv_vis.replicate_comparison:v0.2",
        "comparison_label": comparison_label,
        "input_count": len(entries),
        "input_metadata_refs": input_metadata_refs,
        "table_ref": table_ref,
        "entries": entries,
        "statistics": statistics,
        "feature_matching": feature_matching,
        "missing_data": missing_data,
        "outputs": {
            "record": record_ref,
            "table": table_ref,
        },
        "warnings": warnings,
        "review_refs": sorted({*review_refs, *([feature_match_review_ref] if feature_match_review_ref else [])}),
        "source_refs": source_refs,
        "boundaries": [
            "UV-Vis replicate comparison reads existing processed UV-Vis metadata and output tables only.",
            "It does not reprocess raw data, infer replicate grouping silently, apply optical corrections, create ReviewRecords, inject source-backed interpretation candidates, write memory, or prove band gaps, transition mechanisms, feature assignments, correction validity, replicate equivalence, or sample ranking.",
            "Statistics are descriptive summaries for comparable screening values only; not-comparable metrics remain labeled with basis differences and missing-data reasons.",
            "Feature matching is disabled by default and runs only with explicit reviewed tolerance parameters plus a confirmed review ref.",
        ],
    }
    write_yaml(record_path, comparison_record)
    provenance_path = write_provenance_entry(
        root,
        workflow="uv_vis_replicate_comparison",
        inputs={"records": input_metadata_refs, "files": sorted(set(input_files))},
        outputs={"records": [record_ref, table_ref], "files": []},
        parameters={
            "comparison_id": comparison_id,
            "comparison_label": comparison_label,
            "input_count": len(entries),
            "statistics": sorted(statistics.keys()),
            "feature_matching_enabled": bool(feature_matching["enabled"]),
            "feature_match_tolerance_eV": energy_tolerance_eV,
            "feature_match_tolerance_nm": wavelength_tolerance_nm,
            "feature_match_review_ref": feature_match_review_ref,
        },
        review_refs=comparison_record["review_refs"],
        source_refs=source_refs,
        warnings=warnings,
        scripts=[{"path": "src/ea/uv_vis/service.py", "version": "0.2.0"}],
        created_at=created_at,
    )
    comparison_record["provenance_ref"] = _relative_to_root(root, provenance_path)
    write_yaml(record_path, comparison_record)
    return {
        "comparison_id": comparison_id,
        "record": str(record_path),
        "table": str(table_path),
        "status": comparison_record["status"],
        "input_count": len(entries),
        "statistics": statistics,
        "feature_matching": feature_matching,
        "warnings": warnings,
        "provenance": str(provenance_path),
    }


def _created_day(created_at: str | None) -> str | None:
    return created_at[:10] if created_at else None


def _uses_v0_2_project_ids(project_id: str) -> bool:
    return project_id.startswith("prj-")


def _plot_uv_vis(processed: pd.DataFrame, features: pd.DataFrame, output: Path, x_unit: str, signal_mode: str, *, footer: str | None = None) -> None:
    fig, ax = styled_subplots(figsize=(6.0, 4.0))
    x_column = "wavelength_nm" if x_unit == "nm" and "wavelength_nm" in processed.columns else "uv_vis_axis"
    feature_x = "wavelength_nm" if x_column == "wavelength_nm" and "wavelength_nm" in features.columns else "position"
    ax.plot(processed[x_column], processed["processed_signal"], color=NATURE_LIKE_COLORS["blue"], linewidth=1.2, label="Processed signal")
    if not features.empty:
        ax.scatter(features[feature_x], features["processed_signal"], color=NATURE_LIKE_COLORS["black"], s=18, label="Detected features", zorder=3)
        for _, feature in features.sort_values("prominence", ascending=False).head(8).iterrows():
            label_value = feature.get(feature_x)
            ax.annotate(
                f"{float(label_value):.0f}" if x_unit == "nm" else f"{float(label_value):.2f}",
                (float(feature[feature_x]), float(feature["processed_signal"])),
                textcoords="offset points",
                xytext=(0, 6),
                ha="center",
                fontsize=7,
            )
    xlabel = "Wavelength (nm)" if x_unit == "nm" else ("Energy (eV)" if x_unit == "eV" else "UV-Vis axis (unknown unit)")
    ylabel = {
        "absorbance": "Absorbance (a.u.)",
        "transmittance": "Transmittance (a.u.)",
        "reflectance": "Reflectance (a.u.)",
    }[signal_mode]
    style_axis(ax, title="UV-Vis spectrum", xlabel=xlabel, ylabel=ylabel)
    save_styled_figure(fig, output, footer=footer)


def process_uv_vis_result(
    root: Path,
    *,
    characterization_metadata_path: Path,
    project_id: str,
    sample_refs: list[str],
    request: UVVisProcessingRequest,
    created_at: str | None = None,
) -> Path:
    metadata = read_yaml(characterization_metadata_path)
    require_confirmed_review(root, request.column_review_ref)
    require_confirmed_review(root, request.parameter_review_ref)
    raw_path = root / metadata["project_raw_path"]
    inspection = inspect_uv_vis_file(raw_path)
    if inspection.file_kind != "uv_vis":
        raise UVVisProcessingError(f"File is {inspection.file_kind}, not UV-Vis")

    parameters = _merge_parameters(request.processing_parameters)
    processed, processing_warnings = _apply_processing(_confirmed_frame(raw_path, request), parameters)
    features = _detect_features(processed, parameters, request.signal_mode, request.x_unit)
    edge = _estimate_edge(processed, parameters, request.signal_mode)
    tauc_analysis, tauc_warnings = _run_tauc_analysis(processed, parameters, request.signal_mode)
    derivative_table, derivative_analysis, derivative_warnings = _run_derivative_analysis(processed, parameters)
    correction_context, correction_warnings = _record_correction_context(parameters)
    feature_analysis = _analyze_features(features, edge, tauc_analysis, derivative_analysis, correction_context)
    day = _created_day(created_at)
    project_slug = infer_project_slug(project_id)
    if _uses_v0_2_project_ids(project_id):
        result_id = next_standard_id(root, "result", project_slug, method="uv_vis", day=day)
        figure_id = next_standard_id(root, "figure", project_slug, method="uv_vis", day=day)
    else:
        result_id = next_id(root, "uv_vis_result", day)
        figure_id = None
    sample_dir = sample_refs[0] if sample_refs else "unmapped-sample"
    output_dir = root / "processed" / sample_dir / "uv_vis" / result_id
    processed_csv = output_dir / "uv_vis_processed.csv"
    features_csv = output_dir / "uv_vis_features.csv"
    tauc_csv = output_dir / "uv_vis_tauc.csv"
    derivative_csv = output_dir / "uv_vis_derivative.csv"
    correction_context_yml = output_dir / "uv_vis_correction_context.yml"
    figure_name = f"{figure_id}.png" if figure_id else "uv_vis_plot.png"
    figure = output_dir / figure_name
    result_metadata = output_dir / "uv_vis_metadata.yml"
    for output in [processed_csv, features_csv, tauc_csv, derivative_csv, correction_context_yml, figure, result_metadata]:
        assert_not_raw_output_path(root, output)

    output_dir.mkdir(parents=True, exist_ok=True)
    processed.to_csv(processed_csv, index=False)
    features.to_csv(features_csv, index=False)
    tauc_output_ref: str | None = None
    if tauc_analysis and "tauc_y" in processed.columns:
        tauc_columns = ["tauc_energy_eV", "tauc_alpha_proxy", "tauc_y", "tauc_fit_window"]
        processed[tauc_columns].to_csv(tauc_csv, index=False)
        tauc_output_ref = str(tauc_csv.relative_to(root))
        feature_analysis["tauc_analysis"]["table_ref"] = tauc_output_ref
    derivative_output_ref: str | None = None
    if derivative_table is not None:
        derivative_table.to_csv(derivative_csv, index=False)
        derivative_output_ref = str(derivative_csv.relative_to(root))
        if feature_analysis.get("derivative_analysis"):
            feature_analysis["derivative_analysis"]["table_ref"] = derivative_output_ref
    correction_context_ref: str | None = None
    if correction_context is not None:
        correction_context_ref = str(correction_context_yml.relative_to(root))
        correction_context["record_ref"] = correction_context_ref
        write_yaml(correction_context_yml, correction_context)
        if feature_analysis.get("correction_context"):
            feature_analysis["correction_context"]["record_ref"] = correction_context_ref
    _plot_uv_vis(processed, features, figure, request.x_unit, request.signal_mode, footer=figure_footer(figure_id, None) if figure_id else None)

    warnings: list[Any] = []
    if request.x_unit == "unknown":
        warnings.append(_warning("uv_vis_x_unit_unknown", "UV-Vis x unit remains unknown after confirmation.", severity="medium"))
    warnings.extend(processing_warnings)
    warnings.extend(tauc_warnings)
    warnings.extend(derivative_warnings)
    warnings.extend(correction_warnings)
    outputs = {
        "figure": str(figure.relative_to(root)),
        "peak_table": str(features_csv.relative_to(root)),
        "processed_csv": str(processed_csv.relative_to(root)),
        "metadata": str(result_metadata.relative_to(root)),
    }
    if tauc_output_ref:
        outputs["tauc_table"] = tauc_output_ref
    if derivative_output_ref:
        outputs["derivative_table"] = derivative_output_ref
    if correction_context_ref:
        outputs["correction_context"] = correction_context_ref
    provenance_files = [
        str(processed_csv.relative_to(root)),
        str(features_csv.relative_to(root)),
        str(figure.relative_to(root)),
    ]
    if tauc_output_ref:
        provenance_files.append(tauc_output_ref)
    if derivative_output_ref:
        provenance_files.append(derivative_output_ref)
    if correction_context_ref:
        provenance_files.append(correction_context_ref)
    result = UVVisProcessingResult(
        uv_vis_result_id=result_id,
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
        peak_analysis=feature_analysis,
        figure_id=figure_id,
        warnings=warnings,
        review_refs=[request.column_review_ref, request.parameter_review_ref],
        created_at=created_at or EARecord.now_iso(),
        updated_at=created_at or EARecord.now_iso(),
    )
    write_yaml(result_metadata, result.model_dump(exclude_none=True))
    provenance_path = write_provenance_entry(
        root,
        workflow="uv_vis_processing",
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
        scripts=[{"path": "src/ea/uv_vis/service.py", "version": "0.2.0"}],
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
                "script": "src/ea/uv_vis/service.py",
                "parameters": {
                    "x_column": request.x_column,
                    "y_column": request.y_column,
                    "x_unit": request.x_unit,
                    "signal_mode": request.signal_mode,
                    "processing_parameters": parameters,
                },
            },
            caption="UV-Vis spectrum with processed signal, detected optical features, and traceable processing parameters.",
            purpose="uv_vis_analysis_report",
            style_profile=NATURE_LIKE_STYLE_PROFILE,
            source_data_refs=[
                str(processed_csv.relative_to(root)),
                str(features_csv.relative_to(root)),
            ]
            + ([tauc_output_ref] if tauc_output_ref else [])
            + ([derivative_output_ref] if derivative_output_ref else [])
            + ([correction_context_ref] if correction_context_ref else []),
        )
    return result_metadata
