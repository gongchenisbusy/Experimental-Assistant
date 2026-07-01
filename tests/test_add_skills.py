from __future__ import annotations

import json
from pathlib import Path

from ea.cli import main
from ea.skills import register_skill_manifest, required_outputs_for_manifest, run_skill_dry_run, validate_skill_manifest
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


def test_category_aware_manifest_requirements_accept_non_characterization_skills(tmp_path: Path) -> None:
    literature_manifest = {
        "ea_skill": {
            "id": "ea.test-literature",
            "version": "0.2.0",
            "category": "literature.library",
            "method": "literature",
            "input_artifacts": ["project_context", "user_confirmation"],
            "output_artifacts": ["literature_status", "reference_record", "report_section", "provenance_record"],
            "review_gates": ["confirm_search_scope", "confirm_interpretation_before_memory_write"],
            "required_indices": ["literature/references/index.yml", "reports/index.yml", "provenance/index.yml"],
        }
    }
    figure_manifest = {
        "ea_skill": {
            "id": "ea.test-figure",
            "version": "0.2.0",
            "category": "visualization.figure",
            "method": "scientific_figure",
            "input_artifacts": ["processed_result", "project_context"],
            "output_artifacts": ["figure_record", "report_section", "provenance_record"],
            "review_gates": ["confirm_plot_content", "confirm_interpretation_before_memory_write"],
            "required_indices": ["figures/index.yml", "reports/index.yml", "provenance/index.yml"],
        }
    }
    bad_literature = {
        "ea_skill": {
            **literature_manifest["ea_skill"],
            "id": "ea.bad-literature",
            "output_artifacts": ["literature_status", "report_section", "provenance_record"],
        }
    }

    literature_path = _write_manifest(tmp_path, literature_manifest)
    literature_check = validate_skill_manifest(literature_path)
    assert literature_check.ok is True
    assert "processed_result" not in required_outputs_for_manifest(literature_check.manifest)
    assert "figures/index.yml" not in literature_check.warnings

    figure_path = _write_manifest(tmp_path, figure_manifest)
    figure_check = validate_skill_manifest(figure_path)
    assert figure_check.ok is True
    assert required_outputs_for_manifest(figure_check.manifest) == {
        "figure_record",
        "report_section",
        "provenance_record",
    }

    bad_path = _write_manifest(tmp_path, bad_literature)
    bad_check = validate_skill_manifest(bad_path)
    assert bad_check.ok is False
    assert "missing_output:reference_record" in bad_check.errors
    assert "missing_output:processed_result" not in bad_check.errors


def test_builtin_skill_registry_catalogue_is_valid(tmp_path: Path) -> None:
    registry = read_yaml(Path("skill-registry/index.yml"))
    indexed_paths = {item["manifest"] for item in registry["skills"]}
    builtin_paths = {path.as_posix() for path in Path("skill-registry/builtins").glob("*.yml")}

    assert indexed_paths == builtin_paths
    assert len(indexed_paths) >= 10

    expected_ids = {
        "ea.local-literature-library",
        "ea.scientific-figure",
        "ea.raman-analysis",
        "ea.pl-analysis",
        "ea.xrd-analysis",
        "ea.ftir-analysis",
        "ea.uv-vis-analysis",
        "ea.xps-analysis",
        "ea.electrochemistry-analysis",
        "ea.thermal-analysis",
        "ea.image-analysis",
        "ea.project-traceability",
    }
    assert {item["id"] for item in registry["skills"]} == expected_ids

    for item in registry["skills"]:
        manifest_path = Path(item["manifest"])
        check = validate_skill_manifest(manifest_path)
        dry_run = run_skill_dry_run(
            tmp_path / "project",
            manifest_path,
            created_at="2026-06-30T12:30:00",
        )
        assert check.ok is True, item["id"]
        assert dry_run.ok is True, item["id"]
        assert check.manifest["id"] == item["id"]
        assert check.manifest["category"] == item["category"]


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
