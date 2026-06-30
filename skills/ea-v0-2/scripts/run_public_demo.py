#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


REPO_ROOT = _repo_root()
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ea.experiments import save_confirmed_experiment, structure_experiment_log
from ea.memory import record_suggestion, update_suggestion_status, write_open_item, write_progress_event
from ea.projects import initialize_project
from ea.raman import RamanProcessingRequest, default_processing_parameters, process_raman_result
from ea.raw_import import import_raw_file
from ea.reports import generate_raman_report
from ea.review import write_review_record
from ea.samples import recommend_raman_candidates, save_sample_record
from ea.storage import read_markdown_record, read_yaml


PUBLIC_DIALOGUE_7 = (
    "第一炉，流速60，四片，硫源660°C开启，保温时间缩短到1min，有有3片长上了，"
    "一片长得很好，两片还不错。长得很好的那一片呈现标准的正三角形形状，"
    "最好的单边尺寸55微米，小一些的也有30微米的。长得稍微差一点的两片，"
    "只有小部分三角形是很标准的，大概尺寸在10到25微米左右，可以考虑用于后续表征。"
    "目前这个cvd反应条件可以保存为阶段实验的标准条件了，后续多炉可以都用这个条件烧。"
)


def run_demo(workspace: Path, fixture_root: Path, *, force: bool = False) -> dict[str, str]:
    raw_root = fixture_root / "raw_data"
    if not raw_root.is_dir():
        raise SystemExit(f"Fixture raw_data directory not found: {raw_root}")
    if workspace.exists():
        if not force:
            raise SystemExit(f"Workspace already exists; pass --force to replace it: {workspace}")
        shutil.rmtree(workspace)

    outputs = initialize_project(
        workspace,
        project_name="MoS2 mica CVD",
        project_slug="mos2-mica-cvd",
        research_direction="在 mica 上生长单层二硫化钼",
        material_system="MoS2",
        experiment_type="CVD growth and Raman characterization",
        enable_literature=True,
        created_at="2026-06-02T17:00:00",
    )
    project_frontmatter, _ = read_markdown_record(outputs["project"])
    project_id = project_frontmatter["project_id"]

    draft = structure_experiment_log(PUBLIC_DIALOGUE_7)
    experiment_path = save_confirmed_experiment(
        workspace,
        project_id=project_id,
        material_system="MoS2",
        experiment_type="CVD growth",
        experiment_date="2026-05-16",
        draft=draft,
        user_response="可以，保存",
        saved_at="2026-06-02T17:05:00",
    )
    experiment_frontmatter, _ = read_markdown_record(experiment_path)

    sample_id = "20260516-run1-sub1"
    save_sample_record(
        workspace,
        sample_id=sample_id,
        project_id=project_id,
        material_system="MoS2",
        created_from_experiment=experiment_frontmatter["experiment_id"],
        quality_status="candidate_good",
        morphology_observations=["standard regular triangular morphology"],
        quality_notes=["55 um and 30 um domains; user considered suitable for characterization"],
        source_refs=[experiment_frontmatter["experiment_id"]],
    )
    candidates = recommend_raman_candidates(workspace)

    raman_raw = import_raw_file(
        workspace,
        raw_root / "MoS-2(1).txt",
        project_id=project_id,
        sample_refs=[sample_id],
        experiment_refs=[experiment_frontmatter["experiment_id"]],
        imported_at="2026-06-02T17:10:00",
    )
    pl_raw = import_raw_file(
        workspace,
        raw_root / "MoS-PL-2(1).txt",
        project_id=project_id,
        characterization_type="pl",
        sample_refs=[sample_id],
        experiment_refs=[experiment_frontmatter["experiment_id"]],
        imported_at="2026-06-02T17:11:00",
    )
    column_review = write_review_record(
        workspace,
        target_type="raman_columns",
        target_ref=raman_raw.metadata_path.relative_to(workspace).as_posix(),
        user_response="可以，保存",
        reviewed_content="x=col_0, y=col_1, unit=cm^-1",
    )
    parameter_review = write_review_record(
        workspace,
        target_type="raman_parameters",
        target_ref=raman_raw.metadata_path.relative_to(workspace).as_posix(),
        user_response="可以，保存",
        reviewed_content=str(default_processing_parameters()),
    )
    raman_result = process_raman_result(
        workspace,
        characterization_metadata_path=raman_raw.metadata_path,
        project_id=project_id,
        sample_refs=[sample_id],
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
        workspace,
        project_id=project_id,
        raman_metadata_path=raman_result,
        related_experiments=[experiment_frontmatter["experiment_id"]],
        related_samples=[sample_id],
        created_at="2026-06-02T17:20:00",
    )
    report_frontmatter, _ = read_markdown_record(report_path)

    suggestion = record_suggestion(
        workspace,
        project_id=project_id,
        trigger="user asks whether additional characterization is needed",
        suggestion_text="可以考虑补充 AFM 或 PL 作为后续验证，但这只是 EA 建议草稿。",
        related_records=[report_frontmatter["report_id"]],
        source_refs=[report_frontmatter["report_id"]],
    )
    update_suggestion_status(suggestion, status="accepted", user_response="这个建议可以")

    progress_review = write_review_record(
        workspace,
        target_type="progress_event",
        target_ref="progress/",
        user_response="可以，保存",
        reviewed_content="Raman data uploaded and processed.",
    )
    progress_path = write_progress_event(
        workspace,
        user_original_text="用户提交 Raman 原始数据并请求分析。",
        ea_summary="Raman data uploaded and processed.",
        event_type="analysis",
        source_kind="file",
        source_refs=[raman_raw.characterization_id],
        review_refs=[progress_review.stem],
        recorded_at="2026-06-02T17:25:00",
    )
    open_item = write_open_item(
        workspace,
        item_type="uncertain_mapping",
        description="Raman/PL files are linked to a candidate sample, but exact substrate mapping remains user-uncertain.",
        related_records=[raman_raw.characterization_id, pl_raw.characterization_id],
        priority="high",
        source_refs=[experiment_frontmatter["experiment_id"]],
    )
    raman_metadata = read_yaml(raman_result)
    return {
        "workspace": str(workspace),
        "project_id": project_id,
        "experiment_path": str(experiment_path),
        "candidate_sample": candidates[0].sample_id if candidates else "",
        "raman_metadata_path": str(raman_result),
        "report_path": str(report_path),
        "figure_path": str(workspace / raman_metadata["outputs"]["figure"]),
        "processed_csv_path": str(workspace / raman_metadata["outputs"]["processed_csv"]),
        "peak_table_path": str(workspace / raman_metadata["outputs"]["peak_table"]),
        "progress_path": str(progress_path),
        "open_item_path": str(open_item),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run EA v0.2 public fixture demo.")
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--fixture-root", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    summary = run_demo(args.workspace, args.fixture_root, force=args.force)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
