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


def _analyze_features(features: pd.DataFrame, edge: dict[str, Any] | None) -> dict[str, Any]:
    analysis: dict[str, Any] = {
        "feature_count": int(len(features)),
        "strongest_features": [],
        "edge_estimate": edge,
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
    return analysis


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
    feature_analysis = _analyze_features(features, edge)
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
    figure_name = f"{figure_id}.png" if figure_id else "uv_vis_plot.png"
    figure = output_dir / figure_name
    result_metadata = output_dir / "uv_vis_metadata.yml"
    for output in [processed_csv, features_csv, figure, result_metadata]:
        assert_not_raw_output_path(root, output)

    output_dir.mkdir(parents=True, exist_ok=True)
    processed.to_csv(processed_csv, index=False)
    features.to_csv(features_csv, index=False)
    _plot_uv_vis(processed, features, figure, request.x_unit, request.signal_mode, footer=figure_footer(figure_id, None) if figure_id else None)

    warnings: list[Any] = []
    if request.x_unit == "unknown":
        warnings.append(_warning("uv_vis_x_unit_unknown", "UV-Vis x unit remains unknown after confirmation.", severity="medium"))
    warnings.extend(processing_warnings)
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
        outputs={
            "figure": str(figure.relative_to(root)),
            "peak_table": str(features_csv.relative_to(root)),
            "processed_csv": str(processed_csv.relative_to(root)),
            "metadata": str(result_metadata.relative_to(root)),
        },
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
            ],
        )
    return result_metadata
