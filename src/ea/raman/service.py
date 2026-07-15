from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit
from scipy import sparse
from scipy.signal import find_peaks, peak_widths, savgol_filter
from scipy.sparse.linalg import spsolve

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
from ea.materials import infer_material_from_project, match_raman_peaks
from ea.provenance import write_provenance_entry
from ea.report_messages import ensure_interpretation_message_contract
from ea.raw_import import assert_not_raw_output_path
from ea.review import require_confirmed_review
from ea.schema import RamanProcessingResult
from ea.schema.models import EARecord
from ea.standards import infer_project_slug
from ea.storage.files import read_yaml, write_yaml
from ea.storage.ids import next_id, next_standard_id


class RamanProcessingError(RuntimeError):
    """Raised when Raman processing would violate a v0.1 confirmation boundary."""


@dataclass(frozen=True)
class SpectrumInspection:
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
class RamanProcessingRequest:
    x_column: str
    y_column: str
    x_unit: str
    processing_parameters: dict[str, Any]
    column_review_ref: str
    parameter_review_ref: str


def default_processing_parameters() -> dict[str, Any]:
    return {
        "baseline_correction": {
            "enabled": False,
            "method": "asls",
            "lambda": 100000.0,
            "p": 0.01,
            "niter": 10,
        },
        "smoothing": {
            "enabled": False,
            "method": "savitzky_golay",
            "window_length": 9,
            "polyorder": 2,
        },
        "normalization": {"enabled": True, "method": "max_intensity"},
        "spike_detection": {
            "enabled": False,
            "method": "rolling_mad",
            "window": 7,
            "mad_threshold": 8.0,
        },
        "peak_detection": {
            "method": "scipy_find_peaks",
            "prominence": "auto",
            "distance": "auto",
        },
        "peak_fitting": {
            "enabled": True,
            "method": "local_gaussian",
            "window_cm-1": "auto",
            "min_points": 7,
        },
    }


def _merge_parameters(parameters: dict[str, Any] | None) -> dict[str, Any]:
    merged = default_processing_parameters()
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


def _parse_metadata_line(line: str) -> tuple[str, str] | None:
    line = line[1:].strip()
    if "=" not in line:
        return None
    key, value = line.split("=", 1)
    return key.strip(), value.strip()


def _parse_text_table(path: Path) -> tuple[pd.DataFrame, dict[str, str]]:
    metadata: dict[str, str] = {}
    rows: list[list[float]] = []
    header: list[str] | None = None
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            parsed = _parse_metadata_line(line)
            if parsed:
                metadata[parsed[0]] = parsed[1]
            continue
        parts = [part for part in re.split(r"[\t,\s]+", line) if part]
        try:
            rows.append([float(value) for value in parts[:2]])
        except ValueError:
            if header is None:
                header = parts[:2]
    columns = header if header and len(header) >= 2 else ["col_0", "col_1"]
    return pd.DataFrame(rows, columns=columns[:2]), metadata


def _read_spectrum(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".csv"}:
        return _parse_text_table(path)
    if suffix in {".xlsx", ".xlsm"}:
        frame = pd.read_excel(path)
        numeric = frame.select_dtypes(include=["number"])
        if numeric.shape[1] < 2:
            raise RamanProcessingError(f"Need at least two numeric columns in {path}")
        return numeric.iloc[:, :2].rename(columns=str), {}
    raise RamanProcessingError(f"Unsupported spectrum format: {path.suffix}")


def _metadata_value(metadata: dict[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    return str(value) if value is not None else None


def _instrument_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "laser_wavelength": _metadata_value(metadata, "Laser"),
        "integration_time": _metadata_value(metadata, "Acq. time (s)"),
        "objective": _metadata_value(metadata, "Objective"),
        "grating": _metadata_value(metadata, "Grating"),
        "accumulations": _metadata_value(metadata, "Accumulations"),
        "instrument_model": _metadata_value(metadata, "Instrument"),
    }


def inspect_spectrum_file(path: Path) -> SpectrumInspection:
    frame, metadata = _read_spectrum(path)
    columns = [str(column) for column in frame.columns]
    if frame.empty or len(columns) < 2:
        raise RamanProcessingError(
            f"No two-column numeric spectrum data found in {path}"
        )

    x_values = pd.to_numeric(frame.iloc[:, 0], errors="coerce").dropna()
    x_min = float(x_values.min())
    x_max = float(x_values.max())
    axis_unit = (metadata.get("AxisUnit[1]") or metadata.get("x_unit") or "").lower()
    filename_upper = path.name.upper()

    if (
        "PL" in filename_upper
        or axis_unit == "ev"
        or (0.5 <= x_min <= 5 and 0.5 <= x_max <= 5)
    ):
        file_kind = "pl"
        x_unit = "eV"
    elif 100 <= x_min <= 4000 or 100 <= x_max <= 4000:
        file_kind = "raman"
        x_unit = "cm^-1" if "cm" in axis_unit else "unknown"
    else:
        file_kind = "unknown"
        x_unit = "unknown"

    warnings: list[str] = []
    if file_kind == "raman" and x_unit == "unknown":
        warnings.append("x_unit_unknown")
    instrument = _instrument_metadata(metadata)
    if file_kind == "raman" and not any(instrument.values()):
        warnings.append("instrument_metadata_missing")

    return SpectrumInspection(
        path=path,
        file_kind=file_kind,
        row_count=len(frame),
        columns=columns,
        x_column_candidate=columns[0],
        y_column_candidate=columns[1],
        x_unit=x_unit,
        metadata={**metadata, "instrument_metadata": instrument},
        warnings=warnings,
        requires_user_confirmation=True,
    )


def _confirmed_frame(path: Path, request: RamanProcessingRequest) -> pd.DataFrame:
    frame, _ = _read_spectrum(path)
    frame.columns = [str(column) for column in frame.columns]
    if request.x_column not in frame.columns or request.y_column not in frame.columns:
        raise RamanProcessingError(
            "Confirmed x/y columns are not present in the raw file"
        )
    if request.x_unit not in {"cm^-1", "unknown"}:
        raise RamanProcessingError(
            "Raman x_unit must be user-confirmed as cm^-1 or unknown"
        )
    data = frame[[request.x_column, request.y_column]].copy()
    data.columns = ["raman_shift", "raw_intensity"]
    data["raman_shift"] = pd.to_numeric(data["raman_shift"], errors="coerce")
    data["raw_intensity"] = pd.to_numeric(data["raw_intensity"], errors="coerce")
    data = data.dropna().sort_values("raman_shift").reset_index(drop=True)
    if data.empty:
        raise RamanProcessingError("Confirmed Raman columns contain no numeric data")
    return data


def _asls_baseline(
    intensity: np.ndarray,
    *,
    lam: float = 100000.0,
    p: float = 0.01,
    niter: int = 10,
) -> np.ndarray:
    length = intensity.size
    if length < 3:
        return np.zeros_like(intensity, dtype=float)
    difference = sparse.diags(
        [1, -2, 1], [0, -1, -2], shape=(length, length - 2), dtype=float, format="csc"
    )
    weights = np.ones(length)
    for _ in range(niter):
        weight_matrix = sparse.spdiags(weights, 0, length, length)
        system = (weight_matrix + lam * difference.dot(difference.transpose())).tocsc()
        baseline = spsolve(system, weights * intensity)
        weights = p * (intensity > baseline) + (1 - p) * (intensity <= baseline)
    return np.asarray(baseline, dtype=float)


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


def _apply_baseline_correction(
    processed: pd.DataFrame,
    intensity: np.ndarray,
    parameters: dict[str, Any],
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    baseline_params = parameters.get("baseline_correction", {})
    if not baseline_params.get("enabled", False):
        return intensity, []

    warnings: list[dict[str, Any]] = []
    if baseline_params.get("method", "asls") != "asls":
        warnings.append(
            _warning(
                "baseline_method_adjusted",
                "Unsupported baseline method was replaced with AsLS.",
                method=baseline_params.get("method"),
            )
        )

    lam, lam_adjusted = _coerce_float(
        baseline_params.get("lambda"), 100000.0, minimum=1.0
    )
    p, p_adjusted = _coerce_float(
        baseline_params.get("p"), 0.01, minimum=0.0001, maximum=0.9999
    )
    niter, niter_adjusted = _coerce_int(baseline_params.get("niter"), 10, minimum=1)
    if lam_adjusted or p_adjusted or niter_adjusted:
        warnings.append(
            _warning(
                "baseline_parameter_adjusted",
                "Invalid AsLS baseline parameters were replaced with safe defaults.",
                lambda_value=lam,
                p=p,
                niter=niter,
            )
        )

    if intensity.size < 3:
        processed["baseline"] = 0.0
        processed["baseline_corrected_intensity"] = intensity
        warnings.append(
            _warning(
                "baseline_correction_skipped",
                "Baseline correction was skipped because the spectrum has fewer than three points.",
                severity="medium",
            )
        )
        return intensity, warnings

    baseline = _asls_baseline(intensity, lam=lam, p=p, niter=niter)
    corrected = intensity - baseline
    processed["baseline"] = baseline
    processed["baseline_corrected_intensity"] = corrected
    warnings.append(
        _warning(
            "baseline_correction_applied",
            "AsLS baseline correction was applied before downstream processing.",
            method="asls",
            lambda_value=lam,
            p=p,
            niter=niter,
        )
    )
    return corrected, warnings


def _apply_smoothing(
    processed: pd.DataFrame,
    intensity: np.ndarray,
    parameters: dict[str, Any],
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    smoothing_params = parameters.get("smoothing", {})
    if not smoothing_params.get("enabled", False):
        return intensity, []

    warnings: list[dict[str, Any]] = []
    if smoothing_params.get("method", "savitzky_golay") != "savitzky_golay":
        warnings.append(
            _warning(
                "smoothing_method_adjusted",
                "Unsupported smoothing method was replaced with Savitzky-Golay.",
                method=smoothing_params.get("method"),
            )
        )

    if intensity.size < 3:
        processed["smoothed_intensity"] = intensity
        warnings.append(
            _warning(
                "smoothing_skipped",
                "Smoothing was skipped because the spectrum has fewer than three points.",
                severity="medium",
            )
        )
        return intensity, warnings

    window_length, window_adjusted = _coerce_int(
        smoothing_params.get("window_length"), 9, minimum=3
    )
    polyorder, poly_adjusted = _coerce_int(
        smoothing_params.get("polyorder"), 2, minimum=1
    )
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
    if adjusted:
        warnings.append(
            _warning(
                "smoothing_parameter_adjusted",
                "Invalid Savitzky-Golay parameters were adjusted to fit the spectrum length.",
                window_length=window_length,
                polyorder=polyorder,
            )
        )

    smoothed = savgol_filter(
        intensity, window_length=window_length, polyorder=polyorder, mode="interp"
    )
    processed["smoothed_intensity"] = smoothed
    warnings.append(
        _warning(
            "smoothing_applied",
            "Savitzky-Golay smoothing was applied before normalization and peak detection.",
            method="savitzky_golay",
            window_length=window_length,
            polyorder=polyorder,
        )
    )
    return np.asarray(smoothed, dtype=float), warnings


def _detect_spike_candidates(
    intensity: np.ndarray, parameters: dict[str, Any]
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    spike_params = parameters.get("spike_detection", {})
    if not spike_params.get("enabled", False):
        return np.zeros(intensity.size, dtype=bool), []

    warnings: list[dict[str, Any]] = []
    if spike_params.get("method", "rolling_mad") != "rolling_mad":
        warnings.append(
            _warning(
                "spike_detection_method_adjusted",
                "Unsupported spike detection method was replaced with rolling MAD.",
                method=spike_params.get("method"),
            )
        )

    window, window_adjusted = _coerce_int(spike_params.get("window"), 7, minimum=3)
    threshold, threshold_adjusted = _coerce_float(
        spike_params.get("mad_threshold"), 8.0, minimum=1.0
    )
    if window % 2 == 0:
        window += 1
        window_adjusted = True
    if intensity.size < 3:
        warnings.append(
            _warning(
                "spike_detection_skipped",
                "Spike detection was skipped because the spectrum has fewer than three points.",
                severity="medium",
            )
        )
        return np.zeros(intensity.size, dtype=bool), warnings
    if window > intensity.size:
        window = intensity.size if intensity.size % 2 == 1 else intensity.size - 1
        window_adjusted = True
    if window_adjusted or threshold_adjusted:
        warnings.append(
            _warning(
                "spike_detection_parameter_adjusted",
                "Invalid rolling MAD spike-detection parameters were adjusted.",
                window=window,
                mad_threshold=threshold,
            )
        )

    rolling_median = (
        pd.Series(intensity)
        .rolling(window=window, center=True, min_periods=1)
        .median()
        .to_numpy(dtype=float)
    )
    residual = np.abs(intensity - rolling_median)
    residual_median = float(np.median(residual))
    mad = float(np.median(np.abs(residual - residual_median)))
    floor = max(float(np.ptp(intensity)) * 1e-8, 1e-12)
    cutoff = residual_median + threshold * max(mad, floor)
    candidates = residual > cutoff
    count = int(np.count_nonzero(candidates))
    warnings.append(
        _warning(
            "spike_detection_applied",
            "Rolling MAD spike-candidate diagnostics were applied.",
            method="rolling_mad",
            window=window,
            mad_threshold=threshold,
            candidate_count=count,
        )
    )
    if count:
        warnings.append(
            _warning(
                "spike_candidates_detected",
                "Potential spike candidates were marked in the processed Raman CSV for user review.",
                severity="medium",
                candidate_count=count,
            )
        )
    return candidates, warnings


def _apply_processing(
    data: pd.DataFrame, parameters: dict[str, Any]
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    processed = data.copy()
    warnings: list[dict[str, Any]] = []
    intensity = processed["raw_intensity"].to_numpy(dtype=float)

    intensity, baseline_warnings = _apply_baseline_correction(
        processed, intensity, parameters
    )
    warnings.extend(baseline_warnings)

    intensity, smoothing_warnings = _apply_smoothing(processed, intensity, parameters)
    warnings.extend(smoothing_warnings)

    spike_candidates, spike_warnings = _detect_spike_candidates(intensity, parameters)
    processed["spike_candidate"] = spike_candidates
    warnings.extend(spike_warnings)

    if parameters.get("normalization", {}).get("enabled", True):
        max_value = float(np.max(np.abs(intensity)))
        if max_value > 0:
            intensity = intensity / max_value
        warnings.append(
            _warning(
                "normalization_applied",
                "Intensity normalized by processing parameters.",
            )
        )
    processed["processed_intensity"] = intensity
    return processed, warnings


def _gaussian_with_offset(
    x: np.ndarray, offset: float, amplitude: float, center: float, sigma: float
) -> np.ndarray:
    return offset + amplitude * np.exp(-((x - center) ** 2) / (2 * sigma**2))


def _axis_step(x_values: np.ndarray) -> float:
    diffs = np.diff(np.sort(x_values.astype(float)))
    positive = diffs[diffs > 0]
    if positive.size == 0:
        return 1.0
    return float(np.median(positive))


def _interpolated_x(x_values: np.ndarray, fractional_index: float) -> float:
    indices = np.arange(x_values.size, dtype=float)
    return float(np.interp(fractional_index, indices, x_values.astype(float)))


def _fit_peak(
    processed: pd.DataFrame,
    *,
    peak_index: int,
    width_cm: float,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    fitting_params = parameters.get("peak_fitting", {})
    if not fitting_params.get("enabled", True):
        return {
            "fit_method": "none",
            "fit_status": "disabled",
            "fit_center_cm-1": np.nan,
            "fit_height": np.nan,
            "fit_sigma_cm-1": np.nan,
            "fit_fwhm_cm-1": np.nan,
            "fit_area": np.nan,
            "fit_r2": np.nan,
        }

    x = processed["raman_shift"].to_numpy(dtype=float)
    y = processed["processed_intensity"].to_numpy(dtype=float)
    center_guess = float(x[peak_index])
    step = _axis_step(x)
    requested_window = fitting_params.get("window_cm-1", "auto")
    if requested_window == "auto":
        half_window = max(
            float(width_cm) * 1.5 if np.isfinite(width_cm) else 0.0, step * 5, 4.0
        )
    else:
        half_window, _ = _coerce_float(
            requested_window, max(step * 5, 4.0), minimum=step
        )
    min_points, _ = _coerce_int(fitting_params.get("min_points"), 7, minimum=4)
    mask = np.abs(x - center_guess) <= half_window
    local = processed.loc[mask, ["raman_shift", "processed_intensity"]]
    if len(local) < min_points:
        left = max(0, peak_index - min_points // 2)
        right = min(len(processed), left + min_points)
        left = max(0, right - min_points)
        local = processed.iloc[left:right][["raman_shift", "processed_intensity"]]
    if len(local) < 4:
        return {
            "fit_method": "local_gaussian",
            "fit_status": "skipped_insufficient_points",
            "fit_center_cm-1": np.nan,
            "fit_height": np.nan,
            "fit_sigma_cm-1": np.nan,
            "fit_fwhm_cm-1": np.nan,
            "fit_area": np.nan,
            "fit_r2": np.nan,
        }

    local_x = local["raman_shift"].to_numpy(dtype=float)
    local_y = local["processed_intensity"].to_numpy(dtype=float)
    y_min = float(np.min(local_y))
    y_max = float(np.max(local_y))
    y_range = max(float(np.ptp(local_y)), 1e-9)
    offset0 = float(np.percentile(local_y, 10))
    amplitude0 = max(float(y[peak_index] - offset0), y_range * 0.2, 1e-6)
    sigma0 = max(
        (float(width_cm) / 2.354820045)
        if np.isfinite(width_cm) and width_cm > 0
        else step * 2,
        step / 2,
        1e-6,
    )
    lower = [y_min - y_range * 2, 0.0, float(local_x.min()), max(step / 10, 1e-6)]
    upper = [
        y_max + y_range * 2,
        max(y_max + y_range * 2, amplitude0 * 4, 1.0),
        float(local_x.max()),
        max(float(np.ptp(local_x)) * 2, step),
    ]
    try:
        popt, _ = curve_fit(
            _gaussian_with_offset,
            local_x,
            local_y,
            p0=[offset0, amplitude0, center_guess, sigma0],
            bounds=(lower, upper),
            maxfev=5000,
        )
        fitted = _gaussian_with_offset(local_x, *popt)
        ss_res = float(np.sum((local_y - fitted) ** 2))
        ss_tot = float(np.sum((local_y - np.mean(local_y)) ** 2))
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
        _, amplitude, center, sigma = [float(value) for value in popt]
        sigma = abs(sigma)
        return {
            "fit_method": "local_gaussian",
            "fit_status": "success",
            "fit_center_cm-1": center,
            "fit_height": amplitude,
            "fit_sigma_cm-1": sigma,
            "fit_fwhm_cm-1": 2.354820045 * sigma,
            "fit_area": amplitude * sigma * float(np.sqrt(2 * np.pi)),
            "fit_r2": r2,
        }
    except (
        Exception
    ) as exc:  # pragma: no cover - fit failures depend on scipy internals
        return {
            "fit_method": "local_gaussian",
            "fit_status": f"failed:{type(exc).__name__}",
            "fit_center_cm-1": np.nan,
            "fit_height": np.nan,
            "fit_sigma_cm-1": np.nan,
            "fit_fwhm_cm-1": np.nan,
            "fit_area": np.nan,
            "fit_r2": np.nan,
        }


def _detect_peaks(processed: pd.DataFrame, parameters: dict[str, Any]) -> pd.DataFrame:
    y = processed["processed_intensity"].to_numpy(dtype=float)
    x = processed["raman_shift"].to_numpy(dtype=float)
    peak_params = parameters.get("peak_detection", {})
    prominence = peak_params.get("prominence", "auto")
    distance = peak_params.get("distance", "auto")
    if prominence == "auto":
        prominence = max(float(np.ptp(y)) * 0.08, 0.02)
    if distance == "auto":
        distance = max(len(y) // 40, 1)
    peaks, properties = find_peaks(y, prominence=prominence, distance=distance)
    width_result = (
        peak_widths(y, peaks, rel_height=0.5) if len(peaks) else ([], [], [], [])
    )
    widths = width_result[0]
    left_ips = width_result[2]
    right_ips = width_result[3]
    rows = []
    for index, peak_index in enumerate(peaks, start=1):
        width = float(widths[index - 1]) if len(widths) else np.nan
        left_x = (
            _interpolated_x(x, float(left_ips[index - 1])) if len(left_ips) else np.nan
        )
        right_x = (
            _interpolated_x(x, float(right_ips[index - 1]))
            if len(right_ips)
            else np.nan
        )
        width_cm = (
            float(right_x - left_x)
            if np.isfinite(left_x) and np.isfinite(right_x)
            else np.nan
        )
        fit = _fit_peak(
            processed,
            peak_index=int(peak_index),
            width_cm=width_cm,
            parameters=parameters,
        )
        rows.append(
            {
                "peak_id": f"peak-{index:03d}",
                "position_cm-1": processed.iloc[int(peak_index)]["raman_shift"],
                "intensity": processed.iloc[int(peak_index)]["raw_intensity"],
                "height": y[int(peak_index)],
                "prominence": properties["prominences"][index - 1],
                "width": width,
                "method": "scipy_find_peaks",
                "notes": "requires scientific review",
                "width_cm-1": width_cm,
                "left_base_cm-1": left_x,
                "right_base_cm-1": right_x,
                **fit,
            }
        )
    columns = [
        "peak_id",
        "position_cm-1",
        "intensity",
        "height",
        "prominence",
        "width",
        "method",
        "notes",
        "width_cm-1",
        "left_base_cm-1",
        "right_base_cm-1",
        "fit_method",
        "fit_status",
        "fit_center_cm-1",
        "fit_height",
        "fit_sigma_cm-1",
        "fit_fwhm_cm-1",
        "fit_area",
        "fit_r2",
    ]
    return pd.DataFrame(rows, columns=columns)


def _analyze_peak_assignments(
    peaks: pd.DataFrame, root: Path, project_id: str
) -> dict[str, Any]:
    default_columns: dict[str, Any] = {
        "assignment": "",
        "assignment_confidence": "",
        "assignment_delta_cm-1": np.nan,
        "assignment_feature": "",
        "assignment_source": "",
    }
    for column, default in default_columns.items():
        if column not in peaks.columns:
            peaks[column] = default

    analysis: dict[str, Any] = {
        "peak_count": int(len(peaks)),
        "assigned_features": [],
        "possible_interpretations": [],
    }
    if peaks.empty:
        analysis["possible_interpretations"].append(
            {
                "text": "当前自动设置未检测到稳定 Raman 峰；需要复核信噪比、基线和检峰参数。",
                "confidence": "insufficient",
                "evidence": [],
            }
        )
        return analysis

    material_id = infer_material_from_project(root, project_id)
    if not material_id:
        analysis["possible_interpretations"].append(
            {
                "text": "已完成自动检峰和局部拟合，但当前 project_id 未匹配到材料特异性 Raman 归属规则。",
                "confidence": "low",
                "evidence": [str(peaks.iloc[0]["peak_id"])],
            }
        )
        return analysis

    material_analysis = match_raman_peaks(material_id, peaks.to_dict("records"))
    for update in material_analysis.pop("peak_updates", []):
        mask = peaks["peak_id"].astype(str) == str(update["peak_id"])
        for key, value in update.items():
            if key != "peak_id":
                peaks.loc[mask, key] = value
    return material_analysis


def _created_day(created_at: str | None) -> str | None:
    if not created_at:
        return None
    return created_at[:10]


def _uses_v0_2_project_ids(project_id: str) -> bool:
    return project_id.startswith("prj-")


def _plot_raman(
    processed: pd.DataFrame,
    peaks: pd.DataFrame,
    output: Path,
    x_unit: str,
    *,
    footer: str | None = None,
    language: str = "en",
) -> None:
    zh = language == "zh"
    fig, ax = styled_subplots(figsize=(6.0, 4.0))
    ax.plot(
        processed["raman_shift"],
        processed["processed_intensity"],
        color=NATURE_LIKE_COLORS["orange"],
        linewidth=1.2,
        label="处理强度（归一化）" if zh else "Processed intensity (normalized)",
    )
    raw_ax = ax.twinx()
    raw_ax.plot(
        processed["raman_shift"],
        processed["raw_intensity"],
        color=NATURE_LIKE_COLORS["gray"],
        linewidth=1.0,
        alpha=0.38,
        label="原始强度（原始量程）" if zh else "Raw intensity (original scale)",
    )
    if not peaks.empty:
        ax.scatter(
            peaks["position_cm-1"],
            peaks["height"],
            color=NATURE_LIKE_COLORS["black"],
            s=18,
            label="候选峰" if zh else "Detected peaks",
            zorder=3,
        )
    if "spike_candidate" in processed.columns and processed["spike_candidate"].any():
        spike_rows = processed[processed["spike_candidate"]]
        ax.scatter(
            spike_rows["raman_shift"],
            spike_rows["processed_intensity"],
            facecolors="none",
            edgecolors=NATURE_LIKE_COLORS["pink"],
            s=28,
            linewidths=0.8,
            label="尖峰候选" if zh else "Spike candidates",
            zorder=4,
        )
    unit_label = "cm$^{-1}$" if x_unit == "cm^-1" else "unknown unit"
    style_axis(
        ax,
        title="Raman 光谱" if zh else "Raman spectrum",
        xlabel=f"Raman 位移 ({unit_label})" if zh else f"Raman shift ({unit_label})",
        ylabel="处理强度（归一化，a.u.）" if zh else "Processed intensity (normalized a.u.)",
        legend=False,
    )
    raw_ax.set_ylabel("原始强度（原始量程）" if zh else "Raw intensity (original scale)")
    raw_ax.grid(False)
    raw_ax.spines["top"].set_visible(False)
    raw_ax.spines["right"].set_visible(True)
    handles, labels = ax.get_legend_handles_labels()
    raw_handles, raw_labels = raw_ax.get_legend_handles_labels()
    ax.legend(handles + raw_handles, labels + raw_labels, frameon=False)
    save_styled_figure(fig, output, footer=footer)


def process_raman_result(
    root: Path,
    *,
    characterization_metadata_path: Path,
    project_id: str,
    sample_refs: list[str],
    request: RamanProcessingRequest,
    created_at: str | None = None,
) -> Path:
    metadata = read_yaml(characterization_metadata_path)
    require_confirmed_review(root, request.column_review_ref)
    require_confirmed_review(root, request.parameter_review_ref)
    raw_path = root / metadata["project_raw_path"]
    inspection = inspect_spectrum_file(raw_path)
    if inspection.file_kind != "raman":
        raise RamanProcessingError(f"File is {inspection.file_kind}, not Raman")

    parameters = _merge_parameters(request.processing_parameters)
    processed, preprocessing_warnings = _apply_processing(
        _confirmed_frame(raw_path, request), parameters
    )
    peaks = _detect_peaks(processed, parameters)
    peak_analysis = ensure_interpretation_message_contract(
        _analyze_peak_assignments(peaks, root, project_id), "raman"
    )
    day = _created_day(created_at)
    project_slug = infer_project_slug(project_id)
    if _uses_v0_2_project_ids(project_id):
        result_id = next_standard_id(
            root, "result", project_slug, method="raman", day=day
        )
        figure_id = next_standard_id(
            root, "figure", project_slug, method="raman", day=day
        )
    else:
        result_id = next_id(root, "raman_result", day)
        figure_id = None
    sample_dir = sample_refs[0] if sample_refs else "unmapped-sample"
    output_dir = root / "processed" / sample_dir / "raman" / result_id
    processed_csv = output_dir / "raman_processed.csv"
    peaks_csv = output_dir / "raman_peaks.csv"
    figure_name = f"{figure_id}.png" if figure_id else "raman_plot.png"
    figure = output_dir / figure_name
    result_metadata = output_dir / "raman_metadata.yml"
    for output in [processed_csv, peaks_csv, figure, result_metadata]:
        assert_not_raw_output_path(root, output)

    output_dir.mkdir(parents=True, exist_ok=True)
    processed.to_csv(processed_csv, index=False)
    peaks.to_csv(peaks_csv, index=False)
    _plot_raman(
        processed,
        peaks,
        figure,
        request.x_unit,
        footer=figure_footer(figure_id, None) if figure_id else None,
        language=str(
            read_yaml(root / ".ea" / "project_config.yml").get("report_language")
            if (root / ".ea" / "project_config.yml").is_file()
            else "zh"
        ),
    )

    warnings: list[Any] = []
    inspection_warning_set = set(inspection.warnings)
    if "instrument_metadata_missing" in inspection_warning_set:
        warnings.append(
            _warning(
                "instrument_metadata_missing",
                "仪器元数据未在原始 Raman 文件中找到；报告解释需要保留该限制。",
                severity="medium",
            )
        )
    if "x_unit_unknown" in inspection_warning_set and request.x_unit == "unknown":
        warnings.append(
            _warning(
                "x_unit_unknown",
                "Raman x unit remains unknown after confirmation.",
                severity="medium",
            )
        )
    elif request.x_unit == "unknown":
        warnings.append(
            _warning(
                "x_unit_unknown",
                "Raman x unit remains unknown after confirmation.",
                severity="medium",
            )
        )
    raw_sample_refs = list(metadata.get("sample_refs") or [])
    if not sample_refs:
        warnings.append(
            _warning(
                "sample_mapping_missing",
                "未为本次 Raman 处理提供样品映射；报告解释需要保留样品到文件关系不确定性。",
                severity="medium",
            )
        )
    elif raw_sample_refs and set(raw_sample_refs) != set(sample_refs):
        warnings.append(
            _warning(
                "sample_mapping_differs_from_raw_metadata",
                "本次处理样品映射与 raw metadata 中记录的 sample_refs 不完全一致。",
                severity="medium",
                raw_sample_refs=raw_sample_refs,
                processing_sample_refs=sample_refs,
            )
        )
    warnings.extend(preprocessing_warnings)
    if not parameters.get("baseline_correction", {}).get("enabled", False):
        warnings.append(
            _warning("baseline_not_corrected", "No baseline correction was applied.")
        )

    result = RamanProcessingResult(
        raman_result_id=result_id,
        project_id=project_id,
        characterization_file_ref=metadata["characterization_id"],
        sample_refs=sample_refs,
        status="warning" if warnings else "success",
        x_column=request.x_column,
        y_column=request.y_column,
        x_unit=request.x_unit,  # type: ignore[arg-type]
        processing_parameters=parameters,
        outputs={
            "figure": figure.relative_to(root).as_posix(),
            "peak_table": peaks_csv.relative_to(root).as_posix(),
            "processed_csv": processed_csv.relative_to(root).as_posix(),
            "metadata": result_metadata.relative_to(root).as_posix(),
        },
        peak_analysis=peak_analysis,
        figure_id=figure_id,
        result_id=result_id,
        warnings=warnings,
        review_refs=[request.column_review_ref, request.parameter_review_ref],
        created_at=created_at or EARecord.now_iso(),
        updated_at=created_at or EARecord.now_iso(),
    )
    write_yaml(result_metadata, result.model_dump(exclude_none=True))
    provenance_path = write_provenance_entry(
        root,
        workflow="raman_processing",
        inputs={
            "records": [characterization_metadata_path.relative_to(root).as_posix()],
            "files": [metadata["project_raw_path"]],
        },
        outputs={
            "records": [result_metadata.relative_to(root).as_posix()],
            "files": [
                processed_csv.relative_to(root).as_posix(),
                peaks_csv.relative_to(root).as_posix(),
                figure.relative_to(root).as_posix(),
            ],
        },
        parameters={
            "x_column": request.x_column,
            "y_column": request.y_column,
            "x_unit": request.x_unit,
            "processing_parameters": parameters,
        },
        review_refs=[request.column_review_ref, request.parameter_review_ref],
        warnings=warnings,
        scripts=[{"path": "src/ea/raman/service.py", "version": "0.2.0"}],
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
                "script": "src/ea/raman/service.py",
                "parameters": {
                    "x_column": request.x_column,
                    "y_column": request.y_column,
                    "x_unit": request.x_unit,
                    "plot_layout": "processed_main_raw_secondary_axis",
                    "processing_parameters": parameters,
                },
            },
            caption="Raman spectrum with processed intensity and detected peaks.",
            purpose="raman_analysis_report",
            style_profile=NATURE_LIKE_STYLE_PROFILE,
            source_data_refs=[
                processed_csv.relative_to(root).as_posix(),
                peaks_csv.relative_to(root).as_posix(),
            ],
            source_data=[
                source_data_entry(
                    root,
                    processed_csv.relative_to(root).as_posix(),
                    role="primary_plotting_dataset",
                    purpose="Processed Raman trace plotted on the main axis.",
                    primary=True,
                ),
                source_data_entry(
                    root,
                    peaks_csv.relative_to(root).as_posix(),
                    role="peak_table",
                    purpose="Detected and fitted Raman peak annotations.",
                ),
            ],
        )
    return result_metadata
