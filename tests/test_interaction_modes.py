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
    assert error["code"] == "EA-MODE-COMMAND-BLOCKED"
    assert "consult" in error["cause"]["message"]
    assert not new_project.exists()


def test_audit_requires_no_write_flags_and_record_blocks_execution(tmp_path: Path, capsys) -> None:
    project = tmp_path / "project"
    _project(project)

    assert main(["--mode", "audit", "brief", "project", str(project), "--no-write", "--json"]) == 0
    capsys.readouterr()
    assert main(["--mode", "audit", "brief", "project", str(project), "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["code"] == "EA-MODE-COMMAND-BLOCKED"

    source = tmp_path / "spectrum.txt"
    source.write_text("100 1\n101 2\n", encoding="utf-8")
    assert main(["--mode", "record", "raman", "inspect", str(project), str(source)]) == 2
    assert json.loads(capsys.readouterr().out)["code"] == "EA-MODE-COMMAND-BLOCKED"


def test_audit_read_only_allowlist_does_not_admit_neighboring_writes(
    tmp_path: Path, capsys
) -> None:
    project = tmp_path / "project"
    _project(project)
    before = _snapshot(project)

    assert main(
        [
            "--mode",
            "audit",
            "references",
            "add",
            str(project),
            "--citation",
            "Blocked write candidate",
        ]
    ) == 2
    assert json.loads(capsys.readouterr().out)["code"] == "EA-MODE-COMMAND-BLOCKED"

    assert main(
        [
            "--mode",
            "audit",
            "export",
            "report-bundle",
            str(project),
            "--report-id",
            "rpt-blocked",
        ]
    ) == 2
    assert json.loads(capsys.readouterr().out)["code"] == "EA-MODE-COMMAND-BLOCKED"
    assert _snapshot(project) == before


def test_mode_command_is_read_only_and_describes_all_modes(tmp_path: Path, capsys) -> None:
    assert main(["--mode", "consult", "mode", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["active_mode"] == "consult"
    assert set(result["modes"]) == {"consult", "record", "execute", "audit"}
    assert result["modes"]["consult"]["writes"] is False


def test_consult_and_audit_allow_spectrum_inspection_without_project_writes(
    tmp_path: Path, capsys
) -> None:
    project = tmp_path / "project"
    _project(project)
    spectrum = tmp_path / "spectrum.txt"
    spectrum.write_text("wavenumber intensity\n100 1\n101 2\n", encoding="utf-8")
    before = _snapshot(project)

    assert main(["--mode", "consult", "raman", "inspect", str(project), str(spectrum)]) == 0
    assert json.loads(capsys.readouterr().out)["path"] == str(spectrum)
    assert main(["--mode", "audit", "pl", "inspect", str(project), str(spectrum)]) == 0
    assert json.loads(capsys.readouterr().out)["path"] == str(spectrum)
    assert main(["--mode", "consult", "raman", "list-assignment-libraries"]) == 0
    capsys.readouterr()
    assert _snapshot(project) == before


def test_consult_still_blocks_spectrum_processing(tmp_path: Path, capsys) -> None:
    project = tmp_path / "project"
    _project(project)

    assert main(
        [
            "--mode",
            "consult",
            "raman",
            "process",
            str(project),
            "--metadata",
            "raw/raman/char-001/metadata.yml",
            "--project-id",
            "project-mode-project",
            "--x-column",
            "col_0",
            "--y-column",
            "col_1",
            "--x-unit",
            "cm^-1",
            "--column-review-ref",
            "review-columns",
            "--parameter-review-ref",
            "review-parameters",
        ]
    ) == 2
    assert json.loads(capsys.readouterr().out)["code"] == "EA-MODE-COMMAND-BLOCKED"
