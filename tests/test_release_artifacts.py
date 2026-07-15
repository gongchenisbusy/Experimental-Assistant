from __future__ import annotations

import json
import tarfile
import time
from pathlib import Path

from ea.release_artifacts import _install_env, build_install_smoke_report
from ea.release_reproducibility import (
    _sha256,
    canonicalize_sdist,
    compare_build_directories,
)


def test_install_smoke_requires_wheel_and_sdist(monkeypatch, tmp_path: Path) -> None:
    artifacts = [tmp_path / "experimental_assistant-0.9.9-py3-none-any.whl"]
    artifacts[0].write_bytes(b"wheel")
    monkeypatch.setattr(
        "ea.release_artifacts.smoke_install_artifact",
        lambda root, artifact, python_executable: {
            "artifact": artifact.name,
            "artifact_kind": "wheel",
            "status": "pass",
        },
    )

    report = build_install_smoke_report(tmp_path, artifacts=artifacts)

    assert report["status"] == "fail"
    assert report["required_artifact_kinds"] == ["wheel", "sdist"]


def test_artifact_install_uses_absolute_constraint_path(
    monkeypatch, tmp_path: Path
) -> None:
    constraints = tmp_path / "requirements" / "release.txt"
    constraints.parent.mkdir()
    constraints.write_text("build==1.5.1\n", encoding="utf-8")
    monkeypatch.setenv("PIP_CONSTRAINT", "requirements/release.txt")

    env = _install_env(constraints)

    assert env["PIP_CONSTRAINT"] == str(constraints.resolve())


def test_reproducibility_requires_identical_wheel_and_sdist(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    for folder in (first, second):
        (folder / "experimental_assistant-0.9.9-py3-none-any.whl").write_bytes(b"wheel")
        (folder / "experimental_assistant-0.9.9.tar.gz").write_bytes(b"sdist")

    matching = compare_build_directories(first, second, source_date_epoch="123")
    assert matching["status"] == "pass"

    (second / "experimental_assistant-0.9.9.tar.gz").write_bytes(b"changed")
    mismatching = compare_build_directories(first, second, source_date_epoch="123")
    assert mismatching["status"] == "fail"
    assert json.dumps(mismatching)


def test_sdist_canonicalization_removes_archive_time_and_order(tmp_path: Path) -> None:
    source = tmp_path / "payload.txt"
    source.write_bytes(b"same payload\n")
    archives = [tmp_path / "first.tar.gz", tmp_path / "second.tar.gz"]
    for index, archive in enumerate(archives):
        with tarfile.open(archive, "w:gz") as handle:
            info = handle.gettarinfo(source, arcname="package/payload.txt")
            info.mtime = int(time.time()) + index
            with source.open("rb") as payload:
                handle.addfile(info, payload)

    assert _sha256(archives[0]) != _sha256(archives[1])
    for archive in archives:
        canonicalize_sdist(archive, source_date_epoch="123")

    assert _sha256(archives[0]) == _sha256(archives[1])
    with tarfile.open(archives[0], "r:gz") as handle:
        assert handle.extractfile("package/payload.txt").read() == b"same payload\n"
