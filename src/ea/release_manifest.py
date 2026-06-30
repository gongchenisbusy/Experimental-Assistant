from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any, Iterable

import yaml


DEFAULT_INCLUDE_ROOTS = [
    "README.md",
    "pyproject.toml",
    "src/ea",
    "skills/ea-v0-2",
    "skill-registry",
    "docs",
    "tests",
    "scripts",
]
DEFAULT_OUTPUT = Path("dist") / "ea-v0.2-release-manifest.yml"
EXCLUDED_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "venv",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".log"}
PUBLIC_BOUNDARY_NOTES = [
    "No developer-machine Zotero configuration is required by the release manifest.",
    "No browser profile, institution login, live web search, PDF download, or private literature cache is required.",
    "Public-user configuration must be supplied during project initialization or left disabled.",
    "Local test fixtures are separated from product defaults.",
]
SMOKE_GATE_COMMANDS = [
    "python3 scripts/public_release_smoke.py",
    "ea-public-release-smoke",
    "ea-release-package",
]


def _repo_root(path: Path | None = None) -> Path:
    return (path or Path.cwd()).resolve()


def _run_git(root: Path, args: list[str]) -> str | None:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def git_state(root: Path) -> dict[str, Any]:
    status_lines = (_run_git(root, ["status", "--short", "--untracked-files=all"]) or "").splitlines()
    tags = (_run_git(root, ["tag", "--points-at", "HEAD"]) or "").splitlines()
    return {
        "commit": _run_git(root, ["rev-parse", "HEAD"]),
        "branch": _run_git(root, ["branch", "--show-current"]),
        "tags_at_head": sorted(tag for tag in tags if tag),
        "dirty": bool(status_lines),
        "dirty_files": status_lines,
    }


def pyproject_metadata(root: Path) -> dict[str, Any]:
    pyproject = root / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    project = data.get("project", {})
    return {
        "name": project.get("name"),
        "version": project.get("version"),
        "description": project.get("description"),
        "requires_python": project.get("requires-python"),
        "dependencies": project.get("dependencies", []),
        "optional_dependencies": project.get("optional-dependencies", {}),
        "console_scripts": project.get("scripts", {}),
    }


def _should_skip(path: Path) -> bool:
    if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
        return True
    if path.name == ".DS_Store":
        return True
    return path.suffix in EXCLUDED_SUFFIXES


def iter_release_files(root: Path, include_roots: Iterable[str] = DEFAULT_INCLUDE_ROOTS) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for rel in include_roots:
        path = root / rel
        if not path.exists():
            continue
        candidates = [path] if path.is_file() else sorted(item for item in path.rglob("*") if item.is_file())
        for candidate in candidates:
            rel_path = candidate.relative_to(root)
            if rel_path in seen or _should_skip(rel_path):
                continue
            seen.add(rel_path)
            files.append(candidate)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_checksum_records(root: Path, files: Iterable[Path]) -> list[dict[str, Any]]:
    records = []
    for path in files:
        records.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    return records


def aggregate_checksum(records: Iterable[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for record in sorted(records, key=lambda item: item["path"]):
        digest.update(f"{record['path']}\0{record['sha256']}\0{record['size_bytes']}\n".encode("utf-8"))
    return digest.hexdigest()


def build_release_manifest(
    root: Path,
    *,
    include_roots: Iterable[str] = DEFAULT_INCLUDE_ROOTS,
) -> dict[str, Any]:
    root = _repo_root(root)
    metadata = pyproject_metadata(root)
    files = iter_release_files(root, include_roots)
    checksums = file_checksum_records(root, files)
    return {
        "schema_version": "0.2",
        "manifest_type": "ea_v0_2_repository_release",
        "repository_root_name": root.name,
        "package": metadata,
        "git": git_state(root),
        "release_inputs": {
            "include_roots": list(include_roots),
            "excluded_dir_names": sorted(EXCLUDED_DIR_NAMES),
            "excluded_suffixes": sorted(EXCLUDED_SUFFIXES),
            "file_count": len(checksums),
            "aggregate_sha256": aggregate_checksum(checksums),
            "files": checksums,
        },
        "validation_contract": {
            "smoke_gate_commands": SMOKE_GATE_COMMANDS,
            "required_smoke_steps": [
                "pytest",
                "skill_validation",
                "cli_help",
                "cli_export_help",
                "cli_eval_help",
                "release_manifest_help",
                "release_package_help",
                "portability_scan",
            ],
            "skill_validation_target": "skills/ea-v0-2",
            "portability_scan_scope": ["README.md", "pyproject.toml", "src", "skills/ea-v0-2", "skill-registry"],
        },
        "public_boundaries": PUBLIC_BOUNDARY_NOTES,
        "signature": {
            "status": "not_signed",
            "note": "This manifest records local file integrity only. User-managed cryptographic signing is a future release slice.",
        },
    }


def write_release_manifest(
    root: Path,
    *,
    output: Path | None = None,
    include_roots: Iterable[str] = DEFAULT_INCLUDE_ROOTS,
) -> tuple[Path, dict[str, Any]]:
    root = _repo_root(root)
    output_path = output or DEFAULT_OUTPUT
    if not output_path.is_absolute():
        output_path = root / output_path
    manifest = build_release_manifest(root, include_roots=include_roots)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return output_path, manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate an EA v0.2 repository release manifest.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--include-root", action="append", default=[])
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--print-manifest", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = _repo_root(args.root)
    include_roots = args.include_root or DEFAULT_INCLUDE_ROOTS
    if args.no_write:
        manifest = build_release_manifest(root, include_roots=include_roots)
        output_path = None
    else:
        output_path, manifest = write_release_manifest(root, output=args.output, include_roots=include_roots)
    summary = {
        "status": "complete",
        "manifest": str(output_path) if output_path else None,
        "package": {
            "name": manifest["package"]["name"],
            "version": manifest["package"]["version"],
        },
        "git": manifest["git"],
        "file_count": manifest["release_inputs"]["file_count"],
        "aggregate_sha256": manifest["release_inputs"]["aggregate_sha256"],
    }
    if args.print_manifest:
        summary["release_manifest"] = manifest
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
