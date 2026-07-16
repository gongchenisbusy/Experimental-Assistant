from __future__ import annotations

import json
import os
from pathlib import Path
import time

import pytest
import yaml

from ea.cli import main
from ea.errors import error_record
from ea.migrations import (
    apply_project_migration,
    plan_project_migration,
    project_format_status,
    rollback_project_migration,
)
from ea.projects import initialize_project
from ea.storage import atomic_write_text, next_id, read_yaml
from ea.storage.transactions import OperationJournal


def _legacy_project(root: Path) -> None:
    initialize_project(
        root,
        project_name="Legacy project",
        research_direction="migration test",
        material_system="MoS2",
        experiment_type="Raman",
        created_at="2026-07-10T10:00:00+00:00",
    )
    (root / ".ea" / "project_format.yml").unlink()


def test_atomic_write_keeps_previous_file_when_replace_fails(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "state.yml"
    target.write_text("old\n", encoding="utf-8")

    def fail_replace(source, destination):
        raise OSError("injected replace failure")

    monkeypatch.setattr("ea.storage.files.os.replace", fail_replace)

    with pytest.raises(OSError, match="injected replace failure"):
        atomic_write_text(target, "new\n")

    assert target.read_text(encoding="utf-8") == "old\n"
    assert list(tmp_path.glob(".state.yml.*.tmp")) == []


def test_migration_plan_is_read_only_and_legacy_project_remains_unchanged(tmp_path: Path) -> None:
    _legacy_project(tmp_path)
    before = (tmp_path / "EA_PROJECT.md").read_bytes()

    plan = plan_project_migration(tmp_path)

    assert plan["status"] == "ready"
    assert plan["source_version"] == "0.9"
    assert plan["target_version"] == "1.0"
    assert plan["read_only"] is True
    assert plan["raw_data_copied"] is False
    assert not (tmp_path / ".ea" / "project_format.yml").exists()
    assert (tmp_path / "EA_PROJECT.md").read_bytes() == before


@pytest.mark.parametrize("created_with_ea", ["0.9.7", "0.9.8", "0.9.9"])
def test_v0_9_x_current_format_projects_open_read_only_without_identity_rewrite(
    tmp_path: Path, created_with_ea: str
) -> None:
    initialize_project(
        tmp_path,
        project_name=f"Historical {created_with_ea}",
        research_direction="compatibility",
        material_system="MoS2",
        experiment_type="Raman",
        created_at="2026-07-10T10:00:00+00:00",
    )
    format_path = tmp_path / ".ea" / "project_format.yml"
    project_format = read_yaml(format_path)
    project_format["created_with_ea"] = created_with_ea
    format_path.write_text(
        yaml.safe_dump(project_format, sort_keys=False), encoding="utf-8"
    )
    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    status = project_format_status(tmp_path)
    plan = plan_project_migration(tmp_path)

    assert status["status"] == "pass"
    assert status["detected_project_format_version"] == "1.0"
    assert plan["status"] == "already_current"
    assert read_yaml(format_path)["created_with_ea"] == created_with_ea
    after = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_migration_apply_is_idempotent_and_rollback_restores_legacy_detection(tmp_path: Path) -> None:
    _legacy_project(tmp_path)

    applied = apply_project_migration(
        tmp_path,
        confirmed=True,
        created_at="2026-07-10T11:00:00+00:00",
    )

    assert applied["status"] == "completed"
    assert project_format_status(tmp_path)["detected_project_format_version"] == "1.0"
    assert read_yaml(tmp_path / applied["backup_manifest"])["raw_data_copied"] is False

    repeated = apply_project_migration(tmp_path, confirmed=True)
    assert repeated["status"] == "already_current"
    assert repeated["artifacts_written"] == []

    rolled_back = rollback_project_migration(
        tmp_path,
        migration_id=applied["migration_id"],
        confirmed=True,
        created_at="2026-07-10T12:00:00+00:00",
    )
    assert rolled_back["status"] == "completed"
    assert rolled_back["detected_project_format_version"] == "0.9"
    assert not (tmp_path / ".ea" / "project_format.yml").exists()


def test_operation_journal_records_failure_and_written_artifacts(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="injected"):
        with OperationJournal(tmp_path, "operation-001", "test", expected_outputs=["result.yml"]) as journal:
            journal.add_artifact("partial.yml")
            raise RuntimeError("injected")

    record = read_yaml(tmp_path / ".ea" / "operations" / "operation-001.yml")
    assert record["status"] == "failed"
    assert record["artifacts_written"] == ["partial.yml"]
    assert record["error"]["type"] == "RuntimeError"


def test_next_id_recovers_dead_stale_lock(tmp_path: Path) -> None:
    lock = tmp_path / ".ea" / "id_counters.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text(
        json.dumps({"pid": 99999999, "hostname": "", "created_at": "2020-01-01T00:00:00+00:00"}),
        encoding="utf-8",
    )
    old = time.time() - 120
    os.utime(lock, (old, old))

    assert next_id(tmp_path, "review", "2026-07-10") == "review-20260710-001"
    assert not lock.exists()


def test_migration_cli_plan_is_read_only_and_requires_confirmation(tmp_path: Path, capsys) -> None:
    _legacy_project(tmp_path)

    assert main(["migrate", "plan", str(tmp_path)]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["status"] == "ready"
    assert not (tmp_path / ".ea" / "project_format.yml").exists()

    assert main(["migrate", "apply", str(tmp_path)]) == 2
    error = json.loads(capsys.readouterr().out)
    assert error["code"] == "EA-IO-PERMISSION-DENIED"
    assert error["artifacts_written"] == []


def test_error_record_distinguishes_directory_and_connection_failures() -> None:
    directory = error_record(IsADirectoryError("cache path is a directory"))
    refused = error_record(ConnectionRefusedError("Zotero refused connection"))

    assert directory["code"] == "EA-IO-PATH-NOT-FILE"
    assert refused["code"] == "EA-INTEGRATION-CONNECTION-REFUSED"
    assert refused["safe_to_retry"] is True
