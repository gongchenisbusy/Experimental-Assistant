from __future__ import annotations

import json
import math
from pathlib import Path

from ea.cli import main
from ea.storage import read_markdown_record, read_yaml
from ea.uv_vis import default_uv_vis_processing_parameters, inspect_uv_vis_file


def _json_output(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def _write_uv_vis_fixture(path: Path) -> Path:
    lines = [
        "# x_unit = nm",
        "# y_label = absorbance",
        "wavelength_nm absorbance",
    ]
    for index in range(1300):
        wavelength = 250.0 + index * 0.5
        edge = 0.45 / (1.0 + math.exp((wavelength - 620.0) / 18.0))
        signal = 0.04 + edge
        for center, amplitude, width in [
            (330.0, 0.18, 18.0),
            (520.0, 0.14, 28.0),
        ]:
            signal += amplitude * math.exp(-((wavelength - center) ** 2) / (2.0 * width**2))
        lines.append(f"{wavelength:.2f} {signal:.8f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_uv_vis_tauc_fixture(path: Path) -> Path:
    lines = [
        "# x_unit = eV",
        "# y_label = absorbance",
        "energy_eV absorbance",
    ]
    band_gap = 2.0
    for index in range(360):
        energy = 1.2 + index * 0.008
        absorbance = math.sqrt(max(energy - band_gap, 0.0)) / energy if energy > band_gap else 0.001
        lines.append(f"{energy:.5f} {absorbance:.8f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_inspect_synthetic_uv_vis_fixture(tmp_path: Path) -> None:
    fixture = _write_uv_vis_fixture(tmp_path / "synthetic-uv-vis-spectrum.txt")

    inspection = inspect_uv_vis_file(fixture)

    assert inspection.file_kind == "uv_vis"
    assert inspection.row_count == 1300
    assert inspection.x_column_candidate == "wavelength_nm"
    assert inspection.y_column_candidate == "absorbance"
    assert inspection.x_unit == "nm"
    assert inspection.signal_mode_candidate == "absorbance"
    assert inspection.requires_user_confirmation is True


def test_cli_runs_synthetic_uv_vis_workflow_end_to_end(tmp_path: Path, capsys) -> None:
    fixture = _write_uv_vis_fixture(tmp_path / "synthetic-uv-vis-spectrum.txt")
    workspace = tmp_path / "cli-uv-vis-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "CLI UV-Vis Workflow",
            "--slug",
            "cli-uv-vis-workflow",
            "--direction",
            "UV-Vis workflow",
            "--material",
            "oxide thin film",
            "--experiment-type",
            "materials UV-Vis characterization",
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
            "uv_vis",
            "--sample-ref",
            "sample-uv-vis-001",
            "--experiment-ref",
            "exp-uv-vis-001",
        ]
    ) == 0
    raw_output = _json_output(capsys)
    raw_metadata = Path(raw_output["metadata"])
    raw_metadata_ref = raw_metadata.relative_to(workspace).as_posix()

    assert raw_output["import_status"] == "imported"
    assert main(["uv-vis", "inspect", str(workspace), raw_output["project_raw_path"]]) == 0
    inspection = _json_output(capsys)
    assert inspection["file_kind"] == "uv_vis"
    assert inspection["x_unit"] == "nm"
    assert inspection["signal_mode_candidate"] == "absorbance"

    assert main(
        [
            "review",
            "add",
            str(workspace),
            "--target-type",
            "uv_vis_columns",
            "--target-ref",
            raw_metadata_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            "x=wavelength_nm, y=absorbance, unit=nm, signal_mode=absorbance",
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
            "uv_vis_parameters",
            "--target-ref",
            raw_metadata_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            json.dumps(default_uv_vis_processing_parameters(), ensure_ascii=False),
        ]
    ) == 0
    parameter_review = _json_output(capsys)
    assert parameter_review["review_status"] == "user_confirmed"

    assert main(
        [
            "uv-vis",
            "process",
            str(workspace),
            "--metadata",
            raw_metadata_ref,
            "--project-id",
            project_id,
            "--sample-ref",
            "sample-uv-vis-001",
            "--x-column",
            "wavelength_nm",
            "--y-column",
            "absorbance",
            "--x-unit",
            "nm",
            "--signal-mode",
            "absorbance",
            "--column-review-ref",
            column_review["review_id"],
            "--parameter-review-ref",
            parameter_review["review_id"],
        ]
    ) == 0
    process_output = _json_output(capsys)
    uv_vis_metadata = Path(process_output["metadata"])
    uv_vis = read_yaml(uv_vis_metadata)

    assert uv_vis["result_id"].startswith("res-cli-uv-vis-workflow-uv-vis-")
    assert uv_vis["uv_vis_result_id"] == uv_vis["result_id"]
    assert uv_vis["signal_mode"] == "absorbance"
    assert uv_vis["peak_analysis"]["feature_count"] > 0
    assert uv_vis["peak_analysis"]["edge_estimate"]
    assert uv_vis["peak_analysis"]["possible_interpretations"]
    assert (workspace / uv_vis["outputs"]["peak_table"]).exists()
    assert (workspace / uv_vis["outputs"]["figure"]).exists()
    figure_record = read_yaml(workspace / "figures" / "index.yml")["figures"][uv_vis["figure_id"]]
    assert figure_record["style_profile"] == "nature_like_clean"
    assert figure_record["generation"]["parameters"]["signal_mode"] == "absorbance"
    assert uv_vis["outputs"]["processed_csv"] in figure_record["source_data_refs"]
    assert uv_vis["outputs"]["peak_table"] in figure_record["source_data_refs"]

    assert main(
        [
            "uv-vis",
            "report",
            str(workspace),
            "--metadata",
            uv_vis_metadata.relative_to(workspace).as_posix(),
            "--project-id",
            project_id,
            "--sample-ref",
            "sample-uv-vis-001",
            "--experiment-ref",
            "exp-uv-vis-001",
        ]
    ) == 0
    report_output = _json_output(capsys)
    report_frontmatter, report_body = read_markdown_record(Path(report_output["report"]))
    assert report_frontmatter["report_type"] == "uv_vis_analysis"
    assert "## UV-Vis feature 参数" in report_body
    assert "![UV-Vis spectrum]" in report_body
    assert "processed CSV" in report_body

    assert main(["healthcheck", str(workspace)]) == 0
    health = _json_output(capsys)
    assert health["status"] == "pass"

    assert main(["eval", "project", str(workspace), "--no-write"]) == 0
    evaluation = _json_output(capsys)
    assert evaluation["status"] == "pass"
    assert evaluation["figures"]["analysis_figure_count"] == 1
    assert evaluation["reports"]["report_count"] == 1


def test_uv_vis_tauc_screening_records_reviewed_fit_window(tmp_path: Path, capsys) -> None:
    fixture = _write_uv_vis_tauc_fixture(tmp_path / "synthetic-uv-vis-tauc-spectrum.txt")
    workspace = tmp_path / "uv-vis-tauc-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "UV-Vis Tauc Workflow",
            "--slug",
            "uv-vis-tauc-workflow",
            "--direction",
            "UV-Vis optical gap screening",
            "--material",
            "semiconductor thin film",
            "--experiment-type",
            "UV-Vis Tauc screening",
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
            "uv_vis",
            "--sample-ref",
            "sample-uv-vis-tauc-001",
            "--experiment-ref",
            "exp-uv-vis-tauc-001",
        ]
    ) == 0
    raw_output = _json_output(capsys)
    raw_metadata_ref = Path(raw_output["metadata"]).relative_to(workspace).as_posix()

    assert main(
        [
            "review",
            "add",
            str(workspace),
            "--target-type",
            "uv_vis_columns",
            "--target-ref",
            raw_metadata_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            "x=energy_eV, y=absorbance, unit=eV, signal_mode=absorbance",
        ]
    ) == 0
    column_review = _json_output(capsys)

    parameters = default_uv_vis_processing_parameters()
    parameters["tauc_analysis"].update(
        {
            "enabled": True,
            "transform": "absorbance",
            "transition": "direct_allowed",
            "fit_window_eV": [2.2, 3.0],
            "min_points": 12,
        }
    )
    assert main(
        [
            "review",
            "add",
            str(workspace),
            "--target-type",
            "uv_vis_parameters",
            "--target-ref",
            raw_metadata_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            json.dumps(parameters, ensure_ascii=False),
        ]
    ) == 0
    parameter_review = _json_output(capsys)

    assert main(
        [
            "uv-vis",
            "process",
            str(workspace),
            "--metadata",
            raw_metadata_ref,
            "--project-id",
            project_id,
            "--sample-ref",
            "sample-uv-vis-tauc-001",
            "--x-column",
            "energy_eV",
            "--y-column",
            "absorbance",
            "--x-unit",
            "eV",
            "--signal-mode",
            "absorbance",
            "--parameters-json",
            json.dumps({"tauc_analysis": parameters["tauc_analysis"]}, ensure_ascii=False),
            "--column-review-ref",
            column_review["review_id"],
            "--parameter-review-ref",
            parameter_review["review_id"],
        ]
    ) == 0
    process_output = _json_output(capsys)
    uv_vis_metadata = Path(process_output["metadata"])
    uv_vis = read_yaml(uv_vis_metadata)
    tauc = uv_vis["peak_analysis"]["tauc_analysis"]

    assert tauc["status"] == "screening_fit_recorded"
    assert tauc["transform"] == "absorbance"
    assert tauc["transition"] == "direct_allowed"
    assert tauc["confidence"] == "low"
    assert tauc["fit_window_eV"] == [2.2, 3.0]
    assert abs(tauc["intercept_energy_eV"] - 2.0) < 0.05
    assert tauc["r2"] > 0.999
    assert "Screening Tauc/Kubelka-Munk fit only" in tauc["boundary"]
    assert uv_vis["outputs"]["tauc_table"].endswith("uv_vis_tauc.csv")
    tauc_table = workspace / uv_vis["outputs"]["tauc_table"]
    assert tauc_table.exists()
    assert "tauc_energy_eV,tauc_alpha_proxy,tauc_y,tauc_fit_window" in tauc_table.read_text(encoding="utf-8").splitlines()[0]

    figure_record = read_yaml(workspace / "figures" / "index.yml")["figures"][uv_vis["figure_id"]]
    assert uv_vis["outputs"]["tauc_table"] in figure_record["source_data_refs"]

    assert main(
        [
            "uv-vis",
            "report",
            str(workspace),
            "--metadata",
            uv_vis_metadata.relative_to(workspace).as_posix(),
            "--project-id",
            project_id,
            "--sample-ref",
            "sample-uv-vis-tauc-001",
            "--experiment-ref",
            "exp-uv-vis-tauc-001",
        ]
    ) == 0
    report_output = _json_output(capsys)
    _, report_body = read_markdown_record(Path(report_output["report"]))
    assert "## Tauc/Kubelka-Munk screening" in report_body
    assert "只作为筛查记录" in report_body
    assert "Tauc/Kubelka-Munk table" in report_body


def test_uv_vis_docs_and_skill_references_are_discoverable() -> None:
    root = Path.cwd()

    readme = (root / "README.md").read_text(encoding="utf-8")
    skill = (root / "skills" / "ea-v0-2" / "SKILL.md").read_text(encoding="utf-8")
    uv_vis_reference = root / "skills" / "ea-v0-2" / "references" / "uv-vis-workflow.md"
    registry = read_yaml(root / "skill-registry" / "index.yml")

    assert "ea uv-vis inspect" in readme
    assert "ea uv-vis process" in skill
    assert "references/uv-vis-workflow.md" in skill
    assert uv_vis_reference.exists()
    reference_text = uv_vis_reference.read_text(encoding="utf-8")
    assert "signal_mode" in reference_text
    assert "Tauc/Kubelka-Munk" in reference_text
    uv_vis_record = next(item for item in registry["skills"] if item["id"] == "ea.uv-vis-analysis")
    assert "Minimal UV-Vis workflow implemented" in uv_vis_record["notes"]
    assert "tauc_kubelka_munk_screening" in uv_vis_record["notes"]
