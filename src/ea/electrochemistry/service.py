from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import matplotlib

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
        "eis_circuit_fit": {
            "enabled": False,
            "method": "reviewed_eis_circuit_fit",
            "source": "ea.electrochemistry.eis_circuit_fit:v0.2",
            "frequency_input_column": "frequency_Hz",
            "frequency_unit": "Hz",
            "z_real_input_column": "z_real_ohm",
            "z_imag_input_column": "z_imag_ohm",
            "imaginary_input_convention": "signed_z_imag_ohm",
            "circuit_model": "series_r_rc",
            "frequency_output_column": "frequency_Hz",
            "fit_z_real_column": "eis_fit_z_real_ohm",
            "fit_z_imag_column": "eis_fit_z_imag_ohm",
            "fit_neg_z_imag_column": "eis_fit_neg_z_imag_ohm",
            "initial_values": {
                "rs_ohm": None,
                "rct_ohm": None,
                "c_dl_F": None,
            },
            "bounds": {
                "rs_ohm": {"min": 0.0, "max": None},
                "rct_ohm": {"min": 0.0, "max": None},
                "c_dl_F": {"min": 0.0, "max": None},
            },
            "minimum_points": 8,
            "fit_quality_thresholds": {
                "max_reduced_chi_square_ohm2": None,
                "min_r_squared_complex": None,
            },
            "max_nfev": 10000,
            "perturbation_amplitude_mV": None,
            "frequency_order_reviewed": False,
            "reference_ids": [],
            "reviewer_notes": [],
            "caveats": [],
        },
        "correction_record": {
            "enabled": False,
            "method": "reviewed_metadata_record",
            "source": "ea.electrochemistry.correction_record:v0.2",
            "reference_electrode": {},
            "converted_potential_scale": {},
            "uncompensated_resistance": {},
            "ir_compensation": {},
            "correction_notes": [],
        },
        "potential_conversion": {
            "enabled": False,
            "method": "reviewed_offset_conversion",
            "source": "ea.electrochemistry.potential_conversion:v0.2",
            "input_scale": "",
            "target_scale": "",
            "offset_V": 0.0,
            "equation": "",
            "output_column": "converted_potential_V",
            "reference_electrode": {},
            "reference_ids": [],
            "reviewer_notes": [],
            "caveats": [],
        },
        "ir_drop_correction": {
            "enabled": False,
            "method": "reviewed_ir_drop_correction",
            "source": "ea.electrochemistry.ir_drop_correction:v0.2",
            "potential_input_column": "",
            "current_input_column": "processed_current_mA",
            "current_unit": "mA",
            "ru_ohm": None,
            "compensation_fraction": 1.0,
            "sign_convention": "subtract_i_ru",
            "formula": "E_corrected = E_input - I_A * Ru_ohm * compensation_fraction",
            "output_column": "ir_corrected_potential_V",
            "drop_column": "ir_drop_V",
            "reference_ids": [],
            "reviewer_notes": [],
            "caveats": [],
        },
        "tafel_analysis": {
            "enabled": False,
            "method": "reviewed_tafel_linear_fit",
            "source": "ea.electrochemistry.tafel_analysis:v0.2",
            "potential_input_column": "",
            "current_input_column": "",
            "current_unit": "",
            "fit_window_V": {"min": None, "max": None},
            "minimum_points": 4,
            "minimum_log_span_decades": 0.2,
            "log_current_column": "",
            "fit_potential_column": "tafel_fit_potential_V",
            "overpotential_reference_V": None,
            "overpotential_column": "overpotential_V",
            "reference_scale": "",
            "reference_ids": [],
            "reviewer_notes": [],
            "caveats": [],
        },
        "gcd_analysis": {
            "enabled": False,
            "method": "reviewed_gcd_discharge_metrics",
            "source": "ea.electrochemistry.gcd_analysis:v0.2",
            "time_input_column": "time_s",
            "voltage_input_column": "",
            "voltage_unit": "V",
            "voltage_output_column": "gcd_voltage_V",
            "segment_column": "gcd_discharge_segment",
            "discharge_time_window_s": {"start": None, "end": None},
            "voltage_window_V": {"min": None, "max": None},
            "discharge_current_mA": None,
            "current_sign_convention": "reviewed_discharge_current_magnitude",
            "mass_mg": None,
            "area_cm2": None,
            "active_material_loading_mg_cm2": None,
            "minimum_points": 3,
            "reference_ids": [],
            "reviewer_notes": [],
            "caveats": [],
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
    if "x_unit = s" in text or "x_unit=s" in text or "time_s" in text or "time (s" in text:
        return "s"
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


def _read_raw_numeric_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        frame = pd.read_excel(path)
        frame.columns = [str(column) for column in frame.columns]
        return frame
    rows: list[list[float]] = []
    header: list[str] | None = None
    max_width = 0
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part for part in re.split(r"[\t,\s]+", line) if part]
        if not parts:
            continue
        try:
            row = [float(value) for value in parts]
        except ValueError:
            if header is None:
                header = parts
            continue
        rows.append(row)
        max_width = max(max_width, len(row))
    if not rows:
        return pd.DataFrame()
    width = len(header) if header else max_width
    normalized_rows = [row[:width] + [np.nan] * max(width - len(row), 0) for row in rows]
    columns = header[:width] if header and len(header) >= width else [f"col_{index}" for index in range(width)]
    return pd.DataFrame(normalized_rows, columns=columns)


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


_ELECTROCHEMISTRY_CORRECTION_SECTIONS = (
    "reference_electrode",
    "converted_potential_scale",
    "uncompensated_resistance",
    "ir_compensation",
)


def _has_correction_payload(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_has_correction_payload(item) for item in value.values())
    if isinstance(value, list | tuple):
        return any(_has_correction_payload(item) for item in value)
    return True


def _correction_section(params: dict[str, Any], name: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    value = params.get(name, {})
    if isinstance(value, dict):
        return deepcopy(value), None
    return (
        {},
        _warning(
            "electrochemistry_correction_section_ignored",
            "An electrochemistry correction-record section was ignored because it was not a mapping.",
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
            "electrochemistry_correction_notes_ignored",
            "Electrochemistry correction notes were ignored because they were not a list or non-empty string.",
            severity="medium",
        ),
    )


def _record_correction(parameters: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    params = parameters.get("correction_record", {})
    if not isinstance(params, dict) or not params.get("enabled", False):
        return None, []
    warnings: list[dict[str, Any]] = []
    sections: dict[str, dict[str, Any]] = {}
    for name in _ELECTROCHEMISTRY_CORRECTION_SECTIONS:
        section, warning = _correction_section(params, name)
        sections[name] = section
        if warning:
            warnings.append(warning)
    notes, notes_warning = _correction_notes(params)
    if notes_warning:
        warnings.append(notes_warning)

    reviewed_fields = [name for name, section in sections.items() if _has_correction_payload(section)]
    if _has_correction_payload(notes):
        reviewed_fields.append("correction_notes")
    has_reviewed_context = bool(reviewed_fields)
    if not has_reviewed_context:
        warnings.append(
            _warning(
                "electrochemistry_correction_record_empty",
                "Electrochemistry correction_record was enabled, but no reviewed reference/iR compensation metadata was supplied.",
                severity="medium",
            )
        )
    source = str(params.get("source") or "ea.electrochemistry.correction_record:v0.2")
    return (
        {
            "enabled": True,
            "status": "reviewed_correction_recorded" if has_reviewed_context else "enabled_without_reviewed_correction",
            "method": str(params.get("method") or "reviewed_metadata_record"),
            "assignment_source": source,
            "confidence": "low" if has_reviewed_context else "insufficient",
            "reviewed_correction_fields": reviewed_fields,
            **sections,
            "correction_notes": notes,
            "warnings": warnings,
            "boundary": "Electrochemistry correction record is metadata/provenance only; no automatic potential-scale conversion, iR compensation, equivalent-circuit fitting, Tafel analysis, or performance calculation was applied.",
        },
        warnings,
    )


def _append_correction_interpretation(analysis: dict[str, Any], correction_record: dict[str, Any] | None) -> dict[str, Any]:
    analysis["correction_record"] = correction_record
    if correction_record and correction_record.get("status") == "reviewed_correction_recorded":
        fields = ", ".join(str(value) for value in correction_record.get("reviewed_correction_fields", [])) or "correction record"
        analysis.setdefault("possible_interpretations", []).append(
            {
                "text": (
                    f"Reviewed electrochemistry correction/reference metadata was recorded for {fields}. Use it to interpret potentials, "
                    "currents, and EIS screening summaries, but do not treat the metadata record as an automatic correction or mechanism/performance result."
                ),
                "confidence": correction_record.get("confidence", "low"),
                "evidence": ["correction_record"],
                "assignment_source": correction_record.get("assignment_source", "ea.electrochemistry.correction_record:v0.2"),
            }
        )
    return analysis


def _conversion_mapping(params: dict[str, Any], name: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    value = params.get(name, {})
    if isinstance(value, dict):
        return deepcopy(value), None
    return (
        {},
        _warning(
            "electrochemistry_potential_conversion_section_ignored",
            "An electrochemistry potential-conversion section was ignored because it was not a mapping.",
            severity="medium",
            section=name,
        ),
    )


def _conversion_list(params: dict[str, Any], name: str) -> tuple[list[Any], dict[str, Any] | None]:
    value = params.get(name, [])
    if isinstance(value, list):
        return deepcopy(value), None
    if isinstance(value, tuple):
        return list(value), None
    if isinstance(value, str) and value.strip():
        return [value], None
    if value in (None, "", []):
        return [], None
    return (
        [],
        _warning(
            "electrochemistry_potential_conversion_list_ignored",
            "An electrochemistry potential-conversion list field was ignored because it was not a list or non-empty string.",
            severity="medium",
            field=name,
        ),
    )


def _potential_conversion_column_name(params: dict[str, Any]) -> str:
    output_column = str(params.get("output_column") or "converted_potential_V").strip()
    return output_column or "converted_potential_V"


def _apply_potential_conversion(
    processed: pd.DataFrame,
    parameters: dict[str, Any],
    measurement_mode: str,
) -> tuple[pd.DataFrame, dict[str, Any] | None, list[dict[str, Any]]]:
    params = parameters.get("potential_conversion", {})
    if not isinstance(params, dict) or not params.get("enabled", False):
        return processed, None, []

    converted = processed.copy()
    warnings: list[dict[str, Any]] = []
    source = str(params.get("source") or "ea.electrochemistry.potential_conversion:v0.2")
    method = str(params.get("method") or "reviewed_offset_conversion")
    if method != "reviewed_offset_conversion":
        warnings.append(
            _warning(
                "electrochemistry_potential_conversion_method_unsupported",
                "Only reviewed_offset_conversion is supported for electrochemistry potential conversion in this Experimental Assistant v0.9.7 workflow.",
                severity="medium",
                requested_method=method,
            )
        )
        method = "reviewed_offset_conversion"

    offset, offset_adjusted = _coerce_float(params.get("offset_V"), 0.0)
    if offset_adjusted:
        warnings.append(
            _warning(
                "electrochemistry_potential_conversion_offset_defaulted",
                "Potential conversion offset_V was missing or invalid and defaulted to 0.0 V.",
                severity="medium",
            )
        )
    input_scale = str(params.get("input_scale") or params.get("source_scale") or "").strip()
    target_scale = str(params.get("target_scale") or "").strip()
    if not input_scale:
        warnings.append(
            _warning(
                "electrochemistry_potential_conversion_input_scale_missing",
                "Potential conversion input_scale was not recorded; confirm the original reference scale before scientific interpretation.",
                severity="medium",
            )
        )
    if not target_scale:
        warnings.append(
            _warning(
                "electrochemistry_potential_conversion_target_scale_missing",
                "Potential conversion target_scale was not recorded; confirm the converted reference scale before scientific interpretation.",
                severity="medium",
            )
        )

    reference_electrode, reference_warning = _conversion_mapping(params, "reference_electrode")
    if reference_warning:
        warnings.append(reference_warning)
    reference_ids, reference_ids_warning = _conversion_list(params, "reference_ids")
    if reference_ids_warning:
        warnings.append(reference_ids_warning)
    reviewer_notes, reviewer_notes_warning = _conversion_list(params, "reviewer_notes")
    if reviewer_notes_warning:
        warnings.append(reviewer_notes_warning)
    caveats, caveats_warning = _conversion_list(params, "caveats")
    if caveats_warning:
        warnings.append(caveats_warning)

    output_column = _potential_conversion_column_name(params)
    requested_output_column = output_column
    if output_column in converted.columns:
        output_column = f"{output_column}_converted"
        warnings.append(
            _warning(
                "electrochemistry_potential_conversion_output_column_adjusted",
                "Potential conversion output column already existed and was renamed to avoid overwriting processed data.",
                severity="medium",
                requested_output_column=requested_output_column,
                output_column=output_column,
            )
        )

    applied = False
    input_column = "potential_V" if "potential_V" in converted.columns else None
    if measurement_mode == "eis":
        warnings.append(
            _warning(
                "electrochemistry_potential_conversion_skipped_for_eis",
                "Potential conversion was skipped for EIS mode because the reviewed data are impedance coordinates, not potential/current coordinates.",
                severity="medium",
            )
        )
    elif input_column is None:
        warnings.append(
            _warning(
                "electrochemistry_potential_conversion_no_potential_column",
                "Potential conversion was enabled but no potential_V column was available in the processed electrochemistry table.",
                severity="medium",
            )
        )
    else:
        converted[output_column] = converted[input_column].to_numpy(dtype=float) + offset
        applied = True

    status = "reviewed_potential_conversion_applied" if applied else "enabled_without_potential_conversion"
    confidence = str(params.get("confidence") or ("medium" if applied and input_scale and target_scale else "low" if applied else "insufficient"))
    record = {
        "enabled": True,
        "status": status,
        "method": method,
        "assignment_source": source,
        "confidence": confidence,
        "input_scale": input_scale,
        "target_scale": target_scale,
        "offset_V": offset,
        "equation": str(params.get("equation") or ""),
        "input_column": input_column,
        "output_column": output_column if applied else None,
        "applied_to_processed_data": applied,
        "applied_to_plot_axis": applied,
        "applied_to_feature_detection": False,
        "reference_electrode": reference_electrode,
        "reference_ids": reference_ids,
        "reviewer_notes": reviewer_notes,
        "caveats": caveats,
        "warnings": warnings,
        "boundary": "Potential conversion is a user-reviewed numeric coordinate transform applied to processed voltammetry tables and plots only; it is not iR compensation, Tafel analysis, equivalent-circuit fitting, GCD performance calculation, catalyst ranking, or mechanistic proof.",
    }
    return converted, record, warnings


def _append_potential_conversion_interpretation(analysis: dict[str, Any], conversion_record: dict[str, Any] | None) -> dict[str, Any]:
    analysis["potential_conversion"] = conversion_record
    if conversion_record and conversion_record.get("applied_to_processed_data"):
        target_scale = conversion_record.get("target_scale") or "converted scale"
        output_column = conversion_record.get("output_column") or "converted potential column"
        analysis.setdefault("possible_interpretations", []).append(
            {
                "text": (
                    f"Reviewed potential conversion was applied to processed voltammetry coordinates as {output_column} on the {target_scale} scale. "
                    "Use the converted coordinate for alignment with protocol/literature context, while keeping raw potential and current evidence traceable."
                ),
                "confidence": conversion_record.get("confidence", "low"),
                "evidence": ["potential_conversion"],
                "assignment_source": conversion_record.get("assignment_source", "ea.electrochemistry.potential_conversion:v0.2"),
            }
        )
    return analysis


def _ir_correction_list(params: dict[str, Any], name: str) -> tuple[list[Any], dict[str, Any] | None]:
    value = params.get(name, [])
    if isinstance(value, list):
        return deepcopy(value), None
    if isinstance(value, tuple):
        return list(value), None
    if isinstance(value, str) and value.strip():
        return [value], None
    if value in (None, "", []):
        return [], None
    return (
        [],
        _warning(
            "electrochemistry_ir_drop_correction_list_ignored",
            "An electrochemistry iR drop correction list field was ignored because it was not a list or non-empty string.",
            severity="medium",
            field=name,
        ),
    )


def _required_float(value: Any, name: str) -> tuple[float | None, dict[str, Any] | None]:
    try:
        coerced = float(value)
    except (TypeError, ValueError):
        return (
            None,
            _warning(
                "electrochemistry_ir_drop_correction_required_value_missing",
                "A required numeric iR drop correction value was missing or invalid.",
                severity="medium",
                field=name,
            ),
        )
    if not np.isfinite(coerced):
        return (
            None,
            _warning(
                "electrochemistry_ir_drop_correction_required_value_missing",
                "A required numeric iR drop correction value was missing or invalid.",
                severity="medium",
                field=name,
            ),
        )
    return coerced, None


def _current_series_to_a(series: pd.Series, unit: str) -> tuple[np.ndarray, dict[str, Any] | None]:
    values = series.to_numpy(dtype=float)
    normalized = unit.strip()
    if normalized == "A":
        return values, None
    if normalized == "mA":
        return values / 1000.0, None
    if normalized in {"uA", "µA"}:
        return values / 1_000_000.0, None
    return (
        values / 1000.0,
        _warning(
            "electrochemistry_ir_drop_correction_current_unit_defaulted",
            "iR drop correction current_unit was missing or unsupported and defaulted to mA.",
            severity="medium",
            current_unit=unit,
        ),
    )


def _available_potential_input_column(processed: pd.DataFrame, params: dict[str, Any], potential_conversion_record: dict[str, Any] | None) -> str | None:
    requested = str(params.get("potential_input_column") or "").strip()
    if requested:
        return requested if requested in processed.columns else None
    if potential_conversion_record and potential_conversion_record.get("applied_to_processed_data"):
        candidate = potential_conversion_record.get("output_column")
        if isinstance(candidate, str) and candidate in processed.columns:
            return candidate
    return "potential_V" if "potential_V" in processed.columns else None


def _ir_output_column_name(params: dict[str, Any], fallback: str) -> str:
    value = str(params.get(fallback) or "").strip()
    if value:
        return value
    return "ir_drop_V" if fallback == "drop_column" else "ir_corrected_potential_V"


def _apply_ir_drop_correction(
    processed: pd.DataFrame,
    parameters: dict[str, Any],
    measurement_mode: str,
    potential_conversion_record: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any] | None, list[dict[str, Any]]]:
    params = parameters.get("ir_drop_correction", {})
    if not isinstance(params, dict) or not params.get("enabled", False):
        return processed, None, []

    corrected = processed.copy()
    warnings: list[dict[str, Any]] = []
    source = str(params.get("source") or "ea.electrochemistry.ir_drop_correction:v0.2")
    method = str(params.get("method") or "reviewed_ir_drop_correction")
    if method != "reviewed_ir_drop_correction":
        warnings.append(
            _warning(
                "electrochemistry_ir_drop_correction_method_unsupported",
                "Only reviewed_ir_drop_correction is supported for iR drop correction in this Experimental Assistant v0.9.7 workflow.",
                severity="medium",
                requested_method=method,
            )
        )
        method = "reviewed_ir_drop_correction"

    ru_ohm, ru_warning = _required_float(params.get("ru_ohm"), "ru_ohm")
    if ru_warning:
        warnings.append(ru_warning)
    if ru_ohm is not None and ru_ohm < 0:
        warnings.append(
            _warning(
                "electrochemistry_ir_drop_correction_ru_negative",
                "iR drop correction Ru must be non-negative.",
                severity="medium",
                ru_ohm=ru_ohm,
            )
        )
        ru_ohm = None
    fraction, fraction_adjusted = _coerce_float(params.get("compensation_fraction"), 1.0, minimum=0.0, maximum=1.0)
    if fraction_adjusted:
        warnings.append(
            _warning(
                "electrochemistry_ir_drop_correction_fraction_defaulted",
                "iR drop correction compensation_fraction was missing or outside 0-1 and defaulted to 1.0.",
                severity="medium",
            )
        )

    sign_convention = str(params.get("sign_convention") or "subtract_i_ru").strip()
    if sign_convention not in {"subtract_i_ru", "add_i_ru"}:
        warnings.append(
            _warning(
                "electrochemistry_ir_drop_correction_sign_convention_defaulted",
                "iR drop correction sign_convention was unsupported and defaulted to subtract_i_ru.",
                severity="medium",
                sign_convention=sign_convention,
            )
        )
        sign_convention = "subtract_i_ru"

    potential_input_column = _available_potential_input_column(corrected, params, potential_conversion_record)
    requested_potential_input = str(params.get("potential_input_column") or "").strip()
    current_input_column = str(params.get("current_input_column") or "processed_current_mA").strip() or "processed_current_mA"
    current_unit = str(params.get("current_unit") or "mA")
    output_column = _ir_output_column_name(params, "output_column")
    drop_column = _ir_output_column_name(params, "drop_column")
    for column_name, label in [(output_column, "output_column"), (drop_column, "drop_column")]:
        if column_name in corrected.columns:
            adjusted = f"{column_name}_ir_corrected" if label == "output_column" else f"{column_name}_calculated"
            warnings.append(
                _warning(
                    "electrochemistry_ir_drop_correction_output_column_adjusted",
                    "An iR drop correction output column already existed and was renamed to avoid overwriting processed data.",
                    severity="medium",
                    requested_column=column_name,
                    output_column=adjusted,
                )
            )
            if label == "output_column":
                output_column = adjusted
            else:
                drop_column = adjusted

    reference_ids, reference_warning = _ir_correction_list(params, "reference_ids")
    if reference_warning:
        warnings.append(reference_warning)
    reviewer_notes, notes_warning = _ir_correction_list(params, "reviewer_notes")
    if notes_warning:
        warnings.append(notes_warning)
    caveats, caveats_warning = _ir_correction_list(params, "caveats")
    if caveats_warning:
        warnings.append(caveats_warning)

    applied = False
    potential_offset = 0.0
    if measurement_mode == "eis":
        warnings.append(
            _warning(
                "electrochemistry_ir_drop_correction_skipped_for_eis",
                "iR drop correction was skipped for EIS mode because the reviewed data are impedance coordinates, not potential/current coordinates.",
                severity="medium",
            )
        )
    elif potential_input_column is None:
        warnings.append(
            _warning(
                "electrochemistry_ir_drop_correction_no_potential_column",
                "iR drop correction was enabled but no usable potential input column was available in the processed electrochemistry table.",
                severity="medium",
                requested_potential_input_column=requested_potential_input or "auto",
            )
        )
    elif current_input_column not in corrected.columns:
        warnings.append(
            _warning(
                "electrochemistry_ir_drop_correction_no_current_column",
                "iR drop correction was enabled but the reviewed current input column was not available in the processed electrochemistry table.",
                severity="medium",
                current_input_column=current_input_column,
            )
        )
    elif ru_ohm is not None:
        current_a, current_warning = _current_series_to_a(corrected[current_input_column], current_unit)
        if current_warning:
            warnings.append(current_warning)
        potential = corrected[potential_input_column].to_numpy(dtype=float)
        drop_v = current_a * ru_ohm * fraction
        if sign_convention == "subtract_i_ru":
            corrected_potential = potential - drop_v
        else:
            corrected_potential = potential + drop_v
        corrected[drop_column] = drop_v
        corrected[output_column] = corrected_potential
        applied = True
        if potential_input_column == "potential_V":
            potential_offset = 0.0
        elif potential_conversion_record and potential_input_column == potential_conversion_record.get("output_column"):
            potential_offset = float(potential_conversion_record.get("offset_V") or 0.0)

    status = "reviewed_ir_drop_correction_applied" if applied else "enabled_without_ir_drop_correction"
    record = {
        "enabled": True,
        "status": status,
        "method": method,
        "assignment_source": source,
        "confidence": str(params.get("confidence") or ("medium" if applied else "insufficient")),
        "ru_ohm": ru_ohm,
        "compensation_fraction": fraction,
        "sign_convention": sign_convention,
        "formula": str(params.get("formula") or "E_corrected = E_input - I_A * Ru_ohm * compensation_fraction"),
        "potential_input_column": potential_input_column,
        "current_input_column": current_input_column,
        "current_unit": current_unit,
        "output_column": output_column if applied else None,
        "drop_column": drop_column if applied else None,
        "potential_input_offset_from_potential_V": potential_offset,
        "applied_to_processed_data": applied,
        "applied_to_plot_axis": applied,
        "applied_to_feature_detection": False,
        "reference_ids": reference_ids,
        "reviewer_notes": reviewer_notes,
        "caveats": caveats,
        "warnings": warnings,
        "boundary": "iR drop correction is a user-reviewed numeric coordinate correction applied to processed voltammetry tables and plots only; it is not Tafel analysis, equivalent-circuit fitting, GCD performance calculation, overpotential proof, catalyst ranking, or mechanistic proof.",
    }
    return corrected, record, warnings


def _append_ir_drop_correction_interpretation(analysis: dict[str, Any], ir_record: dict[str, Any] | None) -> dict[str, Any]:
    analysis["ir_drop_correction"] = ir_record
    if ir_record and ir_record.get("applied_to_processed_data"):
        output_column = ir_record.get("output_column") or "iR-corrected potential column"
        analysis.setdefault("possible_interpretations", []).append(
            {
                "text": (
                    f"Reviewed iR drop correction was applied to processed voltammetry coordinates as {output_column}. "
                    "Use this coordinate only with the reviewed Ru, compensation fraction, sign convention, and protocol context."
                ),
                "confidence": ir_record.get("confidence", "low"),
                "evidence": ["ir_drop_correction"],
                "assignment_source": ir_record.get("assignment_source", "ea.electrochemistry.ir_drop_correction:v0.2"),
            }
        )
    return analysis


def _tafel_list(params: dict[str, Any], name: str) -> tuple[list[Any], dict[str, Any] | None]:
    value = params.get(name, [])
    if isinstance(value, list):
        return deepcopy(value), None
    if isinstance(value, tuple):
        return list(value), None
    if isinstance(value, str) and value.strip():
        return [value], None
    if value in (None, "", []):
        return [], None
    return (
        [],
        _warning(
            "electrochemistry_tafel_analysis_list_ignored",
            "An electrochemistry Tafel analysis list field was ignored because it was not a list or non-empty string.",
            severity="medium",
            field=name,
        ),
    )


def _tafel_required_float(value: Any, name: str) -> tuple[float | None, dict[str, Any] | None]:
    try:
        coerced = float(value)
    except (TypeError, ValueError):
        return (
            None,
            _warning(
                "electrochemistry_tafel_analysis_required_value_missing",
                "A required numeric Tafel analysis value was missing or invalid.",
                severity="medium",
                field=name,
            ),
        )
    if not np.isfinite(coerced):
        return (
            None,
            _warning(
                "electrochemistry_tafel_analysis_required_value_missing",
                "A required numeric Tafel analysis value was missing or invalid.",
                severity="medium",
                field=name,
            ),
        )
    return coerced, None


def _mapping_first_present(mapping: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def _tafel_fit_window(params: dict[str, Any]) -> tuple[tuple[float | None, float | None], list[dict[str, Any]]]:
    window = params.get("fit_window_V") or params.get("kinetic_window_V") or {}
    warnings: list[dict[str, Any]] = []
    if not isinstance(window, dict):
        warnings.append(
            _warning(
                "electrochemistry_tafel_analysis_window_ignored",
                "Tafel analysis fit_window_V was ignored because it was not a mapping with min/max values.",
                severity="medium",
            )
        )
        return (None, None), warnings
    lower, lower_warning = _tafel_required_float(_mapping_first_present(window, ("min", "lower", "start", "from")), "fit_window_V.min")
    upper, upper_warning = _tafel_required_float(_mapping_first_present(window, ("max", "upper", "end", "to")), "fit_window_V.max")
    for warning in (lower_warning, upper_warning):
        if warning:
            warnings.append(warning)
    if lower is not None and upper is not None and lower > upper:
        lower, upper = upper, lower
    return (lower, upper), warnings


def _tafel_potential_column(
    processed: pd.DataFrame,
    params: dict[str, Any],
    potential_conversion_record: dict[str, Any] | None,
    ir_drop_correction_record: dict[str, Any] | None,
) -> str | None:
    requested = str(params.get("potential_input_column") or "").strip()
    if requested:
        return requested if requested in processed.columns else None
    if ir_drop_correction_record and ir_drop_correction_record.get("applied_to_processed_data"):
        candidate = ir_drop_correction_record.get("output_column")
        if isinstance(candidate, str) and candidate in processed.columns:
            return candidate
    if potential_conversion_record and potential_conversion_record.get("applied_to_processed_data"):
        candidate = potential_conversion_record.get("output_column")
        if isinstance(candidate, str) and candidate in processed.columns:
            return candidate
    return "potential_V" if "potential_V" in processed.columns else None


def _tafel_current_column(processed: pd.DataFrame, params: dict[str, Any]) -> str | None:
    requested = str(params.get("current_input_column") or "").strip()
    if requested:
        return requested if requested in processed.columns else None
    if "processed_current_density_mA_cm-2" in processed.columns:
        return "processed_current_density_mA_cm-2"
    return "processed_current_mA" if "processed_current_mA" in processed.columns else None


def _tafel_current_unit(params: dict[str, Any], current_column: str | None) -> str:
    requested = str(params.get("current_unit") or "").strip()
    if requested:
        return requested
    if current_column == "processed_current_density_mA_cm-2":
        return "mA cm^-2"
    if current_column == "processed_current_mA":
        return "mA"
    return "unknown"


def _tafel_log_column_name(params: dict[str, Any], current_column: str | None) -> str:
    requested = str(params.get("log_current_column") or "").strip()
    if requested:
        return requested
    if current_column == "processed_current_density_mA_cm-2":
        return "tafel_log10_abs_current_density_mA_cm-2"
    return "tafel_log10_abs_current"


def _unique_processed_column(processed: pd.DataFrame, requested: str, suffix: str, warnings: list[dict[str, Any]], code: str) -> str:
    column = requested.strip() or suffix
    if column not in processed.columns:
        return column
    adjusted = f"{column}_{suffix}"
    counter = 2
    while adjusted in processed.columns:
        adjusted = f"{column}_{suffix}_{counter}"
        counter += 1
    warnings.append(
        _warning(
            code,
            "A reviewed electrochemistry output column already existed and was renamed to avoid overwriting processed data.",
            severity="medium",
            requested_column=column,
            output_column=adjusted,
        )
    )
    return adjusted


def _apply_tafel_analysis(
    processed: pd.DataFrame,
    parameters: dict[str, Any],
    measurement_mode: str,
    potential_conversion_record: dict[str, Any] | None = None,
    ir_drop_correction_record: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any] | None, list[dict[str, Any]]]:
    params = parameters.get("tafel_analysis", {})
    if not isinstance(params, dict) or not params.get("enabled", False):
        return processed, None, []

    analyzed = processed.copy()
    warnings: list[dict[str, Any]] = []
    source = str(params.get("source") or "ea.electrochemistry.tafel_analysis:v0.2")
    method = str(params.get("method") or "reviewed_tafel_linear_fit")
    if method != "reviewed_tafel_linear_fit":
        warnings.append(
            _warning(
                "electrochemistry_tafel_analysis_method_unsupported",
                "Only reviewed_tafel_linear_fit is supported for Tafel analysis in this Experimental Assistant v0.9.7 workflow.",
                severity="medium",
                requested_method=method,
            )
        )
        method = "reviewed_tafel_linear_fit"

    fit_window, window_warnings = _tafel_fit_window(params)
    warnings.extend(window_warnings)
    potential_column = _tafel_potential_column(analyzed, params, potential_conversion_record, ir_drop_correction_record)
    current_column = _tafel_current_column(analyzed, params)
    current_unit = _tafel_current_unit(params, current_column)
    log_column = _unique_processed_column(
        analyzed,
        _tafel_log_column_name(params, current_column),
        "tafel_log",
        warnings,
        "electrochemistry_tafel_analysis_log_column_adjusted",
    )
    fit_column = _unique_processed_column(
        analyzed,
        str(params.get("fit_potential_column") or "tafel_fit_potential_V"),
        "tafel_fit",
        warnings,
        "electrochemistry_tafel_analysis_fit_column_adjusted",
    )
    overpotential_column = _unique_processed_column(
        analyzed,
        str(params.get("overpotential_column") or "overpotential_V"),
        "overpotential",
        warnings,
        "electrochemistry_tafel_analysis_overpotential_column_adjusted",
    )

    reference_ids, reference_warning = _tafel_list(params, "reference_ids")
    if reference_warning:
        warnings.append(reference_warning)
    reviewer_notes, notes_warning = _tafel_list(params, "reviewer_notes")
    if notes_warning:
        warnings.append(notes_warning)
    caveats, caveats_warning = _tafel_list(params, "caveats")
    if caveats_warning:
        warnings.append(caveats_warning)

    overpotential_reference: float | None = None
    overpotential_reference_raw = params.get("overpotential_reference_V")
    if overpotential_reference_raw not in (None, ""):
        overpotential_reference, overpotential_warning = _tafel_required_float(overpotential_reference_raw, "overpotential_reference_V")
        if overpotential_warning:
            warnings.append(overpotential_warning)

    fit_applied = False
    overpotential_applied = False
    fit_stats: dict[str, Any] = {}
    if measurement_mode == "eis":
        warnings.append(
            _warning(
                "electrochemistry_tafel_analysis_skipped_for_eis",
                "Tafel analysis was skipped for EIS mode because the reviewed data are impedance coordinates, not potential/current coordinates.",
                severity="medium",
            )
        )
    elif potential_column is None:
        warnings.append(
            _warning(
                "electrochemistry_tafel_analysis_no_potential_column",
                "Tafel analysis was enabled but no reviewed potential input column was available in the processed electrochemistry table.",
                severity="medium",
                requested_potential_input_column=str(params.get("potential_input_column") or "auto"),
            )
        )
    elif current_column is None:
        warnings.append(
            _warning(
                "electrochemistry_tafel_analysis_no_current_column",
                "Tafel analysis was enabled but no reviewed current/current-density input column was available in the processed electrochemistry table.",
                severity="medium",
                requested_current_input_column=str(params.get("current_input_column") or "auto"),
            )
        )
    else:
        potential = analyzed[potential_column].to_numpy(dtype=float)
        current = analyzed[current_column].to_numpy(dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            log_current = np.where(np.abs(current) > 0, np.log10(np.abs(current)), np.nan)
        analyzed[log_column] = log_current
        if overpotential_reference is not None:
            analyzed[overpotential_column] = potential - overpotential_reference
            overpotential_applied = True

        window_min, window_max = fit_window
        if window_min is None or window_max is None:
            warnings.append(
                _warning(
                    "electrochemistry_tafel_analysis_window_missing",
                    "Tafel analysis was enabled but no complete reviewed fit_window_V min/max was supplied; no Tafel fit was performed.",
                    severity="medium",
                )
            )
        else:
            finite = np.isfinite(potential) & np.isfinite(log_current)
            in_window = finite & (potential >= window_min) & (potential <= window_max)
            minimum_points, _ = _coerce_int(params.get("minimum_points"), 4, minimum=2)
            point_count = int(np.count_nonzero(in_window))
            if point_count < minimum_points:
                warnings.append(
                    _warning(
                        "electrochemistry_tafel_analysis_insufficient_points",
                        "Tafel analysis fit window did not contain enough finite non-zero-current points.",
                        severity="medium",
                        point_count=point_count,
                        minimum_points=minimum_points,
                    )
                )
            else:
                x = log_current[in_window]
                y = potential[in_window]
                log_span = float(np.nanmax(x) - np.nanmin(x))
                min_log_span, _ = _coerce_float(params.get("minimum_log_span_decades"), 0.2, minimum=0.0)
                if log_span < min_log_span:
                    warnings.append(
                        _warning(
                            "electrochemistry_tafel_analysis_low_log_span",
                            "Tafel analysis fit window has a small log-current span; treat the slope as low-confidence screening evidence.",
                            severity="medium",
                            log_span_decades=log_span,
                            minimum_log_span_decades=min_log_span,
                        )
                    )
                slope_v_decade, intercept_v = np.polyfit(x, y, 1)
                fitted = slope_v_decade * log_current + intercept_v
                analyzed[fit_column] = np.nan
                analyzed.loc[in_window, fit_column] = fitted[in_window]
                fitted_window = slope_v_decade * x + intercept_v
                ss_res = float(np.sum((y - fitted_window) ** 2))
                ss_tot = float(np.sum((y - float(np.mean(y))) ** 2))
                r_squared = 1.0 if ss_tot == 0.0 else 1.0 - ss_res / ss_tot
                fit_stats = {
                    "fit_point_count": point_count,
                    "log_current_min": float(np.nanmin(x)),
                    "log_current_max": float(np.nanmax(x)),
                    "log_current_span_decades": log_span,
                    "potential_min_V": float(np.nanmin(y)),
                    "potential_max_V": float(np.nanmax(y)),
                    "tafel_slope_V_decade": float(slope_v_decade),
                    "tafel_slope_mV_decade": float(slope_v_decade * 1000.0),
                    "absolute_tafel_slope_mV_decade": float(abs(slope_v_decade * 1000.0)),
                    "intercept_V": float(intercept_v),
                    "r_squared": float(r_squared),
                }
                fit_applied = True

    status = "reviewed_tafel_fit_applied" if fit_applied else "enabled_without_tafel_fit"
    record = {
        "enabled": True,
        "status": status,
        "method": method,
        "assignment_source": source,
        "confidence": str(params.get("confidence") or ("medium" if fit_applied else "insufficient")),
        "potential_input_column": potential_column,
        "current_input_column": current_column,
        "current_unit": current_unit,
        "current_input_is_density": bool(current_unit and "cm" in current_unit),
        "fit_window_V": {"min": fit_window[0], "max": fit_window[1]},
        "log_current_column": log_column if current_column is not None and measurement_mode != "eis" else None,
        "fit_potential_column": fit_column if fit_applied else None,
        "overpotential_reference_V": overpotential_reference,
        "overpotential_column": overpotential_column if overpotential_applied else None,
        "reference_scale": str(params.get("reference_scale") or ""),
        "fit_statistics": fit_stats,
        "applied_to_processed_data": bool(fit_applied or overpotential_applied),
        "applied_to_plot_axis": False,
        "applied_to_feature_detection": False,
        "reference_ids": reference_ids,
        "reviewer_notes": reviewer_notes,
        "caveats": caveats,
        "warnings": warnings,
        "boundary": "Tafel/overpotential analysis is a user-reviewed screening fit applied only inside the reviewed kinetic window; it is not automatic kinetic-window selection, exchange-current proof, catalyst ranking, EIS fitting, GCD capacity/capacitance calculation, stability assessment, or mechanistic proof.",
    }
    return analyzed, record, warnings


def _append_tafel_analysis_interpretation(analysis: dict[str, Any], tafel_record: dict[str, Any] | None) -> dict[str, Any]:
    analysis["tafel_analysis"] = tafel_record
    if tafel_record and tafel_record.get("status") == "reviewed_tafel_fit_applied":
        stats = tafel_record.get("fit_statistics") or {}
        slope = stats.get("tafel_slope_mV_decade")
        window = tafel_record.get("fit_window_V") or {}
        analysis.setdefault("possible_interpretations", []).append(
            {
                "text": (
                    f"Reviewed Tafel screening fit used {tafel_record.get('potential_input_column')} vs {tafel_record.get('current_input_column')} "
                    f"within {window.get('min')} to {window.get('max')} V and produced a slope of {slope} mV dec^-1. "
                    "Treat it as protocol-dependent screening evidence until normalization, reference scale, replicates, and literature context are reviewed."
                ),
                "confidence": tafel_record.get("confidence", "low"),
                "evidence": ["tafel_analysis"],
                "assignment_source": tafel_record.get("assignment_source", "ea.electrochemistry.tafel_analysis:v0.2"),
            }
        )
    return analysis


def _gcd_list(params: dict[str, Any], name: str) -> tuple[list[Any], dict[str, Any] | None]:
    value = params.get(name, [])
    if isinstance(value, list):
        return deepcopy(value), None
    if isinstance(value, tuple):
        return list(value), None
    if isinstance(value, str) and value.strip():
        return [value], None
    if value in (None, "", []):
        return [], None
    return (
        [],
        _warning(
            "electrochemistry_gcd_analysis_list_ignored",
            "An electrochemistry GCD analysis list field was ignored because it was not a list or non-empty string.",
            severity="medium",
            field=name,
        ),
    )


def _gcd_required_float(value: Any, name: str) -> tuple[float | None, dict[str, Any] | None]:
    try:
        coerced = float(value)
    except (TypeError, ValueError):
        return (
            None,
            _warning(
                "electrochemistry_gcd_analysis_required_value_missing",
                "A required numeric GCD analysis value was missing or invalid.",
                severity="medium",
                field=name,
            ),
        )
    if not np.isfinite(coerced):
        return (
            None,
            _warning(
                "electrochemistry_gcd_analysis_required_value_missing",
                "A required numeric GCD analysis value was missing or invalid.",
                severity="medium",
                field=name,
            ),
        )
    return coerced, None


def _gcd_window(
    params: dict[str, Any],
    field: str,
    lower_keys: tuple[str, ...],
    upper_keys: tuple[str, ...],
) -> tuple[tuple[float | None, float | None], list[dict[str, Any]]]:
    window = params.get(field) or {}
    warnings: list[dict[str, Any]] = []
    if not isinstance(window, dict):
        warnings.append(
            _warning(
                "electrochemistry_gcd_analysis_window_ignored",
                "A GCD analysis window was ignored because it was not a mapping with lower/upper values.",
                severity="medium",
                field=field,
            )
        )
        return (None, None), warnings
    lower, lower_warning = _gcd_required_float(_mapping_first_present(window, lower_keys), f"{field}.lower")
    upper, upper_warning = _gcd_required_float(_mapping_first_present(window, upper_keys), f"{field}.upper")
    for warning in (lower_warning, upper_warning):
        if warning:
            warnings.append(warning)
    if lower is not None and upper is not None and lower > upper:
        lower, upper = upper, lower
    return (lower, upper), warnings


def _gcd_voltage_to_v(series: pd.Series, unit: str) -> tuple[np.ndarray, dict[str, Any] | None]:
    values = series.to_numpy(dtype=float)
    normalized = unit.strip()
    if normalized == "V":
        return values, None
    if normalized == "mV":
        return values / 1000.0, None
    return (
        values,
        _warning(
            "electrochemistry_gcd_analysis_voltage_unit_defaulted",
            "GCD analysis voltage_unit was missing or unsupported and defaulted to V.",
            severity="medium",
            voltage_unit=unit,
        ),
    )


def _gcd_input_column(processed: pd.DataFrame, params: dict[str, Any], field: str, fallback: str) -> str | None:
    requested = str(params.get(field) or "").strip()
    if requested:
        return requested if requested in processed.columns else None
    return fallback if fallback in processed.columns else None


def _gcd_normalization_metrics(
    *,
    charge_c: float,
    capacity_mAh: float,
    capacitance_f: float,
    params: dict[str, Any],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    mass_mg, mass_warning = (None, None)
    area_cm2, area_warning = (None, None)
    loading_mg_cm2, loading_warning = (None, None)
    if params.get("mass_mg") not in (None, ""):
        mass_mg, mass_warning = _gcd_required_float(params.get("mass_mg"), "mass_mg")
    if params.get("area_cm2") not in (None, ""):
        area_cm2, area_warning = _gcd_required_float(params.get("area_cm2"), "area_cm2")
    if params.get("active_material_loading_mg_cm2") not in (None, ""):
        loading_mg_cm2, loading_warning = _gcd_required_float(params.get("active_material_loading_mg_cm2"), "active_material_loading_mg_cm2")
    for warning in (mass_warning, area_warning, loading_warning):
        if warning:
            warnings.append(warning)
    if (mass_mg is None or mass_mg <= 0) and area_cm2 and area_cm2 > 0 and loading_mg_cm2 and loading_mg_cm2 > 0:
        mass_mg = area_cm2 * loading_mg_cm2
    metrics: dict[str, Any] = {
        "mass_mg": mass_mg,
        "area_cm2": area_cm2,
        "active_material_loading_mg_cm2": loading_mg_cm2,
    }
    if mass_mg is not None and mass_mg > 0:
        mass_g = mass_mg / 1000.0
        metrics["mass_g"] = mass_g
        metrics["specific_capacity_mAh_g-1"] = capacity_mAh / mass_g
        metrics["specific_capacitance_F_g-1"] = capacitance_f / mass_g
        metrics["specific_charge_C_g-1"] = charge_c / mass_g
    else:
        warnings.append(
            _warning(
                "electrochemistry_gcd_analysis_mass_missing",
                "GCD analysis mass/loading metadata was not supplied; mass-normalized capacity/capacitance were not calculated.",
                severity="medium",
            )
        )
    if area_cm2 is not None and area_cm2 > 0:
        metrics["areal_capacity_mAh_cm-2"] = capacity_mAh / area_cm2
        metrics["areal_capacitance_F_cm-2"] = capacitance_f / area_cm2
        metrics["areal_charge_C_cm-2"] = charge_c / area_cm2
    else:
        warnings.append(
            _warning(
                "electrochemistry_gcd_analysis_area_missing",
                "GCD analysis area metadata was not supplied; area-normalized capacity/capacitance were not calculated.",
                severity="medium",
            )
        )
    return metrics


def _apply_gcd_analysis(
    processed: pd.DataFrame,
    parameters: dict[str, Any],
    measurement_mode: str,
) -> tuple[pd.DataFrame, dict[str, Any] | None, list[dict[str, Any]]]:
    params = parameters.get("gcd_analysis", {})
    if not isinstance(params, dict) or not params.get("enabled", False):
        return processed, None, []

    analyzed = processed.copy()
    warnings: list[dict[str, Any]] = []
    source = str(params.get("source") or "ea.electrochemistry.gcd_analysis:v0.2")
    method = str(params.get("method") or "reviewed_gcd_discharge_metrics")
    if method != "reviewed_gcd_discharge_metrics":
        warnings.append(
            _warning(
                "electrochemistry_gcd_analysis_method_unsupported",
                "Only reviewed_gcd_discharge_metrics is supported for GCD analysis in this Experimental Assistant v0.9.7 workflow.",
                severity="medium",
                requested_method=method,
            )
        )
        method = "reviewed_gcd_discharge_metrics"

    time_column = _gcd_input_column(analyzed, params, "time_input_column", "time_s")
    voltage_column = _gcd_input_column(analyzed, params, "voltage_input_column", "current_raw")
    voltage_unit = str(params.get("voltage_unit") or "V")
    voltage_output_column = _unique_processed_column(
        analyzed,
        str(params.get("voltage_output_column") or "gcd_voltage_V"),
        "gcd_voltage",
        warnings,
        "electrochemistry_gcd_analysis_voltage_column_adjusted",
    )
    segment_column = _unique_processed_column(
        analyzed,
        str(params.get("segment_column") or "gcd_discharge_segment"),
        "gcd_segment",
        warnings,
        "electrochemistry_gcd_analysis_segment_column_adjusted",
    )
    time_window, time_warnings = _gcd_window(params, "discharge_time_window_s", ("start", "min", "lower", "from"), ("end", "max", "upper", "to"))
    voltage_window, voltage_warnings = _gcd_window(params, "voltage_window_V", ("min", "lower", "start", "from"), ("max", "upper", "end", "to"))
    warnings.extend(time_warnings)
    warnings.extend(voltage_warnings)
    discharge_current_mA, current_warning = _gcd_required_float(params.get("discharge_current_mA"), "discharge_current_mA")
    if current_warning:
        warnings.append(current_warning)
    if discharge_current_mA is not None and discharge_current_mA < 0:
        warnings.append(
            _warning(
                "electrochemistry_gcd_analysis_current_negative",
                "GCD analysis discharge_current_mA was negative; absolute magnitude was used after recording the warning.",
                severity="medium",
                discharge_current_mA=discharge_current_mA,
            )
        )
        discharge_current_mA = abs(discharge_current_mA)
    reference_ids, reference_warning = _gcd_list(params, "reference_ids")
    if reference_warning:
        warnings.append(reference_warning)
    reviewer_notes, notes_warning = _gcd_list(params, "reviewer_notes")
    if notes_warning:
        warnings.append(notes_warning)
    caveats, caveats_warning = _gcd_list(params, "caveats")
    if caveats_warning:
        warnings.append(caveats_warning)

    applied = False
    metrics: dict[str, Any] = {}
    if measurement_mode != "gcd":
        warnings.append(
            _warning(
                "electrochemistry_gcd_analysis_wrong_mode",
                "GCD analysis was skipped because measurement_mode was not gcd.",
                severity="medium",
                measurement_mode=measurement_mode,
            )
        )
    elif time_column is None:
        warnings.append(
            _warning(
                "electrochemistry_gcd_analysis_no_time_column",
                "GCD analysis was enabled but no reviewed time input column was available.",
                severity="medium",
                requested_time_input_column=str(params.get("time_input_column") or "time_s"),
            )
        )
    elif voltage_column is None:
        warnings.append(
            _warning(
                "electrochemistry_gcd_analysis_no_voltage_column",
                "GCD analysis was enabled but no reviewed voltage signal column was available.",
                severity="medium",
                requested_voltage_input_column=str(params.get("voltage_input_column") or "current_raw"),
            )
        )
    elif discharge_current_mA is None:
        warnings.append(
            _warning(
                "electrochemistry_gcd_analysis_current_missing",
                "GCD analysis was enabled but no reviewed discharge_current_mA was supplied.",
                severity="medium",
            )
        )
    else:
        time_values = analyzed[time_column].to_numpy(dtype=float)
        voltage_values, voltage_warning = _gcd_voltage_to_v(analyzed[voltage_column], voltage_unit)
        if voltage_warning:
            warnings.append(voltage_warning)
        analyzed[voltage_output_column] = voltage_values
        analyzed[segment_column] = False
        time_start, time_end = time_window
        voltage_min, voltage_max = voltage_window
        if time_start is None or time_end is None or voltage_min is None or voltage_max is None:
            warnings.append(
                _warning(
                    "electrochemistry_gcd_analysis_window_missing",
                    "GCD analysis was enabled but reviewed time and voltage windows were incomplete; no metrics were calculated.",
                    severity="medium",
                )
            )
        else:
            finite = np.isfinite(time_values) & np.isfinite(voltage_values)
            in_window = finite & (time_values >= time_start) & (time_values <= time_end) & (voltage_values >= voltage_min) & (voltage_values <= voltage_max)
            minimum_points, _ = _coerce_int(params.get("minimum_points"), 3, minimum=2)
            point_count = int(np.count_nonzero(in_window))
            if point_count < minimum_points:
                warnings.append(
                    _warning(
                        "electrochemistry_gcd_analysis_insufficient_points",
                        "GCD analysis reviewed discharge window did not contain enough finite points.",
                        severity="medium",
                        point_count=point_count,
                        minimum_points=minimum_points,
                    )
                )
            else:
                analyzed.loc[in_window, segment_column] = True
                selected = analyzed.loc[in_window, [time_column, voltage_output_column]].copy()
                selected = selected.sort_values(time_column)
                selected_time = selected[time_column].to_numpy(dtype=float)
                selected_voltage = selected[voltage_output_column].to_numpy(dtype=float)
                duration_s = float(selected_time[-1] - selected_time[0])
                voltage_start = float(selected_voltage[0])
                voltage_end = float(selected_voltage[-1])
                voltage_span = float(abs(voltage_start - voltage_end))
                if duration_s <= 0 or voltage_span <= 0:
                    warnings.append(
                        _warning(
                            "electrochemistry_gcd_analysis_invalid_span",
                            "GCD analysis reviewed discharge window did not have positive time and voltage spans.",
                            severity="medium",
                            duration_s=duration_s,
                            voltage_span_V=voltage_span,
                        )
                    )
                else:
                    current_a = discharge_current_mA / 1000.0
                    charge_c = current_a * duration_s
                    capacity_mAh = discharge_current_mA * duration_s / 3600.0
                    capacitance_f = charge_c / voltage_span
                    metrics = {
                        "point_count": point_count,
                        "duration_s": duration_s,
                        "voltage_start_V": voltage_start,
                        "voltage_end_V": voltage_end,
                        "voltage_span_V": voltage_span,
                        "discharge_current_mA": discharge_current_mA,
                        "charge_C": charge_c,
                        "capacity_mAh": capacity_mAh,
                        "capacitance_F": capacitance_f,
                    }
                    metrics.update(_gcd_normalization_metrics(charge_c=charge_c, capacity_mAh=capacity_mAh, capacitance_f=capacitance_f, params=params, warnings=warnings))
                    applied = True

    status = "reviewed_gcd_metrics_applied" if applied else "enabled_without_gcd_metrics"
    record = {
        "enabled": True,
        "status": status,
        "method": method,
        "assignment_source": source,
        "confidence": str(params.get("confidence") or ("medium" if applied else "insufficient")),
        "time_input_column": time_column,
        "voltage_input_column": voltage_column,
        "voltage_unit": voltage_unit,
        "voltage_output_column": voltage_output_column if measurement_mode == "gcd" and voltage_column is not None else None,
        "segment_column": segment_column if measurement_mode == "gcd" and voltage_column is not None else None,
        "discharge_time_window_s": {"start": time_window[0], "end": time_window[1]},
        "voltage_window_V": {"min": voltage_window[0], "max": voltage_window[1]},
        "discharge_current_mA": discharge_current_mA,
        "current_sign_convention": str(params.get("current_sign_convention") or "reviewed_discharge_current_magnitude"),
        "metrics": metrics,
        "applied_to_processed_data": applied,
        "applied_to_plot_axis": applied,
        "applied_to_feature_detection": False,
        "reference_ids": reference_ids,
        "reviewer_notes": reviewer_notes,
        "caveats": caveats,
        "warnings": warnings,
        "boundary": "GCD analysis is a user-reviewed discharge-window metrics record only; it is not automatic segment selection, current-sign inference, device-performance proof, rate-capability or stability assessment, catalyst ranking, EIS fitting, Tafel analysis, or mechanistic proof.",
    }
    return analyzed, record, warnings


def _append_gcd_analysis_interpretation(analysis: dict[str, Any], gcd_record: dict[str, Any] | None) -> dict[str, Any]:
    analysis["gcd_analysis"] = gcd_record
    if gcd_record and gcd_record.get("status") == "reviewed_gcd_metrics_applied":
        metrics = gcd_record.get("metrics") or {}
        analysis.setdefault("possible_interpretations", []).append(
            {
                "text": (
                    f"Reviewed GCD discharge-window metrics used {gcd_record.get('time_input_column')} and {gcd_record.get('voltage_input_column')} "
                    f"with duration {metrics.get('duration_s')} s and voltage span {metrics.get('voltage_span_V')} V. "
                    "Treat capacity/capacitance values as protocol-dependent screening evidence until mass/area normalization, replicates, rate protocol, and literature context are reviewed."
                ),
                "confidence": gcd_record.get("confidence", "low"),
                "evidence": ["gcd_analysis"],
                "assignment_source": gcd_record.get("assignment_source", "ea.electrochemistry.gcd_analysis:v0.2"),
            }
        )
    return analysis


_EIS_CIRCUIT_PARAMETERS = ("rs_ohm", "rct_ohm", "c_dl_F")


def _eis_fit_list(params: dict[str, Any], name: str) -> tuple[list[Any], dict[str, Any] | None]:
    value = params.get(name, [])
    if isinstance(value, list):
        return deepcopy(value), None
    if isinstance(value, tuple):
        return list(value), None
    if isinstance(value, str) and value.strip():
        return [value], None
    if value in (None, "", []):
        return [], None
    return (
        [],
        _warning(
            "electrochemistry_eis_circuit_fit_list_ignored",
            "An EIS circuit-fit list field was ignored because it was not a list or non-empty string.",
            severity="medium",
            field=name,
        ),
    )


def _eis_fit_required_float(value: Any, field: str) -> tuple[float | None, dict[str, Any] | None]:
    try:
        coerced = float(value)
    except (TypeError, ValueError):
        return (
            None,
            _warning(
                "electrochemistry_eis_circuit_fit_required_value_missing",
                "A required numeric EIS circuit-fit value was missing or invalid.",
                severity="medium",
                field=field,
            ),
        )
    if not np.isfinite(coerced):
        return (
            None,
            _warning(
                "electrochemistry_eis_circuit_fit_required_value_missing",
                "A required numeric EIS circuit-fit value was missing or invalid.",
                severity="medium",
                field=field,
            ),
        )
    return coerced, None


def _eis_fit_optional_float(value: Any, field: str) -> tuple[float | None, dict[str, Any] | None]:
    if value in (None, ""):
        return None, None
    try:
        coerced = float(value)
    except (TypeError, ValueError):
        return (
            None,
            _warning(
                "electrochemistry_eis_circuit_fit_optional_value_ignored",
                "An optional numeric EIS circuit-fit value was ignored because it was invalid.",
                severity="medium",
                field=field,
            ),
        )
    if not np.isfinite(coerced):
        return (
            None,
            _warning(
                "electrochemistry_eis_circuit_fit_optional_value_ignored",
                "An optional numeric EIS circuit-fit value was ignored because it was invalid.",
                severity="medium",
                field=field,
            ),
        )
    return coerced, None


def _eis_fit_column_name(params: dict[str, Any], key: str, fallback: str, frame: pd.DataFrame) -> tuple[str, dict[str, Any] | None]:
    requested = str(params.get(key) or fallback).strip() or fallback
    column = requested
    warning: dict[str, Any] | None = None
    if column in frame.columns:
        column = f"{column}_fit"
        warning = _warning(
            "electrochemistry_eis_circuit_fit_output_column_adjusted",
            "An EIS circuit-fit output column already existed and was renamed to avoid overwriting processed data.",
            severity="medium",
            requested_output_column=requested,
            output_column=column,
        )
    return column, warning


def _eis_frequency_to_hz(values: pd.Series, unit: str) -> tuple[np.ndarray, dict[str, Any] | None]:
    frequency = values.to_numpy(dtype=float)
    normalized = unit.strip()
    if normalized == "Hz":
        return frequency, None
    if normalized == "kHz":
        return frequency * 1000.0, None
    if normalized == "MHz":
        return frequency * 1_000_000.0, None
    if normalized == "mHz":
        return frequency / 1000.0, None
    return (
        frequency,
        _warning(
            "electrochemistry_eis_circuit_fit_frequency_unit_defaulted",
            "EIS circuit-fit frequency_unit was missing or unsupported and defaulted to Hz.",
            severity="medium",
            frequency_unit=unit,
        ),
    )


def _eis_imaginary_series(processed: pd.DataFrame, column: str, convention: str) -> tuple[np.ndarray | None, dict[str, Any] | None]:
    if column not in processed.columns:
        return (
            None,
            _warning(
                "electrochemistry_eis_circuit_fit_no_z_imag_column",
                "EIS circuit-fit was enabled but the reviewed imaginary impedance column was not present in processed data.",
                severity="medium",
                z_imag_input_column=column,
            ),
        )
    values = processed[column].to_numpy(dtype=float)
    normalized = convention.strip() or "signed_z_imag_ohm"
    if normalized in {"signed_z_imag_ohm", "signed", "z_imag_ohm"}:
        return values, None
    if normalized in {"neg_z_imag_positive", "negative_imaginary_plotted_positive", "plotted_negative_imaginary"}:
        return -values, None
    return (
        values,
        _warning(
            "electrochemistry_eis_circuit_fit_imaginary_convention_defaulted",
            "EIS circuit-fit imaginary_input_convention was unsupported and defaulted to signed z_imag in ohm.",
            severity="medium",
            imaginary_input_convention=convention,
        ),
    )


def _eis_initial_values(params: dict[str, Any]) -> tuple[dict[str, float], list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    values = params.get("initial_values", {})
    if not isinstance(values, dict):
        values = {}
        warnings.append(
            _warning(
                "electrochemistry_eis_circuit_fit_initial_values_ignored",
                "EIS circuit-fit initial_values were ignored because they were not a mapping.",
                severity="medium",
            )
        )
    parsed: dict[str, float] = {}
    for name in _EIS_CIRCUIT_PARAMETERS:
        value, warning = _eis_fit_required_float(values.get(name), f"initial_values.{name}")
        if warning:
            warnings.append(warning)
        if value is not None:
            parsed[name] = value
    return parsed, warnings


def _eis_bounds(params: dict[str, Any]) -> tuple[dict[str, dict[str, float | None]], list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    bounds = params.get("bounds", {})
    if not isinstance(bounds, dict):
        bounds = {}
        warnings.append(
            _warning(
                "electrochemistry_eis_circuit_fit_bounds_ignored",
                "EIS circuit-fit bounds were ignored because they were not a mapping.",
                severity="medium",
            )
        )
    parsed: dict[str, dict[str, float | None]] = {}
    for name in _EIS_CIRCUIT_PARAMETERS:
        entry = bounds.get(name, {})
        if not isinstance(entry, dict):
            entry = {}
            warnings.append(
                _warning(
                    "electrochemistry_eis_circuit_fit_bound_ignored",
                    "An EIS circuit-fit parameter bound was ignored because it was not a mapping.",
                    severity="medium",
                    parameter=name,
                )
            )
        lower, lower_warning = _eis_fit_optional_float(entry.get("min", 0.0), f"bounds.{name}.min")
        upper, upper_warning = _eis_fit_optional_float(entry.get("max"), f"bounds.{name}.max")
        if lower_warning:
            warnings.append(lower_warning)
        if upper_warning:
            warnings.append(upper_warning)
        if lower is None:
            lower = 0.0
        parsed[name] = {"min": lower, "max": upper}
    return parsed, warnings


def _eis_thresholds(params: dict[str, Any]) -> tuple[dict[str, float | None], list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    thresholds = params.get("fit_quality_thresholds", {})
    if not isinstance(thresholds, dict):
        return (
            {"max_reduced_chi_square_ohm2": None, "min_r_squared_complex": None},
            [
                _warning(
                    "electrochemistry_eis_circuit_fit_thresholds_ignored",
                    "EIS circuit-fit quality thresholds were ignored because they were not a mapping.",
                    severity="medium",
                )
            ],
        )
    parsed: dict[str, float | None] = {}
    for name in ["max_reduced_chi_square_ohm2", "min_r_squared_complex"]:
        value, warning = _eis_fit_optional_float(thresholds.get(name), f"fit_quality_thresholds.{name}")
        if warning:
            warnings.append(warning)
        parsed[name] = value
    return parsed, warnings


def _series_r_rc_impedance(frequency_hz: np.ndarray, rs_ohm: float, rct_ohm: float, c_dl_F: float) -> tuple[np.ndarray, np.ndarray]:
    omega = 2.0 * np.pi * frequency_hz
    rct = max(float(rct_ohm), 1e-30)
    cdl = max(float(c_dl_F), 0.0)
    z_parallel = 1.0 / ((1.0 / rct) + (1j * omega * cdl))
    z_model = float(rs_ohm) + z_parallel
    return np.real(z_model), np.imag(z_model)


def _eis_fit_quality(
    observed_real: np.ndarray,
    observed_imag: np.ndarray,
    fitted_real: np.ndarray,
    fitted_imag: np.ndarray,
    parameter_count: int,
) -> dict[str, float | None]:
    real_residual = observed_real - fitted_real
    imag_residual = observed_imag - fitted_imag
    residual = np.concatenate([real_residual, imag_residual])
    observed = np.concatenate([observed_real, observed_imag])
    fitted = np.concatenate([fitted_real, fitted_imag])
    rss = float(np.sum(residual**2))
    dof = max(int(observed.size - parameter_count), 1)
    sst_complex = float(np.sum((observed - float(np.mean(observed))) ** 2))
    sst_real = float(np.sum((observed_real - float(np.mean(observed_real))) ** 2))
    sst_imag = float(np.sum((observed_imag - float(np.mean(observed_imag))) ** 2))
    return {
        "point_count": int(observed_real.size),
        "residual_sum_squares_ohm2": rss,
        "rmse_ohm": float(np.sqrt(rss / max(observed.size, 1))),
        "reduced_chi_square_ohm2": float(rss / dof),
        "r_squared_complex": float(1.0 - rss / sst_complex) if sst_complex > 0 else None,
        "r_squared_real": float(1.0 - np.sum(real_residual**2) / sst_real) if sst_real > 0 else None,
        "r_squared_imag": float(1.0 - np.sum(imag_residual**2) / sst_imag) if sst_imag > 0 else None,
        "max_abs_real_residual_ohm": float(np.max(np.abs(real_residual))),
        "max_abs_imag_residual_ohm": float(np.max(np.abs(imag_residual))),
        "mean_abs_complex_residual_ohm": float(np.mean(np.abs(observed - fitted))),
    }


def _eis_quality_checks(metrics: dict[str, float | None], thresholds: dict[str, float | None]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    checks: dict[str, Any] = {}
    warnings: list[dict[str, Any]] = []
    max_chi = thresholds.get("max_reduced_chi_square_ohm2")
    if max_chi is not None:
        value = metrics.get("reduced_chi_square_ohm2")
        passed = value is not None and float(value) <= float(max_chi)
        checks["max_reduced_chi_square_ohm2"] = {"threshold": max_chi, "value": value, "passed": bool(passed)}
        if not passed:
            warnings.append(
                _warning(
                    "electrochemistry_eis_circuit_fit_quality_threshold_failed",
                    "EIS circuit-fit reduced chi-square exceeded the reviewed threshold.",
                    severity="medium",
                    metric="reduced_chi_square_ohm2",
                    value=value,
                    threshold=max_chi,
                )
            )
    min_r2 = thresholds.get("min_r_squared_complex")
    if min_r2 is not None:
        value = metrics.get("r_squared_complex")
        passed = value is not None and float(value) >= float(min_r2)
        checks["min_r_squared_complex"] = {"threshold": min_r2, "value": value, "passed": bool(passed)}
        if not passed:
            warnings.append(
                _warning(
                    "electrochemistry_eis_circuit_fit_quality_threshold_failed",
                    "EIS circuit-fit complex R-squared was below the reviewed threshold.",
                    severity="medium",
                    metric="r_squared_complex",
                    value=value,
                    threshold=min_r2,
                )
            )
    return checks, warnings


def _apply_eis_circuit_fit(
    processed: pd.DataFrame,
    parameters: dict[str, Any],
    measurement_mode: str,
    raw_path: Path,
) -> tuple[pd.DataFrame, dict[str, Any] | None, list[dict[str, Any]]]:
    params = parameters.get("eis_circuit_fit", {})
    if not isinstance(params, dict) or not params.get("enabled", False):
        return processed, None, []

    fitted = processed.copy()
    warnings: list[dict[str, Any]] = []
    source = str(params.get("source") or "ea.electrochemistry.eis_circuit_fit:v0.2")
    method = str(params.get("method") or "reviewed_eis_circuit_fit")
    if method != "reviewed_eis_circuit_fit":
        warnings.append(
            _warning(
                "electrochemistry_eis_circuit_fit_method_unsupported",
                "Only reviewed_eis_circuit_fit is supported for EIS circuit fitting in this Experimental Assistant v0.9.7 workflow.",
                severity="medium",
                requested_method=method,
            )
        )
        method = "reviewed_eis_circuit_fit"

    circuit_model = str(params.get("circuit_model") or "series_r_rc").strip()
    if circuit_model not in {"series_r_rc", "randles_rc"}:
        warnings.append(
            _warning(
                "electrochemistry_eis_circuit_fit_model_unsupported",
                "Only a reviewed series_r_rc EIS circuit-fit screening model is supported in this Experimental Assistant v0.9.7 workflow.",
                severity="medium",
                circuit_model=circuit_model,
            )
        )
        circuit_model = "series_r_rc"

    reference_ids, reference_warning = _eis_fit_list(params, "reference_ids")
    if reference_warning:
        warnings.append(reference_warning)
    reviewer_notes, notes_warning = _eis_fit_list(params, "reviewer_notes")
    if notes_warning:
        warnings.append(notes_warning)
    caveats, caveats_warning = _eis_fit_list(params, "caveats")
    if caveats_warning:
        warnings.append(caveats_warning)

    initial_values, initial_warnings = _eis_initial_values(params)
    warnings.extend(initial_warnings)
    bounds, bounds_warnings = _eis_bounds(params)
    warnings.extend(bounds_warnings)
    thresholds, threshold_warnings = _eis_thresholds(params)
    warnings.extend(threshold_warnings)
    perturbation_mV, perturbation_warning = _eis_fit_optional_float(params.get("perturbation_amplitude_mV"), "perturbation_amplitude_mV")
    if perturbation_warning:
        warnings.append(perturbation_warning)

    frequency_column = str(params.get("frequency_input_column") or "frequency_Hz").strip()
    frequency_unit = str(params.get("frequency_unit") or "Hz").strip()
    z_real_column = str(params.get("z_real_input_column") or "z_real_ohm").strip()
    z_imag_column = str(params.get("z_imag_input_column") or "z_imag_ohm").strip()
    imaginary_convention = str(params.get("imaginary_input_convention") or "signed_z_imag_ohm").strip()
    minimum_points, minimum_adjusted = _coerce_int(params.get("minimum_points"), 8, minimum=3)
    if minimum_adjusted:
        warnings.append(
            _warning(
                "electrochemistry_eis_circuit_fit_minimum_points_defaulted",
                "EIS circuit-fit minimum_points was missing or below 3 and defaulted to 8.",
                severity="medium",
            )
        )

    applied = False
    fitted_parameters: dict[str, float] = {}
    fit_metrics: dict[str, float | None] = {}
    quality_checks: dict[str, Any] = {}
    optimizer_status: dict[str, Any] = {}
    frequency_output_column = None
    fit_z_real_column = None
    fit_z_imag_column = None
    fit_neg_z_imag_column = None

    if measurement_mode != "eis":
        warnings.append(
            _warning(
                "electrochemistry_eis_circuit_fit_wrong_mode",
                "EIS circuit-fit was skipped because measurement_mode was not eis.",
                severity="medium",
                measurement_mode=measurement_mode,
            )
        )
    elif z_real_column not in fitted.columns:
        warnings.append(
            _warning(
                "electrochemistry_eis_circuit_fit_no_z_real_column",
                "EIS circuit-fit was enabled but the reviewed real impedance column was not present in processed data.",
                severity="medium",
                z_real_input_column=z_real_column,
            )
        )
    else:
        z_imag, imag_warning = _eis_imaginary_series(fitted, z_imag_column, imaginary_convention)
        if imag_warning:
            warnings.append(imag_warning)
        if z_imag is not None and len(initial_values) == len(_EIS_CIRCUIT_PARAMETERS):
            raw_frame = _read_raw_numeric_table(raw_path)
            raw_frame.columns = [str(column) for column in raw_frame.columns]
            if frequency_column not in raw_frame.columns:
                warnings.append(
                    _warning(
                        "electrochemistry_eis_circuit_fit_no_frequency_column",
                        "EIS circuit-fit was enabled but the reviewed frequency column was not present in the raw table.",
                        severity="medium",
                        frequency_input_column=frequency_column,
                    )
                )
            else:
                frequency_raw = pd.to_numeric(raw_frame[frequency_column], errors="coerce").dropna().reset_index(drop=True)
                frequency_hz, frequency_warning = _eis_frequency_to_hz(frequency_raw, frequency_unit)
                if frequency_warning:
                    warnings.append(frequency_warning)
                if len(frequency_hz) != len(fitted):
                    warnings.append(
                        _warning(
                            "electrochemistry_eis_circuit_fit_frequency_length_mismatch",
                            "EIS circuit-fit was skipped because numeric frequency values did not align with the reviewed impedance rows.",
                            severity="medium",
                            frequency_count=int(len(frequency_hz)),
                            impedance_count=int(len(fitted)),
                        )
                    )
                elif np.any(~np.isfinite(frequency_hz)) or np.any(frequency_hz <= 0):
                    warnings.append(
                        _warning(
                            "electrochemistry_eis_circuit_fit_frequency_invalid",
                            "EIS circuit-fit was skipped because reviewed frequency values must be positive finite numbers.",
                            severity="medium",
                        )
                    )
                elif len(fitted) < minimum_points:
                    warnings.append(
                        _warning(
                            "electrochemistry_eis_circuit_fit_insufficient_points",
                            "EIS circuit-fit was skipped because the reviewed data had fewer points than minimum_points.",
                            severity="medium",
                            point_count=int(len(fitted)),
                            minimum_points=minimum_points,
                        )
                    )
                else:
                    lower_bounds: list[float] = []
                    upper_bounds: list[float] = []
                    x0: list[float] = []
                    bounds_valid = True
                    for name in _EIS_CIRCUIT_PARAMETERS:
                        initial = float(initial_values[name])
                        lower = bounds[name]["min"]
                        upper = bounds[name]["max"]
                        lower_value = float(lower if lower is not None else 0.0)
                        upper_value = float(upper) if upper is not None else np.inf
                        if upper_value <= lower_value or initial < lower_value or initial > upper_value:
                            bounds_valid = False
                            warnings.append(
                                _warning(
                                    "electrochemistry_eis_circuit_fit_bounds_invalid",
                                    "EIS circuit-fit was skipped because a reviewed initial value was outside the reviewed parameter bounds.",
                                    severity="medium",
                                    parameter=name,
                                    initial_value=initial,
                                    lower_bound=lower_value,
                                    upper_bound=upper_value,
                                )
                            )
                        lower_bounds.append(lower_value)
                        upper_bounds.append(upper_value)
                        x0.append(initial)
                    if bounds_valid:
                        observed_real = fitted[z_real_column].to_numpy(dtype=float)
                        observed_imag = np.asarray(z_imag, dtype=float)

                        def residual(values: np.ndarray) -> np.ndarray:
                            model_real, model_imag = _series_r_rc_impedance(
                                frequency_hz,
                                float(values[0]),
                                float(values[1]),
                                float(values[2]),
                            )
                            return np.concatenate([model_real - observed_real, model_imag - observed_imag])

                        max_nfev, max_nfev_adjusted = _coerce_int(params.get("max_nfev"), 10000, minimum=100)
                        if max_nfev_adjusted:
                            warnings.append(
                                _warning(
                                    "electrochemistry_eis_circuit_fit_max_nfev_defaulted",
                                    "EIS circuit-fit max_nfev was missing or below 100 and defaulted to 10000.",
                                    severity="medium",
                                )
                            )
                        try:
                            result = least_squares(
                                residual,
                                np.asarray(x0, dtype=float),
                                bounds=(np.asarray(lower_bounds, dtype=float), np.asarray(upper_bounds, dtype=float)),
                                max_nfev=max_nfev,
                            )
                        except ValueError as exc:
                            warnings.append(
                                _warning(
                                    "electrochemistry_eis_circuit_fit_optimizer_failed",
                                    "EIS circuit-fit optimizer failed before producing reviewed fit parameters.",
                                    severity="medium",
                                    error=str(exc),
                                )
                            )
                        else:
                            model_real, model_imag = _series_r_rc_impedance(
                                frequency_hz,
                                float(result.x[0]),
                                float(result.x[1]),
                                float(result.x[2]),
                            )
                            fit_metrics = _eis_fit_quality(observed_real, observed_imag, model_real, model_imag, len(_EIS_CIRCUIT_PARAMETERS))
                            quality_checks, quality_warnings = _eis_quality_checks(fit_metrics, thresholds)
                            warnings.extend(quality_warnings)
                            for name, value in zip(_EIS_CIRCUIT_PARAMETERS, result.x, strict=True):
                                fitted_parameters[name] = float(value)
                            optimizer_status = {
                                "success": bool(result.success),
                                "status": int(result.status),
                                "message": str(result.message),
                                "nfev": int(result.nfev),
                                "cost": float(result.cost),
                            }
                            applied = bool(result.success)
                            if result.success:
                                frequency_output_column, warning = _eis_fit_column_name(params, "frequency_output_column", "frequency_Hz", fitted)
                                if warning:
                                    warnings.append(warning)
                                fit_z_real_column, warning = _eis_fit_column_name(params, "fit_z_real_column", "eis_fit_z_real_ohm", fitted)
                                if warning:
                                    warnings.append(warning)
                                fit_z_imag_column, warning = _eis_fit_column_name(params, "fit_z_imag_column", "eis_fit_z_imag_ohm", fitted)
                                if warning:
                                    warnings.append(warning)
                                fit_neg_z_imag_column, warning = _eis_fit_column_name(params, "fit_neg_z_imag_column", "eis_fit_neg_z_imag_ohm", fitted)
                                if warning:
                                    warnings.append(warning)
                                fitted[frequency_output_column] = frequency_hz
                                fitted[fit_z_real_column] = model_real
                                fitted[fit_z_imag_column] = model_imag
                                fitted[fit_neg_z_imag_column] = -model_imag
                            else:
                                warnings.append(
                                    _warning(
                                        "electrochemistry_eis_circuit_fit_optimizer_not_converged",
                                        "EIS circuit-fit optimizer returned without convergence; parameters are recorded as low-confidence screening output.",
                                        severity="medium",
                                        optimizer_message=str(result.message),
                                    )
                                )

    if not bool(params.get("frequency_order_reviewed", False)):
        warnings.append(
            _warning(
                "electrochemistry_eis_circuit_fit_frequency_order_not_reviewed",
                "EIS circuit-fit frequency_order_reviewed was not true; interpret fitted parameters only as low-confidence screening output.",
                severity="medium",
            )
        )
    if perturbation_mV is None:
        warnings.append(
            _warning(
                "electrochemistry_eis_circuit_fit_perturbation_missing",
                "EIS circuit-fit perturbation_amplitude_mV was not recorded; compare fitted values cautiously.",
                severity="medium",
            )
        )

    status = "reviewed_eis_circuit_fit_applied" if applied else "enabled_without_eis_circuit_fit"
    failed_quality = any(isinstance(item, dict) and item.get("passed") is False for item in quality_checks.values())
    confidence = str(
        params.get("confidence")
        or (
            "medium"
            if applied and not failed_quality and bool(params.get("frequency_order_reviewed", False)) and perturbation_mV is not None
            else "low"
            if applied
            else "insufficient"
        )
    )
    record = {
        "enabled": True,
        "status": status,
        "method": method,
        "assignment_source": source,
        "confidence": confidence,
        "circuit_model": circuit_model,
        "frequency_input_column": frequency_column,
        "frequency_unit": frequency_unit,
        "frequency_output_column": frequency_output_column,
        "z_real_input_column": z_real_column,
        "z_imag_input_column": z_imag_column,
        "imaginary_input_convention": imaginary_convention,
        "fit_z_real_column": fit_z_real_column,
        "fit_z_imag_column": fit_z_imag_column,
        "fit_neg_z_imag_column": fit_neg_z_imag_column,
        "initial_values": initial_values,
        "bounds": bounds,
        "fitted_parameters": fitted_parameters,
        "fit_quality": fit_metrics,
        "fit_quality_thresholds": thresholds,
        "fit_quality_checks": quality_checks,
        "optimizer_status": optimizer_status,
        "minimum_points": minimum_points,
        "perturbation_amplitude_mV": perturbation_mV,
        "frequency_order_reviewed": bool(params.get("frequency_order_reviewed", False)),
        "applied_to_processed_data": applied,
        "applied_to_plot_axis": applied,
        "applied_to_feature_detection": False,
        "reference_ids": reference_ids,
        "reviewer_notes": reviewer_notes,
        "caveats": caveats,
        "warnings": warnings,
        "boundary": "EIS circuit fitting is a user-reviewed screening fit for one explicitly selected equivalent-circuit model; it is not automatic model selection, mechanism proof, device-performance proof, replicate statistics, Tafel/GCD analysis, catalyst ranking, or a durable Rct/Warburg conclusion without protocol, replicate, and literature review.",
    }
    return fitted, record, warnings


def _append_eis_circuit_fit_interpretation(analysis: dict[str, Any], fit_record: dict[str, Any] | None) -> dict[str, Any]:
    analysis["eis_circuit_fit"] = fit_record
    if fit_record and fit_record.get("status") == "reviewed_eis_circuit_fit_applied":
        parameters = fit_record.get("fitted_parameters") or {}
        quality = fit_record.get("fit_quality") or {}
        analysis.setdefault("possible_interpretations", []).append(
            {
                "text": (
                    f"Reviewed EIS circuit-fit screening used the {fit_record.get('circuit_model')} model and returned "
                    f"Rs={parameters.get('rs_ohm')} ohm, Rct={parameters.get('rct_ohm')} ohm, and Cdl={parameters.get('c_dl_F')} F "
                    f"with complex R^2={quality.get('r_squared_complex')}. Treat these as model-dependent screening parameters until the circuit choice, frequency order, perturbation amplitude, replicates, and literature context are reviewed."
                ),
                "confidence": fit_record.get("confidence", "low"),
                "evidence": ["eis_circuit_fit"],
                "assignment_source": fit_record.get("assignment_source", "ea.electrochemistry.eis_circuit_fit:v0.2"),
            }
        )
    return analysis


def _eis_summary(
    processed: pd.DataFrame,
    features: pd.DataFrame,
    request: ElectrochemistryProcessingRequest,
    correction_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    z_real = processed["z_real_ohm"].to_numpy(dtype=float)
    neg_imag = processed["neg_z_imag_ohm"].to_numpy(dtype=float)
    min_index = int(np.nanargmin(z_real))
    max_index = int(np.nanargmax(z_real))
    apex_index = int(np.nanargmax(neg_imag))
    span = float(z_real[max_index] - z_real[min_index])
    source = "ea.electrochemistry.eis_nyquist_screening:v0.2"
    convention = str(processed["imaginary_convention"].iloc[0]) if "imaginary_convention" in processed.columns and not processed.empty else "unknown"
    analysis = {
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
    return _append_correction_interpretation(analysis, correction_record)


def _summary(
    processed: pd.DataFrame,
    features: pd.DataFrame,
    request: ElectrochemistryProcessingRequest,
    correction_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if request.measurement_mode == "eis":
        return _eis_summary(processed, features, request, correction_record)
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
    return _append_correction_interpretation(analysis, correction_record)


def _created_day(created_at: str | None) -> str | None:
    return created_at[:10] if created_at else None


def _uses_v0_2_project_ids(project_id: str) -> bool:
    return project_id.startswith("prj-")


def _plot_electrochemistry(
    processed: pd.DataFrame,
    features: pd.DataFrame,
    output: Path,
    measurement_mode: str,
    *,
    potential_conversion_record: dict[str, Any] | None = None,
    ir_drop_correction_record: dict[str, Any] | None = None,
    eis_circuit_fit_record: dict[str, Any] | None = None,
    gcd_analysis_record: dict[str, Any] | None = None,
    footer: str | None = None,
) -> None:
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
        if eis_circuit_fit_record and eis_circuit_fit_record.get("applied_to_plot_axis"):
            fit_real = eis_circuit_fit_record.get("fit_z_real_column")
            fit_neg_imag = eis_circuit_fit_record.get("fit_neg_z_imag_column")
            if isinstance(fit_real, str) and isinstance(fit_neg_imag, str) and fit_real in processed.columns and fit_neg_imag in processed.columns:
                ax.plot(
                    processed[fit_real],
                    processed[fit_neg_imag],
                    color=NATURE_LIKE_COLORS["orange"],
                    linewidth=1.1,
                    linestyle="--",
                    label="Reviewed circuit fit",
                )
        style_axis(ax, title="Electrochemistry EIS Nyquist screening", xlabel="Z real (ohm)", ylabel="-Z imag (ohm)")
        ax.set_aspect("equal", adjustable="datalim")
        save_styled_figure(fig, output, footer=footer)
        return
    if measurement_mode == "gcd" and gcd_analysis_record and gcd_analysis_record.get("applied_to_plot_axis"):
        time_column = gcd_analysis_record.get("time_input_column")
        voltage_column = gcd_analysis_record.get("voltage_output_column")
        if isinstance(time_column, str) and isinstance(voltage_column, str) and time_column in processed.columns and voltage_column in processed.columns:
            ax.plot(processed[time_column], processed[voltage_column], color=NATURE_LIKE_COLORS["blue"], linewidth=1.2, label="Reviewed GCD voltage")
            segment_column = gcd_analysis_record.get("segment_column")
            if isinstance(segment_column, str) and segment_column in processed.columns:
                segment = processed[segment_column].astype(bool)
                if bool(segment.any()):
                    ax.scatter(
                        processed.loc[segment, time_column],
                        processed.loc[segment, voltage_column],
                        color=NATURE_LIKE_COLORS["black"],
                        s=12,
                        label="Reviewed discharge window",
                        zorder=3,
                    )
            style_axis(ax, title="Electrochemistry GCD discharge screening", xlabel="Time (s)", ylabel="Voltage (V)")
            save_styled_figure(fig, output, footer=footer)
            return
    ir_column = None
    if ir_drop_correction_record and ir_drop_correction_record.get("applied_to_plot_axis"):
        candidate = ir_drop_correction_record.get("output_column")
        if isinstance(candidate, str) and candidate in processed.columns:
            ir_column = candidate
    conversion_column = None
    if potential_conversion_record and potential_conversion_record.get("applied_to_plot_axis"):
        candidate = potential_conversion_record.get("output_column")
        if isinstance(candidate, str) and candidate in processed.columns:
            conversion_column = candidate
    if ir_column:
        x = processed[ir_column]
        xlabel = "iR-corrected potential (V)"
    elif conversion_column:
        x = processed[conversion_column]
        target_scale = potential_conversion_record.get("target_scale") or "converted scale"
        xlabel = f"Potential vs {target_scale} (V)"
    elif "potential_V" in processed.columns:
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
        if ir_column and "potential_V" in features.columns:
            offset = float(ir_drop_correction_record.get("potential_input_offset_from_potential_V") or 0.0)
            ru_ohm = float(ir_drop_correction_record.get("ru_ohm") or 0.0)
            fraction = float(ir_drop_correction_record.get("compensation_fraction") or 1.0)
            feature_current_a = features["current_mA"] / 1000.0
            feature_drop = feature_current_a * ru_ohm * fraction
            if ir_drop_correction_record.get("sign_convention") == "add_i_ru":
                feature_x = features["potential_V"] + offset + feature_drop
            else:
                feature_x = features["potential_V"] + offset - feature_drop
        elif conversion_column and "potential_V" in features.columns:
            feature_x = features["potential_V"] + float(potential_conversion_record.get("offset_V", 0.0))
        else:
            feature_x = features["axis_value"]
        ax.scatter(feature_x, features[feature_y], color=NATURE_LIKE_COLORS["black"], s=18, label="Detected features", zorder=3)
        for _, feature in features.head(8).iterrows():
            feature_x_value = float(feature["axis_value"])
            if ir_column and "potential_V" in feature.index and pd.notna(feature.get("potential_V")):
                offset = float(ir_drop_correction_record.get("potential_input_offset_from_potential_V") or 0.0)
                ru_ohm = float(ir_drop_correction_record.get("ru_ohm") or 0.0)
                fraction = float(ir_drop_correction_record.get("compensation_fraction") or 1.0)
                feature_drop = float(feature["current_mA"]) / 1000.0 * ru_ohm * fraction
                if ir_drop_correction_record.get("sign_convention") == "add_i_ru":
                    feature_x_value = float(feature["potential_V"]) + offset + feature_drop
                else:
                    feature_x_value = float(feature["potential_V"]) + offset - feature_drop
            elif conversion_column and "potential_V" in feature.index and pd.notna(feature.get("potential_V")):
                feature_x_value = float(feature["potential_V"]) + float(potential_conversion_record.get("offset_V", 0.0))
            ax.annotate(
                str(feature["feature_id"]).replace("ec-", ""),
                (feature_x_value, float(feature[feature_y])),
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
    processed, potential_conversion_record, potential_conversion_warnings = _apply_potential_conversion(processed, parameters, request.measurement_mode)
    processed, ir_drop_correction_record, ir_drop_correction_warnings = _apply_ir_drop_correction(processed, parameters, request.measurement_mode, potential_conversion_record)
    processed, tafel_analysis_record, tafel_analysis_warnings = _apply_tafel_analysis(
        processed,
        parameters,
        request.measurement_mode,
        potential_conversion_record,
        ir_drop_correction_record,
    )
    processed, gcd_analysis_record, gcd_analysis_warnings = _apply_gcd_analysis(processed, parameters, request.measurement_mode)
    processed, eis_circuit_fit_record, eis_circuit_fit_warnings = _apply_eis_circuit_fit(processed, parameters, request.measurement_mode, raw_path)
    features = _detect_features(processed, parameters, request.measurement_mode)
    correction_record, correction_warnings = _record_correction(parameters)
    analysis = _summary(processed, features, request, correction_record)
    analysis = _append_potential_conversion_interpretation(analysis, potential_conversion_record)
    analysis = _append_ir_drop_correction_interpretation(analysis, ir_drop_correction_record)
    analysis = _append_tafel_analysis_interpretation(analysis, tafel_analysis_record)
    analysis = _append_gcd_analysis_interpretation(analysis, gcd_analysis_record)
    analysis = _append_eis_circuit_fit_interpretation(analysis, eis_circuit_fit_record)
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
    correction_yml = output_dir / "electrochemistry_correction.yml"
    potential_conversion_yml = output_dir / "electrochemistry_potential_conversion.yml"
    ir_drop_correction_yml = output_dir / "electrochemistry_ir_drop_correction.yml"
    tafel_analysis_yml = output_dir / "electrochemistry_tafel_analysis.yml"
    gcd_analysis_yml = output_dir / "electrochemistry_gcd_analysis.yml"
    eis_circuit_fit_yml = output_dir / "electrochemistry_eis_circuit_fit.yml"
    figure_name = f"{figure_id}.png" if figure_id else "electrochemistry_plot.png"
    figure = output_dir / figure_name
    result_metadata = output_dir / "electrochemistry_metadata.yml"
    for output in [processed_csv, features_csv, correction_yml, potential_conversion_yml, ir_drop_correction_yml, tafel_analysis_yml, gcd_analysis_yml, eis_circuit_fit_yml, figure, result_metadata]:
        assert_not_raw_output_path(root, output)

    output_dir.mkdir(parents=True, exist_ok=True)
    processed.to_csv(processed_csv, index=False)
    features.to_csv(features_csv, index=False)
    correction_ref: str | None = None
    if correction_record is not None:
        correction_ref = correction_yml.relative_to(root).as_posix()
        correction_record["record_ref"] = correction_ref
        write_yaml(correction_yml, correction_record)
        if analysis.get("correction_record"):
            analysis["correction_record"]["record_ref"] = correction_ref
    potential_conversion_ref: str | None = None
    if potential_conversion_record is not None:
        potential_conversion_ref = potential_conversion_yml.relative_to(root).as_posix()
        potential_conversion_record["record_ref"] = potential_conversion_ref
        write_yaml(potential_conversion_yml, potential_conversion_record)
        if analysis.get("potential_conversion"):
            analysis["potential_conversion"]["record_ref"] = potential_conversion_ref
    ir_drop_correction_ref: str | None = None
    if ir_drop_correction_record is not None:
        ir_drop_correction_ref = ir_drop_correction_yml.relative_to(root).as_posix()
        ir_drop_correction_record["record_ref"] = ir_drop_correction_ref
        write_yaml(ir_drop_correction_yml, ir_drop_correction_record)
        if analysis.get("ir_drop_correction"):
            analysis["ir_drop_correction"]["record_ref"] = ir_drop_correction_ref
    tafel_analysis_ref: str | None = None
    if tafel_analysis_record is not None:
        tafel_analysis_ref = tafel_analysis_yml.relative_to(root).as_posix()
        tafel_analysis_record["record_ref"] = tafel_analysis_ref
        write_yaml(tafel_analysis_yml, tafel_analysis_record)
        if analysis.get("tafel_analysis"):
            analysis["tafel_analysis"]["record_ref"] = tafel_analysis_ref
    gcd_analysis_ref: str | None = None
    if gcd_analysis_record is not None:
        gcd_analysis_ref = gcd_analysis_yml.relative_to(root).as_posix()
        gcd_analysis_record["record_ref"] = gcd_analysis_ref
        write_yaml(gcd_analysis_yml, gcd_analysis_record)
        if analysis.get("gcd_analysis"):
            analysis["gcd_analysis"]["record_ref"] = gcd_analysis_ref
    eis_circuit_fit_ref: str | None = None
    if eis_circuit_fit_record is not None:
        eis_circuit_fit_ref = eis_circuit_fit_yml.relative_to(root).as_posix()
        eis_circuit_fit_record["record_ref"] = eis_circuit_fit_ref
        write_yaml(eis_circuit_fit_yml, eis_circuit_fit_record)
        if analysis.get("eis_circuit_fit"):
            analysis["eis_circuit_fit"]["record_ref"] = eis_circuit_fit_ref
    _plot_electrochemistry(
        processed,
        features,
        figure,
        request.measurement_mode,
        potential_conversion_record=potential_conversion_record,
        ir_drop_correction_record=ir_drop_correction_record,
        eis_circuit_fit_record=eis_circuit_fit_record,
        gcd_analysis_record=gcd_analysis_record,
        footer=figure_footer(figure_id, None) if figure_id else None,
    )

    warnings: list[Any] = []
    if request.x_unit == "unknown":
        message = "EIS impedance unit remains unknown after confirmation." if request.measurement_mode == "eis" else "Electrochemistry x unit remains unknown after confirmation."
        warnings.append(_warning("electrochemistry_x_unit_unknown", message, severity="medium"))
    if request.current_unit == "unknown" and request.measurement_mode not in {"eis", "gcd"}:
        warnings.append(_warning("electrochemistry_current_unit_unknown", "Electrochemistry current unit remains unknown after confirmation.", severity="medium"))
    if not request.context_summary:
        warnings.append(_warning("electrochemistry_context_missing", "Electrode/electrolyte context summary is empty.", severity="medium"))
    warnings.extend(processing_warnings)
    warnings.extend(correction_warnings)
    warnings.extend(potential_conversion_warnings)
    warnings.extend(ir_drop_correction_warnings)
    warnings.extend(tafel_analysis_warnings)
    warnings.extend(gcd_analysis_warnings)
    warnings.extend(eis_circuit_fit_warnings)
    outputs = {
        "figure": figure.relative_to(root).as_posix(),
        "feature_table": features_csv.relative_to(root).as_posix(),
        "peak_table": features_csv.relative_to(root).as_posix(),
        "processed_csv": processed_csv.relative_to(root).as_posix(),
        "metadata": result_metadata.relative_to(root).as_posix(),
    }
    if correction_ref:
        outputs["correction_record"] = correction_ref
    if potential_conversion_ref:
        outputs["potential_conversion"] = potential_conversion_ref
    if ir_drop_correction_ref:
        outputs["ir_drop_correction"] = ir_drop_correction_ref
    if tafel_analysis_ref:
        outputs["tafel_analysis"] = tafel_analysis_ref
    if gcd_analysis_ref:
        outputs["gcd_analysis"] = gcd_analysis_ref
    if eis_circuit_fit_ref:
        outputs["eis_circuit_fit"] = eis_circuit_fit_ref
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
        outputs=outputs,
        peak_analysis=analysis,
        figure_id=figure_id,
        warnings=warnings,
        review_refs=[request.column_review_ref, request.context_review_ref, request.parameter_review_ref],
        created_at=created_at or EARecord.now_iso(),
        updated_at=created_at or EARecord.now_iso(),
    )
    write_yaml(result_metadata, result.model_dump(exclude_none=True))
    provenance_files = [
        processed_csv.relative_to(root).as_posix(),
        features_csv.relative_to(root).as_posix(),
        figure.relative_to(root).as_posix(),
    ]
    if correction_ref:
        provenance_files.append(correction_ref)
    if potential_conversion_ref:
        provenance_files.append(potential_conversion_ref)
    if ir_drop_correction_ref:
        provenance_files.append(ir_drop_correction_ref)
    if tafel_analysis_ref:
        provenance_files.append(tafel_analysis_ref)
    if gcd_analysis_ref:
        provenance_files.append(gcd_analysis_ref)
    if eis_circuit_fit_ref:
        provenance_files.append(eis_circuit_fit_ref)
    provenance_path = write_provenance_entry(
        root,
        workflow="electrochemistry_processing",
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
            "EIS Nyquist plot with screening impedance features, optional reviewed circuit-fit screening, reviewed context, and traceable processing parameters."
            if request.measurement_mode == "eis"
            else "Electrochemistry trace with processed current or reviewed GCD voltage, screening features, reviewed context, optional reviewed potential conversion/iR correction/Tafel/GCD records, and traceable processing parameters."
        )
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
                processed_csv.relative_to(root).as_posix(),
                features_csv.relative_to(root).as_posix(),
            ]
            + ([correction_ref] if correction_ref else [])
            + ([potential_conversion_ref] if potential_conversion_ref else [])
            + ([ir_drop_correction_ref] if ir_drop_correction_ref else [])
            + ([tafel_analysis_ref] if tafel_analysis_ref else [])
            + ([gcd_analysis_ref] if gcd_analysis_ref else [])
            + ([eis_circuit_fit_ref] if eis_circuit_fit_ref else []),
        )
    return result_metadata
