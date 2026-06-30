from __future__ import annotations

import json
import math
from pathlib import Path

from ea.cli import main
from ea.ftir import default_ftir_processing_parameters, inspect_ftir_file
from ea.storage import read_markdown_record, read_yaml


def _json_output(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def _write_ftir_fixture(path: Path) -> Path:
    lines = [
        "# x_unit = cm^-1",
        "# y_label = absorbance",
        "wavenumber absorbance",
    ]
    for index in range(1800):
        wavenumber = 4000.0 - index * 2.0
        baseline = 0.025 + 0.00001 * (4000.0 - wavenumber)
        signal = baseline
        for center, amplitude, width in [
            (3400.0, 0.32, 55.0),
            (2920.0, 0.22, 35.0),
            (1720.0, 0.28, 28.0),
            (1100.0, 0.36, 45.0),
        ]:
            signal += amplitude * math.exp(-((wavenumber - center) ** 2) / (2.0 * width**2))
        lines.append(f"{wavenumber:.2f} {signal:.8f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_inspect_synthetic_ftir_fixture(tmp_path: Path) -> None:
    fixture = _write_ftir_fixture(tmp_path / "synthetic-ftir-spectrum.txt")

    inspection = inspect_ftir_file(fixture)

    assert inspection.file_kind == "ftir"
    assert inspection.row_count == 1800
    assert inspection.x_column_candidate == "wavenumber"
    assert inspection.y_column_candidate == "absorbance"
    assert inspection.x_unit == "cm^-1"
    assert inspection.signal_mode_candidate == "absorbance"
    assert inspection.requires_user_confirmation is True


def test_cli_runs_synthetic_ftir_workflow_end_to_end(tmp_path: Path, capsys) -> None:
    fixture = _write_ftir_fixture(tmp_path / "synthetic-ftir-spectrum.txt")
    workspace = tmp_path / "cli-ftir-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "CLI FTIR Workflow",
            "--slug",
            "cli-ftir-workflow",
            "--direction",
            "FTIR workflow",
            "--material",
            "polymer composite",
            "--experiment-type",
            "materials FTIR characterization",
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
            "ftir",
            "--sample-ref",
            "sample-ftir-001",
            "--experiment-ref",
            "exp-ftir-001",
        ]
    ) == 0
    raw_output = _json_output(capsys)
    raw_metadata = Path(raw_output["metadata"])
    raw_metadata_ref = raw_metadata.relative_to(workspace).as_posix()

    assert raw_output["import_status"] == "imported"
    assert main(["ftir", "inspect", str(workspace), raw_output["project_raw_path"]]) == 0
    inspection = _json_output(capsys)
    assert inspection["file_kind"] == "ftir"
    assert inspection["x_unit"] == "cm^-1"
    assert inspection["signal_mode_candidate"] == "absorbance"

    assert main(
        [
            "review",
            "add",
            str(workspace),
            "--target-type",
            "ftir_columns",
            "--target-ref",
            raw_metadata_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            "x=wavenumber, y=absorbance, unit=cm^-1, signal_mode=absorbance",
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
            "ftir_parameters",
            "--target-ref",
            raw_metadata_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            json.dumps(default_ftir_processing_parameters(), ensure_ascii=False),
        ]
    ) == 0
    parameter_review = _json_output(capsys)
    assert parameter_review["review_status"] == "user_confirmed"

    assert main(
        [
            "ftir",
            "process",
            str(workspace),
            "--metadata",
            raw_metadata_ref,
            "--project-id",
            project_id,
            "--sample-ref",
            "sample-ftir-001",
            "--x-column",
            "wavenumber",
            "--y-column",
            "absorbance",
            "--x-unit",
            "cm^-1",
            "--signal-mode",
            "absorbance",
            "--column-review-ref",
            column_review["review_id"],
            "--parameter-review-ref",
            parameter_review["review_id"],
        ]
    ) == 0
    process_output = _json_output(capsys)
    ftir_metadata = Path(process_output["metadata"])
    ftir = read_yaml(ftir_metadata)

    assert ftir["result_id"].startswith("res-cli-ftir-workflow-ftir-")
    assert ftir["ftir_result_id"] == ftir["result_id"]
    assert ftir["signal_mode"] == "absorbance"
    assert ftir["peak_analysis"]["band_count"] > 0
    assert ftir["peak_analysis"]["possible_interpretations"]
    assert any("builtin_band_windows" in item["assignment_source"] for item in ftir["peak_analysis"]["possible_interpretations"])
    assert (workspace / ftir["outputs"]["peak_table"]).exists()
    assert (workspace / ftir["outputs"]["figure"]).exists()
    figure_record = read_yaml(workspace / "figures" / "index.yml")["figures"][ftir["figure_id"]]
    assert figure_record["style_profile"] == "nature_like_clean"
    assert figure_record["generation"]["parameters"]["signal_mode"] == "absorbance"
    assert ftir["outputs"]["processed_csv"] in figure_record["source_data_refs"]
    assert ftir["outputs"]["peak_table"] in figure_record["source_data_refs"]

    assert main(
        [
            "ftir",
            "report",
            str(workspace),
            "--metadata",
            ftir_metadata.relative_to(workspace).as_posix(),
            "--project-id",
            project_id,
            "--sample-ref",
            "sample-ftir-001",
            "--experiment-ref",
            "exp-ftir-001",
        ]
    ) == 0
    report_output = _json_output(capsys)
    report_frontmatter, report_body = read_markdown_record(Path(report_output["report"]))
    assert report_frontmatter["report_type"] == "ftir_analysis"
    assert "## FTIR band 参数" in report_body
    assert "![FTIR spectrum]" in report_body
    assert "processed CSV" in report_body

    assert main(["healthcheck", str(workspace)]) == 0
    health = _json_output(capsys)
    assert health["status"] == "pass"

    assert main(["eval", "project", str(workspace), "--no-write"]) == 0
    evaluation = _json_output(capsys)
    assert evaluation["status"] == "pass"
    assert evaluation["figures"]["analysis_figure_count"] == 1
    assert evaluation["reports"]["report_count"] == 1


def test_ftir_docs_and_skill_references_are_discoverable() -> None:
    root = Path.cwd()

    readme = (root / "README.md").read_text(encoding="utf-8")
    skill = (root / "skills" / "ea-v0-2" / "SKILL.md").read_text(encoding="utf-8")
    ftir_reference = root / "skills" / "ea-v0-2" / "references" / "ftir-workflow.md"
    registry = read_yaml(root / "skill-registry" / "index.yml")

    assert "ea ftir inspect" in readme
    assert "ea ftir process" in skill
    assert "references/ftir-workflow.md" in skill
    assert ftir_reference.exists()
    assert "signal_mode" in ftir_reference.read_text(encoding="utf-8")
    ftir_record = next(item for item in registry["skills"] if item["id"] == "ea.ftir-analysis")
    assert "Minimal FTIR workflow implemented" in ftir_record["notes"]
