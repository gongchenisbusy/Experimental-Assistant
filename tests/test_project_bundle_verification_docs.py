from __future__ import annotations

import zipfile
from pathlib import Path

from ea.release_manifest import build_release_manifest
from ea.release_package import write_release_package


BUNDLE_DOC = Path("docs/PROJECT_BUNDLE_VERIFICATION.md")
FORBIDDEN_PUBLIC_DEFAULTS = [
    "/Users/geecoe",
    "New project 4",
    "zotero.sqlite",
    "Chrome Profile",
    "institution password",
]


def test_project_bundle_verification_doc_is_public_safe_and_actionable() -> None:
    text = BUNDLE_DOC.read_text(encoding="utf-8")

    assert "# Experimental Assistant v0.9.8 Project Bundle Verification" in text
    assert "ea export report-bundle" in text
    assert "ea export batch-bundle" in text
    assert "ea export verify-bundle" in text
    assert "ea export verify-archive" in text
    assert "bundle_manifest.yml" in text
    assert "batch_bundle_manifest.yml" in text
    assert "bundle_checksums.yml" in text
    assert "--include-trace" in text
    assert "focused traceability YAML/Markdown" in text
    assert "nested_report_focused_trace_views" in text
    assert "provenance" in text
    assert "does not provide a built-in detached signing command for project export bundles" in text
    assert "repository release packages" in text
    for forbidden in FORBIDDEN_PUBLIC_DEFAULTS:
        assert forbidden not in text


def test_project_bundle_verification_doc_is_in_default_release_inputs_and_package(tmp_path: Path) -> None:
    manifest = build_release_manifest(Path.cwd())
    paths = {record["path"] for record in manifest["release_inputs"]["files"]}
    assert BUNDLE_DOC.as_posix() in paths

    package = write_release_package(Path.cwd(), output=tmp_path / "release.zip", archive_root="ea-release-doc-test")
    with zipfile.ZipFile(package["archive_path"]) as archive:
        assert "ea-release-doc-test/docs/PROJECT_BUNDLE_VERIFICATION.md" in archive.namelist()
