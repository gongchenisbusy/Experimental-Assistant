from __future__ import annotations

import zipfile
from pathlib import Path

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


def test_v0_9_release_candidate_docs_are_public_safe_and_actionable() -> None:
    text_by_path = {path: path.read_text(encoding="utf-8") for path in RC_DOCS}

    assert "EA v0.9 Public Acceptance Matrix" in text_by_path[Path("docs/PUBLIC_ACCEPTANCE_MATRIX.md")]
    assert "Package version: `0.9.0rc1`" in text_by_path[Path("docs/V0_9_RELEASE_NOTES.md")]
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


def test_v0_9_release_candidate_docs_are_packaged(tmp_path: Path) -> None:
    manifest = build_release_manifest(Path.cwd())
    paths = {record["path"] for record in manifest["release_inputs"]["files"]}
    for doc in RC_DOCS:
        assert doc.as_posix() in paths

    assert manifest["release_candidate"]["label"] == "v0.9-rc1"
    assert manifest["release_candidate"]["acceptance_matrix_ref"] == "docs/PUBLIC_ACCEPTANCE_MATRIX.md"

    package = write_release_package(Path.cwd(), output=tmp_path / "release.zip", archive_root="ea-release-doc-test")
    with zipfile.ZipFile(package["archive_path"]) as archive:
        names = set(archive.namelist())

    for doc in RC_DOCS:
        assert f"ea-release-doc-test/{doc.as_posix()}" in names
