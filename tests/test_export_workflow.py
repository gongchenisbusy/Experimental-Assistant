from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path

from ea.batch import run_batch_manifest
from ea.cli import main
from ea.projects import initialize_project
from ea.raman import RamanProcessingRequest, default_processing_parameters, process_raman_result
from ea.raw_import import import_raw_file
from ea.references import register_reference
from ea.reports import generate_raman_report
from ea.review import write_review_record
from ea.storage import read_markdown_record, read_yaml, write_yaml


FIXTURE_RAW = Path("tests/fixtures/public/test-case-001/raw_data/MoS-2(1).txt").resolve()


def _json_output(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build_report_project(root: Path) -> dict[str, str]:
    outputs = initialize_project(
        root,
        project_name="Report Bundle",
        project_slug="report-bundle",
        research_direction="Traceable report export",
        material_system="MoS2",
        experiment_type="CVD and Raman",
        created_at="2026-06-30T15:00:00",
    )
    project_frontmatter, _ = read_markdown_record(outputs["project"])
    project_id = project_frontmatter["project_id"]
    raw = import_raw_file(
        root,
        FIXTURE_RAW,
        project_id=project_id,
        sample_refs=["sample-bundle-001"],
        experiment_refs=["exp-bundle-001"],
        imported_at="2026-06-30T15:05:00",
    )
    raw_metadata_ref = raw.metadata_path.relative_to(root).as_posix()
    column_review = write_review_record(
        root,
        target_type="raman_columns",
        target_ref=raw_metadata_ref,
        user_response="可以，保存",
        reviewed_content="x=col_0, y=col_1, unit=cm^-1",
        reviewed_at="2026-06-30T15:10:00",
    )
    parameter_review = write_review_record(
        root,
        target_type="raman_parameters",
        target_ref=raw_metadata_ref,
        user_response="可以，保存",
        reviewed_content=json.dumps(default_processing_parameters(), ensure_ascii=False),
        reviewed_at="2026-06-30T15:11:00",
    )
    result_path = process_raman_result(
        root,
        characterization_metadata_path=raw.metadata_path,
        project_id=project_id,
        sample_refs=["sample-bundle-001"],
        request=RamanProcessingRequest(
            x_column="col_0",
            y_column="col_1",
            x_unit="cm^-1",
            processing_parameters=default_processing_parameters(),
            column_review_ref=column_review.stem,
            parameter_review_ref=parameter_review.stem,
        ),
        created_at="2026-06-30T15:20:00",
    )
    local_pdf = root / "literature" / "fulltext" / "lee-2010.pdf"
    local_pdf.parent.mkdir(parents=True, exist_ok=True)
    local_pdf.write_text("placeholder local reference file", encoding="utf-8")
    reference_path = register_reference(
        root,
        project_id=project_id,
        citation="Lee C. et al. Anomalous lattice vibrations of single- and few-layer MoS2. ACS Nano (2010).",
        doi="10.1021/nn1003937",
        local_path="literature/fulltext/lee-2010.pdf",
        created_at="2026-06-30T15:25:00",
    )
    report_path = generate_raman_report(
        root,
        project_id=project_id,
        raman_metadata_path=result_path,
        related_experiments=["exp-bundle-001"],
        related_samples=["sample-bundle-001"],
        reference_ids=[reference_path.stem],
        created_at="2026-06-30T15:30:00",
    )
    report_frontmatter, _ = read_markdown_record(report_path)
    result = read_yaml(result_path)
    return {
        "project_id": project_id,
        "report_id": report_frontmatter["report_id"],
        "result_id": result["result_id"],
        "figure_id": result["figure_id"],
        "reference_id": reference_path.stem,
    }


def _build_batch_project(root: Path) -> dict[str, str]:
    outputs = initialize_project(
        root,
        project_name="Batch Bundle",
        project_slug="batch-bundle",
        research_direction="Traceable batch export",
        material_system="MoS2",
        experiment_type="CVD and Raman",
        created_at="2026-06-30T16:00:00",
    )
    project_frontmatter, _ = read_markdown_record(outputs["project"])
    project_id = project_frontmatter["project_id"]
    raw = import_raw_file(
        root,
        FIXTURE_RAW,
        project_id=project_id,
        sample_refs=["sample-batch-bundle-001"],
        experiment_refs=["exp-batch-bundle-001"],
        imported_at="2026-06-30T16:05:00",
    )
    raw_metadata_ref = raw.metadata_path.relative_to(root).as_posix()
    column_review = write_review_record(
        root,
        target_type="raman_columns",
        target_ref=raw_metadata_ref,
        user_response="可以，保存",
        reviewed_content="x=col_0, y=col_1, unit=cm^-1",
        reviewed_at="2026-06-30T16:10:00",
    )
    parameter_review = write_review_record(
        root,
        target_type="raman_parameters",
        target_ref=raw_metadata_ref,
        user_response="可以，保存",
        reviewed_content=json.dumps(default_processing_parameters(), ensure_ascii=False),
        reviewed_at="2026-06-30T16:11:00",
    )
    write_yaml(
        root / "batch_manifest.yml",
        {
            "batch": {
                "project_id": project_id,
                "create_reports": True,
                "continue_on_error": True,
                "items": [
                    {
                        "item_id": "raman-bundle-001",
                        "method": "raman",
                        "metadata": raw_metadata_ref,
                        "sample_refs": ["sample-batch-bundle-001"],
                        "experiment_refs": ["exp-batch-bundle-001"],
                        "x_column": "col_0",
                        "y_column": "col_1",
                        "x_unit": "cm^-1",
                        "column_review_ref": column_review.stem,
                        "parameter_review_ref": parameter_review.stem,
                        "processing_parameters": default_processing_parameters(),
                    }
                ],
            }
        },
    )
    batch = run_batch_manifest(root, Path("batch_manifest.yml"), created_at="2026-06-30T16:20:00")
    record = read_yaml(Path(batch["record"]))
    report_ref = record["items"][0]["report_ref"]
    report_frontmatter, _ = read_markdown_record(root / report_ref)
    return {
        "batch_id": batch["batch_id"],
        "report_id": report_frontmatter["report_id"],
        "record_ref": Path(batch["record"]).relative_to(root).as_posix(),
        "summary_ref": Path(batch["summary"]).relative_to(root).as_posix(),
    }


def test_cli_exports_report_bundle_with_traceable_artifacts(tmp_path: Path, capsys) -> None:
    built = _build_report_project(tmp_path)

    assert main(["export", "report-bundle", str(tmp_path), "--report-id", built["report_id"]]) == 0
    output = _json_output(capsys)
    manifest_path = Path(output["manifest_path"])
    manifest = read_yaml(manifest_path)
    bundle_dir = Path(manifest["bundle_path"])

    assert manifest["status"] == "complete"
    assert manifest["report_id"] == built["report_id"]
    assert manifest["missing_refs"] == []
    assert manifest["artifacts"]["reports"][0]["copied"] is True
    assert manifest["artifacts"]["figures"][0]["label"] == built["figure_id"]
    assert manifest["artifacts"]["results"][0]["label"] == built["result_id"]
    assert len(manifest["artifacts"]["source_data"]) >= 2
    assert manifest["artifacts"]["references"][0]["label"] == built["reference_id"]
    assert manifest["artifacts"]["reference_files"][0]["copied"] is True
    assert manifest["artifacts"]["provenance"]
    assert manifest["provenance_inputs"]

    for group in ["reports", "figures", "source_data", "results", "references", "reference_files", "provenance"]:
        for artifact in manifest["artifacts"][group]:
            if artifact["copied"]:
                assert (bundle_dir / artifact["bundle_ref"]).exists(), artifact


def test_cli_exports_user_readable_report_html_with_embedded_figure(tmp_path: Path, capsys) -> None:
    built = _build_report_project(tmp_path)

    assert main(["export", "report-html", str(tmp_path), "--report-id", built["report_id"]]) == 0
    output = _json_output(capsys)
    html_path = Path(output["html_path"])
    metadata_path = Path(output["metadata_path"])
    html = html_path.read_text(encoding="utf-8")
    metadata = read_yaml(metadata_path)

    assert output["status"] == "complete"
    assert output["export_type"] == "friendly_report_html"
    assert html_path.exists()
    assert metadata_path.exists()
    assert '<img src="data:image/png;base64,' in html
    assert "Canonical Markdown report" in html
    assert built["report_id"] in html
    assert built["figure_id"] in html
    assert "Raman spectrum with processed intensity and detected peaks" in html
    assert "Provenance Summary" in html
    assert output["canonical_report_ref"].startswith("reports/")
    assert metadata["canonical_report_ref"] == output["canonical_report_ref"]
    assert metadata["figures"][0]["figure_id"] == built["figure_id"]
    assert metadata["figures"][0]["embedded"] is True
    assert metadata["citation_check"]["status"] == "pass"


def test_cli_exports_source_backed_report_html_with_references_and_provenance(tmp_path: Path, capsys) -> None:
    project = tmp_path / "public-ftir"
    shutil.copytree(Path("examples/public-ftir-assignment-project"), project)
    report_id = "rpt-public-ftir-assignment-example-20260604-001"

    assert main(["export", "report-html", str(project), "--report-id", report_id]) == 0
    output = _json_output(capsys)
    html = Path(output["html_path"]).read_text(encoding="utf-8")
    metadata = read_yaml(Path(output["metadata_path"]))

    assert output["status"] == "complete"
    assert '<img src="data:image/png;base64,' in html
    assert "fig-public-ftir-assignment-example-ftir-20260604-001" in html
    assert "FTIR spectrum with processed signal" in html
    assert "[1]" in html and "Colthup" in html
    assert "[2]" in html and "Socrates" in html
    assert "Provenance Summary" in html
    assert "sha256:" in html
    assert output["citation_check"] == {
        "status": "pass",
        "body_numbers": [1, 2],
        "reference_numbers": [1, 2],
        "missing_reference_numbers": [],
    }
    assert [reference["number"] for reference in metadata["references"]] == [1, 2]
    assert metadata["provenance"]
    assert metadata["provenance"][0]["workflow"] == "report_generation"
    assert metadata["figures"][0]["source_data_refs"]


def test_cli_exports_report_bundle_zip_archive(tmp_path: Path, capsys) -> None:
    built = _build_report_project(tmp_path)

    assert main(["export", "report-bundle", str(tmp_path), "--report-id", built["report_id"], "--zip"]) == 0
    output = _json_output(capsys)
    manifest = read_yaml(Path(output["manifest_path"]))
    archive_path = Path(output["archive_path"])
    checksum_manifest = read_yaml(Path(output["checksum_manifest_path"]))
    checksum_entries = {item["path"]: item for item in checksum_manifest["files"]}

    assert output["archive_created"] is True
    assert manifest["archive_path"] == str(archive_path)
    assert manifest["archive_ref"] == f"exports/report-bundles/{built['report_id']}.zip"
    assert manifest["checksum_manifest_bundle_ref"] == "bundle_checksums.yml"
    assert archive_path.exists()
    assert Path(output["archive_checksum_path"]).exists()
    assert Path(output["archive_checksum_path"]).read_text(encoding="utf-8").split()[0] == _sha256(archive_path)
    assert checksum_manifest["algorithm"] == "sha256"
    assert checksum_entries["bundle_manifest.yml"]["sha256"] == _sha256(Path(output["manifest_path"]))
    assert checksum_entries["bundle_manifest.yml"]["size_bytes"] == Path(output["manifest_path"]).stat().st_size

    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())

    assert "bundle_manifest.yml" in names
    assert "bundle_checksums.yml" in names
    assert any(name.startswith("reports/") for name in names)
    assert any(name.startswith("figures/") for name in names)
    assert any(name.startswith("source-data/") for name in names)
    assert any(name.startswith("results/") for name in names)
    assert any(name.startswith("references/") for name in names)
    assert any(name.startswith("provenance/") for name in names)


def test_cli_exports_report_bundle_with_focused_trace_view(tmp_path: Path, capsys) -> None:
    built = _build_report_project(tmp_path)

    assert (
        main(
            [
                "export",
                "report-bundle",
                str(tmp_path),
                "--report-id",
                built["report_id"],
                "--include-trace",
                "--zip",
            ]
        )
        == 0
    )
    output = _json_output(capsys)
    manifest = read_yaml(Path(output["manifest_path"]))
    bundle_dir = Path(manifest["bundle_path"])
    checksum_manifest = read_yaml(Path(output["checksum_manifest_path"]))
    checksum_paths = {item["path"] for item in checksum_manifest["files"]}

    assert manifest["trace_export"]["included"] is True
    assert manifest["trace_export"]["strategy"] == "focused_report_trace_view"
    trace_artifact = manifest["artifacts"]["traceability"][0]
    assert trace_artifact["kind"] == "traceability_view"
    assert trace_artifact["label"] == built["report_id"]
    assert trace_artifact["focus_ref"].startswith("reports/")
    assert trace_artifact["canonical_focus_ref"] == trace_artifact["focus_ref"]
    assert trace_artifact["bundle_ref"].startswith("traceability/")
    assert trace_artifact["markdown_bundle_ref"].startswith("traceability/")
    assert "prove scientific conclusions" in " ".join(trace_artifact["boundaries"])
    assert (bundle_dir / trace_artifact["bundle_ref"]).exists()
    assert (bundle_dir / trace_artifact["markdown_bundle_ref"]).exists()
    trace = read_yaml(bundle_dir / trace_artifact["bundle_ref"])
    assert trace["focus_ref"] == trace_artifact["focus_ref"]
    assert trace["canonical_focus_ref"] == trace_artifact["focus_ref"]
    assert trace_artifact["bundle_ref"] in checksum_paths
    assert trace_artifact["markdown_bundle_ref"] in checksum_paths

    with zipfile.ZipFile(Path(output["archive_path"])) as archive:
        names = set(archive.namelist())

    assert trace_artifact["bundle_ref"] in names
    assert trace_artifact["markdown_bundle_ref"] in names


def test_cli_verifies_report_bundle_and_archive_checksums(tmp_path: Path, capsys) -> None:
    built = _build_report_project(tmp_path)
    assert main(["export", "report-bundle", str(tmp_path), "--report-id", built["report_id"], "--zip"]) == 0
    output = _json_output(capsys)
    bundle_dir = Path(output["bundle_path"])
    archive_path = Path(output["archive_path"])

    assert main(["export", "verify-bundle", str(bundle_dir)]) == 0
    bundle_check = _json_output(capsys)
    assert bundle_check["status"] == "pass"
    assert bundle_check["checked_count"] > 0
    assert bundle_check["failures"] == []

    assert main(["export", "verify-archive", str(archive_path)]) == 0
    archive_check = _json_output(capsys)
    assert archive_check["status"] == "pass"
    assert archive_check["actual_sha256"] == _sha256(archive_path)


def test_cli_verify_bundle_reports_hash_mismatch(tmp_path: Path, capsys) -> None:
    built = _build_report_project(tmp_path)
    assert main(["export", "report-bundle", str(tmp_path), "--report-id", built["report_id"]]) == 0
    output = _json_output(capsys)
    bundle_dir = Path(output["bundle_path"])
    report_file = next((bundle_dir / "reports").iterdir())
    report_file.write_text(report_file.read_text(encoding="utf-8") + "\nchanged after export\n", encoding="utf-8")

    assert main(["export", "verify-bundle", str(bundle_dir)]) == 2
    check = _json_output(capsys)
    reasons = {failure["reason"] for failure in check["failures"]}

    assert check["status"] == "fail"
    assert "sha256_mismatch" in reasons
    assert "size_mismatch" in reasons


def test_cli_verify_bundle_reports_missing_file(tmp_path: Path, capsys) -> None:
    built = _build_report_project(tmp_path)
    assert main(["export", "report-bundle", str(tmp_path), "--report-id", built["report_id"]]) == 0
    output = _json_output(capsys)
    bundle_dir = Path(output["bundle_path"])
    next((bundle_dir / "figures").iterdir()).unlink()

    assert main(["export", "verify-bundle", str(bundle_dir)]) == 2
    check = _json_output(capsys)

    assert check["status"] == "fail"
    assert "missing_file" in {failure["reason"] for failure in check["failures"]}


def test_cli_verify_archive_reports_hash_mismatch(tmp_path: Path, capsys) -> None:
    built = _build_report_project(tmp_path)
    assert main(["export", "report-bundle", str(tmp_path), "--report-id", built["report_id"], "--zip"]) == 0
    output = _json_output(capsys)
    archive_path = Path(output["archive_path"])
    archive_path.write_bytes(archive_path.read_bytes() + b"changed after export")

    assert main(["export", "verify-archive", str(archive_path)]) == 2
    check = _json_output(capsys)

    assert check["status"] == "fail"
    assert check["failures"][0]["reason"] == "sha256_mismatch"


def test_cli_exports_batch_bundle_with_nested_report_bundle_zip(tmp_path: Path, capsys) -> None:
    built = _build_batch_project(tmp_path)

    assert main(["export", "batch-bundle", str(tmp_path), "--batch-id", built["batch_id"], "--include-trace", "--zip"]) == 0
    output = _json_output(capsys)
    manifest = read_yaml(Path(output["manifest_path"]))
    bundle_dir = Path(manifest["bundle_path"])
    archive_path = Path(output["archive_path"])
    checksum_manifest = read_yaml(Path(output["checksum_manifest_path"]))
    checksum_entries = {item["path"]: item for item in checksum_manifest["files"]}

    assert manifest["status"] == "complete"
    assert manifest["batch_id"] == built["batch_id"]
    assert manifest["archive_created"] is True
    assert manifest["trace_export"]["included"] is True
    assert manifest["trace_export"]["strategy"] == "nested_report_focused_trace_views"
    assert manifest["trace_export"]["batch_level_trace_included"] is False
    assert archive_path.exists()
    assert Path(output["archive_checksum_path"]).exists()
    assert Path(output["archive_checksum_path"]).read_text(encoding="utf-8").split()[0] == _sha256(archive_path)
    assert checksum_manifest["algorithm"] == "sha256"
    assert checksum_entries["batch_bundle_manifest.yml"]["sha256"] == _sha256(Path(output["manifest_path"]))
    assert {record["kind"] for record in manifest["artifacts"]["batch_records"]} == {
        "batch_index",
        "batch_run",
        "batch_summary",
        "batch_manifest",
    }
    assert all(record["copied"] for record in manifest["artifacts"]["batch_records"])
    assert manifest["artifacts"]["provenance"]
    assert len(manifest["artifacts"]["report_bundles"]) == 1

    nested = manifest["artifacts"]["report_bundles"][0]
    assert nested["label"] == built["report_id"]
    nested_manifest = read_yaml(bundle_dir / nested["manifest_ref"])
    assert nested_manifest["report_id"] == built["report_id"]
    assert nested_manifest["trace_export"]["included"] is True
    assert nested_manifest["artifacts"]["reports"][0]["copied"] is True
    assert nested_manifest["artifacts"]["figures"]
    assert nested_manifest["artifacts"]["source_data"]
    assert nested_manifest["artifacts"]["results"]
    assert nested_manifest["artifacts"]["traceability"]
    nested_trace = nested_manifest["artifacts"]["traceability"][0]
    assert nested_trace["focus_ref"].startswith("reports/")
    assert nested_trace["bundle_ref"].startswith("traceability/")
    assert nested["traceability"][0]["bundle_ref"] == nested_trace["bundle_ref"]
    nested_checksum_path = bundle_dir / nested["bundle_ref"] / "bundle_checksums.yml"
    nested_checksum = read_yaml(nested_checksum_path)
    nested_entries = {item["path"]: item for item in nested_checksum["files"]}
    assert nested_entries["bundle_manifest.yml"]["sha256"] == _sha256(bundle_dir / nested["manifest_ref"])

    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())

    assert "batch_bundle_manifest.yml" in names
    assert "bundle_checksums.yml" in names
    assert any(name.startswith("batch/") for name in names)
    assert any(name.startswith("report-bundles/") and name.endswith("bundle_manifest.yml") for name in names)
    assert any(name.startswith("report-bundles/") and name.endswith("bundle_checksums.yml") for name in names)
    assert any(name.startswith("report-bundles/") and "/figures/" in name for name in names)
    assert any(name.startswith("report-bundles/") and "/traceability/" in name for name in names)


def test_export_report_bundle_returns_nonzero_for_unknown_report(tmp_path: Path, capsys) -> None:
    _build_report_project(tmp_path)

    assert main(["export", "report-bundle", str(tmp_path), "--report-id", "rpt-missing"]) == 2
    output = _json_output(capsys)

    assert output["status"] == "fail"
    assert "Unknown report_id" in output["error"]


def test_export_batch_bundle_returns_nonzero_for_unknown_batch(tmp_path: Path, capsys) -> None:
    _build_batch_project(tmp_path)

    assert main(["export", "batch-bundle", str(tmp_path), "--batch-id", "batch-missing"]) == 2
    output = _json_output(capsys)

    assert output["status"] == "fail"
    assert "Unknown batch_id" in output["error"]


def test_report_bundle_warns_when_linked_reference_file_is_missing(tmp_path: Path, capsys) -> None:
    built = _build_report_project(tmp_path)
    (tmp_path / "literature" / "fulltext" / "lee-2010.pdf").unlink()

    assert main(["export", "report-bundle", str(tmp_path), "--report-id", built["report_id"]]) == 1
    output = _json_output(capsys)

    assert output["status"] == "warning"
    missing = {(item["kind"], item["reason"]) for item in output["missing_refs"]}
    assert ("reference_file", "missing_source") in missing
