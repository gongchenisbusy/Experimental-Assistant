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


def _analyze_peaks(peaks: pd.DataFrame, request: XPSProcessingRequest) -> dict[str, Any]:
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
    return analysis


def _created_day(created_at: str | None) -> str | None:
    return created_at[:10] if created_at else None


def _uses_v0_2_project_ids(project_id: str) -> bool:
    return project_id.startswith("prj-")


def _plot_xps(processed: pd.DataFrame, peaks: pd.DataFrame, output: Path, *, footer: str | None = None) -> None:
    fig, ax = styled_subplots(figsize=(6.0, 4.0))
    ax.plot(processed["binding_energy_eV"], processed["processed_intensity"], color=NATURE_LIKE_COLORS["blue"], linewidth=1.2, label="Processed intensity")
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
    peaks = _detect_peaks(processed, parameters, request.x_unit)
    peak_analysis = _analyze_peaks(peaks, request)
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
    figure_name = f"{figure_id}.png" if figure_id else "xps_plot.png"
    figure = output_dir / figure_name
    result_metadata = output_dir / "xps_metadata.yml"
    for output in [processed_csv, peaks_csv, figure, result_metadata]:
        assert_not_raw_output_path(root, output)

    output_dir.mkdir(parents=True, exist_ok=True)
    processed.to_csv(processed_csv, index=False)
    peaks.to_csv(peaks_csv, index=False)
    _plot_xps(processed, peaks, figure, footer=figure_footer(figure_id, None) if figure_id else None)

    warnings: list[Any] = []
    if request.x_unit == "unknown":
        warnings.append(_warning("xps_x_unit_unknown", "XPS x unit remains unknown after confirmation.", severity="medium"))
    if not request.calibration_reference:
        warnings.append(_warning("xps_calibration_reference_missing", "No XPS calibration reference text was recorded.", severity="medium"))
    warnings.extend(processing_warnings)
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
        outputs={
            "figure": str(figure.relative_to(root)),
            "peak_table": str(peaks_csv.relative_to(root)),
            "processed_csv": str(processed_csv.relative_to(root)),
            "metadata": str(result_metadata.relative_to(root)),
        },
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
                str(processed_csv.relative_to(root)),
                str(peaks_csv.relative_to(root)),
                str(figure.relative_to(root)),
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
            caption="XPS spectrum with processed intensity, detected screening peaks, and traceable calibration/processing parameters.",
            purpose="xps_analysis_report",
            style_profile=NATURE_LIKE_STYLE_PROFILE,
            source_data_refs=[
                str(processed_csv.relative_to(root)),
                str(peaks_csv.relative_to(root)),
            ],
        )
    return result_metadata
