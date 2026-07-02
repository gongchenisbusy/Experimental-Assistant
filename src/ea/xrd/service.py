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
            "Use this packet as a staging input for future XRD suggestion/review/report workflows; this builder does not match peaks or apply assignments.",
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
