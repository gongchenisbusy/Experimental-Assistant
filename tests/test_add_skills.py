from __future__ import annotations

import json
from pathlib import Path

from ea.cli import main
from ea.skills import register_skill_manifest, run_skill_dry_run
from ea.storage import read_yaml, write_yaml


VALID_MANIFEST = {
    "ea_skill": {
        "id": "ea.example-analysis",
        "version": "0.2.0",
        "category": "characterization.spectrum",
        "method": "example",
        "input_artifacts": ["raw_spectrum", "sample_context", "project_context"],
        "output_artifacts": [
            "processed_result",
            "figure_record",
            "report_section",
            "provenance_record",
            "memory_candidate",
        ],
        "review_gates": [
            "confirm_method",
            "confirm_processing_parameters",
            "confirm_interpretation_before_memory_write",
        ],
        "required_indices": [
            "raw/index.yml",
            "reports/index.yml",
            "figures/index.yml",
            "provenance/index.yml",
        ],
    }
}


VALID_SAMPLE_OUTPUT = {
    "outputs": {
        "processed_result": {"result_id": "res-example-analysis-20260630-001"},
        "figure_record": {
            "figure_id": "fig-example-analysis-20260630-001",
            "path": "figures/fig-example-analysis-20260630-001.png",
            "raw_data_ids": ["raw-example-20260630-001-a1b2c3d4"],
            "sample_ids": ["sample-001"],
        },
        "report_section": {"markdown": "## Analysis\n\nObserved a stable feature."},
        "provenance_record": {
            "workflow": "example_analysis",
            "inputs": {"records": [], "files": []},
            "outputs": {"records": [], "files": []},
            "review_refs": ["review-20260630-001"],
        },
        "memory_candidate": {"status": "draft", "text": "Candidate finding."},
    }
}


def _write_manifest(tmp_path: Path, data: dict = VALID_MANIFEST) -> Path:
    path = tmp_path / "manifest.yml"
    write_yaml(path, data)
    return path


def _write_sample(tmp_path: Path, data: dict = VALID_SAMPLE_OUTPUT) -> Path:
    path = tmp_path / "sample-output.yml"
    write_yaml(path, data)
    return path


def test_add_skills_dry_run_writes_report_for_valid_manifest(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    manifest = _write_manifest(tmp_path)
    sample = _write_sample(tmp_path)

    result = run_skill_dry_run(
        workspace,
        manifest,
        sample_output_path=sample,
        created_at="2026-06-30T12:00:00",
    )
    report = read_yaml(workspace / result.report_path)

    assert result.ok is True
    assert result.dry_run_id == "dryrun-ea-example-analysis-20260630T120000"
    assert report["ok"] is True
    assert report["manifest"]["id"] == "ea.example-analysis"


def test_add_skills_dry_run_rejects_bad_sample_output(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    manifest = _write_manifest(tmp_path)
    sample = _write_sample(
        tmp_path,
        {
            "outputs": {
                "processed_result": {},
                "figure_record": {"figure_id": "fig-001"},
                "report_section": {},
                "provenance_record": {"workflow": "bad"},
                "memory_candidate": {"status": "confirmed"},
            }
        },
    )

    result = run_skill_dry_run(
        workspace,
        manifest,
        sample_output_path=sample,
        created_at="2026-06-30T12:00:00",
    )

    assert result.ok is False
    assert "sample_output_missing_field:processed_result.result_id" in result.errors
    assert "sample_output_missing_field:figure_record.path" in result.errors
    assert "sample_report_section_missing_text" in result.errors
    assert "sample_memory_candidate_must_not_be_confirmed" in result.errors


def test_add_skills_register_updates_project_registry(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    manifest = _write_manifest(tmp_path)
    sample = _write_sample(tmp_path)

    result = register_skill_manifest(
        workspace,
        manifest,
        sample_output_path=sample,
        created_at="2026-06-30T12:00:00",
    )
    index = read_yaml(workspace / "skill-registry" / "index.yml")

    assert result["ok"] is True
    assert result["installed"] is True
    assert index["registry_type"] == "ea_project_skill_registry"
    assert index["skills"][0]["id"] == "ea.example-analysis"
    assert index["skills"][0]["dry_run_report"].endswith(".yml")


def test_add_skills_register_refuses_noncompliant_manifest(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    manifest = _write_manifest(
        tmp_path,
        {
            "ea_skill": {
                "id": "ea.bad-analysis",
                "version": "0.1.0",
                "category": "characterization",
                "input_artifacts": ["raw_spectrum"],
                "output_artifacts": ["processed_result"],
                "review_gates": [],
                "required_indices": [],
            }
        },
    )

    result = register_skill_manifest(
        workspace,
        manifest,
        created_at="2026-06-30T12:00:00",
    )

    assert result["ok"] is False
    assert result["installed"] is False
    assert not (workspace / "skill-registry" / "index.yml").exists()


def test_cli_add_skills_dry_run_and_register(tmp_path: Path, capsys) -> None:
    workspace = tmp_path / "project"
    manifest = _write_manifest(tmp_path)
    sample = _write_sample(tmp_path)

    assert main(["add-skills", "dry-run", str(manifest), "--workspace", str(workspace), "--sample-output", str(sample)]) == 0
    dry_run = json.loads(capsys.readouterr().out)
    assert dry_run["ok"] is True

    assert main(
        [
            "add-skills",
            "register",
            str(manifest),
            "--workspace",
            str(workspace),
            "--sample-output",
            str(sample),
            "--status",
            "sandbox",
        ]
    ) == 0
    registered = json.loads(capsys.readouterr().out)
    assert registered["installed"] is True
    assert registered["record"]["status"] == "sandbox"
