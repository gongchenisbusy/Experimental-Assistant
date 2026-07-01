from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from ea.cli import main
from ea.references import register_reference
from ea.storage import read_markdown_record, read_yaml, write_yaml
from ea.uv_vis import build_uv_vis_source_packet, default_uv_vis_processing_parameters, inspect_uv_vis_file


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


def test_uv_vis_derivative_screening_records_gradient_table(tmp_path: Path, capsys) -> None:
    fixture = _write_uv_vis_fixture(tmp_path / "synthetic-uv-vis-derivative-spectrum.txt")
    workspace = tmp_path / "uv-vis-derivative-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "UV-Vis Derivative Workflow",
            "--slug",
            "uv-vis-derivative-workflow",
            "--direction",
            "UV-Vis derivative screening",
            "--material",
            "semiconductor thin film",
            "--experiment-type",
            "UV-Vis derivative screening",
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
            "sample-uv-vis-derivative-001",
            "--experiment-ref",
            "exp-uv-vis-derivative-001",
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
            "x=wavelength_nm, y=absorbance, unit=nm, signal_mode=absorbance",
        ]
    ) == 0
    column_review = _json_output(capsys)

    parameters = default_uv_vis_processing_parameters()
    parameters["derivative_analysis"].update(
        {
            "enabled": True,
            "axis": "energy_eV",
            "min_points": 20,
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
            "sample-uv-vis-derivative-001",
            "--x-column",
            "wavelength_nm",
            "--y-column",
            "absorbance",
            "--x-unit",
            "nm",
            "--signal-mode",
            "absorbance",
            "--parameters-json",
            json.dumps({"derivative_analysis": parameters["derivative_analysis"]}, ensure_ascii=False),
            "--column-review-ref",
            column_review["review_id"],
            "--parameter-review-ref",
            parameter_review["review_id"],
        ]
    ) == 0
    process_output = _json_output(capsys)
    uv_vis_metadata = Path(process_output["metadata"])
    uv_vis = read_yaml(uv_vis_metadata)
    derivative = uv_vis["peak_analysis"]["derivative_analysis"]

    assert derivative["status"] == "screening_derivative_recorded"
    assert derivative["axis"] == "energy_eV"
    assert derivative["axis_unit"] == "eV"
    assert derivative["confidence"] == "low"
    assert derivative["max_abs_slope"]["energy_eV"] is not None
    assert "screening-only" in derivative["boundary"]
    assert uv_vis["outputs"]["derivative_table"].endswith("uv_vis_derivative.csv")
    derivative_table = workspace / uv_vis["outputs"]["derivative_table"]
    assert derivative_table.exists()
    derivatives = pd.read_csv(derivative_table)
    assert {"derivative_axis", "first_derivative", "second_derivative", "assignment_source"}.issubset(derivatives.columns)
    assert derivatives["first_derivative"].notna().any()

    figure_record = read_yaml(workspace / "figures" / "index.yml")["figures"][uv_vis["figure_id"]]
    assert uv_vis["outputs"]["derivative_table"] in figure_record["source_data_refs"]

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
            "sample-uv-vis-derivative-001",
            "--experiment-ref",
            "exp-uv-vis-derivative-001",
        ]
    ) == 0
    report_output = _json_output(capsys)
    _, report_body = read_markdown_record(Path(report_output["report"]))
    assert "## Derivative screening" in report_body
    assert "derivative table" in report_body
    assert "谱肩、边缘或拐点候选区域" in report_body


def test_uv_vis_correction_context_records_reviewed_metadata(tmp_path: Path, capsys) -> None:
    fixture = _write_uv_vis_fixture(tmp_path / "synthetic-uv-vis-correction-context-spectrum.txt")
    workspace = tmp_path / "uv-vis-correction-context-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "UV-Vis Correction Context Workflow",
            "--slug",
            "uv-vis-correction-context-workflow",
            "--direction",
            "UV-Vis correction context screening",
            "--material",
            "semiconductor thin film on quartz",
            "--experiment-type",
            "UV-Vis correction context record",
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
            "sample-uv-vis-correction-001",
            "--experiment-ref",
            "exp-uv-vis-correction-001",
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
            "x=wavelength_nm, y=absorbance, unit=nm, signal_mode=absorbance",
        ]
    ) == 0
    column_review = _json_output(capsys)

    parameters = default_uv_vis_processing_parameters()
    parameters["correction_context"].update(
        {
            "enabled": True,
            "sample_geometry": {"sample_form": "thin_film", "path_length": "not_applicable"},
            "substrate": {"material": "quartz", "status": "reviewed", "subtraction": "not_applied"},
            "reference": {"reference_type": "blank_quartz", "reference_ref": "user-reviewed blank spectrum", "status": "reviewed"},
            "background": {"background_ref": "instrument dark baseline", "status": "reviewed", "numeric_correction": "instrument_applied"},
            "diffuse_reflectance": {"integrating_sphere": False, "kubelka_munk_context": "not_used"},
            "correction_notes": ["No numeric correction applied by EA; context recorded for interpretation."],
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
            "sample-uv-vis-correction-001",
            "--x-column",
            "wavelength_nm",
            "--y-column",
            "absorbance",
            "--x-unit",
            "nm",
            "--signal-mode",
            "absorbance",
            "--parameters-json",
            json.dumps({"correction_context": parameters["correction_context"]}, ensure_ascii=False),
            "--column-review-ref",
            column_review["review_id"],
            "--parameter-review-ref",
            parameter_review["review_id"],
        ]
    ) == 0
    process_output = _json_output(capsys)
    uv_vis_metadata = Path(process_output["metadata"])
    uv_vis = read_yaml(uv_vis_metadata)
    correction_context = uv_vis["peak_analysis"]["correction_context"]

    assert correction_context["status"] == "reviewed_correction_context_recorded"
    assert correction_context["confidence"] == "low"
    assert "substrate" in correction_context["reviewed_context_fields"]
    assert correction_context["substrate"]["material"] == "quartz"
    assert "metadata/provenance record only" in correction_context["boundary"]
    assert uv_vis["outputs"]["correction_context"].endswith("uv_vis_correction_context.yml")
    correction_record = read_yaml(workspace / uv_vis["outputs"]["correction_context"])
    assert correction_record["reference"]["reference_type"] == "blank_quartz"
    assert correction_record["record_ref"] == uv_vis["outputs"]["correction_context"]

    figure_record = read_yaml(workspace / "figures" / "index.yml")["figures"][uv_vis["figure_id"]]
    assert uv_vis["outputs"]["correction_context"] in figure_record["source_data_refs"]

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
            "sample-uv-vis-correction-001",
            "--experiment-ref",
            "exp-uv-vis-correction-001",
        ]
    ) == 0
    report_output = _json_output(capsys)
    _, report_body = read_markdown_record(Path(report_output["report"]))
    assert "## Correction context 记录" in report_body
    assert "quartz" in report_body
    assert "correction context" in report_body
    assert "不执行自动数值校正" in report_body


def test_uv_vis_source_packet_template_contains_expected_candidate_types(tmp_path: Path) -> None:
    result = build_uv_vis_source_packet(
        tmp_path,
        project_id="prj-uv-vis-source-packet-template",
        template=True,
        created_at="2026-07-01T20:00:00",
    )

    packet_path = Path(result["source_packet"])
    packet = read_yaml(packet_path)

    assert packet_path == tmp_path / "templates" / "uv_vis_source_packet.yml"
    assert result["status"] == "template_requires_user_edit"
    assert packet["source"] == "ea.uv_vis.source_packet:v0.2"
    assert packet["source_library_kind"] == "template"
    assert packet["candidate_count"] == 4
    assert {
        "optical_transition_model",
        "optical_gap_candidate",
        "optical_feature_assignment",
        "correction_context_candidate",
    } == {candidate["candidate_type"] for candidate in packet["candidates"]}
    assert "does not perform live lookup" in " ".join(packet["boundaries"])
    assert (tmp_path / packet["provenance_ref"]).exists()


def test_cli_uv_vis_builds_source_packet_from_confirmed_literature_manifest(tmp_path: Path, capsys) -> None:
    workspace = tmp_path / "uv-vis-source-packet-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "UV Vis Source Packet",
            "--slug",
            "uv-vis-source-packet",
            "--direction",
            "source-backed UV-Vis interpretation",
            "--material",
            "oxide semiconductor film",
            "--experiment-type",
            "UV-Vis source packet staging",
        ]
    ) == 0
    project = _json_output(capsys)
    project_frontmatter, _ = read_markdown_record(Path(project["project"]))
    project_id = project_frontmatter["project_id"]
    manifest_path = workspace / "literature" / "confirmed_uv_vis_source_candidates.yml"
    write_yaml(
        manifest_path,
        {
            "schema_version": "0.2",
            "source": "ea.literature.source_candidates:v0.2",
            "project_id": project_id,
            "method_scope": ["uv_vis"],
            "confirmed_for_source_packet": True,
            "confirmation_status": "confirmed",
            "reference_seeds": {
                "ref-uv-gap": {
                    "title": "Optical gap reporting for oxide semiconductor films",
                    "authors": ["A. Source"],
                    "year": 2025,
                    "doi": "10.1000/uv-gap",
                },
                "ref-unused": {
                    "title": "Unused UV-Vis source",
                    "authors": ["U. Source"],
                    "year": 2024,
                },
            },
            "guidance_notes": ["Use comparable sample geometry before discussing UV-Vis optical-gap candidates."],
            "candidates": [
                {
                    "candidate_id": "uv-gap-001",
                    "method": "uv_vis",
                    "include_in_source_packet": True,
                    "candidate_type": "optical_gap_candidate",
                    "optical_target": "absorption edge screening",
                    "reported_energy_eV": 3.18,
                    "energy_window_eV": [3.05, 3.30],
                    "transition_assumption": "direct-allowed Tauc-style screening context from the cited source",
                    "source_summary": "Comparable oxide film source reports an optical-gap candidate.",
                    "applicability_notes": ["Use only after checking substrate/background and transition assumptions."],
                    "reference_ids": ["ref-uv-gap"],
                    "confidence": "medium",
                    "caveats": ["Source-backed candidate only; not a definitive band-gap proof."],
                },
                {
                    "candidate_id": "uv-transition-001",
                    "method": "uv_vis",
                    "include_in_source_packet": True,
                    "candidate_type": "optical_transition_model",
                    "optical_target": "transition model",
                    "transition_model": "direct_allowed",
                    "transition_assumption": "Use only after the user confirms model context.",
                    "source_summary": "A source-backed transition-model candidate.",
                    "applicability_notes": ["Review model assumptions before use."],
                    "reference_ids": ["ref-uv-gap"],
                    "confidence": "low",
                    "caveats": ["Model staging only."],
                },
                {
                    "candidate_id": "uv-excluded-001",
                    "method": "uv_vis",
                    "include_in_source_packet": False,
                    "candidate_type": "correction_context_candidate",
                },
            ],
        },
    )

    assert main(
        [
            "uv-vis",
            "build-source-packet",
            str(workspace),
            "--literature-manifest",
            "literature/confirmed_uv_vis_source_candidates.yml",
            "--candidate-type",
            "optical_gap_candidate",
            "--output",
            "suggestions/uv_vis/source-packets/literature_uv_vis_packet.yml",
        ]
    ) == 0
    output = _json_output(capsys)
    packet_path = workspace / "suggestions" / "uv_vis" / "source-packets" / "literature_uv_vis_packet.yml"
    packet = read_yaml(packet_path)
    provenance = read_yaml(workspace / packet["provenance_ref"])

    assert output["status"] == "staged_for_future_uv_vis_suggestions"
    assert output["source_library_kind"] == "confirmed_literature_manifest"
    assert packet["source_library_ref"] == "literature/confirmed_uv_vis_source_candidates.yml"
    assert packet["source_manifest_ref"] == "literature/confirmed_uv_vis_source_candidates.yml"
    assert packet["confirmation_status"] == "confirmed"
    assert packet["candidate_count"] == 1
    assert packet["candidates"][0]["candidate_id"] == "uv-gap-001"
    assert packet["candidates"][0]["candidate_type"] == "optical_gap_candidate"
    assert packet["reference_ids"] == ["ref-uv-gap"]
    assert packet["reference_seed_count"] == 1
    assert "ref-uv-gap" in packet["reference_seeds"]
    assert "ref-unused" not in packet["reference_seeds"]
    assert packet["filters"]["candidate_types"] == ["optical_gap_candidate"]
    assert "future UV-Vis suggestion/review/report workflow" in " ".join(packet["next_steps"])
    assert "does not register references" in " ".join(packet["boundaries"])
    assert provenance["workflow"] == "uv_vis_source_packet"
    assert provenance["source_refs"] == ["ref-uv-gap"]
    assert Path(output["provenance"]).exists()


def test_cli_uv_vis_suggests_source_backed_interpretations(tmp_path: Path, capsys) -> None:
    workspace = tmp_path / "uv-vis-interpretation-suggestion-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "UV Vis Interpretation Suggestions",
            "--slug",
            "uv-vis-interpretation-suggestions",
            "--direction",
            "source-backed UV-Vis interpretation suggestions",
            "--material",
            "oxide semiconductor film on quartz",
            "--experiment-type",
            "UV-Vis source-backed suggestions",
        ]
    ) == 0
    project = _json_output(capsys)
    project_frontmatter, _ = read_markdown_record(Path(project["project"]))
    project_id = project_frontmatter["project_id"]
    register_reference(
        workspace,
        project_id=project_id,
        reference_id="ref-uv-gap",
        citation="A. Source. Optical gap reporting for oxide films. Example Journal (2025).",
        title="Optical gap reporting for oxide films",
        authors=["A. Source"],
        year=2025,
        doi="10.1000/uv-gap",
        source_type="manual",
        created_at="2026-07-01T21:00:00",
    )

    result_dir = workspace / "processed" / "sample-uv-suggestion-001" / "uv_vis" / "res-uv-vis-source-suggestion"
    features_path = result_dir / "uv_vis_features.csv"
    tauc_path = result_dir / "uv_vis_tauc.csv"
    derivative_path = result_dir / "uv_vis_derivative.csv"
    correction_path = result_dir / "uv_vis_correction_context.yml"
    metadata_path = result_dir / "uv_vis_metadata.yml"
    features_ref = features_path.relative_to(workspace).as_posix()
    tauc_ref = tauc_path.relative_to(workspace).as_posix()
    derivative_ref = derivative_path.relative_to(workspace).as_posix()
    correction_ref = correction_path.relative_to(workspace).as_posix()
    metadata_ref = metadata_path.relative_to(workspace).as_posix()

    result_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "feature_id": "uvvis-feature-001",
                "position": 590.0,
                "position_unit": "nm",
                "wavelength_nm": 590.0,
                "energy_eV": 2.10,
                "raw_signal": 0.2,
                "processed_signal": 1.0,
                "detection_height": 1.0,
                "prominence": 0.3,
                "method": "scipy_find_peaks",
                "signal_mode": "absorbance",
                "feature_type": "absorbance_maximum",
                "assignment_confidence": "low",
                "assignment_source": "ea.uv_vis.feature_detection:v0.2",
                "notes": "fixture feature for source-backed suggestion matching",
            }
        ]
    ).to_csv(features_path, index=False)
    pd.DataFrame([{"energy_eV": 2.12, "tauc_fit_window": True}]).to_csv(tauc_path, index=False)
    pd.DataFrame([{"energy_eV": 2.11, "first_derivative": 0.8}]).to_csv(derivative_path, index=False)
    write_yaml(
        correction_path,
        {
            "record_id": "uv-vis-correction-context-test",
            "record_ref": correction_ref,
            "reviewed_context_fields": ["substrate", "reference"],
            "confidence": "low",
        },
    )
    write_yaml(
        metadata_path,
        {
            "schema_version": "0.2",
            "source": "ea.uv_vis.processing_result:v0.2",
            "project_id": project_id,
            "result_id": "res-uv-vis-source-suggestion",
            "uv_vis_result_id": "res-uv-vis-source-suggestion",
            "sample_refs": ["sample-uv-suggestion-001"],
            "outputs": {
                "metadata": metadata_ref,
                "peak_table": features_ref,
                "tauc_table": tauc_ref,
                "derivative_table": derivative_ref,
                "correction_context": correction_ref,
            },
            "peak_analysis": {
                "edge_estimate": {"energy_eV": 2.08, "wavelength_nm": 596.1, "confidence": "low"},
                "tauc_analysis": {
                    "status": "screening_fit_recorded",
                    "intercept_energy_eV": 2.12,
                    "transition": "direct_allowed",
                    "transform": "absorbance",
                    "confidence": "low",
                    "table_ref": tauc_ref,
                },
                "derivative_analysis": {
                    "status": "screening_derivative_recorded",
                    "max_abs_slope": {"energy_eV": 2.11},
                    "confidence": "low",
                    "table_ref": derivative_ref,
                },
                "correction_context": {
                    "status": "reviewed_correction_context_recorded",
                    "record_ref": correction_ref,
                    "reviewed_context_fields": ["substrate", "reference"],
                    "confidence": "low",
                },
            },
        },
    )

    packet_path = workspace / "suggestions" / "uv_vis" / "source-packets" / "uv_vis_source_packet.yml"
    packet_ref = packet_path.relative_to(workspace).as_posix()
    write_yaml(
        packet_path,
        {
            "schema_version": "0.2",
            "source_packet_id": "uv-vis-source-packet-test",
            "project_id": project_id,
            "source": "ea.uv_vis.source_packet:v0.2",
            "status": "staged_for_future_uv_vis_suggestions",
            "candidates": [
                {
                    "candidate_id": "uv-gap-ready",
                    "candidate_type": "optical_gap_candidate",
                    "optical_target": "absorption edge screening",
                    "reported_energy_eV": 2.10,
                    "energy_window_eV": [2.0, 2.2],
                    "transition_assumption": "direct-allowed Tauc-style screening context from the cited source",
                    "expected_feature": "absorbance_maximum",
                    "source_summary": "Comparable oxide film source reports an optical-gap candidate near this energy.",
                    "applicability_notes": ["Use only after checking substrate/background and transition assumptions."],
                    "reference_ids": ["ref-uv-gap"],
                    "confidence": "medium",
                    "caveats": ["Source-backed candidate only; not a definitive band-gap proof."],
                },
                {
                    "candidate_id": "uv-feature-ready",
                    "candidate_type": "optical_feature_assignment",
                    "optical_target": "visible absorption feature",
                    "feature_label": "source-backed visible absorbance maximum",
                    "energy_window_eV": [2.05, 2.15],
                    "wavelength_window_nm": [580.0, 600.0],
                    "expected_feature": "absorbance_maximum",
                    "source_summary": "Source describes a comparable absorbance feature in the visible region.",
                    "applicability_notes": ["Review overlap with scattering and substrate absorption."],
                    "reference_ids": ["ref-uv-gap"],
                    "confidence": "medium",
                    "caveats": ["Feature match alone does not prove mechanism."],
                },
                {
                    "candidate_id": "uv-correction-ready",
                    "candidate_type": "correction_context_candidate",
                    "optical_target": "substrate correction context",
                    "correction_context_type": "substrate",
                    "correction_method": "source-backed substrate/reference context",
                    "source_summary": "Source discusses substrate/reference handling for comparable thin films.",
                    "applicability_notes": ["Use only as interpretation context unless a numeric correction protocol is reviewed."],
                    "reference_ids": ["ref-uv-gap"],
                    "confidence": "low",
                    "caveats": ["This suggestion does not apply any numeric correction."],
                },
                {
                    "candidate_id": "uv-transition-unresolved",
                    "candidate_type": "optical_transition_model",
                    "optical_target": "Tauc transition model",
                    "transition_model": "direct_allowed",
                    "transition_assumption": "Review whether direct-allowed screening is appropriate.",
                    "source_summary": "A source-backed transition-model candidate with an unresolved reference.",
                    "applicability_notes": ["Register the missing reference before use in reports."],
                    "reference_ids": ["ref-missing"],
                    "confidence": "low",
                    "caveats": ["Unresolved source; advisory only."],
                },
                {
                    "candidate_id": "uv-feature-no-match",
                    "candidate_type": "optical_feature_assignment",
                    "optical_target": "near-UV absorption feature",
                    "feature_label": "source-backed near-UV feature with no current match",
                    "energy_window_eV": [3.0, 3.2],
                    "expected_feature": "absorbance_maximum",
                    "source_summary": "Source describes a comparable near-UV feature that is absent from the current processed spectrum.",
                    "applicability_notes": ["Keep as no-match context unless processing or candidate windows change."],
                    "reference_ids": ["ref-uv-gap"],
                    "confidence": "low",
                    "caveats": ["No current processed evidence match."],
                },
                {
                    "candidate_id": "uv-gap-invalid",
                    "candidate_type": "optical_gap_candidate",
                    "optical_target": "invalid source metadata fixture",
                    "reported_energy_eV": 2.1,
                    "energy_window_eV": [2.0, 2.2],
                    "transition_assumption": "direct-allowed screening context",
                    "applicability_notes": ["Deliberately missing source summary for validation."],
                    "reference_ids": ["ref-uv-gap"],
                    "confidence": "low",
                    "caveats": ["Invalid test fixture."],
                },
            ],
        },
    )

    assert main(
        [
            "uv-vis",
            "suggest-interpretations",
            str(workspace),
            "--metadata",
            metadata_ref,
            "--source-file",
            packet_ref,
            "--related-record",
            "raw/uv_vis/char-test/metadata.yml",
        ]
    ) == 0
    output = _json_output(capsys)
    record = read_yaml(Path(output["record"]))
    table = pd.read_csv(Path(output["table"]))
    provenance = read_yaml(Path(output["provenance"]))

    assert output["status"] == "ready_for_user_review"
    assert output["candidate_count"] == 6
    assert output["ready_for_user_review_count"] == 3
    assert output["needs_reference_registration_count"] == 1
    assert output["no_evidence_match_count"] == 1
    assert output["invalid_count"] == 1
    assert record["source"] == "ea.uv_vis.interpretation_suggestions:v0.2"
    assert record["source_packet_ref"] == packet_ref
    assert record["uv_vis_metadata_ref"] == metadata_ref
    assert record["feature_table_ref"] == features_ref
    assert record["related_records"] == ["raw/uv_vis/char-test/metadata.yml"]
    assert "does not perform live lookup" in " ".join(record["boundaries"])
    assert "does not register references" in " ".join(record["boundaries"])
    assert "review-package/report/memory workflow" in " ".join(record["next_steps"])

    candidates = {candidate["candidate_id"]: candidate for candidate in record["candidates"]}
    gap = candidates["uv-gap-ready"]
    assert gap["status"] == "ready_for_user_review"
    assert gap["matched_feature_ids"] == ["uvvis-feature-001"]
    assert {"uvvis-feature-001", "edge_estimate", tauc_ref, derivative_ref}.issubset(set(gap["evidence_refs"]))
    assert gap["auto_applied"] is False
    assert gap["requires_user_review"] is True
    assert candidates["uv-feature-ready"]["status"] == "ready_for_user_review"
    assert candidates["uv-feature-ready"]["matched_feature_ids"] == ["uvvis-feature-001"]
    assert candidates["uv-correction-ready"]["status"] == "ready_for_user_review"
    assert candidates["uv-correction-ready"]["evidence_refs"] == [correction_ref]
    unresolved = candidates["uv-transition-unresolved"]
    assert unresolved["status"] == "needs_reference_registration"
    assert unresolved["unresolved_reference_ids"] == ["ref-missing"]
    assert candidates["uv-feature-no-match"]["status"] == "no_evidence_match"
    assert candidates["uv-gap-invalid"]["status"] == "invalid_missing_required_metadata"
    assert "source_summary" in candidates["uv-gap-invalid"]["missing_fields"]
    assert "ref-missing" in record["reference_ids"]
    assert set(table["candidate_id"]) == set(candidates)
    assert provenance["workflow"] == "uv_vis_interpretation_suggestion"
    assert provenance["inputs"]["records"] == [packet_ref, metadata_ref, "raw/uv_vis/char-test/metadata.yml"]
    assert {features_ref, tauc_ref, derivative_ref, correction_ref}.issubset(set(provenance["inputs"]["files"]))
    assert set(provenance["source_refs"]) == {"ref-uv-gap", "ref-missing"}

    suggestion_ref = Path(output["record"]).relative_to(workspace).as_posix()
    review_count_before_package = len(list((workspace / "reviews").glob("*.yml")))
    assert main(["uv-vis", "prepare-review", str(workspace), "--project-id", project_id, "--suggestion", suggestion_ref]) == 0
    review_package_output = _json_output(capsys)
    assert review_package_output["status"] == "review_package_prepared"
    assert review_package_output["selected_candidate_count"] == 6
    assert review_package_output["selected_status_counts"]["ready_for_user_review"] == 3
    assert review_package_output["selected_status_counts"]["needs_reference_registration"] == 1
    assert review_package_output["selected_status_counts"]["no_evidence_match"] == 1
    assert review_package_output["selected_status_counts"]["invalid_missing_required_metadata"] == 1
    assert len(list((workspace / "reviews").glob("*.yml"))) == review_count_before_package

    review_package = read_yaml(Path(review_package_output["review_package"]))
    review_package_markdown = Path(review_package_output["review_package_markdown"]).read_text(encoding="utf-8")
    groups = {group["group"]: set(group["candidate_ids"]) for group in review_package["groups"]}
    assert review_package["source"] == "ea.uv_vis.interpretation_review_package:v0.2"
    assert review_package["review_target_type"] == "uv_vis_interpretation_suggestions"
    assert review_package["review_target_ref"] == suggestion_ref
    assert groups["ready_for_user_review"] == {"uv-gap-ready", "uv-feature-ready", "uv-correction-ready"}
    assert groups["needs_reference_registration"] == {"uv-transition-unresolved"}
    assert groups["no_evidence_match"] == {"uv-feature-no-match"}
    assert groups["invalid_or_incomplete"] == {"uv-gap-invalid"}
    assert "ref-missing" in review_package["unresolved_reference_ids"]
    assert "ea review add /path/to/ea-project" in review_package["recommended_commands"]["create_review_record"]
    assert "ea uv-vis suggest-interpretations" in review_package["recommended_commands"]["rerun_after_reference_registration"]
    assert "does not create a ReviewRecord" in " ".join(review_package["boundaries"])
    assert "does not apply UV-Vis optical models" in " ".join(review_package["boundaries"])
    assert read_yaml(Path(review_package_output["provenance"]))["workflow"] == "uv_vis_interpretation_review_package"
    assert "UV-Vis Interpretation Suggestion Review Package" in review_package_markdown
    assert "uv-gap-ready" in review_package_markdown
    assert "visible absorption feature" in review_package_markdown
    assert "reported_energy_eV=2.1" in review_package_markdown
    assert "uv-feature-no-match" in review_package_markdown
    assert "uv-gap-invalid" in review_package_markdown
    assert "does not apply UV-Vis optical models" in review_package_markdown


def test_uv_vis_docs_and_skill_references_are_discoverable() -> None:
    root = Path.cwd()

    readme = (root / "README.md").read_text(encoding="utf-8")
    skill = (root / "skills" / "ea-v0-2" / "SKILL.md").read_text(encoding="utf-8")
    uv_vis_reference = root / "skills" / "ea-v0-2" / "references" / "uv-vis-workflow.md"
    registry = read_yaml(root / "skill-registry" / "index.yml")

    assert "ea uv-vis inspect" in readme
    assert "ea uv-vis build-source-packet" in readme
    assert "ea uv-vis suggest-interpretations" in readme
    assert "ea uv-vis prepare-review" in readme
    assert "ea uv-vis process" in skill
    assert "ea uv-vis build-source-packet" in skill
    assert "ea uv-vis suggest-interpretations" in skill
    assert "ea uv-vis prepare-review" in skill
    assert "references/uv-vis-workflow.md" in skill
    assert uv_vis_reference.exists()
    reference_text = uv_vis_reference.read_text(encoding="utf-8")
    assert "signal_mode" in reference_text
    assert "Tauc/Kubelka-Munk" in reference_text
    assert "derivative_analysis" in reference_text
    assert "correction_context" in reference_text
    assert "prepare-source-candidates --method uv_vis" in reference_text
    assert "ea uv-vis build-source-packet" in reference_text
    assert "ea uv-vis suggest-interpretations" in reference_text
    assert "ea uv-vis prepare-review" in reference_text
    assert "optical_gap_candidate" in reference_text
    assert "examples/public-uv-vis-project" in reference_text
    uv_vis_record = next(item for item in registry["skills"] if item["id"] == "ea.uv-vis-analysis")
    assert "Minimal UV-Vis workflow implemented" in uv_vis_record["notes"]
    assert "tauc_kubelka_munk_screening" in uv_vis_record["notes"]
    assert "derivative_screening" in uv_vis_record["notes"]
    assert "correction_context_records" in uv_vis_record["notes"]
    assert "source-candidate manifest/preflight" in uv_vis_record["notes"]
    assert "source_packet building" in uv_vis_record["notes"]
    assert "interpretation_suggestions" in uv_vis_record["notes"]
    assert "review packages" in uv_vis_record["notes"]
