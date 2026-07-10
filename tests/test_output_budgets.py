from __future__ import annotations

import json
import shutil
from pathlib import Path

from ea.cli import main
from ea.projects import initialize_project


MAX_NORMAL_STDOUT_BYTES = 4096


def _project(root: Path) -> None:
    initialize_project(
        root,
        project_name="Output budget project",
        project_slug="output-budget-project",
        research_direction="compact output regression",
        material_system="MoS2",
        experiment_type="Raman",
    )


def _run(capsys, argv: list[str]) -> str:
    assert main(argv) == 0
    output = capsys.readouterr().out
    assert len(output.encode("utf-8")) < MAX_NORMAL_STDOUT_BYTES, (argv, len(output.encode("utf-8")))
    return output


def test_public_status_brief_diagnostics_and_report_plan_stay_compact(tmp_path: Path, capsys) -> None:
    project = tmp_path / "project"
    _project(project)

    status = json.loads(_run(capsys, ["--mode", "consult", "status", str(project)]))
    assert status["read_only"] is True
    _run(capsys, ["--mode", "consult", "brief", "project", str(project), "--no-write"])
    diagnostics = json.loads(_run(capsys, ["--mode", "audit", "diagnostics", "collect", str(project)]))
    assert diagnostics["context_cost_proxy"]["exact_model_tokens_available"] is False

    example = tmp_path / "public-raman-project"
    shutil.copytree(Path("examples/public-raman-project"), example)
    metadata = "processed/sample-example-mos2-001/raman/res-public-raman-example-raman-20260602-001/raman_metadata.yml"
    report_plan = json.loads(_run(capsys, ["report", str(example), "--method", "raman", "--metadata", metadata]))
    assert report_plan["status"] == "needs_confirmation"


def test_mixed_acquisition_default_output_and_artifact_count_stay_bounded(tmp_path: Path, capsys) -> None:
    _project(tmp_path)
    status_path = tmp_path / "literature" / "zotero_codex_batch_status.json"
    status_path.write_text(
        json.dumps(
            {
                "request_id": "output-budget-five",
                "targets": [
                    {"id": "one", "title": "One", "doi": "10.1/one", "status": "cached", "cache_path": "cache/one"},
                    {"id": "two", "title": "Two", "doi": "10.1/two", "status": "downloaded", "pdf_path": "two.pdf"},
                    {"id": "three", "title": "Three", "doi": "10.1/three", "status": "needs-login", "reason": "login required"},
                    {"id": "four", "title": "Four", "doi": "10.1/four", "status": "needs-subscription", "reason": "subscription required"},
                    {"id": "five", "title": "Five", "doi": "10.1/five", "status": "blocked", "reason": "missing attachment file"},
                ],
            }
        ),
        encoding="utf-8",
    )
    before = {path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*") if path.is_file()}

    output = _run(capsys, ["literature", "import-zotero-status", str(tmp_path)])
    result = json.loads(output)
    after = {path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*") if path.is_file()}
    written = after - before

    assert result["target_count"] == 5
    assert result["ready_count"] == 2
    assert result["current_task_blocker_count"] == 3
    assert written == {
        "literature/external_acquisition_state.yml",
        "literature/acquisition_status_compact.md",
        "literature/zotero_codex_status_import.yml",
        "literature/acquisition_status_update.yml",
    }


def test_extraction_default_output_uses_cost_proxies_not_full_state(tmp_path: Path, capsys) -> None:
    _project(tmp_path)
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "metadata.json").write_text(json.dumps({"title": "Paper", "doi": "10.1/paper"}), encoding="utf-8")
    (cache / "chunks.jsonl").write_text(
        json.dumps({"chunk_id": "c1", "page": 2, "text": "Electrical conductivity was 2 S/cm at 300 K using four-probe in-plane measurement."}) + "\n",
        encoding="utf-8",
    )
    _run(
        capsys,
        [
            "literature",
            "data-plan",
            str(tmp_path),
            "--property",
            "electrical conductivity",
            "--kind",
            "conductivity",
            "--material",
            "2D film",
            "--dataset-id",
            "budget-data",
            "--source",
            str(cache),
            "--yes",
        ],
    )
    result = json.loads(_run(capsys, ["literature", "data-extract", str(tmp_path), "--dataset", "budget-data", "--yes"]))

    assert result["candidate_count"] == 1
    assert result["metrics"]["papers_processed"] == 1
    assert result["metrics"]["chunks_read"] == 1
    assert result["metrics"]["artifact_bytes"] > 0
    assert "exact_model_tokens" not in result
