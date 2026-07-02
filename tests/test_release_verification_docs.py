from __future__ import annotations

import zipfile
from pathlib import Path

from ea.release_manifest import build_release_manifest
from ea.release_package import write_release_package


VERIFICATION_DOC = Path("docs/RELEASE_VERIFICATION.md")
FORBIDDEN_PUBLIC_DEFAULTS = [
    "/Users/geecoe",
    "New project 4",
    "zotero.sqlite",
    "Chrome Profile",
    "institution password",
]


def test_release_verification_doc_is_public_safe_and_actionable() -> None:
    text = VERIFICATION_DOC.read_text(encoding="utf-8")

    assert "# EA v0.9 Release Candidate Verification" in text
    assert "ea-public-release-smoke" in text
    assert "ea-release-manifest" in text
    assert "ea-release-package" in text
    assert "ea-verify-release-package" in text
    assert "ea-verify-release-signature" in text
    assert "ea-release-checklist" in text
    assert "https://github.com/gongchenisbusy/Experimental-Assistant" in text
    assert "https://github.com/gongchenisbusy/Experimental-Assistant/releases/tag/v0.9-rc1" in text
    assert "What Each Check Proves" in text
    assert "sensitive-value scan" in text
    assert "Scope Limits" in text
    for forbidden in FORBIDDEN_PUBLIC_DEFAULTS:
        assert forbidden not in text


def test_release_verification_doc_is_in_default_release_inputs_and_package(tmp_path: Path) -> None:
    manifest = build_release_manifest(Path.cwd())
    paths = {record["path"] for record in manifest["release_inputs"]["files"]}
    assert VERIFICATION_DOC.as_posix() in paths

    package = write_release_package(Path.cwd(), output=tmp_path / "release.zip", archive_root="ea-release-doc-test")
    with zipfile.ZipFile(package["archive_path"]) as archive:
        assert "ea-release-doc-test/docs/RELEASE_VERIFICATION.md" in archive.namelist()
