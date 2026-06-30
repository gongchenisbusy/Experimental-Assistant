from __future__ import annotations

import json
import math
from pathlib import Path

from ea.cli import main
from ea.storage import read_markdown_record, read_yaml
from ea.thermal import default_thermal_processing_parameters, inspect_thermal_file


def _json_output(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def _write_thermal_fixture(path: Path) -> Path:
    lines = [
        "# temperature_unit = C",
        "# signal_unit = %",
        "# measurement_mode = tga",
        "# technique = TGA",
        "temperature_C mass_percent",
    ]
    for index in range(900):
        temperature = 25.0 + index * (775.0 / 899.0)
        loss_1 = 8.0 / (1.0 + math.exp(-(temperature - 180.0) / 12.0))
        loss_2 = 22.0 / (1.0 + math.exp(-(temperature - 410.0) / 18.0))
        loss_3 = 10.0 / (1.0 + math.exp(-(temperature - 650.0) / 22.0))
        mass = 100.0 - loss_1 - loss_2 - loss_3
        lines.append(f"{temperature:.4f} {mass:.8f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_inspect_synthetic_thermal_fixture(tmp_path: Path) -> None:
    fixture = _write_thermal_fixture(tmp_path / "synthetic-thermal-tga.txt")

    inspection = inspect_thermal_file(fixture)

    assert inspection.file_kind == "thermal_analysis"
    assert inspection.row_count == 900
    assert inspection.temperature_column_candidate == "temperature_C"
    assert inspection.signal_column_candidate == "mass_percent"
    assert inspection.temperature_unit_candidate == "C"
    assert inspection.signal_unit_candidate == "%"
    assert inspection.measurement_mode_candidate == "tga"
    assert inspection.requires_user_confirmation is True


def test_cli_runs_synthetic_thermal_workflow_end_to_end(tmp_path: Path, capsys) -> None:
    fixture = _write_thermal_fixture(tmp_path / "synthetic-thermal-tga.txt")
    workspace = tmp_path / "cli-thermal-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "CLI Thermal Workflow",
            "--slug",
            "cli-thermal-workflow",
            "--direction",
            "thermal analysis workflow",
            "--material",
            "polymer composite",
            "--experiment-type",
            "materials thermal characterization",
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
            "thermal_analysis",
            "--sample-ref",
            "sample-thermal-001",
            "--experiment-ref",
            "exp-thermal-001",
        ]
    ) == 0
    raw_output = _json_output(capsys)
    raw_metadata = Path(raw_output["metadata"])
    raw_metadata_ref = raw_metadata.relative_to(workspace).as_posix()

    assert raw_output["import_status"] == "imported"
    assert main(["thermal", "inspect", str(workspace), raw_output["project_raw_path"]]) == 0
    inspection = _json_output(capsys)
    assert inspection["file_kind"] == "thermal_analysis"
    assert inspection["temperature_unit_candidate"] == "C"
    assert inspection["signal_unit_candidate"] == "%"
    assert inspection["measurement_mode_candidate"] == "tga"

    assert main(
        [
            "review",
            "add",
            str(workspace),
            "--target-type",
            "thermal_columns",
            "--target-ref",
            raw_metadata_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            "temperature=temperature_C, signal=mass_percent, temperature_unit=C, signal_unit=%, mode=tga",
        ]
    ) == 0
    column_review = _json_output(capsys)
    assert column_review["review_status"] == "user_confirmed"

    context_text = "N2 atmosphere; 10 C/min; sample mass and baseline reviewed"
    assert main(
        [
            "review",
            "add",
            str(workspace),
            "--target-type",
            "thermal_context",
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
            "thermal_parameters",
            "--target-ref",
            raw_metadata_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            json.dumps(default_thermal_processing_parameters(), ensure_ascii=False),
        ]
    ) == 0
    parameter_review = _json_output(capsys)
    assert parameter_review["review_status"] == "user_confirmed"

    assert main(
        [
            "thermal",
            "process",
            str(workspace),
            "--metadata",
            raw_metadata_ref,
            "--project-id",
            project_id,
            "--sample-ref",
            "sample-thermal-001",
            "--temperature-column",
            "temperature_C",
            "--signal-column",
            "mass_percent",
            "--temperature-unit",
            "C",
            "--signal-unit",
            "%",
            "--measurement-mode",
            "tga",
            "--context-summary",
            context_text,
            "--column-review-ref",
            column_review["review_id"],
            "--context-review-ref",
            context_review["review_id"],
            "--parameter-review-ref",
            parameter_review["review_id"],
        ]
    ) == 0
    process_output = _json_output(capsys)
    thermal_metadata = Path(process_output["metadata"])
    thermal = read_yaml(thermal_metadata)

    assert thermal["result_id"].startswith("res-cli-thermal-workflow-thermal-analysis-")
    assert thermal["thermal_result_id"] == thermal["result_id"]
    assert thermal["measurement_mode"] == "tga"
    assert thermal["temperature_unit"] == "C"
    assert thermal["signal_unit"] == "%"
    assert thermal["context_summary"] == context_text
    assert thermal["peak_analysis"]["feature_count"] > 0
    assert thermal["peak_analysis"]["mass_summary"]["total_mass_loss_percent"] > 0
    assert thermal["peak_analysis"]["possible_interpretations"]
    assert (workspace / thermal["outputs"]["feature_table"]).exists()
    assert (workspace / thermal["outputs"]["figure"]).exists()
    figure_record = read_yaml(workspace / "figures" / "index.yml")["figures"][thermal["figure_id"]]
    assert figure_record["style_profile"] == "nature_like_clean"
    assert figure_record["generation"]["parameters"]["measurement_mode"] == "tga"
    assert thermal["outputs"]["processed_csv"] in figure_record["source_data_refs"]
    assert thermal["outputs"]["feature_table"] in figure_record["source_data_refs"]

    assert main(
        [
            "thermal",
            "report",
            str(workspace),
            "--metadata",
            thermal_metadata.relative_to(workspace).as_posix(),
            "--project-id",
            project_id,
            "--sample-ref",
            "sample-thermal-001",
            "--experiment-ref",
            "exp-thermal-001",
        ]
    ) == 0
    report_output = _json_output(capsys)
    report_frontmatter, report_body = read_markdown_record(Path(report_output["report"]))
    assert report_frontmatter["report_type"] == "thermal_analysis"
    assert "## Thermal event 参数" in report_body
    assert "![Thermal analysis trace]" in report_body
    assert "processed CSV" in report_body
    assert "动力学参数" in report_body

    assert main(["healthcheck", str(workspace)]) == 0
    health = _json_output(capsys)
    assert health["status"] == "pass"

    assert main(["eval", "project", str(workspace), "--no-write"]) == 0
    evaluation = _json_output(capsys)
    assert evaluation["status"] == "pass"
    assert evaluation["figures"]["analysis_figure_count"] == 1
    assert evaluation["reports"]["report_count"] == 1


def test_thermal_docs_and_skill_references_are_discoverable() -> None:
    root = Path.cwd()

    readme = (root / "README.md").read_text(encoding="utf-8")
    skill = (root / "skills" / "ea-v0-2" / "SKILL.md").read_text(encoding="utf-8")
    thermal_reference = root / "skills" / "ea-v0-2" / "references" / "thermal-workflow.md"
    registry = read_yaml(root / "skill-registry" / "index.yml")

    assert "ea thermal inspect" in readme
    assert "ea thermal process" in skill
    assert "references/thermal-workflow.md" in skill
    assert thermal_reference.exists()
    reference_text = thermal_reference.read_text(encoding="utf-8")
    assert "context_review_ref" in reference_text
    assert "kinetic" in reference_text
    thermal_record = next(item for item in registry["skills"] if item["id"] == "ea.thermal-analysis")
    assert "Minimal thermal analysis workflow implemented" in thermal_record["notes"]
