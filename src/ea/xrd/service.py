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
from ea.materials import infer_material_from_text, match_xrd_peaks
from ea.provenance import write_provenance_entry
from ea.raman.service import _read_spectrum
from ea.raw_import import assert_not_raw_output_path
from ea.review import require_confirmed_review
from ea.schema import XRDProcessingResult
from ea.schema.models import EARecord
from ea.standards import infer_project_slug
from ea.storage.files import read_yaml, write_yaml
from ea.storage.ids import next_id, next_standard_id


class XRDProcessingError(RuntimeError):
    """Raised when XRD processing would violate review or data boundaries."""


@dataclass(frozen=True)
class XRDInspection:
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
class XRDProcessingRequest:
    x_column: str
    y_column: str
    x_unit: str
    processing_parameters: dict[str, Any]
    column_review_ref: str
    parameter_review_ref: str


def default_xrd_processing_parameters() -> dict[str, Any]:
    return {
        "radiation": {
            "label": "Cu Kalpha",
            "wavelength_angstrom": 1.5406,
            "source": "default_requires_user_review",
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
        },
    }


def _merge_parameters(parameters: dict[str, Any] | None) -> dict[str, Any]:
    merged = default_xrd_processing_parameters()
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


def _coerce_float(value: Any, default: float, *, minimum: float | None = None) -> tuple[float, bool]:
    try:
        coerced = float(value)
    except (TypeError, ValueError):
        return default, True
    if minimum is not None and coerced < minimum:
        return default, True
    return coerced, False


def inspect_xrd_file(path: Path) -> XRDInspection:
    frame, metadata = _read_spectrum(path)
    columns = [str(column) for column in frame.columns]
    if frame.empty or len(columns) < 2:
        raise XRDProcessingError(f"No two-column numeric diffraction data found in {path}")

    x_values = pd.to_numeric(frame.iloc[:, 0], errors="coerce").dropna()
    x_min = float(x_values.min())
    x_max = float(x_values.max())
    axis_unit = str(metadata.get("AxisUnit[1]") or metadata.get("x_unit") or "").lower()
    axis_label = str(metadata.get("AxisLabel[1]") or metadata.get("x_label") or "").lower()
    filename_upper = path.name.upper()
    looks_like_two_theta = (
        "XRD" in filename_upper
        or "2THETA" in axis_label.replace(" ", "").upper()
        or "2θ" in axis_label
        or "theta" in axis_label
        or (3 <= x_min <= 90 and 10 <= x_max <= 180)
    )
    x_unit = "2theta_deg" if ("deg" in axis_unit or looks_like_two_theta) else "unknown"
    file_kind = "xrd" if looks_like_two_theta else "unknown"
    warnings: list[str] = []
    if file_kind == "xrd" and "deg" not in axis_unit:
        warnings.append("xrd_unit_inferred_from_range_or_filename")
    if file_kind == "unknown":
        warnings.append("xrd_file_kind_unknown")

    return XRDInspection(
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


def _confirmed_frame(path: Path, request: XRDProcessingRequest) -> pd.DataFrame:
    frame, _ = _read_spectrum(path)
    frame.columns = [str(column) for column in frame.columns]
    if request.x_column not in frame.columns or request.y_column not in frame.columns:
        raise XRDProcessingError("Confirmed x/y columns are not present in the raw file")
    if request.x_unit not in {"2theta_deg", "unknown"}:
        raise XRDProcessingError("XRD x_unit must be user-confirmed as 2theta_deg or unknown")
    data = frame[[request.x_column, request.y_column]].copy()
    data.columns = ["two_theta", "raw_intensity"]
    data["two_theta"] = pd.to_numeric(data["two_theta"], errors="coerce")
    data["raw_intensity"] = pd.to_numeric(data["raw_intensity"], errors="coerce")
    data = data.dropna().sort_values("two_theta").reset_index(drop=True)
    if data.empty:
        raise XRDProcessingError("Confirmed XRD columns contain no numeric data")
    return data


def _apply_processing(
    data: pd.DataFrame,
    parameters: dict[str, Any],
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    processed = data.copy()
    warnings: list[dict[str, Any]] = []
    intensity = processed["raw_intensity"].to_numpy(dtype=float)

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
        if adjusted:
            warnings.append(
                _warning(
                    "xrd_smoothing_parameter_adjusted",
                    "Invalid Savitzky-Golay parameters were adjusted for XRD processing.",
                    window_length=window_length,
                    polyorder=polyorder,
                )
            )
        if intensity.size >= 3 and window_length >= 3:
            intensity = np.asarray(savgol_filter(intensity, window_length=window_length, polyorder=polyorder, mode="interp"), dtype=float)
            processed["smoothed_intensity"] = intensity
            warnings.append(
                _warning(
                    "xrd_smoothing_applied",
                    "Savitzky-Golay smoothing was applied before XRD normalization and peak detection.",
                    method="savitzky_golay",
                    window_length=window_length,
                    polyorder=polyorder,
                )
            )
        else:
            warnings.append(_warning("xrd_smoothing_skipped", "XRD smoothing skipped because the pattern has fewer than three points.", severity="medium"))

    if parameters.get("normalization", {}).get("enabled", True):
        max_value = float(np.max(np.abs(intensity)))
        if max_value > 0:
            intensity = intensity / max_value
        warnings.append(_warning("xrd_normalization_applied", "XRD intensity normalized by processing parameters."))
    processed["processed_intensity"] = intensity
    return processed, warnings


def _wavelength(parameters: dict[str, Any]) -> tuple[float | None, list[dict[str, Any]]]:
    radiation = parameters.get("radiation", {})
    value = radiation.get("wavelength_angstrom")
    if value in {None, ""}:
        return None, [_warning("xrd_wavelength_missing", "No X-ray wavelength was provided; d-spacing was not calculated.", severity="medium")]
    wavelength, adjusted = _coerce_float(value, 1.5406, minimum=0.01)
    if adjusted:
        return wavelength, [_warning("xrd_wavelength_adjusted", "Invalid X-ray wavelength was replaced with a safe default.", wavelength_angstrom=wavelength)]
    return wavelength, []


def _add_d_spacing(processed: pd.DataFrame, x_unit: str, wavelength: float | None) -> None:
    if x_unit != "2theta_deg" or wavelength is None:
        return
    theta_radians = np.deg2rad(processed["two_theta"].to_numpy(dtype=float) / 2.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        d_spacing = wavelength / (2.0 * np.sin(theta_radians))
    processed["d_spacing_angstrom"] = np.where(np.isfinite(d_spacing), d_spacing, np.nan)


def _detect_peaks(processed: pd.DataFrame, parameters: dict[str, Any]) -> pd.DataFrame:
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
        row = processed.iloc[int(peak_index)]
        d_spacing = row.get("d_spacing_angstrom", np.nan)
        rows.append(
            {
                "peak_id": f"xrd-peak-{index:03d}",
                "two_theta_deg": float(row["two_theta"]),
                "d_spacing_angstrom": float(d_spacing) if pd.notna(d_spacing) else np.nan,
                "intensity": float(row["raw_intensity"]),
                "height": float(y[int(peak_index)]),
                "prominence": float(properties["prominences"][index - 1]),
                "method": "scipy_find_peaks",
                "possible_phase": "",
                "assignment_confidence": "",
                "assignment_feature": "",
                "assignment_source": "",
                "notes": "requires phase-reference review",
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "peak_id",
            "two_theta_deg",
            "d_spacing_angstrom",
            "intensity",
            "height",
            "prominence",
            "method",
            "possible_phase",
            "assignment_confidence",
            "assignment_feature",
            "assignment_source",
            "notes",
        ],
    )


def _analyze_xrd_peaks(peaks: pd.DataFrame, project_id: str) -> dict[str, Any]:
    for column in ["possible_phase", "assignment_confidence", "assignment_feature", "assignment_source"]:
        if column not in peaks.columns:
            peaks[column] = ""

    analysis: dict[str, Any] = {
        "peak_count": int(len(peaks)),
        "strongest_peaks": [],
        "possible_interpretations": [],
    }
    if peaks.empty:
        analysis["possible_interpretations"].append(
            {
                "text": "No stable XRD peak was detected by the current automatic settings.",
                "confidence": "insufficient",
                "evidence": [],
            }
        )
        return analysis

    strongest = peaks.sort_values("prominence", ascending=False).head(6)
    analysis["strongest_peaks"] = [
        {
            "peak_id": str(row["peak_id"]),
            "two_theta_deg": float(row["two_theta_deg"]),
            "d_spacing_angstrom": float(row["d_spacing_angstrom"]) if pd.notna(row["d_spacing_angstrom"]) else None,
        }
        for _, row in strongest.iterrows()
    ]

    material_id = infer_material_from_text(project_id)
    if not material_id:
        evidence = [str(strongest.iloc[0]["peak_id"])]
        text = "XRD peaks were detected, but no material-specific phase-assignment rule was applied for this project context."
        analysis["possible_interpretations"].append({"text": text, "confidence": "low", "evidence": evidence})
        return analysis

    material_analysis = match_xrd_peaks(material_id, peaks.to_dict("records"))
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


def _plot_xrd(processed: pd.DataFrame, peaks: pd.DataFrame, output: Path, *, footer: str | None = None) -> None:
    fig, ax = styled_subplots(figsize=(6.0, 4.0))
    ax.plot(processed["two_theta"], processed["processed_intensity"], color=NATURE_LIKE_COLORS["blue"], linewidth=1.2, label="Processed intensity")
    if not peaks.empty:
        ax.scatter(peaks["two_theta_deg"], peaks["height"], color=NATURE_LIKE_COLORS["black"], s=18, label="Detected peaks", zorder=3)
        for _, peak in peaks.sort_values("prominence", ascending=False).head(6).iterrows():
            ax.annotate(
                f"{float(peak['two_theta_deg']):.1f}",
                (float(peak["two_theta_deg"]), float(peak["height"])),
                textcoords="offset points",
                xytext=(0, 6),
                ha="center",
                fontsize=7,
            )
    style_axis(
        ax,
        title="XRD pattern",
        xlabel="2theta (deg)",
        ylabel="Intensity (a.u.)",
    )
    save_styled_figure(fig, output, footer=footer)


def process_xrd_result(
    root: Path,
    *,
    characterization_metadata_path: Path,
    project_id: str,
    sample_refs: list[str],
    request: XRDProcessingRequest,
    created_at: str | None = None,
) -> Path:
    metadata = read_yaml(characterization_metadata_path)
    require_confirmed_review(root, request.column_review_ref)
    require_confirmed_review(root, request.parameter_review_ref)
    raw_path = root / metadata["project_raw_path"]
    inspection = inspect_xrd_file(raw_path)
    if inspection.file_kind != "xrd":
        raise XRDProcessingError(f"File is {inspection.file_kind}, not XRD")

    parameters = _merge_parameters(request.processing_parameters)
    processed, processing_warnings = _apply_processing(_confirmed_frame(raw_path, request), parameters)
    wavelength, wavelength_warnings = _wavelength(parameters)
    _add_d_spacing(processed, request.x_unit, wavelength)
    peaks = _detect_peaks(processed, parameters)
    peak_analysis = _analyze_xrd_peaks(peaks, project_id)
    day = _created_day(created_at)
    project_slug = infer_project_slug(project_id)
    if _uses_v0_2_project_ids(project_id):
        result_id = next_standard_id(root, "result", project_slug, method="xrd", day=day)
        figure_id = next_standard_id(root, "figure", project_slug, method="xrd", day=day)
    else:
        result_id = next_id(root, "xrd_result", day)
        figure_id = None
    sample_dir = sample_refs[0] if sample_refs else "unmapped-sample"
    output_dir = root / "processed" / sample_dir / "xrd" / result_id
    processed_csv = output_dir / "xrd_processed.csv"
    peaks_csv = output_dir / "xrd_peaks.csv"
    figure_name = f"{figure_id}.png" if figure_id else "xrd_plot.png"
    figure = output_dir / figure_name
    result_metadata = output_dir / "xrd_metadata.yml"
    for output in [processed_csv, peaks_csv, figure, result_metadata]:
        assert_not_raw_output_path(root, output)

    output_dir.mkdir(parents=True, exist_ok=True)
    processed.to_csv(processed_csv, index=False)
    peaks.to_csv(peaks_csv, index=False)
    _plot_xrd(processed, peaks, figure, footer=figure_footer(figure_id, None) if figure_id else None)

    warnings: list[Any] = []
    if request.x_unit == "unknown":
        warnings.append(_warning("xrd_x_unit_unknown", "XRD x unit remains unknown after confirmation.", severity="medium"))
    warnings.extend(wavelength_warnings)
    warnings.extend(processing_warnings)
    result = XRDProcessingResult(
        xrd_result_id=result_id,
        result_id=result_id,
        project_id=project_id,
        characterization_file_ref=metadata["characterization_id"],
        sample_refs=sample_refs,
        status="warning" if warnings else "success",
        x_column=request.x_column,
        y_column=request.y_column,
        x_unit=request.x_unit,  # type: ignore[arg-type]
        wavelength_angstrom=wavelength,
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
        review_refs=[request.column_review_ref, request.parameter_review_ref],
        created_at=created_at or EARecord.now_iso(),
        updated_at=created_at or EARecord.now_iso(),
    )
    write_yaml(result_metadata, result.model_dump(exclude_none=True))
    provenance_path = write_provenance_entry(
        root,
        workflow="xrd_processing",
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
            "processing_parameters": parameters,
        },
        review_refs=[request.column_review_ref, request.parameter_review_ref],
        warnings=warnings,
        scripts=[{"path": "src/ea/xrd/service.py", "version": "0.2.0"}],
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
                "script": "src/ea/xrd/service.py",
                "parameters": {
                    "x_column": request.x_column,
                    "y_column": request.y_column,
                    "x_unit": request.x_unit,
                    "processing_parameters": parameters,
                },
            },
            caption="XRD pattern with detected peaks and traceable processing parameters.",
            purpose="xrd_analysis_report",
            style_profile=NATURE_LIKE_STYLE_PROFILE,
            source_data_refs=[
                str(processed_csv.relative_to(root)),
                str(peaks_csv.relative_to(root)),
            ],
        )
    return result_metadata
