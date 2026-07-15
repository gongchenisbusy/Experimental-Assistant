from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from ea import __version__


FIXED_ZIP_TIME = (2020, 1, 1, 0, 0, 0)
SKILL_NAMES = ("ea", "ea-v0-2")


def _repository_root(start: Path | None = None) -> Path:
    root = (start or Path.cwd()).resolve()
    for candidate in (root, *root.parents):
        if (candidate / "pyproject.toml").is_file() and (
            candidate / "skills" / "ea" / "SKILL.md"
        ).is_file():
            return candidate
    raise FileNotFoundError(
        "Could not locate the Experimental Assistant repository root."
    )


def build_skill_bundle(
    *,
    repository_root: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, object]:
    root = _repository_root(repository_root)
    output = (
        output_path
        or root / "dist" / f"experimental-assistant-{__version__}-skills.zip"
    )
    if not output.is_absolute():
        output = root / output
    output.parent.mkdir(parents=True, exist_ok=True)
    members: list[str] = []
    with zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for skill_name in SKILL_NAMES:
            skill_root = root / "skills" / skill_name
            if not (skill_root / "SKILL.md").is_file():
                raise FileNotFoundError(skill_root / "SKILL.md")
            for path in sorted(skill_root.rglob("*")):
                if (
                    not path.is_file()
                    or "__pycache__" in path.parts
                    or path.suffix in {".pyc", ".pyo"}
                ):
                    continue
                relative = path.relative_to(root).as_posix()
                info = zipfile.ZipInfo(relative, FIXED_ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, path.read_bytes())
                members.append(relative)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    checksum_path = output.with_suffix(output.suffix + ".sha256")
    checksum_path.write_text(f"{digest}  {output.name}\n", encoding="utf-8")
    return {
        "schema_version": "1.0",
        "status": "pass",
        "version": __version__,
        "bundle": str(output),
        "checksum": str(checksum_path),
        "sha256": digest,
        "member_count": len(members),
        "skills": list(SKILL_NAMES),
    }


def verify_skill_bundle(
    bundle_path: Path, *, checksum_path: Path | None = None
) -> dict[str, object]:
    bundle = bundle_path.resolve()
    checksum = (
        checksum_path or bundle.with_suffix(bundle.suffix + ".sha256")
    ).resolve()
    failures: list[dict[str, str]] = []
    actual = None
    expected = None
    members: set[str] = set()
    if not bundle.is_file():
        failures.append({"path": str(bundle), "reason": "missing_bundle"})
    else:
        actual = hashlib.sha256(bundle.read_bytes()).hexdigest()
    if not checksum.is_file():
        failures.append({"path": str(checksum), "reason": "missing_checksum"})
    else:
        parts = checksum.read_text(encoding="utf-8").split()
        expected = parts[0] if parts else None
        named_file = parts[1] if len(parts) > 1 else None
        if expected != actual:
            failures.append({"path": str(bundle), "reason": "checksum_mismatch"})
        if named_file != bundle.name:
            failures.append(
                {"path": str(checksum), "reason": "checksum_filename_mismatch"}
            )
    if bundle.is_file():
        try:
            with zipfile.ZipFile(bundle) as archive:
                members = set(archive.namelist())
                if any(
                    Path(name).is_absolute() or ".." in Path(name).parts
                    for name in members
                ):
                    failures.append(
                        {"path": str(bundle), "reason": "unsafe_archive_member"}
                    )
        except zipfile.BadZipFile:
            failures.append({"path": str(bundle), "reason": "invalid_zip"})
    for skill_name in SKILL_NAMES:
        required = f"skills/{skill_name}/SKILL.md"
        if required not in members:
            failures.append({"path": required, "reason": "missing_skill_manifest"})
    return {
        "schema_version": "1.0",
        "check_type": "experimental_assistant_skill_bundle",
        "status": "fail" if failures else "pass",
        "bundle": str(bundle),
        "checksum": str(checksum),
        "expected_sha256": expected,
        "actual_sha256": actual,
        "member_count": len(members),
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the compact Experimental Assistant Codex skill bundle."
    )
    parser.add_argument("--repository-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = build_skill_bundle(
        repository_root=args.repository_root, output_path=args.output
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
