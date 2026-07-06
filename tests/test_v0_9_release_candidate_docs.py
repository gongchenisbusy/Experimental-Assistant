from __future__ import annotations

import zipfile
from pathlib import Path

from ea.cli import build_parser
from ea.release_manifest import build_release_manifest
from ea.release_package import write_release_package


RC_DOCS = [
    Path("docs/PUBLIC_ACCEPTANCE_MATRIX.md"),
    Path("docs/V0_9_RELEASE_NOTES.md"),
    Path("docs/V0_9_KNOWN_LIMITATIONS.md"),
    Path("docs/V0_9_MANUAL_TEST_CHECKLIST.md"),
    Path("docs/V0_9_AGENT_HANDOFF.md"),
]
FORBIDDEN_PUBLIC_DEFAULTS = [
    "/Users/geecoe",
    "New project 4",
    "zotero.sqlite",
    "Chrome Profile",
    "institution password",
]
PUBLIC_VERSION_SURFACES = [
    Path("README.md"),
    Path("docs/PUBLIC_INSTALL_AND_CODEX_SKILL_SETUP.md"),
    Path("docs/PUBLIC_ONBOARDING.md"),
    Path("docs/RELEASE_VERIFICATION.md"),
    Path("docs/PROJECT_BUNDLE_VERIFICATION.md"),
    Path("skills/ea-v0-2/SKILL.md"),
    Path("skills/ea-v0-2/references/evaluator-workflow.md"),
    Path("skills/ea-v0-2/references/project-workflow.md"),
    Path("skills/ea-v0-2/references/release-workflow.md"),
    Path("skills/ea-v0-2/references/raman-workflow.md"),
    Path("skills/ea-v0-2/references/pl-workflow.md"),
    Path("skills/ea-v0-2/references/xrd-workflow.md"),
    Path("skills/ea-v0-2/references/ftir-workflow.md"),
    Path("skills/ea-v0-2/references/uv-vis-workflow.md"),
    Path("skills/ea-v0-2/references/xps-workflow.md"),
    Path("skills/ea-v0-2/references/electrochemistry-workflow.md"),
    Path("skills/ea-v0-2/references/thermal-workflow.md"),
]
CONFUSING_CURRENT_VERSION_PHRASES = [
    "v0.2 project",
    "v0.2 work",
    "EA v0.2 skill",
    "EA v0.2 repository",
    "EA v0.2 public",
    "v0.2 currently",
    "v0.2 behavior",
    "v0.2 workflow",
    "EA-v0.2",
    "not supported by EA v0.2",
    "in EA v0.2",
]


def test_v0_9_release_candidate_docs_are_public_safe_and_actionable() -> None:
    text_by_path = {path: path.read_text(encoding="utf-8") for path in RC_DOCS}

    assert "Experimental Assistant v0.9.6 Public Acceptance Matrix" in text_by_path[Path("docs/PUBLIC_ACCEPTANCE_MATRIX.md")]
    assert "Package version: `0.9.6`" in text_by_path[Path("docs/V0_9_RELEASE_NOTES.md")]
    assert "Relationship To v1.0" in text_by_path[Path("docs/V0_9_RELEASE_NOTES.md")]
    assert "Scientific Boundaries" in text_by_path[Path("docs/V0_9_KNOWN_LIMITATIONS.md")]
    assert "Manual Test Checklist" in text_by_path[Path("docs/V0_9_MANUAL_TEST_CHECKLIST.md")]
    assert "Agent Handoff" in text_by_path[Path("docs/V0_9_AGENT_HANDOFF.md")]

    combined = "\n".join(text_by_path.values())
    assert "ea export report-bundle" in combined
    assert "ea export verify-archive" in combined
    assert "ea literature zotero-readiness" in combined
    assert "ea-public-release-smoke" in combined
    for forbidden in FORBIDDEN_PUBLIC_DEFAULTS:
        assert forbidden not in combined


def test_v0_9_public_version_surfaces_do_not_look_like_v0_2_release() -> None:
    parser_help = build_parser().format_help()
    assert "init-project" in parser_help
    assert "initialize a public-user Experimental Assistant v0.9.6" in parser_help
    assert "project workspace" in parser_help

    combined = "\n".join(path.read_text(encoding="utf-8") for path in PUBLIC_VERSION_SURFACES)
    assert "Naming note" in combined
    assert "compatibility identifier" in combined
    for phrase in CONFUSING_CURRENT_VERSION_PHRASES:
        assert phrase not in combined


def test_v0_9_release_candidate_docs_are_packaged(tmp_path: Path) -> None:
    manifest = build_release_manifest(Path.cwd())
    paths = {record["path"] for record in manifest["release_inputs"]["files"]}
    for doc in RC_DOCS:
        assert doc.as_posix() in paths

    assert manifest["release"]["label"] == "v0.9.6"
    assert manifest["release"]["acceptance_matrix_ref"] == "docs/PUBLIC_ACCEPTANCE_MATRIX.md"
    assert manifest["public_repository"]["project_name"] == "Experimental Assistant (EA)"
    assert manifest["public_repository"]["repository_full_name"] == "gongchenisbusy/Experimental-Assistant"
    assert manifest["public_repository"]["release_url"].endswith("/releases/tag/v0.9.6")

    package = write_release_package(Path.cwd(), output=tmp_path / "release.zip", archive_root="ea-release-doc-test")
    with zipfile.ZipFile(package["archive_path"]) as archive:
        names = set(archive.namelist())

    for doc in RC_DOCS:
        assert f"ea-release-doc-test/{doc.as_posix()}" in names
