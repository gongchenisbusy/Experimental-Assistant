from __future__ import annotations

import csv
import json
from pathlib import Path

from ea.cli import main
from ea.literature import (
    confirm_literature_selection,
    generate_literature_keywords,
    plan_literature_deployment,
    prepare_literature_acquisition_handoff,
    sync_literature_acquisition_status,
)
from ea.projects import initialize_project
from ea.storage import read_yaml, write_yaml


def test_literature_keywords_extract_project_methods_and_materials() -> None:
    keywords = generate_literature_keywords(
        project_name="MoS2 mica Raman project",
        research_direction="single-layer MoS2 growth on mica",
        material_system="MoS2",
        experiment_type="CVD growth and Raman characterization",
        extra_keywords=["strain", "doping"],
    )

    assert "mos2" in keywords["material_terms"]
    assert "raman" in keywords["method_terms"]
    assert "cvd" in keywords["method_terms"]
    assert "strain" in keywords["exact_terms"]


def test_literature_plan_writes_confirmation_package_and_skeleton_tables(tmp_path: Path) -> None:
    initialize_project(
        tmp_path,
        project_name="MoS2 Literature",
        project_slug="mos2-literature",
        research_direction="single-layer MoS2 growth on mica",
        material_system="MoS2",
        experiment_type="CVD growth and Raman characterization",
        enable_literature=True,
        created_at="2026-06-30T13:00:00",
    )

    result = plan_literature_deployment(
        tmp_path,
        scope="ordinary",
        access_mode="open_access_only",
        extra_keywords=["strain", "doping"],
    )
    status = read_yaml(tmp_path / "literature" / "deployment_status.yml")
    queries = read_yaml(tmp_path / "literature" / "search_queries.yml")
    confirmation = read_yaml(tmp_path / "literature" / "confirmation_request.yml")

    assert status["status"] == "planned_awaiting_user_confirmation"
    assert status["recommended_top_n"] == 50
    assert status["selected_top_n"] is None
    assert queries["coverage_goal"] == "systematic_multi_source_search_with_logged_gaps"
    assert any("mos2" in query["query"].lower() for query in queries["queries"])
    assert confirmation["requires_user_confirmation_before_download"] is True
    assert result["confirmation"]["estimated_time_minutes"]["search_and_rank"] >= 10
    assert "No claim of exhaustive web coverage" in (tmp_path / "literature" / "search_log.md").read_text(encoding="utf-8")

    with (tmp_path / "literature" / "ranking.csv").open(encoding="utf-8") as handle:
        headers = next(csv.reader(handle))
    assert "project_relevance" in headers
    assert "score" in headers


def test_literature_confirm_records_selected_top_n_and_warning(tmp_path: Path) -> None:
    initialize_project(
        tmp_path,
        project_name="MoS2 Review",
        project_slug="mos2-review",
        research_direction="broad MoS2 literature review",
        material_system="MoS2",
        experiment_type="Raman and PL comparison",
        enable_literature=True,
    )
    plan_literature_deployment(tmp_path, scope="narrow", access_mode="index_only")

    result = confirm_literature_selection(
        tmp_path,
        selected_top_n=40,
        user_response="确认下载 top 40，分批执行。",
        confirmed_at="2026-06-30T13:30:00",
    )
    status = result["status"]
    selected = read_yaml(tmp_path / "literature" / "selected_items.yml")

    assert status["status"] == "confirmed_awaiting_acquisition"
    assert status["selected_top_n"] == 40
    assert status["warnings"][0]["code"] == "selected_top_n_above_recommendation"
    assert selected["selection_status"] == "awaiting_search_results"
    assert selected["selected_top_n"] == 40


def test_literature_handoff_requires_confirmation_and_writes_sync_contract(tmp_path: Path) -> None:
    initialize_project(
        tmp_path,
        project_name="MoS2 Handoff",
        project_slug="mos2-handoff",
        research_direction="MoS2 literature acquisition",
        material_system="MoS2",
        experiment_type="Raman characterization",
        enable_literature=True,
    )
    plan_literature_deployment(tmp_path, scope="ordinary", access_mode="open_access_only")

    try:
        prepare_literature_acquisition_handoff(tmp_path)
    except ValueError as exc:
        assert "confirmed_awaiting_acquisition" in str(exc)
    else:  # pragma: no cover - defensive guard
        raise AssertionError("handoff should require confirmation")

    confirm_literature_selection(
        tmp_path,
        selected_top_n=50,
        user_response="确认 top 50，开始文献专用流程。",
        confirmed_at="2026-06-30T14:00:00",
    )
    result = prepare_literature_acquisition_handoff(
        tmp_path,
        handoff_mode="dedicated_thread",
        literature_thread_id="thread-lit-001",
        created_at="2026-06-30T14:05:00",
    )

    status = read_yaml(tmp_path / "literature" / "deployment_status.yml")
    handoff = read_yaml(tmp_path / "literature" / "acquisition_handoff.yml")
    sync = read_yaml(tmp_path / "literature" / "origin_thread_sync.yml")
    prompt = (tmp_path / "literature" / "acquisition_handoff.md").read_text(encoding="utf-8")

    assert status["status"] == "acquisition_handoff_ready"
    assert status["literature_thread_id"] == "thread-lit-001"
    assert status["acquisition_handoff_ref"] == "literature/acquisition_handoff.yml"
    assert handoff["selected_top_n"] == 50
    assert handoff["expected_output_refs"]["status_update"] == "literature/acquisition_status_update.yml"
    assert "Do not assume developer-machine Zotero" in handoff["workflow_contract"][0]
    assert "ea literature sync-status" in prompt
    assert sync["status"] == "handoff_ready"
    assert result["handoff"]["handoff_id"] == "lit-handoff-20260630T140500"


def test_literature_sync_status_updates_origin_project(tmp_path: Path) -> None:
    initialize_project(
        tmp_path,
        project_name="MoS2 Sync",
        project_slug="mos2-sync",
        research_direction="MoS2 literature sync",
        material_system="MoS2",
        experiment_type="CVD and Raman",
        enable_literature=True,
    )
    plan_literature_deployment(tmp_path, scope="narrow", access_mode="open_access_only")
    confirm_literature_selection(tmp_path, selected_top_n=30, user_response="确认 top 30。")
    prepare_literature_acquisition_handoff(tmp_path, created_at="2026-06-30T15:00:00")
    update_path = tmp_path / "literature" / "acquisition_status_update.yml"
    write_yaml(
        update_path,
        {
            "schema_version": "0.2",
            "status": "acquisition_in_progress",
            "candidate_count": 120,
            "deduped_count": 85,
            "downloaded_fulltext": 12,
            "cached_fulltext": 10,
            "needs_user_login": [{"doi": "10.0000/example", "reason": "publisher_login_required"}],
            "blocked_items": [{"title": "Blocked paper", "reason": "no_lawful_access"}],
            "summary_for_origin_thread": "Search finished, acquisition partially complete.",
        },
    )

    result = sync_literature_acquisition_status(
        tmp_path,
        update_path=Path("literature/acquisition_status_update.yml"),
        synced_at="2026-06-30T15:30:00",
    )
    status = result["status"]
    sync = read_yaml(tmp_path / "literature" / "origin_thread_sync.yml")

    assert status["candidate_count"] == 120
    assert status["deduped_count"] == 85
    assert status["downloaded_fulltext"] == 12
    assert status["cached_fulltext"] == 10
    assert status["needs_user_login"][0]["doi"] == "10.0000/example"
    assert status["blocked_items"][0]["title"] == "Blocked paper"
    assert status["last_acquisition_sync_at"] == "2026-06-30T15:30:00"
    assert sync["status"] == "acquisition_in_progress"
    assert sync["summary_for_origin_thread"] == "Search finished, acquisition partially complete."


def test_cli_literature_plan_and_confirm(tmp_path: Path, capsys) -> None:
    initialize_project(
        tmp_path,
        project_name="CLI Literature",
        project_slug="cli-literature",
        research_direction="MoS2 Raman literature",
        material_system="MoS2",
        experiment_type="Raman characterization",
        enable_literature=True,
    )

    assert main(["literature", "plan", str(tmp_path), "--scope", "ordinary", "--keyword", "strain"]) == 0
    planned = json.loads(capsys.readouterr().out)
    assert planned["confirmation"]["recommended_top_n"] == 50

    assert main(
        [
            "literature",
            "confirm",
            str(tmp_path),
            "--selected-top-n",
            "50",
            "--user-response",
            "确认 top 50。",
        ]
    ) == 0
    confirmed = json.loads(capsys.readouterr().out)
    assert confirmed["status"]["status"] == "confirmed_awaiting_acquisition"
    assert confirmed["status"]["selected_top_n"] == 50

    assert main(["literature", "handoff", str(tmp_path), "--literature-thread-id", "thread-cli-lit"]) == 0
    handoff = json.loads(capsys.readouterr().out)
    assert handoff["status"]["status"] == "acquisition_handoff_ready"
    assert handoff["handoff"]["literature_thread_id"] == "thread-cli-lit"

    write_yaml(
        tmp_path / "literature" / "acquisition_status_update.yml",
        {"status": "acquisition_in_progress", "candidate_count": 75, "summary_for_origin_thread": "CLI sync update."},
    )
    assert main(["literature", "sync-status", str(tmp_path)]) == 0
    synced = json.loads(capsys.readouterr().out)
    assert synced["status"]["candidate_count"] == 75
    assert synced["sync"]["summary_for_origin_thread"] == "CLI sync update."
