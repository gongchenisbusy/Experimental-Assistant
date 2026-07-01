from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from ea.cli import main
from ea.storage import read_markdown_record, read_yaml
from ea.xps import default_xps_processing_parameters, inspect_xps_file


def _json_output(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def _write_xps_fixture(path: Path) -> Path:
    lines = [
        "# x_unit = eV",
        "# x_label = binding energy",
        "# y_label = counts",
        "binding_energy_eV intensity",
    ]
    for index in range(2400):
        energy = 1200.0 - index * 0.5
        baseline = 0.035 + 0.00002 * energy
        signal = baseline
        for center, amplitude, width in [
            (284.8, 0.34, 1.4),
            (532.1, 0.26, 1.8),
            (711.0, 0.22, 2.2),
        ]:
            signal += amplitude * math.exp(-((energy - center) ** 2) / (2.0 * width**2))
        lines.append(f"{energy:.2f} {signal:.8f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _component_quantification_parameters() -> dict:
    parameters = default_xps_processing_parameters()
    parameters["component_quantification"] = {
        "enabled": True,
        "method": "reviewed_window_integration",
        "integration_baseline": "local_minimum",
        "min_points": 5,
        "source": "ea.xps.component_quantification:v0.2",
        "components": [
            {
                "component_id": "xps-c1s-001",
                "label": "C 1s reviewed window",
                "element": "C",
                "core_level": "1s",
                "binding_energy_window_eV": [282.5, 287.0],
                "sensitivity_factor": 1.0,
                "model": "reviewed_window",
                "background": "local_minimum",
            },
            {
                "component_id": "xps-o1s-001",
                "label": "O 1s reviewed window",
                "element": "O",
                "core_level": "1s",
                "binding_energy_window_eV": [529.0, 535.0],
                "sensitivity_factor": 2.93,
                "model": "reviewed_window",
                "background": "local_minimum",
            },
            {
                "component_id": "xps-fe2p-001",
                "label": "Fe 2p reviewed window",
                "element": "Fe",
                "core_level": "2p",
                "binding_energy_window_eV": [706.0, 716.0],
                "sensitivity_factor": 13.91,
                "model": "reviewed_window",
                "background": "local_minimum",
            },
        ],
    }
    parameters["background_model"] = {
        "enabled": True,
        "method": "reviewed_background_record",
        "source": "ea.xps.background_model:v0.2",
        "applied_to_processed_data": False,
        "software": {"name": "instrument export", "version": "reviewed"},
        "regions": [
            {
                "region_id": "xps-bg-c1s-001",
                "label": "C 1s Shirley background choice",
                "background_type": "shirley",
                "binding_energy_window_eV": [280.0, 292.0],
                "parameters": {"endpoint_strategy": "reviewed_component_edges"},
                "reference_ids": ["ref-xps-background-001"],
                "reviewer_notes": ["User confirmed Shirley background choice for C 1s interpretation."],
                "caveats": ["EA records this model choice only; no numeric Shirley subtraction was applied."],
                "confidence": "low",
            },
            {
                "region_id": "xps-bg-o1s-001",
                "label": "O 1s Tougaard background choice",
                "background_type": "tougaard",
                "binding_energy_window_eV": [526.0, 538.0],
                "parameters": {"parameter_source": "external fitting software"},
                "reference_ids": ["ref-xps-background-001"],
                "reviewer_notes": ["User confirmed Tougaard background model should be documented for future fitting."],
                "confidence": "low",
            },
        ],
    }
    parameters["background_subtraction"] = {
        "enabled": True,
        "method": "reviewed_linear_background_subtraction",
        "source": "ea.xps.background_subtraction:v0.2",
        "input_intensity_column": "processed_intensity",
        "background_column": "xps_linear_background",
        "corrected_intensity_column": "xps_background_subtracted_intensity",
        "region_id_column": "xps_background_subtraction_region_id",
        "min_points": 5,
        "reference_ids": ["ref-xps-background-001"],
        "regions": [
            {
                "region_id": "xps-bgsub-c1s-001",
                "label": "C 1s reviewed linear background",
                "binding_energy_window_eV": [280.0, 292.0],
                "left_anchor_window_eV": [280.0, 281.0],
                "right_anchor_window_eV": [291.0, 292.0],
                "reference_ids": ["ref-xps-background-001"],
                "reviewer_notes": ["User confirmed endpoint windows for a linear background preprocessing record."],
                "caveats": ["Linear subtraction only; not a Shirley/Tougaard model."],
                "confidence": "low",
            }
        ],
    }
    return parameters


def _shirley_background_subtraction_parameters() -> dict:
    parameters = default_xps_processing_parameters()
    parameters["background_subtraction"] = {
        "enabled": True,
        "method": "reviewed_shirley_background_subtraction",
        "source": "ea.xps.background_subtraction:v0.2",
        "input_intensity_column": "processed_intensity",
        "min_points": 5,
        "max_iterations": 200,
        "tolerance": 1e-5,
        "reference_ids": ["ref-xps-background-001"],
        "regions": [
            {
                "region_id": "xps-shirley-c1s-001",
                "label": "C 1s reviewed Shirley background",
                "binding_energy_window_eV": [280.0, 292.0],
                "left_anchor_window_eV": [280.0, 281.0],
                "right_anchor_window_eV": [291.0, 292.0],
                "reference_ids": ["ref-xps-background-001"],
                "reviewer_notes": ["User confirmed endpoint windows and Shirley iteration settings."],
                "caveats": ["Reviewed Shirley preprocessing only; not chemical-state proof."],
                "confidence": "low",
            }
        ],
    }
    return parameters


def _tougaard_background_subtraction_parameters() -> dict:
    parameters = default_xps_processing_parameters()
    parameters["background_subtraction"] = {
        "enabled": True,
        "method": "reviewed_tougaard_u2_background_subtraction",
        "source": "ea.xps.background_subtraction:v0.2",
        "input_intensity_column": "processed_intensity",
        "min_points": 5,
        "tougaard_B": 1200.0,
        "tougaard_C_eV2": 1643.0,
        "integration_direction": "toward_higher_binding_energy",
        "reference_ids": ["ref-xps-tougaard-001"],
        "regions": [
            {
                "region_id": "xps-tougaard-c1s-001",
                "label": "C 1s reviewed Tougaard U2 background",
                "binding_energy_window_eV": [280.0, 292.0],
                "left_anchor_window_eV": [280.0, 281.0],
                "right_anchor_window_eV": [291.0, 292.0],
                "reference_ids": ["ref-xps-tougaard-001"],
                "reviewer_notes": ["User confirmed endpoint windows and Tougaard U2 B/C parameters."],
                "caveats": ["Reviewed Tougaard U2 preprocessing only; not QUASES depth-profile modeling."],
                "confidence": "low",
            }
        ],
    }
    return parameters


def test_inspect_synthetic_xps_fixture(tmp_path: Path) -> None:
    fixture = _write_xps_fixture(tmp_path / "synthetic-xps-survey.txt")

    inspection = inspect_xps_file(fixture)

    assert inspection.file_kind == "xps"
    assert inspection.row_count == 2400
    assert inspection.x_column_candidate == "binding_energy_eV"
    assert inspection.y_column_candidate == "intensity"
    assert inspection.x_unit == "eV"
    assert inspection.requires_user_confirmation is True


def test_cli_runs_synthetic_xps_workflow_end_to_end(tmp_path: Path, capsys) -> None:
    fixture = _write_xps_fixture(tmp_path / "synthetic-xps-survey.txt")
    parameters = _component_quantification_parameters()
    workspace = tmp_path / "cli-xps-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "CLI XPS Workflow",
            "--slug",
            "cli-xps-workflow",
            "--direction",
            "XPS workflow",
            "--material",
            "oxide thin film",
            "--experiment-type",
            "materials XPS characterization",
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
            "xps",
            "--sample-ref",
            "sample-xps-001",
            "--experiment-ref",
            "exp-xps-001",
        ]
    ) == 0
    raw_output = _json_output(capsys)
    raw_metadata = Path(raw_output["metadata"])
    raw_metadata_ref = raw_metadata.relative_to(workspace).as_posix()

    assert raw_output["import_status"] == "imported"
    assert main(["xps", "inspect", str(workspace), raw_output["project_raw_path"]]) == 0
    inspection = _json_output(capsys)
    assert inspection["file_kind"] == "xps"
    assert inspection["x_unit"] == "eV"

    assert main(
        [
            "review",
            "add",
            str(workspace),
            "--target-type",
            "xps_columns",
            "--target-ref",
            raw_metadata_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            "x=binding_energy_eV, y=intensity, unit=eV",
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
            "xps_calibration",
            "--target-ref",
            raw_metadata_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            "C 1s reference at 284.8 eV; no additional shift needed",
        ]
    ) == 0
    calibration_review = _json_output(capsys)
    assert calibration_review["review_status"] == "user_confirmed"

    assert main(
        [
            "review",
            "add",
            str(workspace),
            "--target-type",
            "xps_parameters",
            "--target-ref",
            raw_metadata_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            json.dumps(parameters, ensure_ascii=False),
        ]
    ) == 0
    parameter_review = _json_output(capsys)
    assert parameter_review["review_status"] == "user_confirmed"

    assert main(
        [
            "xps",
            "process",
            str(workspace),
            "--metadata",
            raw_metadata_ref,
            "--project-id",
            project_id,
            "--sample-ref",
            "sample-xps-001",
            "--x-column",
            "binding_energy_eV",
            "--y-column",
            "intensity",
            "--x-unit",
            "eV",
            "--energy-shift-ev",
            "0.0",
            "--calibration-reference",
            "C 1s 284.8 eV user-confirmed reference",
            "--column-review-ref",
            column_review["review_id"],
            "--calibration-review-ref",
            calibration_review["review_id"],
            "--parameter-review-ref",
            parameter_review["review_id"],
            "--parameters-json",
            json.dumps(parameters, ensure_ascii=False),
        ]
    ) == 0
    process_output = _json_output(capsys)
    xps_metadata = Path(process_output["metadata"])
    xps = read_yaml(xps_metadata)

    assert xps["result_id"].startswith("res-cli-xps-workflow-xps-")
    assert xps["xps_result_id"] == xps["result_id"]
    assert xps["x_unit"] == "eV"
    assert xps["energy_shift_eV"] == 0.0
    assert "C 1s" in xps["calibration_reference"]
    assert xps["peak_analysis"]["peak_count"] > 0
    assert xps["peak_analysis"]["calibration"]["confidence"] == "low"
    component_summary = xps["peak_analysis"]["component_quantification"]
    assert component_summary["enabled"] is True
    assert component_summary["status"] == "rsf_normalized_screening"
    assert component_summary["quantified_component_count"] == 3
    assert component_summary["rsf_complete"] is True
    background_record = xps["peak_analysis"]["background_model"]
    assert background_record["status"] == "reviewed_background_model_recorded"
    assert background_record["region_count"] == 2
    assert "does not automatically perform Shirley/Tougaard" in background_record["boundary"]
    assert xps["outputs"]["background_model"].endswith("xps_background.yml")
    saved_background = read_yaml(workspace / xps["outputs"]["background_model"])
    assert saved_background["record_ref"] == xps["outputs"]["background_model"]
    assert {region["background_type"] for region in saved_background["regions"]} == {"shirley", "tougaard"}
    assert saved_background["regions"][0]["applied_to_processed_data"] is False
    assert saved_background["reference_ids"] == ["ref-xps-background-001"]
    subtraction_record = xps["peak_analysis"]["background_subtraction"]
    assert subtraction_record["status"] == "reviewed_linear_background_subtracted"
    assert subtraction_record["corrected_region_count"] == 1
    assert subtraction_record["record_ref"] == xps["outputs"]["background_subtraction"]
    assert subtraction_record["corrected_intensity_column"] == "xps_background_subtracted_intensity"
    assert "does not automatically choose endpoints" in subtraction_record["boundary"]
    assert xps["outputs"]["background_subtraction"].endswith("xps_background_subtraction.yml")
    saved_subtraction = read_yaml(workspace / xps["outputs"]["background_subtraction"])
    assert saved_subtraction["record_ref"] == xps["outputs"]["background_subtraction"]
    assert saved_subtraction["regions"][0]["status"] == "linear_background_subtracted"
    assert saved_subtraction["regions"][0]["left_anchor"]["mode"] == "window_mean"
    assert saved_subtraction["reference_ids"] == ["ref-xps-background-001"]
    interpretations = xps["peak_analysis"]["possible_interpretations"]
    assert any(xps["outputs"]["background_subtraction"] in item.get("evidence", []) for item in interpretations)
    assert xps["peak_analysis"]["possible_interpretations"]
    assert (workspace / xps["outputs"]["peak_table"]).exists()
    assert (workspace / xps["outputs"]["component_table"]).exists()
    assert (workspace / xps["outputs"]["background_model"]).exists()
    assert (workspace / xps["outputs"]["background_subtraction"]).exists()
    processed = pd.read_csv(workspace / xps["outputs"]["processed_csv"])
    assert "xps_linear_background" in processed.columns
    assert "xps_background_subtracted_intensity" in processed.columns
    corrected = processed.loc[processed["xps_background_subtraction_region_id"] == "xps-bgsub-c1s-001", "xps_background_subtracted_intensity"]
    assert corrected.notna().any()
    components = pd.read_csv(workspace / xps["outputs"]["component_table"])
    assert set(components["component_id"]) == {"xps-c1s-001", "xps-o1s-001", "xps-fe2p-001"}
    assert components["relative_atomic_percent_screening"].notna().all()
    assert math.isclose(float(components["relative_atomic_percent_screening"].sum()), 100.0, rel_tol=0.01)
    assert (workspace / xps["outputs"]["figure"]).exists()
    figure_record = read_yaml(workspace / "figures" / "index.yml")["figures"][xps["figure_id"]]
    assert figure_record["style_profile"] == "nature_like_clean"
    assert figure_record["generation"]["parameters"]["energy_shift_eV"] == 0.0
    assert figure_record["generation"]["parameters"]["processing_parameters"]["component_quantification"]["enabled"] is True
    assert xps["outputs"]["processed_csv"] in figure_record["source_data_refs"]
    assert xps["outputs"]["peak_table"] in figure_record["source_data_refs"]
    assert xps["outputs"]["component_table"] in figure_record["source_data_refs"]
    assert xps["outputs"]["background_model"] in figure_record["source_data_refs"]
    assert xps["outputs"]["background_subtraction"] in figure_record["source_data_refs"]

    assert main(
        [
            "xps",
            "report",
            str(workspace),
            "--metadata",
            xps_metadata.relative_to(workspace).as_posix(),
            "--project-id",
            project_id,
            "--sample-ref",
            "sample-xps-001",
            "--experiment-ref",
            "exp-xps-001",
        ]
    ) == 0
    report_output = _json_output(capsys)
    report_frontmatter, report_body = read_markdown_record(Path(report_output["report"]))
    assert report_frontmatter["report_type"] == "xps_analysis"
    assert "## XPS background model record" in report_body
    assert "## XPS reviewed background subtraction" in report_body
    assert "xps-bg-c1s-001" in report_body
    assert "xps-bgsub-c1s-001" in report_body
    assert "xps_background_subtracted_intensity" in report_body
    assert "shirley" in report_body
    assert "tougaard" in report_body
    assert "## XPS peak 参数" in report_body
    assert "## XPS component quantification screening" in report_body
    assert "xps-c1s-001" in report_body
    assert "atomic % screening" in report_body
    assert "![XPS spectrum]" in report_body
    assert "processed CSV" in report_body

    assert main(["healthcheck", str(workspace)]) == 0
    health = _json_output(capsys)
    assert health["status"] == "pass"

    assert main(["eval", "project", str(workspace), "--no-write"]) == 0
    evaluation = _json_output(capsys)
    assert evaluation["status"] == "pass"
    assert evaluation["figures"]["analysis_figure_count"] == 1
    assert evaluation["reports"]["report_count"] == 1


def test_cli_runs_reviewed_shirley_background_subtraction(tmp_path: Path, capsys) -> None:
    fixture = _write_xps_fixture(tmp_path / "synthetic-xps-shirley.txt")
    parameters = _shirley_background_subtraction_parameters()
    workspace = tmp_path / "cli-xps-shirley-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "CLI XPS Shirley Workflow",
            "--slug",
            "cli-xps-shirley",
            "--direction",
            "XPS Shirley workflow",
            "--material",
            "oxide thin film",
            "--experiment-type",
            "materials XPS characterization",
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
            "xps",
            "--sample-ref",
            "sample-xps-shirley-001",
            "--experiment-ref",
            "exp-xps-shirley-001",
        ]
    ) == 0
    raw_output = _json_output(capsys)
    raw_metadata_ref = Path(raw_output["metadata"]).relative_to(workspace).as_posix()

    for target_type, reviewed_content in [
        ("xps_columns", "x=binding_energy_eV, y=intensity, unit=eV"),
        ("xps_calibration", "C 1s reference at 284.8 eV; no additional shift needed"),
        ("xps_parameters", json.dumps(parameters, ensure_ascii=False)),
    ]:
        assert main(
            [
                "review",
                "add",
                str(workspace),
                "--target-type",
                target_type,
                "--target-ref",
                raw_metadata_ref,
                "--user-response",
                "可以，保存",
                "--reviewed-content",
                reviewed_content,
            ]
        ) == 0
        review = _json_output(capsys)
        if target_type == "xps_columns":
            column_review = review
        elif target_type == "xps_calibration":
            calibration_review = review
        else:
            parameter_review = review

    assert main(
        [
            "xps",
            "process",
            str(workspace),
            "--metadata",
            raw_metadata_ref,
            "--project-id",
            project_id,
            "--sample-ref",
            "sample-xps-shirley-001",
            "--x-column",
            "binding_energy_eV",
            "--y-column",
            "intensity",
            "--x-unit",
            "eV",
            "--energy-shift-ev",
            "0.0",
            "--calibration-reference",
            "C 1s 284.8 eV user-confirmed reference",
            "--column-review-ref",
            column_review["review_id"],
            "--calibration-review-ref",
            calibration_review["review_id"],
            "--parameter-review-ref",
            parameter_review["review_id"],
            "--parameters-json",
            json.dumps(parameters, ensure_ascii=False),
        ]
    ) == 0
    process_output = _json_output(capsys)
    xps_metadata = Path(process_output["metadata"])
    xps = read_yaml(xps_metadata)

    subtraction_record = xps["peak_analysis"]["background_subtraction"]
    assert subtraction_record["status"] == "reviewed_shirley_background_subtracted"
    assert subtraction_record["method"] == "reviewed_shirley_background_subtraction"
    assert subtraction_record["background_column"] == "xps_shirley_background"
    assert subtraction_record["corrected_intensity_column"] == "xps_shirley_subtracted_intensity"
    assert subtraction_record["corrected_region_count"] == 1
    saved_subtraction = read_yaml(workspace / xps["outputs"]["background_subtraction"])
    region = saved_subtraction["regions"][0]
    assert region["status"] == "shirley_background_subtracted"
    assert region["algorithm"] == "iterative_shirley_background"
    assert region["iterations"] <= 200
    assert region["converged"] is True
    assert "residual_area" in region
    processed = pd.read_csv(workspace / xps["outputs"]["processed_csv"])
    assert "xps_shirley_background" in processed.columns
    assert "xps_shirley_subtracted_intensity" in processed.columns
    corrected = processed.loc[processed["xps_background_subtraction_region_id"] == "xps-shirley-c1s-001", "xps_shirley_subtracted_intensity"]
    assert corrected.notna().any()
    figure_record = read_yaml(workspace / "figures" / "index.yml")["figures"][xps["figure_id"]]
    assert xps["outputs"]["background_subtraction"] in figure_record["source_data_refs"]
    assert any(xps["outputs"]["background_subtraction"] in item.get("evidence", []) for item in xps["peak_analysis"]["possible_interpretations"])

    assert main(
        [
            "xps",
            "report",
            str(workspace),
            "--metadata",
            xps_metadata.relative_to(workspace).as_posix(),
            "--project-id",
            project_id,
            "--sample-ref",
            "sample-xps-shirley-001",
            "--experiment-ref",
            "exp-xps-shirley-001",
        ]
    ) == 0
    report_output = _json_output(capsys)
    _, report_body = read_markdown_record(Path(report_output["report"]))
    assert "Reviewed XPS Shirley background subtraction" in report_body
    assert "xps-shirley-c1s-001" in report_body
    assert "xps_shirley_subtracted_intensity" in report_body
    assert "iterative_shirley_background" in report_body


def test_cli_runs_reviewed_tougaard_u2_background_subtraction(tmp_path: Path, capsys) -> None:
    fixture = _write_xps_fixture(tmp_path / "synthetic-xps-tougaard.txt")
    parameters = _tougaard_background_subtraction_parameters()
    workspace = tmp_path / "cli-xps-tougaard-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "CLI XPS Tougaard Workflow",
            "--slug",
            "cli-xps-tougaard",
            "--direction",
            "XPS Tougaard workflow",
            "--material",
            "oxide thin film",
            "--experiment-type",
            "materials XPS characterization",
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
            "xps",
            "--sample-ref",
            "sample-xps-tougaard-001",
            "--experiment-ref",
            "exp-xps-tougaard-001",
        ]
    ) == 0
    raw_output = _json_output(capsys)
    raw_metadata_ref = Path(raw_output["metadata"]).relative_to(workspace).as_posix()

    for target_type, reviewed_content in [
        ("xps_columns", "x=binding_energy_eV, y=intensity, unit=eV"),
        ("xps_calibration", "C 1s reference at 284.8 eV; no additional shift needed"),
        ("xps_parameters", json.dumps(parameters, ensure_ascii=False)),
    ]:
        assert main(
            [
                "review",
                "add",
                str(workspace),
                "--target-type",
                target_type,
                "--target-ref",
                raw_metadata_ref,
                "--user-response",
                "可以，保存",
                "--reviewed-content",
                reviewed_content,
            ]
        ) == 0
        review = _json_output(capsys)
        if target_type == "xps_columns":
            column_review = review
        elif target_type == "xps_calibration":
            calibration_review = review
        else:
            parameter_review = review

    assert main(
        [
            "xps",
            "process",
            str(workspace),
            "--metadata",
            raw_metadata_ref,
            "--project-id",
            project_id,
            "--sample-ref",
            "sample-xps-tougaard-001",
            "--x-column",
            "binding_energy_eV",
            "--y-column",
            "intensity",
            "--x-unit",
            "eV",
            "--energy-shift-ev",
            "0.0",
            "--calibration-reference",
            "C 1s 284.8 eV user-confirmed reference",
            "--column-review-ref",
            column_review["review_id"],
            "--calibration-review-ref",
            calibration_review["review_id"],
            "--parameter-review-ref",
            parameter_review["review_id"],
            "--parameters-json",
            json.dumps(parameters, ensure_ascii=False),
        ]
    ) == 0
    process_output = _json_output(capsys)
    xps_metadata = Path(process_output["metadata"])
    xps = read_yaml(xps_metadata)

    subtraction_record = xps["peak_analysis"]["background_subtraction"]
    assert subtraction_record["status"] == "reviewed_tougaard_u2_background_subtracted"
    assert subtraction_record["method"] == "reviewed_tougaard_u2_background_subtraction"
    assert subtraction_record["background_column"] == "xps_tougaard_u2_background"
    assert subtraction_record["corrected_intensity_column"] == "xps_tougaard_u2_subtracted_intensity"
    assert subtraction_record["tougaard_B"] == 1200.0
    assert subtraction_record["tougaard_C_eV2"] == 1643.0
    assert subtraction_record["integration_direction"] == "toward_higher_binding_energy"
    assert subtraction_record["corrected_region_count"] == 1
    assert "QUASES/depth-profile" in subtraction_record["boundary"]
    saved_subtraction = read_yaml(workspace / xps["outputs"]["background_subtraction"])
    region = saved_subtraction["regions"][0]
    assert region["status"] == "tougaard_u2_background_subtracted"
    assert region["algorithm"] == "reviewed_tougaard_u2_kernel"
    assert region["kernel"] == "delta_E/(C_eV2+delta_E^2)^2"
    assert region["tougaard_B"] == 1200.0
    assert region["tougaard_C_eV2"] == 1643.0
    assert region["integration_direction"] == "toward_higher_binding_energy"
    assert region["tougaard_integral_max"] >= 0.0
    processed = pd.read_csv(workspace / xps["outputs"]["processed_csv"])
    assert "xps_tougaard_u2_background" in processed.columns
    assert "xps_tougaard_u2_subtracted_intensity" in processed.columns
    corrected = processed.loc[processed["xps_background_subtraction_region_id"] == "xps-tougaard-c1s-001", "xps_tougaard_u2_subtracted_intensity"]
    assert corrected.notna().any()
    figure_record = read_yaml(workspace / "figures" / "index.yml")["figures"][xps["figure_id"]]
    assert xps["outputs"]["background_subtraction"] in figure_record["source_data_refs"]
    assert any(xps["outputs"]["background_subtraction"] in item.get("evidence", []) for item in xps["peak_analysis"]["possible_interpretations"])

    assert main(
        [
            "xps",
            "report",
            str(workspace),
            "--metadata",
            xps_metadata.relative_to(workspace).as_posix(),
            "--project-id",
            project_id,
            "--sample-ref",
            "sample-xps-tougaard-001",
            "--experiment-ref",
            "exp-xps-tougaard-001",
        ]
    ) == 0
    report_output = _json_output(capsys)
    _, report_body = read_markdown_record(Path(report_output["report"]))
    assert "Reviewed XPS Tougaard U2 background subtraction" in report_body
    assert "xps-tougaard-c1s-001" in report_body
    assert "xps_tougaard_u2_subtracted_intensity" in report_body
    assert "reviewed_tougaard_u2_kernel" in report_body
    assert "toward_higher_binding_energy" in report_body


def test_xps_docs_and_skill_references_are_discoverable() -> None:
    root = Path.cwd()

    readme = (root / "README.md").read_text(encoding="utf-8")
    skill = (root / "skills" / "ea-v0-2" / "SKILL.md").read_text(encoding="utf-8")
    xps_reference = root / "skills" / "ea-v0-2" / "references" / "xps-workflow.md"
    registry = read_yaml(root / "skill-registry" / "index.yml")

    assert "ea xps inspect" in readme
    assert "ea xps process" in skill
    assert "references/xps-workflow.md" in skill
    assert xps_reference.exists()
    xps_reference_text = xps_reference.read_text(encoding="utf-8")
    assert "calibration_review_ref" in xps_reference_text
    assert "component_quantification" in xps_reference_text
    assert "background_model" in xps_reference_text
    assert "background_subtraction" in xps_reference_text
    assert "reviewed_shirley_background_subtraction" in xps_reference_text
    assert "reviewed_tougaard_u2_background_subtraction" in xps_reference_text
    assert "screening-only" in xps_reference_text
    xps_record = next(item for item in registry["skills"] if item["id"] == "ea.xps-analysis")
    assert "component_quantification_screening" in xps_record["notes"]
    assert "background_model_records" in xps_record["notes"]
    assert "background_subtraction" in xps_record["notes"]
    assert "reviewed_shirley_background_subtraction" in xps_record["notes"]
    assert "reviewed_tougaard_u2_background_subtraction" in xps_record["notes"]
