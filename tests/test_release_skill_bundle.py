from __future__ import annotations

import hashlib
from pathlib import Path
import zipfile

from ea import __version__
from ea.release_skill_bundle import build_skill_bundle, verify_skill_bundle


def test_skill_bundle_is_compact_deterministic_and_contains_only_primary_skill(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    one = build_skill_bundle(repository_root=Path.cwd(), output_path=first)
    two = build_skill_bundle(repository_root=Path.cwd(), output_path=second)

    assert one["version"] == __version__
    assert one["sha256"] == two["sha256"]
    assert hashlib.sha256(first.read_bytes()).hexdigest() == one["sha256"]
    with zipfile.ZipFile(first) as archive:
        names = set(archive.namelist())
    assert "skills/ea/SKILL.md" in names
    assert not any(name.startswith("skills/ea-v0-2/") for name in names)
    assert one["skills"] == ["ea"]
    assert not any("__pycache__" in name or name.endswith(".pyc") for name in names)
    assert verify_skill_bundle(first)["status"] == "pass"


def test_skill_bundle_verifier_rejects_checksum_mismatch(tmp_path: Path) -> None:
    bundle = tmp_path / "skills.zip"
    build_skill_bundle(repository_root=Path.cwd(), output_path=bundle)
    bundle.with_suffix(".zip.sha256").write_text(
        f"{'0' * 64}  {bundle.name}\n", encoding="utf-8"
    )

    result = verify_skill_bundle(bundle)

    assert result["status"] == "fail"
    assert {failure["reason"] for failure in result["failures"]} == {
        "checksum_mismatch"
    }
