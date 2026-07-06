from __future__ import annotations

import json
from pathlib import Path

from ea.release_distribution import build_distribution_checklist, main, render_distribution_markdown, write_distribution_checklist
from ea.release_manifest import write_release_manifest
from ea.release_package import write_release_package
from ea.release_signature import generate_release_keypair, sign_release_package
from test_release_manifest import _minimal_release_root


def test_distribution_checklist_reports_missing_artifacts(tmp_path: Path) -> None:
    root = _minimal_release_root(tmp_path)

    checklist = build_distribution_checklist(root)

    assert checklist["status"] == "fail"
    failure_codes = {failure["code"] for failure in checklist["failures"]}
    assert "release_manifest.file_present" in failure_codes
    assert "release_package.archive_present" in failure_codes


def test_distribution_checklist_passes_for_manifest_and_package(tmp_path: Path) -> None:
    root = _minimal_release_root(tmp_path)
    write_release_manifest(root)
    package = write_release_package(root, output=Path("dist/release.zip"), archive_root="ea-release")

    checklist = build_distribution_checklist(root)

    assert checklist["status"] == "pass"
    assert checklist["release_artifacts"]["manifest"]["exists"] is True
    assert checklist["release_artifacts"]["archives"][0]["path"] == "dist/release.zip"
    assert checklist["release_artifacts"]["archives"][0]["verification"]["status"] == "pass"
    assert checklist["release_artifacts"]["archives"][0]["signature"]["status"] == "not_present"
    assert "ea-release-checklist" in checklist["recommended_handoff_commands"]
    assert Path(package["archive_path"]).exists()


def test_distribution_checklist_prefers_current_version_archives(tmp_path: Path) -> None:
    root = _minimal_release_root(tmp_path)
    write_release_manifest(root)
    package = write_release_package(root)
    old_archive = root / "dist" / "ea-v0-2-0.2.0-old-release.zip"
    old_archive.write_bytes(b"not a current release package")

    checklist = build_distribution_checklist(root)

    assert checklist["status"] == "pass"
    archives = checklist["release_artifacts"]["archives"]
    assert [archive["path"] for archive in archives] == [Path(package["archive_path"]).relative_to(root).as_posix()]


def test_distribution_checklist_verifies_optional_signature_when_public_key_is_supplied(tmp_path: Path) -> None:
    root = _minimal_release_root(tmp_path / "repo")
    write_release_manifest(root)
    package = write_release_package(root, output=Path("dist/release.zip"), archive_root="ea-release")
    private_key = tmp_path / "release-private.pem"
    public_key = tmp_path / "release-public.pem"
    generate_release_keypair(private_key_path=private_key, public_key_path=public_key)
    sign_release_package(Path(package["archive_path"]), private_key_path=private_key, public_key_path=public_key)

    checklist = build_distribution_checklist(root, public_key_path=public_key)

    assert checklist["status"] == "pass"
    signature = checklist["release_artifacts"]["archives"][0]["signature"]
    assert signature["status"] == "pass"
    assert signature["verification"]["status"] == "pass"


def test_distribution_checklist_cli_writes_json_and_markdown(tmp_path: Path, capsys) -> None:
    root = _minimal_release_root(tmp_path)
    write_release_manifest(root)
    write_release_package(root, output=Path("dist/release.zip"), archive_root="ea-release")

    exit_code = main(["--root", str(root), "--output-json", "dist/checklist.json", "--output-md", "dist/checklist.md"])
    summary = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert summary["status"] == "pass"
    assert Path(summary["json_path"]).exists()
    assert Path(summary["markdown_path"]).exists()
    assert "Experimental Assistant v0.9.6 Distribution Checklist" in Path(summary["markdown_path"]).read_text(encoding="utf-8")


def test_distribution_checklist_markdown_includes_required_checks(tmp_path: Path) -> None:
    root = _minimal_release_root(tmp_path)
    write_release_manifest(root)
    write_release_package(root, output=Path("dist/release.zip"), archive_root="ea-release")

    checklist = build_distribution_checklist(root)
    markdown = render_distribution_markdown(checklist)

    assert "- [x] `git.clean_worktree`" in markdown
    assert "ea-verify-release-package <release.zip>" in markdown


def test_write_distribution_checklist_returns_paths_and_payload(tmp_path: Path) -> None:
    root = _minimal_release_root(tmp_path)
    write_release_manifest(root)
    write_release_package(root, output=Path("dist/release.zip"), archive_root="ea-release")

    json_path, md_path, checklist = write_distribution_checklist(root, output_json=Path("dist/out.json"), output_md=Path("dist/out.md"))

    assert json_path == root / "dist" / "out.json"
    assert md_path == root / "dist" / "out.md"
    assert checklist["status"] == "pass"
