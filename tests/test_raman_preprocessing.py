from pathlib import Path

import pandas as pd

from ea.raman import RamanProcessingRequest, default_processing_parameters, process_raman_result
from ea.raw_import import import_raw_file
from ea.review import write_review_record
from ea.storage import read_yaml


PUBLIC_RAW = Path("tests/fixtures/public/test-case-001/raw_data")


def _confirmed_request(project: Path, raw_metadata_path: Path, parameters: dict) -> RamanProcessingRequest:
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
    parameters["baseline_correction"].update({"enabled": True, "lambda": 10000.0, "p": 0.01, "niter": 5})
    parameters["smoothing"].update({"enabled": True, "window_length": 11, "polyorder": 2})

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
    assert {"baseline", "baseline_corrected_intensity", "smoothed_intensity", "spike_candidate", "processed_intensity"}.issubset(
        processed.columns
    )
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
    parameters["spike_detection"].update({"enabled": True, "window": 5, "mad_threshold": 5.0})

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
