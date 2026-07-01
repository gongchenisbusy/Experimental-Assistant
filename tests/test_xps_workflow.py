from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
import pytest

from ea.cli import main
from ea.storage import read_markdown_record, read_yaml
from ea.xps import XPSProcessingError, build_xps_parameter_source_packet, default_xps_processing_parameters, inspect_xps_file


def _json_output(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def _register_xps_spin_orbit_reference_seed(workspace: Path, project_id: str, capsys) -> None:
    reference_seed_packet = workspace / "xps_spin_orbit_reference_seed.yml"
    reference_seed_packet.write_text(
        """
reference_seeds:
  ref-xps-spin-orbit-001:
    citation: "User-reviewed XPS spin-orbit reference note. Example Journal (2026)."
    title: "User-reviewed XPS spin-orbit reference note"
    year: 2026
    url: "https://example.org/xps-spin-orbit-reference-note"
    source_type: manual
""".strip()
        + "\n",
        encoding="utf-8",
    )
    assert (
        main(
            [
                "references",
                "register-seeds",
                str(workspace),
                "--source-packet",
                reference_seed_packet.relative_to(workspace).as_posix(),
                "--project-id",
                project_id,
            ]
        )
        == 0
    )
    reference_seed_output = _json_output(capsys)
    assert reference_seed_output["imported_count"] == 1


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
    assert "may suggest source-backed endpoints/windows" in subtraction_record["boundary"]
    assert "does not silently choose or apply them" in subtraction_record["boundary"]
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
    assert "may use reviewed user-provided or source-backed" in fit_record["boundary"]
    assert "does not silently choose them" in fit_record["boundary"]
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
    _register_xps_spin_orbit_reference_seed(workspace, project_id, capsys)

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

    suggestion_source = workspace / "xps_spin_orbit_parameter_source.yml"
    suggestion_source.write_text(
        """
candidates:
  - candidate_id: xps-param-fe2p-spin-report-001
    suggestion_type: spin_orbit_constraint
    element: Fe
    core_level: 2p
    constraint_id: xps-spin-fe2p-001
    center_delta_eV: 13.4
    area_ratio: 0.5
    fwhm_ratio: 1.0
    parameter_origin: user_confirmed_source_suggested
    source_summary: Fe 2p spin-orbit screening values from the registered XPS reference used for the reviewed component-fit screening.
    applicability_notes:
      - Applies only to this reviewed Fe 2p screening model and does not prove chemical state.
    reference_ids:
      - ref-xps-spin-orbit-001
    confidence: low
    caveats:
      - Candidate constraint only; report discussion does not apply parameters.
  - candidate_id: xps-param-fe2p-be-report-001
    suggestion_type: binding_energy_candidate
    element: Fe
    core_level: 2p3/2
    chemical_state_label: Fe(III) oxide binding-energy candidate
    expected_binding_energy_eV: 710.8
    binding_energy_window_eV: [710.0, 711.8]
    calibration_reference: C 1s 284.8 eV user-confirmed reference from the processed XPS calibration record.
    charge_reference_assumption: Same calibrated spectrum; no automatic charge correction is applied by this suggestion record.
    parameter_origin: source_suggested
    source_summary: Fe 2p3/2 oxide binding-energy discussion candidate from the registered XPS reference.
    applicability_notes:
      - Applies only to calibrated Fe 2p spectra with reviewed background/model context; check satellite and multiplet overlap before interpretation.
    overlap_notes:
      - Fe 2p satellites and mixed-valence components may overlap this window.
    reference_ids:
      - ref-xps-spin-orbit-001
    confidence: low
    caveats:
      - Binding-energy candidate only; not a chemical-state proof.
""".strip()
        + "\n",
        encoding="utf-8",
    )
    assert (
        main(
            [
                "xps",
                "suggest-parameters",
                str(workspace),
                "--source-file",
                suggestion_source.relative_to(workspace).as_posix(),
                "--project-id",
                project_id,
                "--related-record",
                xps_metadata.relative_to(workspace).as_posix(),
            ]
        )
        == 0
    )
    suggestion_output = _json_output(capsys)
    assert suggestion_output["status"] == "ready_for_user_review"

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
            "--parameter-suggestion",
            Path(suggestion_output["record"]).relative_to(workspace).as_posix(),
        ]
    ) == 0
    report_output = _json_output(capsys)
    report_frontmatter, report_body = read_markdown_record(Path(report_output["report"]))
    assert "ref-xps-spin-orbit-001" in report_frontmatter["reference_ids"]
    assert "spin-orbit constraints" in report_body
    assert "source-backed" in report_body
    assert "xps-spin-fe2p-001" in report_body
    assert "dependent" in report_body
    assert "## Source-backed XPS parameter suggestions" in report_body
    assert "xps-param-fe2p-spin-report-001" in report_body
    assert "spin_orbit_constraint[1]" in report_body
    assert "target_parameter_path: `component_fit.spin_orbit_constraints`" in report_body
    assert "review_state: `ready_for_user_review`" in report_body
    assert "Fe 2p spin-orbit screening values" in report_body
    assert "xps-param-fe2p-be-report-001" in report_body
    assert "binding_energy_candidate" in report_body
    assert "Fe(III) oxide binding-energy candidate" in report_body
    assert "expected_binding_energy_eV=710.8" in report_body
    assert "charge_reference_assumption=Same calibrated spectrum" in report_body
    assert "不会自动写入 processing parameters" in report_body
    assert "不能单独证明化学态" in report_body
    assert "User-reviewed XPS spin-orbit reference note" in report_body
    assert "不静默选择" in report_body or "screening" in report_body


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
  - candidate_id: xps-param-fe2p-be-001
    suggestion_type: binding_energy_candidate
    element: Fe
    core_level: 2p3/2
    chemical_state_label: Fe(III) oxide binding-energy candidate
    expected_binding_energy_eV: 710.8
    binding_energy_window_eV:
      - 710.0
      - 711.8
    calibration_reference: C 1s 284.8 eV user-confirmed reference from the project calibration record.
    charge_reference_assumption: Same calibrated spectrum; this suggestion does not apply a new charge correction.
    calibration_group_id: cal-fe2p-c1s-001
    parameter_origin: source_suggested
    source_summary: Fe 2p3/2 oxide BE candidate from the registered project XPS reference.
    applicability_notes:
      - Use only with reviewed Fe 2p calibration/background/model context and cross-check nearby satellites.
    overlap_notes:
      - Multiplet splitting, satellites, and mixed Fe states may overlap the proposed window.
    reference_ids:
      - {ref_id}
    confidence: low
    caveats:
      - Candidate discussion only; not chemical-state proof.
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
    assert output["candidate_count"] == 4
    assert output["ready_for_user_review_count"] == 3
    assert output["needs_reference_registration_count"] == 1

    record = read_yaml(Path(output["record"]))
    table = pd.read_csv(Path(output["table"]))
    assert record["source"] == "ea.xps.parameter_suggestions:v0.2"
    assert record["ready_for_user_review_count"] == 3
    assert record["needs_reference_registration_count"] == 1
    assert record["candidates"][0]["auto_applied"] is False
    assert record["candidates"][0]["target_parameter_path"] == "component_fit.spin_orbit_constraints"
    assert record["candidates"][1]["target_parameter_path"] == "background_subtraction.tougaard"
    assert record["candidates"][2]["target_parameter_path"] == "interpretation.binding_energy_candidates"
    assert record["candidates"][2]["chemical_state_label"] == "Fe(III) oxide binding-energy candidate"
    assert record["candidates"][2]["expected_binding_energy_eV"] == 710.8
    assert record["candidates"][2]["binding_energy_window_eV"] == [710.0, 711.8]
    assert record["candidates"][2]["calibration_reference"].startswith("C 1s 284.8 eV")
    assert record["candidates"][2]["charge_reference_assumption"].startswith("Same calibrated spectrum")
    assert record["candidates"][2]["status"] == "ready_for_user_review"
    assert record["candidates"][3]["status"] == "needs_reference_registration"
    assert "ref-missing-001" in record["candidates"][3]["unresolved_reference_ids"]
    assert "Ask the user to review ready candidates" in " ".join(record["next_steps"])
    assert "binding-energy candidates" in " ".join(record["next_steps"])
    assert "does not perform unconfirmed live network lookup" in " ".join(record["boundaries"])
    assert "EA may prepare source packets" in " ".join(record["boundaries"])
    assert (workspace / record["provenance_ref"]).exists()
    assert set(table["status"]) == {"ready_for_user_review", "needs_reference_registration"}
    assert set(table["auto_applied"]) == {False}
    assert "chemical_state_label" in table.columns
    assert "Fe(III) oxide binding-energy candidate" in set(table["chemical_state_label"].dropna())
    assert "processed" not in output["record"]

    suggestion_ref = Path(output["record"]).relative_to(workspace).as_posix()
    review_count_before_package = len(list((workspace / "reviews").glob("*.yml")))
    assert main(["xps", "prepare-review", str(workspace), "--project-id", project_id, "--suggestion", suggestion_ref]) == 0
    review_package_output = _json_output(capsys)
    assert review_package_output["status"] == "review_package_prepared"
    assert review_package_output["selected_candidate_count"] == 4
    assert review_package_output["selected_status_counts"]["ready_for_user_review"] == 3
    assert review_package_output["selected_status_counts"]["needs_reference_registration"] == 1
    assert len(list((workspace / "reviews").glob("*.yml"))) == review_count_before_package

    review_package = read_yaml(Path(review_package_output["review_package"]))
    review_package_markdown = Path(review_package_output["review_package_markdown"]).read_text(encoding="utf-8")
    assert review_package["source"] == "ea.xps.parameter_review_package:v0.2"
    assert review_package["review_target_type"] == "xps_parameter_suggestions"
    assert review_package["review_target_ref"] == suggestion_ref
    assert review_package["groups"][0]["group"] == "ready_for_user_review"
    assert set(review_package["groups"][0]["candidate_ids"]) == {
        "xps-param-fe2p-spin-001",
        "xps-param-tougaard-u2-001",
        "xps-param-fe2p-be-001",
    }
    assert "ref-missing-001" in review_package["unresolved_reference_ids"]
    assert "ea review add /path/to/ea-project" in review_package["recommended_commands"]["create_review_record"]
    assert "ea xps propose-memory" in review_package["recommended_commands"]["propose_memory_after_review"]
    assert "does not create a ReviewRecord" in " ".join(review_package["boundaries"])
    assert "XPS Parameter Suggestion Review Package" in review_package_markdown
    assert "xps-param-fe2p-spin-001" in review_package_markdown
    assert "xps-param-fe2p-be-001" in review_package_markdown
    assert "Fe(III) oxide binding-energy candidate" in review_package_markdown
    assert "expected_binding_energy_eV=710.8" in review_package_markdown
    assert "does not apply XPS parameters" in review_package_markdown

    assert (
        main(
            [
                "review",
                "add",
                str(workspace),
                "--target-type",
                "xps_parameter_suggestions",
                "--target-ref",
                suggestion_ref,
                "--user-response",
                "可以，保存",
                "--reviewed-content",
                "用户确认 ready XPS source-backed 参数候选可作为后续方法讨论的草稿记忆候选。",
            ]
        )
        == 0
    )
    suggestion_review = _json_output(capsys)

    assert (
        main(
            [
                "xps",
                "propose-memory",
                str(workspace),
                "--project-id",
                project_id,
                "--suggestion",
                suggestion_ref,
                "--review-ref",
                suggestion_review["review_id"],
            ]
        )
        == 0
    )
    memory_output = _json_output(capsys)
    assert memory_output["status"] == "memory_candidates_proposed"
    assert memory_output["proposed_count"] == 3
    assert memory_output["skipped_count"] == 1
    assert memory_output["provenance_ref"]
    assert "does not commit confirmed memory" in " ".join(memory_output["boundaries"])
    assert "do not by themselves apply" in " ".join(memory_output["boundaries"])
    skipped_reasons = {item["candidate_id"]: item["details"] for item in memory_output["skipped"] if item["reason"] == "not_memory_candidate_eligible"}
    assert "unresolved_reference_ids" in skipped_reasons["xps-param-unregistered-ref-001"]

    proposed_ids = {item["candidate_id"] for item in memory_output["memory_candidates"]}
    assert proposed_ids == {"xps-param-fe2p-spin-001", "xps-param-tougaard-u2-001", "xps-param-fe2p-be-001"}
    memory_candidate_path = Path(memory_output["memory_candidates"][0]["memory_candidate"])
    memory_frontmatter, memory_body = read_markdown_record(memory_candidate_path)
    assert memory_frontmatter["status"] == "draft"
    assert memory_frontmatter["category"] == "method_note"
    assert memory_frontmatter["confidence"] == "low"
    assert suggestion_ref in memory_frontmatter["source_refs"]
    assert record["table_ref"] in memory_frontmatter["source_refs"]
    assert record["source_packet_ref"] in memory_frontmatter["source_refs"]
    assert "raw/xps/example-metadata.yml" in memory_frontmatter["source_refs"]
    assert ref_id in memory_frontmatter["source_refs"]
    assert record["provenance_ref"] in memory_frontmatter["provenance_refs"]
    assert memory_frontmatter["review_refs"] == []
    assert "xps-param-" in memory_body
    assert "target parameter path" in memory_body
    assert "source-backed XPS parameter candidate only" in memory_body
    assert "does not copy values into processing parameters" in memory_body
    be_memory = next(item for item in memory_output["memory_candidates"] if item["candidate_id"] == "xps-param-fe2p-be-001")
    assert be_memory["category"] == "interpretation"
    be_frontmatter, be_body = read_markdown_record(Path(be_memory["memory_candidate"]))
    assert be_frontmatter["category"] == "interpretation"
    assert "Fe(III) oxide binding-energy candidate" in be_body
    assert "expected_binding_energy_eV=710.8" in be_body
    assert "does not copy values into processing parameters" in be_body
    assert "prove chemical state/composition" in be_body
    candidate_index = read_yaml(workspace / "memory" / "candidates" / "index.yml")
    assert memory_frontmatter["memory_candidate_id"] in candidate_index["candidates"]


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

    library = workspace / "project_xps_parameter_library.yml"
    library.write_text(
        """
schema_version: "0.2"
library_id: project-xps-library
reference_seeds:
  ref-xps-seed-fe2p-001:
    citation: "Seeded Fe 2p spin-orbit reference note. Example Journal (2026)."
    title: "Seeded Fe 2p spin-orbit reference note"
    year: 2026
    url: "https://example.org/seeded-xps-fe2p"
    source_type: manual
  ref-xps-seed-tougaard-001:
    citation: "Seeded Tougaard U2 reference note. Example Journal (2026)."
    title: "Seeded Tougaard U2 reference note"
    year: 2026
    url: "https://example.org/seeded-xps-tougaard"
    source_type: manual
  ref-xps-seed-o1s-ignored:
    citation: "Filtered O 1s XPS reference note. Example Journal (2026)."
    title: "Filtered O 1s XPS reference note"
    year: 2026
    url: "https://example.org/seeded-xps-o1s"
    source_type: manual
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
      - ref-xps-seed-fe2p-001
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
      - ref-xps-seed-tougaard-001
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
      - ref-xps-seed-o1s-ignored
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
    assert packet_output["reference_seed_count"] == 2
    packet = read_yaml(Path(packet_output["source_packet"]))
    assert packet["source"] == "ea.xps.parameter_source_packet:v0.2"
    assert packet["source_library_ref"] == library.relative_to(workspace).as_posix()
    assert packet["candidate_count"] == 2
    assert packet["reference_seed_count"] == 2
    assert set(packet["reference_seeds"]) == {"ref-xps-seed-fe2p-001", "ref-xps-seed-tougaard-001"}
    assert "ref-xps-seed-o1s-ignored" not in packet["reference_seeds"]
    assert packet["reference_seeds"]["ref-xps-seed-fe2p-001"]["title"] == "Seeded Fe 2p spin-orbit reference note"
    assert packet["candidates"][0]["parameter_origin"] == "source_suggested"
    assert packet["reference_ids"] == ["ref-xps-seed-fe2p-001", "ref-xps-seed-tougaard-001"]
    assert packet["filters"]["include_candidates"] == ["xps-param-fe2p-spin-001", "xps-param-tougaard-u2-001"]
    assert "register-seeds" in " ".join(packet["next_steps"])
    assert "registration hints only" in " ".join(packet["boundaries"])
    assert "does not perform unconfirmed live network lookup" in " ".join(packet["boundaries"])
    assert "EA may use those sources to prepare candidates" in " ".join(packet["boundaries"])
    assert (workspace / packet["provenance_ref"]).exists()

    packet_ref = Path(packet_output["source_packet"]).relative_to(workspace).as_posix()
    assert (
        main(
            [
                "references",
                "register-seeds",
                str(workspace),
                "--source-packet",
                packet_ref,
                "--project-id",
                project_id,
            ]
        )
        == 0
    )
    seed_output = _json_output(capsys)
    assert seed_output["imported_count"] == 2
    assert {item["reference_id"] for item in seed_output["imported"]} == {"ref-xps-seed-fe2p-001", "ref-xps-seed-tougaard-001"}
    assert seed_output["skipped_count"] == 0
    assert (workspace / "literature" / "references" / "ref-xps-seed-fe2p-001.yml").exists()

    assert main(
        [
            "xps",
            "suggest-parameters",
            str(workspace),
            "--source-file",
            packet_ref,
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
    assert template_packet["candidate_count"] == 3
    assert template_packet["source_packet_id"].startswith("xps_source_packet-")
    assert template_packet["candidates"][0]["center_delta_eV"] is None
    assert template_packet["candidates"][2]["suggestion_type"] == "binding_energy_candidate"
    assert template_packet["candidates"][2]["chemical_state_label"] == "TODO candidate state label"


def test_cli_builds_xps_parameter_source_packet_from_confirmed_literature_manifest(tmp_path: Path, capsys) -> None:
    workspace = tmp_path / "xps-literature-manifest-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "XPS Literature Source Packet",
            "--slug",
            "xps-literature-source-packet",
            "--direction",
            "XPS literature source packet workflow",
            "--material",
            "oxide thin film",
            "--experiment-type",
            "materials XPS characterization",
        ]
    ) == 0
    project = _json_output(capsys)
    project_frontmatter, _ = read_markdown_record(Path(project["project"]))
    project_id = project_frontmatter["project_id"]

    manifest = workspace / "literature" / "confirmed_xps_source_candidates.yml"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        """
schema_version: "0.2"
source: ea.literature.source_candidates:v0.2
method_scope:
  - xps
confirmation_status: user_confirmed
guidance_notes:
  - Charge referencing guidance was reviewed as source context only.
guidance_reference_ids:
  - ref-lit-xps-guidance-001
reference_seeds:
  ref-lit-xps-fe2p-001:
    citation: "Literature Fe 2p XPS reference. Example Journal (2026)."
    title: "Literature Fe 2p XPS reference"
    year: 2026
    url: "https://example.org/lit-xps-fe2p"
    source_type: literature_library
  ref-lit-xps-guidance-001:
    citation: "Literature XPS charge reference guidance. Example Journal (2026)."
    title: "Literature XPS charge reference guidance"
    year: 2026
    url: "https://example.org/lit-xps-guidance"
    source_type: literature_library
  ref-lit-xps-excluded-001:
    citation: "Excluded XPS source. Example Journal (2026)."
    title: "Excluded XPS source"
    year: 2026
    url: "https://example.org/lit-xps-excluded"
    source_type: literature_library
candidates:
  - method: xps
    candidate_id: xps-lit-fe2p-spin-001
    suggestion_type: spin_orbit_constraint
    element: Fe
    core_level: 2p
    constraint_id: xps-lit-fe2p-source-001
    center_delta_eV: 13.4
    area_ratio: 0.5
    fwhm_ratio: 1.0
    parameter_origin: source_suggested
    source_summary: Literature source reports Fe 2p spin-orbit screening values for the reviewed oxide context.
    applicability_notes:
      - Use only after reviewed Fe 2p component IDs, bounds, and background are confirmed.
    reference_ids:
      - ref-lit-xps-fe2p-001
    confidence: low
    caveats:
      - Literature-derived candidate only; not chemical-state proof.
  - method: xps
    include_in_source_packet: false
    candidate_id: xps-lit-excluded-001
    suggestion_type: tougaard_parameter
    reference_ids:
      - ref-lit-xps-excluded-001
  - method: ftir
    candidate_id: ftir-lit-ignored-001
    assignment_label: ignored FTIR candidate
    reference_ids:
      - ref-lit-xps-excluded-001
""".strip()
        + "\n",
        encoding="utf-8",
    )

    assert (
        main(
            [
                "xps",
                "build-source-packet",
                str(workspace),
                "--project-id",
                project_id,
                "--literature-manifest",
                manifest.relative_to(workspace).as_posix(),
                "--output",
                "suggestions/xps/source-packets/literature_xps_packet.yml",
            ]
        )
        == 0
    )
    packet_output = _json_output(capsys)
    packet = read_yaml(Path(packet_output["source_packet"]))
    assert packet_output["status"] == "ready_for_suggest_parameters"
    assert packet_output["candidate_count"] == 1
    assert packet_output["reference_seed_count"] == 2
    assert packet_output["source_library_kind"] == "confirmed_literature_manifest"
    assert packet["source_library_kind"] == "confirmed_literature_manifest"
    assert packet["source_manifest_ref"] == manifest.relative_to(workspace).as_posix()
    assert packet["confirmation_status"] == "user_confirmed"
    assert packet["guidance_reference_ids"] == ["ref-lit-xps-guidance-001"]
    assert packet["candidates"][0]["candidate_id"] == "xps-lit-fe2p-spin-001"
    assert set(packet["reference_seeds"]) == {"ref-lit-xps-fe2p-001", "ref-lit-xps-guidance-001"}
    assert "ref-lit-xps-excluded-001" not in packet["reference_seeds"]
    assert "registration hints only" in " ".join(packet["boundaries"])
    assert "do not register references" in " ".join(packet["boundaries"])
    assert (workspace / packet["provenance_ref"]).exists()

    unconfirmed_manifest = workspace / "literature" / "unconfirmed_xps_source_candidates.yml"
    unconfirmed_manifest.write_text(
        """
schema_version: "0.2"
method_scope: [xps]
candidates:
  - method: xps
    candidate_id: xps-unconfirmed-001
    suggestion_type: tougaard_parameter
    tougaard_C_eV2: 1643.0
    source_summary: Unconfirmed source candidate.
    applicability_notes:
      - Missing manifest confirmation should block this packet.
    reference_ids:
      - ref-lit-xps-fe2p-001
""".strip()
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(XPSProcessingError, match="confirmed_for_source_packet"):
        build_xps_parameter_source_packet(
            workspace,
            project_id=project_id,
            literature_manifest_path=unconfirmed_manifest,
        )


def test_cli_builds_builtin_xps_parameter_source_packet(tmp_path: Path, capsys) -> None:
    workspace = tmp_path / "cli-xps-builtin-source-packet-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "CLI XPS Builtin Source Packet",
            "--slug",
            "cli-xps-builtin-source-packet",
            "--direction",
            "XPS built-in parameter source packet workflow",
            "--material",
            "oxide thin film",
            "--experiment-type",
            "materials XPS characterization",
        ]
    ) == 0
    project = _json_output(capsys)
    project_frontmatter, _ = read_markdown_record(Path(project["project"]))
    project_id = project_frontmatter["project_id"]

    assert main(["xps", "build-source-packet", str(workspace), "--project-id", project_id]) == 0
    packet_output = _json_output(capsys)
    packet = read_yaml(Path(packet_output["source_packet"]))
    assert packet_output["status"] == "ready_for_suggest_parameters"
    assert packet_output["source_library_kind"] == "built_in"
    assert packet_output["source_library_ref"] == "builtin:generic_xps_parameters"
    assert packet_output["candidate_count"] >= 17
    assert packet_output["reference_seed_count"] >= 16
    assert packet["source_library_kind"] == "built_in"
    assert packet["source_library_ref"] == "builtin:generic_xps_parameters"
    assert "builtin-xps-charge-reference-guide-2020" in packet["guidance_reference_ids"]
    assert "builtin-xps-charge-reference-guide-2020" in packet["reference_seeds"]
    assert "builtin-xps-thermo-ti" in packet["reference_seeds"]
    assert "builtin-xps-thermo-mo" in packet["reference_seeds"]
    assert "builtin-xps-thermo-s" in packet["reference_seeds"]
    assert "builtin-xps-thermo-c" in packet["reference_seeds"]
    assert "silently apply adventitious-carbon" in " ".join(packet["guidance_notes"])
    candidates = {candidate["candidate_id"]: candidate for candidate in packet["candidates"]}
    assert "xps-builtin-fe2p-spin-orbit-metal-screening" in candidates
    assert "xps-builtin-tougaard-u2-typical-background-screening" in candidates
    assert "xps-builtin-ti2p-oxide-spin-orbit-screening" in candidates
    assert "xps-builtin-ni2p-spin-orbit-metal-screening" in candidates
    assert "xps-builtin-co2p-spin-orbit-metal-screening" in candidates
    assert "xps-builtin-zn2p-spin-orbit-screening" in candidates
    assert "xps-builtin-mo3d-spin-orbit-screening" in candidates
    assert "xps-builtin-w4f-spin-orbit-screening" in candidates
    assert "xps-builtin-s2p-spin-orbit-generic-screening" in candidates
    assert "xps-builtin-p2p-spin-orbit-generic-screening" in candidates
    assert "xps-builtin-c1s-adventitious-cc-binding-energy-candidate" in candidates
    assert "xps-builtin-c1s-c-o-c-binding-energy-candidate" in candidates
    assert "xps-builtin-c1s-o-c-o-binding-energy-candidate" in candidates
    assert "xps-builtin-si2p-elemental-binding-energy-candidate" in candidates
    assert "xps-builtin-si2p-sio2-binding-energy-candidate" in candidates
    assert candidates["xps-builtin-mo3d-spin-orbit-screening"]["area_ratio"] == 0.6667
    assert candidates["xps-builtin-w4f-spin-orbit-screening"]["area_ratio"] == 0.75
    assert candidates["xps-builtin-s2p-spin-orbit-generic-screening"]["center_delta_eV"] == 1.16
    assert "not a sulfide/sulfate/elemental sulfur assignment" in " ".join(candidates["xps-builtin-s2p-spin-orbit-generic-screening"]["caveats"])
    assert candidates["xps-builtin-c1s-adventitious-cc-binding-energy-candidate"]["suggestion_type"] == "binding_energy_candidate"
    assert candidates["xps-builtin-c1s-adventitious-cc-binding-energy-candidate"]["expected_binding_energy_eV"] == 284.8
    assert candidates["xps-builtin-c1s-adventitious-cc-binding-energy-candidate"]["binding_energy_window_eV"] == [284.6, 285.0]
    assert "not always valid" in candidates["xps-builtin-c1s-adventitious-cc-binding-energy-candidate"]["calibration_reference"]
    assert candidates["xps-builtin-si2p-sio2-binding-energy-candidate"]["expected_binding_energy_eV"] == 103.5
    assert "builtin-xps-thermo-c" in candidates["xps-builtin-c1s-c-o-c-binding-energy-candidate"]["reference_ids"]
    assert "built-in or local reference_seeds" in " ".join(packet["next_steps"])
    assert "registration hints only" in " ".join(packet["boundaries"])
    assert "does not perform unconfirmed live network lookup" in " ".join(packet["boundaries"])
    assert (workspace / packet["provenance_ref"]).exists()

    packet_ref = Path(packet_output["source_packet"]).relative_to(workspace).as_posix()
    assert main(["xps", "suggest-parameters", str(workspace), "--source-file", packet_ref, "--project-id", project_id]) == 0
    unresolved_output = _json_output(capsys)
    assert unresolved_output["status"] == "needs_reference_registration"
    assert unresolved_output["needs_reference_registration_count"] == packet_output["candidate_count"]

    assert (
        main(
            [
                "references",
                "register-seeds",
                str(workspace),
                "--source-packet",
                packet_ref,
                "--project-id",
                project_id,
            ]
        )
        == 0
    )
    seed_output = _json_output(capsys)
    assert seed_output["imported_count"] == packet_output["reference_seed_count"]
    assert {item["reference_id"] for item in seed_output["imported"]} >= {
        "builtin-xps-charge-reference-guide-2020",
        "builtin-xps-background-guide-2021",
        "builtin-xps-thermo-c",
        "builtin-xps-thermo-fe",
        "builtin-xps-thermo-ti",
        "builtin-xps-thermo-mo",
        "builtin-xps-thermo-s",
    }

    assert main(["xps", "suggest-parameters", str(workspace), "--source-file", packet_ref, "--project-id", project_id]) == 0
    suggestion_output = _json_output(capsys)
    assert suggestion_output["status"] == "ready_for_user_review"
    assert suggestion_output["ready_for_user_review_count"] == packet_output["candidate_count"]
    suggestion_record = read_yaml(Path(suggestion_output["record"]))
    ready_candidates = {candidate["candidate_id"]: candidate for candidate in suggestion_record["candidates"]}
    assert ready_candidates["xps-builtin-si2p-sio2-binding-energy-candidate"]["target_parameter_path"] == "interpretation.binding_energy_candidates"
    assert ready_candidates["xps-builtin-si2p-sio2-binding-energy-candidate"]["status"] == "ready_for_user_review"

    assert (
        main(
            [
                "xps",
                "build-source-packet",
                str(workspace),
                "--project-id",
                project_id,
                "--builtin-library",
                "generic_xps_parameters",
                "--include-candidate",
                "xps-builtin-si2p-spin-orbit-elemental-screening",
                "--element",
                "Si",
                "--core-level",
                "2p",
            ]
        )
        == 0
    )
    filtered_output = _json_output(capsys)
    filtered_packet = read_yaml(Path(filtered_output["source_packet"]))
    assert filtered_output["candidate_count"] == 1
    assert filtered_packet["candidates"][0]["candidate_id"] == "xps-builtin-si2p-spin-orbit-elemental-screening"
    assert filtered_packet["filters"]["elements"] == ["si"]
    assert filtered_packet["filters"]["core_levels"] == ["2p"]

    assert (
        main(
            [
                "xps",
                "build-source-packet",
                str(workspace),
                "--project-id",
                project_id,
                "--builtin-library",
                "generic_xps_parameters",
                "--element",
                "S",
                "--core-level",
                "2p",
            ]
        )
        == 0
    )
    sulfur_filtered_output = _json_output(capsys)
    sulfur_filtered_packet = read_yaml(Path(sulfur_filtered_output["source_packet"]))
    assert sulfur_filtered_output["candidate_count"] == 1
    assert sulfur_filtered_packet["candidates"][0]["candidate_id"] == "xps-builtin-s2p-spin-orbit-generic-screening"
    assert set(sulfur_filtered_packet["reference_ids"]) == {
        "builtin-xps-handbook-1995",
        "builtin-xps-nist-srd20",
        "builtin-xps-thermo-s",
        "builtin-xps-charge-reference-guide-2020",
    }

    assert (
        main(
            [
                "xps",
                "build-source-packet",
                str(workspace),
                "--project-id",
                project_id,
                "--builtin-library",
                "generic_xps_parameters",
                "--suggestion-type",
                "binding_energy_candidate",
            ]
        )
        == 0
    )
    be_filtered_output = _json_output(capsys)
    be_filtered_packet = read_yaml(Path(be_filtered_output["source_packet"]))
    assert be_filtered_output["candidate_count"] == 5
    assert {candidate["suggestion_type"] for candidate in be_filtered_packet["candidates"]} == {"binding_energy_candidate"}
    assert set(be_filtered_packet["reference_ids"]) == {
        "builtin-xps-charge-reference-guide-2020",
        "builtin-xps-thermo-c",
        "builtin-xps-thermo-si",
    }


def test_cli_builds_oxide_o1s_builtin_source_packet(tmp_path: Path, capsys) -> None:
    workspace = tmp_path / "cli-xps-oxide-o1s-source-packet-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "CLI XPS Oxide O1s Source Packet Workflow",
            "--slug",
            "cli-xps-oxide-o1s-source-packet",
            "--direction",
            "XPS O 1s oxide candidate workflow",
            "--material",
            "air-exposed oxide thin film",
            "--experiment-type",
            "materials XPS characterization",
        ]
    ) == 0
    project = _json_output(capsys)
    project_frontmatter, _ = read_markdown_record(Path(project["project"]))
    project_id = project_frontmatter["project_id"]

    assert (
        main(
            [
                "xps",
                "build-source-packet",
                str(workspace),
                "--project-id",
                project_id,
                "--builtin-library",
                "oxide_o1s_binding_energy",
                "--suggestion-type",
                "binding_energy_candidate",
            ]
        )
        == 0
    )
    packet_output = _json_output(capsys)
    packet = read_yaml(Path(packet_output["source_packet"]))
    assert packet_output["status"] == "ready_for_suggest_parameters"
    assert packet_output["source_library_ref"] == "builtin:oxide_o1s_binding_energy"
    assert packet_output["candidate_count"] == 4
    assert packet_output["reference_seed_count"] == 5
    assert "builtin-xps-o1s-metal-oxide-insight-2025" in packet["guidance_reference_ids"]
    assert "builtin-xps-o1s-oxygen-vacancy-critical-2025" in packet["guidance_reference_ids"]
    assert set(packet["reference_seeds"]) == {
        "builtin-xps-cardiff-o1s-reference",
        "builtin-xps-charge-reference-guide-2020",
        "builtin-xps-o1s-metal-oxide-insight-2025",
        "builtin-xps-o1s-oxygen-vacancy-critical-2025",
        "builtin-xps-thermo-o",
    }
    assert "oxygen vacancies" in " ".join(packet["guidance_notes"])
    candidates = {candidate["candidate_id"]: candidate for candidate in packet["candidates"]}
    lattice = candidates["xps-builtin-o1s-lattice-oxide-binding-energy-candidate"]
    assert lattice["expected_binding_energy_eV"] == 529.8
    assert lattice["binding_energy_window_eV"] == [529.0, 531.0]
    assert lattice["confidence"] == "medium"
    assert "stoichiometry" in " ".join(lattice["caveats"])
    hydroxyl = candidates["xps-builtin-o1s-hydroxyl-adsorbed-oxygen-binding-energy-candidate"]
    assert hydroxyl["binding_energy_window_eV"] == [531.0, 532.2]
    assert "Not an oxygen-vacancy proof" in " ".join(hydroxyl["caveats"])
    carbonate = candidates["xps-builtin-o1s-carbonate-carbonyl-binding-energy-candidate"]
    assert "289-290 eV" in carbonate["calibration_reference"]
    high_be = candidates["xps-builtin-o1s-silica-organic-co-binding-energy-candidate"]
    assert high_be["expected_binding_energy_eV"] == 532.9
    assert "SiO2" in high_be["source_summary"]

    packet_ref = Path(packet_output["source_packet"]).relative_to(workspace).as_posix()
    assert main(["xps", "suggest-parameters", str(workspace), "--source-file", packet_ref, "--project-id", project_id]) == 0
    unresolved_output = _json_output(capsys)
    assert unresolved_output["status"] == "needs_reference_registration"
    assert unresolved_output["needs_reference_registration_count"] == 4

    assert (
        main(
            [
                "references",
                "register-seeds",
                str(workspace),
                "--source-packet",
                packet_ref,
                "--project-id",
                project_id,
            ]
        )
        == 0
    )
    seed_output = _json_output(capsys)
    assert seed_output["imported_count"] == packet_output["reference_seed_count"]

    assert main(["xps", "suggest-parameters", str(workspace), "--source-file", packet_ref, "--project-id", project_id]) == 0
    suggestion_output = _json_output(capsys)
    assert suggestion_output["status"] == "ready_for_user_review"
    assert suggestion_output["ready_for_user_review_count"] == 4
    suggestion_record = read_yaml(Path(suggestion_output["record"]))
    ready_candidates = {candidate["candidate_id"]: candidate for candidate in suggestion_record["candidates"]}
    assert ready_candidates["xps-builtin-o1s-lattice-oxide-binding-energy-candidate"]["target_parameter_path"] == (
        "interpretation.binding_energy_candidates"
    )
    assert ready_candidates["xps-builtin-o1s-hydroxyl-adsorbed-oxygen-binding-energy-candidate"]["auto_applied"] is False
    assert "oxygen vacancies" in " ".join(suggestion_record["candidates"][1]["overlap_notes"]).lower()


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
    assert "without review/provenance" in region_record["boundary"]
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
    assert "不在缺少审核记录时共享 charge correction" in report_body
    assert "不静默对齐 survey/core-level" in report_body


def test_xps_docs_and_skill_references_are_discoverable() -> None:
    root = Path.cwd()

    readme = (root / "README.md").read_text(encoding="utf-8")
    skill = (root / "skills" / "ea-v0-2" / "SKILL.md").read_text(encoding="utf-8")
    xps_reference = root / "skills" / "ea-v0-2" / "references" / "xps-workflow.md"
    registry = read_yaml(root / "skill-registry" / "index.yml")

    assert "ea xps inspect" in readme
    assert "ea xps process" in skill
    assert "ea xps build-source-packet" in skill
    assert "ea xps suggest-parameters" in skill
    assert "ea xps propose-memory" in skill
    assert "--builtin-library" in skill
    assert "generic_xps_parameters" in skill
    assert "oxide_o1s_binding_energy" in skill
    assert "--parameter-suggestion" in skill
    assert "register-seeds" in skill
    assert "references/xps-workflow.md" in skill
    assert xps_reference.exists()
    xps_reference_text = xps_reference.read_text(encoding="utf-8")
    assert "calibration_review_ref" in xps_reference_text
    assert "component_quantification" in xps_reference_text
    assert "component_fit" in xps_reference_text
    assert "spin_orbit_constraints" in xps_reference_text
    assert "build-source-packet" in xps_reference_text
    assert "xps_parameter_source_packet" in xps_reference_text
    assert "reference_seeds" in xps_reference_text
    assert "guidance_reference_ids" in xps_reference_text
    assert "generic_xps_parameters" in xps_reference_text
    assert "oxide_o1s_binding_energy" in xps_reference_text
    assert "register-seeds" in xps_reference_text
    assert "suggest-parameters" in xps_reference_text
    assert "propose-memory" in xps_reference_text
    assert "draft method-note or interpretation memory candidates" in xps_reference_text
    assert "xps_parameter_suggestions" in xps_reference_text
    assert "--parameter-suggestion" in xps_reference_text
    assert "source-backed parameter suggestion section" in xps_reference_text
    assert "region_records" in xps_reference_text
    assert "background_model" in xps_reference_text
    assert "background_subtraction" in xps_reference_text
    assert "reviewed_shirley_background_subtraction" in xps_reference_text
    assert "reviewed_tougaard_u2_background_subtraction" in xps_reference_text
    assert "screening-only" in xps_reference_text
    assert "no unconfirmed live lookup" in xps_reference_text
    assert "not a ban on EA preparing source-backed candidates" in xps_reference_text
    assert "does not require every signed energy separation, area ratio, FWHM ratio" in xps_reference_text
    assert "without reducing EA to a user-provided-only calculator" in xps_reference_text
    assert "binding_energy_candidate" in xps_reference_text
    assert "expected BE center or BE window" in xps_reference_text
    assert "calibration reference" in xps_reference_text
    assert "charge-reference assumption" in xps_reference_text
    assert "C-C/C-H, C-O-C, O-C=O, elemental Si, and SiO2" in xps_reference_text
    assert "lattice oxide, hydroxyl/adsorbed-oxygen-like, carbonate/carbonyl-like, and silica/organic C-O" in xps_reference_text
    assert "--suggestion-type binding_energy_candidate" in xps_reference_text
    assert "examples/public-xps-be-project" in xps_reference_text
    xps_record = next(item for item in registry["skills"] if item["id"] == "ea.xps-analysis")
    assert "component_quantification_screening" in xps_record["notes"]
    assert "component_fit" in xps_record["notes"]
    assert "parameter_source_packets" in xps_record["notes"]
    assert "reference_seeds" in xps_record["notes"]
    assert "guidance_reference_ids" in xps_record["notes"]
    assert "generic_xps_parameters" in xps_record["notes"]
    assert "oxide_o1s_binding_energy" in xps_record["notes"]
    assert "register-seeds" in xps_record["notes"]
    assert "parameter_suggestions" in xps_record["notes"]
    assert "propose-memory" in xps_record["notes"]
    assert "draft memory_candidate proposals" in xps_record["notes"]
    assert "--parameter-suggestion" in xps_record["notes"]
    assert "spin_orbit_constraints" in xps_record["notes"]
    assert "region_records" in xps_record["notes"]
    assert "background_model_records" in xps_record["notes"]
    assert "background_subtraction" in xps_record["notes"]
    assert "reviewed_shirley_background_subtraction" in xps_record["notes"]
    assert "reviewed_tougaard_u2_background_subtraction" in xps_record["notes"]
    assert "spin-orbit energy separations, area ratios, FWHM ratios" in xps_record["notes"]
    assert "binding_energy_candidate" in xps_record["notes"]
    assert "calibration reference" in xps_record["notes"]
    assert "C 1s/Si 2p binding-energy starter candidates" in xps_record["notes"]
    assert "O 1s lattice oxide" in xps_record["notes"]
