from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

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


def _write_dsc_fixture(path: Path) -> Path:
    lines = [
        "# temperature_unit = C",
        "# signal_unit = mW/mg",
        "# measurement_mode = dsc",
        "# technique = DSC heat flow",
        "temperature_C heat_flow_mW_mg",
    ]
    for index in range(800):
        temperature = 25.0 + index * (275.0 / 799.0)
        baseline = 0.001 * (temperature - 25.0)
        endotherm = -0.55 * math.exp(-((temperature - 145.0) ** 2) / (2.0 * 8.0**2))
        exotherm = 0.35 * math.exp(-((temperature - 210.0) ** 2) / (2.0 * 10.0**2))
        signal = baseline + endotherm + exotherm
        lines.append(f"{temperature:.4f} {signal:.8f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_dsc_transition_fixture(path: Path) -> Path:
    lines = [
        "# temperature_unit = C",
        "# signal_unit = mW/mg",
        "# measurement_mode = dsc",
        "# technique = DSC heat flow with reviewed transition windows",
        "temperature_C heat_flow_mW_mg",
    ]
    for index in range(900):
        temperature = 30.0 + index * (230.0 / 899.0)
        baseline = 0.001 * (temperature - 30.0)
        glass_step = 0.08 / (1.0 + math.exp(-(temperature - 95.0) / 3.0))
        endotherm = -0.48 * math.exp(-((temperature - 145.0) ** 2) / (2.0 * 7.0**2))
        exotherm = 0.34 * math.exp(-((temperature - 210.0) ** 2) / (2.0 * 8.0**2))
        signal = baseline + glass_step + endotherm + exotherm
        lines.append(f"{temperature:.4f} {signal:.8f}")
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


def test_thermal_context_record_preserves_reviewed_sign_and_baseline_metadata(tmp_path: Path, capsys) -> None:
    fixture = _write_dsc_fixture(tmp_path / "synthetic-thermal-dsc.txt")
    workspace = tmp_path / "thermal-context-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "Thermal Context Records",
            "--slug",
            "thermal-context-records",
            "--direction",
            "thermal context record workflow",
            "--material",
            "polymer film",
            "--experiment-type",
            "materials DSC context record",
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
            "sample-dsc-001",
            "--experiment-ref",
            "exp-dsc-001",
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
            "thermal_columns",
            "--target-ref",
            raw_metadata_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            "temperature=temperature_C, signal=heat_flow_mW_mg, temperature_unit=C, signal_unit=mW/mg, mode=dsc",
        ]
    ) == 0
    column_review = _json_output(capsys)

    context_text = "DSC nitrogen; 10 C/min; sealed aluminum pan; exotherm-up reviewed; instrument linear baseline applied"
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

    parameters = default_thermal_processing_parameters()
    parameters["context_record"].update(
        {
            "enabled": True,
            "dsc_sign_convention": {
                "exotherm_direction": "up",
                "endotherm_direction": "down",
                "status": "reviewed",
            },
            "baseline_reference": {
                "baseline_method": "instrument_linear_baseline",
                "reference_pan": "empty aluminum pan",
                "numeric_correction": "instrument_applied",
                "status": "reviewed",
            },
            "sample_context": {
                "sample_mass_mg": 5.2,
                "pan": "sealed aluminum",
                "sample_form": "polymer film",
            },
            "atmosphere_program": {
                "atmosphere": "N2",
                "flow_mL_min": 50,
                "heating_rate_C_min": 10,
            },
            "correction_notes": [
                "EA records thermal context only; no Tg/Tm/Tc assignment or kinetic fitting was applied."
            ],
        }
    )
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
            json.dumps(parameters, ensure_ascii=False),
        ]
    ) == 0
    parameter_review = _json_output(capsys)

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
            "sample-dsc-001",
            "--temperature-column",
            "temperature_C",
            "--signal-column",
            "heat_flow_mW_mg",
            "--temperature-unit",
            "C",
            "--signal-unit",
            "mW/mg",
            "--measurement-mode",
            "dsc",
            "--context-summary",
            context_text,
            "--column-review-ref",
            column_review["review_id"],
            "--context-review-ref",
            context_review["review_id"],
            "--parameter-review-ref",
            parameter_review["review_id"],
            "--parameters-json",
            json.dumps({"context_record": parameters["context_record"]}, ensure_ascii=False),
        ]
    ) == 0
    process_output = _json_output(capsys)
    thermal_metadata = Path(process_output["metadata"])
    thermal = read_yaml(thermal_metadata)

    context_record = thermal["peak_analysis"]["context_record"]
    assert context_record["status"] == "reviewed_context_recorded"
    assert context_record["confidence"] == "low"
    assert "dsc_sign_convention" in context_record["reviewed_context_fields"]
    assert context_record["dsc_sign_convention"]["exotherm_direction"] == "up"
    assert "metadata/provenance only" in context_record["boundary"]
    assert "Tg/Tm/Tc assignment" in context_record["boundary"]
    assert thermal["outputs"]["context_record"].endswith("thermal_context.yml")
    saved_context = read_yaml(workspace / thermal["outputs"]["context_record"])
    assert saved_context["record_ref"] == thermal["outputs"]["context_record"]
    assert saved_context["baseline_reference"]["reference_pan"] == "empty aluminum pan"
    assert "context_record" in thermal["peak_analysis"]["possible_interpretations"][-1]["evidence"]

    figure_record = read_yaml(workspace / "figures" / "index.yml")["figures"][thermal["figure_id"]]
    assert thermal["outputs"]["context_record"] in figure_record["source_data_refs"]

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
            "sample-dsc-001",
            "--experiment-ref",
            "exp-dsc-001",
        ]
    ) == 0
    report_output = _json_output(capsys)
    _, report_body = read_markdown_record(Path(report_output["report"]))
    assert "## Thermal context record" in report_body
    assert "exotherm_direction=up" in report_body
    assert "不自动翻转 DSC 符号" in report_body
    assert thermal["outputs"]["context_record"] in report_body


def test_thermal_baseline_correction_applies_reviewed_linear_model(tmp_path: Path, capsys) -> None:
    fixture = _write_dsc_fixture(tmp_path / "synthetic-thermal-dsc-baseline.txt")
    workspace = tmp_path / "thermal-baseline-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "Thermal Baseline Correction",
            "--slug",
            "thermal-baseline-correction",
            "--direction",
            "thermal baseline correction workflow",
            "--material",
            "polymer film",
            "--experiment-type",
            "materials DSC baseline correction",
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
            "sample-dsc-baseline-001",
            "--experiment-ref",
            "exp-dsc-baseline-001",
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
            "thermal_columns",
            "--target-ref",
            raw_metadata_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            "temperature=temperature_C, signal=heat_flow_mW_mg, temperature_unit=C, signal_unit=mW/mg, mode=dsc",
        ]
    ) == 0
    column_review = _json_output(capsys)

    context_text = "DSC nitrogen; reviewed linear baseline anchors at trace edges; no transition assignment requested"
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

    parameters = default_thermal_processing_parameters()
    parameters["baseline_correction"].update(
        {
            "enabled": True,
            "method": "linear_two_point",
            "anchor_strategy": "reviewed_trace_edges",
            "anchor_temperatures_C": [25.0, 300.0],
        }
    )
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
            json.dumps(parameters, ensure_ascii=False),
        ]
    ) == 0
    parameter_review = _json_output(capsys)

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
            "sample-dsc-baseline-001",
            "--temperature-column",
            "temperature_C",
            "--signal-column",
            "heat_flow_mW_mg",
            "--temperature-unit",
            "C",
            "--signal-unit",
            "mW/mg",
            "--measurement-mode",
            "dsc",
            "--context-summary",
            context_text,
            "--column-review-ref",
            column_review["review_id"],
            "--context-review-ref",
            context_review["review_id"],
            "--parameter-review-ref",
            parameter_review["review_id"],
            "--parameters-json",
            json.dumps({"baseline_correction": parameters["baseline_correction"]}, ensure_ascii=False),
        ]
    ) == 0
    process_output = _json_output(capsys)
    thermal_metadata = Path(process_output["metadata"])
    thermal = read_yaml(thermal_metadata)

    baseline = thermal["peak_analysis"]["baseline_correction"]
    assert baseline["status"] == "applied_linear_baseline"
    assert baseline["applied"] is True
    assert baseline["confidence"] == "medium"
    assert baseline["corrected_column"] == "baseline_corrected_signal"
    assert "does not assign Tg/Tm/Tc" in baseline["boundary"]
    assert thermal["outputs"]["baseline_correction"].endswith("thermal_baseline.yml")
    saved_baseline = read_yaml(workspace / thermal["outputs"]["baseline_correction"])
    assert saved_baseline["record_ref"] == thermal["outputs"]["baseline_correction"]
    assert len(saved_baseline["anchor_points"]) == 2
    assert saved_baseline["anchor_points"][0]["actual_temperature_C"] == 25.0

    processed = pd.read_csv(workspace / thermal["outputs"]["processed_csv"])
    assert "baseline_estimate" in processed.columns
    assert "baseline_corrected_signal" in processed.columns
    assert abs(float(processed["baseline_corrected_signal"].iloc[0])) < 1e-8
    assert abs(float(processed["baseline_corrected_signal"].iloc[-1])) < 1e-8
    assert thermal["peak_analysis"]["signal_summary"]["start_signal"] == 0.0
    assert thermal["peak_analysis"]["possible_interpretations"][-1]["evidence"][0] == "baseline_correction"

    figure_record = read_yaml(workspace / "figures" / "index.yml")["figures"][thermal["figure_id"]]
    assert thermal["outputs"]["baseline_correction"] in figure_record["source_data_refs"]

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
            "sample-dsc-baseline-001",
            "--experiment-ref",
            "exp-dsc-baseline-001",
        ]
    ) == 0
    report_output = _json_output(capsys)
    _, report_body = read_markdown_record(Path(report_output["report"]))
    assert "## Thermal baseline correction" in report_body
    assert "linear_two_point" in report_body
    assert "数值处理步骤" in report_body
    assert thermal["outputs"]["baseline_correction"] in report_body


def test_thermal_transition_screening_extracts_reviewed_window_candidates(tmp_path: Path, capsys) -> None:
    fixture = _write_dsc_transition_fixture(tmp_path / "synthetic-thermal-dsc-transitions.txt")
    workspace = tmp_path / "thermal-transition-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "Thermal Transition Screening",
            "--slug",
            "thermal-transition-screening",
            "--direction",
            "thermal transition screening workflow",
            "--material",
            "polymer film",
            "--experiment-type",
            "materials DSC transition screening",
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
            "sample-dsc-transition-001",
            "--experiment-ref",
            "exp-dsc-transition-001",
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
            "thermal_columns",
            "--target-ref",
            raw_metadata_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            "temperature=temperature_C, signal=heat_flow_mW_mg, temperature_unit=C, signal_unit=mW/mg, mode=dsc",
        ]
    ) == 0
    column_review = _json_output(capsys)

    context_text = "DSC nitrogen; reviewed transition windows for Tg, Tm, and Tc; exotherm-up convention reviewed"
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

    parameters = default_thermal_processing_parameters()
    parameters["baseline_correction"].update(
        {
            "enabled": True,
            "method": "linear_two_point",
            "anchor_temperatures_C": [30.0, 260.0],
        }
    )
    parameters["transition_analysis"].update(
        {
            "enabled": True,
            "method": "reviewed_window_screening",
            "transitions": [
                {
                    "transition_id": "tg-001",
                    "transition_type": "Tg",
                    "label": "reviewed Tg candidate window",
                    "temperature_window_C": [85.0, 105.0],
                    "signal_direction": "auto",
                },
                {
                    "transition_id": "tm-001",
                    "transition_type": "Tm",
                    "label": "reviewed melting candidate window",
                    "temperature_window_C": [135.0, 155.0],
                    "signal_direction": "endotherm_down",
                },
                {
                    "transition_id": "tc-001",
                    "transition_type": "Tc",
                    "label": "reviewed crystallization candidate window",
                    "temperature_window_C": [200.0, 220.0],
                    "signal_direction": "exotherm_up",
                },
            ],
        }
    )
    parameters["transition_assignment"].update(
        {
            "enabled": True,
            "method": "user_confirmed_transition_assignments",
            "assignments": [
                {
                    "assignment_id": "ta-tg-001",
                    "transition_id": "tg-001",
                    "assigned_transition_type": "Tg",
                    "assigned_label": "user-confirmed glass-transition assignment",
                    "confidence": "medium",
                    "evidence_refs": ["thermal_transitions.csv:tg-001", "thermal_context_review"],
                    "reference_ids": ["ref-polymer-dsc-001"],
                    "reviewer_notes": ["User confirmed Tg label after reviewing DSC context and candidate window."],
                    "caveats": ["Needs replicate DSC runs before publication-level assignment."],
                },
                {
                    "assignment_id": "ta-tm-001",
                    "transition_id": "tm-001",
                    "assigned_transition_type": "Tm",
                    "assigned_label": "user-confirmed melting assignment",
                    "confidence": "medium",
                    "evidence_refs": ["thermal_transitions.csv:tm-001", "exotherm_up_context"],
                    "reference_ids": ["ref-polymer-dsc-001"],
                    "reviewer_notes": ["User confirmed melting label for the endotherm-down candidate."],
                    "caveats": ["No kinetic interpretation from this single trace."],
                },
            ],
        }
    )
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
            json.dumps(parameters, ensure_ascii=False),
        ]
    ) == 0
    parameter_review = _json_output(capsys)

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
            "sample-dsc-transition-001",
            "--temperature-column",
            "temperature_C",
            "--signal-column",
            "heat_flow_mW_mg",
            "--temperature-unit",
            "C",
            "--signal-unit",
            "mW/mg",
            "--measurement-mode",
            "dsc",
            "--context-summary",
            context_text,
            "--column-review-ref",
            column_review["review_id"],
            "--context-review-ref",
            context_review["review_id"],
            "--parameter-review-ref",
            parameter_review["review_id"],
            "--parameters-json",
            json.dumps(
                {
                    "baseline_correction": parameters["baseline_correction"],
                    "transition_analysis": parameters["transition_analysis"],
                    "transition_assignment": parameters["transition_assignment"],
                },
                ensure_ascii=False,
            ),
        ]
    ) == 0
    process_output = _json_output(capsys)
    thermal_metadata = Path(process_output["metadata"])
    thermal = read_yaml(thermal_metadata)

    transition_record = thermal["peak_analysis"]["transition_analysis"]
    assert transition_record["status"] == "reviewed_transition_candidates_recorded"
    assert transition_record["transition_count"] == 3
    assert "does not make formal Tg/Tm/Tc assignments" in transition_record["boundary"]
    assert thermal["outputs"]["transition_table"].endswith("thermal_transitions.csv")
    assert thermal["outputs"]["transition_record"].endswith("thermal_transitions.yml")
    saved_transition = read_yaml(workspace / thermal["outputs"]["transition_record"])
    assert saved_transition["record_ref"] == thermal["outputs"]["transition_record"]
    assert saved_transition["table_ref"] == thermal["outputs"]["transition_table"]

    transition_table = pd.read_csv(workspace / thermal["outputs"]["transition_table"])
    assert set(transition_table["transition_id"]) == {"tg-001", "tm-001", "tc-001"}
    tg = transition_table.set_index("transition_id").loc["tg-001"]
    tm = transition_table.set_index("transition_id").loc["tm-001"]
    tc = transition_table.set_index("transition_id").loc["tc-001"]
    assert 90.0 <= float(tg["estimated_temperature_C"]) <= 100.0
    assert tg["metric"] == "derivative_absolute_extremum"
    assert 140.0 <= float(tm["estimated_temperature_C"]) <= 150.0
    assert tm["metric"] == "signal_minimum"
    assert 205.0 <= float(tc["estimated_temperature_C"]) <= 215.0
    assert tc["metric"] == "signal_maximum"
    assert any(
        thermal["outputs"]["transition_table"] in item.get("evidence", [])
        for item in thermal["peak_analysis"]["possible_interpretations"]
    )

    assignment_record = thermal["peak_analysis"]["transition_assignment"]
    assert assignment_record["status"] == "reviewed_transition_assignments_recorded"
    assert assignment_record["assignment_count"] == 2
    assert "does not infer formal Tg/Tm/Tc" in assignment_record["boundary"]
    assert thermal["outputs"]["transition_assignment"].endswith("thermal_transition_assignments.yml")
    saved_assignment = read_yaml(workspace / thermal["outputs"]["transition_assignment"])
    assert saved_assignment["record_ref"] == thermal["outputs"]["transition_assignment"]
    assert saved_assignment["assignments"][0]["candidate_link_status"] == "linked_to_screening_candidate"
    assert 90.0 <= float(saved_assignment["assignments"][0]["assigned_temperature_C"]) <= 100.0
    assert saved_assignment["assignments"][0]["reference_ids"] == ["ref-polymer-dsc-001"]
    assert thermal["outputs"]["transition_assignment"] in thermal["peak_analysis"]["possible_interpretations"][-1]["evidence"]

    figure_record = read_yaml(workspace / "figures" / "index.yml")["figures"][thermal["figure_id"]]
    assert thermal["outputs"]["transition_table"] in figure_record["source_data_refs"]
    assert thermal["outputs"]["transition_record"] in figure_record["source_data_refs"]
    assert thermal["outputs"]["transition_assignment"] in figure_record["source_data_refs"]

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
            "sample-dsc-transition-001",
            "--experiment-ref",
            "exp-dsc-transition-001",
        ]
    ) == 0
    report_output = _json_output(capsys)
    _, report_body = read_markdown_record(Path(report_output["report"]))
    assert "## Thermal transition screening" in report_body
    assert "reviewed_window_screening" in report_body
    assert "tg-001" in report_body
    assert "不是正式相变赋值" in report_body
    assert thermal["outputs"]["transition_table"] in report_body
    assert "## Thermal transition assignments" in report_body
    assert "ta-tg-001" in report_body
    assert "用户确认" in report_body
    assert thermal["outputs"]["transition_assignment"] in report_body


def test_thermal_docs_and_skill_references_are_discoverable() -> None:
    root = Path.cwd()

    readme = (root / "README.md").read_text(encoding="utf-8")
    skill = (root / "skills" / "ea" / "SKILL.md").read_text(encoding="utf-8")
    cli_index = (root / "skills" / "ea" / "references" / "cli-command-index.md").read_text(encoding="utf-8")
    thermal_reference = root / "skills" / "ea" / "references" / "thermal-workflow.md"
    registry = read_yaml(root / "skill-registry" / "index.yml")

    assert "ea thermal inspect" in readme
    assert "references/thermal-workflow.md" in skill
    assert "ea thermal process" in cli_index
    assert thermal_reference.exists()
    reference_text = thermal_reference.read_text(encoding="utf-8")
    assert "context_review_ref" in reference_text
    assert "context_record" in reference_text
    assert "baseline_correction" in reference_text
    assert "transition_analysis" in reference_text
    assert "transition_assignment" in reference_text
    assert "kinetic" in reference_text
    thermal_record = next(item for item in registry["skills"] if item["id"] == "ea.thermal-analysis")
    assert "Minimal thermal analysis workflow implemented" in thermal_record["notes"]
    assert "context_records" in thermal_record["notes"]
    assert "baseline_corrections" in thermal_record["notes"]
    assert "transition_screening" in thermal_record["notes"]
    assert "transition_assignments" in thermal_record["notes"]
