from __future__ import annotations

import subprocess
from pathlib import Path

from ea.companion import EA_FEEDBACK_ACCEPTED_COMMIT, inspect_ea_feedback_companion
from ea.storage.files import read_yaml


def test_compatibility_manifest_matches_runtime_constant() -> None:
    manifest = read_yaml(Path("skill-registry/companion-compatibility.yml"))

    assert manifest["ea_release"] == "v0.9.9"
    assert (
        manifest["companions"]["ea-feedback"]["accepted_commit"]
        == EA_FEEDBACK_ACCEPTED_COMMIT
    )
    assert manifest["companions"]["zotero-codex-literature"][
        "acquisition_handoff_reader"
    ] == ["1.0", "2.0"]


def test_companion_absence_is_explicit_but_optional(tmp_path: Path) -> None:
    result = inspect_ea_feedback_companion(tmp_path)

    assert result["status"] == "inactive"
    assert result["required"] is False
    assert result.get("detected_commit") is None


def test_mismatched_checkout_is_not_reported_as_current(tmp_path: Path) -> None:
    companion = tmp_path / "skills" / "ea-feedback"
    companion.mkdir(parents=True)
    (companion / "SKILL.md").write_text("# EA Feedback\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=companion, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=companion, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=companion, check=True)
    subprocess.run(["git", "add", "SKILL.md"], cwd=companion, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=companion, check=True)

    result = inspect_ea_feedback_companion(tmp_path)

    assert result["status"] == "warning"
    assert result["code"] == "EA-COMPANION-FEEDBACK-COMMIT-MISMATCH"
    assert result["detected_commit"] != result["expected_commit"]
