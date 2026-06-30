from __future__ import annotations

import json
import math
from pathlib import Path

from ea.cli import main
from ea.electrochemistry import default_electrochemistry_processing_parameters, inspect_electrochemistry_file
from ea.storage import read_markdown_record, read_yaml


def _json_output(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def _write_electrochemistry_fixture(path: Path) -> Path:
    lines = [
        "# x_unit = V",
        "# current_unit = mA",
        "# measurement_mode = cv",
        "# technique = cyclic voltammetry",
        "potential_V current_mA",
    ]
    for index in range(900):
        potential = -0.2 + index * (1.1 / 899.0)
        baseline = 0.04 * potential
        anodic = 0.82 * math.exp(-((potential - 0.55) ** 2) / (2.0 * 0.035**2))
        cathodic = -0.58 * math.exp(-((potential - 0.16) ** 2) / (2.0 * 0.045**2))
        current = baseline + anodic + cathodic
        lines.append(f"{potential:.6f} {current:.9f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_inspect_synthetic_electrochemistry_fixture(tmp_path: Path) -> None:
    fixture = _write_electrochemistry_fixture(tmp_path / "synthetic-electrochemistry-cv.txt")

    inspection = inspect_electrochemistry_file(fixture)

    assert inspection.file_kind == "electrochemistry"
    assert inspection.row_count == 900
    assert inspection.x_column_candidate == "potential_V"
    assert inspection.y_column_candidate == "current_mA"
    assert inspection.x_unit_candidate == "V"
    assert inspection.current_unit_candidate == "mA"
    assert inspection.measurement_mode_candidate == "cv"
    assert inspection.requires_user_confirmation is True


def test_cli_runs_synthetic_electrochemistry_workflow_end_to_end(tmp_path: Path, capsys) -> None:
    fixture = _write_electrochemistry_fixture(tmp_path / "synthetic-electrochemistry-cv.txt")
    workspace = tmp_path / "cli-electrochemistry-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "CLI Electrochemistry Workflow",
            "--slug",
            "cli-electrochemistry-workflow",
            "--direction",
            "electrochemistry workflow",
            "--material",
            "oxide catalyst",
            "--experiment-type",
            "materials electrochemistry characterization",
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
            str(fixture),
            "--characterization-type",
            "electrochemistry",
            "--sample-ref",
            "sample-ec-001",
            "--experiment-ref",
            "exp-ec-001",
        ]
    ) == 0
    raw_output = _json_output(capsys)
    raw_metadata = Path(raw_output["metadata"])
    raw_metadata_ref = raw_metadata.relative_to(workspace).as_posix()

    assert raw_output["import_status"] == "imported"
    assert main(["electrochemistry", "inspect", str(workspace), raw_output["project_raw_path"]]) == 0
    inspection = _json_output(capsys)
    assert inspection["file_kind"] == "electrochemistry"
    assert inspection["current_unit_candidate"] == "mA"
    assert inspection["measurement_mode_candidate"] == "cv"

    assert main(
        [
            "review",
            "add",
            str(workspace),
            "--target-type",
            "electrochemistry_columns",
            "--target-ref",
            raw_metadata_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            "x=potential_V, y=current_mA, x_unit=V, current_unit=mA, mode=cv",
        ]
    ) == 0
    column_review = _json_output(capsys)
    assert column_review["review_status"] == "user_confirmed"

    context_text = "0.196 cm2 working electrode; Ag/AgCl reference; aqueous electrolyte; scan rate reviewed"
    assert main(
        [
            "review",
            "add",
            str(workspace),
            "--target-type",
            "electrochemistry_context",
            "--target-ref",
            raw_metadata_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            context_text,
        ]
    ) == 0
    context_review = _json_output(capsys)
    assert context_review["review_status"] == "user_confirmed"

    assert main(
        [
            "review",
            "add",
            str(workspace),
            "--target-type",
            "electrochemistry_parameters",
            "--target-ref",
            raw_metadata_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            json.dumps(default_electrochemistry_processing_parameters(), ensure_ascii=False),
        ]
    ) == 0
    parameter_review = _json_output(capsys)
    assert parameter_review["review_status"] == "user_confirmed"

    assert main(
        [
            "electrochemistry",
            "process",
            str(workspace),
            "--metadata",
            raw_metadata_ref,
            "--project-id",
            project_id,
            "--sample-ref",
            "sample-ec-001",
            "--x-column",
            "potential_V",
            "--y-column",
            "current_mA",
            "--x-unit",
            "V",
            "--current-unit",
            "mA",
            "--measurement-mode",
            "cv",
            "--context-summary",
            context_text,
            "--electrode-area-cm2",
            "0.196",
            "--column-review-ref",
            column_review["review_id"],
            "--context-review-ref",
            context_review["review_id"],
            "--parameter-review-ref",
            parameter_review["review_id"],
        ]
    ) == 0
    process_output = _json_output(capsys)
    electrochemistry_metadata = Path(process_output["metadata"])
    electrochemistry = read_yaml(electrochemistry_metadata)

    assert electrochemistry["result_id"].startswith("res-cli-electrochemistry-workflow-electrochemistry-")
    assert electrochemistry["electrochemistry_result_id"] == electrochemistry["result_id"]
    assert electrochemistry["measurement_mode"] == "cv"
    assert electrochemistry["current_unit"] == "mA"
    assert electrochemistry["electrode_area_cm2"] == 0.196
    assert electrochemistry["peak_analysis"]["feature_count"] > 0
    assert electrochemistry["peak_analysis"]["possible_interpretations"]
    assert (workspace / electrochemistry["outputs"]["feature_table"]).exists()
    assert (workspace / electrochemistry["outputs"]["figure"]).exists()
    figure_record = read_yaml(workspace / "figures" / "index.yml")["figures"][electrochemistry["figure_id"]]
    assert figure_record["style_profile"] == "nature_like_clean"
    assert figure_record["generation"]["parameters"]["measurement_mode"] == "cv"
    assert electrochemistry["outputs"]["processed_csv"] in figure_record["source_data_refs"]
    assert electrochemistry["outputs"]["feature_table"] in figure_record["source_data_refs"]

    assert main(
        [
            "electrochemistry",
            "report",
            str(workspace),
            "--metadata",
            electrochemistry_metadata.relative_to(workspace).as_posix(),
            "--project-id",
            project_id,
            "--sample-ref",
            "sample-ec-001",
            "--experiment-ref",
            "exp-ec-001",
        ]
    ) == 0
    report_output = _json_output(capsys)
    report_frontmatter, report_body = read_markdown_record(Path(report_output["report"]))
    assert report_frontmatter["report_type"] == "electrochemistry_analysis"
    assert "## Electrochemistry feature 参数" in report_body
    assert "![Electrochemistry trace]" in report_body
    assert "performance or mechanism" not in report_body
    assert "processed CSV" in report_body

    assert main(["healthcheck", str(workspace)]) == 0
    health = _json_output(capsys)
    assert health["status"] == "pass"

    assert main(["eval", "project", str(workspace), "--no-write"]) == 0
    evaluation = _json_output(capsys)
    assert evaluation["status"] == "pass"
    assert evaluation["figures"]["analysis_figure_count"] == 1
    assert evaluation["reports"]["report_count"] == 1


def test_electrochemistry_docs_and_skill_references_are_discoverable() -> None:
    root = Path.cwd()

    readme = (root / "README.md").read_text(encoding="utf-8")
    skill = (root / "skills" / "ea-v0-2" / "SKILL.md").read_text(encoding="utf-8")
    electrochemistry_reference = root / "skills" / "ea-v0-2" / "references" / "electrochemistry-workflow.md"
    registry = read_yaml(root / "skill-registry" / "index.yml")

    assert "ea electrochemistry inspect" in readme
    assert "ea electrochemistry process" in skill
    assert "references/electrochemistry-workflow.md" in skill
    assert electrochemistry_reference.exists()
    reference_text = electrochemistry_reference.read_text(encoding="utf-8")
    assert "context_review_ref" in reference_text
    assert "EIS fitting" in reference_text
    electrochemistry_record = next(item for item in registry["skills"] if item["id"] == "ea.electrochemistry-analysis")
    assert "Minimal electrochemistry workflow implemented" in electrochemistry_record["notes"]
