from __future__ import annotations

import json
import platform
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

from ea import __version__
from ea.identity import DISTRIBUTION_NAME, RELEASE_LABEL, SKILL_INVOCATION
from ea.storage.files import atomic_write_text, read_yaml


FORBIDDEN_PARTS = {
    "raw",
    "processed",
    "fulltext",
    "credentials",
    "cookies",
    "browser-profiles",
    "browser_profiles",
}
TOKEN_PATTERN = re.compile(
    r"(?i)(?P<label>token|password|secret|cookie|authorization|api[_-]?key|session[_-]?id)\s*[:=]\s*(?P<value>[^\s,;]+)"
)
HOME_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?:/Users/[^/\s]+|/home/[^/\s]+|[A-Za-z]:\\Users\\[^\\\s]+)(?:[/\\][^\s,;]+)*"
)
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
URL_PATTERN = re.compile(r"https?://[^\s'\"]+")


def _safe_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "[redacted-url]"
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def redact_diagnostic_text(value: str) -> str:
    text = TOKEN_PATTERN.sub(lambda match: f"{match.group('label')}=[REDACTED]", value)
    text = URL_PATTERN.sub(lambda match: _safe_url(match.group(0)), text)
    text = HOME_PATH_PATTERN.sub("[LOCAL_PATH]", text)
    text = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
    return text


def _safe_yaml(path: Path, counters: dict[str, int]) -> dict[str, Any]:
    if not path.is_file():
        return {}
    counters["files_read"] += 1
    counters["bytes_read"] += path.stat().st_size
    try:
        return read_yaml(path)
    except (OSError, ValueError):
        return {}


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return f"selected-log/{path.name}"


def _selected_log(root: Path, path: Path, counters: dict[str, int]) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    parts = {part.lower() for part in resolved.parts}
    if parts & FORBIDDEN_PARTS or any(
        term in resolved.name.lower() for term in ("cookie", "credential", "secret")
    ):
        raise PermissionError(
            f"Diagnostics refuses sensitive or research-data path: {resolved.name}"
        )
    if resolved.suffix.lower() not in {".log", ".txt", ".json"}:
        raise ValueError(
            f"Selected diagnostic log must be .log, .txt, or .json: {resolved.name}"
        )
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    raw = resolved.read_text(encoding="utf-8", errors="replace")[:65536]
    counters["files_read"] += 1
    counters["bytes_read"] += min(resolved.stat().st_size, 65536)
    return {
        "ref": _relative(root, resolved),
        "bytes_sampled": len(raw.encode("utf-8")),
        "redacted_excerpt": redact_diagnostic_text(raw),
    }


def collect_diagnostics(
    root: Path,
    *,
    selected_logs: Iterable[Path] = (),
    output_path: Path | None = None,
    debug_json: bool = False,
    collected_at: str | None = None,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if not (root / "EA_PROJECT.md").is_file():
        raise FileNotFoundError(root / "EA_PROJECT.md")
    if debug_json and output_path is None:
        raise ValueError("--debug-json requires an explicit local --output path")
    collected_at = collected_at or datetime.now(timezone.utc).isoformat()
    counters = {"files_read": 0, "bytes_read": 0}
    project_format = _safe_yaml(root / ".ea" / "project_format.yml", counters)
    operations: list[dict[str, Any]] = []
    for path in sorted(
        (root / ".ea" / "operations").glob("*.yml"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )[:10]:
        record = _safe_yaml(path, counters)
        operations.append(
            {
                "ref": _relative(root, path),
                "operation": record.get("operation"),
                "status": record.get("status"),
                "error_type": (record.get("error") or {}).get("type")
                if isinstance(record.get("error"), dict)
                else None,
            }
        )
    evaluations: list[dict[str, Any]] = []
    for path in sorted(
        (root / "evaluation").glob("*.yml"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )[:3]:
        record = _safe_yaml(path, counters)
        evaluations.append(
            {
                "ref": _relative(root, path),
                "status": record.get("status"),
                "error_count": record.get("error_count", 0),
                "warning_count": record.get("warning_count", 0),
            }
        )
    external = _safe_yaml(
        root / "literature" / "external_acquisition_state.yml", counters
    )
    external_summary = external.get("summary") or {}
    logs = [
        _selected_log(root, path if path.is_absolute() else root / path, counters)
        for path in selected_logs
    ]
    failure_count = sum(item.get("status") == "failed" for item in operations) + sum(
        int(item.get("error_count") or 0) for item in evaluations
    )
    debug_payload = {
        "schema_version": "1.0",
        "collected_at": collected_at,
        "identity": {
            "version": __version__,
            "release": RELEASE_LABEL,
            "distribution": DISTRIBUTION_NAME,
            "skill": SKILL_INVOCATION,
            "python": platform.python_version(),
            "platform": platform.system(),
        },
        "project": {
            "project_format_version": project_format.get("project_format_version"),
            "operation_count": len(operations),
            "failed_operation_count": sum(
                item.get("status") == "failed" for item in operations
            ),
            "evaluation_count": len(evaluations),
        },
        "operations": operations,
        "evaluations": evaluations,
        "literature_acquisition": {
            "external_cache_used": bool(external_summary.get("ready_count")),
            "ready_count": external_summary.get("ready_count", 0),
            "blocked_count": external_summary.get("blocked_count", 0),
            "current_task_blocker_count": len(
                external.get("current_task_blockers") or []
            ),
        },
        "selected_logs": logs
        if debug_json
        else [
            {"ref": item["ref"], "bytes_sampled": item["bytes_sampled"]}
            for item in logs
        ],
        "exclusions": [
            "raw research data",
            "processed scientific data",
            "credentials and cookies",
            "browser profiles and institution sessions",
            "Zotero secrets",
            "private PDFs and full text",
        ],
        "submission": {
            "performed": False,
            "requires_separate_preview_and_confirmation": True,
        },
        "feedback_suggestion": "Consider the read-only ea-feedback skill after repeated failures or explicit user dissatisfaction."
        if failure_count
        else None,
    }
    serialized = json.dumps(debug_payload, ensure_ascii=False, indent=2)
    counters.update(
        {
            "artifact_count": 1 if output_path else 0,
            "artifact_bytes": len(serialized.encode("utf-8")) if output_path else 0,
            "estimated_context_range": "small"
            if counters["bytes_read"] < 100_000
            else "moderate",
            "exact_model_tokens_available": False,
        }
    )
    debug_payload["context_cost_proxy"] = counters
    artifact_ref = None
    if output_path:
        destination = output_path if output_path.is_absolute() else root / output_path
        atomic_write_text(
            destination, json.dumps(debug_payload, ensure_ascii=False, indent=2) + "\n"
        )
        artifact_ref = _relative(root, destination)
    return {
        "status": "attention" if failure_count else "ready",
        "version": __version__,
        "failed_operation_count": debug_payload["project"]["failed_operation_count"],
        "evaluation_error_count": sum(
            int(item.get("error_count") or 0) for item in evaluations
        ),
        "external_literature_ready_count": debug_payload["literature_acquisition"][
            "ready_count"
        ],
        "selected_log_count": len(logs),
        "context_cost_proxy": counters,
        "diagnostics_ref": artifact_ref,
        "submission_performed": False,
        "next_steps": [
            "Inspect the local diagnostics artifact."
            if artifact_ref
            else "Add --output to write a local redacted artifact.",
            "Use ea-feedback only after review; submission remains a separate confirmed action.",
        ],
    }
