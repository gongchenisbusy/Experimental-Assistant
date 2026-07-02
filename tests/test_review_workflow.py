from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ea.review import classify_user_response, write_review_record


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
