from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path
from typing import Any

from ea.storage.files import read_yaml, write_yaml


class FigureLookupError(KeyError):
    pass


def figure_footer(figure_id: str, report_id: str | None) -> str:
    """Return the one final footer, or an empty footer for a processing-stage base."""
    if report_id is None:
        return ""
    return f"FigID: {figure_id} | Report: {report_id}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_data_entry(
    root: Path,
    ref: str,
    *,
    role: str,
    purpose: str,
    primary: bool = False,
    columns: list[str] | None = None,
) -> dict[str, Any]:
    """Build an explicit, public-safe source-data record for a figure."""
    path = root / ref
    detected_columns = list(columns or [])
    if columns is None and path.suffix.lower() in {".csv", ".tsv"} and path.is_file():
        import pandas as pd

        separator = "\t" if path.suffix.lower() == ".tsv" else ","
        detected_columns = [
            str(value) for value in pd.read_csv(path, sep=separator, nrows=0).columns
        ]
    return {
        "ref": ref,
        "role": role,
        "purpose": purpose,
        "columns": detected_columns,
        "primary": primary,
        "protected_raw": False,
    }


def _index_path(root: Path) -> Path:
    return root / "figures" / "index.yml"


def _safe_report_slug(report_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", report_id).strip("-") or "report"


FOOTER_HTML_CONTENT_WIDTH_CSS_PX = 932
FOOTER_MIN_EFFECTIVE_CSS_PX = 12.0
FOOTER_TARGET_EFFECTIVE_CSS_PX = 13.0


def _wrap_footer_text(draw, text: str, font, max_width: int) -> str:
    tokens = text.split(" ")
    lines: list[str] = []
    current = ""
    for token in tokens:
        candidate = token if not current else f"{current} {token}"
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
            current = ""
        token_bbox = draw.textbbox((0, 0), token, font=font)
        if token_bbox[2] - token_bbox[0] <= max_width:
            current = token
            continue
        chunk = ""
        for character in token:
            candidate_chunk = chunk + character
            chunk_bbox = draw.textbbox((0, 0), candidate_chunk, font=font)
            if chunk and chunk_bbox[2] - chunk_bbox[0] > max_width:
                lines.append(chunk)
                chunk = character
            else:
                chunk = candidate_chunk
        current = chunk
    if current:
        lines.append(current)
    return "\n".join(lines)


def _render_report_bound_png(
    root: Path, record: dict[str, Any], report_id: str
) -> dict[str, Any] | None:
    base_ref = str(record.get("base_path") or "")
    base_path = root / base_ref
    if base_path.suffix.lower() != ".png" or not base_path.is_file():
        return None
    try:
        from PIL import Image, ImageDraw, ImageFont, PngImagePlugin
        from matplotlib import font_manager
    except Exception:  # pragma: no cover - Pillow is normally available via matplotlib
        return None

    footer = figure_footer(str(record["figure_id"]), report_id)
    final_path = base_path.with_name(
        f"{base_path.stem}--{_safe_report_slug(report_id)}.png"
    )
    with Image.open(base_path) as source:
        base = source.convert("RGB")
        display_scale = min(1.0, FOOTER_HTML_CONTENT_WIDTH_CSS_PX / base.width)
        font_px = max(
            16,
            math.ceil(FOOTER_TARGET_EFFECTIVE_CSS_PX / display_scale),
        )
        font_path = Path(font_manager.findfont("DejaVu Sans", fallback_to_default=True))
        font = ImageFont.truetype(str(font_path), size=font_px)
        measure = ImageDraw.Draw(base)
        padding_x = max(12, math.ceil(base.width * 0.012))
        padding_y = max(8, math.ceil(font_px * 0.45))
        wrapped_footer = _wrap_footer_text(
            measure, footer, font, max(1, base.width - padding_x * 2)
        )
        line_spacing = max(3, math.ceil(font_px * 0.22))
        bbox = measure.multiline_textbbox(
            (0, 0), wrapped_footer, font=font, spacing=line_spacing
        )
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        strip_height = text_height + padding_y * 2
        canvas = Image.new("RGB", (base.width, base.height + strip_height), "white")
        canvas.paste(base, (0, 0))
        draw = ImageDraw.Draw(canvas)
        text_x = canvas.width - text_width - padding_x
        text_y = canvas.height - text_height - padding_y
        footer_clipped = not (
            0 <= text_x
            and text_x + text_width <= canvas.width
            and base.height <= text_y
            and text_y + text_height <= canvas.height
        )
        draw.multiline_text(
            (text_x, text_y),
            wrapped_footer,
            font=font,
            fill=(32, 32, 32),
            spacing=line_spacing,
            align="right",
        )
        effective_css_px = font_px * display_scale
        pnginfo = PngImagePlugin.PngInfo()
        pnginfo.add_text("ea_footer", footer)
        pnginfo.add_text("ea_figure_id", str(record["figure_id"]))
        pnginfo.add_text("ea_report_id", report_id)
        pnginfo.add_text("ea_footer_font_px", str(font_px))
        pnginfo.add_text("ea_footer_effective_css_px", f"{effective_css_px:.3f}")
        pnginfo.add_text(
            "ea_footer_min_effective_css_px",
            f"{FOOTER_MIN_EFFECTIVE_CSS_PX:.1f}",
        )
        pnginfo.add_text(
            "ea_footer_html_content_width_css_px",
            str(FOOTER_HTML_CONTENT_WIDTH_CSS_PX),
        )
        pnginfo.add_text("ea_footer_font", font_path.name)
        pnginfo.add_text("ea_footer_font_sha256", _sha256(font_path))
        pnginfo.add_text("ea_footer_contrast", "#202020-on-#ffffff")
        pnginfo.add_text("ea_footer_contrast_ratio", "16.29")
        pnginfo.add_text("ea_footer_line_count", str(len(wrapped_footer.splitlines())))
        pnginfo.add_text("ea_footer_base_width_px", str(base.width))
        pnginfo.add_text("ea_footer_base_height_px", str(base.height))
        pnginfo.add_text("ea_footer_strip_height_px", str(strip_height))
        pnginfo.add_text(
            "ea_footer_text_bbox_px",
            f"{text_x},{text_y},{text_x + text_width},{text_y + text_height}",
        )
        pnginfo.add_text("ea_footer_clipped", str(footer_clipped).lower())
        final_path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(
            final_path, format="PNG", pnginfo=pnginfo, compress_level=9, optimize=False
        )

    return {
        "path": final_path.relative_to(root).as_posix(),
        "sha256": _sha256(final_path),
        "footer": footer,
        "base_path": base_ref,
        "base_sha256": record.get("base_sha256"),
        "render_policy": "footer_free_base_to_report_bound_final_v1",
        "footer_contract_version": "2.0",
        "footer_font_px": font_px,
        "footer_effective_css_px": effective_css_px,
        "footer_min_effective_css_px": FOOTER_MIN_EFFECTIVE_CSS_PX,
        "footer_html_content_width_css_px": FOOTER_HTML_CONTENT_WIDTH_CSS_PX,
        "footer_font": font_path.name,
        "footer_font_sha256": _sha256(font_path),
        "footer_line_count": len(wrapped_footer.splitlines()),
        "footer_text_bbox_px": [
            text_x,
            text_y,
            text_x + text_width,
            text_y + text_height,
        ],
        "footer_strip_height_px": strip_height,
        "footer_contrast_ratio": 16.29,
        "footer_clipped": footer_clipped,
    }


def register_figure(
    root: Path,
    *,
    figure_id: str,
    path: str,
    report_id: str | None,
    result_id: str | None,
    raw_data_ids: list[str],
    sample_ids: list[str],
    experiment_ids: list[str] | None = None,
    generation: dict[str, Any] | None = None,
    caption: str | None = None,
    purpose: str | None = None,
    style_profile: str | None = None,
    source_data_refs: list[str] | None = None,
    source_data: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    index_path = _index_path(root)
    index = (
        read_yaml(index_path)
        if index_path.exists()
        else {"schema_version": "0.3", "figures": {}}
    )
    index["schema_version"] = "0.3"
    explicit_source_data = list(source_data or [])
    legacy_refs = list(
        source_data_refs
        or [str(item.get("ref")) for item in explicit_source_data if item.get("ref")]
    )
    if not explicit_source_data:
        explicit_source_data = [
            {
                "ref": ref,
                "role": "legacy_unspecified",
                "purpose": "Legacy source-data reference; classify before the next report export.",
                "columns": [],
                "primary": index == 0,
                "protected_raw": False,
            }
            for index, ref in enumerate(legacy_refs)
        ]
    base_path = root / path
    record: dict[str, Any] = {
        "figure_id": figure_id,
        "path": path,
        "base_path": path,
        "base_sha256": _sha256(base_path) if base_path.is_file() else None,
        "render_policy": "footer_free_base_to_report_bound_final_v1",
        "report_id": None,
        "result_id": result_id,
        "raw_data_ids": raw_data_ids,
        "sample_ids": sample_ids,
        "experiment_ids": experiment_ids or [],
        "generation": generation or {},
        "caption": caption,
        "purpose": purpose,
        "style_profile": style_profile,
        "source_data_refs": legacy_refs,
        "source_data": explicit_source_data,
        "footer": None,
        "renderings": {},
    }
    if report_id:
        rendering = _render_report_bound_png(root, record, report_id)
        record["report_id"] = report_id
        record["footer"] = figure_footer(figure_id, report_id)
        if rendering:
            record["renderings"][report_id] = rendering
            record["path"] = rendering["path"]
    index.setdefault("figures", {})[figure_id] = record
    write_yaml(index_path, index)
    return record


def update_figure_report_ref(
    root: Path, figure_id: str, report_id: str
) -> dict[str, Any]:
    index_path = _index_path(root)
    if not index_path.exists():
        raise FigureLookupError(f"Figure index is missing: {index_path}")
    index = read_yaml(index_path)
    try:
        record = index["figures"][figure_id]
    except KeyError as exc:
        raise FigureLookupError(f"Unknown figure_id: {figure_id}") from exc

    if record.get(
        "render_policy"
    ) != "footer_free_base_to_report_bound_final_v1" or not record.get("base_path"):
        legacy_path = root / str(record.get("path") or "")
        record["upgrade_plan"] = {
            "status": "explicit_rerender_required",
            "reason": "legacy_figure_preserved_without_automatic_raster_rewrite",
            "requested_report_id": report_id,
            "legacy_path": str(record.get("path") or ""),
            "legacy_sha256": _sha256(legacy_path) if legacy_path.is_file() else None,
            "next_action": "Re-run the originating analysis to create a footer-free current-format base figure.",
        }
        write_yaml(index_path, index)
        return record

    rendering = _render_report_bound_png(root, record, report_id)
    record["report_id"] = report_id
    record["footer"] = figure_footer(figure_id, report_id)
    if rendering:
        record.setdefault("renderings", {})[report_id] = rendering
        record["path"] = rendering["path"]
    else:
        record["render_warning"] = "report_bound_render_not_created"
    write_yaml(index_path, index)
    return record


def figure_path_for_report(record: dict[str, Any], report_id: str | None) -> str:
    if report_id:
        rendering = (record.get("renderings") or {}).get(report_id) or {}
        if rendering.get("path"):
            return str(rendering["path"])
    return str(record.get("path") or record.get("base_path") or "")


def lookup_figure(root: Path, figure_id: str) -> dict[str, Any]:
    index_path = _index_path(root)
    if not index_path.exists():
        raise FigureLookupError(f"Figure index is missing: {index_path}")
    index = read_yaml(index_path)
    try:
        return index["figures"][figure_id]
    except KeyError as exc:
        raise FigureLookupError(f"Unknown figure_id: {figure_id}") from exc
