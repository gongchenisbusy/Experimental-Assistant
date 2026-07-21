from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Any

import yaml


EA_PROJECT_DIRS = [
    ".ea",
    ".ea/migrations",
    ".ea/migrations/backups",
    ".ea/migrations/history",
    ".ea/operations",
    "experiments",
    "evaluation",
    "briefs",
    "exports",
    "exports/batch-bundles",
    "exports/report-bundles",
    "exports/user-reports",
    "samples",
    "raw",
    "templates",
    "processed",
    "processed/batches",
    "figures",
    "reports",
    "traceability",
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
    "drafts",
    "literature/data-extractions",
]


def ensure_project_dirs(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for rel in EA_PROJECT_DIRS:
        (root / rel).mkdir(parents=True, exist_ok=True)


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        directory_fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def atomic_write_bytes(path: Path, content: bytes, *, mode: int | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temp_path, mode)
        os.replace(temp_path, path)
        _fsync_directory(path.parent)
    except BaseException:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
        raise
    return path


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8", mode: int | None = None) -> Path:
    return atomic_write_bytes(path, content.encode(encoding), mode=mode)


def atomic_copy_file(source: Path, destination: Path) -> Path:
    source = source.expanduser()
    if not source.exists():
        raise FileNotFoundError(f"Source file does not exist: {source}")
    if not source.is_file():
        raise IsADirectoryError(f"Source path is not a file: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    temp_path = Path(temp_name)
    original_destination_mode: int | None = None
    try:
        with os.fdopen(fd, "wb") as temp_handle, source.open("rb") as source_handle:
            shutil.copyfileobj(source_handle, temp_handle, length=1024 * 1024)
            temp_handle.flush()
            os.fsync(temp_handle.fileno())
        # Apply source metadata only after the writable descriptor is closed. This
        # keeps 0400/0444 sources copyable without weakening the final artifact.
        shutil.copystat(source, temp_path)
        try:
            os.replace(temp_path, destination)
        except PermissionError:
            # Windows can reject replacement of a read-only destination. Make the
            # old target replaceable, but restore it if replacement still fails.
            if not destination.exists():
                raise
            original_destination_mode = stat.S_IMODE(destination.stat().st_mode)
            destination.chmod(original_destination_mode | stat.S_IWUSR)
            try:
                os.replace(temp_path, destination)
            except BaseException:
                destination.chmod(original_destination_mode)
                raise
        _fsync_directory(destination.parent)
    except BaseException:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
        raise
    return destination


def write_yaml(path: Path, data: dict[str, Any]) -> Path:
    return atomic_write_text(
        path,
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
    )


def read_yaml(path: Path) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8")
    loaded = yaml.safe_load(content)
    return loaded or {}


def write_markdown_record(path: Path, frontmatter: dict[str, Any], body: str) -> Path:
    yaml_text = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False)
    return atomic_write_text(path, f"---\n{yaml_text}---\n\n{body.strip()}\n")


def read_markdown_record(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    _, rest = text.split("---\n", 1)
    yaml_text, body = rest.split("---\n", 1)
    return yaml.safe_load(yaml_text) or {}, body.lstrip("\n")
