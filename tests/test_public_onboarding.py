from __future__ import annotations

from pathlib import Path

from ea.release_manifest import build_release_manifest


ONBOARDING_PATH = Path("docs/PUBLIC_ONBOARDING.md")
FORBIDDEN_PUBLIC_DEFAULTS = [
    "/Users/geecoe",
    "New project 4",
    "zotero.sqlite",
    "Chrome Profile",
    "institution password",
]


def test_public_onboarding_doc_is_public_safe_and_actionable() -> None:
    text = ONBOARDING_PATH.read_text(encoding="utf-8")

    assert "# EA v0.2 Public Onboarding" in text
    assert "ea init-project" in text
    assert "ea healthcheck" in text
    assert "ea eval project" in text
    assert "ea trace view" in text
    assert "ea literature plan" in text
    assert "ea literature prepare-source-candidates" in text
    assert "ea literature preflight-source-candidates" in text
    assert "open-items/" in text
    assert "--enable-literature" in text
    assert "ea export report-bundle" in text
    assert "ea-public-release-smoke" in text
    assert "developer-machine assumptions" in text
    for forbidden in FORBIDDEN_PUBLIC_DEFAULTS:
        assert forbidden not in text


def test_public_onboarding_doc_is_in_default_release_inputs() -> None:
    manifest = build_release_manifest(Path.cwd())
    paths = {record["path"] for record in manifest["release_inputs"]["files"]}

    assert ONBOARDING_PATH.as_posix() in paths
