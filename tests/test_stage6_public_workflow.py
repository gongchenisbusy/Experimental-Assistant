from pathlib import Path

from ea.experiments import save_confirmed_experiment, structure_experiment_log
from ea.memory import record_suggestion, update_suggestion_status, write_open_item, write_progress_event
from ea.projects import initialize_project
from ea.raman import RamanProcessingRequest, default_processing_parameters, process_raman_result
from ea.raw_import import import_raw_file
from ea.review import write_review_record
from ea.reports import generate_raman_report
from ea.samples import recommend_raman_candidates, save_sample_record
from ea.storage import read_markdown_record, read_yaml


PUBLIC_ROOT = Path("工作指南/test_cases/test-case-001/public")
PUBLIC_RAW = PUBLIC_ROOT / "raw_data"
PUBLIC_DIALOGUE_7 = (
    "第一炉，流速60，四片，硫源660°C开启，保温时间缩短到1min，有有3片长上了，"
    "一片长得很好，两片还不错。长得很好的那一片呈现标准的正三角形形状，"
    "最好的单边尺寸55微米，小一些的也有30微米的。长得稍微差一点的两片，"
    "只有小部分三角形是很标准的，大概尺寸在10到25微米左右，可以考虑用于后续表征。"
    "目前这个cvd反应条件可以保存为阶段实验的标准条件了，后续多炉可以都用这个条件烧。"
)


def test_public_workflow_runs_without_hidden_truth(tmp_path: Path) -> None:
    project = tmp_path / "ea-project"
    initialize_project(
        project,
        project_name="MoS2 mica CVD",
        research_direction="在 mica 上生长单层二硫化钼",
        material_system="MoS2",
        experiment_type="CVD growth and Raman characterization",
        created_at="2026-06-02T17:00:00",
    )

    draft = structure_experiment_log(PUBLIC_DIALOGUE_7)
    experiment_path = save_confirmed_experiment(
        project,
        project_id="project-20260602-mos2-mica-cvd",
        material_system="MoS2",
        experiment_type="CVD growth",
        experiment_date="2026-05-16",
        draft=draft,
        user_response="可以，保存",
        saved_at="2026-06-02T17:05:00",
    )
    experiment_frontmatter, _ = read_markdown_record(experiment_path)
    assert experiment_frontmatter["status"] == "user_confirmed"
    assert "possible_typo_grown_count" in experiment_frontmatter["uncertainties"]

    save_sample_record(
        project,
        sample_id="20260516-run1-sub1",
        project_id="project-20260602-mos2-mica-cvd",
        material_system="MoS2",
        created_from_experiment=experiment_frontmatter["experiment_id"],
        quality_status="candidate_good",
        morphology_observations=["standard regular triangular morphology"],
        quality_notes=["55 um and 30 um domains; user considered suitable for characterization"],
        source_refs=[experiment_frontmatter["experiment_id"]],
    )
    candidates = recommend_raman_candidates(project)
    assert candidates[0].sample_id == "20260516-run1-sub1"
    assert candidates[0].source_ref == experiment_frontmatter["experiment_id"]

    raman_raw = import_raw_file(
        project,
        PUBLIC_RAW / "MoS-2(1).txt",
        project_id="project-20260602-mos2-mica-cvd",
        sample_refs=["20260516-run1-sub1"],
        experiment_refs=[experiment_frontmatter["experiment_id"]],
        imported_at="2026-06-02T17:10:00",
    )
    pl_raw = import_raw_file(
        project,
        PUBLIC_RAW / "MoS-PL-2(1).txt",
        project_id="project-20260602-mos2-mica-cvd",
        characterization_type="pl",
        sample_refs=["20260516-run1-sub1"],
        experiment_refs=[experiment_frontmatter["experiment_id"]],
        imported_at="2026-06-02T17:11:00",
    )
    assert read_yaml(pl_raw.metadata_path)["characterization_type"] == "pl"
    column_review = write_review_record(
        project,
        target_type="raman_columns",
        target_ref=raman_raw.metadata_path.relative_to(project).as_posix(),
        user_response="可以，保存",
        reviewed_content="x=col_0, y=col_1, unit=cm^-1",
    )
    parameter_review = write_review_record(
        project,
        target_type="raman_parameters",
        target_ref=raman_raw.metadata_path.relative_to(project).as_posix(),
        user_response="可以，保存",
        reviewed_content=str(default_processing_parameters()),
    )

    raman_result = process_raman_result(
        project,
        characterization_metadata_path=raman_raw.metadata_path,
        project_id="project-20260602-mos2-mica-cvd",
        sample_refs=["20260516-run1-sub1"],
        request=RamanProcessingRequest(
            x_column="col_0",
            y_column="col_1",
            x_unit="cm^-1",
            processing_parameters=default_processing_parameters(),
            column_review_ref=column_review.stem,
            parameter_review_ref=parameter_review.stem,
        ),
        created_at="2026-06-02T17:15:00",
    )
    report_path = generate_raman_report(
        project,
        project_id="project-20260602-mos2-mica-cvd",
        raman_metadata_path=raman_result,
        related_experiments=[experiment_frontmatter["experiment_id"]],
        related_samples=["20260516-run1-sub1"],
        created_at="2026-06-02T17:20:00",
    )
    report_frontmatter, report_body = read_markdown_record(report_path)
    assert report_frontmatter["include_next_step_suggestions"] is False
    assert "谨慎解释" in report_body
    assert "下一步建议" not in report_body

    suggestion = record_suggestion(
        project,
        project_id="project-20260602-mos2-mica-cvd",
        trigger="user asks whether additional characterization is needed",
        suggestion_text="可以考虑补充 AFM 或 PL 作为后续验证，但这只是 EA 建议草稿。",
        related_records=[report_frontmatter["report_id"]],
        source_refs=[report_frontmatter["report_id"]],
    )
    update_suggestion_status(suggestion, status="accepted", user_response="这个建议可以")
    assert not (project / "memory" / "decision-log.md").exists()
    progress_review = write_review_record(
        project,
        target_type="progress_event",
        target_ref="progress/",
        user_response="可以，保存",
        reviewed_content="Raman data uploaded and processed.",
    )

    progress = write_progress_event(
        project,
        user_original_text="用户提交 Raman 原始数据并请求分析。",
        ea_summary="Raman data uploaded and processed.",
        event_type="analysis",
        source_kind="file",
        source_refs=[raman_raw.characterization_id],
        review_refs=[progress_review.stem],
        recorded_at="2026-06-02T17:25:00",
    )
    assert read_yaml(progress)["event_type"] == "analysis"

    open_item = write_open_item(
        project,
        item_type="uncertain_mapping",
        description="Raman/PL files are linked to a candidate sample, but exact substrate mapping remains user-uncertain.",
        related_records=[raman_raw.characterization_id, pl_raw.characterization_id],
        priority="high",
        source_refs=[experiment_frontmatter["experiment_id"]],
    )
    assert read_yaml(open_item)["status"] == "open"

    workflows = {
        read_yaml(path)["workflow"]
        for path in (project / "provenance").glob("*.yml")
    }
    assert {"experiment_log_save", "raw_file_import", "raman_processing", "report_generation", "suggestion_generation"}.issubset(workflows)
    assert not any("hidden_truth" in str(path) for path in project.rglob("*"))


def test_cli_init_smoke(tmp_path: Path) -> None:
    from ea.cli import main

    workspace = tmp_path / "cli-project"
    result = main(
        [
            "init",
            str(workspace),
            "--name",
            "MoS2 CLI Project",
            "--direction",
            "single-layer MoS2",
            "--material",
            "MoS2",
            "--experiment-type",
            "CVD",
        ]
    )

    assert result == 0
    assert (workspace / "EA_PROJECT.md").exists()
    assert (workspace / "PROJECT_RULE_CARD.md").exists()
