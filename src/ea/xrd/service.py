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
from ea.literature.source_packet_manifest import SourcePacketManifestError, confirmed_source_packet_library
from ea.materials import infer_material_from_project, match_xrd_peaks, resolve_material_id, summarize_xrd_assignment_libraries
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


BUILTIN_XRD_ASSIGNMENT_LIBRARY_DEFAULT = "builtin_material_assignments"


def builtin_xrd_assignment_libraries() -> list[str]:
    return [BUILTIN_XRD_ASSIGNMENT_LIBRARY_DEFAULT]


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


def _analyze_xrd_peaks(peaks: pd.DataFrame, root: Path, project_id: str) -> dict[str, Any]:
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

    material_id = infer_material_from_project(root, project_id)
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


def _relative_to_root(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _coerce_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list | tuple | set):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _normalize_key(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _xrd_assignment_source_candidates(source_packet: Any) -> list[Any]:
    if isinstance(source_packet, list):
        return source_packet
    if isinstance(source_packet, dict):
        raw_candidates = (
            source_packet.get("candidates")
            or source_packet.get("assignments")
            or source_packet.get("source_candidates")
            or source_packet.get("suggestions")
            or []
        )
        return raw_candidates if isinstance(raw_candidates, list) else []
    return []


def _xrd_candidate_identity(candidate: dict[str, Any]) -> str:
    return str(candidate.get("candidate_id") or candidate.get("assignment_id") or candidate.get("suggestion_id") or "").strip()


def _xrd_coerce_window(candidate: dict[str, Any], *names: str) -> list[float] | None:
    for name in names:
        raw = candidate.get(name)
        if raw is None:
            continue
        if isinstance(raw, dict):
            raw = [
                raw.get("min", raw.get("lower", raw.get("start", raw.get("low")))),
                raw.get("max", raw.get("upper", raw.get("end", raw.get("high")))),
            ]
        if not isinstance(raw, list | tuple) or len(raw) != 2:
            continue
        try:
            lower = float(raw[0])
            upper = float(raw[1])
        except (TypeError, ValueError):
            continue
        if np.isfinite(lower) and np.isfinite(upper):
            return [min(lower, upper), max(lower, upper)]
    return None


def _xrd_window_overlaps(window: list[float] | None, lower: float | None, upper: float | None) -> bool:
    if lower is None and upper is None:
        return True
    if window is None:
        return False
    if lower is not None and window[1] < lower:
        return False
    if upper is not None and window[0] > upper:
        return False
    return True


def _xrd_candidate_material_keys(candidate: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for field in ["material_id", "material", "material_display_name", "formula", "material_scope"]:
        value = candidate.get(field)
        if value is None:
            continue
        keys.add(_normalize_key(value))
        resolved = resolve_material_id(str(value))
        if resolved:
            keys.add(_normalize_key(resolved))
    return keys


def _xrd_candidate_matches_filters(
    candidate: dict[str, Any],
    *,
    include_candidates: set[str],
    material_filters: set[str],
    feature_filters: set[str],
    two_theta_min_deg: float | None,
    two_theta_max_deg: float | None,
    d_spacing_min_angstrom: float | None,
    d_spacing_max_angstrom: float | None,
) -> bool:
    if include_candidates and _xrd_candidate_identity(candidate) not in include_candidates:
        return False
    if material_filters and not (_xrd_candidate_material_keys(candidate) & material_filters):
        return False
    if feature_filters:
        searchable = " ".join(
            str(candidate.get(field) or "")
            for field in [
                "candidate_id",
                "feature",
                "feature_id",
                "label",
                "assignment_label",
                "candidate_type",
                "assignment_type",
            ]
        )
        searchable_key = _normalize_key(searchable)
        if not any(feature and feature in searchable_key for feature in feature_filters):
            return False
    two_theta_window = _xrd_coerce_window(
        candidate,
        "two_theta_window_deg",
        "two_theta_deg_range",
        "two_theta_range_deg",
        "two_theta_window",
        "two_theta_range",
    )
    if not _xrd_window_overlaps(two_theta_window, two_theta_min_deg, two_theta_max_deg):
        return False
    d_spacing_window = _xrd_coerce_window(
        candidate,
        "d_spacing_window_angstrom",
        "d_spacing_angstrom_range",
        "d_spacing_range_angstrom",
        "d_spacing_window",
        "d_spacing_range",
    )
    if not _xrd_window_overlaps(d_spacing_window, d_spacing_min_angstrom, d_spacing_max_angstrom):
        return False
    return True


def _xrd_assignment_template_candidates() -> list[dict[str, Any]]:
    return [
        {
            "candidate_id": "xrd-assignment-template-001",
            "candidate_type": "diffraction_feature_assignment",
            "assignment_type": "diffraction_feature_assignment",
            "material_id": "TODO-material-id",
            "feature": "TODO-feature-id",
            "label": "TODO: e.g. layered (002) reflection",
            "two_theta_window_deg": [None, None],
            "d_spacing_window_angstrom": [None, None],
            "source_summary": "TODO: summarize the reference pattern, PDF card, or literature table supporting this window.",
            "applicability_notes": [
                "TODO: describe radiation wavelength, phase/material assumptions, sample context, and known overlapping peaks."
            ],
            "reference_ids": ["TODO-registered-reference-id"],
            "confidence": "low",
            "caveats": [
                "Template candidate only; fill source metadata and reviewed windows before using it for XRD interpretation.",
                "This candidate does not prove phase identity, material identity, crystallinity, texture, strain, or sample quality by itself.",
            ],
            "auto_applied": False,
            "requires_user_review": True,
        }
    ]


def _xrd_source_reference_seeds(
    source_packet: Any,
    *,
    referenced_ids: set[str],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(source_packet, dict):
        return {}
    raw_seeds = source_packet.get("reference_seeds") or {}
    if not raw_seeds:
        return {}
    if not isinstance(raw_seeds, dict):
        warnings.append(
            _warning(
                "xrd_assignment_source_reference_seeds_invalid",
                "XRD assignment source reference_seeds were ignored because they were not a mapping.",
                severity="medium",
            )
        )
        return {}
    seeds: dict[str, Any] = {}
    for raw_seed_id, raw_seed in raw_seeds.items():
        seed_id = str(raw_seed_id).strip()
        if not seed_id or seed_id not in referenced_ids:
            continue
        if not isinstance(raw_seed, dict):
            warnings.append(
                _warning(
                    "xrd_assignment_source_reference_seed_ignored",
                    "An XRD assignment source reference_seed was skipped because its metadata was not a mapping.",
                    severity="medium",
                    seed_id=seed_id,
                )
            )
            continue
        seeds[seed_id] = deepcopy(raw_seed)
    return seeds


def _xrd_builtin_assignment_source_library(
    *,
    materials: list[str],
    features: list[str],
    two_theta_min_deg: float | None,
    two_theta_max_deg: float | None,
    d_spacing_min_angstrom: float | None,
    d_spacing_max_angstrom: float | None,
) -> dict[str, Any]:
    summary = summarize_xrd_assignment_libraries(
        materials=materials,
        features=features,
        two_theta_min_deg=two_theta_min_deg,
        two_theta_max_deg=two_theta_max_deg,
        d_spacing_min_angstrom=d_spacing_min_angstrom,
        d_spacing_max_angstrom=d_spacing_max_angstrom,
    )
    library = summary["libraries"][0]
    reference_seeds: dict[str, Any] = {}
    candidates: list[dict[str, Any]] = []
    for profile in library.get("material_profiles", []):
        hints_by_key = {
            str(hint.get("key")): hint
            for hint in profile.get("reference_hints", [])
            if isinstance(hint, dict) and hint.get("key")
        }
        for raw_candidate in profile.get("candidates", []):
            if not isinstance(raw_candidate, dict):
                continue
            reference_ids: list[str] = []
            for hint_key in raw_candidate.get("reference_hint_keys", []):
                hint = hints_by_key.get(str(hint_key))
                if not hint:
                    continue
                seed_id = f"builtin-xrd-{hint_key}"
                reference_ids.append(seed_id)
                seed: dict[str, Any] = {
                    "source_type": "manual",
                    "title": hint.get("label") or hint_key,
                    "citation": hint.get("label") or hint_key,
                    "notes": "Built-in XRD reference hint; register or replace this seed before treating packet candidates as report evidence.",
                }
                if hint.get("doi"):
                    seed["doi"] = str(hint["doi"])
                    seed["url"] = f"https://doi.org/{hint['doi']}"
                if hint.get("url") and not seed.get("url"):
                    seed["url"] = hint["url"]
                reference_seeds[seed_id] = seed
            notes = _coerce_string_list(raw_candidate.get("notes"))
            caveats = list(profile.get("caveats", [])) + notes
            caveats.append(
                "Built-in XRD candidates are source-backed screening metadata; use registered references and user review before interpretation."
            )
            candidate = deepcopy(raw_candidate)
            candidate.update(
                {
                    "candidate_type": "diffraction_feature_assignment",
                    "assignment_type": "diffraction_feature_assignment",
                    "material_id": profile.get("material_id"),
                    "material_display_name": profile.get("display_name"),
                    "formula": profile.get("formula"),
                    "reference_ids": reference_ids,
                    "source_summary": (
                        f"Built-in source-backed XRD screening candidate for {profile.get('display_name') or profile.get('material_id')} "
                        f"{raw_candidate.get('label') or raw_candidate.get('feature')}; use the cited reference seed(s) to verify the expected "
                        "diffraction feature in the project context."
                    ),
                    "applicability_notes": [
                        "Compare against processed XRD peak positions only after the raw-data columns and processing parameters have been reviewed.",
                        "Check radiation wavelength, sample preparation, preferred orientation, substrate/background peaks, and possible overlapping phases.",
                    ],
                    "confidence": "low",
                    "caveats": caveats,
                    "auto_applied": False,
                    "requires_user_review": True,
                }
            )
            candidates.append(candidate)
    return {
        "schema_version": "0.2",
        "source": "ea.materials.xrd_assignment_builtin_source_library:v0.2",
        "library_id": BUILTIN_XRD_ASSIGNMENT_LIBRARY_DEFAULT,
        "library_ref": library.get("library_ref"),
        "reference_seeds": reference_seeds,
        "guidance_notes": [
            "Built-in XRD candidates are starter source-packet seeds. Register or replace reference seeds before using candidates as report evidence."
        ],
        "guidance_reference_ids": [],
        "candidates": candidates,
    }


def build_xrd_assignment_source_packet(
    root: Path,
    *,
    project_id: str,
    library_path: Path | None = None,
    builtin_library: str | None = None,
    literature_manifest_path: Path | None = None,
    output_path: Path | None = None,
    include_candidates: list[str] | None = None,
    materials: list[str] | None = None,
    features: list[str] | None = None,
    two_theta_min_deg: float | None = None,
    two_theta_max_deg: float | None = None,
    d_spacing_min_angstrom: float | None = None,
    d_spacing_max_angstrom: float | None = None,
    template: bool = False,
    created_at: str | None = None,
) -> dict[str, Any]:
    selected_source_count = sum(bool(value) for value in [library_path, builtin_library, literature_manifest_path, template])
    if selected_source_count > 1:
        raise XRDProcessingError(
            "Use only one of --library-file, --builtin-library, --literature-manifest, or --write-template for XRD assignment source-packet generation"
        )
    if not library_path and not literature_manifest_path and not template:
        builtin_library = builtin_library or BUILTIN_XRD_ASSIGNMENT_LIBRARY_DEFAULT
    if builtin_library and builtin_library not in builtin_xrd_assignment_libraries():
        available = ", ".join(builtin_xrd_assignment_libraries())
        raise XRDProcessingError(f"Unknown built-in XRD assignment library: {builtin_library}. Available libraries: {available}")

    template_mode = template and library_path is None and builtin_library is None and literature_manifest_path is None
    builtin_mode = builtin_library is not None
    literature_mode = literature_manifest_path is not None
    day = _created_day(created_at)
    timestamp = created_at or EARecord.now_iso()
    source_packet_id = next_id(root, "xrd_assignment_source_packet", day)
    if output_path is None:
        if template_mode:
            output_path = root / "templates" / "xrd_assignment_source_packet.yml"
        else:
            output_path = root / "suggestions" / "xrd" / "source-packets" / f"{source_packet_id}.yml"
    elif not output_path.is_absolute():
        output_path = root / output_path
    assert_not_raw_output_path(root, output_path)

    material_filters_raw = [str(item).strip() for item in materials or [] if str(item).strip()]
    feature_filters_raw = [str(item).strip() for item in features or [] if str(item).strip()]
    warnings: list[dict[str, Any]] = []
    library_ref: str | None = None
    library_kind = "template" if template_mode else "local_file"
    source_library: Any = {}
    if template_mode:
        raw_candidates = _xrd_assignment_template_candidates()
    elif builtin_mode:
        try:
            source_library = _xrd_builtin_assignment_source_library(
                materials=material_filters_raw,
                features=feature_filters_raw,
                two_theta_min_deg=two_theta_min_deg,
                two_theta_max_deg=two_theta_max_deg,
                d_spacing_min_angstrom=d_spacing_min_angstrom,
                d_spacing_max_angstrom=d_spacing_max_angstrom,
            )
        except KeyError as exc:
            raise XRDProcessingError(str(exc)) from exc
        raw_candidates = _xrd_assignment_source_candidates(source_library)
        library_ref = f"builtin:{builtin_library}"
        library_kind = "built_in"
    elif literature_mode:
        source_path = literature_manifest_path if literature_manifest_path and literature_manifest_path.is_absolute() else root / literature_manifest_path if literature_manifest_path else None
        if source_path is None:
            raise XRDProcessingError("XRD literature manifest path was not supplied")
        try:
            source_library, manifest_warnings = confirmed_source_packet_library(
                root,
                manifest_path=source_path,
                method="xrd",
                method_aliases={"xrd", "diffraction", "x_ray_diffraction", "xrd_assignment", "xrd_assignment_source_packet"},
            )
        except SourcePacketManifestError as exc:
            raise XRDProcessingError(str(exc)) from exc
        warnings.extend(manifest_warnings)
        raw_candidates = _xrd_assignment_source_candidates(source_library)
        library_ref = _relative_to_root(root, source_path)
        library_kind = "confirmed_literature_manifest"
    else:
        source_path = library_path if library_path and library_path.is_absolute() else root / library_path if library_path else None
        if source_path is None or not source_path.exists():
            raise XRDProcessingError(f"XRD assignment library file not found: {library_path}")
        library_ref = _relative_to_root(root, source_path)
        source_library = read_yaml(source_path)
        raw_candidates = _xrd_assignment_source_candidates(source_library)

    include_set = {str(item).strip() for item in include_candidates or [] if str(item).strip()}
    material_filter_keys: set[str] = set()
    for material in material_filters_raw:
        material_filter_keys.add(_normalize_key(material))
        resolved = resolve_material_id(material)
        if resolved:
            material_filter_keys.add(_normalize_key(resolved))
    feature_filter_keys = {_normalize_key(feature) for feature in feature_filters_raw}

    selected: list[dict[str, Any]] = []
    for index, raw_candidate in enumerate(raw_candidates, start=1):
        if not isinstance(raw_candidate, dict):
            warnings.append(
                _warning(
                    "xrd_assignment_source_candidate_ignored",
                    "An XRD assignment source candidate was not a mapping and was skipped while building the source packet.",
                    severity="medium",
                    candidate_index=index,
                )
            )
            continue
        if not _xrd_candidate_matches_filters(
            raw_candidate,
            include_candidates=include_set,
            material_filters=material_filter_keys,
            feature_filters=feature_filter_keys,
            two_theta_min_deg=two_theta_min_deg,
            two_theta_max_deg=two_theta_max_deg,
            d_spacing_min_angstrom=d_spacing_min_angstrom,
            d_spacing_max_angstrom=d_spacing_max_angstrom,
        ):
            continue
        candidate = deepcopy(raw_candidate)
        candidate.setdefault("auto_applied", False)
        candidate.setdefault("requires_user_review", True)
        selected.append(candidate)

    if not raw_candidates:
        warnings.append(
            _warning(
                "xrd_assignment_source_library_empty",
                "No XRD assignment candidates were found in the source library.",
                severity="medium",
            )
        )
    if raw_candidates and not selected:
        warnings.append(
            _warning(
                "xrd_assignment_source_no_matches",
                "No XRD assignment candidates matched the requested filters.",
                severity="medium",
            )
        )

    candidate_reference_ids = {reference_id for candidate in selected for reference_id in _coerce_string_list(candidate.get("reference_ids"))}
    guidance_reference_ids = (
        _coerce_string_list(source_library.get("guidance_reference_ids")) if isinstance(source_library, dict) else []
    )
    reference_ids = sorted(candidate_reference_ids | set(guidance_reference_ids))
    reference_seeds = _xrd_source_reference_seeds(
        source_library,
        referenced_ids=set(reference_ids),
        warnings=warnings,
    )
    packet_ref = _relative_to_root(root, output_path)
    status = "template_requires_user_edit" if template_mode else ("ready_for_review" if selected else "no_matching_candidates")
    filters = {
        "include_candidates": sorted(include_set),
        "materials": material_filters_raw,
        "resolved_materials": sorted(material_filter_keys),
        "features": feature_filters_raw,
        "two_theta_min_deg": two_theta_min_deg,
        "two_theta_max_deg": two_theta_max_deg,
        "d_spacing_min_angstrom": d_spacing_min_angstrom,
        "d_spacing_max_angstrom": d_spacing_max_angstrom,
    }
    packet = {
        "schema_version": "0.2",
        "source_packet_id": source_packet_id,
        "project_id": project_id,
        "status": status,
        "created_at": timestamp,
        "updated_at": timestamp,
        "source": "ea.xrd.assignment_source_packet:v0.2",
        "source_library_kind": library_kind,
        "source_library_ref": library_ref,
        "source_manifest_ref": source_library.get("source_manifest_ref") if literature_mode and isinstance(source_library, dict) else None,
        "confirmation_status": source_library.get("confirmation_status") if literature_mode and isinstance(source_library, dict) else None,
        "reference_seed_count": len(reference_seeds),
        "reference_seeds": reference_seeds,
        "guidance_notes": _coerce_string_list(source_library.get("guidance_notes")) if isinstance(source_library, dict) else [],
        "guidance_reference_ids": guidance_reference_ids,
        "candidate_count": len(selected),
        "candidates": selected,
        "filters": filters,
        "reference_ids": reference_ids,
        "warnings": warnings,
        "next_steps": [
            "Register or replace reference_seeds with project references before treating any XRD assignment candidate as report evidence.",
            "Review and edit this packet until every candidate has source_summary, applicability_notes, reference_ids, confidence, caveats, and reviewed 2theta/d-spacing windows where relevant.",
            "Run ea xrd suggest-assignments with processed XRD metadata to create advisory matched-peak suggestion records; this builder does not match peaks or apply assignments.",
        ],
        "boundaries": [
            "XRD assignment source packets are staging artifacts and do not modify raw data, processing outputs, reports, or project memory.",
            "This builder is deterministic and does not perform live lookup, article download, full-text parsing, raw-data processing, peak matching, report citation injection, ReviewRecord creation, memory writes, or automatic assignment application.",
            "Values may originate from built-in source-backed metadata, local project libraries, user-provided records, project literature records, or separately confirmed literature/search connectors; EA may prepare those candidates, but they remain reviewable suggestions.",
            "Confirmed-literature manifests and built-in reference seeds do not prove phase identity, material identity, crystallinity, texture, strain, lattice parameters, instrument calibration, or sample quality.",
        ],
    }
    write_yaml(output_path, packet)
    provenance_path = write_provenance_entry(
        root,
        workflow="xrd_assignment_source_packet",
        inputs={"records": [library_ref] if library_ref else [], "files": []},
        outputs={"records": [packet_ref], "files": []},
        parameters={
            "candidate_count": len(selected),
            "reference_seed_count": len(reference_seeds),
            "template": template_mode,
            "builtin_library": builtin_library if builtin_mode else None,
            "source_library_kind": library_kind,
            "filters": filters,
            "auto_applied": False,
        },
        warnings=warnings,
        source_refs=reference_ids,
        created_at=created_at,
    )
    packet["provenance_ref"] = _relative_to_root(root, provenance_path)
    write_yaml(output_path, packet)
    return {
        "source_packet": str(output_path),
        "source_packet_id": source_packet_id,
        "status": status,
        "candidate_count": len(selected),
        "reference_ids": reference_ids,
        "reference_seed_count": len(reference_seeds),
        "source_library_kind": library_kind,
        "source_library_ref": library_ref,
        "warnings": warnings,
        "provenance": str(provenance_path),
    }


def _registered_reference_ids(root: Path) -> set[str]:
    index_path = root / "literature" / "references" / "index.yml"
    if not index_path.exists():
        return set()
    index = read_yaml(index_path)
    references = index.get("references")
    if not isinstance(references, dict):
        return set()
    return {str(reference_id) for reference_id in references}


def _xrd_assignment_columns() -> list[str]:
    return [
        "candidate_id",
        "assignment_type",
        "material_id",
        "feature",
        "label",
        "status",
        "requires_user_review",
        "auto_applied",
        "two_theta_window_deg",
        "d_spacing_window_angstrom",
        "matched_peak_ids",
        "matched_two_theta_deg",
        "matched_d_spacing_angstrom",
        "source_summary",
        "reference_ids",
        "unresolved_reference_ids",
        "applicability_notes",
        "confidence",
        "missing_fields",
        "caveats",
    ]


def _xrd_peak_float(row: Any, *names: str) -> float | None:
    for name in names:
        try:
            value = row.get(name)
        except AttributeError:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if np.isfinite(number):
            return number
    return None


def _xrd_peak_matches_candidate(
    row: Any,
    *,
    two_theta_window: list[float] | None,
    d_spacing_window: list[float] | None,
) -> dict[str, Any] | None:
    two_theta = _xrd_peak_float(row, "two_theta_deg", "two_theta", "position_2theta_deg", "position")
    d_spacing = _xrd_peak_float(row, "d_spacing_angstrom", "d_spacing", "d_spacing_A")
    checks: list[bool] = []
    if two_theta_window is not None and two_theta is not None:
        checks.append(two_theta_window[0] <= two_theta <= two_theta_window[1])
    if d_spacing_window is not None and d_spacing is not None:
        checks.append(d_spacing_window[0] <= d_spacing <= d_spacing_window[1])
    if not checks or not all(checks):
        return None
    return {
        "peak_id": str(row.get("peak_id") or ""),
        "two_theta_deg": two_theta,
        "d_spacing_angstrom": d_spacing,
        "height": _xrd_peak_float(row, "height"),
        "prominence": _xrd_peak_float(row, "prominence"),
        "possible_phase": str(row.get("possible_phase") or ""),
        "assignment_feature": str(row.get("assignment_feature") or ""),
        "assignment_confidence": str(row.get("assignment_confidence") or ""),
    }


def _match_xrd_assignment_peaks(
    peaks: pd.DataFrame,
    *,
    two_theta_window: list[float] | None,
    d_spacing_window: list[float] | None,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    if peaks.empty:
        return matches
    for _, row in peaks.iterrows():
        match = _xrd_peak_matches_candidate(row, two_theta_window=two_theta_window, d_spacing_window=d_spacing_window)
        if match is not None:
            matches.append(match)
    return matches


def _normalize_xrd_assignment_candidate(
    raw_candidate: Any,
    *,
    suggestion_id: str,
    number: int,
    peaks: pd.DataFrame,
    registered_references: set[str],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(raw_candidate, dict):
        candidate_id = f"{suggestion_id}-cand-{number:03d}"
        warnings.append(
            _warning(
                "xrd_assignment_suggestion_ignored",
                "An XRD assignment suggestion candidate was not a mapping and was recorded as invalid.",
                severity="medium",
                candidate_id=candidate_id,
            )
        )
        return {
            "candidate_id": candidate_id,
            "assignment_type": "unknown",
            "status": "invalid_candidate_mapping",
            "requires_user_review": True,
            "auto_applied": False,
            "missing_fields": ["candidate_mapping"],
        }

    candidate_id = _xrd_candidate_identity(raw_candidate) or f"{suggestion_id}-cand-{number:03d}"
    assignment_type = str(raw_candidate.get("assignment_type") or raw_candidate.get("candidate_type") or "diffraction_feature_assignment").strip()
    material_id = str(raw_candidate.get("material_id") or raw_candidate.get("material") or "").strip()
    feature = str(raw_candidate.get("feature") or raw_candidate.get("feature_id") or "").strip()
    label = str(raw_candidate.get("label") or raw_candidate.get("assignment_label") or feature).strip()
    two_theta_window = _xrd_coerce_window(
        raw_candidate,
        "two_theta_window_deg",
        "two_theta_deg_range",
        "two_theta_range_deg",
        "two_theta_window",
        "two_theta_range",
    )
    d_spacing_window = _xrd_coerce_window(
        raw_candidate,
        "d_spacing_window_angstrom",
        "d_spacing_angstrom_range",
        "d_spacing_range_angstrom",
        "d_spacing_window",
        "d_spacing_range",
    )
    source_summary = str(raw_candidate.get("source_summary") or raw_candidate.get("reference_summary") or "").strip()
    reference_ids = _coerce_string_list(raw_candidate.get("reference_ids"))
    applicability_notes = _coerce_string_list(raw_candidate.get("applicability_notes"))
    caveats = _coerce_string_list(raw_candidate.get("caveats"))
    confidence = str(raw_candidate.get("confidence") or "low").strip().lower()
    unresolved_reference_ids = [reference_id for reference_id in reference_ids if reference_id not in registered_references]
    missing_fields: list[str] = []
    if not label:
        missing_fields.append("label")
    if two_theta_window is None and d_spacing_window is None:
        missing_fields.append("two_theta_or_d_spacing_window")
    if not source_summary:
        missing_fields.append("source_summary")
    if not reference_ids:
        missing_fields.append("reference_ids")
    if not applicability_notes:
        missing_fields.append("applicability_notes")

    matches = (
        _match_xrd_assignment_peaks(peaks, two_theta_window=two_theta_window, d_spacing_window=d_spacing_window)
        if two_theta_window is not None or d_spacing_window is not None
        else []
    )
    if missing_fields:
        status = "invalid_missing_required_metadata"
    elif unresolved_reference_ids:
        status = "needs_reference_registration"
    elif not matches:
        status = "no_feature_match"
    else:
        status = "ready_for_user_review"

    candidate = {
        "candidate_id": candidate_id,
        "assignment_type": assignment_type,
        "material_id": material_id or None,
        "feature": feature or None,
        "label": label,
        "status": status,
        "requires_user_review": True,
        "auto_applied": False,
        "two_theta_window_deg": two_theta_window or [],
        "d_spacing_window_angstrom": d_spacing_window or [],
        "matched_peaks": matches,
        "matched_peak_ids": [match["peak_id"] for match in matches if match.get("peak_id")],
        "matched_two_theta_deg": [match["two_theta_deg"] for match in matches if match.get("two_theta_deg") is not None],
        "matched_d_spacing_angstrom": [match["d_spacing_angstrom"] for match in matches if match.get("d_spacing_angstrom") is not None],
        "source_summary": source_summary,
        "reference_ids": reference_ids,
        "unresolved_reference_ids": unresolved_reference_ids,
        "applicability_notes": applicability_notes,
        "confidence": confidence,
        "missing_fields": missing_fields,
        "caveats": caveats,
    }
    if unresolved_reference_ids:
        warnings.append(
            _warning(
                "xrd_assignment_suggestion_reference_unresolved",
                "An XRD assignment suggestion cites reference_ids that are not registered in the project reference index.",
                severity="medium",
                candidate_id=candidate_id,
                unresolved_reference_ids=unresolved_reference_ids,
            )
        )
    if missing_fields:
        warnings.append(
            _warning(
                "xrd_assignment_suggestion_missing_metadata",
                "An XRD assignment suggestion is missing required source, diffraction-window, or applicability metadata.",
                severity="medium",
                candidate_id=candidate_id,
                missing_fields=missing_fields,
            )
        )
    if status == "no_feature_match":
        warnings.append(
            _warning(
                "xrd_assignment_suggestion_no_feature_match",
                "An XRD assignment candidate did not match any detected XRD peak in the processed peak table.",
                severity="low",
                candidate_id=candidate_id,
                two_theta_window_deg=candidate["two_theta_window_deg"],
                d_spacing_window_angstrom=candidate["d_spacing_window_angstrom"],
            )
        )
    return candidate


def suggest_xrd_assignments(
    root: Path,
    *,
    project_id: str,
    xrd_metadata_path: Path,
    source_path: Path,
    related_records: list[str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    source_packet = read_yaml(source_path)
    raw_candidates = _xrd_assignment_source_candidates(source_packet)
    xrd_metadata = read_yaml(xrd_metadata_path)
    peak_table_ref = xrd_metadata.get("outputs", {}).get("peak_table")
    if not peak_table_ref:
        raise XRDProcessingError("XRD metadata does not include outputs.peak_table for assignment matching")
    peak_table_path = root / str(peak_table_ref)
    if not peak_table_path.exists():
        raise XRDProcessingError(f"XRD peak table not found: {peak_table_ref}")
    peaks = pd.read_csv(peak_table_path)

    day = _created_day(created_at)
    timestamp = created_at or EARecord.now_iso()
    suggestion_id = next_id(root, "suggestion", day)
    output_dir = root / "suggestions" / "xrd" / suggestion_id
    record_path = output_dir / "xrd_assignment_suggestions.yml"
    table_path = output_dir / "xrd_assignment_suggestions.csv"
    for path in [record_path, table_path]:
        assert_not_raw_output_path(root, path)

    warnings: list[dict[str, Any]] = []
    if not raw_candidates:
        warnings.append(
            _warning(
                "xrd_assignment_suggestion_empty_source",
                "No XRD assignment candidates were found in the source packet.",
                severity="medium",
            )
        )
    registered_references = _registered_reference_ids(root)
    candidates = [
        _normalize_xrd_assignment_candidate(
            candidate,
            suggestion_id=suggestion_id,
            number=index,
            peaks=peaks,
            registered_references=registered_references,
            warnings=warnings,
        )
        for index, candidate in enumerate(raw_candidates, start=1)
    ]
    table = pd.DataFrame(candidates, columns=_xrd_assignment_columns())
    for column in [
        "two_theta_window_deg",
        "d_spacing_window_angstrom",
        "matched_peak_ids",
        "matched_two_theta_deg",
        "matched_d_spacing_angstrom",
        "reference_ids",
        "unresolved_reference_ids",
        "applicability_notes",
        "missing_fields",
        "caveats",
    ]:
        if column in table.columns:
            table[column] = table[column].apply(lambda value: "; ".join(str(item) for item in value) if isinstance(value, list) else value)

    ready_count = sum(1 for candidate in candidates if candidate.get("status") == "ready_for_user_review")
    unresolved_count = sum(1 for candidate in candidates if candidate.get("status") == "needs_reference_registration")
    no_match_count = sum(1 for candidate in candidates if candidate.get("status") == "no_feature_match")
    invalid_count = sum(1 for candidate in candidates if str(candidate.get("status", "")).startswith("invalid"))
    if ready_count:
        status = "ready_for_user_review"
    elif unresolved_count:
        status = "needs_reference_registration"
    elif no_match_count:
        status = "no_feature_match"
    else:
        status = "needs_source_metadata"

    source_ref = _relative_to_root(root, source_path)
    metadata_ref = _relative_to_root(root, xrd_metadata_path)
    record_ref = _relative_to_root(root, record_path)
    table_ref = _relative_to_root(root, table_path)
    related_records = related_records or []
    all_reference_ids = sorted({reference_id for candidate in candidates for reference_id in candidate.get("reference_ids", [])})
    record = {
        "schema_version": "0.2",
        "suggestion_id": suggestion_id,
        "project_id": project_id,
        "status": status,
        "created_at": timestamp,
        "updated_at": timestamp,
        "source": "ea.xrd.assignment_suggestions:v0.2",
        "source_packet_ref": source_ref,
        "xrd_metadata_ref": metadata_ref,
        "peak_table_ref": str(peak_table_ref),
        "table_ref": table_ref,
        "candidate_count": len(candidates),
        "ready_for_user_review_count": ready_count,
        "needs_reference_registration_count": unresolved_count,
        "no_feature_match_count": no_match_count,
        "invalid_count": invalid_count,
        "candidates": candidates,
        "related_records": related_records,
        "reference_ids": all_reference_ids,
        "warnings": warnings,
        "next_steps": [
            "Register or correct unresolved reference_ids before using source-backed XRD assignment suggestions as report evidence.",
            "Run ea xrd prepare-review to create a grouped review package before asking the user which candidate IDs to accept, reject, edit, or defer.",
            "Use matched peak IDs, source summaries, applicability notes, and caveats when discussing possible diffraction features; do not treat a peak-window match alone as phase or material proof.",
        ],
        "boundaries": [
            "XRD assignment suggestions are advisory and auto_applied is always false.",
            "This suggestion-record step does not perform live lookup, process raw data, detect new peaks, mutate source packets, register references, inject report citations, create ReviewRecords, apply assignments, prove structural claims, or write confirmed memory.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(table_path, index=False)
    write_yaml(record_path, record)
    provenance_path = write_provenance_entry(
        root,
        workflow="xrd_assignment_suggestion",
        inputs={"records": [source_ref, metadata_ref, *related_records], "files": [str(peak_table_ref)]},
        outputs={"records": [record_ref, table_ref], "files": []},
        parameters={"candidate_count": len(candidates), "auto_applied": False},
        warnings=warnings,
        source_refs=all_reference_ids,
        created_at=created_at,
    )
    record["provenance_ref"] = _relative_to_root(root, provenance_path)
    write_yaml(record_path, record)
    return {
        "suggestion_id": suggestion_id,
        "record": str(record_path),
        "table": str(table_path),
        "status": status,
        "candidate_count": len(candidates),
        "ready_for_user_review_count": ready_count,
        "needs_reference_registration_count": unresolved_count,
        "no_feature_match_count": no_match_count,
        "invalid_count": invalid_count,
        "warnings": warnings,
    }


def _xrd_review_status_counts(candidates: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        status = str(candidate.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _xrd_review_group_for_status(status: str) -> str:
    if status == "ready_for_user_review":
        return "ready_for_user_review"
    if status == "needs_reference_registration":
        return "needs_reference_registration"
    if status == "no_feature_match":
        return "no_feature_match"
    if status.startswith("invalid"):
        return "invalid_or_incomplete"
    return "other"


def _xrd_review_value(value: Any) -> str:
    if value in (None, "", [], {}):
        return "not recorded"
    if isinstance(value, list | tuple):
        return ", ".join(str(item) for item in value if str(item).strip()) or "not recorded"
    if isinstance(value, dict):
        parts = [f"{key}={item}" for key, item in value.items() if item not in (None, "", [], {})]
        return "; ".join(parts) or "not recorded"
    return str(value)


def _xrd_review_candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    status = str(candidate.get("status") or "unknown")
    if status == "ready_for_user_review":
        action = "Ask the user to accept, reject, or edit this source-backed diffraction candidate before report/memory reuse."
    elif status == "needs_reference_registration":
        action = "Register, replace, or remove unresolved reference_ids before treating this candidate as report evidence."
    elif status == "no_feature_match":
        action = "Keep as no-match context unless the user changes peak detection, source windows, or sample context."
    elif status.startswith("invalid"):
        action = "Fix missing source, window, reference, or applicability metadata before user review."
    else:
        action = "Inspect status and decide whether more source/context work is needed."
    return {
        "candidate_id": str(candidate.get("candidate_id") or ""),
        "review_group": _xrd_review_group_for_status(status),
        "status": status,
        "assignment_type": str(candidate.get("assignment_type") or "unknown"),
        "material_id": str(candidate.get("material_id") or "not recorded"),
        "feature": str(candidate.get("feature") or "not recorded"),
        "label": str(candidate.get("label") or "not recorded"),
        "confidence": str(candidate.get("confidence") or "low"),
        "two_theta_window_deg": candidate.get("two_theta_window_deg") or [],
        "d_spacing_window_angstrom": candidate.get("d_spacing_window_angstrom") or [],
        "matched_peak_ids": _coerce_string_list(candidate.get("matched_peak_ids")),
        "matched_two_theta_deg": _coerce_string_list(candidate.get("matched_two_theta_deg")),
        "matched_d_spacing_angstrom": _coerce_string_list(candidate.get("matched_d_spacing_angstrom")),
        "reference_ids": _coerce_string_list(candidate.get("reference_ids")),
        "unresolved_reference_ids": _coerce_string_list(candidate.get("unresolved_reference_ids")),
        "missing_fields": _coerce_string_list(candidate.get("missing_fields")),
        "source_summary": str(candidate.get("source_summary") or "not recorded"),
        "applicability_notes": _coerce_string_list(candidate.get("applicability_notes")),
        "caveats": _coerce_string_list(candidate.get("caveats")),
        "recommended_action": action,
    }


def _render_xrd_review_package_markdown(package: dict[str, Any]) -> str:
    lines = [
        "# XRD Assignment Suggestion Review Package",
        "",
        "## Summary",
        f"- review_package_id: `{package.get('review_package_id')}`",
        f"- project_id: `{package.get('project_id')}`",
        f"- suggestion_ref: `{package.get('suggestion_ref')}`",
        f"- selected_candidates: `{package.get('selected_candidate_count')}` / `{package.get('candidate_count')}`",
        f"- status: `{package.get('status')}`",
        "",
        "## Status Counts",
    ]
    for status, count in (package.get("selected_status_counts") or {}).items():
        lines.append(f"- `{status}`: {count}")
    lines.extend(["", "## Candidate Groups"])
    for group in package.get("groups", []):
        lines.append(f"### {group.get('group')}")
        lines.append(f"- candidate_ids: `{_xrd_review_value(group.get('candidate_ids'))}`")
        lines.append(f"- recommended_action: {group.get('recommended_action')}")
        lines.append("")
    lines.append("## Candidates")
    for candidate in package.get("candidate_summaries", []):
        lines.extend(
            [
                f"### `{candidate.get('candidate_id')}`",
                f"- group/status: `{candidate.get('review_group')}` / `{candidate.get('status')}`",
                f"- assignment: `{candidate.get('label')}` (`{candidate.get('assignment_type')}`)",
                f"- material/feature: `{candidate.get('material_id')}` / `{candidate.get('feature')}`",
                f"- two_theta_window_deg: `{_xrd_review_value(candidate.get('two_theta_window_deg'))}`",
                f"- d_spacing_window_angstrom: `{_xrd_review_value(candidate.get('d_spacing_window_angstrom'))}`",
                f"- matched_peak_ids: `{_xrd_review_value(candidate.get('matched_peak_ids'))}`",
                f"- matched_two_theta_deg: `{_xrd_review_value(candidate.get('matched_two_theta_deg'))}`",
                f"- matched_d_spacing_angstrom: `{_xrd_review_value(candidate.get('matched_d_spacing_angstrom'))}`",
                f"- references: `{_xrd_review_value(candidate.get('reference_ids'))}`",
                f"- unresolved_references: `{_xrd_review_value(candidate.get('unresolved_reference_ids'))}`",
                f"- confidence: `{candidate.get('confidence')}`",
                f"- source_summary: {candidate.get('source_summary')}",
                f"- applicability_notes: {_xrd_review_value(candidate.get('applicability_notes'))}",
                f"- caveats: {_xrd_review_value(candidate.get('caveats'))}",
                f"- recommended_action: {candidate.get('recommended_action')}",
                "",
            ]
        )
    commands = package.get("recommended_commands") or {}
    lines.extend(["## Suggested Commands"])
    for name, command in commands.items():
        lines.append(f"- {name}: `{command}`")
    lines.extend(["", "## Boundaries"])
    for boundary in package.get("boundaries", []):
        lines.append(f"- {boundary}")
    lines.append("")
    return "\n".join(lines)


def prepare_xrd_assignment_review_package(
    root: Path,
    *,
    project_id: str,
    suggestion_path: Path,
    candidate_ids: list[str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    resolved_suggestion_path = suggestion_path if suggestion_path.is_absolute() else root / suggestion_path
    suggestion = read_yaml(resolved_suggestion_path)
    if suggestion.get("source") != "ea.xrd.assignment_suggestions:v0.2":
        raise XRDProcessingError(f"Not an XRD assignment suggestion record: {suggestion_path}")

    suggestion_ref = _relative_to_root(root, resolved_suggestion_path)
    suggestion_project_id = str(suggestion.get("project_id") or "")
    if suggestion_project_id and project_id and suggestion_project_id != project_id:
        raise XRDProcessingError(f"Project ID mismatch: suggestion has {suggestion_project_id}, request has {project_id}")

    candidates = [candidate for candidate in suggestion.get("candidates", []) if isinstance(candidate, dict)]
    requested_ids = [str(candidate_id) for candidate_id in candidate_ids or [] if str(candidate_id).strip()]
    requested_set = set(requested_ids)
    selected = [candidate for candidate in candidates if not requested_set or str(candidate.get("candidate_id")) in requested_set]
    found_ids = {str(candidate.get("candidate_id")) for candidate in selected}
    missing_candidate_ids = [candidate_id for candidate_id in requested_ids if candidate_id not in found_ids]
    warnings: list[dict[str, Any]] = [
        _warning(
            "xrd_review_package_candidate_not_found",
            "A requested XRD assignment suggestion candidate_id was not found in the suggestion record.",
            severity="medium",
            candidate_id=candidate_id,
        )
        for candidate_id in missing_candidate_ids
    ]

    summaries = [_xrd_review_candidate_summary(candidate) for candidate in selected]
    group_actions = {
        "ready_for_user_review": "Review these candidates with the user; create a ReviewRecord only after explicit confirmation.",
        "needs_reference_registration": "Resolve references first with `ea references register-seeds` or `ea references add`, then regenerate suggestions or review with caveats.",
        "no_feature_match": "Treat as no-match context unless peak detection, source windows, or sample context changes.",
        "invalid_or_incomplete": "Fix candidate metadata before asking the user to review.",
        "other": "Inspect manually before downstream use.",
    }
    groups = []
    for group_name in ["ready_for_user_review", "needs_reference_registration", "no_feature_match", "invalid_or_incomplete", "other"]:
        ids = [summary["candidate_id"] for summary in summaries if summary["review_group"] == group_name]
        if ids:
            groups.append({"group": group_name, "candidate_ids": ids, "recommended_action": group_actions[group_name]})

    package_dir = resolved_suggestion_path.parent
    package_path = package_dir / "review_package.yml"
    markdown_path = package_dir / "review_package.md"
    for path in [package_path, markdown_path]:
        assert_not_raw_output_path(root, path)
    package_ref = _relative_to_root(root, package_path)
    markdown_ref = _relative_to_root(root, markdown_path)
    timestamp = created_at or EARecord.now_iso()
    package_id = f"{suggestion.get('suggestion_id') or package_dir.name}-review-package"
    xrd_metadata_ref = suggestion.get("xrd_metadata_ref") or "<xrd_metadata.yml>"
    source_packet_ref = suggestion.get("source_packet_ref") or "<xrd_assignment_source_packet.yml>"
    package: dict[str, Any] = {
        "schema_version": "0.2",
        "review_package_id": package_id,
        "project_id": project_id or suggestion_project_id,
        "method": "xrd",
        "source": "ea.xrd.assignment_review_package:v0.2",
        "status": "review_package_prepared" if selected else "no_candidates_selected",
        "created_at": timestamp,
        "updated_at": timestamp,
        "suggestion_id": suggestion.get("suggestion_id"),
        "suggestion_ref": suggestion_ref,
        "table_ref": suggestion.get("table_ref"),
        "source_packet_ref": suggestion.get("source_packet_ref"),
        "xrd_metadata_ref": suggestion.get("xrd_metadata_ref"),
        "peak_table_ref": suggestion.get("peak_table_ref"),
        "related_records": suggestion.get("related_records") or [],
        "review_target_type": "xrd_assignment_suggestions",
        "review_target_ref": suggestion_ref,
        "candidate_count": len(candidates),
        "selected_candidate_count": len(selected),
        "requested_candidate_ids": requested_ids,
        "missing_candidate_ids": missing_candidate_ids,
        "overall_status_counts": _xrd_review_status_counts(candidates),
        "selected_status_counts": _xrd_review_status_counts(selected),
        "groups": groups,
        "candidate_summaries": summaries,
        "reference_ids": sorted({ref for candidate in summaries for ref in candidate.get("reference_ids", [])}),
        "unresolved_reference_ids": sorted({ref for candidate in summaries for ref in candidate.get("unresolved_reference_ids", [])}),
        "recommended_commands": {
            "create_review_record": (
                "ea review add /path/to/ea-project --target-type xrd_assignment_suggestions "
                f"--target-ref {suggestion_ref} --user-response \"可以，保存\" "
                "--reviewed-content \"User reviewed the listed XRD assignment candidates; record accepted/rejected/edited candidate IDs.\""
            ),
            "rerun_after_reference_registration": (
                "ea xrd suggest-assignments /path/to/ea-project "
                f"--metadata {xrd_metadata_ref} --source-file {source_packet_ref}"
            ),
        },
        "next_steps": [
            "Ask the user to review ready candidates and state which candidate IDs are accepted, rejected, edited, or deferred.",
            "Resolve unresolved references before using candidates as report evidence unless future report integration explicitly discusses them as unresolved.",
            "Keep the confirmed ReviewRecord with this suggestion record; XRD report and memory integration for assignment suggestions must be implemented in separate reviewed phases.",
        ],
        "boundaries": [
            "This package prepares review context only; it does not create a ReviewRecord.",
            "It does not apply XRD assignments, change processing outputs or source packets, inject report citations, write confirmed memory, or prove phase/material/crystallinity/texture/strain/lattice/sample-quality claims.",
            "Unresolved, no-match, or invalid candidates remain visible so the user can decide whether to fix, exclude, or discuss them with caveats.",
        ],
        "warnings": warnings,
    }
    write_yaml(package_path, package)
    markdown_path.write_text(_render_xrd_review_package_markdown(package), encoding="utf-8")
    provenance_path = write_provenance_entry(
        root,
        workflow="xrd_assignment_review_package",
        inputs={"records": [suggestion_ref], "files": []},
        outputs={"records": [package_ref, markdown_ref], "files": []},
        parameters={
            "suggestion_id": suggestion.get("suggestion_id"),
            "requested_candidate_ids": requested_ids,
            "selected_candidate_count": len(selected),
            "auto_applied": False,
        },
        warnings=warnings,
        source_refs=package["reference_ids"],
        created_at=created_at,
    )
    package["provenance_ref"] = _relative_to_root(root, provenance_path)
    write_yaml(package_path, package)
    markdown_path.write_text(_render_xrd_review_package_markdown(package), encoding="utf-8")
    return {
        "status": package["status"],
        "review_package": str(package_path),
        "review_package_markdown": str(markdown_path),
        "review_package_ref": package_ref,
        "review_package_markdown_ref": markdown_ref,
        "suggestion_id": suggestion.get("suggestion_id"),
        "suggestion_ref": suggestion_ref,
        "candidate_count": len(candidates),
        "selected_candidate_count": len(selected),
        "selected_status_counts": package["selected_status_counts"],
        "missing_candidate_ids": missing_candidate_ids,
        "provenance": str(provenance_path),
        "warnings": warnings,
    }


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
    peak_analysis = _analyze_xrd_peaks(peaks, root, project_id)
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
