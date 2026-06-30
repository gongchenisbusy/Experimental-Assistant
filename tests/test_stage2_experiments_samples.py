from pathlib import Path

import pytest

from ea.experiments import (
    ReviewRequiredError,
    save_confirmed_experiment,
    structure_experiment_log,
)
from ea.samples import recommend_raman_candidates, save_sample_record
from ea.storage import read_markdown_record, read_yaml


PUBLIC_DIALOGUE_7 = (
    "第一炉，流速60，四片，硫源660°C开启，保温时间缩短到1min，有有3片长上了，"
    "一片长得很好，两片还不错。长得很好的那一片呈现标准的正三角形形状，"
    "最好的单边尺寸55微米，小一些的也有30微米的。长得稍微差一点的两片，"
    "只有小部分三角形是很标准的，大概尺寸在10到25微米左右，可以考虑用于后续表征。"
    "目前这个cvd反应条件可以保存为阶段实验的标准条件了，后续多炉可以都用这个条件烧。"
)


def test_structure_experiment_log_creates_review_gated_draft() -> None:
    draft = structure_experiment_log(PUBLIC_DIALOGUE_7)

    assert draft.status == "needs_user_review"
    assert draft.process_conditions["flow_rate"] == 60
    assert draft.process_conditions["flow_rate_unit"] == "unknown"
    assert draft.process_conditions["substrate_count"] == 4
    assert draft.process_conditions["sulfur_start_temperature_c"] == 660
    assert draft.process_conditions["hold_time_min"] == 1
    assert draft.process_conditions["grown_substrate_count"] == 3
    assert "regular_triangle_morphology_mentioned" in draft.observations
    assert "actual_experiment_date" in draft.uncertainties
    assert "possible_typo_grown_count" in draft.uncertainties
    assert "requires_explicit_decision_log_confirmation" in draft.uncertainties


def test_experiment_save_requires_clear_user_confirmation(tmp_path: Path) -> None:
    draft = structure_experiment_log(PUBLIC_DIALOGUE_7)

    with pytest.raises(ReviewRequiredError):
        save_confirmed_experiment(
            tmp_path,
            project_id="project-20260602-mos2",
            material_system="MoS2",
            experiment_type="CVD growth",
            experiment_date="2026-05-16",
            draft=draft,
            user_response="可能吧",
        )

    path = save_confirmed_experiment(
        tmp_path,
        project_id="project-20260602-mos2",
        material_system="MoS2",
        experiment_type="CVD growth",
        experiment_date="2026-05-16",
        draft=draft,
        user_response="可以，保存",
        saved_at="2026-06-02T13:00:00",
    )
    frontmatter, body = read_markdown_record(path)

    assert frontmatter["status"] == "user_confirmed"
    assert frontmatter["experiment_id"] == "exp-20260516-001"
    assert frontmatter["review_refs"]
    assert frontmatter["provenance_refs"]
    assert PUBLIC_DIALOGUE_7 in body

    review = read_yaml(tmp_path / "reviews" / f"{frontmatter['review_refs'][0]}.yml")
    provenance = read_yaml(
        tmp_path / "provenance" / f"{frontmatter['provenance_refs'][0]}.yml"
    )
    assert review["review_status"] == "user_confirmed"
    assert provenance["workflow"] == "experiment_log_save"


def test_raman_candidate_recommendations_include_sources(tmp_path: Path) -> None:
    save_sample_record(
        tmp_path,
        sample_id="20260516-run1-sub1",
        project_id="project-20260602-mos2",
        material_system="MoS2",
        created_from_experiment="exp-20260516-001",
        quality_status="candidate_good",
        morphology_observations=["regular triangular domains"],
        quality_notes=["55 um and 30 um domains suitable for Raman/AFM"],
        source_refs=["exp-20260516-001"],
    )
    save_sample_record(
        tmp_path,
        sample_id="20260516-run1-sub2",
        project_id="project-20260602-mos2",
        material_system="MoS2",
        created_from_experiment="exp-20260516-001",
        quality_status="candidate_medium",
        morphology_observations=["some standard triangles"],
        quality_notes=["10 to 25 um domains"],
        source_refs=["exp-20260516-001"],
    )
    save_sample_record(
        tmp_path,
        sample_id="20260515-run2-sub1",
        project_id="project-20260602-mos2",
        material_system="MoS2",
        created_from_experiment="exp-20260515-002",
        quality_status="candidate_poor",
        morphology_observations=["too thick"],
        quality_notes=["discarded by user"],
        source_refs=["exp-20260515-002"],
    )

    candidates = recommend_raman_candidates(tmp_path)

    assert [candidate.sample_id for candidate in candidates] == [
        "20260516-run1-sub1",
        "20260516-run1-sub2",
    ]
    assert candidates[0].source_label == "exp-20260516-001"
    assert "regular triangular" in candidates[0].reason
