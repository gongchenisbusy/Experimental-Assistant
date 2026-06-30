from __future__ import annotations

import csv
import json
from pathlib import Path

from ea.cli import main
from ea.storage import read_markdown_record, read_yaml
from ea.xrd import default_xrd_processing_parameters, inspect_xrd_file


FIXTURE_XRD = Path("tests/fixtures/public/test-case-001/raw_data/MoS-XRD-1.txt").resolve()


def _json_output(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def test_inspect_public_xrd_fixture() -> None:
    inspection = inspect_xrd_file(FIXTURE_XRD)

    assert inspection.file_kind == "xrd"
    assert inspection.row_count == 40
    assert inspection.x_column_candidate == "two_theta"
    assert inspection.y_column_candidate == "intensity"
    assert inspection.x_unit == "2theta_deg"
    assert inspection.requires_user_confirmation is True


def test_cli_runs_public_xrd_workflow_end_to_end(tmp_path: Path, capsys) -> None:
    workspace = tmp_path / "cli-xrd-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "CLI XRD Workflow",
            "--slug",
            "mos2-xrd-workflow",
            "--direction",
            "XRD workflow",
            "--material",
            "MoS2",
            "--experiment-type",
            "CVD and XRD",
        ]
    ) == 0
    project = _json_output(capsys)
    project_frontmatter, _ = read_markdown_record(Path(project["project"]))
    project_id = project_frontmatter["project_id"]

    assert main(
        [
            "raw",
            "import",
            str(workspace),
            str(FIXTURE_XRD),
            "--characterization-type",
            "xrd",
            "--sample-ref",
            "sample-xrd-001",
            "--experiment-ref",
            "exp-xrd-001",
        ]
    ) == 0
    raw_output = _json_output(capsys)
    raw_metadata = Path(raw_output["metadata"])
    raw_metadata_ref = raw_metadata.relative_to(workspace).as_posix()

    assert raw_output["import_status"] == "imported"
    assert main(["xrd", "inspect", str(workspace), raw_output["project_raw_path"]]) == 0
    inspection = _json_output(capsys)
    assert inspection["file_kind"] == "xrd"
    assert inspection["x_unit"] == "2theta_deg"

    assert main(
        [
            "review",
            "add",
            str(workspace),
            "--target-type",
            "xrd_columns",
            "--target-ref",
            raw_metadata_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            "x=two_theta, y=intensity, unit=2theta_deg",
        ]
    ) == 0
    column_review = _json_output(capsys)
    assert column_review["review_status"] == "user_confirmed"

    assert main(
        [
            "review",
            "add",
            str(workspace),
            "--target-type",
            "xrd_parameters",
            "--target-ref",
            raw_metadata_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            json.dumps(default_xrd_processing_parameters(), ensure_ascii=False),
        ]
    ) == 0
    parameter_review = _json_output(capsys)
    assert parameter_review["review_status"] == "user_confirmed"

    assert main(
        [
            "xrd",
            "process",
            str(workspace),
            "--metadata",
            raw_metadata_ref,
            "--project-id",
            project_id,
            "--sample-ref",
            "sample-xrd-001",
            "--x-column",
            "two_theta",
            "--y-column",
            "intensity",
            "--x-unit",
            "2theta_deg",
            "--column-review-ref",
            column_review["review_id"],
            "--parameter-review-ref",
            parameter_review["review_id"],
        ]
    ) == 0
    process_output = _json_output(capsys)
    xrd_metadata = Path(process_output["metadata"])
    xrd = read_yaml(xrd_metadata)

    assert xrd["result_id"].startswith("res-mos2-xrd-workflow-xrd-")
    assert xrd["xrd_result_id"] == xrd["result_id"]
    assert xrd["wavelength_angstrom"] == 1.5406
    assert xrd["peak_analysis"]["peak_count"] > 0
    assert xrd["peak_analysis"]["assignment_source"] == "ea.materials.builtin:mos2:xrd:v0.2"
    assert xrd["peak_analysis"]["possible_interpretations"][0]["confidence"] == "medium"
    assert (workspace / xrd["outputs"]["peak_table"]).exists()
    assert (workspace / xrd["outputs"]["figure"]).exists()
    figure_record = read_yaml(workspace / "figures" / "index.yml")["figures"][xrd["figure_id"]]
    assert figure_record["style_profile"] == "nature_like_clean"
    assert figure_record["generation"]["style_profile"] == "nature_like_clean"
    assert xrd["outputs"]["processed_csv"] in figure_record["source_data_refs"]
    assert xrd["outputs"]["peak_table"] in figure_record["source_data_refs"]

    with (workspace / xrd["outputs"]["peak_table"]).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert any(13.5 <= float(row["two_theta_deg"]) <= 15.5 for row in rows)
    assert any("MoS2" in row["possible_phase"] for row in rows)
    assert all("d_spacing_angstrom" in row for row in rows)

    assert main(
        [
            "xrd",
            "report",
            str(workspace),
            "--metadata",
            xrd_metadata.relative_to(workspace).as_posix(),
            "--project-id",
            project_id,
            "--sample-ref",
            "sample-xrd-001",
            "--experiment-ref",
            "exp-xrd-001",
        ]
    ) == 0
    report_output = _json_output(capsys)
    report_frontmatter, report_body = read_markdown_record(Path(report_output["report"]))
    assert report_frontmatter["report_type"] == "xrd_analysis"
    assert "## XRD 峰参数" in report_body
    assert "processed CSV" in report_body

    assert main(["healthcheck", str(workspace)]) == 0
    health = _json_output(capsys)
    assert health["status"] == "pass"
