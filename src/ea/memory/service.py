from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Literal

from ea.provenance import write_provenance_entry
from ea.review import classify_user_response, require_confirmed_review, write_review_record
from ea.schema import OpenItem, ProgressEvent, SuggestionRecord
from ea.schema.models import EARecord
from ea.storage.files import read_markdown_record, read_yaml, write_markdown_record, write_yaml
from ea.storage.ids import next_id


class MemoryBoundaryError(RuntimeError):
    """Raised when a write would blur suggestion, decision, progress, or finding."""


DECISION_PHRASES = ["我采用", "我下一步计划", "接下来我决定", "这条路线先暂停", "我们改成"]
MEMORY_CATEGORIES = {"finding", "interpretation", "hypothesis", "method_note", "project_rule"}
CONFIDENCE_VALUES = {"high", "medium", "low", "insufficient"}


def _append_markdown(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_text(encoding="utf-8")
    else:
        existing = ""
    path.write_text(existing.rstrip() + "\n\n" + text.strip() + "\n", encoding="utf-8")


def _relative_ref(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _project_path(root: Path, value: Path) -> Path:
    return value if value.is_absolute() else root / value


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _load_candidate(root: Path, candidate_path: Path) -> tuple[Path, dict[str, Any], str]:
    path = _project_path(root, candidate_path)
    frontmatter, body = read_markdown_record(path)
    if not frontmatter.get("memory_candidate_id"):
        raise MemoryBoundaryError(f"Not a memory candidate: {candidate_path}")
    return path, frontmatter, body


def _memory_index_path(root: Path) -> Path:
    return root / "memory" / "index.yml"


def _update_candidate_index(root: Path, candidate_ref: str, data: dict[str, Any]) -> None:
    index_path = root / "memory" / "candidates" / "index.yml"
    index = read_yaml(index_path) if index_path.exists() else {"schema_version": "0.2", "candidates": {}}
    index.setdefault("candidates", {})[data["memory_candidate_id"]] = {
        "memory_candidate_id": data["memory_candidate_id"],
        "path": candidate_ref,
        "project_id": data["project_id"],
        "status": data["status"],
        "category": data["category"],
        "confidence": data["confidence"],
        "source_refs": data.get("source_refs", []),
        "provenance_refs": data.get("provenance_refs", []),
        "review_refs": data.get("review_refs", []),
        "committed_memory_id": data.get("committed_memory_id"),
    }
    write_yaml(index_path, index)


def _update_memory_index(root: Path, record: dict[str, Any]) -> None:
    index_path = _memory_index_path(root)
    index = read_yaml(index_path) if index_path.exists() else {"schema_version": "0.2", "memories": {}}
    index.setdefault("memories", {})[record["memory_id"]] = record
    write_yaml(index_path, index)


def propose_memory_candidate(
    root: Path,
    *,
    project_id: str,
    candidate_text: str,
    source_refs: list[str],
    provenance_refs: list[str],
    category: Literal["finding", "interpretation", "hypothesis", "method_note", "project_rule"] = "interpretation",
    confidence: Literal["high", "medium", "low", "insufficient"] = "medium",
    rationale: str | None = None,
    created_at: str | None = None,
) -> Path:
    if category not in MEMORY_CATEGORIES:
        raise ValueError(f"Unsupported memory category: {category}")
    if confidence not in CONFIDENCE_VALUES:
        raise ValueError(f"Unsupported confidence: {confidence}")
    if not candidate_text.strip():
        raise MemoryBoundaryError("Memory candidate text cannot be empty")
    if not source_refs:
        raise MemoryBoundaryError("Memory candidate requires source_refs")
    if not provenance_refs:
        raise MemoryBoundaryError("Memory candidate requires provenance_refs")

    candidate_id = next_id(root, "memory_candidate", created_at[:10] if created_at else None)
    path = root / "memory" / "candidates" / f"{candidate_id}.md"
    frontmatter = {
        "schema_version": "0.2",
        "memory_candidate_id": candidate_id,
        "project_id": project_id,
        "status": "draft",
        "category": category,
        "confidence": confidence,
        "source_refs": source_refs,
        "provenance_refs": provenance_refs,
        "review_refs": [],
        "committed_memory_id": None,
        "content_hash": _content_hash(candidate_text.strip()),
        "rationale": rationale,
        "created_at": created_at or EARecord.now_iso(),
        "updated_at": created_at or EARecord.now_iso(),
    }
    body = candidate_text.strip()
    write_markdown_record(path, frontmatter, body)
    candidate_ref = _relative_ref(root, path)
    _update_candidate_index(root, candidate_ref, frontmatter)
    write_provenance_entry(
        root,
        workflow="memory_candidate_proposal",
        inputs={"records": source_refs, "files": []},
        outputs={"records": [candidate_ref, "memory/candidates/index.yml"], "files": []},
        parameters={"category": category, "confidence": confidence, "status": "draft", "provenance_refs": provenance_refs},
        source_refs=source_refs,
        created_at=created_at,
    )
    return path


def review_memory_candidate(
    root: Path,
    *,
    candidate_path: Path,
    user_response: str,
    reviewed_content: str | None = None,
    reviewed_at: str | None = None,
) -> Path:
    path, frontmatter, body = _load_candidate(root, candidate_path)
    review_path = write_review_record(
        root,
        target_type="memory_candidate",
        target_ref=_relative_ref(root, path),
        user_response=user_response,
        reviewed_content=reviewed_content or body,
        reviewed_at=reviewed_at,
    )
    classification = classify_user_response(user_response)
    if classification.can_save:
        status = "user_confirmed"
    elif classification.review_status == "user_rejected":
        status = "rejected"
    elif classification.review_status == "user_edited":
        status = "needs_revision"
    else:
        status = "deferred"
    review_refs = list(frontmatter.get("review_refs") or [])
    review_refs.append(review_path.stem)
    frontmatter.update(
        {
            "status": status,
            "review_refs": review_refs,
            "user_response": user_response,
            "updated_at": reviewed_at or EARecord.now_iso(),
        }
    )
    write_markdown_record(path, frontmatter, body)
    _update_candidate_index(root, _relative_ref(root, path), frontmatter)
    return path


def commit_memory_candidate(
    root: Path,
    *,
    candidate_path: Path,
    review_ref: str | None = None,
    committed_at: str | None = None,
) -> Path:
    path, frontmatter, body = _load_candidate(root, candidate_path)
    if frontmatter.get("status") != "user_confirmed":
        raise MemoryBoundaryError("Memory candidate must be user_confirmed before commit")
    review_refs = list(frontmatter.get("review_refs") or [])
    selected_review = review_ref or (review_refs[-1] if review_refs else None)
    if not selected_review:
        raise MemoryBoundaryError("Memory candidate commit requires a review_ref")
    if selected_review not in review_refs:
        raise MemoryBoundaryError("Selected review_ref is not linked to the candidate")
    require_confirmed_review(root, selected_review)

    memory_id = next_id(root, "memory", committed_at[:10] if committed_at else None)
    category = str(frontmatter.get("category", "interpretation"))
    target_ref = "memory/hypotheses.md" if category == "hypothesis" else "memory/confirmed-findings.md"
    target_path = root / target_ref
    candidate_ref = _relative_ref(root, path)
    memory_record = {
        "memory_id": memory_id,
        "project_id": frontmatter["project_id"],
        "category": category,
        "confidence": frontmatter.get("confidence"),
        "candidate_ref": candidate_ref,
        "source_refs": frontmatter.get("source_refs", []),
        "provenance_refs": frontmatter.get("provenance_refs", []),
        "review_refs": [selected_review],
        "target_ref": target_ref,
        "committed_at": committed_at or EARecord.now_iso(),
        "content_hash": frontmatter.get("content_hash"),
    }
    block = f"""## Memory {memory_id}

{body.strip()}

category: {category}
confidence: {frontmatter.get('confidence')}
candidate_ref: {candidate_ref}
source_refs: {frontmatter.get('source_refs', [])}
review_refs: [{selected_review}]
provenance_refs: {frontmatter.get('provenance_refs', [])}
"""
    _append_markdown(target_path, block)
    _update_memory_index(root, memory_record)
    frontmatter["status"] = "committed"
    frontmatter["committed_memory_id"] = memory_id
    frontmatter["updated_at"] = committed_at or EARecord.now_iso()
    write_markdown_record(path, frontmatter, body)
    _update_candidate_index(root, candidate_ref, frontmatter)
    write_provenance_entry(
        root,
        workflow="memory_candidate_commit",
        inputs={"records": [candidate_ref] + frontmatter.get("source_refs", []), "files": []},
        outputs={"records": [target_ref, "memory/index.yml", "memory/candidates/index.yml"], "files": []},
        parameters={"memory_id": memory_id, "category": category, "target": target_ref},
        review_refs=[selected_review],
        source_refs=frontmatter.get("source_refs", []),
        created_at=committed_at,
    )
    return target_path


def record_suggestion(
    root: Path,
    *,
    project_id: str,
    trigger: str,
    suggestion_text: str,
    related_records: list[str] | None = None,
    source_refs: list[str] | None = None,
    created_at: str | None = None,
) -> Path:
    suggestion_id = next_id(root, "suggestion")
    suggestion = SuggestionRecord(
        suggestion_id=suggestion_id,
        project_id=project_id,
        status="draft",
        created_at=created_at or EARecord.now_iso(),
        trigger=trigger,
        suggestion_text=suggestion_text,
        related_records=related_records or [],
        source_refs=source_refs or [],
    )
    path = root / "suggestions" / f"{suggestion_id}.md"
    write_markdown_record(path, suggestion.model_dump(exclude_none=True), suggestion_text)
    write_provenance_entry(
        root,
        workflow="suggestion_generation",
        inputs={"records": related_records or [], "files": []},
        outputs={"records": [str(path.relative_to(root))], "files": []},
        parameters={"status": "draft"},
        source_refs=source_refs or [],
        created_at=created_at,
    )
    return path


def update_suggestion_status(
    suggestion_path: Path,
    *,
    status: str,
    user_response: str,
) -> Path:
    if status not in {"accepted", "modified", "rejected"}:
        raise ValueError(status)
    frontmatter, body = read_markdown_record(suggestion_path)
    frontmatter["status"] = status
    frontmatter["user_response"] = user_response
    write_markdown_record(suggestion_path, frontmatter, body)
    return suggestion_path


def write_decision_log_entry(
    root: Path,
    *,
    user_original_text: str,
    ea_summary: str,
    related_suggestion_ref: str | None = None,
    source_refs: list[str] | None = None,
    review_refs: list[str] | None = None,
    decided_at: str | None = None,
) -> Path:
    if not any(phrase in user_original_text for phrase in DECISION_PHRASES):
        raise MemoryBoundaryError("Decision log requires explicit user decision language")
    if not review_refs:
        raise MemoryBoundaryError("Decision log requires confirmed review_refs")
    for review_ref in review_refs:
        require_confirmed_review(root, review_ref)
    decision_id = next_id(root, "decision")
    entry = {
        "decision_id": decision_id,
        "decided_at": decided_at or EARecord.now_iso(),
        "user_original_text": user_original_text,
        "ea_summary": ea_summary,
        "related_suggestion_ref": related_suggestion_ref,
        "source_refs": source_refs or [],
        "review_refs": review_refs or [],
    }
    path = root / "memory" / "decision-log.md"
    _append_markdown(path, "```yaml\n" + _simple_yaml(entry) + "```")
    write_provenance_entry(
        root,
        workflow="memory_write",
        inputs={"records": source_refs or [], "files": []},
        outputs={"records": ["memory/decision-log.md"], "files": []},
        parameters={"target": "decision-log"},
        review_refs=review_refs,
        source_refs=source_refs or [],
        created_at=decided_at,
    )
    return path


def write_progress_event(
    root: Path,
    *,
    user_original_text: str,
    ea_summary: str,
    event_type: str,
    source_kind: str,
    source_refs: list[str] | None = None,
    review_refs: list[str] | None = None,
    recorded_at: str | None = None,
) -> Path:
    if source_kind == "suggestion":
        raise MemoryBoundaryError("EA suggestions cannot become progress events")
    if not review_refs:
        raise MemoryBoundaryError("Progress event requires confirmed review_refs")
    for review_ref in review_refs:
        require_confirmed_review(root, review_ref)
    progress_id = next_id(root, "progress")
    event = ProgressEvent(
        progress_id=progress_id,
        recorded_at=recorded_at or EARecord.now_iso(),
        user_original_text=user_original_text,
        ea_summary=ea_summary,
        event_type=event_type,  # type: ignore[arg-type]
        source_refs=source_refs or [],
        review_refs=review_refs or [],
    )
    path = root / "progress" / f"{progress_id}.yml"
    write_yaml(path, event.model_dump(exclude_none=True))
    write_provenance_entry(
        root,
        workflow="progress_event_write",
        inputs={"records": source_refs or [], "files": []},
        outputs={"records": [str(path.relative_to(root))], "files": []},
        parameters={"event_type": event_type, "source_kind": source_kind},
        review_refs=review_refs,
        source_refs=source_refs or [],
        created_at=recorded_at,
    )
    return path


def write_confirmed_finding(
    root: Path,
    *,
    finding_text: str,
    source_refs: list[str],
    user_response: str,
    reviewed_content: str,
    provenance_refs: list[str],
    reviewed_at: str | None = None,
    finding_type: str = "interpretation",
) -> Path:
    if finding_type == "hypothesis":
        raise MemoryBoundaryError("Hypotheses must be written to open questions, not confirmed findings")
    if not source_refs:
        raise MemoryBoundaryError("Confirmed finding requires source_refs")
    if not provenance_refs:
        raise MemoryBoundaryError("Confirmed finding requires provenance_refs")
    classification = classify_user_response(user_response)
    if not classification.can_save:
        raise MemoryBoundaryError("Confirmed finding requires clear user confirmation")
    review_path = write_review_record(
        root,
        target_type="confirmed_finding",
        target_ref="memory/confirmed-findings.md",
        user_response=user_response,
        reviewed_content=reviewed_content,
        reviewed_at=reviewed_at,
    )
    path = root / "memory" / "confirmed-findings.md"
    block = f"""## Confirmed Finding

{finding_text}

source_refs: {source_refs}
review_refs: [{review_path.stem}]
provenance_refs: {provenance_refs}
"""
    _append_markdown(path, block)
    write_provenance_entry(
        root,
        workflow="memory_write",
        inputs={"records": source_refs, "files": []},
        outputs={"records": ["memory/confirmed-findings.md"], "files": []},
        parameters={"target": "confirmed-findings"},
        review_refs=[review_path.stem],
        source_refs=source_refs,
        created_at=reviewed_at,
    )
    return path


def write_open_item(
    root: Path,
    *,
    item_type: str,
    description: str,
    related_records: list[str] | None = None,
    priority: str = "medium",
    source_refs: list[str] | None = None,
    created_at: str | None = None,
) -> Path:
    open_item_id = next_id(root, "open_item", created_at[:10] if created_at else None)
    item = OpenItem(
        open_item_id=open_item_id,
        created_at=created_at or EARecord.now_iso(),
        item_type=item_type,
        description=description,
        related_records=related_records or [],
        priority=priority,  # type: ignore[arg-type]
        source_refs=source_refs or [],
    )
    path = root / "open-items" / f"{open_item_id}.yml"
    write_yaml(path, item.model_dump(exclude_none=True))
    return path


def _simple_yaml(entry: dict) -> str:
    import yaml

    return yaml.safe_dump(entry, allow_unicode=True, sort_keys=False)
