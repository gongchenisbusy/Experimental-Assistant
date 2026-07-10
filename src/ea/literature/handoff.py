from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import urlsplit, urlunsplit


HANDOFF_SCHEMA_VERSION = "1.0"
TARGET_STATUSES = {
    "acquired",
    "cache_verified",
    "needs_login",
    "needs_subscription",
    "blocked",
    "manual_pdf_handoff_ready",
    "invalid_pdf",
    "retryable_error",
    "not_attempted",
}
READY_STATUSES = {"acquired", "cache_verified"}

_STATUS_ALIASES = {
    "complete": "acquired",
    "completed": "acquired",
    "success": "acquired",
    "ok": "acquired",
    "downloaded": "acquired",
    "imported": "acquired",
    "ingested": "acquired",
    "cached": "cache_verified",
    "reused-cache": "cache_verified",
    "reused_cache": "cache_verified",
    "cache-created-or-verified": "cache_verified",
    "cache_created_or_verified": "cache_verified",
    "acquired-and-cached": "cache_verified",
    "acquired_and_cached": "cache_verified",
    "acquired-and-read": "cache_verified",
    "acquired_and_read": "cache_verified",
    "cache-ok": "cache_verified",
    "cache_ok": "cache_verified",
    "needs-login": "needs_login",
    "login-required": "needs_login",
    "login_required": "needs_login",
    "auth-required": "needs_login",
    "auth_required": "needs_login",
    "needs-browser-authorization": "needs_login",
    "needs_browser_authorization": "needs_login",
    "subscription-required": "needs_subscription",
    "subscription_required": "needs_subscription",
    "paywall": "needs_subscription",
    "no-access": "needs_subscription",
    "no_access": "needs_subscription",
    "manual-pdf-handoff-ready": "manual_pdf_handoff_ready",
    "manual_pdf_ready": "manual_pdf_handoff_ready",
    "downloaded-without-import": "manual_pdf_handoff_ready",
    "downloaded_without_import": "manual_pdf_handoff_ready",
    "failed-nonpdf": "invalid_pdf",
    "failed_nonpdf": "invalid_pdf",
    "invalid-pdf": "invalid_pdf",
    "invalid_pdf": "invalid_pdf",
    "timeout": "retryable_error",
    "connection-refused": "retryable_error",
    "connection_refused": "retryable_error",
    "retryable": "retryable_error",
    "retryable-error": "retryable_error",
    "failed-nonjson": "retryable_error",
    "failed_nonjson": "retryable_error",
    "failed": "blocked",
    "failure": "blocked",
    "error": "blocked",
    "failed-ambiguous": "blocked",
    "failed_ambiguous": "blocked",
    "pending": "not_attempted",
    "queued": "not_attempted",
    "planned": "not_attempted",
    "running": "not_attempted",
    "not-attempted": "not_attempted",
}

_ERROR_PATTERNS = [
    (re.compile(r"\b(eperm|permission denied|operation not permitted)\b", re.I), "permission_denied"),
    (re.compile(r"\b(connection refused|econnrefused)\b", re.I), "connection_refused"),
    (re.compile(r"\b(timeout|timed out|etimedout)\b", re.I), "timeout"),
    (re.compile(r"\b(not running|software unavailable|service unavailable)\b", re.I), "software_not_running"),
    (re.compile(r"\b(duplicate parent|ambiguous parent|multiple parent)\b", re.I), "duplicate_parent_ambiguous"),
    (re.compile(r"\b(missing attachment|attachment file.*missing|attachment.*not found)\b", re.I), "missing_attachment_file"),
    (re.compile(r"\b(is a directory|path.*directory|eisdir)\b", re.I), "path_is_directory"),
    (re.compile(r"\b(subscription|paywall|no access)\b", re.I), "subscription_required"),
    (re.compile(r"\b(login|sign[ -]?in|authentication|authorization)\b", re.I), "user_login_required"),
    (re.compile(r"\b(non[- ]?pdf|invalid pdf|corrupt pdf|html instead of pdf)\b", re.I), "invalid_pdf"),
]

_NEXT_ACTIONS = {
    "acquired": "Verify or index the acquired PDF, then continue the EA evidence workflow.",
    "cache_verified": "Use the verified cache for extraction; no new download is required.",
    "needs_login": "Complete lawful sign-in in the user-managed browser session, then retry this target.",
    "needs_subscription": "Use institution access or provide a lawfully obtained PDF; do not bypass access controls.",
    "blocked": "Review the blocked reason and use the recorded lawful repair or manual handoff path.",
    "manual_pdf_handoff_ready": "Provide the lawfully obtained PDF to the recorded manual ingest path.",
    "invalid_pdf": "Replace the response with a verified PDF before ingesting or extracting data.",
    "retryable_error": "Resolve the transient local error, then run the privacy-safe retry command.",
    "not_attempted": "Start acquisition for this target when the user confirms the external workflow.",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _status_text(item: dict[str, Any]) -> str:
    return _text(
        item.get("status")
        or item.get("acquisition_status")
        or item.get("result_status")
        or item.get("outcome")
        or item.get("state")
    ).lower()


def classify_blocked_reason(value: Any) -> str | None:
    text = _text(value)
    if not text:
        return None
    for pattern, code in _ERROR_PATTERNS:
        if pattern.search(text):
            return code
    normalized = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return normalized[:80] or "unspecified_blocker"


def normalize_target_status(item: dict[str, Any]) -> str:
    source_status = _status_text(item).replace(" ", "-")
    normalized = _STATUS_ALIASES.get(source_status, source_status.replace("-", "_"))
    has_cache = any(item.get(key) for key in ("cache_path", "cache_dir", "cached_path", "source_hash", "cache_hash"))
    has_pdf = any(item.get(key) for key in ("local_path", "pdf_path", "attachment_path", "pdf"))
    if normalized not in TARGET_STATUSES:
        reason = classify_blocked_reason(item.get("reason") or item.get("error") or item.get("message"))
        if reason in {"connection_refused", "timeout", "software_not_running"}:
            normalized = "retryable_error"
        elif reason == "user_login_required":
            normalized = "needs_login"
        elif reason == "subscription_required":
            normalized = "needs_subscription"
        elif reason == "invalid_pdf":
            normalized = "invalid_pdf"
        elif has_cache:
            normalized = "cache_verified"
        elif has_pdf or item.get("zotero_item_key") or item.get("item_key"):
            normalized = "acquired"
        elif source_status:
            normalized = "blocked"
        else:
            normalized = "not_attempted"
    return normalized


def privacy_safe_url(value: Any) -> str | None:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = urlsplit(text)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def privacy_safe_cache_ref(value: Any) -> str | None:
    text = _text(value)
    if not text:
        return None
    posix_path = PurePosixPath(text)
    windows_path = PureWindowsPath(text)
    relative_path = PurePosixPath(text.replace("\\", "/"))
    is_absolute = posix_path.is_absolute() or windows_path.is_absolute()
    if not is_absolute and ".." not in relative_path.parts:
        return relative_path.as_posix()
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    name = (windows_path.name if windows_path.is_absolute() else posix_path.name) or "cache"
    return f"external-cache://{digest}/{name}"


def privacy_safe_retry_command(value: Any) -> str | None:
    if isinstance(value, list):
        value = " ".join(str(item) for item in value)
    command = _text(value)
    if not command:
        return None
    command = re.sub(r"https?://[^\s'\"]+", lambda match: privacy_safe_url(match.group(0)) or "<redacted-url>", command)
    command = re.sub(r"(?i)(--(?:browser-)?profile(?:-path)?\s+)(?:'[^']*'|\"[^\"]*\"|\S+)", r"\1<user-profile>", command)
    command = re.sub(r"(?i)(--(?:session|session-id|token|cookie)\s+)(?:'[^']*'|\"[^\"]*\"|\S+)", r"\1<redacted>", command)
    command = re.sub(r"(?<![\w.-])(?:/[\w .@+,:=-]+){2,}", "<local-path>", command)
    return command[:500]


def _source_hash(item: dict[str, Any]) -> str | None:
    value = _text(
        item.get("source_hash")
        or item.get("cache_hash")
        or item.get("sha256")
        or item.get("pdf_sha256")
        or item.get("cache_identity")
    )
    if not value:
        return None
    return value[:160]


def _attempts(item: dict[str, Any]) -> list[dict[str, Any]]:
    source = item.get("attempts")
    if isinstance(source, int):
        return [{"attempt": index + 1} for index in range(min(source, 5))]
    if not isinstance(source, list):
        return []
    attempts: list[dict[str, Any]] = []
    for index, attempt in enumerate(source[-5:], start=max(1, len(source) - 4)):
        if not isinstance(attempt, dict):
            continue
        attempts.append(
            {
                key: value
                for key, value in {
                    "attempt": attempt.get("attempt") or index,
                    "status": _STATUS_ALIASES.get(_status_text(attempt), _status_text(attempt).replace("-", "_")) or None,
                    "blocked_reason": classify_blocked_reason(attempt.get("reason") or attempt.get("error") or attempt.get("message")),
                    "updated_at": attempt.get("updated_at") or attempt.get("ended_at"),
                }.items()
                if value not in (None, "")
            }
        )
    return attempts


def normalize_handoff_target(item: dict[str, Any], *, updated_at: str) -> dict[str, Any]:
    result = item.get("result") if isinstance(item.get("result"), dict) else {}
    next_action = item.get("next_action") if isinstance(item.get("next_action"), dict) else {}
    status = normalize_target_status(item)
    reason_value = (
        item.get("blocked_reason")
        or item.get("reason")
        or item.get("error")
        or item.get("last_error")
        or item.get("message")
    )
    blocked_reason = classify_blocked_reason(reason_value) if status not in READY_STATUSES else None
    return {
        "target_id": item.get("target_id") or item.get("id"),
        "rank": item.get("rank") or item.get("top30_rank"),
        "title": item.get("title") or result.get("title") or "Untitled target",
        "doi": item.get("doi") or item.get("DOI") or result.get("doi"),
        "url": privacy_safe_url(item.get("url") or item.get("landing_page_url")),
        "attempts": _attempts(item),
        "status": status,
        "cache_dir": privacy_safe_cache_ref(
            item.get("cache_dir") or item.get("cache_path") or item.get("cached_path") or result.get("cache_dir")
        ),
        "zotero_item_key": item.get("zotero_item_key") or item.get("item_key") or result.get("item_key"),
        "blocked_reason": blocked_reason,
        "retry_command": privacy_safe_retry_command(
            item.get("retry_command")
            or item.get("retry")
            or next_action.get("retry_command")
            or next_action.get("manual_pdf_handoff_command")
            or next_action.get("prepare_command")
        ),
        "source_hash": _source_hash(item),
        "updated_at": item.get("updated_at") or updated_at,
        "next_action": _NEXT_ACTIONS[status],
    }


def _items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("targets", "items", "results", "records", "entries"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            return [item for item in value.values() if isinstance(item, dict)]
    return []


def _identifier_keys(item: dict[str, Any]) -> set[str]:
    keys = set()
    for field in ("target_id", "doi"):
        value = _text(item.get(field)).lower()
        if value:
            keys.add(f"{field}:{value}")
    return keys


def _compact_state_item(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"status": "unknown", "summary": _text(item)[:200]}
    return {
        key: value
        for key, value in {
            "status": item.get("status"),
            "code": classify_blocked_reason(item.get("code") or item.get("reason") or item.get("error")),
            "summary": _text(item.get("summary") or item.get("message") or item.get("reason"))[:200] or None,
            "updated_at": item.get("updated_at"),
        }.items()
        if value not in (None, "")
    }


def normalize_acquisition_handoff(payload: dict[str, Any], *, updated_at: str) -> dict[str, Any]:
    targets = [normalize_handoff_target(item, updated_at=updated_at) for item in _items(payload)]
    current_keys = set().union(*(_identifier_keys(item) for item in targets)) if targets else set()
    current_task_blockers = [
        {
            "target_id": item.get("target_id"),
            "doi": item.get("doi"),
            "status": item["status"],
            "blocked_reason": item.get("blocked_reason"),
            "next_action": item["next_action"],
        }
        for item in targets
        if item["status"] not in READY_STATUSES
    ]
    stale_global_state = [_compact_state_item(item) for item in (payload.get("stale_global_state") or [])]
    for session in payload.get("sessions") or []:
        if not isinstance(session, dict):
            continue
        session_keys = _identifier_keys(session)
        if session_keys and session_keys & current_keys:
            if normalize_target_status(session) not in READY_STATUSES:
                current_task_blockers.append(_compact_state_item(session))
        else:
            stale_global_state.append(_compact_state_item(session))
    ready_count = sum(item["status"] in READY_STATUSES for item in targets)
    blocked_count = len(targets) - ready_count
    aggregate_status = "complete" if targets and not blocked_count else "partial" if ready_count else "blocked" if targets else "not_started"
    source_hash = hashlib.sha256(
        json.dumps(targets, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    attempts = sum(max(1, len(item["attempts"])) if item["status"] != "not_attempted" else 0 for item in targets)
    return {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "request_id": payload.get("request_id") or payload.get("batch_id") or payload.get("acquisition_id") or f"external-{source_hash[:12]}",
        "targets": targets,
        "attempts": attempts,
        "status": aggregate_status,
        "cache_dir": "per_target_privacy_safe_refs" if any(item.get("cache_dir") for item in targets) else None,
        "zotero_item_key": "per_target" if any(item.get("zotero_item_key") for item in targets) else None,
        "blocked_reason": "see_current_task_blockers" if current_task_blockers else None,
        "retry_command": "per_target" if any(item.get("retry_command") for item in targets) else None,
        "source_hash": source_hash,
        "updated_at": updated_at,
        "summary": {
            "target_count": len(targets),
            "ready_count": ready_count,
            "acquired_count": sum(item["status"] == "acquired" for item in targets),
            "cache_verified_count": sum(item["status"] == "cache_verified" for item in targets),
            "blocked_count": blocked_count,
        },
        "current_task_blockers": current_task_blockers,
        "optional_capabilities": [_compact_state_item(item) for item in (payload.get("optional_capabilities") or [])],
        "stale_global_state": stale_global_state,
        "browser_download_event_fallback": {
            "status": "companion_contract_available",
            "required_controls": [
                "user-managed lawful authorization",
                "dedicated browser profile",
                "session-scoped download behavior",
                "bounded wait for a download event",
                "PDF signature and content-type validation",
                "existing ingest/cache call",
                "preference restoration or recorded restoration status",
            ],
        },
        "privacy": {
            "signed_url_queries": "removed",
            "session_ids": "omitted",
            "browser_profile_paths": "redacted",
            "devtools_metadata": "omitted",
        },
    }


def render_compact_status_markdown(state: dict[str, Any]) -> str:
    summary = state.get("summary") or {}
    lines = [
        "# Literature Acquisition Status",
        "",
        f"Status: `{state.get('status')}` | ready: {summary.get('ready_count', 0)}/{summary.get('target_count', 0)} | blocked: {summary.get('blocked_count', 0)}",
        "",
        "| Title | DOI | Status | Reason | Next action |",
        "|---|---|---|---|---|",
    ]
    for item in state.get("targets") or []:
        values = [
            item.get("title") or "Untitled",
            item.get("doi") or "not_reported",
            item.get("status") or "not_attempted",
            item.get("blocked_reason") or "-",
            item.get("next_action") or "-",
        ]
        lines.append("| " + " | ".join(str(value).replace("|", "\\|").replace("\n", " ") for value in values) + " |")
    lines.extend(
        [
            "",
            "External acquisition remains a companion workflow. EA does not bypass login, subscription, CAPTCHA, SSO, MFA, or publisher controls.",
            "",
        ]
    )
    return "\n".join(lines)
