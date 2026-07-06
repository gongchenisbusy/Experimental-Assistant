from __future__ import annotations

import json
from pathlib import Path

from ea.cli import main
from ea.raman import default_processing_parameters
from ea.storage import read_markdown_record, read_yaml


FIXTURE_RAW = Path("tests/fixtures/public/test-case-001/raw_data/MoS-2(1).txt").resolve()


def _json_output(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def test_cli_runs_public_raman_workflow_end_to_end(tmp_path: Path, capsys) -> None:
    workspace = tmp_path / "cli-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "CLI Raman Workflow",
            "--slug",
            "cli-raman-workflow",
            "--direction",
            "Raman workflow",
            "--material",
            "MoS2",
            "--experiment-type",
            "CVD and Raman",
        ]
    ) == 0
    project = _json_output(capsys)
    assert project["literature_decision_open_item"].endswith(".yml")
    assert project["project_working_memory"].endswith("memory/project-working-memory.md")
    literature_decision = read_yaml(Path(project["literature_decision_open_item"]))
    assert literature_decision["item_type"] == "literature_library_decision"
    assert "ea literature plan" in literature_decision["description"]
    project_frontmatter, _ = read_markdown_record(Path(project["project"]))
    project_id = project_frontmatter["project_id"]

    assert main(
        [
            "raw",
            "import",
            str(workspace),
            str(FIXTURE_RAW),
            "--characterization-type",
            "raman",
            "--sample-ref",
            "sample-cli-001",
            "--experiment-ref",
            "exp-cli-001",
        ]
    ) == 0
    raw_output = _json_output(capsys)
    raw_metadata = Path(raw_output["metadata"])
    raw_metadata_ref = raw_metadata.relative_to(workspace).as_posix()

    assert raw_output["import_status"] == "imported"
    assert raw_output["characterization_id"].startswith("char-")

    assert main(["raman", "inspect", str(workspace), raw_output["project_raw_path"]]) == 0
    inspection = _json_output(capsys)
    assert inspection["file_kind"] == "raman"
    assert inspection["x_column_candidate"] == "col_0"

    assert main(
        [
            "review",
            "add",
            str(workspace),
            "--target-type",
            "raman_columns",
            "--target-ref",
            raw_metadata_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            "x=col_0, y=col_1, unit=cm^-1",
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
            "raman_parameters",
            "--target-ref",
            raw_metadata_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            json.dumps(default_processing_parameters(), ensure_ascii=False),
        ]
    ) == 0
    parameter_review = _json_output(capsys)
    assert parameter_review["review_status"] == "user_confirmed"

    assert main(
        [
            "raman",
            "process",
            str(workspace),
            "--metadata",
            raw_metadata_ref,
            "--project-id",
            project_id,
            "--sample-ref",
            "sample-cli-001",
            "--x-column",
            "col_0",
            "--y-column",
            "col_1",
            "--x-unit",
            "cm^-1",
            "--column-review-ref",
            column_review["review_id"],
            "--parameter-review-ref",
            parameter_review["review_id"],
        ]
    ) == 0
    process_output = _json_output(capsys)
    raman_metadata = Path(process_output["metadata"])
    raman = read_yaml(raman_metadata)
    figure_before_report = (workspace / raman["outputs"]["figure"]).read_bytes()

    assert raman["result_id"].startswith("res-cli-raman-workflow-raman-")
    assert "peak_analysis" in raman
    assert (workspace / raman["outputs"]["peak_table"]).exists()
    warning_codes = {warning["code"] for warning in raman["warnings"]}
    assert "instrument_metadata_missing" in warning_codes
    figure_record = read_yaml(workspace / "figures" / "index.yml")["figures"][raman["figure_id"]]
    assert figure_record["generation"]["parameters"]["plot_layout"] == "processed_main_raw_secondary_axis"

    assert main(
        [
            "raman",
            "report",
            str(workspace),
            "--metadata",
            raman_metadata.relative_to(workspace).as_posix(),
            "--project-id",
            project_id,
            "--sample-ref",
            "sample-cli-001",
            "--experiment-ref",
            "exp-cli-001",
        ]
    ) == 0
    report_output = _json_output(capsys)
    report_frontmatter, report_body = read_markdown_record(Path(report_output["report"]))
    assert report_frontmatter["report_type"] == "raman_analysis"
    assert "## 拟合峰参数" in report_body
    assert "仪器元数据" in report_body
    assert "Automatic peaks were fitted" not in report_body
    assert "No stable Raman peaks" not in report_body
    figure_after_report = (workspace / raman["outputs"]["figure"]).read_bytes()
    assert figure_after_report != figure_before_report
    updated_figure_record = read_yaml(workspace / "figures" / "index.yml")["figures"][raman["figure_id"]]
    assert updated_figure_record["footer"] == f"FigID: {raman['figure_id']} | Report: {report_frontmatter['report_id']}"

    assert main(["healthcheck", str(workspace)]) == 0
    health = _json_output(capsys)
    assert health["status"] == "pass"


def test_cli_boundary_errors_are_json_without_traceback(tmp_path: Path, capsys) -> None:
    workspace = tmp_path / "cli-error-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "CLI Error Project",
            "--slug",
            "cli-error-project",
            "--direction",
            "Raman workflow",
            "--material",
            "MoS2",
            "--experiment-type",
            "CVD and Raman",
        ]
    ) == 0
    capsys.readouterr()
    assert main(
        [
            "raw",
            "import",
            str(workspace),
            str(FIXTURE_RAW),
            "--characterization-type",
            "raman",
        ]
    ) == 0
    raw_output = _json_output(capsys)

    result = main(
        [
            "raman",
            "process",
            str(workspace),
            "--metadata",
            Path(raw_output["metadata"]).relative_to(workspace).as_posix(),
            "--project-id",
            "prj-cli-error-project",
            "--x-column",
            "col_0",
            "--y-column",
            "col_1",
            "--x-unit",
            "cm^-1",
            "--column-review-ref",
            "missing-review",
            "--parameter-review-ref",
            "missing-review",
        ]
    )
    output_text = capsys.readouterr().out
    output = json.loads(output_text)

    assert result == 2
    assert output["status"] == "error"
    assert output["error_type"] == "ReviewRequiredErrorForRef"
    assert "missing-review" in output["message"]
    assert "Traceback" not in output_text
