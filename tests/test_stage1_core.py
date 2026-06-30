from pathlib import Path

from ea.projects import confirm_rule_card_item, initialize_project
from ea.provenance import write_provenance_entry
from ea.review import classify_user_response, write_review_record
from ea.storage import EA_PROJECT_DIRS, read_markdown_record, read_yaml
from ea.storage.ids import next_id


def test_initialize_project_creates_required_local_workspace(tmp_path: Path) -> None:
    outputs = initialize_project(
        tmp_path,
        project_name="MoS2 mica CVD",
        research_direction="single-layer MoS2 on mica",
        material_system="MoS2",
        experiment_type="CVD growth and Raman characterization",
    )

    for rel in EA_PROJECT_DIRS:
        assert (tmp_path / rel).is_dir(), rel

    project_frontmatter, _ = read_markdown_record(outputs["project"])
    rule_frontmatter, _ = read_markdown_record(outputs["rule_card"])

    assert project_frontmatter["workspace_mode"] == "single_project"
    assert project_frontmatter["knowledge_global_dir"] == "knowledge/global/"
    assert project_frontmatter["provenance_refs"]
    assert rule_frontmatter["status"] == "draft"
    assert rule_frontmatter["raw_file_policy"] == "controlled_readonly_copy"
    review_path = confirm_rule_card_item(
        tmp_path,
        rule_key="sample_id_rule",
        reviewed_content="Use date-run-substrate sample IDs",
        user_response="可以，保存",
        reviewed_at="2026-06-02T12:00:00",
    )
    assert read_yaml(review_path)["review_status"] == "user_confirmed"


def test_review_classifier_allows_only_clear_confirmation() -> None:
    assert classify_user_response("可以，保存").can_save is True
    assert classify_user_response("没问题").review_status == "user_confirmed"
    assert classify_user_response("可能吧").can_save is False
    assert classify_user_response("先放着").review_status == "deferred"
    assert classify_user_response("这里不对，改成 60 sccm").review_status == "user_edited"


def test_review_and_provenance_records_are_written_with_links(tmp_path: Path) -> None:
    review_path = write_review_record(
        tmp_path,
        target_type="experiment_record",
        target_ref="experiments/exp-20260602-001.md",
        user_response="可以，保存",
        reviewed_content="flow_rate: 60 sccm",
        reviewed_at="2026-06-02T12:00:00",
    )
    review = read_yaml(review_path)

    assert review["review_status"] == "user_confirmed"
    assert review["target_ref"] == "experiments/exp-20260602-001.md"
    assert len(review["reviewed_content_hash"]) == 64

    provenance_path = write_provenance_entry(
        tmp_path,
        workflow="experiment_log_save",
        inputs={"records": [], "files": []},
        outputs={"records": ["experiments/exp-20260602-001.md"], "files": []},
        parameters={"review_gate": "required"},
        review_refs=[review["review_id"]],
        created_at="2026-06-02T12:01:00",
    )
    provenance = read_yaml(provenance_path)

    assert provenance["workflow"] == "experiment_log_save"
    assert provenance["review_refs"] == [review["review_id"]]
    assert provenance["outputs"]["records"] == ["experiments/exp-20260602-001.md"]


def test_next_id_uses_project_local_daily_counters(tmp_path: Path) -> None:
    assert next_id(tmp_path, "experiment", "2026-06-02") == "exp-20260602-001"
    assert next_id(tmp_path, "experiment", "2026-06-02") == "exp-20260602-002"
    assert next_id(tmp_path, "review", "2026-06-02") == "review-20260602-001"
