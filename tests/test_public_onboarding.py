from __future__ import annotations

from pathlib import Path

from ea.release_manifest import build_release_manifest


ONBOARDING_PATH = Path("docs/PUBLIC_ONBOARDING.md")
INSTALL_SKILL_SETUP_PATH = Path("docs/PUBLIC_INSTALL_AND_CODEX_SKILL_SETUP.md")
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
    assert "docs/PUBLIC_INSTALL_AND_CODEX_SKILL_SETUP.md" in text
    assert "ea init-project" in text
    assert "ea healthcheck" in text
    assert "ea eval project" in text
    assert "ea brief project" in text
    assert "ea trace view" in text
    assert "ea literature plan" in text
    assert "ea literature prepare-source-candidates" in text
    assert "ea literature preflight-source-candidates" in text
    assert "ea literature acceptance-checklist" in text
    assert "ea materials audit-assignment-library" in text
    assert "ea raman list-assignment-libraries" in text
    assert "ea pl list-assignment-libraries" in text
    assert "ea xrd list-assignment-libraries" in text
    assert "ea xrd build-assignment-packet" in text
    assert "ea xrd suggest-assignments" in text
    assert "ea xrd prepare-review" in text
    assert "ea xrd report --assignment-suggestion" in text
    assert "--assignment-review-ref" in text
    assert "ea ftir list-assignment-libraries" in text
    assert "ea uv-vis list-source-libraries" in text
    assert "ea xps list-parameter-libraries" in text
    assert "open-items/" in text
    assert "--enable-literature" in text
    assert "ea export report-bundle" in text
    assert "--include-trace" in text
    assert "focused report traceability YAML/Markdown" in text
    assert "ea-public-release-smoke" in text
    assert "credential-like values" in text
    assert "developer-machine assumptions" in text
    assert "examples/public-xps-be-project" in text
    assert "examples/public-uv-vis-project" in text
    assert "EA may help gather or suggest source-backed XPS endpoints" in text
    assert "只接受用户明确给出的能量差" not in text
    for forbidden in FORBIDDEN_PUBLIC_DEFAULTS:
        assert forbidden not in text


def test_public_install_and_skill_setup_doc_is_public_safe_and_actionable() -> None:
    text = INSTALL_SKILL_SETUP_PATH.read_text(encoding="utf-8")

    assert "# EA Public Install And Codex Skill Setup" in text
    assert "git clone https://github.com/OWNER/REPOSITORY.git ea" in text
    assert "python3 -m pip install -e ." in text
    assert 'python3 -m pip install -e ".[dev]"' in text
    assert "ea --help" in text
    assert "CODEX_HOME" in text
    assert "cp -R skills/ea-v0-2" in text
    assert "quick_validate.py" in text
    assert "ea healthcheck examples/public-raman-project" in text
    assert "ea eval project examples/public-xps-be-project --no-write" in text
    assert "ordinary user install" in text.lower()
    assert "developer install" in text.lower()
    assert "local integration tests" in text.lower()
    assert "must not search for private keys" in text
    assert "must not inherit a developer machine" in text
    for forbidden in FORBIDDEN_PUBLIC_DEFAULTS:
        assert forbidden not in text


def test_public_onboarding_doc_is_in_default_release_inputs() -> None:
    manifest = build_release_manifest(Path.cwd())
    paths = {record["path"] for record in manifest["release_inputs"]["files"]}

    assert ONBOARDING_PATH.as_posix() in paths
    assert INSTALL_SKILL_SETUP_PATH.as_posix() in paths
