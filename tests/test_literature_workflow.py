from __future__ import annotations

import csv
import json
from pathlib import Path

from ea.cli import main
from ea.literature import (
    confirm_literature_selection,
    generate_literature_keywords,
    plan_literature_deployment,
)
from ea.projects import initialize_project
from ea.storage import read_yaml


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
