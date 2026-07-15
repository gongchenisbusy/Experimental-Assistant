from __future__ import annotations

from pathlib import Path
from typing import Any

from ea.storage.files import read_markdown_record, read_yaml


def _yaml_records(root: Path, pattern: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(root.glob(pattern)):
        if not path.is_file():
            continue
        try:
            payload = read_yaml(path)
        except (OSError, ValueError):
            continue
        records.append({"path": path.relative_to(root).as_posix(), **payload})
    return records


def aggregate_project_state(root: Path) -> dict[str, Any]:
    """Read shared project state once for dashboard and decision-oriented brief views."""
    root = root.expanduser().resolve()
    project_path = root / "EA_PROJECT.md"
    if not project_path.is_file():
        raise FileNotFoundError(f"EA_PROJECT.md was not found: {project_path}")
    project, _ = read_markdown_record(project_path)
    config_path = root / ".ea" / "project_config.yml"
    config = read_yaml(config_path) if config_path.is_file() else {}
    open_items = [
        record
        for record in _yaml_records(root, "open-items/*.yml")
        if record.get("status") not in {"closed", "resolved", "archived", "done"}
    ]
    operations = _yaml_records(root, ".ea/operations/*.yml")
    incomplete_operations = [
        record
        for record in operations
        if record.get("status") in {"planned", "in_progress", "failed", "partial"}
    ]

    reports_index_path = root / "reports" / "index.yml"
    reports_index = (
        read_yaml(reports_index_path).get("reports", {})
        if reports_index_path.is_file()
        else {}
    )
    reports: list[dict[str, Any]] = []
    seen: set[str] = set()
    for report_id, record in reports_index.items():
        if not isinstance(record, dict):
            continue
        ref = str(record.get("path") or f"reports/{report_id}.md")
        seen.add(ref)
        frontmatter: dict[str, Any] = {}
        path = root / ref
        if path.is_file():
            try:
                frontmatter, _ = read_markdown_record(path)
            except (OSError, ValueError):
                pass
        reports.append(
            {
                "report_id": str(report_id),
                "path": ref,
                "report_type": frontmatter.get("report_type")
                or record.get("report_type"),
                "status": frontmatter.get("status"),
                "created_at": frontmatter.get("created_at"),
            }
        )
    for path in (root / "reports").glob("*.md"):
        ref = path.relative_to(root).as_posix()
        if ref not in seen:
            reports.append(
                {
                    "report_id": path.stem,
                    "path": ref,
                    "report_type": None,
                    "status": None,
                    "created_at": None,
                }
            )
    reports.sort(
        key=lambda item: str(item.get("created_at") or item["path"]), reverse=True
    )

    literature_status_path = root / "literature" / "deployment_status.yml"
    literature_status = (
        read_yaml(literature_status_path) if literature_status_path.is_file() else {}
    )
    external_path = root / "literature" / "external_acquisition_state.yml"
    external_acquisition = read_yaml(external_path) if external_path.is_file() else {}
    return {
        "root": root,
        "project": project,
        "config": config,
        "open_items": open_items,
        "operations": operations,
        "incomplete_operations": incomplete_operations,
        "reports": reports,
        "literature_status": literature_status,
        "external_acquisition": external_acquisition,
    }
