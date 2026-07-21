from __future__ import annotations

import zipfile
from pathlib import Path

from ea.cli import build_parser
from ea.release_manifest import build_release_manifest
from ea.release_package import write_release_package


CURRENT_RELEASE_DOCS = [
    Path("docs/PUBLIC_ACCEPTANCE_MATRIX.md"),
    Path("docs/V1_1_RELEASE_NOTES.md"),
    Path("docs/V1_1_KNOWN_LIMITATIONS.md"),
    Path("docs/V1_1_TRIAL_REPORT.md"),
    Path("docs/V1_1_RELEASE_DOSSIER.md"),
    Path("docs/V1_1_ISSUE_DISPOSITION.md"),
]
HISTORICAL_V0_9_9_DOCS = [
    Path("docs/V0_9_9_RELEASE_NOTES.md"),
    Path("docs/V0_9_9_TRIAL_REPORT.md"),
    Path("docs/V0_9_9_ISSUE_DISPOSITION.md"),
    Path("docs/V1_0_READINESS_DOSSIER.md"),
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
    Path("skills/ea/SKILL.md"),
    Path("skills/ea/references/evaluator-workflow.md"),
    Path("skills/ea/references/project-workflow.md"),
    Path("skills/ea/references/release-workflow.md"),
    Path("skills/ea/references/raman-workflow.md"),
    Path("skills/ea/references/pl-workflow.md"),
    Path("skills/ea/references/xrd-workflow.md"),
    Path("skills/ea/references/ftir-workflow.md"),
    Path("skills/ea/references/uv-vis-workflow.md"),
    Path("skills/ea/references/xps-workflow.md"),
    Path("skills/ea/references/electrochemistry-workflow.md"),
    Path("skills/ea/references/thermal-workflow.md"),
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


def test_v1_release_docs_are_public_safe_and_actionable() -> None:
    text_by_path = {
        path: path.read_text(encoding="utf-8") for path in CURRENT_RELEASE_DOCS
    }

    assert "Experimental Assistant v1.1.0 Public Acceptance Matrix" in text_by_path[
        Path("docs/PUBLIC_ACCEPTANCE_MATRIX.md")
    ]
    assert "Experimental Assistant v1.1.0 Release Notes" in text_by_path[
        Path("docs/V1_1_RELEASE_NOTES.md")
    ]
    assert "Scientific boundaries" in text_by_path[
        Path("docs/V1_1_KNOWN_LIMITATIONS.md")
    ]
    assert "Candidate Trial Report" in text_by_path[
        Path("docs/V1_1_TRIAL_REPORT.md")
    ]
    assert "Release Dossier" in text_by_path[
        Path("docs/V1_1_RELEASE_DOSSIER.md")
    ]
    assert "Issue Disposition" in text_by_path[
        Path("docs/V1_1_ISSUE_DISPOSITION.md")
    ]

    combined = "\n".join(text_by_path.values())
    assert "ea export report-bundle" in combined
    assert "ea export verify-archive" in combined
    assert "ea literature zotero-readiness" in combined
    assert "ea-public-release-smoke" in combined
    for forbidden in FORBIDDEN_PUBLIC_DEFAULTS:
        assert forbidden not in combined


def test_v0_9_9_release_records_remain_historical() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in HISTORICAL_V0_9_9_DOCS
    )

    assert "Experimental Assistant v0.9.9" in combined
    assert "release_candidate: v0.9.9" in Path(
        "docs/V1_0_READINESS_DOSSIER.yml"
    ).read_text(encoding="utf-8")
    assert "literature-pipeline-v0.9.9" in Path(
        "benchmarks/literature-v0.9.9.yml"
    ).read_text(encoding="utf-8")


def test_v1_public_version_surfaces_do_not_look_like_v0_2_release() -> None:
    parser_help = build_parser().format_help()
    assert "init-project" in parser_help
    assert "initialize a public-user Experimental Assistant v1.1.0" in parser_help
    assert "project workspace" in parser_help

    combined = "\n".join(path.read_text(encoding="utf-8") for path in PUBLIC_VERSION_SURFACES)
    assert "single Codex skill" in combined
    assert "retired Compatibility skill" in combined
    for phrase in CONFUSING_CURRENT_VERSION_PHRASES:
        assert phrase not in combined


def test_v1_release_docs_are_packaged(tmp_path: Path) -> None:
    manifest = build_release_manifest(Path.cwd())
    paths = {record["path"] for record in manifest["release_inputs"]["files"]}
    for doc in CURRENT_RELEASE_DOCS:
        assert doc.as_posix() in paths

    assert manifest["release"]["label"] == "v1.1.0"
    assert manifest["release"]["acceptance_matrix_ref"] == "docs/PUBLIC_ACCEPTANCE_MATRIX.md"
    assert manifest["release"]["release_notes_ref"] == "docs/V1_1_RELEASE_NOTES.md"
    assert manifest["release"]["release_dossier_ref"] == "docs/V1_1_RELEASE_DOSSIER.yml"
    assert manifest["public_repository"]["project_name"] == "Experimental Assistant (EA)"
    assert manifest["public_repository"]["repository_full_name"] == "gongchenisbusy/Experimental-Assistant"
    assert manifest["public_repository"]["release_url"].endswith(
        "/releases/tag/v1.1.0"
    )

    package = write_release_package(Path.cwd(), output=tmp_path / "release.zip", archive_root="ea-release-doc-test")
    with zipfile.ZipFile(package["archive_path"]) as archive:
        names = set(archive.namelist())

    for doc in CURRENT_RELEASE_DOCS:
        assert f"ea-release-doc-test/{doc.as_posix()}" in names
