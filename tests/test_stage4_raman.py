from pathlib import Path

import pytest

from ea.raman import (
    RamanProcessingError,
    RamanProcessingRequest,
    default_processing_parameters,
    inspect_spectrum_file,
    process_raman_result,
)
from ea.raw_import import import_raw_file
from ea.review import write_review_record
from ea.storage import read_yaml


PUBLIC_RAW = Path("tests/fixtures/public/test-case-001/raw_data")


def test_inspect_public_raman_txt_requires_confirmation() -> None:
    inspection = inspect_spectrum_file(PUBLIC_RAW / "MoS-2(1).txt")

    assert inspection.file_kind == "raman"
    assert inspection.row_count == 649
    assert inspection.columns == ["col_0", "col_1"]
    assert inspection.x_column_candidate == "col_0"
    assert inspection.y_column_candidate == "col_1"
    assert inspection.x_unit == "unknown"
    assert "x_unit_unknown" in inspection.warnings
    assert inspection.requires_user_confirmation is True


def test_inspect_public_pl_txt_is_not_auto_raman() -> None:
    inspection = inspect_spectrum_file(PUBLIC_RAW / "MoS-PL-2(1).txt")

    assert inspection.file_kind == "pl"
    assert inspection.row_count == 8280
    assert inspection.x_unit == "eV"
    assert inspection.metadata["instrument_metadata"]["instrument_model"] == "LabRAM HR Evol"
    assert inspection.requires_user_confirmation is True


def test_confirmed_public_raman_processing_writes_outputs(tmp_path: Path) -> None:
    project = tmp_path / "project"
    raw = import_raw_file(
        project,
        PUBLIC_RAW / "MoS-2(1).txt",
        project_id="project-20260602-mos2",
        sample_refs=["20260516-run1-sub1"],
        imported_at="2026-06-02T15:00:00",
    )
    column_review = write_review_record(
        project,
        target_type="raman_columns",
        target_ref=raw.metadata_path.relative_to(project).as_posix(),
        user_response="可以，保存",
        reviewed_content="x=col_0, y=col_1, unit=cm^-1",
    )
    parameter_review = write_review_record(
        project,
        target_type="raman_parameters",
        target_ref=raw.metadata_path.relative_to(project).as_posix(),
        user_response="可以，保存",
        reviewed_content=str(default_processing_parameters()),
    )
    request = RamanProcessingRequest(
        x_column="col_0",
        y_column="col_1",
        x_unit="cm^-1",
        processing_parameters=default_processing_parameters(),
        column_review_ref=column_review.stem,
        parameter_review_ref=parameter_review.stem,
    )

    metadata_path = process_raman_result(
        project,
        characterization_metadata_path=raw.metadata_path,
        project_id="project-20260602-mos2",
        sample_refs=["20260516-run1-sub1"],
        request=request,
        created_at="2026-06-02T15:10:00",
    )
    metadata = read_yaml(metadata_path)

    assert metadata["status"] in {"success", "warning"}
    assert metadata["x_unit"] == "cm^-1"
    assert metadata["review_refs"] == [column_review.stem, parameter_review.stem]
    assert metadata["provenance_refs"]

    for output in metadata["outputs"].values():
        assert (project / output).exists(), output

    peaks = (project / metadata["outputs"]["peak_table"]).read_text(encoding="utf-8")
    assert "peak_id,position_cm-1,intensity,height,prominence,width,method,notes" in peaks
    assert "scipy_find_peaks" in peaks

    with pytest.raises(
        RamanProcessingError,
        match=r"requires x_unit to be user-confirmed as cm\^-1",
    ):
        process_raman_result(
            project,
            characterization_metadata_path=raw.metadata_path,
            project_id="project-20260602-mos2",
            sample_refs=["20260516-run1-sub1"],
            request=RamanProcessingRequest(
                x_column="col_0",
                y_column="col_1",
                x_unit="unknown",
                processing_parameters=default_processing_parameters(),
                column_review_ref=column_review.stem,
                parameter_review_ref=parameter_review.stem,
            ),
        )


def test_pl_file_is_rejected_by_raman_processing(tmp_path: Path) -> None:
    project = tmp_path / "project"
    raw = import_raw_file(
        project,
        PUBLIC_RAW / "MoS-PL-2(1).txt",
        project_id="project-20260602-mos2",
        characterization_type="pl",
        sample_refs=["20260516-run1-sub1"],
    )
    column_review = write_review_record(
        project,
        target_type="raman_columns",
        target_ref=raw.metadata_path.relative_to(project).as_posix(),
        user_response="可以，保存",
        reviewed_content="x=col_0, y=col_1, unit=cm^-1",
    )
    parameter_review = write_review_record(
        project,
        target_type="raman_parameters",
        target_ref=raw.metadata_path.relative_to(project).as_posix(),
        user_response="可以，保存",
        reviewed_content=str(default_processing_parameters()),
    )
    request = RamanProcessingRequest(
        x_column="col_0",
        y_column="col_1",
        x_unit="cm^-1",
        processing_parameters=default_processing_parameters(),
        column_review_ref=column_review.stem,
        parameter_review_ref=parameter_review.stem,
    )

    with pytest.raises(RamanProcessingError, match="not Raman"):
        process_raman_result(
            project,
            characterization_metadata_path=raw.metadata_path,
            project_id="project-20260602-mos2",
            sample_refs=["20260516-run1-sub1"],
            request=request,
        )


def test_raman_processing_rejects_missing_or_unconfirmed_reviews(tmp_path: Path) -> None:
    project = tmp_path / "project"
    raw = import_raw_file(
        project,
        PUBLIC_RAW / "MoS-2(1).txt",
        project_id="project-20260602-mos2",
    )
    deferred_review = write_review_record(
        project,
        target_type="raman_columns",
        target_ref=raw.metadata_path.relative_to(project).as_posix(),
        user_response="先放着",
        reviewed_content="x=col_0, y=col_1",
    )
    with pytest.raises(RuntimeError, match="not user_confirmed"):
        process_raman_result(
            project,
            characterization_metadata_path=raw.metadata_path,
            project_id="project-20260602-mos2",
            sample_refs=[],
            request=RamanProcessingRequest(
                x_column="col_0",
                y_column="col_1",
                x_unit="cm^-1",
                processing_parameters=default_processing_parameters(),
                column_review_ref=deferred_review.stem,
                parameter_review_ref="missing-review",
            ),
        )
