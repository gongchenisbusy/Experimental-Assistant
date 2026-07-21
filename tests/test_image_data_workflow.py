import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pytest

from ea.cli import main
from ea.healthcheck import run_healthcheck
from ea.image_data import create_image_analysis_record, generate_image_analysis_report
from ea.projects import initialize_project
from ea.raw_import import import_raw_file
from ea.review import write_review_record
from ea.review.state import ReviewRequiredErrorForRef
from ea.skills import validate_skill_manifest
from ea.storage import read_markdown_record, read_yaml


def _write_test_image(path: Path) -> None:
    image = np.zeros((12, 12, 3), dtype=float)
    image[2:10, 3:9, 1] = 0.8
    image[5:7, 5:7, 0] = 1.0
    plt.imsave(path, image)


def _project(tmp_path: Path) -> str:
    outputs = initialize_project(
        tmp_path,
        project_name="Image data demo",
        project_slug="image-data-demo",
        research_direction="SEM morphology workflow",
        material_system="MoS2",
        experiment_type="CVD and SEM",
        created_at="2026-06-30T09:00:00",
    )
    frontmatter, _ = read_markdown_record(outputs["project"])
    return frontmatter["project_id"]


def test_image_data_workflow_generates_traceable_report(tmp_path: Path) -> None:
    project_id = _project(tmp_path)
    source = tmp_path / "sem_image.png"
    _write_test_image(source)
    raw = import_raw_file(
        tmp_path,
        source,
        project_id=project_id,
        characterization_type="sem",
        sample_refs=["sample-img-001"],
        experiment_refs=["exp-img-001"],
        imported_at="2026-06-30T09:05:00",
    )
    review = write_review_record(
        tmp_path,
        target_type="image_description",
        target_ref=raw.metadata_path.relative_to(tmp_path).as_posix(),
        user_response="可以，保存",
        reviewed_content="SEM image shows a mostly continuous flake with brighter central contrast.",
        reviewed_at="2026-06-30T09:06:00",
    )

    result_path = create_image_analysis_record(
        tmp_path,
        characterization_metadata_path=raw.metadata_path,
        project_id=project_id,
        method="sem",
        user_description="SEM image shows a mostly continuous flake with brighter central contrast.",
        description_review_ref=review.stem,
        sample_refs=["sample-img-001"],
        ea_observations=["User description is sufficient for a low-confidence morphology note."],
        interpretation="The observed contrast may indicate local thickness or topography variation; confidence remains limited without scale metadata.",
        confidence="low",
        scale_bar="2 um",
        created_at="2026-06-30T09:10:00",
    )
    result = read_yaml(result_path)

    assert result["result_id"] == "res-image-data-demo-sem-20260630-001"
    assert result["figure_id"] == "fig-image-data-demo-sem-20260630-001"
    assert result["review_refs"] == [review.stem]
    assert (tmp_path / result["outputs"]["figure"]).exists()
    assert (tmp_path / result["outputs"]["raw_image"]).exists()

    report_path = generate_image_analysis_report(
        tmp_path,
        project_id=project_id,
        image_metadata_path=result_path,
        related_experiments=["exp-img-001"],
        related_samples=["sample-img-001"],
        created_at="2026-06-30T09:20:00",
    )
    frontmatter, body = read_markdown_record(report_path)
    figures_index = read_yaml(tmp_path / "figures" / "index.yml")
    reports_index = read_yaml(tmp_path / "reports" / "index.yml")

    assert frontmatter["report_type"] == "image_analysis"
    assert frontmatter["related_results"] == [result["result_id"]]
    assert "![fig-image-data-demo-sem-20260630-001]" in body
    assert "confidence: `low` / `低`" in body
    assert "原图链接" in body
    assert figures_index["figures"][result["figure_id"]]["report_id"] == frontmatter["report_id"]
    assert reports_index["reports"][frontmatter["report_id"]]["result_ids"] == [result["result_id"]]
    assert run_healthcheck(tmp_path)["status"] == "pass"


def test_image_data_cli_record_and_report(tmp_path: Path, capsys) -> None:
    project_id = _project(tmp_path)
    source = tmp_path / "tem_image.png"
    _write_test_image(source)
    raw = import_raw_file(
        tmp_path,
        source,
        project_id=project_id,
        characterization_type="tem",
        sample_refs=["sample-cli-img"],
    )
    review = write_review_record(
        tmp_path,
        target_type="image_description",
        target_ref=raw.metadata_path.relative_to(tmp_path).as_posix(),
        user_response="可以，保存",
        reviewed_content="TEM image user note.",
    )

    assert main(
        [
            "image-data",
            "record",
            str(tmp_path),
            "--metadata",
            raw.metadata_path.relative_to(tmp_path).as_posix(),
            "--project-id",
            project_id,
            "--method",
            "tem",
            "--description",
            "TEM image user note.",
            "--description-review-ref",
            review.stem,
            "--sample-ref",
            "sample-cli-img",
            "--confidence",
            "insufficient",
        ]
    ) == 0
    record_output = capsys.readouterr().out
    assert "image_metadata.yml" in record_output
    result_path = next((tmp_path / "processed").glob("sample-cli-img/tem/*/image_metadata.yml"))

    assert main(
        [
            "image-data",
            "report",
            str(tmp_path),
            "--metadata",
            result_path.relative_to(tmp_path).as_posix(),
            "--project-id",
            project_id,
            "--sample-ref",
            "sample-cli-img",
        ]
    ) == 0
    report_output = json.loads(capsys.readouterr().out)
    assert "/reports/rpt-image-data-demo" in Path(report_output["report"]).as_posix()


def test_builtin_image_manifest_is_valid() -> None:
    result = validate_skill_manifest(Path("skill-registry/builtins/image-analysis.yml"))

    assert result.ok is True
    assert result.manifest["id"] == "ea.image-analysis"
    assert "confirm_image_description" in result.manifest["review_gates"]


def test_image_record_rejects_confirmed_review_for_another_raw_record(
    tmp_path: Path,
) -> None:
    project_id = _project(tmp_path)
    source = tmp_path / "sem_image.png"
    _write_test_image(source)
    raw = import_raw_file(
        tmp_path,
        source,
        project_id=project_id,
        characterization_type="sem",
        sample_refs=["sample-img-001"],
    )
    review = write_review_record(
        tmp_path,
        target_type="image_description",
        target_ref="raw/sem/another-characterization/metadata.yml",
        user_response="confirm",
        reviewed_content="SEM image user note.",
        confirm=True,
    )

    with pytest.raises(ReviewRequiredErrorForRef, match="target_ref"):
        create_image_analysis_record(
            tmp_path,
            characterization_metadata_path=raw.metadata_path,
            project_id=project_id,
            method="sem",
            user_description="SEM image user note.",
            description_review_ref=review.stem,
            sample_refs=["sample-img-001"],
        )
