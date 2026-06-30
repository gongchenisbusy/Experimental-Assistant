from __future__ import annotations

from pathlib import Path
from typing import Any

from ea.storage.files import read_yaml, write_yaml


class FigureLookupError(KeyError):
    pass


def figure_footer(figure_id: str, report_id: str | None) -> str:
    return f"FigID: {figure_id} | Report: {report_id or 'pending'}"


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
