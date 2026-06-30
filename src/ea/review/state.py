from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from ea.schema import ReviewRecord
from ea.schema.models import EARecord
from ea.storage.files import write_yaml
from ea.storage.files import read_yaml
from ea.storage.ids import next_id


@dataclass(frozen=True)
class ReviewClassification:
    review_status: str
    decision: str
    can_save: bool


CONFIRM_PATTERNS = [
    "可以，保存",
    "可以,保存",
    "没问题",
    "可以的",
    "确认",
    "就按这个保存",
    "这版是对的",
]
REJECT_PATTERNS = ["拒绝", "不要保存", "不保存", "取消"]
DEFER_PATTERNS = ["再看看", "先放着", "之后再说", "稍后", "可能吧", "大概是"]
EDIT_PATTERNS = ["改成", "修改", "不对", "更正", "应该是"]


def classify_user_response(text: str) -> ReviewClassification:
    normalized = text.strip().lower().replace(" ", "")
    if any(pattern in normalized for pattern in REJECT_PATTERNS):
        return ReviewClassification("user_rejected", "rejected_by_user", False)
    if any(pattern in normalized for pattern in EDIT_PATTERNS):
        return ReviewClassification("user_edited", "accepted_with_user_edits", False)
    if any(pattern in normalized for pattern in DEFER_PATTERNS):
        return ReviewClassification("deferred", "needs_later_review", False)
    if any(pattern in normalized for pattern in CONFIRM_PATTERNS):
        return ReviewClassification("user_confirmed", "confirmed_by_user", True)
    return ReviewClassification("deferred", "needs_clear_confirmation", False)


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def write_review_record(
    root: Path,
    *,
    target_type: str,
    target_ref: str,
    user_response: str,
    reviewed_content: str,
    reviewed_at: str | None = None,
) -> Path:
    classification = classify_user_response(user_response)
    review_id = next_id(root, "review", reviewed_at[:10] if reviewed_at else None)
    record = ReviewRecord(
        review_id=review_id,
        target_type=target_type,
        target_ref=target_ref,
        review_status=classification.review_status,
        decision=classification.decision,
        reviewed_at=reviewed_at or EARecord.now_iso(),
        user_original_text=user_response,
        reviewed_content_hash=content_hash(reviewed_content),
    )
    return write_yaml(root / "reviews" / f"{review_id}.yml", record.model_dump(exclude_none=True))


def review_path_for_ref(root: Path, review_ref: str) -> Path:
    path = Path(review_ref)
    if path.suffix:
        return root / path
    return root / "reviews" / f"{review_ref}.yml"


def require_confirmed_review(root: Path, review_ref: str) -> dict:
    path = review_path_for_ref(root, review_ref)
    if not path.exists():
        raise ReviewRequiredErrorForRef(f"ReviewRecord does not exist: {review_ref}")
    review = read_yaml(path)
    if review.get("review_status") != "user_confirmed":
        raise ReviewRequiredErrorForRef(
            f"ReviewRecord is not user_confirmed: {review_ref}"
        )
    return review


class ReviewRequiredErrorForRef(RuntimeError):
    """Raised when a referenced ReviewRecord is missing or not confirmed."""
