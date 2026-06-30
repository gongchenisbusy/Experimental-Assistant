from __future__ import annotations

import json
from pathlib import Path

from ea.cli import main
from ea.evaluation import run_project_evaluation
from ea.projects import initialize_project
from ea.raman import RamanProcessingRequest, default_processing_parameters, process_raman_result
from ea.raw_import import import_raw_file
from ea.reports import generate_raman_report
from ea.review import write_review_record
from ea.storage import read_markdown_record, read_yaml, write_yaml


FIXTURE_RAW = Path("tests/fixtures/public/test-case-001/raw_data/MoS-2(1).txt").resolve()


def _build_evaluable_project(root: Path) -> dict[str, str]:
    outputs = initialize_project(
        root,
        project_name="Evaluation Raman Project",
        project_slug="evaluation-raman-project",
        research_direction="Raman evaluation workflow",
        material_system="MoS2",
        experiment_type="CVD and Raman",
        created_at="2026-06-30T13:00:00",
    )
    project_frontmatter, _ = read_markdown_record(outputs["project"])
    project_id = project_frontmatter["project_id"]
    raw = import_raw_file(
        root,
        FIXTURE_RAW,
        project_id=project_id,
        sample_refs=["sample-eval-001"],
        experiment_refs=["exp-eval-001"],
        imported_at="2026-06-30T13:05:00",
    )
    column_review = write_review_record(
        root,
        target_type="raman_columns",
        target_ref=raw.metadata_path.relative_to(root).as_posix(),
        user_response="可以，保存",
        reviewed_content="x=col_0, y=col_1, unit=cm^-1",
    )
    parameter_review = write_review_record(
        root,
        target_type="raman_parameters",
        target_ref=raw.metadata_path.relative_to(root).as_posix(),
        user_response="可以，保存",
        reviewed_content=json.dumps(default_processing_parameters(), ensure_ascii=False),
    )
    metadata_path = process_raman_result(
        root,
        characterization_metadata_path=raw.metadata_path,
        project_id=project_id,
        sample_refs=["sample-eval-001"],
        request=RamanProcessingRequest(
            x_column="col_0",
            y_column="col_1",
            x_unit="cm^-1",
            processing_parameters=default_processing_parameters(),
            column_review_ref=column_review.stem,
            parameter_review_ref=parameter_review.stem,
        ),
        created_at="2026-06-30T13:10:00",
    )
    report_path = generate_raman_report(
        root,
        project_id=project_id,
        raman_metadata_path=metadata_path,
        related_experiments=["exp-eval-001"],
        related_samples=["sample-eval-001"],
        created_at="2026-06-30T13:15:00",
    )
    metadata = read_yaml(metadata_path)
    return {
        "project_id": project_id,
        "metadata": metadata_path.relative_to(root).as_posix(),
        "report": report_path.relative_to(root).as_posix(),
        "figure_id": metadata["figure_id"],
    }


def test_project_evaluation_passes_complete_project_and_writes_report(tmp_path: Path) -> None:
    _build_evaluable_project(tmp_path)

    result = run_project_evaluation(tmp_path, created_at="2026-06-30T13:30:00")

    assert result["status"] == "pass"
    assert result["evaluation_id"] == "eval-20260630-001"
    assert result["error_count"] == 0
    assert result["warning_count"] == 0
    assert result["figures"]["analysis_figure_count"] == 1
    assert result["figures"]["source_data_ref_count"] == 2
    assert result["reports"]["report_count"] == 1
    assert Path(result["report_path"]).exists()
    saved = read_yaml(Path(result["report_path"]))
    assert saved["evaluation_id"] == "eval-20260630-001"
    assert saved["scope"]["live_literature_search"] is False


def test_project_evaluation_warns_when_analysis_figure_lacks_source_refs(tmp_path: Path) -> None:
    built = _build_evaluable_project(tmp_path)
    index_path = tmp_path / "figures" / "index.yml"
    index = read_yaml(index_path)
    index["figures"][built["figure_id"]]["source_data_refs"] = []
    write_yaml(index_path, index)

    result = run_project_evaluation(tmp_path, write_report=False, created_at="2026-06-30T13:30:00")
    codes = {finding["code"] for finding in result["findings"]}

    assert result["status"] == "warning"
    assert "figure_source_data_refs_missing" in codes
    assert result["report_path"] is None
    assert not list((tmp_path / "evaluation").glob("*.yml"))


def test_project_evaluation_fails_when_analysis_figure_source_ref_is_missing(tmp_path: Path) -> None:
    built = _build_evaluable_project(tmp_path)
    index_path = tmp_path / "figures" / "index.yml"
    index = read_yaml(index_path)
    index["figures"][built["figure_id"]]["source_data_refs"] = ["processed/missing-source.csv"]
    write_yaml(index_path, index)

    result = run_project_evaluation(tmp_path, write_report=False, created_at="2026-06-30T13:30:00")
    codes = {finding["code"] for finding in result["findings"]}

    assert result["status"] == "fail"
    assert "figure_source_data_ref_missing" in codes


def test_cli_eval_project_no_write_returns_json(tmp_path: Path, capsys) -> None:
    _build_evaluable_project(tmp_path)

    return_code = main(["eval", "project", str(tmp_path), "--no-write"])
    output = json.loads(capsys.readouterr().out)

    assert return_code == 0
    assert output["status"] == "pass"
    assert output["suite"] == "public_release"
    assert output["report_path"] is None
    assert not list((tmp_path / "evaluation").glob("*.yml"))
