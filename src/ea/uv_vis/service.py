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
