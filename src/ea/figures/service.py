from __future__ import annotations

from pathlib import Path
from typing import Any

from ea.storage.files import read_yaml, write_yaml


class FigureLookupError(KeyError):
    pass


def figure_footer(figure_id: str, report_id: str | None) -> str:
    return f"FigID: {figure_id} | Report: {report_id or 'pending'}"


def _rewrite_png_footer(root: Path, record: dict[str, Any], footer: str) -> None:
    figure_path = root / str(record.get("path", ""))
    if figure_path.suffix.lower() != ".png" or not figure_path.exists():
        return
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:  # pragma: no cover - Pillow is normally available via matplotlib
        return
    with Image.open(figure_path) as image:
        canvas = image.convert("RGB")
        draw = ImageDraw.Draw(canvas)
        font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), footer, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        padding_x = 8
        padding_y = 6
        strip_height = max(20, text_height + padding_y * 2)
        draw.rectangle(
            (0, canvas.height - strip_height, canvas.width, canvas.height),
            fill=(255, 255, 255),
        )
        draw.text(
            (canvas.width - text_width - padding_x, canvas.height - text_height - padding_y),
            footer,
            font=font,
            fill=(102, 102, 102),
        )
        canvas.save(figure_path)


def _index_path(root: Path) -> Path:
    return root / "figures" / "index.yml"


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
) -> dict[str, Any]:
    index_path = _index_path(root)
    index = read_yaml(index_path) if index_path.exists() else {"schema_version": "0.2", "figures": {}}
    record = {
        "figure_id": figure_id,
        "path": path,
        "report_id": report_id,
        "result_id": result_id,
        "raw_data_ids": raw_data_ids,
        "sample_ids": sample_ids,
        "experiment_ids": experiment_ids or [],
        "generation": generation or {},
        "caption": caption,
        "purpose": purpose,
        "style_profile": style_profile,
        "source_data_refs": source_data_refs or [],
        "footer": figure_footer(figure_id, report_id),
    }
    index.setdefault("figures", {})[figure_id] = record
    write_yaml(index_path, index)
    return record


def update_figure_report_ref(root: Path, figure_id: str, report_id: str) -> dict[str, Any]:
    index_path = _index_path(root)
    if not index_path.exists():
        raise FigureLookupError(f"Figure index is missing: {index_path}")
    index = read_yaml(index_path)
    try:
        record = index["figures"][figure_id]
    except KeyError as exc:
        raise FigureLookupError(f"Unknown figure_id: {figure_id}") from exc
    record["report_id"] = report_id
    record["footer"] = figure_footer(figure_id, report_id)
    _rewrite_png_footer(root, record, record["footer"])
    write_yaml(index_path, index)
    return record


def lookup_figure(root: Path, figure_id: str) -> dict[str, Any]:
    index_path = _index_path(root)
    if not index_path.exists():
        raise FigureLookupError(f"Figure index is missing: {index_path}")
    index = read_yaml(index_path)
    try:
        return index["figures"][figure_id]
    except KeyError as exc:
        raise FigureLookupError(f"Unknown figure_id: {figure_id}") from exc
