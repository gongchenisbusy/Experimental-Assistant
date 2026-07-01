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


def _write_xps_spin_orbit_fixture(path: Path) -> Path:
    lines = [
        "# x_unit = eV",
        "# x_label = binding energy",
        "# y_label = counts",
        "binding_energy_eV intensity",
    ]
    for index in range(2400):
        energy = 1200.0 - index * 0.5
        baseline = 0.025 + 0.000015 * energy
        signal = baseline
        for center, amplitude, width in [
            (711.0, 0.36, 1.45),
            (724.4, 0.18, 1.45),
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


def _component_fit_parameters() -> dict:
    parameters = _component_quantification_parameters()
    parameters["component_fit"] = {
        "enabled": True,
        "method": "reviewed_component_fit_screening",
        "source": "ea.xps.component_fit:v0.2",
        "input_intensity_column": "xps_background_subtracted_intensity",
        "fit_intensity_column": "xps_component_fit_intensity",
        "residual_column": "xps_component_fit_residual",
        "region_id_column": "xps_component_fit_region_id",
        "min_points": 8,
        "max_nfev": 5000,
        "fit_quality_thresholds": {
            "max_rmse": 0.12,
            "min_r_squared": 0.70,
        },
        "reference_ids": ["ref-xps-fit-001"],
        "regions": [
            {
                "region_id": "xps-fit-c1s-region-001",
                "label": "C 1s reviewed component-fit region",
                "binding_energy_window_eV": [282.0, 288.0],
                "reference_ids": ["ref-xps-fit-001"],
                "reviewer_notes": ["User confirmed one reviewed Gaussian C 1s component for screening fit."],
                "caveats": ["Screening fit only; not chemical-state proof."],
                "confidence": "low",
                "components": [
                    {
                        "component_id": "xps-fit-c1s-001",
                        "label": "C 1s reviewed Gaussian fit",
                        "element": "C",
                        "core_level": "1s",
                        "peak_shape": "gaussian",
                        "initial_center_eV": 284.8,
                        "center_bounds_eV": [283.5, 286.0],
                        "initial_amplitude": 0.8,
                        "amplitude_bounds": [0.05, 1.5],
                        "initial_fwhm_eV": 3.2,
                        "fwhm_bounds_eV": [0.8, 6.0],
                        "reference_ids": ["ref-xps-fit-001"],
                        "reviewer_notes": ["Initial center and FWHM were reviewed from the synthetic C 1s region."],
                        "confidence": "low",
                    }
                ],
            }
        ],
    }
    return parameters


def _region_records_parameters() -> dict:
    parameters = _component_fit_parameters()
    parameters["region_records"] = {
        "enabled": True,
        "method": "reviewed_multi_region_project_record",
        "source": "ea.xps.region_records:v0.2",
        "min_points": 3,
        "default_calibration_group_id": "xps-calibration-c1s-2848",
        "reference_ids": ["ref-xps-region-001"],
        "regions": [
            {
                "region_id": "xps-region-survey-001",
                "label": "Reviewed XPS survey record",
                "region_role": "survey",
                "binding_energy_window_eV": [0.0, 1200.0],
                "calibration_group_id": "xps-calibration-c1s-2848",
                "reference_ids": ["ref-xps-region-001"],
                "reviewer_notes": ["User confirmed this file is the survey-level project XPS context."],
                "caveats": ["Survey region organization only; not quantitative composition."],
                "confidence": "low",
            },
            {
                "region_id": "xps-region-c1s-001",
                "label": "Reviewed C 1s core-level record",
                "region_role": "core_level",
                "element": "C",
                "core_level": "1s",
                "binding_energy_window_eV": [282.0, 288.0],
                "calibration_group_id": "xps-calibration-c1s-2848",
                "component_fit_ref": "reviewed-user-note:component-fit-c1s",
                "reference_ids": ["ref-xps-region-001", "ref-xps-fit-001"],
                "reviewer_notes": ["User linked this C 1s region to the reviewed component-fit screening record."],
                "caveats": ["Core-level grouping only; not chemical-state proof."],
                "confidence": "low",
            },
        ],
    }
    return parameters


def _spin_orbit_component_fit_parameters() -> dict:
    parameters = default_xps_processing_parameters()
    parameters["component_fit"] = {
        "enabled": True,
        "method": "reviewed_component_fit_screening",
        "source": "ea.xps.component_fit:v0.2",
        "input_intensity_column": "processed_intensity",
        "fit_intensity_column": "xps_spin_orbit_fit_intensity",
        "residual_column": "xps_spin_orbit_fit_residual",
        "region_id_column": "xps_spin_orbit_fit_region_id",
        "min_points": 8,
        "max_nfev": 5000,
        "fit_quality_thresholds": {
            "max_rmse": 0.12,
            "min_r_squared": 0.70,
        },
        "reference_ids": ["ref-xps-spin-orbit-001"],
        "regions": [
            {
                "region_id": "xps-fit-fe2p-region-001",
                "label": "Fe 2p reviewed spin-orbit constrained region",
                "binding_energy_window_eV": [706.0, 728.0],
                "reference_ids": ["ref-xps-spin-orbit-001"],
                "reviewer_notes": ["User confirmed reviewed Fe 2p doublet constraint values for screening."],
                "caveats": ["Spin-orbit constrained screening only; not chemical-state proof."],
                "confidence": "low",
                "spin_orbit_constraints": [
                    {
                        "constraint_id": "xps-spin-fe2p-001",
                        "group_id": "xps-spin-fe2p",
                        "anchor_component_id": "xps-fit-fe2p3-001",
                        "dependent_component_id": "xps-fit-fe2p1-001",
                        "center_delta_eV": 13.4,
                        "area_ratio": 0.5,
                        "fwhm_ratio": 1.0,
                        "parameter_origin": "user_confirmed_source_suggested",
                        "source_summary": "Fe 2p doublet screening values were checked against the registered XPS reference before user confirmation.",
                        "applicability_notes": [
                            "Applies only to the reviewed Fe 2p screening model and does not prove chemical state."
                        ],
                        "reference_ids": ["ref-xps-spin-orbit-001"],
                        "reviewer_notes": ["User confirmed the source-backed signed separation, area ratio, and FWHM ratio."],
                        "caveats": ["Source-backed screening constraint only; not chemical-state proof."],
                        "confidence": "low",
                    }
                ],
                "components": [
                    {
                        "component_id": "xps-fit-fe2p3-001",
                        "label": "Fe 2p3/2 reviewed anchor",
                        "element": "Fe",
                        "core_level": "2p3/2",
                        "peak_shape": "gaussian",
                        "spin_orbit_group_id": "xps-spin-fe2p",
                        "initial_center_eV": 711.0,
                        "center_bounds_eV": [709.0, 713.0],
                        "initial_amplitude": 0.35,
                        "amplitude_bounds": [0.05, 0.80],
                        "initial_fwhm_eV": 3.0,
                        "fwhm_bounds_eV": [0.8, 5.0],
                        "reference_ids": ["ref-xps-spin-orbit-001"],
                        "confidence": "low",
                    },
                    {
                        "component_id": "xps-fit-fe2p1-001",
                        "label": "Fe 2p1/2 reviewed dependent",
                        "element": "Fe",
                        "core_level": "2p1/2",
                        "peak_shape": "gaussian",
                        "spin_orbit_group_id": "xps-spin-fe2p",
                        "initial_center_eV": 724.4,
                        "center_bounds_eV": [722.0, 726.5],
                        "initial_amplitude": 0.18,
                        "amplitude_bounds": [0.02, 0.50],
                        "initial_fwhm_eV": 3.0,
                        "fwhm_bounds_eV": [0.8, 5.0],
                        "reference_ids": ["ref-xps-spin-orbit-001"],
                        "confidence": "low",
                    },
                ],
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


def test_cli_runs_reviewed_component_fit_screening(tmp_path: Path, capsys) -> None:
    fixture = _write_xps_fixture(tmp_path / "synthetic-xps-component-fit.txt")
    parameters = _component_fit_parameters()
    workspace = tmp_path / "cli-xps-component-fit-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "CLI XPS Component Fit Workflow",
            "--slug",
            "cli-xps-component-fit",
            "--direction",
            "XPS component fit workflow",
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
            "sample-xps-fit-001",
            "--experiment-ref",
            "exp-xps-fit-001",
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
            "sample-xps-fit-001",
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

    fit_record = xps["peak_analysis"]["component_fit"]
    assert fit_record["status"] == "reviewed_component_fit_screening"
    assert fit_record["method"] == "reviewed_component_fit_screening"
    assert fit_record["input_intensity_column"] == "xps_background_subtracted_intensity"
    assert fit_record["fitted_region_count"] == 1
    assert fit_record["fitted_component_count"] == 1
    assert "components" in fit_record["regions"][0]
    assert "does not automatically choose components" in fit_record["boundary"]
    assert xps["outputs"]["component_fit"].endswith("xps_component_fit.yml")
    assert xps["outputs"]["component_fit_table"].endswith("xps_component_fit.csv")
    saved_fit = read_yaml(workspace / xps["outputs"]["component_fit"])
    assert saved_fit["record_ref"] == xps["outputs"]["component_fit"]
    assert saved_fit["component_table_ref"] == xps["outputs"]["component_fit_table"]
    region = saved_fit["regions"][0]
    component = region["components"][0]
    assert region["status"] == "reviewed_component_fit_screening"
    assert component["component_id"] == "xps-fit-c1s-001"
    assert component["peak_shape"] == "gaussian"
    assert abs(component["fitted_center_eV"] - 284.8) < 0.5
    assert component["relative_fit_area_percent"] == 100.0
    assert region["fit_quality"]["r_squared"] is None or region["fit_quality"]["r_squared"] > 0.70
    processed = pd.read_csv(workspace / xps["outputs"]["processed_csv"])
    assert "xps_component_fit_intensity" in processed.columns
    assert "xps_component_fit_residual" in processed.columns
    fitted = processed.loc[processed["xps_component_fit_region_id"] == "xps-fit-c1s-region-001", "xps_component_fit_intensity"]
    assert fitted.notna().any()
    fit_table = pd.read_csv(workspace / xps["outputs"]["component_fit_table"])
    assert fit_table.loc[0, "component_id"] == "xps-fit-c1s-001"
    assert fit_table.loc[0, "status"] == "fitted"
    figure_record = read_yaml(workspace / "figures" / "index.yml")["figures"][xps["figure_id"]]
    assert xps["outputs"]["component_fit"] in figure_record["source_data_refs"]
    assert xps["outputs"]["component_fit_table"] in figure_record["source_data_refs"]
    assert any(xps["outputs"]["component_fit"] in item.get("evidence", []) for item in xps["peak_analysis"]["possible_interpretations"])

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
            "sample-xps-fit-001",
            "--experiment-ref",
            "exp-xps-fit-001",
        ]
    ) == 0
    report_output = _json_output(capsys)
    _, report_body = read_markdown_record(Path(report_output["report"]))
    assert "## XPS reviewed component fit screening" in report_body
    assert "xps-fit-c1s-001" in report_body
    assert "xps_component_fit_intensity" in report_body
    assert "Screening fit only" in report_body or "screening" in report_body


def test_cli_runs_reviewed_spin_orbit_constrained_component_fit(tmp_path: Path, capsys) -> None:
    fixture = _write_xps_spin_orbit_fixture(tmp_path / "synthetic-xps-spin-orbit.txt")
    parameters = _spin_orbit_component_fit_parameters()
    workspace = tmp_path / "cli-xps-spin-orbit-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "CLI XPS Spin Orbit Workflow",
            "--slug",
            "cli-xps-spin-orbit",
            "--direction",
            "XPS spin-orbit constrained component fit workflow",
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
            "sample-xps-spin-001",
            "--experiment-ref",
            "exp-xps-spin-001",
        ]
    ) == 0
    raw_output = _json_output(capsys)
    raw_metadata_ref = Path(raw_output["metadata"]).relative_to(workspace).as_posix()

    for target_type, reviewed_content in [
        ("xps_columns", "x=binding_energy_eV, y=intensity, unit=eV"),
        ("xps_calibration", "Fe 2p reviewed calibration context; no additional shift needed"),
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
            "sample-xps-spin-001",
            "--x-column",
            "binding_energy_eV",
            "--y-column",
            "intensity",
            "--x-unit",
            "eV",
            "--energy-shift-ev",
            "0.0",
            "--calibration-reference",
            "Fe 2p user-confirmed reference context",
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

    fit_record = xps["peak_analysis"]["component_fit"]
    assert fit_record["status"] == "reviewed_component_fit_screening"
    assert fit_record["spin_orbit_constraint_count"] == 1
    assert fit_record["constrained_component_count"] == 1
    region = fit_record["regions"][0]
    assert region["spin_orbit_constraint_count"] == 1
    constraint = region["spin_orbit_constraints"][0]
    assert constraint["constraint_id"] == "xps-spin-fe2p-001"
    assert constraint["center_delta_eV"] == 13.4
    assert constraint["parameter_origin"] == "user_confirmed_source_suggested"
    assert "registered XPS reference" in constraint["source_summary"]
    assert constraint["applicability_notes"] == [
        "Applies only to the reviewed Fe 2p screening model and does not prove chemical state."
    ]
    components = {component["component_id"]: component for component in region["components"]}
    anchor = components["xps-fit-fe2p3-001"]
    dependent = components["xps-fit-fe2p1-001"]
    assert anchor["spin_orbit_role"] == "anchor"
    assert dependent["spin_orbit_role"] == "dependent"
    assert dependent["spin_orbit_constraint_status"] == "applied"
    assert abs((dependent["fitted_center_eV"] - anchor["fitted_center_eV"]) - 13.4) < 1.0e-6
    assert abs((dependent["fitted_fwhm_eV"] / anchor["fitted_fwhm_eV"]) - 1.0) < 1.0e-6
    assert abs((dependent["fitted_area"] / anchor["fitted_area"]) - 0.5) < 1.0e-6

    fit_table = pd.read_csv(workspace / xps["outputs"]["component_fit_table"])
    assert "spin_orbit_constraint_id" in fit_table.columns
    assert "spin_orbit_parameter_origin" in fit_table.columns
    assert set(fit_table["spin_orbit_role"].dropna()) == {"anchor", "dependent"}
    assert set(fit_table["spin_orbit_constraint_id"].dropna()) == {"xps-spin-fe2p-001"}
    assert set(fit_table["spin_orbit_parameter_origin"].dropna()) == {"user_confirmed_source_suggested"}
    figure_record = read_yaml(workspace / "figures" / "index.yml")["figures"][xps["figure_id"]]
    assert xps["outputs"]["component_fit"] in figure_record["source_data_refs"]
    assert xps["outputs"]["component_fit_table"] in figure_record["source_data_refs"]

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
            "sample-xps-spin-001",
            "--experiment-ref",
            "exp-xps-spin-001",
        ]
    ) == 0
    report_output = _json_output(capsys)
    _, report_body = read_markdown_record(Path(report_output["report"]))
    assert "spin-orbit constraints" in report_body
    assert "source-backed" in report_body
    assert "xps-spin-fe2p-001" in report_body
    assert "dependent" in report_body
    assert "不自动选择" in report_body or "screening" in report_body


def test_cli_records_source_backed_xps_parameter_suggestions(tmp_path: Path, capsys) -> None:
    workspace = tmp_path / "cli-xps-parameter-suggestion-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "CLI XPS Parameter Suggestions",
            "--slug",
            "cli-xps-parameter-suggestions",
            "--direction",
            "XPS source-backed parameter suggestion workflow",
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
            "references",
            "add",
            str(workspace),
            "--project-id",
            project_id,
            "--citation",
            "NIST XPS database entry and user-reviewed method note for Fe 2p and Tougaard U2 screening parameters.",
            "--title",
            "User-reviewed XPS reference parameter note",
            "--url",
            "https://example.org/xps-reference-note",
            "--source-type",
            "manual",
        ]
    ) == 0
    reference = _json_output(capsys)
    ref_id = Path(reference["reference"]).stem

    source_packet = workspace / "xps_parameter_source.yml"
    source_packet.write_text(
        f"""
candidates:
  - candidate_id: xps-param-fe2p-spin-001
    suggestion_type: spin_orbit_constraint
    element: Fe
    core_level: 2p
    constraint_id: xps-spin-fe2p-source-001
    center_delta_eV: 13.4
    area_ratio: 0.5
    fwhm_ratio: 1.0
    parameter_origin: source_suggested
    source_summary: Fe 2p spin-orbit screening values from the registered project XPS reference.
    applicability_notes:
      - Applies only if the user confirms Fe 2p anchor/dependent component IDs and reviewed bounds.
    reference_ids:
      - {ref_id}
    confidence: low
    caveats:
      - Candidate constraint only; not chemical-state proof.
  - candidate_id: xps-param-tougaard-u2-001
    suggestion_type: tougaard_parameter
    tougaard_C_eV2: 1643.0
    integration_direction: toward_higher_binding_energy
    parameter_origin: source_suggested
    source_summary: Tougaard U2 C value from the registered project XPS reference.
    applicability_notes:
      - Requires user-reviewed background region and B scale before subtraction.
    reference_ids:
      - {ref_id}
    confidence: low
  - candidate_id: xps-param-unregistered-ref-001
    suggestion_type: spin_orbit_constraint
    center_delta_eV: 5.0
    area_ratio: 0.5
    fwhm_ratio: 1.0
    parameter_origin: source_suggested
    source_summary: Candidate with a deliberately missing reference record.
    applicability_notes:
      - Used to verify unresolved reference handling.
    reference_ids:
      - ref-missing-001
    confidence: low
""".strip(),
        encoding="utf-8",
    )

    assert main(
        [
            "xps",
            "suggest-parameters",
            str(workspace),
            "--source-file",
            source_packet.relative_to(workspace).as_posix(),
            "--project-id",
            project_id,
            "--related-record",
            "raw/xps/example-metadata.yml",
        ]
    ) == 0
    output = _json_output(capsys)
    assert output["status"] == "ready_for_user_review"
    assert output["candidate_count"] == 3
    assert output["ready_for_user_review_count"] == 2
    assert output["needs_reference_registration_count"] == 1

    record = read_yaml(Path(output["record"]))
    table = pd.read_csv(Path(output["table"]))
    assert record["source"] == "ea.xps.parameter_suggestions:v0.2"
    assert record["ready_for_user_review_count"] == 2
    assert record["needs_reference_registration_count"] == 1
    assert record["candidates"][0]["auto_applied"] is False
    assert record["candidates"][0]["target_parameter_path"] == "component_fit.spin_orbit_constraints"
    assert record["candidates"][1]["target_parameter_path"] == "background_subtraction.tougaard"
    assert record["candidates"][2]["status"] == "needs_reference_registration"
    assert "ref-missing-001" in record["candidates"][2]["unresolved_reference_ids"]
    assert "Ask the user to review ready candidates" in " ".join(record["next_steps"])
    assert "does not run network lookup" in " ".join(record["boundaries"])
    assert (workspace / record["provenance_ref"]).exists()
    assert set(table["status"]) == {"ready_for_user_review", "needs_reference_registration"}
    assert set(table["auto_applied"]) == {False}
    assert "processed" not in output["record"]


def test_cli_builds_xps_parameter_source_packet_from_library(tmp_path: Path, capsys) -> None:
    workspace = tmp_path / "cli-xps-source-packet-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "CLI XPS Source Packet",
            "--slug",
            "cli-xps-source-packet",
            "--direction",
            "XPS parameter source packet workflow",
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
            "references",
            "add",
            str(workspace),
            "--project-id",
            project_id,
            "--citation",
            "User-curated XPS reference note with source-backed Fe 2p and Tougaard candidates.",
            "--title",
            "Project XPS parameter note",
            "--url",
            "https://example.org/project-xps-parameter-note",
            "--source-type",
            "manual",
        ]
    ) == 0
    reference = _json_output(capsys)
    ref_id = Path(reference["reference"]).stem

    library = workspace / "project_xps_parameter_library.yml"
    library.write_text(
        f"""
schema_version: "0.2"
library_id: project-xps-library
candidates:
  - candidate_id: xps-param-fe2p-spin-001
    suggestion_type: spin_orbit_constraint
    element: Fe
    core_level: 2p
    constraint_id: xps-spin-fe2p-source-001
    center_delta_eV: 13.4
    area_ratio: 0.5
    fwhm_ratio: 1.0
    source_summary: Fe 2p spin-orbit screening values from the project source library.
    applicability_notes:
      - Applies only after reviewed Fe 2p component IDs, bounds, and background are confirmed.
    reference_ids:
      - {ref_id}
    confidence: low
  - candidate_id: xps-param-tougaard-u2-001
    suggestion_type: tougaard_parameter
    tougaard_C_eV2: 1643.0
    integration_direction: toward_higher_binding_energy
    parameter_origin: source_suggested
    source_summary: Tougaard U2 C candidate from the project source library.
    applicability_notes:
      - Requires a reviewed background region and user-confirmed B scale before subtraction.
    reference_ids:
      - {ref_id}
    confidence: low
  - candidate_id: xps-param-o1s-spin-ignored
    suggestion_type: spin_orbit_constraint
    element: O
    core_level: 1s
    center_delta_eV: 1.0
    area_ratio: 1.0
    fwhm_ratio: 1.0
    source_summary: Filtered-out candidate.
    applicability_notes:
      - Used only to verify filtering.
    reference_ids:
      - {ref_id}
""".strip(),
        encoding="utf-8",
    )

    assert main(
        [
            "xps",
            "build-source-packet",
            str(workspace),
            "--library-file",
            library.relative_to(workspace).as_posix(),
            "--output",
            "suggestions/xps/source-packets/fe2p_packet.yml",
            "--project-id",
            project_id,
            "--include-candidate",
            "xps-param-fe2p-spin-001",
            "--include-candidate",
            "xps-param-tougaard-u2-001",
        ]
    ) == 0
    packet_output = _json_output(capsys)
    assert packet_output["status"] == "ready_for_suggest_parameters"
    assert packet_output["candidate_count"] == 2
    packet = read_yaml(Path(packet_output["source_packet"]))
    assert packet["source"] == "ea.xps.parameter_source_packet:v0.2"
    assert packet["source_library_ref"] == library.relative_to(workspace).as_posix()
    assert packet["candidate_count"] == 2
    assert packet["candidates"][0]["parameter_origin"] == "source_suggested"
    assert packet["filters"]["include_candidates"] == ["xps-param-fe2p-spin-001", "xps-param-tougaard-u2-001"]
    assert "does not run network lookup" in " ".join(packet["boundaries"])
    assert (workspace / packet["provenance_ref"]).exists()

    assert main(
        [
            "xps",
            "suggest-parameters",
            str(workspace),
            "--source-file",
            Path(packet_output["source_packet"]).relative_to(workspace).as_posix(),
            "--project-id",
            project_id,
        ]
    ) == 0
    suggestion_output = _json_output(capsys)
    assert suggestion_output["status"] == "ready_for_user_review"
    assert suggestion_output["ready_for_user_review_count"] == 2

    assert main(["xps", "build-source-packet", str(workspace), "--project-id", project_id, "--write-template"]) == 0
    template_output = _json_output(capsys)
    template_packet = read_yaml(Path(template_output["source_packet"]))
    assert template_output["status"] == "template_requires_user_edit"
    assert template_packet["candidate_count"] == 2
    assert template_packet["source_packet_id"].startswith("xps_source_packet-")
    assert template_packet["candidates"][0]["center_delta_eV"] is None


def test_cli_runs_reviewed_multi_region_records(tmp_path: Path, capsys) -> None:
    fixture = _write_xps_fixture(tmp_path / "synthetic-xps-region-records.txt")
    parameters = _region_records_parameters()
    workspace = tmp_path / "cli-xps-region-records-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "CLI XPS Region Records Workflow",
            "--slug",
            "cli-xps-region-records",
            "--direction",
            "XPS region records workflow",
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
            "sample-xps-region-001",
            "--experiment-ref",
            "exp-xps-region-001",
        ]
    ) == 0
    raw_output = _json_output(capsys)
    raw_metadata_ref = Path(raw_output["metadata"]).relative_to(workspace).as_posix()

    for target_type, reviewed_content in [
        ("xps_columns", "x=binding_energy_eV, y=intensity, unit=eV"),
        ("xps_calibration", "C 1s reference at 284.8 eV; one reviewed calibration group"),
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
            "sample-xps-region-001",
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

    region_record = xps["peak_analysis"]["region_records"]
    assert region_record["status"] == "reviewed_multi_region_project_record"
    assert region_record["reviewed_region_count"] == 2
    assert "does not automatically share" in region_record["boundary"]
    assert xps["outputs"]["region_records"].endswith("xps_region_records.yml")
    assert xps["outputs"]["region_records_table"].endswith("xps_region_records.csv")
    saved_regions = read_yaml(workspace / xps["outputs"]["region_records"])
    assert saved_regions["record_ref"] == xps["outputs"]["region_records"]
    assert saved_regions["region_table_ref"] == xps["outputs"]["region_records_table"]
    assert saved_regions["regions"][0]["region_role"] == "survey"
    assert saved_regions["regions"][1]["region_role"] == "core_level"
    assert saved_regions["regions"][1]["calibration_group_id"] == "xps-calibration-c1s-2848"
    assert xps["outputs"]["component_fit"] in saved_regions["regions"][1]["linked_output_refs"]
    region_table = pd.read_csv(workspace / xps["outputs"]["region_records_table"])
    assert set(region_table["region_id"]) == {"xps-region-survey-001", "xps-region-c1s-001"}
    figure_record = read_yaml(workspace / "figures" / "index.yml")["figures"][xps["figure_id"]]
    assert xps["outputs"]["region_records"] in figure_record["source_data_refs"]
    assert xps["outputs"]["region_records_table"] in figure_record["source_data_refs"]

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
            "sample-xps-region-001",
            "--experiment-ref",
            "exp-xps-region-001",
        ]
    ) == 0
    report_output = _json_output(capsys)
    _, report_body = read_markdown_record(Path(report_output["report"]))
    assert "## XPS reviewed multi-region records" in report_body
    assert "xps-region-c1s-001" in report_body
    assert "xps_region_records.yml" in report_body
    assert "不自动共享 charge correction" in report_body


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
    assert "component_fit" in xps_reference_text
    assert "spin_orbit_constraints" in xps_reference_text
    assert "build-source-packet" in xps_reference_text
    assert "xps_parameter_source_packet" in xps_reference_text
    assert "suggest-parameters" in xps_reference_text
    assert "xps_parameter_suggestions" in xps_reference_text
    assert "region_records" in xps_reference_text
    assert "background_model" in xps_reference_text
    assert "background_subtraction" in xps_reference_text
    assert "reviewed_shirley_background_subtraction" in xps_reference_text
    assert "reviewed_tougaard_u2_background_subtraction" in xps_reference_text
    assert "screening-only" in xps_reference_text
    xps_record = next(item for item in registry["skills"] if item["id"] == "ea.xps-analysis")
    assert "component_quantification_screening" in xps_record["notes"]
    assert "component_fit" in xps_record["notes"]
    assert "parameter_source_packets" in xps_record["notes"]
    assert "parameter_suggestions" in xps_record["notes"]
    assert "spin_orbit_constraints" in xps_record["notes"]
    assert "region_records" in xps_record["notes"]
    assert "background_model_records" in xps_record["notes"]
    assert "background_subtraction" in xps_record["notes"]
    assert "reviewed_shirley_background_subtraction" in xps_record["notes"]
    assert "reviewed_tougaard_u2_background_subtraction" in xps_record["notes"]
