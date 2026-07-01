from __future__ import annotations

import json
from pathlib import Path

from ea.cli import main
from ea.healthcheck import run_healthcheck
from ea.memory import commit_memory_candidate, propose_memory_candidate, review_memory_candidate
from ea.projects import initialize_project
from ea.provenance import write_provenance_entry
from ea.raman import RamanProcessingRequest, default_processing_parameters, process_raman_result
from ea.raw_import import import_raw_file
from ea.references import build_report_reference_block, register_reference
from ea.reports import generate_raman_report
from ea.review import write_review_record
from ea.storage import read_markdown_record, read_yaml, write_markdown_record, write_yaml


FIXTURE_RAW = Path("tests/fixtures/public/test-case-001/raw_data/MoS-2(1).txt").resolve()


def _build_v0_2_raman_project(root: Path) -> dict[str, Path | str]:
    outputs = initialize_project(
        root,
        project_name="MoS2 Healthcheck",
        project_slug="mos2-healthcheck",
        research_direction="Raman audit workflow",
        material_system="MoS2",
        experiment_type="CVD and Raman",
        created_at="2026-06-30T11:00:00",
    )
    project_frontmatter, _ = read_markdown_record(outputs["project"])
    project_id = project_frontmatter["project_id"]
    raw = import_raw_file(
        root,
        FIXTURE_RAW,
        project_id=project_id,
        sample_refs=["sample-001"],
        experiment_refs=["exp-20260630-001"],
        imported_at="2026-06-30T11:05:00",
    )
    column_review = write_review_record(
        root,
        target_type="raman_columns",
        target_ref=raw.metadata_path.relative_to(root).as_posix(),
        user_response="可以，保存",
        reviewed_content="x=col_0, y=col_1, unit=cm^-1",
    )
    parameter_review = write_review_record(
        root,
        target_type="raman_parameters",
        target_ref=raw.metadata_path.relative_to(root).as_posix(),
        user_response="可以，保存",
        reviewed_content=str(default_processing_parameters()),
    )
    result_path = process_raman_result(
        root,
        characterization_metadata_path=raw.metadata_path,
        project_id=project_id,
        sample_refs=["sample-001"],
        request=RamanProcessingRequest(
            x_column="col_0",
            y_column="col_1",
            x_unit="cm^-1",
            processing_parameters=default_processing_parameters(),
            column_review_ref=column_review.stem,
            parameter_review_ref=parameter_review.stem,
        ),
        created_at="2026-06-30T11:10:00",
    )
    report_path = generate_raman_report(
        root,
        project_id=project_id,
        raman_metadata_path=result_path,
        related_experiments=["exp-20260630-001"],
        related_samples=["sample-001"],
        created_at="2026-06-30T11:20:00",
    )
    result = read_yaml(result_path)
    return {
        "project_id": project_id,
        "raw_metadata_path": raw.metadata_path,
        "raw_path": raw.project_raw_path or root / "missing",
        "result_path": result_path,
        "report_path": report_path,
        "figure_id": result["figure_id"],
    }


def _path_ref(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _write_minimal_batch_record(root: Path, built: dict[str, Path | str]) -> dict[str, Path]:
    batch_id = "batch-20260630-001"
    batch_dir = root / "processed" / "batches" / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    record_path = batch_dir / "batch_run.yml"
    summary_path = batch_dir / "batch_summary.md"
    index_path = root / "processed" / "batches" / "index.yml"
    record_ref = _path_ref(root, record_path)
    summary_ref = _path_ref(root, summary_path)
    result_ref = _path_ref(root, Path(built["result_path"]))
    report_ref = _path_ref(root, Path(built["report_path"]))
    metadata_ref = _path_ref(root, Path(built["raw_metadata_path"]))
    record = {
        "schema_version": "0.2",
        "batch_id": batch_id,
        "project_id": built["project_id"],
        "manifest_ref": "",
        "status": "success",
        "item_count": 1,
        "succeeded": 1,
        "failed": 0,
        "create_reports": True,
        "continue_on_error": True,
        "items": [
            {
                "item_id": "raman-001",
                "method": "raman",
                "metadata_ref": metadata_ref,
                "sample_refs": ["sample-001"],
                "experiment_refs": ["exp-20260630-001"],
                "x_column": "col_0",
                "y_column": "col_1",
                "x_unit": "cm^-1",
                "review_refs": [],
                "status": "success",
                "result_metadata_ref": result_ref,
                "report_ref": report_ref,
            }
        ],
        "warnings": [],
        "created_at": "2026-06-30T11:30:00",
        "updated_at": "2026-06-30T11:30:00",
        "provenance_refs": [],
    }
    write_yaml(record_path, record)
    summary_path.write_text(f"# Batch Characterization Summary: {batch_id}\n\n- status: `success`\n", encoding="utf-8")
    write_yaml(
        index_path,
        {
            "schema_version": "0.2",
            "batches": {
                batch_id: {
                    "batch_id": batch_id,
                    "project_id": built["project_id"],
                    "status": "success",
                    "manifest_ref": "",
                    "record_ref": record_ref,
                    "summary_ref": summary_ref,
                    "item_count": 1,
                    "succeeded": 1,
                    "failed": 0,
                    "created_at": "2026-06-30T11:30:00",
                    "updated_at": "2026-06-30T11:30:00",
                }
            },
        },
    )
    provenance_path = write_provenance_entry(
        root,
        workflow="batch_characterization",
        inputs={"records": [], "files": []},
        outputs={"records": [record_ref, summary_ref, "processed/batches/index.yml", result_ref, report_ref], "files": []},
        created_at="2026-06-30T11:31:00",
    )
    record["provenance_refs"] = [provenance_path.stem]
    write_yaml(record_path, record)
    return {"record_path": record_path, "summary_path": summary_path, "index_path": index_path}


def test_healthcheck_passes_complete_v0_2_raman_project(tmp_path: Path) -> None:
    _build_v0_2_raman_project(tmp_path)

    result = run_healthcheck(tmp_path)

    assert result["status"] == "pass"
    assert result["error_count"] == 0


def test_healthcheck_detects_raw_hash_mismatch(tmp_path: Path) -> None:
    built = _build_v0_2_raman_project(tmp_path)
    raw_path = Path(built["raw_path"])
    raw_path.chmod(0o600)
    raw_path.write_text(raw_path.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")

    result = run_healthcheck(tmp_path)
    codes = {finding["code"] for finding in result["findings"]}

    assert result["status"] == "fail"
    assert "raw_hash_mismatch" in codes


def test_healthcheck_detects_report_figure_backlink_mismatch(tmp_path: Path) -> None:
    built = _build_v0_2_raman_project(tmp_path)
    figures_index = tmp_path / "figures" / "index.yml"
    figures = read_yaml(figures_index)
    figures["figures"][built["figure_id"]]["report_id"] = "rpt-wrong-20260630-999"
    write_yaml(figures_index, figures)

    result = run_healthcheck(tmp_path)
    codes = {finding["code"] for finding in result["findings"]}

    assert result["status"] == "fail"
    assert "figure_report_missing" in codes
    assert "report_figure_backlink_mismatch" in codes


def test_healthcheck_detects_broken_batch_links(tmp_path: Path) -> None:
    built = _build_v0_2_raman_project(tmp_path)
    batch_paths = _write_minimal_batch_record(tmp_path, built)
    batch_paths["summary_path"].unlink()
    record = read_yaml(batch_paths["record_path"])
    record["items"][0].pop("result_metadata_ref")
    write_yaml(batch_paths["record_path"], record)

    result = run_healthcheck(tmp_path)
    codes = {finding["code"] for finding in result["findings"]}

    assert result["status"] == "fail"
    assert "batch_summary_missing" in codes
    assert "batch_item_result_ref_missing" in codes


def test_healthcheck_detects_untraceable_material_assignment_metadata(tmp_path: Path) -> None:
    built = _build_v0_2_raman_project(tmp_path)
    metadata_path = Path(built["result_path"])
    metadata = read_yaml(metadata_path)
    assert metadata["peak_analysis"]["assigned_features"]
    metadata["peak_analysis"]["assignment_source"] = ""
    metadata["peak_analysis"]["assigned_features"][0]["assignment_source"] = ""
    write_yaml(metadata_path, metadata)

    result = run_healthcheck(tmp_path)
    codes = {finding["code"] for finding in result["findings"]}

    assert result["status"] == "fail"
    assert "material_assignment_source_missing" in codes
    assert "material_assignment_feature_source_missing" in codes


def test_cli_healthcheck_returns_nonzero_on_failure(tmp_path: Path, capsys) -> None:
    built = _build_v0_2_raman_project(tmp_path)
    figures_index = tmp_path / "figures" / "index.yml"
    figures = read_yaml(figures_index)
    figures["figures"][built["figure_id"]]["path"] = "figures/missing.png"
    write_yaml(figures_index, figures)

    result_code = main(["healthcheck", str(tmp_path)])
    output = json.loads(capsys.readouterr().out)
    codes = {finding["code"] for finding in output["findings"]}

    assert result_code == 2
    assert output["status"] == "fail"
    assert "figure_file_missing" in codes


def _build_memory_reference_project(root: Path) -> dict[str, str]:
    outputs = initialize_project(
        root,
        project_name="Memory Reference Healthcheck",
        project_slug="memory-reference-healthcheck",
        research_direction="traceability audit",
        material_system="MoS2",
        experiment_type="Raman reporting",
        created_at="2026-06-30T12:00:00",
    )
    project_frontmatter, _ = read_markdown_record(outputs["project"])
    project_id = project_frontmatter["project_id"]
    local_pdf = root / "literature" / "fulltext" / "lee-2010.pdf"
    local_pdf.parent.mkdir(parents=True, exist_ok=True)
    local_pdf.write_text("placeholder pdf bytes for healthcheck test", encoding="utf-8")
    reference_path = register_reference(
        root,
        project_id=project_id,
        citation="Lee C. et al. Anomalous lattice vibrations of single- and few-layer MoS2. ACS Nano (2010).",
        doi="10.1021/nn1003937",
        local_path="literature/fulltext/lee-2010.pdf",
        created_at="2026-06-30T12:05:00",
    )
    reference_block = build_report_reference_block(root, [reference_path.stem])
    report_path = root / "reports" / "rpt-memory-reference-healthcheck-20260630-001.md"
    write_markdown_record(
        report_path,
        {
            "report_id": "rpt-memory-reference-healthcheck-20260630-001",
            "project_id": project_id,
            "report_type": "raman_analysis",
            "related_results": [],
            "figure_ids": [],
            "reference_ids": [reference_path.stem],
            "numbered_references": reference_block["numbered_references"],
        },
        f"""
# Report

The interpretation is supported by a registered reference{reference_block["inline_citation"]}.

## References

{reference_block["references_markdown"]}
""",
    )
    write_yaml(
        root / "reports" / "index.yml",
        {
            "schema_version": "0.2",
            "reports": {
                "rpt-memory-reference-healthcheck-20260630-001": {
                    "report_id": "rpt-memory-reference-healthcheck-20260630-001",
                    "path": "reports/rpt-memory-reference-healthcheck-20260630-001.md",
                    "project_id": project_id,
                    "result_ids": [],
                    "figure_ids": [],
                    "sample_ids": [],
                    "experiment_ids": [],
                    "reference_ids": [reference_path.stem],
                }
            },
        },
    )
    provenance_path = write_provenance_entry(
        root,
        workflow="healthcheck_test_source",
        inputs={"records": [], "files": []},
        outputs={"records": ["reports/rpt-memory-reference-healthcheck-20260630-001.md"], "files": []},
        created_at="2026-06-30T12:06:00",
    )
    candidate_path = propose_memory_candidate(
        root,
        project_id=project_id,
        candidate_text="Registered Raman reference supports a cautious layer-related interpretation.",
        source_refs=["reports/rpt-memory-reference-healthcheck-20260630-001.md"],
        provenance_refs=[provenance_path.stem],
        category="interpretation",
        confidence="medium",
        created_at="2026-06-30T12:10:00",
    )
    review_memory_candidate(
        root,
        candidate_path=candidate_path,
        user_response="可以，保存",
        reviewed_content="Registered Raman reference supports a cautious layer-related interpretation.",
        reviewed_at="2026-06-30T12:15:00",
    )
    candidate_frontmatter, _ = read_markdown_record(candidate_path)
    commit_memory_candidate(
        root,
        candidate_path=candidate_path,
        review_ref=candidate_frontmatter["review_refs"][-1],
        committed_at="2026-06-30T12:20:00",
    )
    return {
        "reference_id": reference_path.stem,
        "report_id": "rpt-memory-reference-healthcheck-20260630-001",
        "candidate_ref": candidate_path.relative_to(root).as_posix(),
    }


def test_healthcheck_passes_memory_and_reference_indices(tmp_path: Path) -> None:
    _build_memory_reference_project(tmp_path)

    result = run_healthcheck(tmp_path)

    assert result["status"] == "pass"
    assert result["error_count"] == 0


def test_healthcheck_allows_registered_reference_ids_and_builtin_record_refs(tmp_path: Path) -> None:
    outputs = initialize_project(
        tmp_path,
        project_name="Reference Source Healthcheck",
        project_slug="reference-source-healthcheck",
        research_direction="Reference source ref healthcheck",
        material_system="public example",
        experiment_type="metadata audit",
        created_at="2026-06-30T12:30:00",
    )
    project_frontmatter, _ = read_markdown_record(outputs["project"])
    project_id = project_frontmatter["project_id"]
    reference_path = register_reference(
        tmp_path,
        project_id=project_id,
        reference_id="ref-healthcheck-source-001",
        citation="Healthcheck source reference. Example Journal (2026).",
        title="Healthcheck source reference",
        url="https://example.org/healthcheck-source-reference",
        source_type="manual",
        created_at="2026-06-30T12:31:00",
    )
    write_provenance_entry(
        tmp_path,
        workflow="healthcheck_registered_reference_source",
        inputs={"records": ["builtin:generic_xps_parameters", reference_path.stem], "files": []},
        outputs={"records": ["EA_PROJECT.md"], "files": []},
        created_at="2026-06-30T12:32:00",
    )
    provenance_path = write_provenance_entry(
        tmp_path,
        workflow="healthcheck_memory_source",
        inputs={"records": [], "files": []},
        outputs={"records": ["EA_PROJECT.md"], "files": []},
        created_at="2026-06-30T12:33:00",
    )
    propose_memory_candidate(
        tmp_path,
        project_id=project_id,
        candidate_text="Registered reference_id is valid as a memory source ref.",
        source_refs=[reference_path.stem],
        provenance_refs=[provenance_path.stem],
        category="interpretation",
        confidence="low",
        created_at="2026-06-30T12:34:00",
    )

    result = run_healthcheck(tmp_path)
    codes = {finding["code"] for finding in result["findings"]}

    assert result["status"] == "pass"
    assert "provenance_input_record_missing" not in codes
    assert "memory_candidate_source_ref_missing" not in codes


def test_healthcheck_detects_missing_reference_record_and_bad_report_citations(tmp_path: Path) -> None:
    built = _build_memory_reference_project(tmp_path)
    (tmp_path / "literature" / "references" / f"{built['reference_id']}.yml").unlink()
    report_path = tmp_path / "reports" / f"{built['report_id']}.md"
    frontmatter, body = read_markdown_record(report_path)
    write_markdown_record(report_path, frontmatter, body.replace("[1]", "[2]", 1))

    result = run_healthcheck(tmp_path)
    codes = {finding["code"] for finding in result["findings"]}

    assert result["status"] == "fail"
    assert "reference_record_missing" in codes
    assert "report_reference_numbering_invalid" in codes


def test_healthcheck_detects_broken_committed_memory_refs(tmp_path: Path) -> None:
    built = _build_memory_reference_project(tmp_path)
    (tmp_path / built["candidate_ref"]).unlink()

    result = run_healthcheck(tmp_path)
    codes = {finding["code"] for finding in result["findings"]}

    assert result["status"] == "fail"
    assert "memory_candidate_record_missing" in codes
    assert "memory_candidate_ref_missing" in codes
