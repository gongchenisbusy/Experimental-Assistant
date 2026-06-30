from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from typing import Any, Iterable

import yaml

from ea.release_manifest import DEFAULT_INCLUDE_ROOTS, build_release_manifest, iter_release_files


FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
MANIFEST_ARCHIVE_NAME = "ea-v0.2-release-manifest.yml"


def _repo_root(path: Path | None = None) -> Path:
    return (path or Path.cwd()).resolve()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _short_commit(manifest: dict[str, Any]) -> str:
    commit = manifest.get("git", {}).get("commit")
    return str(commit)[:7] if commit else "nogit"


def _default_archive_path(root: Path, manifest: dict[str, Any]) -> Path:
    package = manifest["package"]
    name = str(package.get("name") or "ea-v0-2")
    version = str(package.get("version") or "0.2.0")
    return root / "dist" / f"{name}-{version}-{_short_commit(manifest)}-release.zip"


def _default_archive_root(manifest: dict[str, Any]) -> str:
    package = manifest["package"]
    name = str(package.get("name") or "ea-v0-2")
    version = str(package.get("version") or "0.2.0")
    return f"{name}-{version}"


def _write_zip_bytes(archive: zipfile.ZipFile, arcname: str, data: bytes) -> None:
    info = zipfile.ZipInfo(arcname)
    info.date_time = FIXED_ZIP_TIMESTAMP
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, data)


def _checksum_sidecar_path(archive_path: Path) -> Path:
    return archive_path.with_name(f"{archive_path.name}.sha256")


def write_release_package(
    root: Path,
    *,
    output: Path | None = None,
    include_roots: Iterable[str] = DEFAULT_INCLUDE_ROOTS,
    archive_root: str | None = None,
) -> dict[str, Any]:
    root = _repo_root(root)
    manifest = build_release_manifest(root, include_roots=include_roots)
    output_path = output or _default_archive_path(root, manifest)
    if not output_path.is_absolute():
        output_path = root / output_path
    archive_root_name = (archive_root or _default_archive_root(manifest)).strip().strip("/") or "ea-v0-2-release"
    files = iter_release_files(root, include_roots)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    manifest_bytes = yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False).encode("utf-8")
    with zipfile.ZipFile(output_path, "w") as archive:
        _write_zip_bytes(archive, f"{archive_root_name}/{MANIFEST_ARCHIVE_NAME}", manifest_bytes)
        for source in files:
            rel = source.relative_to(root).as_posix()
            _write_zip_bytes(archive, f"{archive_root_name}/{rel}", source.read_bytes())

    checksum_path = _checksum_sidecar_path(output_path)
    archive_sha256 = _sha256_file(output_path)
    checksum_path.write_text(f"{archive_sha256}  {output_path.name}\n", encoding="utf-8")

    return {
        "schema_version": "0.2",
        "status": "complete",
        "archive_path": str(output_path),
        "archive_checksum_path": str(checksum_path),
        "archive_sha256": archive_sha256,
        "archive_size_bytes": output_path.stat().st_size,
        "archive_root": archive_root_name,
        "manifest_archive_ref": f"{archive_root_name}/{MANIFEST_ARCHIVE_NAME}",
        "file_count": len(files),
        "package": {
            "name": manifest["package"]["name"],
            "version": manifest["package"]["version"],
        },
        "git": manifest["git"],
        "signature": manifest["signature"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build an EA v0.2 repository release zip archive.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--include-root", action="append", default=[])
    parser.add_argument("--archive-root")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    include_roots = args.include_root or DEFAULT_INCLUDE_ROOTS
    result = write_release_package(
        args.root,
        output=args.output,
        include_roots=include_roots,
        archive_root=args.archive_root,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
