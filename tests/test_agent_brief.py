from __future__ import annotations

import json
import shutil
from pathlib import Path

from ea.brief import build_project_brief
from ea.cli import main
from ea.projects import initialize_project


PUBLIC_RAMAN_EXAMPLE = Path("examples/public-raman-project").resolve()


def test_project_brief_previews_new_project_without_writing(tmp_path: Path) -> None:
    initialize_project(
        tmp_path,
        project_name="Brief Project",
        project_slug="brief-project",
        research_direction="agent brief workflow",
        material_system="MoS2",
        experiment_type="Raman",
        created_at="2026-07-02T14:00:00",
    )

    brief = build_project_brief(tmp_path, write_report=False, created_at="2026-07-02T14:05:00")

    assert brief["brief_id"] is None
    assert brief["evaluation"]["status"] == "pass"
    assert brief["key_outputs"]["reports"] == []
    assert brief["literature"]["status"] == "decision_needed"
    assert brief["project_working_memory"]["exists"] is True
    assert any("Import raw data" in action for action in brief["next_actions"])
    assert not list((tmp_path / "briefs").glob("*"))


def test_project_brief_writes_user_visible_markdown_for_public_example(tmp_path: Path) -> None:
    workspace = tmp_path / "public-raman-project"
    shutil.copytree(PUBLIC_RAMAN_EXAMPLE, workspace)

    brief = build_project_brief(workspace, created_at="2026-07-02T14:10:00")
    markdown = Path(brief["markdown_path"]).read_text(encoding="utf-8")

    assert brief["brief_id"] == "brief-20260702-001"
    assert Path(brief["yaml_path"]).exists()
    assert "# EA Project Brief" in markdown
    assert "## Key Outputs" in markdown
    assert "reports/" in markdown
    assert "## Recommended Next Actions" in markdown
    assert "Detailed refs, hashes, provenance, review records, and trace graphs stay in local EA files" in markdown
    assert "review-" not in markdown
    assert brief["scope"]["hides_low_level_refs_by_default"] is True


def test_cli_brief_project_no_write_returns_concise_json(tmp_path: Path, capsys) -> None:
    workspace = tmp_path / "public-raman-project"
    shutil.copytree(PUBLIC_RAMAN_EXAMPLE, workspace)

    return_code = main(["brief", "project", str(workspace), "--no-write"])
    output = json.loads(capsys.readouterr().out)

    assert return_code == 0
    assert output["brief_type"] == "ea_agent_user_brief"
    assert output["markdown_path"] is None
    assert output["evaluation"]["status"] == "pass"
    assert output["key_outputs"]["reports"]
    assert "project_working_memory" in output
    assert "markdown" not in output
    assert not list((workspace / "briefs").glob("*"))
