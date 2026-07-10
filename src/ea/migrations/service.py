from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import shutil
from typing import Any

from ea.identity import PROJECT_FORMAT_VERSION
from ea.storage.files import atomic_copy_file, read_yaml, write_yaml
from ea.storage.transactions import OperationJournal


CURRENT_PROJECT_FORMAT_VERSION = PROJECT_FORMAT_VERSION
LEGACY_PROJECT_FORMAT_VERSION = "0.9"
FORMAT_PATH = Path(".ea/project_format.yml")
BACKUP_CANDIDATES = (
    Path("EA_PROJECT.md"),
    Path("PROJECT_RULE_CARD.md"),
    Path(".ea/project_config.yml"),
    Path(".ea/id_counters.yml"),
    Path("memory/project-working-memory.md"),
    Path("literature/deployment_status.yml"),
)


def _now_iso(value: str | None = None) -> str:
    return value or datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _detected_version(root: Path) -> tuple[str | None, str]:
    format_path = root / FORMAT_PATH
    if format_path.exists():
        record = read_yaml(format_path)
        return str(record.get("project_format_version") or "unknown"), "explicit"
    if (root / "EA_PROJECT.md").exists() or (root / ".ea/project_config.yml").exists():
        return LEGACY_PROJECT_FORMAT_VERSION, "legacy_inferred"
    return None, "not_a_project"


def project_format_status(root: Path) -> dict[str, Any]:
    detected, source = _detected_version(root)
    supported = detected in {LEGACY_PROJECT_FORMAT_VERSION, CURRENT_PROJECT_FORMAT_VERSION}
    return {
        "schema_version": "1.0",
        "status": "pass" if supported else "missing" if detected is None else "unsupported",
        "workspace": str(root),
        "detected_project_format_version": detected,
        "detection_source": source,
        "current_project_format_version": CURRENT_PROJECT_FORMAT_VERSION,
        "migration_required": detected == LEGACY_PROJECT_FORMAT_VERSION,
        "read_only": True,
    }


def initialize_project_format(root: Path, *, created_at: str | None = None) -> Path:
    created = _now_iso(created_at)
    return write_yaml(
        root / FORMAT_PATH,
        {
            "schema_version": "1.0",
            "project_format_version": CURRENT_PROJECT_FORMAT_VERSION,
            "created_with_ea": "0.9.7",
            "created_at": created,
            "updated_at": created,
            "migration_history": [],
        },
    )


def plan_project_migration(root: Path, *, target_version: str = CURRENT_PROJECT_FORMAT_VERSION) -> dict[str, Any]:
    status = project_format_status(root)
    source_version = status["detected_project_format_version"]
    if source_version is None:
        raise FileNotFoundError(f"EA project was not found: {root}")
    if target_version != CURRENT_PROJECT_FORMAT_VERSION:
        raise ValueError(f"Unsupported migration target: {target_version}")
    if source_version not in {LEGACY_PROJECT_FORMAT_VERSION, CURRENT_PROJECT_FORMAT_VERSION}:
        raise ValueError(f"Unsupported source project format: {source_version}")
    already_current = source_version == target_version
    backup_files = [str(path) for path in BACKUP_CANDIDATES if (root / path).is_file()]
    return {
        "schema_version": "1.0",
        "status": "already_current" if already_current else "ready",
        "workspace": str(root),
        "source_version": source_version,
        "target_version": target_version,
        "read_only": True,
        "writes": [] if already_current else [str(FORMAT_PATH), ".ea/migrations/history/<migration-id>.yml"],
        "backup_files": backup_files,
        "raw_data_copied": False,
        "reversible": True,
    }


def apply_project_migration(
    root: Path,
    *,
    target_version: str = CURRENT_PROJECT_FORMAT_VERSION,
    confirmed: bool = False,
    created_at: str | None = None,
) -> dict[str, Any]:
    plan = plan_project_migration(root, target_version=target_version)
    if plan["status"] == "already_current":
        return {**plan, "status": "already_current", "artifacts_written": []}
    if not confirmed:
        raise PermissionError("Migration requires explicit confirmation; inspect `ea migrate plan` first.")

    created = _now_iso(created_at)
    stamp = created.replace("-", "").replace(":", "").replace("+", "").replace(".", "")[:15]
    migration_id = f"migration-{plan['source_version']}-to-{target_version}-{stamp}"
    backup_root = root / ".ea" / "migrations" / "backups" / migration_id
    history_path = root / ".ea" / "migrations" / "history" / f"{migration_id}.yml"
    expected = [str(FORMAT_PATH), history_path.relative_to(root).as_posix()]
    artifacts: list[str] = []

    with OperationJournal(root, migration_id, "project_format_migration", expected_outputs=expected) as journal:
        manifest_files: list[dict[str, Any]] = []
        for relative in BACKUP_CANDIDATES:
            source = root / relative
            if not source.is_file():
                continue
            destination = backup_root / relative
            atomic_copy_file(source, destination)
            manifest_files.append(
                {
                    "path": str(relative),
                    "backup_path": destination.relative_to(root).as_posix(),
                    "sha256": _sha256(source),
                }
            )
        manifest_path = backup_root / "manifest.yml"
        write_yaml(
            manifest_path,
            {
                "schema_version": "1.0",
                "migration_id": migration_id,
                "source_version": plan["source_version"],
                "target_version": target_version,
                "created_at": created,
                "files": manifest_files,
                "raw_data_copied": False,
            },
        )
        journal.add_artifact(manifest_path.relative_to(root))
        artifacts.append(manifest_path.relative_to(root).as_posix())

        format_path = initialize_project_format(root, created_at=created)
        format_record = read_yaml(format_path)
        format_record["migrated_from"] = plan["source_version"]
        format_record["migration_history"] = [migration_id]
        write_yaml(format_path, format_record)
        journal.add_artifact(format_path.relative_to(root))
        artifacts.append(format_path.relative_to(root).as_posix())

        history = {
            "schema_version": "1.0",
            "migration_id": migration_id,
            "status": "completed",
            "source_version": plan["source_version"],
            "target_version": target_version,
            "backup_manifest": manifest_path.relative_to(root).as_posix(),
            "created_at": created,
            "raw_data_copied": False,
        }
        write_yaml(history_path, history)
        journal.add_artifact(history_path.relative_to(root))
        artifacts.append(history_path.relative_to(root).as_posix())

    return {
        **plan,
        "status": "completed",
        "migration_id": migration_id,
        "backup_manifest": manifest_path.relative_to(root).as_posix(),
        "artifacts_written": artifacts,
    }


def rollback_project_migration(
    root: Path,
    *,
    migration_id: str,
    confirmed: bool = False,
    created_at: str | None = None,
) -> dict[str, Any]:
    if not confirmed:
        raise PermissionError("Rollback requires explicit confirmation.")
    manifest_path = root / ".ea" / "migrations" / "backups" / migration_id / "manifest.yml"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Migration backup manifest was not found: {manifest_path}")
    manifest = read_yaml(manifest_path)
    restored: list[str] = []
    operation_id = f"rollback-{migration_id}"
    with OperationJournal(root, operation_id, "project_format_rollback") as journal:
        for item in manifest.get("files", []):
            relative = Path(item["path"])
            backup = root / item["backup_path"]
            destination = root / relative
            atomic_copy_file(backup, destination)
            if _sha256(destination) != item["sha256"]:
                raise RuntimeError(f"Restored file hash mismatch: {relative}")
            journal.add_artifact(relative)
            restored.append(str(relative))
        format_path = root / FORMAT_PATH
        if manifest.get("source_version") == LEGACY_PROJECT_FORMAT_VERSION and format_path.exists():
            format_path.unlink()
        rollback_path = root / ".ea" / "migrations" / "history" / f"{operation_id}.yml"
        write_yaml(
            rollback_path,
            {
                "schema_version": "1.0",
                "operation_id": operation_id,
                "status": "completed",
                "migration_id": migration_id,
                "restored": restored,
                "created_at": _now_iso(created_at),
            },
        )
        journal.add_artifact(rollback_path.relative_to(root))
    return {
        "schema_version": "1.0",
        "status": "completed",
        "operation_id": operation_id,
        "restored": restored,
        "detected_project_format_version": project_format_status(root)["detected_project_format_version"],
    }
