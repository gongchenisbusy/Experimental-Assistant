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
from ea.schema import FTIRProcessingResult
from ea.schema.models import EARecord
from ea.standards import infer_project_slug
from ea.storage.files import read_yaml, write_yaml
from ea.storage.ids import next_id, next_standard_id


class FTIRProcessingError(RuntimeError):
    """Raised when FTIR processing would violate review or data boundaries."""


@dataclass(frozen=True)
class FTIRInspection:
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
class FTIRProcessingRequest:
    x_column: str
    y_column: str
    x_unit: str
    signal_mode: str
    processing_parameters: dict[str, Any]
    column_review_ref: str
    parameter_review_ref: str


FTIR_BAND_WINDOWS = [
    {
        "min": 3200.0,
        "max": 3600.0,
        "family": "O-H / N-H stretching region",
        "notes": "Broad bands in this region often require humidity, adsorbate, or sample-preparation review.",
    },
    {
        "min": 3000.0,
        "max": 3100.0,
        "family": "aromatic or alkene C-H stretching region",
        "notes": "Use only as a screening hint unless supported by project chemistry and references.",
    },
    {
        "min": 2800.0,
        "max": 3000.0,
        "family": "aliphatic C-H stretching region",
        "notes": "Can indicate organic residues, ligands, binders, or sample contamination depending on context.",
    },
    {
        "min": 2250.0,
        "max": 2400.0,
        "family": "CO2/background or triple-bond region",
        "notes": "Atmospheric CO2 and instrument background should be checked before interpretation.",
    },
    {
        "min": 1650.0,
        "max": 1800.0,
        "family": "C=O, C=C, amide, or water-bending-adjacent region",
        "notes": "Multiple functional groups overlap here; assignment needs sample and literature context.",
    },
    {
        "min": 1500.0,
        "max": 1650.0,
        "family": "aromatic C=C, amide II, or water bending region",
        "notes": "This is an overlapping region and should not be used alone for chemical identification.",
    },
    {
        "min": 1200.0,
        "max": 1500.0,
        "family": "C-H bending / C-O / C-N mixed fingerprint region",
        "notes": "Fingerprint-region hints need comparison to reference spectra.",
    },
    {
        "min": 900.0,
        "max": 1200.0,
        "family": "C-O, C-O-C, Si-O, or fingerprint region",
        "notes": "Common in oxides, silicates, polymers, and oxygen-containing groups; confirm with context.",
    },
    {
        "min": 650.0,
        "max": 900.0,
        "family": "out-of-plane bending or fingerprint region",
        "notes": "Often diagnostic only when compared with a reviewed reference spectrum.",
    },
    {
        "min": 400.0,
        "max": 650.0,
        "family": "metal-oxygen or low-wavenumber fingerprint region",
        "notes": "Relevant to many inorganic materials but strongly system-dependent.",
    },
]


def default_ftir_processing_parameters() -> dict[str, Any]:
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
        "normalization": {"enabled": True, "method": "max_abs"},
        "peak_detection": {
            "method": "scipy_find_peaks",
            "prominence": "auto",
            "distance": "auto",
            "max_bands": 12,
        },
        "band_assignment": {
            "enabled": True,
            "source": "ea.ftir.builtin_band_windows:v0.2",
        },
        "context_record": {
            "enabled": False,
            "method": "reviewed_metadata_record",
            "source": "ea.ftir.context_record:v0.2",
            "instrument_accessory": {},
            "atmosphere": {},
            "sample_preparation": {},
            "background": {},
            "reference": {},
            "correction_notes": [],
        },
    }


def _merge_parameters(parameters: dict[str, Any] | None) -> dict[str, Any]:
    merged = default_ftir_processing_parameters()
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
    if "trans" in text or "%t" in text:
        return "transmittance"
    if "abs" in text:
        return "absorbance"
    return "absorbance"


def inspect_ftir_file(path: Path) -> FTIRInspection:
    frame, metadata = _read_spectrum(path)
    columns = [str(column) for column in frame.columns]
    if frame.empty or len(columns) < 2:
        raise FTIRProcessingError(f"No two-column numeric FTIR data found in {path}")

    x_values = pd.to_numeric(frame.iloc[:, 0], errors="coerce").dropna()
    x_min = float(x_values.min())
    x_max = float(x_values.max())
    metadata_text = _axis_metadata_text(metadata)
    path_text = path.as_posix().upper()
    looks_like_wavenumber = "cm" in metadata_text or (350 <= x_min <= 4500 and 350 <= x_max <= 4500)
    looks_like_ftir = "FTIR" in path_text or "INFRARED" in path_text or "/IR/" in path_text or (x_min <= 800 and x_max >= 2500)
    file_kind = "ftir" if looks_like_wavenumber and looks_like_ftir else "unknown"
    x_unit = "cm^-1" if "cm" in metadata_text or looks_like_wavenumber else "unknown"
    warnings: list[str] = []
    if file_kind == "unknown":
        warnings.append("ftir_file_kind_unknown")
    if x_unit == "cm^-1" and "cm" not in metadata_text:
        warnings.append("ftir_unit_inferred_from_range_or_path")

    return FTIRInspection(
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


def _confirmed_frame(path: Path, request: FTIRProcessingRequest) -> pd.DataFrame:
    frame, _ = _read_spectrum(path)
    frame.columns = [str(column) for column in frame.columns]
    if request.x_column not in frame.columns or request.y_column not in frame.columns:
        raise FTIRProcessingError("Confirmed x/y columns are not present in the raw file")
    if request.x_unit not in {"cm^-1", "unknown"}:
        raise FTIRProcessingError("FTIR x_unit must be user-confirmed as cm^-1 or unknown")
    if request.signal_mode not in {"absorbance", "transmittance"}:
        raise FTIRProcessingError("FTIR signal_mode must be user-confirmed as absorbance or transmittance")
    data = frame[[request.x_column, request.y_column]].copy()
    data.columns = ["wavenumber_cm-1", "raw_signal"]
    data["wavenumber_cm-1"] = pd.to_numeric(data["wavenumber_cm-1"], errors="coerce")
    data["raw_signal"] = pd.to_numeric(data["raw_signal"], errors="coerce")
    data = data.dropna().sort_values("wavenumber_cm-1").reset_index(drop=True)
    if data.empty:
        raise FTIRProcessingError("Confirmed FTIR columns contain no numeric data")
    return data


def _rolling_quantile_baseline(signal: np.ndarray, parameters: dict[str, Any]) -> tuple[np.ndarray, list[dict[str, Any]]]:
    baseline = parameters.get("baseline_correction", {})
    window_points, window_adjusted = _coerce_int(baseline.get("window_points"), 101, minimum=3)
    quantile, quantile_adjusted = _coerce_float(baseline.get("quantile"), 0.05, minimum=0.0, maximum=1.0)
    adjusted = window_adjusted or quantile_adjusted
    if window_points > signal.size:
        window_points = signal.size
        adjusted = True
    if window_points % 2 == 0:
        window_points = max(3, window_points - 1)
        adjusted = True
    warnings: list[dict[str, Any]] = []
    if adjusted:
        warnings.append(
            _warning(
                "ftir_baseline_parameter_adjusted",
                "Invalid FTIR rolling-quantile baseline parameters were adjusted.",
                window_points=window_points,
                quantile=quantile,
            )
        )
    if signal.size < 3:
        warnings.append(_warning("ftir_baseline_skipped", "FTIR baseline correction skipped because the spectrum has fewer than three points.", severity="medium"))
        return np.zeros_like(signal), warnings
    series = pd.Series(signal)
    baseline_values = series.rolling(window_points, center=True, min_periods=1).quantile(quantile).to_numpy(dtype=float)
    warnings.append(
        _warning(
            "ftir_baseline_applied",
            "Rolling-quantile baseline correction was applied before FTIR peak detection.",
            method="rolling_quantile",
            window_points=window_points,
            quantile=quantile,
        )
    )
    return baseline_values, warnings


def _apply_processing(
    data: pd.DataFrame,
    parameters: dict[str, Any],
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    processed = data.copy()
    warnings: list[dict[str, Any]] = []
    signal = processed["raw_signal"].to_numpy(dtype=float)
    processed["baseline_signal"] = np.nan

    if parameters.get("baseline_correction", {}).get("enabled", False):
        baseline, baseline_warnings = _rolling_quantile_baseline(signal, parameters)
        signal = signal - baseline
        processed["baseline_signal"] = baseline
        warnings.extend(baseline_warnings)

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
                    "ftir_smoothing_parameter_adjusted",
                    "Invalid Savitzky-Golay parameters were adjusted for FTIR processing.",
                    window_length=window_length,
                    polyorder=polyorder,
                )
            )
        if signal.size >= 3 and window_length >= 3:
            signal = np.asarray(savgol_filter(signal, window_length=window_length, polyorder=polyorder, mode="interp"), dtype=float)
            processed["smoothed_signal"] = signal
            warnings.append(
                _warning(
                    "ftir_smoothing_applied",
                    "Savitzky-Golay smoothing was applied before FTIR normalization and peak detection.",
                    method="savitzky_golay",
                    window_length=window_length,
                    polyorder=polyorder,
                )
            )
        else:
            warnings.append(_warning("ftir_smoothing_skipped", "FTIR smoothing skipped because the spectrum has fewer than three points.", severity="medium"))

    if parameters.get("normalization", {}).get("enabled", True):
        max_value = float(np.max(np.abs(signal)))
        if max_value > 0:
            signal = signal / max_value
        warnings.append(_warning("ftir_normalization_applied", "FTIR signal normalized by processing parameters."))
    processed["processed_signal"] = signal
    return processed, warnings


def _band_family(wavenumber: float, parameters: dict[str, Any]) -> dict[str, str]:
    if not parameters.get("band_assignment", {}).get("enabled", True):
        return {"family": "", "confidence": "", "source": "", "notes": "band assignment disabled by processing parameters"}
    for window in FTIR_BAND_WINDOWS:
        if float(window["min"]) <= wavenumber <= float(window["max"]):
            return {
                "family": str(window["family"]),
                "confidence": "low",
                "source": str(parameters.get("band_assignment", {}).get("source") or "ea.ftir.builtin_band_windows:v0.2"),
                "notes": str(window["notes"]),
            }
    return {
        "family": "unassigned FTIR band region",
        "confidence": "insufficient",
        "source": str(parameters.get("band_assignment", {}).get("source") or "ea.ftir.builtin_band_windows:v0.2"),
        "notes": "No built-in broad band window matched this wavenumber.",
    }


def _detect_bands(processed: pd.DataFrame, parameters: dict[str, Any], signal_mode: str) -> pd.DataFrame:
    y = processed["processed_signal"].to_numpy(dtype=float)
    detection_signal = y if signal_mode == "absorbance" else -y
    peak_params = parameters.get("peak_detection", {})
    prominence = peak_params.get("prominence", "auto")
    distance = peak_params.get("distance", "auto")
    max_bands, _ = _coerce_int(peak_params.get("max_bands"), 12, minimum=1)
    if prominence == "auto":
        prominence = max(float(np.ptp(detection_signal)) * 0.08, 0.02)
    if distance == "auto":
        distance = max(len(detection_signal) // 100, 1)
    peaks, properties = find_peaks(detection_signal, prominence=prominence, distance=distance)
    ranked = sorted(
        [(int(peak), float(properties["prominences"][index])) for index, peak in enumerate(peaks)],
        key=lambda item: item[1],
        reverse=True,
    )[:max_bands]
    ranked.sort(key=lambda item: float(processed.iloc[item[0]]["wavenumber_cm-1"]), reverse=True)
    rows = []
    for index, (peak_index, peak_prominence) in enumerate(ranked, start=1):
        row = processed.iloc[peak_index]
        wavenumber = float(row["wavenumber_cm-1"])
        family = _band_family(wavenumber, parameters)
        rows.append(
            {
                "band_id": f"ftir-band-{index:03d}",
                "wavenumber_cm-1": wavenumber,
                "raw_signal": float(row["raw_signal"]),
                "processed_signal": float(row["processed_signal"]),
                "detection_height": float(detection_signal[peak_index]),
                "prominence": peak_prominence,
                "method": "scipy_find_peaks",
                "signal_mode": signal_mode,
                "band_type": "absorbance_maximum" if signal_mode == "absorbance" else "transmittance_minimum",
                "possible_band_family": family["family"],
                "assignment_confidence": family["confidence"],
                "assignment_source": family["source"],
                "notes": family["notes"],
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "band_id",
            "wavenumber_cm-1",
            "raw_signal",
            "processed_signal",
            "detection_height",
            "prominence",
            "method",
            "signal_mode",
            "band_type",
            "possible_band_family",
            "assignment_confidence",
            "assignment_source",
            "notes",
        ],
    )


_FTIR_CONTEXT_SECTIONS = ("instrument_accessory", "atmosphere", "sample_preparation", "background", "reference")


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
            "ftir_context_section_ignored",
            "An FTIR context-record section was ignored because it was not a mapping.",
            severity="medium",
            section=name,
        ),
    )


def _context_notes(params: dict[str, Any]) -> tuple[list[Any], dict[str, Any] | None]:
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
            "ftir_context_notes_ignored",
            "FTIR context notes were ignored because they were not a list or non-empty string.",
            severity="medium",
        ),
    )


def _record_context(parameters: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    params = parameters.get("context_record", {})
    if not isinstance(params, dict) or not params.get("enabled", False):
        return None, []
    warnings: list[dict[str, Any]] = []
    sections: dict[str, dict[str, Any]] = {}
    for name in _FTIR_CONTEXT_SECTIONS:
        section, warning = _context_section(params, name)
        sections[name] = section
        if warning:
            warnings.append(warning)
    notes, notes_warning = _context_notes(params)
    if notes_warning:
        warnings.append(notes_warning)

    reviewed_fields = [name for name, section in sections.items() if _has_context_payload(section)]
    if _has_context_payload(notes):
        reviewed_fields.append("correction_notes")
    has_reviewed_context = bool(reviewed_fields)
    if not has_reviewed_context:
        warnings.append(
            _warning(
                "ftir_context_record_empty",
                "FTIR context_record was enabled, but no reviewed method/context metadata was supplied.",
                severity="medium",
            )
        )
    source = str(params.get("source") or "ea.ftir.context_record:v0.2")
    return (
        {
            "enabled": True,
            "status": "reviewed_context_recorded" if has_reviewed_context else "enabled_without_reviewed_context",
            "method": str(params.get("method") or "reviewed_metadata_record"),
            "assignment_source": source,
            "confidence": "low" if has_reviewed_context else "insufficient",
            "reviewed_context_fields": reviewed_fields,
            **sections,
            "correction_notes": notes,
            "warnings": warnings,
            "boundary": "FTIR context record is metadata/provenance only; no automatic background, reference, ATR, or atmosphere correction was applied.",
        },
        warnings,
    )


def _analyze_bands(bands: pd.DataFrame, context_record: dict[str, Any] | None = None) -> dict[str, Any]:
    analysis: dict[str, Any] = {
        "band_count": int(len(bands)),
        "strongest_bands": [],
        "context_record": context_record,
        "possible_interpretations": [],
    }
    if bands.empty:
        analysis["possible_interpretations"].append(
            {
                "text": "No stable FTIR band was detected by the current automatic settings.",
                "confidence": "insufficient",
                "evidence": [],
            }
        )
    else:
        strongest = bands.sort_values("prominence", ascending=False).head(6)
        analysis["strongest_bands"] = [
            {
                "band_id": str(row["band_id"]),
                "wavenumber_cm-1": float(row["wavenumber_cm-1"]),
                "possible_band_family": str(row["possible_band_family"]),
                "assignment_confidence": str(row["assignment_confidence"]),
                "assignment_source": str(row["assignment_source"]),
            }
            for _, row in strongest.iterrows()
        ]
        for family, family_rows in strongest.groupby("possible_band_family", sort=False):
            evidence = [str(value) for value in family_rows["band_id"].head(3)]
            confidence_values = [str(value) for value in family_rows["assignment_confidence"] if str(value)]
            confidence = "low" if "low" in confidence_values else "insufficient"
            source_values = [str(value) for value in family_rows["assignment_source"] if str(value)]
            analysis["possible_interpretations"].append(
                {
                    "text": f"Detected FTIR feature(s) fall in the broad {family} window; treat this as a screening hint, not a definitive chemical assignment.",
                    "confidence": confidence,
                    "evidence": evidence,
                    "assignment_source": source_values[0] if source_values else "",
                }
            )
    if context_record and context_record.get("status") == "reviewed_context_recorded":
        fields = ", ".join(str(value) for value in context_record.get("reviewed_context_fields", [])) or "FTIR context"
        analysis["possible_interpretations"].append(
            {
                "text": (
                    f"Reviewed FTIR method/context metadata was recorded for {fields}. Use it to interpret band screening hints, "
                    "but do not treat the metadata record as an automatic correction or a standalone chemical assignment."
                ),
                "confidence": context_record.get("confidence", "low"),
                "evidence": ["context_record"],
                "assignment_source": context_record.get("assignment_source", "ea.ftir.context_record:v0.2"),
            }
        )
    return analysis


def _created_day(created_at: str | None) -> str | None:
    return created_at[:10] if created_at else None


def _uses_v0_2_project_ids(project_id: str) -> bool:
    return project_id.startswith("prj-")


def _plot_ftir(processed: pd.DataFrame, bands: pd.DataFrame, output: Path, signal_mode: str, *, footer: str | None = None) -> None:
    fig, ax = styled_subplots(figsize=(6.0, 4.0))
    ax.plot(
        processed["wavenumber_cm-1"],
        processed["processed_signal"],
        color=NATURE_LIKE_COLORS["blue"],
        linewidth=1.2,
        label="Processed signal",
    )
    if not bands.empty:
        ax.scatter(
            bands["wavenumber_cm-1"],
            bands["processed_signal"],
            color=NATURE_LIKE_COLORS["black"],
            s=18,
            label="Detected bands",
            zorder=3,
        )
        for _, band in bands.sort_values("prominence", ascending=False).head(8).iterrows():
            ax.annotate(
                f"{float(band['wavenumber_cm-1']):.0f}",
                (float(band["wavenumber_cm-1"]), float(band["processed_signal"])),
                textcoords="offset points",
                xytext=(0, 6),
                ha="center",
                fontsize=7,
            )
    ax.invert_xaxis()
    ylabel = "Absorbance (a.u.)" if signal_mode == "absorbance" else "Transmittance (a.u.)"
    style_axis(
        ax,
        title="FTIR spectrum",
        xlabel="Wavenumber (cm^-1)",
        ylabel=ylabel,
    )
    save_styled_figure(fig, output, footer=footer)


def process_ftir_result(
    root: Path,
    *,
    characterization_metadata_path: Path,
    project_id: str,
    sample_refs: list[str],
    request: FTIRProcessingRequest,
    created_at: str | None = None,
) -> Path:
    metadata = read_yaml(characterization_metadata_path)
    require_confirmed_review(root, request.column_review_ref)
    require_confirmed_review(root, request.parameter_review_ref)
    raw_path = root / metadata["project_raw_path"]
    inspection = inspect_ftir_file(raw_path)
    if inspection.file_kind != "ftir":
        raise FTIRProcessingError(f"File is {inspection.file_kind}, not FTIR")

    parameters = _merge_parameters(request.processing_parameters)
    processed, processing_warnings = _apply_processing(_confirmed_frame(raw_path, request), parameters)
    bands = _detect_bands(processed, parameters, request.signal_mode)
    context_record, context_warnings = _record_context(parameters)
    band_analysis = _analyze_bands(bands, context_record)
    day = _created_day(created_at)
    project_slug = infer_project_slug(project_id)
    if _uses_v0_2_project_ids(project_id):
        result_id = next_standard_id(root, "result", project_slug, method="ftir", day=day)
        figure_id = next_standard_id(root, "figure", project_slug, method="ftir", day=day)
    else:
        result_id = next_id(root, "ftir_result", day)
        figure_id = None
    sample_dir = sample_refs[0] if sample_refs else "unmapped-sample"
    output_dir = root / "processed" / sample_dir / "ftir" / result_id
    processed_csv = output_dir / "ftir_processed.csv"
    bands_csv = output_dir / "ftir_bands.csv"
    context_yml = output_dir / "ftir_context.yml"
    figure_name = f"{figure_id}.png" if figure_id else "ftir_plot.png"
    figure = output_dir / figure_name
    result_metadata = output_dir / "ftir_metadata.yml"
    for output in [processed_csv, bands_csv, context_yml, figure, result_metadata]:
        assert_not_raw_output_path(root, output)

    output_dir.mkdir(parents=True, exist_ok=True)
    processed.to_csv(processed_csv, index=False)
    bands.to_csv(bands_csv, index=False)
    context_ref: str | None = None
    if context_record is not None:
        context_ref = str(context_yml.relative_to(root))
        context_record["record_ref"] = context_ref
        write_yaml(context_yml, context_record)
        if band_analysis.get("context_record"):
            band_analysis["context_record"]["record_ref"] = context_ref
    _plot_ftir(processed, bands, figure, request.signal_mode, footer=figure_footer(figure_id, None) if figure_id else None)

    warnings: list[Any] = []
    if request.x_unit == "unknown":
        warnings.append(_warning("ftir_x_unit_unknown", "FTIR x unit remains unknown after confirmation.", severity="medium"))
    warnings.extend(processing_warnings)
    warnings.extend(context_warnings)
    outputs = {
        "figure": str(figure.relative_to(root)),
        "peak_table": str(bands_csv.relative_to(root)),
        "processed_csv": str(processed_csv.relative_to(root)),
        "metadata": str(result_metadata.relative_to(root)),
    }
    if context_ref:
        outputs["context_record"] = context_ref
    result = FTIRProcessingResult(
        ftir_result_id=result_id,
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
        peak_analysis=band_analysis,
        figure_id=figure_id,
        warnings=warnings,
        review_refs=[request.column_review_ref, request.parameter_review_ref],
        created_at=created_at or EARecord.now_iso(),
        updated_at=created_at or EARecord.now_iso(),
    )
    write_yaml(result_metadata, result.model_dump(exclude_none=True))
    provenance_files = [
        str(processed_csv.relative_to(root)),
        str(bands_csv.relative_to(root)),
        str(figure.relative_to(root)),
    ]
    if context_ref:
        provenance_files.append(context_ref)
    provenance_path = write_provenance_entry(
        root,
        workflow="ftir_processing",
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
        scripts=[{"path": "src/ea/ftir/service.py", "version": "0.2.0"}],
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
                "script": "src/ea/ftir/service.py",
                "parameters": {
                    "x_column": request.x_column,
                    "y_column": request.y_column,
                    "x_unit": request.x_unit,
                    "signal_mode": request.signal_mode,
                    "processing_parameters": parameters,
                },
            },
            caption="FTIR spectrum with processed signal, detected bands, and broad band-family screening hints.",
            purpose="ftir_analysis_report",
            style_profile=NATURE_LIKE_STYLE_PROFILE,
            source_data_refs=[
                str(processed_csv.relative_to(root)),
                str(bands_csv.relative_to(root)),
            ]
            + ([context_ref] if context_ref else []),
        )
    return result_metadata
