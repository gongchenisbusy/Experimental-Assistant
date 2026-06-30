from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import yaml

from ea.release_package import FIXED_ZIP_TIMESTAMP, main, verify_main, verify_release_package, write_release_package
from test_release_manifest import _minimal_release_root


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rewrite_zip(path: Path, replacements: dict[str, bytes] | None = None, *, skip_suffix: str | None = None) -> None:
    replacements = replacements or {}
    source = path.with_suffix(".rewrite.zip")
    path.replace(source)
    with zipfile.ZipFile(source) as old_archive, zipfile.ZipFile(path, "w") as new_archive:
        for info in old_archive.infolist():
            if skip_suffix and info.filename.endswith(skip_suffix):
                continue
            data = replacements.get(info.filename, old_archive.read(info.filename))
            new_info = zipfile.ZipInfo(info.filename)
            new_info.date_time = info.date_time
            new_info.compress_type = info.compress_type
            new_info.external_attr = info.external_attr
            new_archive.writestr(new_info, data)
    source.unlink()


def test_release_package_writes_zip_manifest_and_checksum_sidecar(tmp_path: Path) -> None:
    root = _minimal_release_root(tmp_path)

    result = write_release_package(root, output=Path("dist/release.zip"), archive_root="ea-release")
    archive_path = Path(result["archive_path"])
    checksum_path = Path(result["archive_checksum_path"])

    assert archive_path.exists()
    assert checksum_path.read_text(encoding="utf-8").split()[0] == _sha256(archive_path)
    assert result["archive_sha256"] == _sha256(archive_path)
    assert result["manifest_archive_ref"] == "ea-release/ea-v0.2-release-manifest.yml"

    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert "ea-release/ea-v0.2-release-manifest.yml" in names
        assert "ea-release/README.md" in names
        assert "ea-release/docs/PUBLIC_ONBOARDING.md" in names
        assert "ea-release/docs/RELEASE_VERIFICATION.md" in names
        assert "ea-release/docs/PROJECT_BUNDLE_VERIFICATION.md" in names
        assert "ea-release/pyproject.toml" in names
        assert "ea-release/src/ea/__init__.py" in names
        assert "ea-release/src/ea/__pycache__/ignored.pyc" not in names
        assert "ea-release/dist/ignored.yml" not in names
        assert all(info.date_time == FIXED_ZIP_TIMESTAMP for info in archive.infolist())
        manifest = yaml.safe_load(archive.read("ea-release/ea-v0.2-release-manifest.yml"))

    assert manifest["manifest_type"] == "ea_v0_2_repository_release"
    assert manifest["package"]["console_scripts"]["ea-release-package"] == "ea.release_package:main"


def test_release_package_is_deterministic_for_same_inputs(tmp_path: Path) -> None:
    root = _minimal_release_root(tmp_path)

    first = write_release_package(root, output=Path("dist/first.zip"), archive_root="ea-release")
    second = write_release_package(root, output=Path("dist/second.zip"), archive_root="ea-release")

    assert first["archive_sha256"] == second["archive_sha256"]


def test_release_package_cli_writes_summary_json(tmp_path: Path, capsys) -> None:
    root = _minimal_release_root(tmp_path)

    exit_code = main(["--root", str(root), "--output", "dist/cli-release.zip", "--archive-root", "ea-release"])
    summary = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert summary["status"] == "complete"
    assert Path(summary["archive_path"]).exists()
    assert Path(summary["archive_checksum_path"]).exists()
    assert summary["package"] == {"name": "ea-v0-2", "version": "0.2.0"}


def test_release_package_verifier_passes_for_valid_package(tmp_path: Path) -> None:
    root = _minimal_release_root(tmp_path)
    package = write_release_package(root, output=Path("dist/release.zip"), archive_root="ea-release")

    result = verify_release_package(Path(package["archive_path"]))

    assert result["status"] == "pass"
    assert result["manifest_archive_ref"] == "ea-release/ea-v0.2-release-manifest.yml"
    assert result["checked_count"] == package["file_count"]
    assert result["failures"] == []


def test_release_package_verifier_reports_missing_sidecar(tmp_path: Path) -> None:
    root = _minimal_release_root(tmp_path)
    package = write_release_package(root, output=Path("dist/release.zip"), archive_root="ea-release")
    Path(package["archive_checksum_path"]).unlink()

    result = verify_release_package(Path(package["archive_path"]))

    assert result["status"] == "fail"
    assert {"path": package["archive_checksum_path"], "reason": "missing_checksum_sidecar"} in result["failures"]


def test_release_package_verifier_reports_archive_hash_mismatch(tmp_path: Path) -> None:
    root = _minimal_release_root(tmp_path)
    package = write_release_package(root, output=Path("dist/release.zip"), archive_root="ea-release")
    Path(package["archive_checksum_path"]).write_text("0" * 64 + "  release.zip\n", encoding="utf-8")

    result = verify_release_package(Path(package["archive_path"]))

    assert result["status"] == "fail"
    assert any(failure["reason"] == "sha256_mismatch" and failure["path"] == "release.zip" for failure in result["failures"])


def test_release_package_verifier_reports_missing_embedded_manifest(tmp_path: Path) -> None:
    root = _minimal_release_root(tmp_path)
    package = write_release_package(root, output=Path("dist/release.zip"), archive_root="ea-release")
    archive_path = Path(package["archive_path"])
    _rewrite_zip(archive_path, skip_suffix="ea-v0.2-release-manifest.yml")
    Path(package["archive_checksum_path"]).write_text(_sha256(archive_path) + "  release.zip\n", encoding="utf-8")

    result = verify_release_package(archive_path)

    assert result["status"] == "fail"
    assert {"path": "ea-v0.2-release-manifest.yml", "reason": "missing_embedded_manifest"} in result["failures"]


def test_release_package_verifier_reports_payload_mismatch(tmp_path: Path) -> None:
    root = _minimal_release_root(tmp_path)
    package = write_release_package(root, output=Path("dist/release.zip"), archive_root="ea-release")
    archive_path = Path(package["archive_path"])
    _rewrite_zip(archive_path, {"ea-release/README.md": b"# tampered\n"})
    Path(package["archive_checksum_path"]).write_text(_sha256(archive_path) + "  release.zip\n", encoding="utf-8")

    result = verify_release_package(archive_path)

    assert result["status"] == "fail"
    assert any(failure["path"] == "ea-release/README.md" and failure["reason"] == "size_mismatch" for failure in result["failures"])
    assert any(failure["path"] == "ea-release/README.md" and failure["reason"] == "sha256_mismatch" for failure in result["failures"])


def test_release_package_verify_cli_returns_nonzero_on_failure(tmp_path: Path, capsys) -> None:
    root = _minimal_release_root(tmp_path)
    package = write_release_package(root, output=Path("dist/release.zip"), archive_root="ea-release")
    Path(package["archive_checksum_path"]).write_text("bad  release.zip\n", encoding="utf-8")

    exit_code = verify_main([package["archive_path"]])
    summary = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert summary["status"] == "fail"
