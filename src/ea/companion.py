from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from ea.identity import RELEASE_LABEL

EA_FEEDBACK_ACCEPTED_COMMIT = "5fd37ea6770d66b3dc8837a095710e1201c39156"


def inspect_ea_feedback_companion(codex_home: Path) -> dict[str, Any]:
    path = codex_home / "skills" / "ea-feedback"
    base: dict[str, Any] = {
        "name": "companion:ea-feedback",
        "required": False,
        "path": str(path),
        "expected_commit": EA_FEEDBACK_ACCEPTED_COMMIT,
    }
    if not (path / "SKILL.md").is_file():
        return {
            **base,
            "status": "inactive",
            "code": "EA-COMPANION-FEEDBACK-NOT-INSTALLED",
            "message": "Optional ea-feedback companion is not installed.",
            "next_steps": [],
        }
    if not (path / ".git").exists():
        return {
            **base,
            "status": "warning",
            "detected_commit": None,
            "code": "EA-COMPANION-FEEDBACK-VERSION-UNVERIFIABLE",
            "message": "ea-feedback is installed, but its accepted commit cannot be verified.",
            "next_steps": [
                "Install the ea-feedback companion from the commit pinned in companion-compatibility.yml."
            ],
        }
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
        check=False,
    )
    detected = (
        completed.stdout.decode("utf-8", errors="replace").strip()
        if completed.returncode == 0
        else None
    )
    matches = detected == EA_FEEDBACK_ACCEPTED_COMMIT
    return {
        **base,
        "status": "pass" if matches else "warning",
        "detected_commit": detected,
        "code": None if matches else "EA-COMPANION-FEEDBACK-COMMIT-MISMATCH",
        "message": (
            f"ea-feedback commit matches the {RELEASE_LABEL} compatibility manifest."
            if matches
            else f"ea-feedback is installed but does not match the {RELEASE_LABEL} accepted commit."
        ),
        "next_steps": []
        if matches
        else ["Update ea-feedback before treating companion evidence as current."],
    }
