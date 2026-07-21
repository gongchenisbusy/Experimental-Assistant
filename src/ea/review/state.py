from __future__ import annotations

import hashlib
import re
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
    "confirmed",
    "confirmandsave",
    "yes",
    "yessave",
    "yessaveit",
    "approved",
    "approve",
    "looksgood",
    "looksgoodpleasesave",
    "pleasesave",
    "saveit",
]
REJECT_PATTERNS = ["拒绝", "不要保存", "不保存", "取消", "donotsave", "dontsave", "reject", "rejected"]
DEFER_PATTERNS = ["再看看", "先放着", "之后再说", "稍后", "可能吧", "大概是", "maybelater", "later", "notreadyyet", "defer"]
EDIT_PATTERNS = ["改成", "修改", "不对", "更正", "应该是", "editto", "change", "revise", "correct"]
EXPLICIT_CONFIRM_TARGET_TYPES = frozenset(
    {
        "draft_promotion",
        "electrochemistry_columns",
        "electrochemistry_context",
        "electrochemistry_parameters",
        "ftir_assignment_suggestions",
        "ftir_columns",
        "ftir_parameters",
        "image_description",
        "composite_report_manifest",
        "pl_columns",
        "pl_parameters",
        "raman_columns",
        "raman_parameters",
        "thermal_columns",
        "thermal_context",
        "thermal_parameters",
        "uv_vis_columns",
        "uv_vis_feature_matching",
        "uv_vis_interpretation_suggestions",
        "uv_vis_parameters",
        "uv_vis_replicate_feature_matching",
        "xps_calibration",
        "xps_columns",
        "xps_parameter_suggestions",
        "xps_parameters",
        "xps_region_records",
        "xrd_assignment_suggestions",
        "xrd_columns",
        "xrd_parameters",
    }
)


def _normalize_response(text: str) -> str:
    return re.sub(r"[\s\.,;:!\?，。；：！？'’\"“”]+", "", text.strip().lower())


def _matches_any(normalized_text: str, patterns: list[str]) -> bool:
    return any(_normalize_response(pattern) in normalized_text for pattern in patterns)


def classify_user_response(text: str) -> ReviewClassification:
    normalized = _normalize_response(text)
    if _matches_any(normalized, REJECT_PATTERNS):
        return ReviewClassification("user_rejected", "rejected_by_user", False)
    if _matches_any(normalized, EDIT_PATTERNS):
        return ReviewClassification("user_edited", "accepted_with_user_edits", False)
    if _matches_any(normalized, DEFER_PATTERNS):
        return ReviewClassification("deferred", "needs_later_review", False)
    if _matches_any(normalized, CONFIRM_PATTERNS):
        return ReviewClassification("user_confirmed", "confirmed_by_user", True)
    return ReviewClassification("deferred", "needs_clear_confirmation", False)


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _target_allows_explicit_confirm(target_type: str) -> bool:
    normalized = target_type.strip().lower()
    return normalized in EXPLICIT_CONFIRM_TARGET_TYPES


def write_review_record(
    root: Path,
    *,
    target_type: str,
    target_ref: str,
    user_response: str,
    reviewed_content: str,
    reviewed_at: str | None = None,
    confirm: bool = False,
) -> Path:
    classification = classify_user_response(user_response)
    explicit_confirm_applied = False
    if confirm:
        if not _target_allows_explicit_confirm(target_type):
            raise ValueError(f"Explicit review confirmation is not allowed for target_type: {target_type}")
        classification = ReviewClassification("user_confirmed", "explicitly_confirmed_by_user", True)
        explicit_confirm_applied = True
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
    data = record.model_dump(exclude_none=True)
    if explicit_confirm_applied:
        data["explicit_confirm"] = True
    return write_yaml(root / "reviews" / f"{review_id}.yml", data)


def review_path_for_ref(root: Path, review_ref: str) -> Path:
    path = Path(review_ref)
    if path.suffix:
        return root / path
    return root / "reviews" / f"{review_ref}.yml"


def require_confirmed_review(
    root: Path,
    review_ref: str,
    *,
    expected_target_type: str | None = None,
    expected_target_ref: str | None = None,
    expected_content_hash: str | None = None,
) -> dict:
    path = review_path_for_ref(root, review_ref)
    if not path.exists():
        raise ReviewRequiredErrorForRef(f"ReviewRecord does not exist: {review_ref}")
    review = read_yaml(path)
    if review.get("review_status") != "user_confirmed":
        raise ReviewRequiredErrorForRef(
            f"ReviewRecord is not user_confirmed: {review_ref}"
        )
    expected_fields = {
        "target_type": expected_target_type,
        "target_ref": expected_target_ref,
        "reviewed_content_hash": expected_content_hash,
    }
    for field, expected in expected_fields.items():
        if expected is not None and review.get(field) != expected:
            raise ReviewRequiredErrorForRef(
                f"ReviewRecord {field} does not match expected value: {review_ref}"
            )
    return review


def promote_review_record(
    root: Path,
    review_ref: str,
    *,
    user_response: str,
    promoted_at: str | None = None,
) -> Path:
    path = review_path_for_ref(root, review_ref)
    if not path.exists():
        raise ReviewRequiredErrorForRef(f"ReviewRecord does not exist: {review_ref}")
    review = read_yaml(path)
    if review.get("review_status") == "user_confirmed":
        return path
    target_type = str(review.get("target_type") or "")
    if not _target_allows_explicit_confirm(target_type):
        raise ValueError(f"Review promotion is not allowed for target_type: {target_type}")
    classification = classify_user_response(user_response)
    if not classification.can_save:
        raise ValueError("Review promotion requires a clear confirmation response")
    review.setdefault("promotion_history", []).append(
        {
            "from_status": review.get("review_status"),
            "from_decision": review.get("decision"),
            "user_response": user_response,
            "promoted_at": promoted_at or EARecord.now_iso(),
        }
    )
    review["review_status"] = "user_confirmed"
    review["decision"] = "promoted_after_explicit_user_confirmation"
    review["promotion_user_original_text"] = user_response
    review["promoted_at"] = promoted_at or EARecord.now_iso()
    return write_yaml(path, review)


class ReviewRequiredErrorForRef(RuntimeError):
    """Raised when a referenced ReviewRecord is missing or not confirmed."""
