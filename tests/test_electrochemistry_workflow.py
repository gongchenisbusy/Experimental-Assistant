from __future__ import annotations

import csv
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


def _write_eis_fixture(path: Path) -> Path:
    lines = [
        "# x_unit = ohm",
        "# measurement_mode = eis",
        "# technique = electrochemical impedance spectroscopy nyquist",
        "z_real_ohm neg_z_imag_ohm",
    ]
    center = 55.0
    radius = 45.0
    for index in range(181):
        z_real = 10.0 + index * 0.5
        neg_imag = math.sqrt(max(radius**2 - (z_real - center) ** 2, 0.0))
        lines.append(f"{z_real:.6f} {neg_imag:.9f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_eis_circuit_fixture(path: Path) -> Path:
    lines = [
        "# x_unit = ohm",
        "# measurement_mode = eis",
        "# technique = electrochemical impedance spectroscopy nyquist circuit fit",
        "z_real_ohm neg_z_imag_ohm frequency_Hz",
    ]
    rs = 8.0
    rct = 72.0
    cdl = 0.001
    for index in range(80):
        exponent = 5.0 - index * (6.0 / 79.0)
        frequency = 10**exponent
        omega_tau = 2.0 * math.pi * frequency * rct * cdl
        z_real = rs + rct / (1.0 + omega_tau**2)
        neg_z_imag = rct * omega_tau / (1.0 + omega_tau**2)
        lines.append(f"{z_real:.9f} {neg_z_imag:.9f} {frequency:.9f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_tafel_fixture(path: Path) -> Path:
    lines = [
        "# x_unit = V",
        "# current_unit = mA",
        "# measurement_mode = lsv",
        "# technique = linear sweep voltammetry tafel screening",
        "potential_V current_mA",
    ]
    for index in range(121):
        potential = 0.2 + index * 0.001
        current = 10 ** ((potential - 0.2) / 0.06)
        lines.append(f"{potential:.6f} {current:.9f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_gcd_fixture(path: Path) -> Path:
    lines = [
        "# x_unit = s",
        "# measurement_mode = gcd",
        "# technique = galvanostatic charge discharge",
        "time_s voltage_V",
    ]
    for index in range(101):
        time_s = float(index)
        voltage = 1.0 - 0.5 * time_s / 100.0
        lines.append(f"{time_s:.6f} {voltage:.9f}")
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


def test_electrochemistry_correction_record_preserves_reviewed_reference_and_ir_metadata(tmp_path: Path, capsys) -> None:
    fixture = _write_electrochemistry_fixture(tmp_path / "synthetic-electrochemistry-correction-cv.txt")
    workspace = tmp_path / "electrochemistry-correction-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "Electrochemistry Correction Workflow",
            "--slug",
            "electrochemistry-correction-workflow",
            "--direction",
            "electrochemistry correction records",
            "--material",
            "oxide catalyst",
            "--experiment-type",
            "materials electrochemistry correction record",
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
            "sample-ec-correction-001",
            "--experiment-ref",
            "exp-ec-correction-001",
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

    context_text = "0.196 cm2 glassy-carbon electrode; 1 M KOH; Ag/AgCl reference; scan rate reviewed"
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

    parameters = default_electrochemistry_processing_parameters()
    parameters["correction_record"].update(
        {
            "enabled": True,
            "reference_electrode": {"type": "Ag/AgCl", "electrolyte": "sat_KCl", "status": "reviewed"},
            "converted_potential_scale": {
                "target_scale": "RHE",
                "offset_V": 0.966,
                "equation": "E_RHE = E_AgAgCl + 0.197 + 0.0591*pH",
                "applied_to_processed_data": False,
            },
            "uncompensated_resistance": {"ru_ohm": 18.5, "source": "EIS high-frequency intercept", "status": "reviewed"},
            "ir_compensation": {"status": "instrument_applied", "fraction": 0.85, "mode": "positive_feedback"},
            "correction_notes": ["EA records correction metadata only; no potential shift or iR correction was applied."],
        }
    )
    parameters["potential_conversion"].update(
        {
            "enabled": True,
            "input_scale": "Ag/AgCl_sat_KCl",
            "target_scale": "RHE",
            "offset_V": 0.966,
            "equation": "E_RHE = E_AgAgCl + 0.197 + 0.0591*pH",
            "output_column": "potential_RHE_V",
            "reference_electrode": {"type": "Ag/AgCl", "electrolyte": "sat_KCl", "status": "reviewed"},
            "reference_ids": ["ref-electrochemistry-method-001"],
            "reviewer_notes": ["Offset reviewed for the synthetic fixture protocol."],
            "caveats": ["Confirm pH and reference calibration before overpotential comparisons."],
        }
    )
    parameters["ir_drop_correction"].update(
        {
            "enabled": True,
            "potential_input_column": "potential_RHE_V",
            "current_input_column": "processed_current_mA",
            "current_unit": "mA",
            "ru_ohm": 18.5,
            "compensation_fraction": 0.85,
            "sign_convention": "subtract_i_ru",
            "formula": "E_iR = E_RHE - I_A * Ru * 0.85",
            "output_column": "potential_RHE_iR_corrected_V",
            "drop_column": "ir_drop_V",
            "reference_ids": ["ref-electrochemistry-method-001"],
            "reviewer_notes": ["Ru and compensation fraction reviewed for the synthetic fixture protocol."],
            "caveats": ["Do not use this correction alone as a Tafel or overpotential claim."],
        }
    )
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
            json.dumps(parameters, ensure_ascii=False),
        ]
    ) == 0
    parameter_review = _json_output(capsys)

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
            "sample-ec-correction-001",
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
            "--parameters-json",
            json.dumps(
                {
                    "correction_record": parameters["correction_record"],
                    "potential_conversion": parameters["potential_conversion"],
                    "ir_drop_correction": parameters["ir_drop_correction"],
                },
                ensure_ascii=False,
            ),
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
    correction_record = electrochemistry["peak_analysis"]["correction_record"]
    potential_conversion = electrochemistry["peak_analysis"]["potential_conversion"]
    ir_drop_correction = electrochemistry["peak_analysis"]["ir_drop_correction"]

    assert correction_record["status"] == "reviewed_correction_recorded"
    assert correction_record["confidence"] == "low"
    assert "reference_electrode" in correction_record["reviewed_correction_fields"]
    assert correction_record["reference_electrode"]["type"] == "Ag/AgCl"
    assert correction_record["converted_potential_scale"]["target_scale"] == "RHE"
    assert correction_record["converted_potential_scale"]["applied_to_processed_data"] is False
    assert "metadata/provenance only" in correction_record["boundary"]
    assert electrochemistry["outputs"]["correction_record"].endswith("electrochemistry_correction.yml")
    saved_correction = read_yaml(workspace / electrochemistry["outputs"]["correction_record"])
    assert saved_correction["uncompensated_resistance"]["ru_ohm"] == 18.5
    assert saved_correction["record_ref"] == electrochemistry["outputs"]["correction_record"]
    assert potential_conversion["status"] == "reviewed_potential_conversion_applied"
    assert potential_conversion["input_scale"] == "Ag/AgCl_sat_KCl"
    assert potential_conversion["target_scale"] == "RHE"
    assert potential_conversion["offset_V"] == 0.966
    assert potential_conversion["output_column"] == "potential_RHE_V"
    assert potential_conversion["applied_to_processed_data"] is True
    assert potential_conversion["applied_to_plot_axis"] is True
    assert potential_conversion["applied_to_feature_detection"] is False
    assert "coordinate transform" in potential_conversion["boundary"]
    assert electrochemistry["outputs"]["potential_conversion"].endswith("electrochemistry_potential_conversion.yml")
    saved_conversion = read_yaml(workspace / electrochemistry["outputs"]["potential_conversion"])
    assert saved_conversion["record_ref"] == electrochemistry["outputs"]["potential_conversion"]
    assert ir_drop_correction["status"] == "reviewed_ir_drop_correction_applied"
    assert ir_drop_correction["ru_ohm"] == 18.5
    assert ir_drop_correction["compensation_fraction"] == 0.85
    assert ir_drop_correction["sign_convention"] == "subtract_i_ru"
    assert ir_drop_correction["potential_input_column"] == "potential_RHE_V"
    assert ir_drop_correction["current_input_column"] == "processed_current_mA"
    assert ir_drop_correction["output_column"] == "potential_RHE_iR_corrected_V"
    assert ir_drop_correction["drop_column"] == "ir_drop_V"
    assert ir_drop_correction["applied_to_processed_data"] is True
    assert ir_drop_correction["applied_to_plot_axis"] is True
    assert ir_drop_correction["applied_to_feature_detection"] is False
    assert "coordinate correction" in ir_drop_correction["boundary"]
    assert electrochemistry["outputs"]["ir_drop_correction"].endswith("electrochemistry_ir_drop_correction.yml")
    saved_ir_correction = read_yaml(workspace / electrochemistry["outputs"]["ir_drop_correction"])
    assert saved_ir_correction["record_ref"] == electrochemistry["outputs"]["ir_drop_correction"]

    with (workspace / electrochemistry["outputs"]["processed_csv"]).open(newline="", encoding="utf-8") as handle:
        processed_rows = list(csv.DictReader(handle))
    assert "potential_RHE_V" in processed_rows[0]
    assert "ir_drop_V" in processed_rows[0]
    assert "potential_RHE_iR_corrected_V" in processed_rows[0]
    first_row = processed_rows[0]
    potential_rhe = float(first_row["potential_RHE_V"])
    current_a = float(first_row["processed_current_mA"]) / 1000.0
    expected_drop = current_a * 18.5 * 0.85
    assert math.isclose(potential_rhe - float(first_row["potential_V"]), 0.966, rel_tol=1e-9, abs_tol=1e-9)
    assert math.isclose(float(first_row["ir_drop_V"]), expected_drop, rel_tol=1e-9, abs_tol=1e-9)
    assert math.isclose(float(first_row["potential_RHE_iR_corrected_V"]), potential_rhe - expected_drop, rel_tol=1e-9, abs_tol=1e-9)

    figure_record = read_yaml(workspace / "figures" / "index.yml")["figures"][electrochemistry["figure_id"]]
    assert electrochemistry["outputs"]["correction_record"] in figure_record["source_data_refs"]
    assert electrochemistry["outputs"]["potential_conversion"] in figure_record["source_data_refs"]
    assert electrochemistry["outputs"]["ir_drop_correction"] in figure_record["source_data_refs"]

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
            "sample-ec-correction-001",
            "--experiment-ref",
            "exp-ec-correction-001",
        ]
    ) == 0
    report_output = _json_output(capsys)
    _, report_body = read_markdown_record(Path(report_output["report"]))
    assert "## Correction/reference record" in report_body
    assert "## Potential conversion" in report_body
    assert "## iR drop correction" in report_body
    assert "Ag/AgCl" in report_body
    assert "RHE" in report_body
    assert "potential_RHE_V" in report_body
    assert "potential_RHE_iR_corrected_V" in report_body
    assert "coordinate transform" in report_body
    assert "coordinate correction" in report_body
    assert "correction_record 自动平移电位" in report_body


def test_electrochemistry_tafel_analysis_uses_reviewed_window_and_records_fit(tmp_path: Path, capsys) -> None:
    fixture = _write_tafel_fixture(tmp_path / "synthetic-electrochemistry-tafel-lsv.txt")
    workspace = tmp_path / "electrochemistry-tafel-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "Electrochemistry Tafel Workflow",
            "--slug",
            "electrochemistry-tafel-workflow",
            "--direction",
            "electrochemistry Tafel screening records",
            "--material",
            "oxide catalyst",
            "--experiment-type",
            "materials electrochemistry Tafel screening",
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
            "sample-ec-tafel-001",
            "--experiment-ref",
            "exp-ec-tafel-001",
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
            "electrochemistry_columns",
            "--target-ref",
            raw_metadata_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            "x=potential_V, y=current_mA, x_unit=V, current_unit=mA, mode=lsv",
        ]
    ) == 0
    column_review = _json_output(capsys)

    context_text = "1.0 cm2 reviewed geometric area; RHE scale already reviewed; LSV kinetic window selected by user"
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

    parameters = default_electrochemistry_processing_parameters()
    parameters["tafel_analysis"].update(
        {
            "enabled": True,
            "potential_input_column": "potential_V",
            "current_input_column": "processed_current_density_mA_cm-2",
            "current_unit": "mA cm^-2",
            "fit_window_V": {"min": 0.22, "max": 0.30},
            "minimum_points": 5,
            "minimum_log_span_decades": 0.5,
            "fit_potential_column": "tafel_fit_potential_V",
            "overpotential_reference_V": 0.2,
            "overpotential_column": "eta_RHE_V",
            "reference_scale": "synthetic_reviewed_RHE",
            "reference_ids": ["ref-electrochemistry-tafel-001"],
            "reviewer_notes": ["Kinetic window was user-reviewed for the synthetic fixture."],
            "caveats": ["Screening fit only; do not rank catalysts from one trace."],
        }
    )
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
            json.dumps(parameters, ensure_ascii=False),
        ]
    ) == 0
    parameter_review = _json_output(capsys)

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
            "sample-ec-tafel-001",
            "--x-column",
            "potential_V",
            "--y-column",
            "current_mA",
            "--x-unit",
            "V",
            "--current-unit",
            "mA",
            "--measurement-mode",
            "lsv",
            "--context-summary",
            context_text,
            "--electrode-area-cm2",
            "1.0",
            "--parameters-json",
            json.dumps({"tafel_analysis": parameters["tafel_analysis"]}, ensure_ascii=False),
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
    tafel = electrochemistry["peak_analysis"]["tafel_analysis"]

    assert tafel["status"] == "reviewed_tafel_fit_applied"
    assert tafel["potential_input_column"] == "potential_V"
    assert tafel["current_input_column"] == "processed_current_density_mA_cm-2"
    assert tafel["current_input_is_density"] is True
    assert tafel["fit_window_V"] == {"min": 0.22, "max": 0.3}
    assert tafel["overpotential_reference_V"] == 0.2
    assert tafel["overpotential_column"] == "eta_RHE_V"
    assert tafel["applied_to_processed_data"] is True
    assert tafel["applied_to_plot_axis"] is False
    assert tafel["applied_to_feature_detection"] is False
    assert "screening fit" in tafel["boundary"]
    assert electrochemistry["outputs"]["tafel_analysis"].endswith("electrochemistry_tafel_analysis.yml")
    saved_tafel = read_yaml(workspace / electrochemistry["outputs"]["tafel_analysis"])
    assert saved_tafel["record_ref"] == electrochemistry["outputs"]["tafel_analysis"]
    assert saved_tafel["fit_statistics"]["fit_point_count"] >= 70
    assert math.isclose(saved_tafel["fit_statistics"]["tafel_slope_mV_decade"], 60.0, rel_tol=1e-6, abs_tol=1e-6)
    assert saved_tafel["fit_statistics"]["r_squared"] > 0.999999

    with (workspace / electrochemistry["outputs"]["processed_csv"]).open(newline="", encoding="utf-8") as handle:
        processed_rows = list(csv.DictReader(handle))
    assert "tafel_log10_abs_current_density_mA_cm-2" in processed_rows[0]
    assert "tafel_fit_potential_V" in processed_rows[0]
    assert "eta_RHE_V" in processed_rows[0]
    fit_row = processed_rows[40]
    assert math.isclose(float(fit_row["potential_V"]), 0.24, rel_tol=1e-9, abs_tol=1e-9)
    assert math.isclose(float(fit_row["tafel_log10_abs_current_density_mA_cm-2"]), (0.24 - 0.2) / 0.06, rel_tol=1e-7, abs_tol=1e-7)
    assert math.isclose(float(fit_row["tafel_fit_potential_V"]), 0.24, rel_tol=1e-7, abs_tol=1e-7)
    assert math.isclose(float(fit_row["eta_RHE_V"]), 0.04, rel_tol=1e-9, abs_tol=1e-9)

    figure_record = read_yaml(workspace / "figures" / "index.yml")["figures"][electrochemistry["figure_id"]]
    assert electrochemistry["outputs"]["tafel_analysis"] in figure_record["source_data_refs"]

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
            "sample-ec-tafel-001",
            "--experiment-ref",
            "exp-ec-tafel-001",
        ]
    ) == 0
    report_output = _json_output(capsys)
    _, report_body = read_markdown_record(Path(report_output["report"]))
    assert "## Tafel/overpotential analysis" in report_body
    assert "tafel_slope_mV_decade" in report_body
    assert "60.0" in report_body
    assert "electrochemistry_tafel_analysis.yml" in report_body


def test_electrochemistry_gcd_analysis_uses_reviewed_discharge_window(tmp_path: Path, capsys) -> None:
    fixture = _write_gcd_fixture(tmp_path / "synthetic-electrochemistry-gcd.txt")
    workspace = tmp_path / "electrochemistry-gcd-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "Electrochemistry GCD Workflow",
            "--slug",
            "electrochemistry-gcd-workflow",
            "--direction",
            "electrochemistry GCD discharge metrics",
            "--material",
            "supercapacitor electrode",
            "--experiment-type",
            "galvanostatic charge discharge",
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
            "sample-ec-gcd-001",
            "--experiment-ref",
            "exp-ec-gcd-001",
        ]
    ) == 0
    raw_output = _json_output(capsys)
    raw_metadata_ref = Path(raw_output["metadata"]).relative_to(workspace).as_posix()

    assert main(["electrochemistry", "inspect", str(workspace), raw_output["project_raw_path"]]) == 0
    inspection = _json_output(capsys)
    assert inspection["file_kind"] == "electrochemistry"
    assert inspection["x_unit_candidate"] == "s"
    assert inspection["measurement_mode_candidate"] == "gcd"

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
            "x=time_s, y=voltage_V, x_unit=s, current_unit=unknown, mode=gcd",
        ]
    ) == 0
    column_review = _json_output(capsys)

    context_text = "GCD discharge segment; 2 mA discharge current; 4 mg active mass; 1 cm2 area; voltage window reviewed"
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

    parameters = default_electrochemistry_processing_parameters()
    parameters["gcd_analysis"].update(
        {
            "enabled": True,
            "time_input_column": "time_s",
            "voltage_input_column": "current_raw",
            "voltage_unit": "V",
            "voltage_output_column": "gcd_voltage_V",
            "segment_column": "gcd_discharge_segment",
            "discharge_time_window_s": {"start": 0.0, "end": 100.0},
            "voltage_window_V": {"min": 0.5, "max": 1.0},
            "discharge_current_mA": 2.0,
            "current_sign_convention": "reviewed_discharge_current_magnitude",
            "mass_mg": 4.0,
            "area_cm2": 1.0,
            "active_material_loading_mg_cm2": 4.0,
            "reference_ids": ["ref-electrochemistry-gcd-001"],
            "reviewer_notes": ["Discharge segment and current were reviewed for the synthetic fixture."],
            "caveats": ["Screening metric only; do not claim rate capability or cycling stability."],
        }
    )
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
            json.dumps(parameters, ensure_ascii=False),
        ]
    ) == 0
    parameter_review = _json_output(capsys)

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
            "sample-ec-gcd-001",
            "--x-column",
            "time_s",
            "--y-column",
            "voltage_V",
            "--x-unit",
            "s",
            "--current-unit",
            "unknown",
            "--measurement-mode",
            "gcd",
            "--context-summary",
            context_text,
            "--parameters-json",
            json.dumps({"gcd_analysis": parameters["gcd_analysis"]}, ensure_ascii=False),
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
    gcd = electrochemistry["peak_analysis"]["gcd_analysis"]
    metrics = gcd["metrics"]

    assert electrochemistry["measurement_mode"] == "gcd"
    assert electrochemistry["status"] == "success"
    assert gcd["status"] == "reviewed_gcd_metrics_applied"
    assert gcd["time_input_column"] == "time_s"
    assert gcd["voltage_input_column"] == "current_raw"
    assert gcd["voltage_output_column"] == "gcd_voltage_V"
    assert gcd["segment_column"] == "gcd_discharge_segment"
    assert gcd["applied_to_processed_data"] is True
    assert gcd["applied_to_plot_axis"] is True
    assert gcd["applied_to_feature_detection"] is False
    assert "discharge-window metrics record" in gcd["boundary"]
    assert math.isclose(metrics["duration_s"], 100.0, rel_tol=1e-9, abs_tol=1e-9)
    assert math.isclose(metrics["voltage_span_V"], 0.5, rel_tol=1e-9, abs_tol=1e-9)
    assert math.isclose(metrics["charge_C"], 0.2, rel_tol=1e-9, abs_tol=1e-9)
    assert math.isclose(metrics["capacity_mAh"], 2.0 * 100.0 / 3600.0, rel_tol=1e-9, abs_tol=1e-9)
    assert math.isclose(metrics["capacitance_F"], 0.4, rel_tol=1e-9, abs_tol=1e-9)
    assert math.isclose(metrics["specific_capacity_mAh_g-1"], (2.0 * 100.0 / 3600.0) / 0.004, rel_tol=1e-9, abs_tol=1e-9)
    assert math.isclose(metrics["specific_capacitance_F_g-1"], 100.0, rel_tol=1e-9, abs_tol=1e-9)
    assert math.isclose(metrics["areal_capacitance_F_cm-2"], 0.4, rel_tol=1e-9, abs_tol=1e-9)
    assert electrochemistry["outputs"]["gcd_analysis"].endswith("electrochemistry_gcd_analysis.yml")
    saved_gcd = read_yaml(workspace / electrochemistry["outputs"]["gcd_analysis"])
    assert saved_gcd["record_ref"] == electrochemistry["outputs"]["gcd_analysis"]

    with (workspace / electrochemistry["outputs"]["processed_csv"]).open(newline="", encoding="utf-8") as handle:
        processed_rows = list(csv.DictReader(handle))
    assert "gcd_voltage_V" in processed_rows[0]
    assert "gcd_discharge_segment" in processed_rows[0]
    assert processed_rows[0]["gcd_discharge_segment"] == "True"
    assert math.isclose(float(processed_rows[-1]["gcd_voltage_V"]), 0.5, rel_tol=1e-9, abs_tol=1e-9)

    figure_record = read_yaml(workspace / "figures" / "index.yml")["figures"][electrochemistry["figure_id"]]
    assert electrochemistry["outputs"]["gcd_analysis"] in figure_record["source_data_refs"]

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
            "sample-ec-gcd-001",
            "--experiment-ref",
            "exp-ec-gcd-001",
        ]
    ) == 0
    report_output = _json_output(capsys)
    _, report_body = read_markdown_record(Path(report_output["report"]))
    assert "## GCD discharge metrics" in report_body
    assert "GCD discharge metrics 摘要" in report_body
    assert "specific_capacitance_F_g-1" in report_body
    assert "100.0" in report_body
    assert "electrochemistry_gcd_analysis.yml" in report_body


def test_electrochemistry_eis_circuit_fit_uses_reviewed_frequency_and_model(tmp_path: Path, capsys) -> None:
    fixture = _write_eis_circuit_fixture(tmp_path / "synthetic-electrochemistry-eis-circuit.txt")
    workspace = tmp_path / "electrochemistry-eis-circuit-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "Electrochemistry EIS Circuit Fit Workflow",
            "--slug",
            "electrochemistry-eis-circuit-workflow",
            "--direction",
            "electrochemistry EIS circuit-fit screening",
            "--material",
            "oxide electrode",
            "--experiment-type",
            "electrochemical impedance spectroscopy",
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
            "sample-ec-eis-fit-001",
            "--experiment-ref",
            "exp-ec-eis-fit-001",
        ]
    ) == 0
    raw_output = _json_output(capsys)
    raw_metadata_ref = Path(raw_output["metadata"]).relative_to(workspace).as_posix()

    assert main(["electrochemistry", "inspect", str(workspace), raw_output["project_raw_path"]]) == 0
    inspection = _json_output(capsys)
    assert inspection["file_kind"] == "electrochemistry"
    assert inspection["x_unit_candidate"] == "ohm"
    assert inspection["measurement_mode_candidate"] == "eis"

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
            "x=z_real_ohm, y=neg_z_imag_ohm, frequency=frequency_Hz, x_unit=ohm, current_unit=unknown, mode=eis",
        ]
    ) == 0
    column_review = _json_output(capsys)

    context_text = "EIS frequency order, 10 mV perturbation, and series R-(Rct||Cdl) model were reviewed by user"
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

    parameters = default_electrochemistry_processing_parameters()
    parameters["eis_circuit_fit"].update(
        {
            "enabled": True,
            "frequency_input_column": "frequency_Hz",
            "frequency_unit": "Hz",
            "z_real_input_column": "z_real_ohm",
            "z_imag_input_column": "z_imag_ohm",
            "imaginary_input_convention": "signed_z_imag_ohm",
            "circuit_model": "series_r_rc",
            "initial_values": {"rs_ohm": 9.0, "rct_ohm": 70.0, "c_dl_F": 0.0008},
            "bounds": {
                "rs_ohm": {"min": 0.0, "max": 20.0},
                "rct_ohm": {"min": 10.0, "max": 120.0},
                "c_dl_F": {"min": 0.0001, "max": 0.01},
            },
            "fit_quality_thresholds": {"max_reduced_chi_square_ohm2": 1e-10, "min_r_squared_complex": 0.999999},
            "perturbation_amplitude_mV": 10.0,
            "frequency_order_reviewed": True,
            "reference_ids": ["ref-electrochemistry-eis-fit-001"],
            "reviewer_notes": ["Circuit model, frequency order, and parameter bounds were reviewed for this synthetic fixture."],
            "caveats": ["Screening fit only; do not treat one fit as replicate-supported mechanism evidence."],
        }
    )
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
            json.dumps(parameters, ensure_ascii=False),
        ]
    ) == 0
    parameter_review = _json_output(capsys)

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
            "sample-ec-eis-fit-001",
            "--x-column",
            "z_real_ohm",
            "--y-column",
            "neg_z_imag_ohm",
            "--x-unit",
            "ohm",
            "--current-unit",
            "unknown",
            "--measurement-mode",
            "eis",
            "--context-summary",
            context_text,
            "--parameters-json",
            json.dumps({"eis_circuit_fit": parameters["eis_circuit_fit"]}, ensure_ascii=False),
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
    fit = electrochemistry["peak_analysis"]["eis_circuit_fit"]

    assert electrochemistry["measurement_mode"] == "eis"
    assert electrochemistry["status"] == "success"
    assert fit["status"] == "reviewed_eis_circuit_fit_applied"
    assert fit["circuit_model"] == "series_r_rc"
    assert fit["frequency_input_column"] == "frequency_Hz"
    assert fit["frequency_output_column"] == "frequency_Hz"
    assert fit["applied_to_processed_data"] is True
    assert fit["applied_to_plot_axis"] is True
    assert fit["applied_to_feature_detection"] is False
    assert "reviewed screening fit" in fit["boundary"]
    assert math.isclose(fit["fitted_parameters"]["rs_ohm"], 8.0, rel_tol=1e-6, abs_tol=1e-6)
    assert math.isclose(fit["fitted_parameters"]["rct_ohm"], 72.0, rel_tol=1e-6, abs_tol=1e-6)
    assert math.isclose(fit["fitted_parameters"]["c_dl_F"], 0.001, rel_tol=1e-6, abs_tol=1e-9)
    assert fit["fit_quality"]["r_squared_complex"] > 0.999999
    assert fit["fit_quality_checks"]["min_r_squared_complex"]["passed"] is True
    assert electrochemistry["outputs"]["eis_circuit_fit"].endswith("electrochemistry_eis_circuit_fit.yml")
    saved_fit = read_yaml(workspace / electrochemistry["outputs"]["eis_circuit_fit"])
    assert saved_fit["record_ref"] == electrochemistry["outputs"]["eis_circuit_fit"]

    with (workspace / electrochemistry["outputs"]["processed_csv"]).open(newline="", encoding="utf-8") as handle:
        processed_rows = list(csv.DictReader(handle))
    assert "frequency_Hz" in processed_rows[0]
    assert "eis_fit_z_real_ohm" in processed_rows[0]
    assert "eis_fit_z_imag_ohm" in processed_rows[0]
    assert "eis_fit_neg_z_imag_ohm" in processed_rows[0]

    figure_record = read_yaml(workspace / "figures" / "index.yml")["figures"][electrochemistry["figure_id"]]
    assert electrochemistry["outputs"]["eis_circuit_fit"] in figure_record["source_data_refs"]

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
            "sample-ec-eis-fit-001",
            "--experiment-ref",
            "exp-ec-eis-fit-001",
        ]
    ) == 0
    report_output = _json_output(capsys)
    _, report_body = read_markdown_record(Path(report_output["report"]))
    assert "## EIS circuit-fit screening" in report_body
    assert "fitted rs_ohm" in report_body
    assert "electrochemistry_eis_circuit_fit.yml" in report_body
    assert "不是自动模型选择" in report_body


def test_cli_runs_eis_nyquist_screening_workflow(tmp_path: Path, capsys) -> None:
    fixture = _write_eis_fixture(tmp_path / "synthetic-electrochemistry-eis.txt")
    workspace = tmp_path / "cli-eis-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "CLI EIS Workflow",
            "--slug",
            "cli-eis-workflow",
            "--direction",
            "EIS workflow",
            "--material",
            "oxide electrode",
            "--experiment-type",
            "electrochemical impedance spectroscopy",
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
            "sample-eis-001",
            "--experiment-ref",
            "exp-eis-001",
        ]
    ) == 0
    raw_output = _json_output(capsys)
    raw_metadata = Path(raw_output["metadata"])
    raw_metadata_ref = raw_metadata.relative_to(workspace).as_posix()

    assert main(["electrochemistry", "inspect", str(workspace), raw_output["project_raw_path"]]) == 0
    inspection = _json_output(capsys)
    assert inspection["file_kind"] == "electrochemistry"
    assert inspection["x_unit_candidate"] == "ohm"
    assert inspection["measurement_mode_candidate"] == "eis"
    assert "electrochemistry_eis_detected_future_work" not in inspection["warnings"]

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
            "x=z_real_ohm, y=neg_z_imag_ohm, x_unit=ohm, current_unit=unknown, mode=eis",
        ]
    ) == 0
    column_review = _json_output(capsys)

    context_text = "EIS Nyquist data; frequency order and perturbation amplitude reviewed by user"
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
            "sample-eis-001",
            "--x-column",
            "z_real_ohm",
            "--y-column",
            "neg_z_imag_ohm",
            "--x-unit",
            "ohm",
            "--current-unit",
            "unknown",
            "--measurement-mode",
            "eis",
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
    electrochemistry_metadata = Path(process_output["metadata"])
    electrochemistry = read_yaml(electrochemistry_metadata)
    eis_summary = electrochemistry["peak_analysis"]["eis_summary"]

    assert electrochemistry["status"] == "success"
    assert electrochemistry["measurement_mode"] == "eis"
    assert electrochemistry["x_unit"] == "ohm"
    assert electrochemistry["current_unit"] == "unknown"
    assert electrochemistry["peak_analysis"]["feature_count"] == 3
    assert abs(eis_summary["high_frequency_intercept_ohm"] - 10.0) < 0.01
    assert abs(eis_summary["real_axis_span_ohm"] - 90.0) < 0.01
    assert abs(eis_summary["max_neg_z_imag_ohm"] - 45.0) < 0.1
    assert "no equivalent-circuit fitting" in eis_summary["boundary"]
    feature_table = workspace / electrochemistry["outputs"]["feature_table"]
    assert feature_table.exists()
    assert "z_real_ohm,z_imag_ohm,neg_z_imag_ohm" in feature_table.read_text(encoding="utf-8").splitlines()[0]
    figure_record = read_yaml(workspace / "figures" / "index.yml")["figures"][electrochemistry["figure_id"]]
    assert figure_record["generation"]["parameters"]["measurement_mode"] == "eis"
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
            "sample-eis-001",
            "--experiment-ref",
            "exp-eis-001",
        ]
    ) == 0
    report_output = _json_output(capsys)
    report_frontmatter, report_body = read_markdown_record(Path(report_output["report"]))
    assert report_frontmatter["report_type"] == "electrochemistry_analysis"
    assert "## EIS Nyquist screening 摘要" in report_body
    assert "EIS Nyquist screening" in report_body
    assert "不能仅凭本次自动处理直接确认等效电路" in report_body
    assert "![Electrochemistry trace]" in report_body


def test_electrochemistry_docs_and_skill_references_are_discoverable() -> None:
    root = Path.cwd()

    readme = (root / "README.md").read_text(encoding="utf-8")
    skill = (root / "skills" / "ea-v0-2" / "SKILL.md").read_text(encoding="utf-8")
    cli_index = (root / "skills" / "ea-v0-2" / "references" / "cli-command-index.md").read_text(encoding="utf-8")
    electrochemistry_reference = root / "skills" / "ea-v0-2" / "references" / "electrochemistry-workflow.md"
    registry = read_yaml(root / "skill-registry" / "index.yml")

    assert "ea electrochemistry inspect" in readme
    assert "references/electrochemistry-workflow.md" in skill
    assert "ea electrochemistry process" in cli_index
    assert electrochemistry_reference.exists()
    reference_text = electrochemistry_reference.read_text(encoding="utf-8")
    assert "context_review_ref" in reference_text
    assert "EIS Nyquist" in reference_text
    assert "equivalent-circuit" in reference_text
    assert "correction_record" in reference_text
    assert "potential_conversion" in reference_text
    assert "ir_drop_correction" in reference_text
    assert "eis_circuit_fit" in reference_text
    assert "tafel_analysis" in reference_text
    assert "gcd_analysis" in reference_text
    electrochemistry_record = next(item for item in registry["skills"] if item["id"] == "ea.electrochemistry-analysis")
    assert "Minimal electrochemistry workflow implemented" in electrochemistry_record["notes"]
    assert "eis_nyquist_screening" in electrochemistry_record["notes"]
    assert "correction_records" in electrochemistry_record["notes"]
    assert "potential_conversion" in electrochemistry_record["notes"]
    assert "ir_drop_correction" in electrochemistry_record["notes"]
    assert "eis_circuit_fit" in electrochemistry_record["notes"]
    assert "tafel_analysis" in electrochemistry_record["notes"]
    assert "gcd_analysis" in electrochemistry_record["notes"]
