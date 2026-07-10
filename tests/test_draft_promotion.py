from __future__ import annotations

from pathlib import Path

import pytest

from ea.drafts import draft_artifact_status, promote_draft_artifact, stage_draft_artifact
from ea.projects import initialize_project
from ea.review import write_review_record
from ea.storage import read_yaml


def _project(root: Path) -> None:
    initialize_project(
        root,
        project_name="Draft project",
        project_slug="draft-project",
        research_direction="transactional draft promotion",
        material_system="MoS2",
        experiment_type="Raman",
    )


def test_draft_stage_and_promotion_are_confirmation_review_and_overwrite_gated(tmp_path: Path) -> None:
    _project(tmp_path)
    source = tmp_path / "generated" / "draft.md"
    source.parent.mkdir()
    source.write_text("# Reviewed draft\n", encoding="utf-8")

    preview = stage_draft_artifact(
        tmp_path,
        source_path=source,
        target_ref="reports/final.md",
        draft_id="draft-20260710-001",
    )
    assert preview["requires_confirmation"] is True
    assert not (tmp_path / "drafts" / "draft-20260710-001").exists()

    staged = stage_draft_artifact(
        tmp_path,
        source_path=source,
        target_ref="reports/final.md",
        draft_id="draft-20260710-001",
        confirmed=True,
        staged_at="2026-07-10T18:00:00",
    )
    manifest_ref = staged["draft_ref"]
    review_path = write_review_record(
        tmp_path,
        target_type="draft_promotion",
        target_ref=manifest_ref,
        user_response="confirmed",
        reviewed_content="Promote this reviewed draft.",
        reviewed_at="2026-07-10T18:01:00",
    )
    promotion_preview = promote_draft_artifact(
        tmp_path,
        draft_id=staged["draft_id"],
        review_ref=review_path.stem,
    )
    assert promotion_preview["requires_confirmation"] is True
    assert not (tmp_path / "reports" / "final.md").exists()

    promoted = promote_draft_artifact(
        tmp_path,
        draft_id=staged["draft_id"],
        review_ref=review_path.stem,
        confirmed=True,
        promoted_at="2026-07-10T18:02:00",
    )
    assert promoted["status"] == "promoted"
    assert (tmp_path / "reports" / "final.md").read_text(encoding="utf-8") == "# Reviewed draft\n"
    assert draft_artifact_status(tmp_path, draft_id=staged["draft_id"])["status"] == "promoted"
    assert read_yaml(tmp_path / promoted["operation_ref"])["status"] == "completed"
    assert promote_draft_artifact(tmp_path, draft_id=staged["draft_id"], review_ref=review_path.stem, confirmed=True)["idempotent"] is True


def test_draft_refuses_raw_sources_wrong_reviews_and_existing_targets(tmp_path: Path) -> None:
    _project(tmp_path)
    raw = tmp_path / "raw" / "private.txt"
    raw.write_text("raw", encoding="utf-8")
    with pytest.raises(PermissionError):
        stage_draft_artifact(tmp_path, source_path=raw, target_ref="reports/raw.md", confirmed=True)

    source = tmp_path / "candidate.md"
    source.write_text("candidate", encoding="utf-8")
    staged = stage_draft_artifact(
        tmp_path,
        source_path=source,
        target_ref="reports/existing.md",
        draft_id="draft-20260710-002",
        confirmed=True,
    )
    wrong_review = write_review_record(
        tmp_path,
        target_type="report_text",
        target_ref=staged["draft_ref"],
        user_response="confirmed",
        reviewed_content="wrong target type",
    )
    with pytest.raises(ValueError, match="draft_promotion"):
        promote_draft_artifact(tmp_path, draft_id=staged["draft_id"], review_ref=wrong_review.stem, confirmed=True)

    correct_review = write_review_record(
        tmp_path,
        target_type="draft_promotion",
        target_ref=staged["draft_ref"],
        user_response="confirmed",
        reviewed_content="correct review",
    )
    (tmp_path / "reports" / "existing.md").write_text("existing", encoding="utf-8")
    with pytest.raises(FileExistsError, match="refuses to overwrite"):
        promote_draft_artifact(tmp_path, draft_id=staged["draft_id"], review_ref=correct_review.stem, confirmed=True)
