from __future__ import annotations

import json
from pathlib import Path

from ea.cli import main
from ea.pl import default_pl_processing_parameters, inspect_pl_file
from ea.storage import read_markdown_record, read_yaml


FIXTURE_PL = Path("tests/fixtures/public/test-case-001/raw_data/MoS-PL-2(1).txt").resolve()


def _json_output(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def test_inspect_public_pl_fixture() -> None:
    inspection = inspect_pl_file(FIXTURE_PL)

    assert inspection.file_kind == "pl"
    assert inspection.row_count == 8280
    assert inspection.x_column_candidate == "col_0"
    assert inspection.y_column_candidate == "col_1"
    assert inspection.x_unit == "eV"
    assert inspection.requires_user_confirmation is True


def test_cli_runs_public_pl_workflow_end_to_end(tmp_path: Path, capsys) -> None:
    workspace = tmp_path / "cli-pl-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "CLI PL Workflow",
            "--slug",
            "cli-pl-workflow",
            "--direction",
            "PL workflow",
            "--material",
            "MoS2",
            "--experiment-type",
            "CVD and PL",
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
            str(FIXTURE_PL),
            "--characterization-type",
            "pl",
            "--sample-ref",
            "sample-pl-001",
            "--experiment-ref",
            "exp-pl-001",
        ]
    ) == 0
    raw_output = _json_output(capsys)
    raw_metadata = Path(raw_output["metadata"])
    raw_metadata_ref = raw_metadata.relative_to(workspace).as_posix()

    assert raw_output["import_status"] == "imported"
    assert main(["pl", "inspect", str(workspace), raw_output["project_raw_path"]]) == 0
    inspection = _json_output(capsys)
    assert inspection["file_kind"] == "pl"
    assert inspection["x_unit"] == "eV"

    assert main(
        [
            "review",
            "add",
            str(workspace),
            "--target-type",
            "pl_columns",
            "--target-ref",
            raw_metadata_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            "x=col_0, y=col_1, unit=eV",
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
            "pl_parameters",
            "--target-ref",
            raw_metadata_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            json.dumps(default_pl_processing_parameters(), ensure_ascii=False),
        ]
    ) == 0
    parameter_review = _json_output(capsys)
    assert parameter_review["review_status"] == "user_confirmed"

    assert main(
        [
            "pl",
            "process",
            str(workspace),
            "--metadata",
            raw_metadata_ref,
            "--project-id",
            project_id,
            "--sample-ref",
            "sample-pl-001",
            "--x-column",
            "col_0",
            "--y-column",
            "col_1",
            "--x-unit",
            "eV",
            "--column-review-ref",
            column_review["review_id"],
            "--parameter-review-ref",
            parameter_review["review_id"],
        ]
    ) == 0
    process_output = _json_output(capsys)
    pl_metadata = Path(process_output["metadata"])
    pl = read_yaml(pl_metadata)

    assert pl["result_id"].startswith("res-cli-pl-workflow-pl-")
    assert pl["pl_result_id"] == pl["result_id"]
    assert pl["peak_analysis"]["peak_count"] > 0
    assert pl["peak_analysis"]["dominant_peak"]["position_unit"] == "eV"
    assert (workspace / pl["outputs"]["peak_table"]).exists()
    assert (workspace / pl["outputs"]["figure"]).exists()
    figure_record = read_yaml(workspace / "figures" / "index.yml")["figures"][pl["figure_id"]]
    assert figure_record["style_profile"] == "nature_like_clean"
    assert figure_record["generation"]["style_profile"] == "nature_like_clean"
    assert pl["outputs"]["processed_csv"] in figure_record["source_data_refs"]
    assert pl["outputs"]["peak_table"] in figure_record["source_data_refs"]

    assert main(
        [
            "pl",
            "report",
            str(workspace),
            "--metadata",
            pl_metadata.relative_to(workspace).as_posix(),
            "--project-id",
            project_id,
            "--sample-ref",
            "sample-pl-001",
            "--experiment-ref",
            "exp-pl-001",
        ]
    ) == 0
    report_output = _json_output(capsys)
    report_frontmatter, report_body = read_markdown_record(Path(report_output["report"]))
    assert report_frontmatter["report_type"] == "pl_analysis"
    assert "## PL 峰参数" in report_body
    assert "processed CSV" in report_body

    assert main(["healthcheck", str(workspace)]) == 0
    health = _json_output(capsys)
    assert health["status"] == "pass"
