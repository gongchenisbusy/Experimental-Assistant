from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import yaml

from ea.release_package import FIXED_ZIP_TIMESTAMP, main, write_release_package
from test_release_manifest import _minimal_release_root


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
