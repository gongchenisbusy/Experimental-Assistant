from pathlib import Path

import pandas as pd

from ea.projects import initialize_project
from ea.raman import (
    RamanProcessingRequest,
    default_processing_parameters,
    process_raman_result,
)
from ea.raw_import import import_raw_file
from ea.reports import generate_raman_report
from ea.review import write_review_record
from ea.storage import read_markdown_record, read_yaml


PUBLIC_RAW = Path("tests/fixtures/public/test-case-001/raw_data")


def _confirmed_request(
    project: Path, raw_metadata_path: Path, parameters: dict
) -> RamanProcessingRequest:
    column_review = write_review_record(
        project,
        target_type="raman_columns",
        target_ref=raw_metadata_path.relative_to(project).as_posix(),
        user_response="可以，保存",
        reviewed_content="x=col_0, y=col_1, unit=cm^-1",
    )
    parameter_review = write_review_record(
        project,
        target_type="raman_parameters",
        target_ref=raw_metadata_path.relative_to(project).as_posix(),
        user_response="可以，保存",
        reviewed_content=str(parameters),
    )
    return RamanProcessingRequest(
        x_column="col_0",
        y_column="col_1",
        x_unit="cm^-1",
        processing_parameters=parameters,
        column_review_ref=column_review.stem,
        parameter_review_ref=parameter_review.stem,
    )


def test_raman_baseline_and_smoothing_are_recorded(tmp_path: Path) -> None:
    project = tmp_path / "project"
    raw = import_raw_file(
        project,
        PUBLIC_RAW / "MoS-2(1).txt",
        project_id="project-20260602-mos2",
        sample_refs=["sample-001"],
    )
    parameters = default_processing_parameters()
    parameters["baseline_correction"].update(
        {"enabled": True, "lambda": 10000.0, "p": 0.01, "niter": 5}
    )
    parameters["smoothing"].update(
        {"enabled": True, "window_length": 11, "polyorder": 2}
    )

    result_path = process_raman_result(
        project,
        characterization_metadata_path=raw.metadata_path,
        project_id="project-20260602-mos2",
        sample_refs=["sample-001"],
        request=_confirmed_request(project, raw.metadata_path, parameters),
        created_at="2026-06-30T10:00:00",
    )

    metadata = read_yaml(result_path)
    processed = pd.read_csv(project / metadata["outputs"]["processed_csv"])
    assert {
        "baseline",
        "baseline_corrected_intensity",
        "smoothed_intensity",
        "spike_candidate",
        "processed_intensity",
    }.issubset(processed.columns)
    assert processed["baseline"].notna().all()
    assert processed["smoothed_intensity"].notna().all()

    warning_codes = {warning["code"] for warning in metadata["warnings"]}
    assert "baseline_correction_applied" in warning_codes
    assert "smoothing_applied" in warning_codes
    assert "normalization_applied" in warning_codes
    assert "baseline_not_corrected" not in warning_codes


def test_raman_spike_candidates_are_traceable(tmp_path: Path) -> None:
    project = tmp_path / "project"
    source = tmp_path / "synthetic_spike_raman.txt"
    rows = [
        (100, 10.0),
        (110, 10.2),
        (120, 10.1),
        (130, 10.0),
        (140, 95.0),
        (150, 10.1),
        (160, 10.0),
        (170, 10.2),
        (180, 10.1),
    ]
    source.write_text("\n".join(f"{x}\t{y}" for x, y in rows), encoding="utf-8")
    raw = import_raw_file(
        project,
        source,
        project_id="project-20260630-spike",
        sample_refs=["sample-spike"],
    )
    parameters = default_processing_parameters()
    parameters["normalization"]["enabled"] = False
    parameters["spike_detection"].update(
        {"enabled": True, "window": 5, "mad_threshold": 5.0}
    )

    result_path = process_raman_result(
        project,
        characterization_metadata_path=raw.metadata_path,
        project_id="project-20260630-spike",
        sample_refs=["sample-spike"],
        request=_confirmed_request(project, raw.metadata_path, parameters),
        created_at="2026-06-30T10:10:00",
    )

    metadata = read_yaml(result_path)
    processed = pd.read_csv(project / metadata["outputs"]["processed_csv"])
    spike_row = processed.loc[processed["raw_intensity"].idxmax()]
    assert bool(spike_row["spike_candidate"]) is True
    assert int(processed["spike_candidate"].sum()) >= 1

    warning_codes = {warning["code"] for warning in metadata["warnings"]}
    assert "spike_detection_applied" in warning_codes
    assert "spike_candidates_detected" in warning_codes


def test_raman_peak_fitting_assignment_and_report_interpretation(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    outputs = initialize_project(
        project,
        project_name="MoS2 peak fitting",
        project_slug="mos2-peak-fitting",
        research_direction="Raman peak fitting workflow",
        material_system="MoS2",
        experiment_type="CVD and Raman",
        created_at="2026-06-30T13:00:00",
    )
    project_frontmatter, _ = read_markdown_record(outputs["project"])
    project_id = project_frontmatter["project_id"]
    raw = import_raw_file(
        project,
        PUBLIC_RAW / "MoS-2(1).txt",
        project_id=project_id,
        sample_refs=["sample-fit-001"],
        experiment_refs=["exp-fit-001"],
        imported_at="2026-06-30T13:05:00",
    )

    result_path = process_raman_result(
        project,
        characterization_metadata_path=raw.metadata_path,
        project_id=project_id,
        sample_refs=["sample-fit-001"],
        request=_confirmed_request(
            project, raw.metadata_path, default_processing_parameters()
        ),
        created_at="2026-06-30T13:10:00",
    )
    metadata = read_yaml(result_path)
    peaks = pd.read_csv(project / metadata["outputs"]["peak_table"])

    assert {
        "fit_center_cm-1",
        "fit_center_standard_error_cm-1",
        "fit_fwhm_cm-1",
        "fit_r2",
        "assignment",
        "assignment_confidence",
    }.issubset(peaks.columns)
    assert (peaks["fit_status"] == "success").any()
    assert metadata["effective_processing_parameters"]["peak_detection"][
        "resolved_prominence"
    ] > 0
    assert metadata["effective_processing_parameters"]["peak_detection"][
        "resolved_distance_points"
    ] >= 1
    assert "peak_analysis" in metadata
    assert metadata["peak_analysis"]["peak_count"] >= 2
    assert (
        metadata["peak_analysis"]["assignment_source"]
        == "ea.materials.builtin:mos2:raman:v0.2"
    )
    assigned_labels = {
        feature["label"] for feature in metadata["peak_analysis"]["assigned_features"]
    }
    assert "MoS2 E2g-like" in assigned_labels
    assert "MoS2 A1g-like" in assigned_labels
    assert "assignment_source" in peaks.columns
    assert 15.0 <= metadata["peak_analysis"]["mode_separation_cm-1"] <= 25.0
    assert metadata["peak_analysis"]["mode_separation_standard_error_cm-1"] > 0
    quality_gate = metadata["peak_analysis"]["fit_quality_gate"]
    assert quality_gate["minimum_r2_for_assignment"] == 0.8
    assigned_peak_ids = {
        feature["peak_id"] for feature in metadata["peak_analysis"]["assigned_features"]
    }
    assert assigned_peak_ids <= set(quality_gate["eligible_peak_ids"])
    assert all(
        float(peaks.loc[peaks["peak_id"] == peak_id, "fit_r2"].iloc[0]) >= 0.8
        for peak_id in assigned_peak_ids
    )

    report_path = generate_raman_report(
        project,
        project_id=project_id,
        raman_metadata_path=result_path,
        related_experiments=["exp-fit-001"],
        related_samples=["sample-fit-001"],
        created_at="2026-06-30T13:20:00",
    )
    _, body = read_markdown_record(report_path)

    assert "## 拟合峰参数" in body
    assert "## 可能结论与可信度" in body
    assert "MoS₂-like Raman 峰对" in body
    assert "Detected E2g-like and A1g-like" not in body
    assert "可信度：`中`" in body
    assert "拟合协方差标准误" in body
    assert "模态间距：`" in body and " ± " in body
    assert "不包含波数校准、预处理、仪器或重复测量不确定度" in body
    assert "（标准误不适用）" in body
    assert "confidence:" not in body
