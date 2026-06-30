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
    if "tga" in text or "tg " in f" {text} " or "thermograv" in text or "mass" in text or "weight" in text:
        return "tga"
    return "unknown"


def _temperature_unit_candidate(text: str, x_min: float, x_max: float) -> str:
    if "temperature_k" in text or " kelvin" in text or " k " in f" {text} ":
        return "K"
    if "temperature_c" in text or "degc" in text or " c " in f" {text} " or "celsius" in text:
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
        raise ThermalAnalysisProcessingError(f"No two-column numeric thermal data found in {path}")
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
    looks_like_thermal = mode != "unknown" or "thermal" in text or ("temperature" in text and ("mass" in text or "heat" in text))
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
        metadata={**metadata, "x_min": x_min, "x_max": x_max, "y_min": y_min, "y_max": y_max},
        warnings=warnings,
        requires_user_confirmation=True,
    )


def _confirmed_frame(path: Path, request: ThermalAnalysisProcessingRequest) -> pd.DataFrame:
    frame, _ = _read_spectrum(path)
    frame.columns = [str(column) for column in frame.columns]
    if request.temperature_column not in frame.columns or request.signal_column not in frame.columns:
        raise ThermalAnalysisProcessingError("Confirmed temperature/signal columns are not present in the raw file")
    if request.temperature_unit not in {"C", "K", "unknown"}:
        raise ThermalAnalysisProcessingError("Thermal temperature_unit must be user-confirmed as C, K, or unknown")
    if request.signal_unit not in {"%", "mg", "mW", "W/g", "mW/mg", "unknown"}:
        raise ThermalAnalysisProcessingError("Thermal signal_unit must be %, mg, mW, W/g, mW/mg, or unknown")
    if request.measurement_mode not in {"tga", "dsc", "dtg", "unknown"}:
        raise ThermalAnalysisProcessingError("Thermal measurement_mode must be tga, dsc, dtg, or unknown")
    data = frame[[request.temperature_column, request.signal_column]].copy()
    data.columns = ["temperature_raw", "signal_raw"]
    data["temperature_raw"] = pd.to_numeric(data["temperature_raw"], errors="coerce")
    data["signal_raw"] = pd.to_numeric(data["signal_raw"], errors="coerce")
    data = data.dropna().reset_index(drop=True)
    if data.empty:
        raise ThermalAnalysisProcessingError("Confirmed thermal columns contain no numeric data")
    if request.temperature_unit == "K":
        data["temperature_C"] = data["temperature_raw"] - 273.15
    else:
        data["temperature_C"] = data["temperature_raw"]
    return data


def _apply_processing(data: pd.DataFrame, request: ThermalAnalysisProcessingRequest, parameters: dict[str, Any]) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    processed = data.copy()
    warnings: list[dict[str, Any]] = []
    signal = processed["signal_raw"].to_numpy(dtype=float)
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
        if signal.size >= 3 and window_length >= 3:
            signal = np.asarray(savgol_filter(signal, window_length=window_length, polyorder=polyorder, mode="interp"), dtype=float)
            warnings.append(_warning("thermal_smoothing_applied", "Savitzky-Golay smoothing was applied before thermal feature detection.", window_length=window_length, polyorder=polyorder))
        if adjusted:
            warnings.append(_warning("thermal_smoothing_parameter_adjusted", "Invalid Savitzky-Golay parameters were adjusted for thermal processing.", severity="medium", window_length=window_length, polyorder=polyorder))
    processed["processed_signal"] = signal
    if request.measurement_mode == "tga" or (request.measurement_mode == "unknown" and request.signal_unit in {"%", "mg"}):
        if request.signal_unit == "%":
            mass_percent = signal
        elif request.signal_unit == "mg" and abs(float(signal[0])) > 1e-12:
            mass_percent = signal / float(signal[0]) * 100.0
        else:
            mass_percent = signal
        processed["processed_mass_percent"] = mass_percent
        if parameters.get("derivative", {}).get("enabled", True) and len(processed) >= 3:
            temperature = processed["temperature_C"].to_numpy(dtype=float)
            processed["mass_derivative_percent_per_C"] = np.gradient(mass_percent, temperature)
    elif request.measurement_mode == "dtg":
        processed["processed_dtg_signal"] = signal
    else:
        processed["processed_heat_flow"] = signal
    return processed, warnings


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
        "mass_derivative_percent_per_C": _as_float(row.get("mass_derivative_percent_per_C")),
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


def _detect_features(processed: pd.DataFrame, parameters: dict[str, Any], request: ThermalAnalysisProcessingRequest) -> pd.DataFrame:
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
        indices, props = find_peaks(-derivative, prominence=prominence, distance=distance)
        ranked.extend((int(index), float(props["prominences"][offset]), "mass_loss_rate_peak", "mass_derivative_percent_per_C") for offset, index in enumerate(indices))
    elif "processed_heat_flow" in processed.columns:
        heat_flow = processed["processed_heat_flow"].to_numpy(dtype=float)
        prominence = feature_params.get("prominence", "auto")
        if prominence == "auto":
            prominence = _auto_prominence(heat_flow)
        positive, positive_props = find_peaks(heat_flow, prominence=prominence, distance=distance)
        negative, negative_props = find_peaks(-heat_flow, prominence=prominence, distance=distance)
        ranked.extend((int(index), float(positive_props["prominences"][offset]), "heat_flow_positive_peak", "processed_heat_flow") for offset, index in enumerate(positive))
        ranked.extend((int(index), float(negative_props["prominences"][offset]), "heat_flow_negative_peak", "processed_heat_flow") for offset, index in enumerate(negative))
    elif "processed_dtg_signal" in processed.columns:
        dtg = processed["processed_dtg_signal"].to_numpy(dtype=float)
        prominence = feature_params.get("prominence", "auto")
        if prominence == "auto":
            prominence = _auto_prominence(dtg)
        positive, positive_props = find_peaks(dtg, prominence=prominence, distance=distance)
        negative, negative_props = find_peaks(-dtg, prominence=prominence, distance=distance)
        ranked.extend((int(index), float(positive_props["prominences"][offset]), "dtg_positive_peak", "processed_dtg_signal") for offset, index in enumerate(positive))
        ranked.extend((int(index), float(negative_props["prominences"][offset]), "dtg_negative_peak", "processed_dtg_signal") for offset, index in enumerate(negative))

    ranked = sorted(ranked, key=lambda item: item[1], reverse=True)[:max_features]
    ranked.sort(key=lambda item: float(processed.iloc[item[0]]["temperature_C"]))
    for number, (index, prominence, event_type, column) in enumerate(ranked, start=1):
        rows.append(_feature_row(f"thermal-event-{number:03d}", event_type, processed.iloc[index], value_column=column, prominence=prominence, source=source, method="scipy_find_peaks"))

    threshold_params = parameters.get("threshold_summary", {})
    if threshold_params.get("enabled", True) and "processed_mass_percent" in processed.columns:
        mass = processed["processed_mass_percent"].to_numpy(dtype=float)
        start = float(mass[0])
        threshold_source = str(threshold_params.get("source") or "ea.thermal.threshold_summary:v0.2")
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


def _summary(processed: pd.DataFrame, features: pd.DataFrame, request: ThermalAnalysisProcessingRequest) -> dict[str, Any]:
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
    return analysis


def _created_day(created_at: str | None) -> str | None:
    return created_at[:10] if created_at else None


def _uses_v0_2_project_ids(project_id: str) -> bool:
    return project_id.startswith("prj-")


def _plot_thermal(processed: pd.DataFrame, features: pd.DataFrame, output: Path, request: ThermalAnalysisProcessingRequest, *, footer: str | None = None) -> None:
    fig, ax = styled_subplots(figsize=(6.0, 4.0))
    x = processed["temperature_C"]
    if "processed_mass_percent" in processed.columns:
        y_column = "processed_mass_percent"
        ylabel = "Mass (%)"
        title = "Thermal TGA trace"
        feature_y = "mass_percent"
    elif "processed_heat_flow" in processed.columns:
        y_column = "processed_heat_flow"
        ylabel = f"Heat flow ({request.signal_unit})" if request.signal_unit != "unknown" else "Heat flow"
        title = "Thermal DSC trace"
        feature_y = "heat_flow"
    else:
        y_column = "processed_dtg_signal"
        ylabel = f"DTG signal ({request.signal_unit})" if request.signal_unit != "unknown" else "DTG signal"
        title = "Thermal DTG trace"
        feature_y = "dtg_signal"
    ax.plot(x, processed[y_column], color=NATURE_LIKE_COLORS["blue"], linewidth=1.2, label="Processed signal")
    if not features.empty:
        feature_values = features[feature_y] if feature_y in features.columns else features["signal_value"]
        usable = features[pd.notna(feature_values)]
        if not usable.empty:
            ax.scatter(usable["temperature_C"], usable[feature_y], color=NATURE_LIKE_COLORS["black"], s=18, label="Detected events", zorder=3)
            for _, event in usable.head(8).iterrows():
                ax.annotate(
                    str(event["event_id"]).replace("thermal-", ""),
                    (float(event["temperature_C"]), float(event[feature_y])),
                    textcoords="offset points",
                    xytext=(0, 6),
                    ha="center",
                    fontsize=7,
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
        raise ThermalAnalysisProcessingError(f"File is {inspection.file_kind}, not thermal_analysis")

    parameters = _merge_parameters(request.processing_parameters)
    processed, processing_warnings = _apply_processing(_confirmed_frame(raw_path, request), request, parameters)
    features = _detect_features(processed, parameters, request)
    analysis = _summary(processed, features, request)
    day = _created_day(created_at)
    project_slug = infer_project_slug(project_id)
    if _uses_v0_2_project_ids(project_id):
        result_id = next_standard_id(root, "result", project_slug, method="thermal_analysis", day=day)
        figure_id = next_standard_id(root, "figure", project_slug, method="thermal_analysis", day=day)
    else:
        result_id = next_id(root, "thermal_result", day)
        figure_id = None
    sample_dir = sample_refs[0] if sample_refs else "unmapped-sample"
    output_dir = root / "processed" / sample_dir / "thermal_analysis" / result_id
    processed_csv = output_dir / "thermal_processed.csv"
    features_csv = output_dir / "thermal_features.csv"
    figure_name = f"{figure_id}.png" if figure_id else "thermal_plot.png"
    figure = output_dir / figure_name
    result_metadata = output_dir / "thermal_metadata.yml"
    for output in [processed_csv, features_csv, figure, result_metadata]:
        assert_not_raw_output_path(root, output)

    output_dir.mkdir(parents=True, exist_ok=True)
    processed.to_csv(processed_csv, index=False)
    features.to_csv(features_csv, index=False)
    _plot_thermal(processed, features, figure, request, footer=figure_footer(figure_id, None) if figure_id else None)

    warnings: list[Any] = []
    if request.temperature_unit == "unknown":
        warnings.append(_warning("thermal_temperature_unit_unknown", "Thermal temperature unit remains unknown after confirmation.", severity="medium"))
    if request.signal_unit == "unknown":
        warnings.append(_warning("thermal_signal_unit_unknown", "Thermal signal unit remains unknown after confirmation.", severity="medium"))
    if not request.context_summary:
        warnings.append(_warning("thermal_context_missing", "Thermal temperature-program/sample/atmosphere context summary is empty.", severity="medium"))
    warnings.extend(processing_warnings)
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
        workflow="thermal_analysis_processing",
        inputs={
            "records": [str(characterization_metadata_path.relative_to(root))],
            "files": [metadata["project_raw_path"]],
        },
        outputs={
            "records": [str(result_metadata.relative_to(root))],
            "files": [str(processed_csv.relative_to(root)), str(features_csv.relative_to(root)), str(figure.relative_to(root))],
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
        review_refs=[request.column_review_ref, request.context_review_ref, request.parameter_review_ref],
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
            path=str(figure.relative_to(root)),
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
            source_data_refs=[str(processed_csv.relative_to(root)), str(features_csv.relative_to(root))],
        )
    return result_metadata
