from __future__ import annotations

import csv
import json
from pathlib import Path

from ea.cli import main
from ea.literature import (
    confirm_literature_selection,
    generate_literature_keywords,
    import_literature_acquisition_manifest,
    plan_literature_deployment,
    prepare_literature_acquisition_request,
    prepare_literature_acquisition_handoff,
    rank_literature_candidates,
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


def test_literature_acquisition_request_writes_zotero_codex_targets_after_confirmation(tmp_path: Path) -> None:
    initialize_project(
        tmp_path,
        project_name="MoS2 Acquisition Request",
        project_slug="mos2-acq-request",
        research_direction="MoS2 literature acquisition",
        material_system="MoS2",
        experiment_type="Raman characterization",
        enable_literature=True,
    )
    plan_literature_deployment(tmp_path, scope="ordinary", access_mode="open_access_only")
    confirm_literature_selection(tmp_path, selected_top_n=2, user_response="确认 top 2。")
    write_yaml(
        tmp_path / "literature" / "selected_items.yml",
        {
            "schema_version": "0.2",
            "project_id": "prj-mos2-acq-request",
            "selection_status": "selected",
            "selected_top_n": 2,
            "items": [
                {
                    "candidate_id": "cand-001",
                    "rank": 1,
                    "title": "Raman modes in MoS2",
                    "doi": "10.1000/mos2-raman",
                    "url": "https://doi.org/10.1000/mos2-raman",
                    "authors": "Lee C. et al.",
                    "year": "2010",
                    "venue": "ACS Nano",
                },
                {
                    "candidate_id": "cand-002",
                    "rank": 2,
                    "title": "MoS2 photoluminescence",
                    "doi": "10.1000/mos2-pl",
                    "url": "https://doi.org/10.1000/mos2-pl",
                },
            ],
        },
    )

    result = prepare_literature_acquisition_request(tmp_path, created_at="2026-06-30T16:00:00")
    request = read_yaml(tmp_path / "literature" / "acquisition_request.yml")
    targets_text = (tmp_path / "literature" / "zotero_codex_targets.jsonl").read_text(encoding="utf-8")
    targets = [json.loads(line) for line in targets_text.splitlines()]
    status = read_yaml(tmp_path / "literature" / "deployment_status.yml")

    assert result["request"]["request_id"] == "lit-acq-20260630T160000"
    assert request["status"] == "ready_for_batch_acquisition"
    assert request["target_count"] == 2
    assert "batch_acquire.py" in request["zotero_codex_contract"]["batch_acquire_command"]
    assert targets[0]["doi"] == "10.1000/mos2-raman"
    assert targets[0]["source_candidate_id"] == "cand-001"
    assert status["status"] == "acquisition_request_ready"
    assert status["zotero_codex_targets_ref"] == "literature/zotero_codex_targets.jsonl"
    assert "No live search" in status["summary_for_origin_thread"]


def test_literature_acquisition_request_without_targets_keeps_search_boundary(tmp_path: Path) -> None:
    initialize_project(
        tmp_path,
        project_name="MoS2 Search Request",
        project_slug="mos2-search-request",
        research_direction="MoS2 literature acquisition",
        material_system="MoS2",
        experiment_type="Raman characterization",
        enable_literature=True,
    )
    plan_literature_deployment(tmp_path, scope="narrow", access_mode="open_access_only")
    confirm_literature_selection(tmp_path, selected_top_n=30, user_response="确认 top 30。")

    result = prepare_literature_acquisition_request(tmp_path, created_at="2026-06-30T16:10:00")

    assert result["request"]["status"] == "awaiting_search_results"
    assert result["request"]["target_count"] == 0
    assert "Run literature search/ranking" in result["request"]["next_action"]
    assert (tmp_path / "literature" / "zotero_codex_queries.jsonl").read_text(encoding="utf-8")
    assert (tmp_path / "literature" / "zotero_codex_targets.jsonl").read_text(encoding="utf-8") == ""


def test_literature_rank_candidates_dedupes_scores_and_exports_selected_items(tmp_path: Path) -> None:
    initialize_project(
        tmp_path,
        project_name="MoS2 Candidate Ranking",
        project_slug="mos2-candidate-ranking",
        research_direction="MoS2 Raman and PL literature",
        material_system="MoS2",
        experiment_type="Raman and PL characterization",
        enable_literature=True,
    )
    plan_literature_deployment(tmp_path, scope="ordinary", access_mode="open_access_only")
    confirm_literature_selection(tmp_path, selected_top_n=2, user_response="确认 top 2。")
    write_yaml(
        tmp_path / "literature" / "candidate_input.yml",
        {
            "schema_version": "0.2",
            "candidates": [
                {
                    "title": "MoS2 Raman strain review",
                    "authors": ["A. Author", "B. Author"],
                    "year": 2024,
                    "venue": "Advanced Materials",
                    "doi": "10.1000/mos2-rank-1",
                    "project_relevance": 5,
                    "venue_authority": 4,
                    "recency": 5,
                    "citation_or_influence": 3,
                    "fulltext_availability_and_usefulness": 4,
                    "source": "crossref",
                },
                {
                    "title": "Duplicate lower score",
                    "year": 2016,
                    "doi": "10.1000/mos2-rank-1",
                    "project_relevance": 2,
                    "venue_authority": 2,
                    "recency": 3,
                    "citation_or_influence": 1,
                    "fulltext_availability_and_usefulness": 1,
                },
                {
                    "title": "Classic monolayer MoS2 photoluminescence",
                    "authors": "K. Mak et al.",
                    "year": 2010,
                    "venue": "Physical Review Letters",
                    "doi": "10.1000/mos2-rank-2",
                    "project_relevance": 4,
                    "venue_authority": 4,
                    "recency": 2,
                    "citation_or_influence": 5,
                    "fulltext_availability_and_usefulness": 3,
                },
                {
                    "title": "Unrelated graphene battery paper",
                    "year": 2025,
                    "venue": "Nature",
                    "doi": "10.1000/not-mos2",
                    "project_relevance": 1,
                    "venue_authority": 5,
                    "recency": 5,
                    "citation_or_influence": 5,
                    "fulltext_availability_and_usefulness": 1,
                },
            ],
        },
    )

    result = rank_literature_candidates(
        tmp_path,
        candidates_path=Path("literature/candidate_input.yml"),
        reference_year=2026,
        ranked_at="2026-07-01T09:00:00",
    )
    status = read_yaml(tmp_path / "literature" / "deployment_status.yml")
    selected = read_yaml(tmp_path / "literature" / "selected_items.yml")
    with (tmp_path / "literature" / "ranking.csv").open(encoding="utf-8") as handle:
        ranking = list(csv.DictReader(handle))

    assert result["candidate_count"] == 4
    assert result["deduped_count"] == 3
    assert result["duplicate_candidate_count"] == 1
    assert result["selection_status"] == "selected_from_ranked_candidates"
    assert status["status"] == "ranked_candidates_ready"
    assert status["candidate_ranking_method"]["weights"]["project_relevance"] == 0.40
    assert "No live search" in status["summary_for_origin_thread"]
    assert ranking[0]["candidate_id"] == "cand-001"
    assert ranking[0]["title"] == "MoS2 Raman strain review"
    assert selected["items"][0]["candidate_id"] == "cand-001"
    assert selected["items"][1]["candidate_id"] == "cand-002"
    assert len(selected["items"]) == 2

    acquisition = prepare_literature_acquisition_request(tmp_path, created_at="2026-07-01T09:05:00")
    assert acquisition["request"]["status"] == "ready_for_batch_acquisition"
    assert acquisition["request"]["target_count"] == 2


def test_cli_literature_rank_candidates_populates_acquisition_targets(tmp_path: Path, capsys) -> None:
    initialize_project(
        tmp_path,
        project_name="CLI Candidate Ranking",
        project_slug="cli-candidate-ranking",
        research_direction="MoS2 Raman literature ranking",
        material_system="MoS2",
        experiment_type="Raman characterization",
        enable_literature=True,
    )
    plan_literature_deployment(tmp_path, scope="narrow", access_mode="open_access_only")
    confirm_literature_selection(tmp_path, selected_top_n=1, user_response="确认 top 1。")
    candidates_path = tmp_path / "literature" / "candidates.json"
    candidates_path.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "title": "MoS2 Raman CLI ranking",
                        "year": 2025,
                        "venue": "ACS Nano",
                        "doi": "10.1000/cli-rank",
                        "project_relevance": 5,
                        "venue_authority": 4,
                        "recency": 5,
                        "citation_or_influence": 2,
                        "fulltext_availability_and_usefulness": 4,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "literature",
                "rank-candidates",
                str(tmp_path),
                "--candidates",
                "literature/candidates.json",
                "--reference-year",
                "2026",
            ]
        )
        == 0
    )
    ranked = json.loads(capsys.readouterr().out)
    assert ranked["status"]["status"] == "ranked_candidates_ready"
    assert ranked["selected_count"] == 1

    assert main(["literature", "acquisition-request", str(tmp_path)]) == 0
    request = json.loads(capsys.readouterr().out)
    assert request["request"]["status"] == "ready_for_batch_acquisition"
    assert request["request"]["target_count"] == 1


def test_literature_import_acquisition_manifest_registers_references_and_syncs_status(tmp_path: Path) -> None:
    initialize_project(
        tmp_path,
        project_name="MoS2 Acquisition Import",
        project_slug="mos2-acq-import",
        research_direction="MoS2 literature acquisition",
        material_system="MoS2",
        experiment_type="Raman characterization",
        enable_literature=True,
    )
    plan_literature_deployment(tmp_path, scope="ordinary", access_mode="open_access_only")
    confirm_literature_selection(tmp_path, selected_top_n=2, user_response="确认 top 2。")
    manifest_path = tmp_path / "literature" / "acquisition_manifest.yml"
    write_yaml(
        manifest_path,
        {
            "schema_version": "0.2",
            "project_id": "prj-mos2-acq-import",
            "status": "acquisition_complete",
            "candidate_count": 8,
            "deduped_count": 2,
            "summary_for_origin_thread": "Imported literature acquisition results.",
            "items": [
                {
                    "title": "Raman modes in MoS2",
                    "authors": ["Lee C.", "Yan H."],
                    "year": 2010,
                    "venue": "ACS Nano",
                    "doi": "10.1000/mos2-raman",
                    "url": "https://doi.org/10.1000/mos2-raman",
                    "local_path": "literature/fulltext/lee-2010.pdf",
                    "cache_path": "literature/cache/ABCD1234",
                    "zotero_item_key": "ABCD1234",
                    "status": "cached",
                },
                {
                    "title": "MoS2 photoluminescence",
                    "authors": "Mak K. et al.",
                    "year": 2010,
                    "venue": "Physical Review Letters",
                    "doi": "10.1000/mos2-pl",
                    "url": "https://doi.org/10.1000/mos2-pl",
                    "status": "metadata_only",
                },
            ],
        },
    )

    result = import_literature_acquisition_manifest(
        tmp_path,
        manifest_path=Path("literature/acquisition_manifest.yml"),
        created_at="2026-06-30T16:20:00",
    )
    status = read_yaml(tmp_path / "literature" / "deployment_status.yml")
    library = read_yaml(tmp_path / "literature" / "library_manifest.yml")
    cache = read_yaml(tmp_path / "literature" / "cache_index.yml")
    references = read_yaml(tmp_path / "literature" / "references" / "index.yml")

    assert result["imported_count"] == 2
    assert result["reused_count"] == 0
    assert status["status"] == "acquisition_complete"
    assert status["candidate_count"] == 8
    assert status["downloaded_fulltext"] == 1
    assert status["cached_fulltext"] == 1
    assert status["reference_import"]["imported_count"] == 2
    assert library["item_count"] == 2
    assert library["items"][0]["reference_id"].startswith("ref-")
    assert cache["cached_count"] == 1
    assert len(references["references"]) == 2


def test_literature_import_acquisition_manifest_reuses_duplicate_reference(tmp_path: Path) -> None:
    initialize_project(
        tmp_path,
        project_name="MoS2 Acquisition Reuse",
        project_slug="mos2-acq-reuse",
        research_direction="MoS2 literature acquisition",
        material_system="MoS2",
        experiment_type="Raman characterization",
        enable_literature=True,
    )
    main(
        [
            "references",
            "add",
            str(tmp_path),
            "--citation",
            "Existing Author. Existing MoS2 reference. Journal (2010).",
            "--doi",
            "10.1000/existing",
        ]
    )
    manifest_path = tmp_path / "literature" / "acquisition_manifest.yml"
    write_yaml(
        manifest_path,
        {
            "items": [
                {
                    "title": "Existing MoS2 reference",
                    "doi": "10.1000/existing",
                    "citation": "Existing Author. Existing MoS2 reference. Journal (2010).",
                }
            ]
        },
    )

    result = import_literature_acquisition_manifest(tmp_path, manifest_path=manifest_path)

    assert result["imported_count"] == 0
    assert result["reused_count"] == 1


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

    assert main(["literature", "acquisition-request", str(tmp_path)]) == 0
    request = json.loads(capsys.readouterr().out)
    assert request["request"]["status"] == "awaiting_search_results"
    assert request["request"]["query_manifest_ref"] == "literature/zotero_codex_queries.jsonl"

    write_yaml(
        tmp_path / "literature" / "acquisition_manifest.yml",
        {
            "status": "acquisition_complete",
            "items": [
                {
                    "title": "CLI literature acquisition paper",
                    "doi": "10.1000/cli-lit",
                    "citation": "CLI Author. CLI literature acquisition paper. Journal (2026).",
                    "cache_path": "literature/cache/CLI12345",
                }
            ],
        },
    )
    assert main(["literature", "import-acquisition", str(tmp_path), "--manifest", "literature/acquisition_manifest.yml"]) == 0
    imported = json.loads(capsys.readouterr().out)
    assert imported["imported_count"] == 1
    assert imported["sync"]["status"]["status"] == "acquisition_complete"

    write_yaml(
        tmp_path / "literature" / "acquisition_status_update.yml",
        {"status": "acquisition_in_progress", "candidate_count": 75, "summary_for_origin_thread": "CLI sync update."},
    )
    assert main(["literature", "sync-status", str(tmp_path)]) == 0
    synced = json.loads(capsys.readouterr().out)
    assert synced["status"]["candidate_count"] == 75
    assert synced["sync"]["summary_for_origin_thread"] == "CLI sync update."


def test_literature_initialization_docs_and_registry_are_discoverable() -> None:
    root = Path.cwd()

    readme = (root / "README.md").read_text(encoding="utf-8")
    skill = (root / "skills" / "ea-v0-2" / "SKILL.md").read_text(encoding="utf-8")
    reference = (root / "skills" / "ea-v0-2" / "references" / "local-literature-library.md").read_text(encoding="utf-8")
    registry = read_yaml(root / "skill-registry" / "index.yml")
    manifest = read_yaml(root / "skill-registry" / "builtins" / "local-literature-library.yml")["ea_skill"]

    assert "literature-library decision record" in readme
    assert "rank-candidates" in readme
    assert "open-items/" in reference
    assert "rank-candidates" in reference
    assert "decision_status: enabled_at_initialization" in reference
    assert "contract boundaries until their implementation services exist" not in skill
    literature_record = next(item for item in registry["skills"] if item["id"] == "ea.local-literature-library")
    assert "Literature initialization decision" in literature_record["notes"]
    assert "open_item" in manifest["output_artifacts"]
    assert "ranked_candidate_table" in manifest["output_artifacts"]
    assert "initialization_open_item_when_literature_not_enabled" in manifest["current_v0_2_support"]["implemented"]
    assert "supplied_candidate_ranking_and_selection_export" in manifest["current_v0_2_support"]["implemented"]
