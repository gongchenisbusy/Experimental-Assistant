from __future__ import annotations

import json
from pathlib import Path
import shutil

from ea.cli import _print_json, main
from ea.user_surface import (
    build_project_dashboard,
    generate_user_report,
    guided_first_journey,
    inspect_analysis_source,
    start_project,
)


def test_json_output_falls_back_to_ascii_escapes_on_western_console(
    monkeypatch,
) -> None:
    class AsciiOnly:
        def __init__(self) -> None:
            self.writes: list[str] = []

        def write(self, value: str) -> int:
            value.encode("ascii")
            self.writes.append(value)
            return len(value)

    writer = AsciiOnly()
    monkeypatch.setattr("ea.cli.sys.stdout", writer)

    _print_json({"message": "确定配置"})

    assert json.loads("".join(writer.writes)) == {"message": "确定配置"}


def test_start_plans_before_writing_and_creates_with_safe_defaults(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "My first project"

    plan = start_project(workspace)

    assert plan["status"] == "needs_confirmation"
    assert plan["values"]["project_name"] == "My first project"
    assert not workspace.exists()

    result = start_project(workspace, material_system="MoS2", confirmed=True)
    assert result["status"] == "completed"
    assert (workspace / "EA_PROJECT.md").is_file()
    assert (workspace / ".ea" / "project_format.yml").is_file()


def test_guided_journey_is_zero_write_and_returns_one_import_action(
    tmp_path: Path, capsys
) -> None:
    workspace = tmp_path / "First project"
    missing = guided_first_journey(workspace)
    assert missing["code"] == "project_not_created"
    assert missing["read_only"] is True
    assert not workspace.exists()

    start_project(workspace, material_system="MoS2", confirmed=True)
    source = tmp_path / "first-raman.csv"
    source.write_text("raman_shift_cm_1,intensity\n380,10\n400,20\n", encoding="utf-8")
    before = {
        path.relative_to(workspace): path.stat().st_mtime_ns
        for path in workspace.rglob("*")
        if path.is_file()
    }

    result = guided_first_journey(
        workspace, source_path=source, method="raman"
    )
    after = {
        path.relative_to(workspace): path.stat().st_mtime_ns
        for path in workspace.rglob("*")
        if path.is_file()
    }

    assert result["code"] == "import_ready_for_confirmation"
    assert result["status"] == "needs_confirmation"
    assert result["read_only"] is True
    assert result["details"]["columns"] == ["raman_shift_cm_1", "intensity"]
    assert result["details"]["unit_proposals"] == {"raman_shift_cm_1": "cm^-1"}
    assert "--preview-hash" in result["next_command"]
    assert before == after

    assert (
        main(
            [
                "--mode",
                "consult",
                "journey",
                str(workspace),
                "--source",
                str(source),
                "--method",
                "raman",
            ]
        )
        == 0
    )
    cli_result = json.loads(capsys.readouterr().out)
    assert cli_result["code"] == "import_ready_for_confirmation"


def test_dashboard_is_read_only_and_uses_optional_literature_semantics(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "project"
    start_project(workspace, confirmed=True)
    before = {
        path.relative_to(workspace): path.stat().st_mtime_ns
        for path in workspace.rglob("*")
        if path.is_file()
    }

    result = build_project_dashboard(workspace)
    after = {
        path.relative_to(workspace): path.stat().st_mtime_ns
        for path in workspace.rglob("*")
        if path.is_file()
    }

    assert result["read_only"] is True
    assert result["literature"]["status"] == "not_used"
    assert result["project_format"]["detected_project_format_version"] == "1.0"
    assert before == after


def test_analyze_is_a_read_only_method_inspection(tmp_path: Path) -> None:
    source = tmp_path / "raman.csv"
    source.write_text("shift,intensity\n100,2\n200,5\n", encoding="utf-8")

    result = inspect_analysis_source("raman", source)

    assert result["status"] == "ready_for_review"
    assert result["read_only"] is True
    assert "maturity" not in result
    assert "not a scientific conclusion" in result["review_boundary"]


def test_report_plans_before_writing_and_dispatches_to_existing_generator(
    tmp_path: Path,
) -> None:
    source = Path("examples/public-raman-project")
    workspace = tmp_path / "raman-project"
    shutil.copytree(source, workspace)
    metadata = next(workspace.glob("processed/**/raman_metadata.yml"))
    before_reports = set((workspace / "reports").glob("*.md"))

    plan = generate_user_report(workspace, method="raman", metadata_path=metadata)
    assert plan["status"] == "needs_confirmation"
    assert set((workspace / "reports").glob("*.md")) == before_reports

    result = generate_user_report(
        workspace, method="raman", metadata_path=metadata, confirmed=True
    )
    assert result["status"] == "completed"
    assert Path(result["report_path"]).is_file()


def test_task_oriented_cli_paths_are_usable(tmp_path: Path, capsys) -> None:
    workspace = tmp_path / "project"
    assert main(["start", str(workspace)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "needs_confirmation"
    assert main(["start", str(workspace), "--yes"]) == 0
    capsys.readouterr()
    assert main(["status", str(workspace)]) == 0
    assert json.loads(capsys.readouterr().out)["read_only"] is True
