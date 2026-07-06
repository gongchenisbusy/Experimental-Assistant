from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from ea.review import classify_user_response, promote_review_record, write_review_record
from ea.storage import read_yaml


def test_review_classification_accepts_common_english_confirmations() -> None:
    for text in [
        "confirmed",
        "confirm and save",
        "yes, save it",
        "approved",
        "looks good, please save",
    ]:
        classification = classify_user_response(text)

        assert classification.review_status == "user_confirmed"
        assert classification.can_save is True


def test_review_ids_remain_unique_under_parallel_writes(tmp_path: Path) -> None:
    def write_one(index: int) -> str:
        path = write_review_record(
            tmp_path,
            target_type="parallel_review",
            target_ref=f"records/item-{index:03d}.yml",
            user_response="confirmed",
            reviewed_content=f"reviewed content {index}",
            reviewed_at="2026-07-02T12:00:00",
        )
        return path.stem

    with ThreadPoolExecutor(max_workers=8) as executor:
        review_ids = list(executor.map(write_one, range(40)))

    assert len(review_ids) == 40
    assert len(set(review_ids)) == 40
    assert sorted(review_ids) == [f"review-20260702-{index:03d}" for index in range(1, 41)]


def test_review_add_confirm_marks_parameter_review_confirmed(tmp_path: Path) -> None:
    path = write_review_record(
        tmp_path,
        target_type="raman_parameters",
        target_ref="raw/raman/metadata.yml",
        user_response="1. baseline=als\n2. smoothing=true",
        reviewed_content="baseline=als; smoothing=true",
        confirm=True,
        reviewed_at="2026-07-07T10:00:00",
    )

    review = read_yaml(path)
    assert review["review_status"] == "user_confirmed"
    assert review["decision"] == "explicitly_confirmed_by_user"
    assert review["explicit_confirm"] is True


def test_review_promote_updates_existing_review_without_changing_hash(tmp_path: Path) -> None:
    path = write_review_record(
        tmp_path,
        target_type="raman_parameters",
        target_ref="raw/raman/metadata.yml",
        user_response="改成 baseline=als",
        reviewed_content="baseline=als",
        reviewed_at="2026-07-07T10:00:00",
    )
    before = read_yaml(path)
    assert before["review_status"] == "user_edited"

    promoted = promote_review_record(
        tmp_path,
        path.stem,
        user_response="可以，保存",
        promoted_at="2026-07-07T10:05:00",
    )
    after = read_yaml(promoted)

    assert promoted == path
    assert after["review_status"] == "user_confirmed"
    assert after["reviewed_content_hash"] == before["reviewed_content_hash"]
    assert after["promotion_history"][0]["from_status"] == "user_edited"


def test_review_confirm_does_not_bypass_scientific_memory_candidate(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        write_review_record(
            tmp_path,
            target_type="memory_candidate",
            target_ref="memory/candidates/memcand-001.md",
            user_response="可以，保存",
            reviewed_content="candidate",
            confirm=True,
        )
