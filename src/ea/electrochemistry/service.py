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
from ea.schema import ElectrochemistryProcessingResult
from ea.schema.models import EARecord
from ea.standards import infer_project_slug
from ea.storage.files import read_yaml, write_yaml
from ea.storage.ids import next_id, next_standard_id


class ElectrochemistryProcessingError(RuntimeError):
    """Raised when electrochemistry processing violates review or data boundaries."""


@dataclass(frozen=True)
class ElectrochemistryInspection:
    path: Path
    file_kind: str
    row_count: int
    columns: list[str]
    x_column_candidate: str | None
    y_column_candidate: str | None
    x_unit_candidate: str
    current_unit_candidate: str
    measurement_mode_candidate: str
    metadata: dict[str, Any]
    warnings: list[str]
    requires_user_confirmation: bool


@dataclass(frozen=True)
class ElectrochemistryProcessingRequest:
    x_column: str
    y_column: str
    x_unit: str
    current_unit: str
    measurement_mode: str
    context_summary: str
    electrode_area_cm2: float | None
    processing_parameters: dict[str, Any]
    column_review_ref: str
    context_review_ref: str
    parameter_review_ref: str


def default_electrochemistry_processing_parameters() -> dict[str, Any]:
    return {
        "smoothing": {
            "enabled": False,
            "method": "savitzky_golay",
            "window_length": 9,
            "polyorder": 2,
        },
        "feature_detection": {
            "enabled": True,
            "method": "scipy_find_peaks",
            "prominence": "auto",
            "distance": "auto",
            "max_features": 12,
            "source": "ea.electrochemistry.feature_detection:v0.2",
        },
        "threshold_summary": {
            "enabled": True,
            "method": "absolute_current_fraction",
            "fraction": 0.1,
            "source": "ea.electrochemistry.threshold_summary:v0.2",
        },
        "eis_summary": {
            "enabled": True,
            "method": "nyquist_screening",
            "source": "ea.electrochemistry.eis_nyquist_screening:v0.2",
        },
    }


def _merge_parameters(parameters: dict[str, Any] | None) -> dict[str, Any]:
    merged = default_electrochemistry_processing_parameters()
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


def _metadata_text(columns: list[str], metadata: dict[str, Any], path: Path) -> str:
    parts = list(columns) + [path.as_posix()]
    parts.extend(str(value) for value in metadata.values())
    return " ".join(parts).lower()


def _mode_candidate(text: str) -> str:
    if "lsv" in text or "linear sweep" in text:
        return "lsv"
    if "chrono" in text or " i-t" in text or " amper" in text:
        return "chrono"
    if "gcd" in text or "charge discharge" in text or "galvanostatic" in text:
        return "gcd"
    if "cv" in text or "cyclic" in text or "voltamm" in text:
        return "cv"
    if "eis" in text or "nyquist" in text or "impedance" in text:
        return "eis"
    return "unknown"


def _x_unit_candidate(text: str) -> str:
    if "ohm" in text or "zreal" in text or "z_real" in text or "impedance" in text or "nyquist" in text:
        return "ohm"
    if "mv" in text:
        return "mV"
    if "potential" in text or "voltage" in text or " v " in f" {text} " or "(v" in text:
        return "V"
    if "time" in text or "second" in text or " s " in f" {text} ":
        return "s"
    return "unknown"


def _current_unit_candidate(text: str) -> str:
    if "ua" in text or "µa" in text or "microamp" in text:
        return "uA"
    if "ma" in text or "milliamp" in text:
        return "mA"
    if "current" in text or "amp" in text or " a " in f" {text} ":
        return "A"
    return "unknown"


def inspect_electrochemistry_file(path: Path) -> ElectrochemistryInspection:
    frame, metadata = _read_spectrum(path)
    columns = [str(column) for column in frame.columns]
    if frame.empty or len(columns) < 2:
        raise ElectrochemistryProcessingError(f"No two-column numeric electrochemistry data found in {path}")
    x_values = pd.to_numeric(frame.iloc[:, 0], errors="coerce").dropna()
    y_values = pd.to_numeric(frame.iloc[:, 1], errors="coerce").dropna()
    x_min = float(x_values.min())
    x_max = float(x_values.max())
    y_min = float(y_values.min())
    y_max = float(y_values.max())
    text = _metadata_text(columns, metadata, path)
    mode = _mode_candidate(text)
    x_unit = _x_unit_candidate(text)
    current_unit = _current_unit_candidate(text)
    looks_like_electrochemistry = (
        mode != "unknown"
        or "electrochem" in text
        or ("potential" in text and "current" in text)
        or ("voltage" in text and "current" in text)
    )
    file_kind = "electrochemistry" if looks_like_electrochemistry else "unknown"
    warnings: list[str] = []
    if file_kind == "unknown":
        warnings.append("electrochemistry_file_kind_unknown")
    if x_unit == "unknown":
        warnings.append("electrochemistry_x_unit_unknown")
    if current_unit == "unknown" and mode != "eis":
        warnings.append("electrochemistry_current_unit_unknown")
    return ElectrochemistryInspection(
        path=path,
        file_kind=file_kind,
        row_count=len(frame),
        columns=columns,
        x_column_candidate=columns[0],
        y_column_candidate=columns[1],
        x_unit_candidate=x_unit,
        current_unit_candidate=current_unit,
        measurement_mode_candidate=mode,
        metadata={**metadata, "x_min": x_min, "x_max": x_max, "y_min": y_min, "y_max": y_max},
        warnings=warnings,
        requires_user_confirmation=True,
    )


def _current_to_mA(values: np.ndarray, current_unit: str) -> np.ndarray:
    if current_unit == "A":
        return values * 1000.0
    if current_unit == "mA":
        return values
    if current_unit in {"uA", "µA"}:
        return values / 1000.0
    return values


def _confirmed_frame(path: Path, request: ElectrochemistryProcessingRequest) -> pd.DataFrame:
    frame, _ = _read_spectrum(path)
    frame.columns = [str(column) for column in frame.columns]
    if request.x_column not in frame.columns or request.y_column not in frame.columns:
        raise ElectrochemistryProcessingError("Confirmed x/y columns are not present in the raw file")
    if request.x_unit not in {"V", "mV", "s", "ohm", "unknown"}:
        raise ElectrochemistryProcessingError("Electrochemistry x_unit must be user-confirmed as V, mV, s, ohm, or unknown")
    if request.current_unit not in {"A", "mA", "uA", "µA", "unknown"}:
        raise ElectrochemistryProcessingError("Electrochemistry current_unit must be user-confirmed as A, mA, uA, µA, or unknown")
    if request.measurement_mode not in {"cv", "lsv", "chrono", "gcd", "eis", "unknown"}:
        raise ElectrochemistryProcessingError("Electrochemistry measurement_mode must be cv, lsv, chrono, gcd, eis, or unknown")
    data = frame[[request.x_column, request.y_column]].copy()
    if request.measurement_mode == "eis":
        data.columns = ["z_real_raw", "z_imag_raw"]
        data["z_real_raw"] = pd.to_numeric(data["z_real_raw"], errors="coerce")
        data["z_imag_raw"] = pd.to_numeric(data["z_imag_raw"], errors="coerce")
        data = data.dropna().reset_index(drop=True)
        if data.empty:
            raise ElectrochemistryProcessingError("Confirmed EIS columns contain no numeric data")
        imag = data["z_imag_raw"].to_numpy(dtype=float)
        if float(np.nanmedian(imag)) >= 0:
            data["z_imag_ohm"] = -imag
            data["neg_z_imag_ohm"] = imag
            data["imaginary_convention"] = "negative_imaginary_plotted_positive"
        else:
            data["z_imag_ohm"] = imag
            data["neg_z_imag_ohm"] = -imag
            data["imaginary_convention"] = "imaginary_negative_values_converted_to_positive"
        data["z_real_ohm"] = data["z_real_raw"]
        data["impedance_magnitude_ohm"] = np.sqrt(data["z_real_ohm"].to_numpy(dtype=float) ** 2 + data["z_imag_ohm"].to_numpy(dtype=float) ** 2)
        return data
    data.columns = ["axis_raw", "current_raw"]
    data["axis_raw"] = pd.to_numeric(data["axis_raw"], errors="coerce")
    data["current_raw"] = pd.to_numeric(data["current_raw"], errors="coerce")
    data = data.dropna().reset_index(drop=True)
    if data.empty:
        raise ElectrochemistryProcessingError("Confirmed electrochemistry columns contain no numeric data")
    if request.x_unit == "V":
        data["potential_V"] = data["axis_raw"]
    elif request.x_unit == "mV":
        data["potential_V"] = data["axis_raw"] / 1000.0
    elif request.x_unit == "s":
        data["time_s"] = data["axis_raw"]
    current_mA = _current_to_mA(data["current_raw"].to_numpy(dtype=float), request.current_unit)
    data["current_mA"] = current_mA
    area = request.electrode_area_cm2
    if area is not None and area > 0:
        data["current_density_mA_cm-2"] = current_mA / area
    return data


def _apply_eis_processing(data: pd.DataFrame, parameters: dict[str, Any]) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    processed = data.copy()
    warnings: list[dict[str, Any]] = []
    if not parameters.get("eis_summary", {}).get("enabled", True):
        warnings.append(_warning("electrochemistry_eis_summary_disabled", "EIS Nyquist screening summary was disabled by processing parameters."))
    return processed, warnings


def _apply_processing(data: pd.DataFrame, parameters: dict[str, Any]) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    processed = data.copy()
    warnings: list[dict[str, Any]] = []
    current = processed["current_mA"].to_numpy(dtype=float)
    smoothing = parameters.get("smoothing", {})
    if smoothing.get("enabled", False):
        window_length, window_adjusted = _coerce_int(smoothing.get("window_length"), 9, minimum=3)
        polyorder, poly_adjusted = _coerce_int(smoothing.get("polyorder"), 2, minimum=1)
        max_window = current.size if current.size % 2 == 1 else current.size - 1
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
        if current.size >= 3 and window_length >= 3:
            current = np.asarray(savgol_filter(current, window_length=window_length, polyorder=polyorder, mode="interp"), dtype=float)
            warnings.append(
                _warning(
                    "electrochemistry_smoothing_applied",
                    "Savitzky-Golay smoothing was applied before electrochemistry feature detection.",
                    method="savitzky_golay",
                    window_length=window_length,
                    polyorder=polyorder,
                )
            )
        if adjusted:
            warnings.append(
                _warning(
                    "electrochemistry_smoothing_parameter_adjusted",
                    "Invalid Savitzky-Golay parameters were adjusted for electrochemistry processing.",
                    severity="medium",
                    window_length=window_length,
                    polyorder=polyorder,
                )
            )
    processed["processed_current_mA"] = current
    if "current_density_mA_cm-2" in processed.columns:
        raw_current = processed["current_mA"].to_numpy(dtype=float)
        density = processed["current_density_mA_cm-2"].to_numpy(dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.divide(current, raw_current, out=np.ones_like(current), where=np.abs(raw_current) > 0)
        processed["processed_current_density_mA_cm-2"] = density * ratio
    return processed, warnings


def _feature_axis(row: pd.Series) -> tuple[float, str]:
    if "potential_V" in row.index and pd.notna(row.get("potential_V")):
        return float(row["potential_V"]), "V"
    if "time_s" in row.index and pd.notna(row.get("time_s")):
        return float(row["time_s"]), "s"
    return float(row["axis_raw"]), "unknown"


def _feature_row(feature_id: str, feature_type: str, row: pd.Series, prominence: float | None, source: str, method: str) -> dict[str, Any]:
    axis, unit = _feature_axis(row)
    density = row.get("processed_current_density_mA_cm-2")
    return {
        "feature_id": feature_id,
        "feature_type": feature_type,
        "axis_value": axis,
        "axis_unit": unit,
        "potential_V": float(row["potential_V"]) if "potential_V" in row.index and pd.notna(row.get("potential_V")) else np.nan,
        "time_s": float(row["time_s"]) if "time_s" in row.index and pd.notna(row.get("time_s")) else np.nan,
        "current_mA": float(row["processed_current_mA"]),
        "current_density_mA_cm-2": float(density) if pd.notna(density) else np.nan,
        "prominence": float(prominence) if prominence is not None else np.nan,
        "method": method,
        "assignment_confidence": "low",
        "assignment_source": source,
        "notes": "automatic electrochemistry summary feature; requires experimental context and user review",
    }


def _detect_features(processed: pd.DataFrame, parameters: dict[str, Any], measurement_mode: str) -> pd.DataFrame:
    if measurement_mode == "eis":
        return _detect_eis_features(processed, parameters)
    current = processed["processed_current_mA"].to_numpy(dtype=float)
    rows: list[dict[str, Any]] = []
    feature_params = parameters.get("feature_detection", {})
    source = str(feature_params.get("source") or "ea.electrochemistry.feature_detection:v0.2")
    if feature_params.get("enabled", True) and measurement_mode in {"cv", "lsv", "unknown"} and len(current) >= 3:
        prominence = feature_params.get("prominence", "auto")
        distance = feature_params.get("distance", "auto")
        max_features, _ = _coerce_int(feature_params.get("max_features"), 12, minimum=1)
        if prominence == "auto":
            prominence = max(float(np.ptp(current)) * 0.08, 0.001)
        if distance == "auto":
            distance = max(len(current) // 120, 1)
        positive, positive_props = find_peaks(current, prominence=prominence, distance=distance)
        negative, negative_props = find_peaks(-current, prominence=prominence, distance=distance)
        ranked: list[tuple[int, float, str]] = [
            (int(peak), float(positive_props["prominences"][index]), "anodic_peak")
            for index, peak in enumerate(positive)
        ]
        ranked.extend(
            (int(peak), float(negative_props["prominences"][index]), "cathodic_peak")
            for index, peak in enumerate(negative)
        )
        ranked = sorted(ranked, key=lambda item: item[1], reverse=True)[:max_features]
        ranked.sort(key=lambda item: float(processed.iloc[item[0]]["axis_raw"]))
        for index, (peak_index, feature_prominence, feature_type) in enumerate(ranked, start=1):
            rows.append(_feature_row(f"ec-feature-{index:03d}", feature_type, processed.iloc[peak_index], feature_prominence, source, "scipy_find_peaks"))
    threshold_params = parameters.get("threshold_summary", {})
    if threshold_params.get("enabled", True) and measurement_mode in {"lsv", "cv", "unknown"} and len(current) >= 3:
        fraction, _ = _coerce_float(threshold_params.get("fraction"), 0.1, minimum=0.001, maximum=1.0)
        threshold = float(np.nanmax(np.abs(current))) * fraction
        candidates = np.where(np.abs(current) >= threshold)[0]
        if candidates.size:
            threshold_source = str(threshold_params.get("source") or "ea.electrochemistry.threshold_summary:v0.2")
            rows.append(_feature_row("ec-threshold-001", "threshold_current", processed.iloc[int(candidates[0])], None, threshold_source, "absolute_current_fraction"))
    return pd.DataFrame(
        rows,
        columns=[
            "feature_id",
            "feature_type",
            "axis_value",
            "axis_unit",
            "potential_V",
            "time_s",
            "current_mA",
            "current_density_mA_cm-2",
            "prominence",
            "method",
            "assignment_confidence",
            "assignment_source",
            "notes",
        ],
    )


def _eis_feature_row(
    feature_id: str,
    feature_type: str,
    row: pd.Series,
    source: str,
    *,
    screening_resistance_ohm: float | None = None,
) -> dict[str, Any]:
    return {
        "feature_id": feature_id,
        "feature_type": feature_type,
        "axis_value": float(row["z_real_ohm"]),
        "axis_unit": "ohm",
        "potential_V": np.nan,
        "time_s": np.nan,
        "current_mA": np.nan,
        "current_density_mA_cm-2": np.nan,
        "prominence": np.nan,
        "z_real_ohm": float(row["z_real_ohm"]),
        "z_imag_ohm": float(row["z_imag_ohm"]),
        "neg_z_imag_ohm": float(row["neg_z_imag_ohm"]),
        "impedance_magnitude_ohm": float(row["impedance_magnitude_ohm"]),
        "screening_resistance_ohm": float(screening_resistance_ohm) if screening_resistance_ohm is not None else np.nan,
        "method": "nyquist_screening",
        "assignment_confidence": "low",
        "assignment_source": source,
        "notes": "automatic EIS Nyquist screening feature; no equivalent-circuit fit was performed",
    }


def _detect_eis_features(processed: pd.DataFrame, parameters: dict[str, Any]) -> pd.DataFrame:
    summary_params = parameters.get("eis_summary", {})
    source = str(summary_params.get("source") or "ea.electrochemistry.eis_nyquist_screening:v0.2")
    if not summary_params.get("enabled", True) or processed.empty:
        return pd.DataFrame(columns=_eis_feature_columns())
    z_real = processed["z_real_ohm"].to_numpy(dtype=float)
    neg_imag = processed["neg_z_imag_ohm"].to_numpy(dtype=float)
    min_index = int(np.nanargmin(z_real))
    max_index = int(np.nanargmax(z_real))
    apex_index = int(np.nanargmax(neg_imag))
    span = float(z_real[max_index] - z_real[min_index])
    rows = [
        _eis_feature_row("eis-rs-001", "high_frequency_intercept_screening", processed.iloc[min_index], source),
        _eis_feature_row("eis-apex-001", "nyquist_arc_apex_screening", processed.iloc[apex_index], source),
        _eis_feature_row("eis-span-001", "real_axis_span_screening", processed.iloc[max_index], source, screening_resistance_ohm=span),
    ]
    return pd.DataFrame(rows, columns=_eis_feature_columns())


def _eis_feature_columns() -> list[str]:
    return [
        "feature_id",
        "feature_type",
        "axis_value",
        "axis_unit",
        "potential_V",
        "time_s",
        "current_mA",
        "current_density_mA_cm-2",
        "prominence",
        "z_real_ohm",
        "z_imag_ohm",
        "neg_z_imag_ohm",
        "impedance_magnitude_ohm",
        "screening_resistance_ohm",
        "method",
        "assignment_confidence",
        "assignment_source",
        "notes",
    ]


def _eis_summary(processed: pd.DataFrame, features: pd.DataFrame, request: ElectrochemistryProcessingRequest) -> dict[str, Any]:
    z_real = processed["z_real_ohm"].to_numpy(dtype=float)
    neg_imag = processed["neg_z_imag_ohm"].to_numpy(dtype=float)
    min_index = int(np.nanargmin(z_real))
    max_index = int(np.nanargmax(z_real))
    apex_index = int(np.nanargmax(neg_imag))
    span = float(z_real[max_index] - z_real[min_index])
    source = "ea.electrochemistry.eis_nyquist_screening:v0.2"
    convention = str(processed["imaginary_convention"].iloc[0]) if "imaginary_convention" in processed.columns and not processed.empty else "unknown"
    return {
        "measurement_mode": request.measurement_mode,
        "context_summary": request.context_summary,
        "electrode_area_cm2": request.electrode_area_cm2,
        "feature_count": int(len(features)),
        "eis_summary": {
            "point_count": int(len(processed)),
            "z_real_min_ohm": float(z_real[min_index]),
            "z_real_max_ohm": float(z_real[max_index]),
            "high_frequency_intercept_ohm": float(z_real[min_index]),
            "real_axis_span_ohm": span,
            "max_neg_z_imag_ohm": float(neg_imag[apex_index]),
            "apex_z_real_ohm": float(z_real[apex_index]),
            "imaginary_convention": convention,
            "confidence": "low",
            "assignment_source": source,
            "boundary": "Nyquist screening summary only; no equivalent-circuit fitting or Rct assignment was performed.",
        },
        "possible_interpretations": [
            {
                "text": "EIS Nyquist screening features summarize impedance-arc shape in the reviewed dataset; treat high-frequency intercept and real-axis span as orientation values only, not equivalent-circuit parameters.",
                "confidence": "low",
                "evidence": [str(value) for value in features["feature_id"].head(3)] if not features.empty else [],
                "assignment_source": source,
            }
        ],
    }


def _summary(processed: pd.DataFrame, features: pd.DataFrame, request: ElectrochemistryProcessingRequest) -> dict[str, Any]:
    if request.measurement_mode == "eis":
        return _eis_summary(processed, features, request)
    current = processed["processed_current_mA"].to_numpy(dtype=float)
    start_current = float(current[0])
    end_current = float(current[-1])
    retention = float(end_current / start_current * 100.0) if abs(start_current) > 1e-12 else None
    max_index = int(np.nanargmax(current))
    min_index = int(np.nanargmin(current))
    analysis: dict[str, Any] = {
        "measurement_mode": request.measurement_mode,
        "context_summary": request.context_summary,
        "electrode_area_cm2": request.electrode_area_cm2,
        "feature_count": int(len(features)),
        "current_summary": {
            "start_current_mA": start_current,
            "end_current_mA": end_current,
            "retention_percent": retention,
            "max_current_mA": float(current[max_index]),
            "min_current_mA": float(current[min_index]),
        },
        "extrema": [
            _feature_row("ec-extrema-max", "maximum_current", processed.iloc[max_index], None, "ea.electrochemistry.summary:v0.2", "summary_extrema"),
            _feature_row("ec-extrema-min", "minimum_current", processed.iloc[min_index], None, "ea.electrochemistry.summary:v0.2", "summary_extrema"),
        ],
        "possible_interpretations": [],
    }
    if not features.empty:
        evidence = [str(value) for value in features["feature_id"].head(5)]
        analysis["possible_interpretations"].append(
            {
                "text": "Detected electrochemical feature(s) summarize current response in the reviewed dataset; treat them as screening evidence until electrode geometry, electrolyte, reference electrode, scan protocol, and literature context are reviewed.",
                "confidence": "low",
                "evidence": evidence,
                "assignment_source": str(features.iloc[0]["assignment_source"]),
            }
        )
    else:
        analysis["possible_interpretations"].append(
            {
                "text": "No stable peak-like electrochemical feature was detected by the current automatic settings.",
                "confidence": "insufficient",
                "evidence": [],
            }
        )
    if request.measurement_mode in {"chrono", "gcd"}:
        analysis["possible_interpretations"].append(
            {
                "text": "Start/end current summary was recorded for orientation only; stability, capacitance, or device-performance claims require reviewed protocol, normalization, and references.",
                "confidence": "low" if retention is not None else "insufficient",
                "evidence": ["current_summary"],
                "assignment_source": "ea.electrochemistry.summary:v0.2",
            }
        )
    return analysis


def _created_day(created_at: str | None) -> str | None:
    return created_at[:10] if created_at else None


def _uses_v0_2_project_ids(project_id: str) -> bool:
    return project_id.startswith("prj-")


def _plot_electrochemistry(processed: pd.DataFrame, features: pd.DataFrame, output: Path, measurement_mode: str, *, footer: str | None = None) -> None:
    fig, ax = styled_subplots(figsize=(6.0, 4.0))
    if measurement_mode == "eis":
        ax.plot(processed["z_real_ohm"], processed["neg_z_imag_ohm"], color=NATURE_LIKE_COLORS["blue"], linewidth=1.2, marker="o", markersize=2.5, label="Nyquist trace")
        if not features.empty and "z_real_ohm" in features.columns:
            ax.scatter(features["z_real_ohm"], features["neg_z_imag_ohm"], color=NATURE_LIKE_COLORS["black"], s=22, label="Screening features", zorder=3)
            for _, feature in features.head(6).iterrows():
                ax.annotate(
                    str(feature["feature_id"]).replace("eis-", ""),
                    (float(feature["z_real_ohm"]), float(feature["neg_z_imag_ohm"])),
                    textcoords="offset points",
                    xytext=(0, 6),
                    ha="center",
                    fontsize=7,
                )
        style_axis(ax, title="Electrochemistry EIS Nyquist screening", xlabel="Z real (ohm)", ylabel="-Z imag (ohm)")
        ax.set_aspect("equal", adjustable="datalim")
        save_styled_figure(fig, output, footer=footer)
        return
    if "potential_V" in processed.columns:
        x = processed["potential_V"]
        xlabel = "Potential (V)"
    elif "time_s" in processed.columns:
        x = processed["time_s"]
        xlabel = "Time (s)"
    else:
        x = processed["axis_raw"]
        xlabel = "Electrochemistry axis"
    y_column = "processed_current_density_mA_cm-2" if "processed_current_density_mA_cm-2" in processed.columns else "processed_current_mA"
    ylabel = "Current density (mA cm^-2)" if y_column == "processed_current_density_mA_cm-2" else "Current (mA)"
    ax.plot(x, processed[y_column], color=NATURE_LIKE_COLORS["blue"], linewidth=1.2, label="Processed current")
    if not features.empty:
        feature_y = "current_density_mA_cm-2" if y_column == "processed_current_density_mA_cm-2" else "current_mA"
        ax.scatter(features["axis_value"], features[feature_y], color=NATURE_LIKE_COLORS["black"], s=18, label="Detected features", zorder=3)
        for _, feature in features.head(8).iterrows():
            ax.annotate(
                str(feature["feature_id"]).replace("ec-", ""),
                (float(feature["axis_value"]), float(feature[feature_y])),
                textcoords="offset points",
                xytext=(0, 6),
                ha="center",
                fontsize=7,
            )
    style_axis(ax, title=f"Electrochemistry {measurement_mode.upper()} trace", xlabel=xlabel, ylabel=ylabel)
    save_styled_figure(fig, output, footer=footer)


def process_electrochemistry_result(
    root: Path,
    *,
    characterization_metadata_path: Path,
    project_id: str,
    sample_refs: list[str],
    request: ElectrochemistryProcessingRequest,
    created_at: str | None = None,
) -> Path:
    metadata = read_yaml(characterization_metadata_path)
    require_confirmed_review(root, request.column_review_ref)
    require_confirmed_review(root, request.context_review_ref)
    require_confirmed_review(root, request.parameter_review_ref)
    raw_path = root / metadata["project_raw_path"]
    inspection = inspect_electrochemistry_file(raw_path)
    if inspection.file_kind != "electrochemistry":
        raise ElectrochemistryProcessingError(f"File is {inspection.file_kind}, not electrochemistry")

    parameters = _merge_parameters(request.processing_parameters)
    confirmed = _confirmed_frame(raw_path, request)
    if request.measurement_mode == "eis":
        processed, processing_warnings = _apply_eis_processing(confirmed, parameters)
    else:
        processed, processing_warnings = _apply_processing(confirmed, parameters)
    features = _detect_features(processed, parameters, request.measurement_mode)
    analysis = _summary(processed, features, request)
    day = _created_day(created_at)
    project_slug = infer_project_slug(project_id)
    if _uses_v0_2_project_ids(project_id):
        result_id = next_standard_id(root, "result", project_slug, method="electrochemistry", day=day)
        figure_id = next_standard_id(root, "figure", project_slug, method="electrochemistry", day=day)
    else:
        result_id = next_id(root, "electrochemistry_result", day)
        figure_id = None
    sample_dir = sample_refs[0] if sample_refs else "unmapped-sample"
    output_dir = root / "processed" / sample_dir / "electrochemistry" / result_id
    processed_csv = output_dir / "electrochemistry_processed.csv"
    features_csv = output_dir / "electrochemistry_features.csv"
    figure_name = f"{figure_id}.png" if figure_id else "electrochemistry_plot.png"
    figure = output_dir / figure_name
    result_metadata = output_dir / "electrochemistry_metadata.yml"
    for output in [processed_csv, features_csv, figure, result_metadata]:
        assert_not_raw_output_path(root, output)

    output_dir.mkdir(parents=True, exist_ok=True)
    processed.to_csv(processed_csv, index=False)
    features.to_csv(features_csv, index=False)
    _plot_electrochemistry(processed, features, figure, request.measurement_mode, footer=figure_footer(figure_id, None) if figure_id else None)

    warnings: list[Any] = []
    if request.x_unit == "unknown":
        message = "EIS impedance unit remains unknown after confirmation." if request.measurement_mode == "eis" else "Electrochemistry x unit remains unknown after confirmation."
        warnings.append(_warning("electrochemistry_x_unit_unknown", message, severity="medium"))
    if request.current_unit == "unknown" and request.measurement_mode != "eis":
        warnings.append(_warning("electrochemistry_current_unit_unknown", "Electrochemistry current unit remains unknown after confirmation.", severity="medium"))
    if not request.context_summary:
        warnings.append(_warning("electrochemistry_context_missing", "Electrode/electrolyte context summary is empty.", severity="medium"))
    warnings.extend(processing_warnings)
    result = ElectrochemistryProcessingResult(
        electrochemistry_result_id=result_id,
        result_id=result_id,
        project_id=project_id,
        characterization_file_ref=metadata["characterization_id"],
        sample_refs=sample_refs,
        status="warning" if warnings else "success",
        x_column=request.x_column,
        y_column=request.y_column,
        x_unit=request.x_unit,  # type: ignore[arg-type]
        current_unit=request.current_unit,  # type: ignore[arg-type]
        measurement_mode=request.measurement_mode,  # type: ignore[arg-type]
        context_summary=request.context_summary,
        electrode_area_cm2=request.electrode_area_cm2,
        processing_parameters=parameters,
        outputs={
            "figure": str(figure.relative_to(root)),
            "feature_table": str(features_csv.relative_to(root)),
            "peak_table": str(features_csv.relative_to(root)),
            "processed_csv": str(processed_csv.relative_to(root)),
            "metadata": str(result_metadata.relative_to(root)),
        },
        peak_analysis=analysis,
        figure_id=figure_id,
        warnings=warnings,
        review_refs=[request.column_review_ref, request.context_review_ref, request.parameter_review_ref],
        created_at=created_at or EARecord.now_iso(),
        updated_at=created_at or EARecord.now_iso(),
    )
    write_yaml(result_metadata, result.model_dump(exclude_none=True))
    provenance_path = write_provenance_entry(
        root,
        workflow="electrochemistry_processing",
        inputs={
            "records": [str(characterization_metadata_path.relative_to(root))],
            "files": [metadata["project_raw_path"]],
        },
        outputs={
            "records": [str(result_metadata.relative_to(root))],
            "files": [
                str(processed_csv.relative_to(root)),
                str(features_csv.relative_to(root)),
                str(figure.relative_to(root)),
            ],
        },
        parameters={
            "x_column": request.x_column,
            "y_column": request.y_column,
            "x_unit": request.x_unit,
            "current_unit": request.current_unit,
            "measurement_mode": request.measurement_mode,
            "context_summary": request.context_summary,
            "electrode_area_cm2": request.electrode_area_cm2,
            "processing_parameters": parameters,
        },
        review_refs=[request.column_review_ref, request.context_review_ref, request.parameter_review_ref],
        warnings=warnings,
        scripts=[{"path": "src/ea/electrochemistry/service.py", "version": "0.2.0"}],
        created_at=created_at,
    )
    result_data = read_yaml(result_metadata)
    result_data["provenance_refs"] = [provenance_path.stem]
    write_yaml(result_metadata, result_data)
    if figure_id:
        caption = (
            "EIS Nyquist plot with screening impedance features, reviewed context, and traceable processing parameters."
            if request.measurement_mode == "eis"
            else "Electrochemistry trace with processed current, screening features, reviewed context, and traceable processing parameters."
        )
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
                "script": "src/ea/electrochemistry/service.py",
                "parameters": {
                    "x_column": request.x_column,
                    "y_column": request.y_column,
                    "x_unit": request.x_unit,
                    "current_unit": request.current_unit,
                    "measurement_mode": request.measurement_mode,
                    "context_summary": request.context_summary,
                    "electrode_area_cm2": request.electrode_area_cm2,
                    "processing_parameters": parameters,
                },
            },
            caption=caption,
            purpose="electrochemistry_analysis_report",
            style_profile=NATURE_LIKE_STYLE_PROFILE,
            source_data_refs=[
                str(processed_csv.relative_to(root)),
                str(features_csv.relative_to(root)),
            ],
        )
    return result_metadata
