from __future__ import annotations

import json
from pathlib import Path

import pytest

from ea.cli import main
from ea.diagnostics import collect_diagnostics
from ea.projects import initialize_project
from ea.storage import write_yaml


def _project(root: Path) -> None:
    initialize_project(
        root,
        project_name="Diagnostics project",
        project_slug="diagnostics-project",
        research_direction="privacy diagnostics",
        material_system="MoS2",
        experiment_type="Raman",
    )


def test_diagnostics_is_compact_redacted_and_never_submits(tmp_path: Path, capsys) -> None:
    _project(tmp_path)
    logs = tmp_path / "logs"
    logs.mkdir()
    selected = logs / "selected.log"
    selected.write_text(
        "token=ghp_1234567890abcdefghijklmnopQRSTUV\n"
        "session_id=private-session\n"
        "profile=/Users/private/Chrome/Profile\n"
        "url=https://publisher.test/paper?X-Amz-Signature=secret&token=private\n"
        "contact=private@example.org\n",
        encoding="utf-8",
    )
    write_yaml(
        tmp_path / ".ea" / "operations" / "failed.yml",
        {"operation": "test", "status": "failed", "error": {"type": "TimeoutError", "message": "/Users/private/secret"}},
    )
    output = Path("exports/diagnostics/ea-diagnostics.json")

    assert (
        main(
            [
                "diagnostics",
                "collect",
                str(tmp_path),
                "--output",
                str(output),
                "--log",
                str(selected),
                "--debug-json",
            ]
        )
        == 0
    )
    stdout = capsys.readouterr().out
    summary = json.loads(stdout)
    artifact = (tmp_path / output).read_text(encoding="utf-8")

    assert len(stdout.encode("utf-8")) < 4096
    assert summary["failed_operation_count"] == 1
    assert summary["submission_performed"] is False
    assert summary["context_cost_proxy"]["exact_model_tokens_available"] is False
    assert summary["diagnostics_ref"] == output.as_posix()
    for secret in ("ghp_", "private-session", "/Users/private", "X-Amz-Signature", "private@example.org"):
        assert secret not in artifact
        assert secret not in stdout
    payload = json.loads(artifact)
    assert payload["submission"]["performed"] is False
    assert payload["selected_logs"][0]["redacted_excerpt"]
    assert "raw research data" in payload["exclusions"]


def test_debug_requires_local_artifact_and_sensitive_paths_are_refused(tmp_path: Path) -> None:
    _project(tmp_path)
    raw_log = tmp_path / "raw" / "private.txt"
    raw_log.write_text("private research value", encoding="utf-8")

    with pytest.raises(ValueError, match="requires an explicit"):
        collect_diagnostics(tmp_path, debug_json=True)
    with pytest.raises(PermissionError, match="refuses"):
        collect_diagnostics(tmp_path, selected_logs=[raw_log])


def test_default_diagnostics_is_read_only(tmp_path: Path) -> None:
    _project(tmp_path)
    before = {path.relative_to(tmp_path).as_posix(): path.stat().st_mtime_ns for path in tmp_path.rglob("*") if path.is_file()}

    result = collect_diagnostics(tmp_path)

    after = {path.relative_to(tmp_path).as_posix(): path.stat().st_mtime_ns for path in tmp_path.rglob("*") if path.is_file()}
    assert result["diagnostics_ref"] is None
    assert before == after
