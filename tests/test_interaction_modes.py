from __future__ import annotations

import json
from pathlib import Path

from ea.cli import main
from ea.projects import initialize_project


def _project(root: Path) -> None:
    initialize_project(
        root,
        project_name="Mode project",
        project_slug="mode-project",
        research_direction="interaction mode semantics",
        material_system="MoS2",
        experiment_type="Raman",
    )


def _snapshot(root: Path) -> dict[str, tuple[int, int]]:
    return {
        path.relative_to(root).as_posix(): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file()
    }


def test_consult_status_is_zero_write_and_mutation_is_blocked(tmp_path: Path, capsys) -> None:
    project = tmp_path / "project"
    _project(project)
    before = _snapshot(project)

    assert main(["--mode", "consult", "status", str(project)]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["read_only"] is True
    assert _snapshot(project) == before

    new_project = tmp_path / "blocked-project"
    assert main(["--mode", "consult", "start", str(new_project), "--yes"]) == 2
    error = json.loads(capsys.readouterr().out)
    assert error["code"] == "EA-IO-PERMISSION-DENIED"
    assert "consult" in error["cause"]["message"]
    assert not new_project.exists()


def test_audit_requires_no_write_flags_and_record_blocks_execution(tmp_path: Path, capsys) -> None:
    project = tmp_path / "project"
    _project(project)

    assert main(["--mode", "audit", "brief", "project", str(project), "--no-write", "--json"]) == 0
    capsys.readouterr()
    assert main(["--mode", "audit", "brief", "project", str(project), "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["code"] == "EA-IO-PERMISSION-DENIED"

    source = tmp_path / "spectrum.txt"
    source.write_text("100 1\n101 2\n", encoding="utf-8")
    assert main(["--mode", "record", "raman", "inspect", str(project), str(source)]) == 2
    assert json.loads(capsys.readouterr().out)["code"] == "EA-IO-PERMISSION-DENIED"


def test_mode_command_is_read_only_and_describes_all_modes(tmp_path: Path, capsys) -> None:
    assert main(["--mode", "consult", "mode", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["active_mode"] == "consult"
    assert set(result["modes"]) == {"consult", "record", "execute", "audit"}
    assert result["modes"]["consult"]["writes"] is False
