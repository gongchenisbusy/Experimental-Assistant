from __future__ import annotations

import errno
from pathlib import Path
from typing import Any


class ReviewRequiredError(ValueError):
    """Raised when reviewed-only output is requested before review exists."""


def _error_details(exc: BaseException) -> tuple[str, str, bool, list[str]]:
    if isinstance(exc, ReviewRequiredError):
        return (
            "EA-REVIEW-REQUIRED",
            "Reviewed evidence is required before this downstream action.",
            False,
            [
                "Run the relevant `ea literature data-review` command, then validate the reviewed dataset."
            ],
        )
    if isinstance(exc, IsADirectoryError):
        return (
            "EA-IO-PATH-NOT-FILE",
            "A file was required but the path is a directory.",
            False,
            ["Choose an existing regular file and retry."],
        )
    if isinstance(exc, FileNotFoundError):
        return (
            "EA-IO-NOT-FOUND",
            "A required file or directory was not found.",
            False,
            ["Check the path and run the related status or preview command again."],
        )
    if isinstance(exc, PermissionError):
        return (
            "EA-IO-PERMISSION-DENIED",
            "The operating system denied access.",
            True,
            [
                "Check file permissions or sandbox policy; do not treat this as proof that companion software is stopped."
            ],
        )
    if isinstance(exc, ConnectionRefusedError):
        return (
            "EA-INTEGRATION-CONNECTION-REFUSED",
            "A local integration refused the connection.",
            True,
            ["Verify the configured endpoint and that the integration is running."],
        )
    if isinstance(exc, TimeoutError):
        return (
            "EA-OPERATION-TIMEOUT",
            "The operation timed out.",
            True,
            ["Inspect current operation status before retrying."],
        )
    if isinstance(exc, KeyError):
        return (
            "EA-SCHEMA-MISSING-FIELD",
            "A required record field is missing.",
            False,
            ["Validate or migrate the project record before retrying."],
        )
    if isinstance(exc, ValueError):
        return (
            "EA-INPUT-INVALID",
            "The supplied value or record is invalid.",
            False,
            ["Review the command input and use a preview or dry-run command first."],
        )
    if isinstance(exc, OSError):
        if exc.errno in {errno.EPERM, errno.EACCES}:
            return (
                "EA-IO-PERMISSION-DENIED",
                "The operating system denied access.",
                True,
                ["Check permissions or sandbox policy before retrying."],
            )
        if exc.errno == errno.ECONNREFUSED:
            return (
                "EA-INTEGRATION-CONNECTION-REFUSED",
                "A local integration refused the connection.",
                True,
                ["Verify the configured endpoint and that the integration is running."],
            )
        if exc.errno == errno.ETIMEDOUT:
            return (
                "EA-INTEGRATION-TIMEOUT",
                "An integration request timed out.",
                True,
                ["Check current-task status and retry only the affected target."],
            )
        return (
            "EA-IO-ERROR",
            "An operating-system operation failed.",
            True,
            ["Inspect the local debug log or diagnostics bundle before retrying."],
        )
    if isinstance(exc, RuntimeError):
        return (
            "EA-OPERATION-FAILED",
            "The requested operation failed.",
            False,
            ["Inspect the operation journal and follow its recovery action."],
        )
    return (
        "EA-UNEXPECTED-ERROR",
        "EA encountered an unexpected error.",
        False,
        ["Collect a local redacted diagnostics bundle before reporting the problem."],
    )


def error_record(
    exc: BaseException,
    *,
    artifacts_written: list[str] | None = None,
    debug_log_ref: Path | str | None = None,
) -> dict[str, Any]:
    code, summary, safe_to_retry, next_steps = _error_details(exc)
    return {
        "status": "error",
        "code": code,
        "summary": summary,
        "cause": {"type": type(exc).__name__, "message": str(exc)},
        "safe_to_retry": safe_to_retry,
        "artifacts_written": list(artifacts_written or []),
        "next_steps": next_steps,
        "debug_log_ref": str(debug_log_ref) if debug_log_ref else None,
    }
