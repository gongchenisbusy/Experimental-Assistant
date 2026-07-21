from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ea.review import (
    classify_user_response,
    require_confirmed_review,
    write_review_record,
)
from ea.review.state import content_hash
from ea.schema.models import EARecord
from ea.storage.files import atomic_copy_file, read_yaml, write_yaml
from ea.storage.ids import next_id
from ea.storage.transactions import OperationJournal


ALLOWED_TARGET_ROOTS = {
    "reports",
    "experiments",
    "samples",
    "literature",
    "suggestions",
    "memory",
    "open-items",
}
FORBIDDEN_SOURCE_PARTS = {"raw", ".ea", "provenance", "knowledge"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_target(root: Path, target_ref: str) -> Path:
    target = Path(target_ref)
    if target.is_absolute() or ".." in target.parts or not target.parts:
        raise ValueError(
            "Draft target must be a project-relative path without parent traversal"
        )
    if target.parts[0] not in ALLOWED_TARGET_ROOTS:
        raise ValueError(f"Draft target root is not allowed: {target.parts[0]}")
    resolved = (root / target).resolve()
    if root.resolve() not in resolved.parents:
        raise ValueError("Draft target escapes the project")
    return resolved


def stage_draft_artifact(
    root: Path,
    *,
    source_path: Path,
    target_ref: str,
    draft_id: str | None = None,
    confirmed: bool = False,
    staged_at: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    source = source_path if source_path.is_absolute() else root / source_path
    source = source.resolve()
    target = _safe_target(root, target_ref)
    if not source.is_file():
        raise FileNotFoundError(source)
    try:
        source_relative = source.relative_to(root)
    except ValueError:
        source_relative = None
    if source_relative and set(source_relative.parts) & FORBIDDEN_SOURCE_PARTS:
        raise PermissionError(
            "Raw, internal, provenance, and knowledge files cannot be staged through the generic draft layer"
        )
    preview = {
        "status": "ready_to_stage",
        "source_name": source.name,
        "target_ref": target.relative_to(root).as_posix(),
        "source_sha256": _sha256(source),
        "requires_confirmation": not confirmed,
    }
    if not confirmed:
        return preview
    staged_at = staged_at or EARecord.now_iso()
    draft_id = draft_id or next_id(root, "draft", day=staged_at[:10])
    if not draft_id.startswith("draft-"):
        raise ValueError("draft_id must start with draft-")
    draft_root = root / "drafts" / draft_id
    manifest_path = draft_root / "draft.yml"
    if manifest_path.exists():
        existing = read_yaml(manifest_path)
        if (
            existing.get("source_sha256") == preview["source_sha256"]
            and existing.get("target_ref") == preview["target_ref"]
        ):
            return {
                **preview,
                "status": existing.get("status"),
                "requires_confirmation": False,
                "draft_id": draft_id,
                "draft_ref": manifest_path.relative_to(root).as_posix(),
            }
        raise FileExistsError(
            f"Draft already exists with different content: {draft_id}"
        )
    content_path = draft_root / f"content{source.suffix}"
    atomic_copy_file(source, content_path)
    manifest = {
        "schema_version": "1.0",
        "draft_id": draft_id,
        "status": "staged",
        "staged_at": staged_at,
        "source_name": source.name,
        "source_sha256": preview["source_sha256"],
        "content_ref": content_path.relative_to(root).as_posix(),
        "target_ref": preview["target_ref"],
        "review_ref": None,
        "promoted_at": None,
        "promotion_operation_ref": None,
    }
    write_yaml(manifest_path, manifest)
    return {
        **preview,
        "status": "staged",
        "requires_confirmation": False,
        "draft_id": draft_id,
        "draft_ref": manifest_path.relative_to(root).as_posix(),
    }


def draft_artifact_status(root: Path, *, draft_id: str) -> dict[str, Any]:
    manifest_path = root / "drafts" / draft_id / "draft.yml"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    manifest = read_yaml(manifest_path)
    return {
        "status": manifest.get("status"),
        "read_only": True,
        "draft_id": draft_id,
        "draft_ref": manifest_path.relative_to(root).as_posix(),
        "target_ref": manifest.get("target_ref"),
        "review_ref": manifest.get("review_ref"),
        "promoted_at": manifest.get("promoted_at"),
    }


def _promotion_review_content(manifest: dict[str, Any]) -> str:
    return json.dumps(
        {
            "draft_id": manifest["draft_id"],
            "source_sha256": manifest["source_sha256"],
            "target_ref": manifest["target_ref"],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def confirm_and_promote_draft_artifact(
    root: Path,
    *,
    draft_id: str,
    user_response: str,
    promoted_at: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    manifest_path = root / "drafts" / draft_id / "draft.yml"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    manifest = read_yaml(manifest_path)
    if manifest.get("status") == "promoted":
        return {
            "status": "promoted",
            "draft_id": draft_id,
            "target_ref": manifest["target_ref"],
            "review_ref": manifest.get("review_ref"),
            "idempotent": True,
        }

    classification = classify_user_response(user_response)
    if not classification.can_save:
        return {
            "status": "needs_clear_confirmation",
            "draft_id": draft_id,
            "target_ref": manifest["target_ref"],
            "review_ref": manifest.get("review_ref"),
            "requires_confirmation": True,
            "writes": False,
        }

    target = _safe_target(root, str(manifest["target_ref"]))
    if target.exists():
        raise FileExistsError(
            f"Draft promotion refuses to overwrite an existing artifact: {manifest['target_ref']}"
        )
    manifest_ref = manifest_path.relative_to(root).as_posix()
    reviewed_content = _promotion_review_content(manifest)
    review_ref = manifest.get("review_ref")
    if review_ref:
        require_confirmed_review(
            root,
            str(review_ref),
            expected_target_type="draft_promotion",
            expected_target_ref=manifest_ref,
            expected_content_hash=content_hash(reviewed_content),
        )
    else:
        review_path = write_review_record(
            root,
            target_type="draft_promotion",
            target_ref=manifest_ref,
            user_response=user_response,
            reviewed_content=reviewed_content,
            reviewed_at=promoted_at,
            confirm=True,
        )
        review_ref = review_path.stem
    return promote_draft_artifact(
        root,
        draft_id=draft_id,
        review_ref=str(review_ref),
        confirmed=True,
        promoted_at=promoted_at,
    )


def promote_draft_artifact(
    root: Path,
    *,
    draft_id: str,
    review_ref: str,
    confirmed: bool = False,
    promoted_at: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    manifest_path = root / "drafts" / draft_id / "draft.yml"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    manifest = read_yaml(manifest_path)
    target = _safe_target(root, str(manifest["target_ref"]))
    if manifest.get("status") == "promoted":
        return {
            "status": "promoted",
            "draft_id": draft_id,
            "target_ref": manifest["target_ref"],
            "idempotent": True,
        }
    manifest_ref = manifest_path.relative_to(root).as_posix()
    review = require_confirmed_review(root, review_ref)
    if (
        review.get("target_ref") != manifest_ref
        or review.get("target_type") != "draft_promotion"
    ):
        raise ValueError(
            "Draft promotion review must target this draft.yml with target_type=draft_promotion"
        )
    require_confirmed_review(
        root,
        review_ref,
        expected_content_hash=content_hash(_promotion_review_content(manifest)),
    )
    preview = {
        "status": "ready_to_promote",
        "draft_id": draft_id,
        "target_ref": manifest["target_ref"],
        "review_ref": review_ref,
        "requires_confirmation": not confirmed,
    }
    if not confirmed:
        return preview
    if target.exists():
        raise FileExistsError(
            f"Draft promotion refuses to overwrite an existing artifact: {manifest['target_ref']}"
        )
    promoted_at = promoted_at or EARecord.now_iso()
    operation_id = f"promote-{draft_id}"
    content_path = root / manifest["content_ref"]
    with OperationJournal(
        root,
        operation_id=operation_id,
        operation="draft_artifact_promotion",
        expected_outputs=[manifest["target_ref"]],
        metadata={"draft_id": draft_id, "review_ref": review_ref},
    ) as journal:
        atomic_copy_file(content_path, target)
        journal.add_artifact(manifest["target_ref"])
        manifest.update(
            {
                "status": "promoted",
                "review_ref": review_ref,
                "promoted_at": promoted_at,
                "target_sha256": _sha256(target),
                "promotion_operation_ref": f".ea/operations/{operation_id}.yml",
            }
        )
        write_yaml(manifest_path, manifest)
        journal.add_artifact(manifest_ref)
    return {
        **preview,
        "status": "promoted",
        "requires_confirmation": False,
        "idempotent": False,
        "operation_ref": manifest["promotion_operation_ref"],
    }
