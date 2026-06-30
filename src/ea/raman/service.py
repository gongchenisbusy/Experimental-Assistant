from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.signal import find_peaks, peak_widths

from ea.figures import figure_footer, register_figure
from ea.provenance import write_provenance_entry
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
        "baseline_correction": {"enabled": False},
        "smoothing": {"enabled": False},
        "normalization": {"enabled": True, "method": "max_intensity"},
        "peak_detection": {
            "method": "scipy_find_peaks",
            "prominence": "auto",
            "distance": "auto",
        },
    }


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
        raise RamanProcessingError(f"No two-column numeric spectrum data found in {path}")

    x_values = pd.to_numeric(frame.iloc[:, 0], errors="coerce").dropna()
    x_min = float(x_values.min())
    x_max = float(x_values.max())
    axis_unit = (metadata.get("AxisUnit[1]") or metadata.get("x_unit") or "").lower()
    filename_upper = path.name.upper()

    if "PL" in filename_upper or axis_unit == "ev" or (0.5 <= x_min <= 5 and 0.5 <= x_max <= 5):
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
        raise RamanProcessingError("Confirmed x/y columns are not present in the raw file")
    if request.x_unit not in {"cm^-1", "unknown"}:
        raise RamanProcessingError("Raman x_unit must be user-confirmed as cm^-1 or unknown")
    data = frame[[request.x_column, request.y_column]].copy()
    data.columns = ["raman_shift", "raw_intensity"]
    data["raman_shift"] = pd.to_numeric(data["raman_shift"], errors="coerce")
    data["raw_intensity"] = pd.to_numeric(data["raw_intensity"], errors="coerce")
    data = data.dropna().sort_values("raman_shift").reset_index(drop=True)
    if data.empty:
        raise RamanProcessingError("Confirmed Raman columns contain no numeric data")
    return data


def _apply_processing(data: pd.DataFrame, parameters: dict[str, Any]) -> pd.DataFrame:
    processed = data.copy()
    intensity = processed["raw_intensity"].to_numpy(dtype=float)
    if parameters.get("normalization", {}).get("enabled", True):
        max_value = float(np.max(np.abs(intensity)))
        if max_value > 0:
            intensity = intensity / max_value
    processed["processed_intensity"] = intensity
    return processed


def _detect_peaks(processed: pd.DataFrame, parameters: dict[str, Any]) -> pd.DataFrame:
    y = processed["processed_intensity"].to_numpy(dtype=float)
    peak_params = parameters.get("peak_detection", {})
    prominence = peak_params.get("prominence", "auto")
    distance = peak_params.get("distance", "auto")
    if prominence == "auto":
        prominence = max(float(np.ptp(y)) * 0.08, 0.02)
    if distance == "auto":
        distance = max(len(y) // 40, 1)
    peaks, properties = find_peaks(y, prominence=prominence, distance=distance)
    widths = peak_widths(y, peaks, rel_height=0.5)[0] if len(peaks) else []
    rows = []
    for index, peak_index in enumerate(peaks, start=1):
        rows.append(
            {
                "peak_id": f"peak-{index:03d}",
                "position_cm-1": processed.iloc[int(peak_index)]["raman_shift"],
                "intensity": processed.iloc[int(peak_index)]["raw_intensity"],
                "height": y[int(peak_index)],
                "prominence": properties["prominences"][index - 1],
                "width": widths[index - 1] if len(widths) else np.nan,
                "method": "scipy_find_peaks",
                "notes": "requires scientific review",
            }
        )
    return pd.DataFrame(rows)


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
) -> None:
    fig, ax = plt.subplots(figsize=(6.0, 4.0))
    ax.plot(
        processed["raman_shift"],
        processed["raw_intensity"],
        color="#0072B2",
        linewidth=1.0,
        alpha=0.55,
        label="Raw intensity",
    )
    ax.plot(
        processed["raman_shift"],
        processed["processed_intensity"],
        color="#D55E00",
        linewidth=1.2,
        label="Processed intensity",
    )
    if not peaks.empty:
        ax.scatter(
            peaks["position_cm-1"],
            peaks["height"],
            color="#000000",
            s=18,
            label="Detected peaks",
            zorder=3,
        )
    unit_label = "cm$^{-1}$" if x_unit == "cm^-1" else "unknown unit"
    ax.set_title("Raman spectrum")
    ax.set_xlabel(f"Raman shift ({unit_label})")
    ax.set_ylabel("Intensity (a.u.)")
    ax.legend(frameon=False)
    ax.grid(True, alpha=0.2)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if footer:
        fig.text(0.99, 0.01, footer, ha="right", va="bottom", fontsize=5.5, color="#888888")
        fig.tight_layout(rect=(0, 0.045, 1, 1))
    else:
        fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=300, bbox_inches="tight")
    plt.close(fig)


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

    parameters = request.processing_parameters or default_processing_parameters()
    processed = _apply_processing(_confirmed_frame(raw_path, request), parameters)
    peaks = _detect_peaks(processed, parameters)
    day = _created_day(created_at)
    project_slug = infer_project_slug(project_id)
    if _uses_v0_2_project_ids(project_id):
        result_id = next_standard_id(root, "result", project_slug, method="raman", day=day)
        figure_id = next_standard_id(root, "figure", project_slug, method="raman", day=day)
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
    )

    warnings: list[Any] = []
    if request.x_unit == "unknown":
        warnings.append({"code": "x_unit_unknown", "message": "Raman x unit remains unknown after confirmation.", "severity": "medium"})
    if parameters.get("normalization", {}).get("enabled", False):
        warnings.append({"code": "normalization_applied", "message": "Intensity normalized by processing parameters.", "severity": "low"})
    if not parameters.get("baseline_correction", {}).get("enabled", False):
        warnings.append({"code": "baseline_not_corrected", "message": "No baseline correction was applied.", "severity": "low"})

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
            "figure": str(figure.relative_to(root)),
            "peak_table": str(peaks_csv.relative_to(root)),
            "processed_csv": str(processed_csv.relative_to(root)),
            "metadata": str(result_metadata.relative_to(root)),
        },
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
            path=str(figure.relative_to(root)),
            report_id=None,
            result_id=result_id,
            raw_data_ids=[metadata["characterization_id"]],
            sample_ids=sample_refs,
            experiment_ids=metadata.get("experiment_refs", []),
            generation={
                "script": "src/ea/raman/service.py",
                "parameters": {
                    "x_column": request.x_column,
                    "y_column": request.y_column,
                    "x_unit": request.x_unit,
                    "processing_parameters": parameters,
                },
            },
            caption="Raman spectrum with processed intensity and detected peaks.",
            purpose="raman_analysis_report",
        )
    return result_metadata
