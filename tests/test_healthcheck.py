from __future__ import annotations

import json
from pathlib import Path

from ea.cli import main
from ea.healthcheck import run_healthcheck
from ea.projects import initialize_project
from ea.raman import RamanProcessingRequest, default_processing_parameters, process_raman_result
from ea.raw_import import import_raw_file
from ea.reports import generate_raman_report
from ea.review import write_review_record
from ea.storage import read_markdown_record, read_yaml, write_yaml


FIXTURE_RAW = Path("tests/fixtures/public/test-case-001/raw_data/MoS-2(1).txt").resolve()


def _build_v0_2_raman_project(root: Path) -> dict[str, Path | str]:
    outputs = initialize_project(
        root,
        project_name="MoS2 Healthcheck",
        project_slug="mos2-healthcheck",
        research_direction="Raman audit workflow",
        material_system="MoS2",
        experiment_type="CVD and Raman",
        created_at="2026-06-30T11:00:00",
    )
    project_frontmatter, _ = read_markdown_record(outputs["project"])
    project_id = project_frontmatter["project_id"]
    raw = import_raw_file(
        root,
        FIXTURE_RAW,
        project_id=project_id,
        sample_refs=["sample-001"],
        experiment_refs=["exp-20260630-001"],
        imported_at="2026-06-30T11:05:00",
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
        reviewed_content=str(default_processing_parameters()),
    )
    result_path = process_raman_result(
        root,
        characterization_metadata_path=raw.metadata_path,
        project_id=project_id,
        sample_refs=["sample-001"],
        request=RamanProcessingRequest(
            x_column="col_0",
            y_column="col_1",
            x_unit="cm^-1",
            processing_parameters=default_processing_parameters(),
            column_review_ref=column_review.stem,
            parameter_review_ref=parameter_review.stem,
        ),
        created_at="2026-06-30T11:10:00",
    )
    report_path = generate_raman_report(
        root,
        project_id=project_id,
        raman_metadata_path=result_path,
        related_experiments=["exp-20260630-001"],
        related_samples=["sample-001"],
        created_at="2026-06-30T11:20:00",
    )
    result = read_yaml(result_path)
    return {
        "project_id": project_id,
        "raw_path": raw.project_raw_path or root / "missing",
        "result_path": result_path,
        "report_path": report_path,
        "figure_id": result["figure_id"],
    }


def test_healthcheck_passes_complete_v0_2_raman_project(tmp_path: Path) -> None:
    _build_v0_2_raman_project(tmp_path)

    result = run_healthcheck(tmp_path)

    assert result["status"] == "pass"
    assert result["error_count"] == 0


def test_healthcheck_detects_raw_hash_mismatch(tmp_path: Path) -> None:
    built = _build_v0_2_raman_project(tmp_path)
    raw_path = Path(built["raw_path"])
    raw_path.chmod(0o600)
    raw_path.write_text(raw_path.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")

    result = run_healthcheck(tmp_path)
    codes = {finding["code"] for finding in result["findings"]}

    assert result["status"] == "fail"
    assert "raw_hash_mismatch" in codes


def test_healthcheck_detects_report_figure_backlink_mismatch(tmp_path: Path) -> None:
    built = _build_v0_2_raman_project(tmp_path)
    figures_index = tmp_path / "figures" / "index.yml"
    figures = read_yaml(figures_index)
    figures["figures"][built["figure_id"]]["report_id"] = "rpt-wrong-20260630-999"
    write_yaml(figures_index, figures)

    result = run_healthcheck(tmp_path)
    codes = {finding["code"] for finding in result["findings"]}

    assert result["status"] == "fail"
    assert "figure_report_missing" in codes
    assert "report_figure_backlink_mismatch" in codes


def test_cli_healthcheck_returns_nonzero_on_failure(tmp_path: Path, capsys) -> None:
    built = _build_v0_2_raman_project(tmp_path)
    figures_index = tmp_path / "figures" / "index.yml"
    figures = read_yaml(figures_index)
    figures["figures"][built["figure_id"]]["path"] = "figures/missing.png"
    write_yaml(figures_index, figures)

    result_code = main(["healthcheck", str(tmp_path)])
    output = json.loads(capsys.readouterr().out)
    codes = {finding["code"] for finding in output["findings"]}

    assert result_code == 2
    assert output["status"] == "fail"
    assert "figure_file_missing" in codes
