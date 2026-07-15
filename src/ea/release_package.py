from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from typing import Any, Iterable

import yaml

from ea import __version__
from ea.release_manifest import (
    DEFAULT_INCLUDE_ROOTS,
    build_release_manifest,
    iter_release_files,
)


FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
MANIFEST_ARCHIVE_NAME = f"experimental-assistant-v{__version__}-release-manifest.yml"


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
    name = str(package.get("name") or "experimental-assistant")
    version = str(package.get("version") or __version__)
    return root / "dist" / f"{name}-{version}-{_short_commit(manifest)}-release.zip"


def _default_archive_root(manifest: dict[str, Any]) -> str:
    package = manifest["package"]
    name = str(package.get("name") or "experimental-assistant")
    version = str(package.get("version") or __version__)
    return f"{name}-{version}"


def _write_zip_bytes(archive: zipfile.ZipFile, arcname: str, data: bytes) -> None:
    info = zipfile.ZipInfo(arcname)
    info.date_time = FIXED_ZIP_TIMESTAMP
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, data)


def _checksum_sidecar_path(archive_path: Path) -> Path:
    return archive_path.with_name(f"{archive_path.name}.sha256")


def _archive_sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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
    archive_root_name = (archive_root or _default_archive_root(manifest)).strip().strip(
        "/"
    ) or "experimental-assistant-release"
    files = iter_release_files(root, include_roots)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    manifest_bytes = yaml.safe_dump(
        manifest, allow_unicode=True, sort_keys=False
    ).encode("utf-8")
    with zipfile.ZipFile(output_path, "w") as archive:
        _write_zip_bytes(
            archive, f"{archive_root_name}/{MANIFEST_ARCHIVE_NAME}", manifest_bytes
        )
        for source in files:
            rel = source.relative_to(root).as_posix()
            _write_zip_bytes(archive, f"{archive_root_name}/{rel}", source.read_bytes())

    checksum_path = _checksum_sidecar_path(output_path)
    archive_sha256 = _sha256_file(output_path)
    checksum_path.write_text(
        f"{archive_sha256}  {output_path.name}\n", encoding="utf-8"
    )

    return {
        "schema_version": "1.0",
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


def verify_release_package(
    archive_path: Path, *, checksum_path: Path | None = None
) -> dict[str, Any]:
    archive_path = archive_path.resolve()
    checksum_path = (checksum_path or _checksum_sidecar_path(archive_path)).resolve()
    result: dict[str, Any] = {
        "schema_version": "1.0",
        "check_type": "ea_v0_9_9_release_package",
        "status": "pass",
        "archive_path": str(archive_path),
        "archive_checksum_path": str(checksum_path),
        "algorithm": "sha256",
        "expected_sha256": None,
        "actual_sha256": None,
        "manifest_archive_ref": None,
        "archive_root": None,
        "checked_count": 0,
        "failures": [],
    }
    if not archive_path.exists():
        result["status"] = "fail"
        result["failures"].append(
            {"path": str(archive_path), "reason": "missing_archive"}
        )
        return result
    if not checksum_path.exists():
        result["status"] = "fail"
        result["failures"].append(
            {"path": str(checksum_path), "reason": "missing_checksum_sidecar"}
        )
    else:
        sidecar = checksum_path.read_text(encoding="utf-8").strip().split()
        if not sidecar:
            result["status"] = "fail"
            result["failures"].append(
                {"path": str(checksum_path), "reason": "empty_checksum_sidecar"}
            )
        else:
            expected_sha = sidecar[0]
            actual_sha = _sha256_file(archive_path)
            result["expected_sha256"] = expected_sha
            result["actual_sha256"] = actual_sha
            if expected_sha != actual_sha:
                result["status"] = "fail"
                result["failures"].append(
                    {
                        "path": archive_path.name,
                        "reason": "sha256_mismatch",
                        "expected_sha256": expected_sha,
                        "actual_sha256": actual_sha,
                    }
                )

    try:
        with zipfile.ZipFile(archive_path) as archive:
            manifest_names = [
                name
                for name in archive.namelist()
                if name.endswith(f"/{MANIFEST_ARCHIVE_NAME}")
                or name == MANIFEST_ARCHIVE_NAME
            ]
            if not manifest_names:
                result["status"] = "fail"
                result["failures"].append(
                    {
                        "path": MANIFEST_ARCHIVE_NAME,
                        "reason": "missing_embedded_manifest",
                    }
                )
                return result
            if len(manifest_names) > 1:
                result["status"] = "fail"
                result["failures"].append(
                    {
                        "path": MANIFEST_ARCHIVE_NAME,
                        "reason": "multiple_embedded_manifests",
                        "matches": sorted(manifest_names),
                    }
                )
                return result
            manifest_ref = manifest_names[0]
            result["manifest_archive_ref"] = manifest_ref
            archive_root = (
                manifest_ref[: -len(f"/{MANIFEST_ARCHIVE_NAME}")]
                if "/" in manifest_ref
                else ""
            )
            result["archive_root"] = archive_root
            manifest = yaml.safe_load(archive.read(manifest_ref)) or {}
            infos = {info.filename: info for info in archive.infolist()}
            for entry in manifest.get("release_inputs", {}).get("files") or []:
                rel = str(entry.get("path") or "")
                if not rel:
                    result["status"] = "fail"
                    result["failures"].append(
                        {"path": rel, "reason": "empty_manifest_path"}
                    )
                    continue
                archive_ref = f"{archive_root}/{rel}" if archive_root else rel
                info = infos.get(archive_ref)
                if info is None:
                    result["status"] = "fail"
                    result["failures"].append(
                        {"path": archive_ref, "reason": "missing_release_input"}
                    )
                    continue
                expected_size = entry.get("size_bytes")
                expected_sha = str(entry.get("sha256") or "")
                data = archive.read(archive_ref)
                actual_size = len(data)
                actual_sha = _archive_sha256_bytes(data)
                result["checked_count"] += 1
                if expected_size != actual_size:
                    result["status"] = "fail"
                    result["failures"].append(
                        {
                            "path": archive_ref,
                            "reason": "size_mismatch",
                            "expected_size_bytes": expected_size,
                            "actual_size_bytes": actual_size,
                        }
                    )
                if expected_sha != actual_sha:
                    result["status"] = "fail"
                    result["failures"].append(
                        {
                            "path": archive_ref,
                            "reason": "sha256_mismatch",
                            "expected_sha256": expected_sha,
                            "actual_sha256": actual_sha,
                        }
                    )
    except zipfile.BadZipFile:
        result["status"] = "fail"
        result["failures"].append({"path": str(archive_path), "reason": "invalid_zip"})
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"Build an Experimental Assistant v{__version__} repository zip archive."
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--include-root", action="append", default=[])
    parser.add_argument("--archive-root")
    return parser


def build_verify_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"Verify an Experimental Assistant v{__version__} repository zip archive."
    )
    parser.add_argument("archive", type=Path)
    parser.add_argument("--checksum", type=Path)
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


def verify_main(argv: list[str] | None = None) -> int:
    args = build_verify_parser().parse_args(argv)
    result = verify_release_package(args.archive, checksum_path=args.checksum)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
