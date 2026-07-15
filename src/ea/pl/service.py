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
from ea.materials import infer_material_from_project, match_pl_peaks
from ea.provenance import write_provenance_entry
from ea.report_messages import ensure_interpretation_message_contract
from ea.raman import SpectrumInspection, inspect_spectrum_file
from ea.raman.service import _read_spectrum
from ea.raw_import import assert_not_raw_output_path
from ea.review import require_confirmed_review
from ea.schema import PLProcessingResult
from ea.schema.models import EARecord
from ea.standards import infer_project_slug
from ea.storage.files import read_yaml, write_yaml
from ea.storage.ids import next_id, next_standard_id


class PLProcessingError(RuntimeError):
    """Raised when PL processing would violate review or data boundaries."""


@dataclass(frozen=True)
class PLProcessingRequest:
    x_column: str
    y_column: str
    x_unit: str
    processing_parameters: dict[str, Any]
    column_review_ref: str
    parameter_review_ref: str


def default_pl_processing_parameters() -> dict[str, Any]:
    return {
        "smoothing": {
            "enabled": False,
            "method": "savitzky_golay",
            "window_length": 11,
            "polyorder": 2,
        },
        "normalization": {"enabled": True, "method": "max_intensity"},
        "peak_detection": {
            "method": "scipy_find_peaks",
            "prominence": "auto",
            "distance": "auto",
        },
    }


def inspect_pl_file(path: Path) -> SpectrumInspection:
    return inspect_spectrum_file(path)


def _merge_parameters(parameters: dict[str, Any] | None) -> dict[str, Any]:
    merged = default_pl_processing_parameters()
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


def _confirmed_frame(path: Path, request: PLProcessingRequest) -> pd.DataFrame:
    frame, _ = _read_spectrum(path)
    frame.columns = [str(column) for column in frame.columns]
    if request.x_column not in frame.columns or request.y_column not in frame.columns:
        raise PLProcessingError("Confirmed x/y columns are not present in the raw file")
    if request.x_unit not in {"eV", "nm", "unknown"}:
        raise PLProcessingError(
            "PL x_unit must be user-confirmed as eV, nm, or unknown"
        )
    data = frame[[request.x_column, request.y_column]].copy()
    data.columns = ["pl_axis", "raw_intensity"]
    data["pl_axis"] = pd.to_numeric(data["pl_axis"], errors="coerce")
    data["raw_intensity"] = pd.to_numeric(data["raw_intensity"], errors="coerce")
    data = data.dropna().sort_values("pl_axis").reset_index(drop=True)
    if data.empty:
        raise PLProcessingError("Confirmed PL columns contain no numeric data")
    if request.x_unit == "eV":
        with np.errstate(divide="ignore", invalid="ignore"):
            data["wavelength_nm"] = 1239.841984 / data["pl_axis"].to_numpy(dtype=float)
    elif request.x_unit == "nm":
        data["wavelength_nm"] = data["pl_axis"]
    return data


def _apply_processing(
    data: pd.DataFrame, parameters: dict[str, Any]
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    processed = data.copy()
    warnings: list[dict[str, Any]] = []
    intensity = processed["raw_intensity"].to_numpy(dtype=float)

    smoothing = parameters.get("smoothing", {})
    if smoothing.get("enabled", False):
        window_length, window_adjusted = _coerce_int(
            smoothing.get("window_length"), 11, minimum=3
        )
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
        if adjusted:
            warnings.append(
                _warning(
                    "pl_smoothing_parameter_adjusted",
                    "Invalid Savitzky-Golay parameters were adjusted for PL processing.",
                    window_length=window_length,
                    polyorder=polyorder,
                )
            )
        if intensity.size >= 3:
            intensity = np.asarray(
                savgol_filter(
                    intensity,
                    window_length=window_length,
                    polyorder=polyorder,
                    mode="interp",
                ),
                dtype=float,
            )
            processed["smoothed_intensity"] = intensity
            warnings.append(
                _warning(
                    "pl_smoothing_applied",
                    "Savitzky-Golay smoothing was applied before PL normalization and peak detection.",
                    method="savitzky_golay",
                    window_length=window_length,
                    polyorder=polyorder,
                )
            )
        else:
            warnings.append(
                _warning(
                    "pl_smoothing_skipped",
                    "PL smoothing skipped because the spectrum has fewer than three points.",
                    severity="medium",
                )
            )

    if parameters.get("normalization", {}).get("enabled", True):
        max_value = float(np.max(np.abs(intensity)))
        if max_value > 0:
            intensity = intensity / max_value
        warnings.append(
            _warning(
                "pl_normalization_applied",
                "PL intensity normalized by processing parameters.",
            )
        )
    processed["processed_intensity"] = intensity
    return processed, warnings


def _detect_peaks(
    processed: pd.DataFrame, parameters: dict[str, Any], x_unit: str
) -> pd.DataFrame:
    y = processed["processed_intensity"].to_numpy(dtype=float)
    peak_params = parameters.get("peak_detection", {})
    prominence = peak_params.get("prominence", "auto")
    distance = peak_params.get("distance", "auto")
    if prominence == "auto":
        prominence = max(float(np.ptp(y)) * 0.08, 0.02)
    if distance == "auto":
        distance = max(len(y) // 80, 1)
    peaks, properties = find_peaks(y, prominence=prominence, distance=distance)
    rows = []
    for index, peak_index in enumerate(peaks, start=1):
        axis_value = float(processed.iloc[int(peak_index)]["pl_axis"])
        wavelength = processed.iloc[int(peak_index)].get("wavelength_nm", np.nan)
        rows.append(
            {
                "peak_id": f"pl-peak-{index:03d}",
                "position": axis_value,
                "position_unit": x_unit,
                "position_eV": axis_value if x_unit == "eV" else np.nan,
                "wavelength_nm": float(wavelength) if pd.notna(wavelength) else np.nan,
                "intensity": float(processed.iloc[int(peak_index)]["raw_intensity"]),
                "height": float(y[int(peak_index)]),
                "prominence": float(properties["prominences"][index - 1]),
                "method": "scipy_find_peaks",
                "assignment": "",
                "assignment_confidence": "",
                "assignment_feature": "",
                "assignment_source": "",
                "notes": "requires scientific review",
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "peak_id",
            "position",
            "position_unit",
            "position_eV",
            "wavelength_nm",
            "intensity",
            "height",
            "prominence",
            "method",
            "assignment",
            "assignment_confidence",
            "assignment_feature",
            "assignment_source",
            "notes",
        ],
    )


def _analyze_pl_peaks(
    peaks: pd.DataFrame, root: Path, project_id: str, x_unit: str
) -> dict[str, Any]:
    for column in [
        "assignment",
        "assignment_confidence",
        "assignment_feature",
        "assignment_source",
    ]:
        if column not in peaks.columns:
            peaks[column] = ""

    analysis: dict[str, Any] = {
        "peak_count": int(len(peaks)),
        "dominant_peak": None,
        "possible_interpretations": [],
    }
    if peaks.empty:
        analysis["possible_interpretations"].append(
            {
                "text": "No stable PL peak was detected by the current automatic settings.",
                "confidence": "insufficient",
                "evidence": [],
            }
        )
        return analysis

    dominant = peaks.sort_values("prominence", ascending=False).iloc[0]
    dominant_peak = {
        "peak_id": str(dominant["peak_id"]),
        "position": float(dominant["position"]),
        "position_unit": str(dominant["position_unit"]),
        "position_eV": float(dominant["position_eV"])
        if pd.notna(dominant["position_eV"])
        else None,
        "wavelength_nm": float(dominant["wavelength_nm"])
        if pd.notna(dominant["wavelength_nm"])
        else None,
    }
    analysis["dominant_peak"] = dominant_peak

    material_id = infer_material_from_project(root, project_id)
    if not material_id:
        text = "A dominant PL feature was detected, but no material-specific PL assignment rule was applied for this project context."
        analysis["possible_interpretations"].append(
            {
                "text": text,
                "confidence": "low",
                "evidence": [dominant_peak["peak_id"]],
                "dominant_peak": dominant_peak,
            }
        )
        return analysis

    material_analysis = match_pl_peaks(
        material_id, peaks.to_dict("records"), x_unit=x_unit
    )
    for update in material_analysis.pop("peak_updates", []):
        mask = peaks["peak_id"].astype(str) == str(update["peak_id"])
        for key, value in update.items():
            if key != "peak_id":
                peaks.loc[mask, key] = value
    return material_analysis


def _created_day(created_at: str | None) -> str | None:
    return created_at[:10] if created_at else None


def _uses_v0_2_project_ids(project_id: str) -> bool:
    return project_id.startswith("prj-")


def _plot_pl(
    processed: pd.DataFrame,
    peaks: pd.DataFrame,
    output: Path,
    x_unit: str,
    *,
    footer: str | None = None,
) -> None:
    fig, ax = styled_subplots(figsize=(6.0, 4.0))
    ax.plot(
        processed["pl_axis"],
        processed["raw_intensity"],
        color=NATURE_LIKE_COLORS["blue"],
        linewidth=1.0,
        alpha=0.5,
        label="Raw intensity",
    )
    ax.plot(
        processed["pl_axis"],
        processed["processed_intensity"],
        color=NATURE_LIKE_COLORS["orange"],
        linewidth=1.2,
        label="Processed intensity",
    )
    if not peaks.empty:
        ax.scatter(
            peaks["position"],
            peaks["height"],
            color=NATURE_LIKE_COLORS["black"],
            s=18,
            label="Detected peaks",
            zorder=3,
        )
    style_axis(
        ax,
        title="PL spectrum",
        xlabel=f"Emission energy ({x_unit})"
        if x_unit != "unknown"
        else "PL axis (unknown unit)",
        ylabel="Intensity (a.u.)",
    )
    save_styled_figure(fig, output, footer=footer)


def process_pl_result(
    root: Path,
    *,
    characterization_metadata_path: Path,
    project_id: str,
    sample_refs: list[str],
    request: PLProcessingRequest,
    created_at: str | None = None,
) -> Path:
    metadata = read_yaml(characterization_metadata_path)
    require_confirmed_review(root, request.column_review_ref)
    require_confirmed_review(root, request.parameter_review_ref)
    raw_path = root / metadata["project_raw_path"]
    inspection = inspect_pl_file(raw_path)
    if inspection.file_kind != "pl":
        raise PLProcessingError(f"File is {inspection.file_kind}, not PL")

    parameters = _merge_parameters(request.processing_parameters)
    processed, processing_warnings = _apply_processing(
        _confirmed_frame(raw_path, request), parameters
    )
    peaks = _detect_peaks(processed, parameters, request.x_unit)
    peak_analysis = ensure_interpretation_message_contract(
        _analyze_pl_peaks(peaks, root, project_id, request.x_unit), "pl"
    )
    day = _created_day(created_at)
    project_slug = infer_project_slug(project_id)
    if _uses_v0_2_project_ids(project_id):
        result_id = next_standard_id(root, "result", project_slug, method="pl", day=day)
        figure_id = next_standard_id(root, "figure", project_slug, method="pl", day=day)
    else:
        result_id = next_id(root, "pl_result", day)
        figure_id = None
    sample_dir = sample_refs[0] if sample_refs else "unmapped-sample"
    output_dir = root / "processed" / sample_dir / "pl" / result_id
    processed_csv = output_dir / "pl_processed.csv"
    peaks_csv = output_dir / "pl_peaks.csv"
    figure_name = f"{figure_id}.png" if figure_id else "pl_plot.png"
    figure = output_dir / figure_name
    result_metadata = output_dir / "pl_metadata.yml"
    for output in [processed_csv, peaks_csv, figure, result_metadata]:
        assert_not_raw_output_path(root, output)

    output_dir.mkdir(parents=True, exist_ok=True)
    processed.to_csv(processed_csv, index=False)
    peaks.to_csv(peaks_csv, index=False)
    _plot_pl(
        processed,
        peaks,
        figure,
        request.x_unit,
        footer=figure_footer(figure_id, None) if figure_id else None,
    )

    warnings: list[Any] = []
    if request.x_unit == "unknown":
        warnings.append(
            _warning(
                "pl_x_unit_unknown",
                "PL x unit remains unknown after confirmation.",
                severity="medium",
            )
        )
    warnings.extend(processing_warnings)
    result = PLProcessingResult(
        pl_result_id=result_id,
        result_id=result_id,
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
        warnings=warnings,
        review_refs=[request.column_review_ref, request.parameter_review_ref],
        created_at=created_at or EARecord.now_iso(),
        updated_at=created_at or EARecord.now_iso(),
    )
    write_yaml(result_metadata, result.model_dump(exclude_none=True))
    provenance_path = write_provenance_entry(
        root,
        workflow="pl_processing",
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
        scripts=[{"path": "src/ea/pl/service.py", "version": "0.2.0"}],
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
                "script": "src/ea/pl/service.py",
                "parameters": {
                    "x_column": request.x_column,
                    "y_column": request.y_column,
                    "x_unit": request.x_unit,
                    "processing_parameters": parameters,
                },
            },
            caption="PL spectrum with processed intensity and detected peaks.",
            purpose="pl_analysis_report",
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
                    purpose="Processed PL trace plotted in the spectrum figure.",
                    primary=True,
                ),
                source_data_entry(
                    root,
                    peaks_csv.relative_to(root).as_posix(),
                    role="peak_table",
                    purpose="Detected PL peak annotations.",
                ),
            ],
        )
    return result_metadata
