from __future__ import annotations

import json
from pathlib import Path

from ea.cli import main
from ea.estimates import estimate_workflow, large_work_reminders_disabled, set_large_work_reminders
from ea.literature import setup_literature_preflight
from ea.memory import refresh_project_working_memory, show_project_working_memory
from ea.projects import initialize_project
from ea.storage import read_markdown_record, read_yaml


def test_project_working_memory_skeleton_refresh_and_show(tmp_path: Path) -> None:
    initialize_project(
        tmp_path,
        project_name="Working Memory Project",
        project_slug="working-memory-project",
        research_direction="long-running project tracking",
        material_system="MoS2",
        experiment_type="CVD",
        created_at="2026-07-07T09:00:00",
    )

    memory_path = tmp_path / "memory" / "project-working-memory.md"
    assert memory_path.exists()
    frontmatter, body = read_markdown_record(memory_path)
    assert frontmatter["memory_type"] == "project_working_memory"
    assert frontmatter["project_id"] == "prj-working-memory-project"
    assert "Handoff Note" in body

    result = refresh_project_working_memory(tmp_path, refreshed_at="2026-07-07T09:05:00")
    shown = show_project_working_memory(tmp_path)

    assert result["status"] == "refreshed"
    assert shown["exists"] is True
    assert "Project Working Memory" in shown["markdown"]
    assert not (tmp_path / "memory" / "confirmed-findings.md").exists()


def test_literature_setup_preflight_groups_public_safe_actions(tmp_path: Path) -> None:
    initialize_project(
        tmp_path,
        project_name="Literature Preflight",
        project_slug="literature-preflight",
        research_direction="literature setup",
        material_system="MoS2",
        experiment_type="Raman",
    )

    result = setup_literature_preflight(tmp_path, lang="zh", checked_at="2026-07-07T09:10:00")

    assert result["check_type"] == "ea_literature_setup_preflight"
    assert "已自动完成" in result
    assert "需要你手动完成" in result
    assert "暂时无法配置" in result
    assert result["environment"]["stores_credentials"] is False
    assert (tmp_path / "literature" / "setup_preflight.yml").exists()


def test_large_work_estimate_threshold_and_opt_out(tmp_path: Path) -> None:
    initialize_project(
        tmp_path,
        project_name="Large Work",
        project_slug="large-work",
        research_direction="large literature workflow",
        material_system="MoS2",
        experiment_type="review",
    )

    estimate = estimate_workflow(
        tmp_path,
        workflow="literature_acquisition",
        requested_items=1000,
    )
    assert estimate["threshold_codex_credit_equivalent"] == 100.0
    assert estimate["requires_confirmation_before_run"] is True

    set_large_work_reminders(tmp_path, disabled=True, reason="user asked to stop reminders")
    assert large_work_reminders_disabled(tmp_path) is True
    disabled_estimate = estimate_workflow(
        tmp_path,
        workflow="literature_acquisition",
        requested_items=1000,
    )
    assert disabled_estimate["exceeds_large_work_threshold"] is True
    assert disabled_estimate["requires_confirmation_before_run"] is False
    preferences = read_yaml(tmp_path / ".ea" / "preferences.yml")
    assert preferences["large_work_reminders"]["preserves_safety_permission_and_review_gates"] is True


def test_cli_v0_9_5_new_commands(tmp_path: Path, capsys) -> None:
    assert main(
        [
            "init-project",
            str(tmp_path),
            "--name",
            "CLI v0.9.6",
            "--slug",
            "cli-v0-9-5",
            "--direction",
            "version workflow",
            "--material",
            "MoS2",
            "--experiment-type",
            "Raman",
        ]
    ) == 0
    init_output = json.loads(capsys.readouterr().out)
    assert init_output["project_working_memory"].endswith("project-working-memory.md")

    assert main(["onboarding", "post-install", "--json"]) == 0
    onboarding = json.loads(capsys.readouterr().out)
    assert onboarding["identity"]["display_version"] == "Experimental Assistant v1.0.0"

    assert main(["memory", "refresh-project", str(tmp_path)]) == 0
    refreshed = json.loads(capsys.readouterr().out)
    assert refreshed["ref"] == "memory/project-working-memory.md"

    assert main(["literature", "setup-preflight", str(tmp_path), "--no-write"]) == 0
    preflight = json.loads(capsys.readouterr().out)
    assert preflight["environment"]["stores_credentials"] is False

    assert main(["estimate", "workflow", str(tmp_path), "--workflow", "literature_acquisition", "--items", "1000"]) == 0
    estimate = json.loads(capsys.readouterr().out)
    assert estimate["requires_confirmation_before_run"] is True
