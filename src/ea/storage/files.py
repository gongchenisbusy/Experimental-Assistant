from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


EA_PROJECT_DIRS = [
    ".ea",
    "experiments",
    "evaluation",
    "exports",
    "exports/batch-bundles",
    "exports/report-bundles",
    "samples",
    "raw",
    "templates",
    "processed",
    "processed/batches",
    "figures",
    "reports",
    "literature",
    "literature/references",
    "skill-registry",
    "memory",
    "memory/paper-materials",
    "provenance",
    "reviews",
    "knowledge/global/literature",
    "knowledge/global/methods",
    "knowledge/global/notes",
    "knowledge/project/literature",
    "knowledge/project/fulltext",
    "knowledge/project/notes",
    "open-items",
    "suggestions",
    "progress",
    "freezes",
]


def ensure_project_dirs(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for rel in EA_PROJECT_DIRS:
        (root / rel).mkdir(parents=True, exist_ok=True)


def write_yaml(path: Path, data: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


def read_yaml(path: Path) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8")
    loaded = yaml.safe_load(content)
    return loaded or {}


def write_markdown_record(path: Path, frontmatter: dict[str, Any], body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    yaml_text = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False)
    path.write_text(f"---\n{yaml_text}---\n\n{body.strip()}\n", encoding="utf-8")
    return path


def read_markdown_record(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    _, rest = text.split("---\n", 1)
    yaml_text, body = rest.split("---\n", 1)
    return yaml.safe_load(yaml_text) or {}, body.lstrip("\n")
