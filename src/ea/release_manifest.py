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

from ea.identity import (
    DISTRIBUTION_NAME,
    LEGACY_SKILL_NAMES,
    PROJECT_FORMAT_VERSION,
    RELEASE_LABEL,
    SKILL_NAME,
    SUPPORTED_PYTHON_MINORS,
)


DEFAULT_INCLUDE_ROOTS = [
    "README.md",
    "LICENSE",
    "NOTICE",
    "CHANGELOG.md",
    "CITATION.cff",
    "GOVERNANCE.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "pyproject.toml",
    "src/ea",
    "skills/ea",
    "skills/ea-v0-2",
    "skill-registry",
    "docs",
    "schemas",
    "benchmarks",
    "requirements",
    ".github",
    "examples",
    "tests",
    "scripts",
]
DEFAULT_OUTPUT = Path("dist") / "experimental-assistant-v0.9.7-release-manifest.yml"
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
PUBLIC_REPOSITORY = {
    "project_name": "Experimental Assistant (EA)",
    "repository_full_name": "gongchenisbusy/Experimental-Assistant",
    "repository_url": "https://github.com/gongchenisbusy/Experimental-Assistant",
    "release_url": "https://github.com/gongchenisbusy/Experimental-Assistant/releases/tag/v0.9.7",
}
SMOKE_GATE_COMMANDS = [
    "python3 scripts/public_release_smoke.py",
    "python3 scripts/check_version_identity.py",
    "python3 scripts/check_downloaded_skill_instructions.py",
    "python3 scripts/validate_skill_packages.py",
    "python3 scripts/run_scientific_benchmarks.py",
    "ea-public-release-smoke",
    "ea healthcheck examples/public-raman-project",
    "ea eval project examples/public-raman-project --no-write",
    "ea healthcheck examples/public-ftir-assignment-project",
    "ea eval project examples/public-ftir-assignment-project --no-write",
    "ea healthcheck examples/public-uv-vis-project",
    "ea eval project examples/public-uv-vis-project --no-write",
    "ea healthcheck examples/public-xps-be-project",
    "ea eval project examples/public-xps-be-project --no-write",
    "ea version",
    "ea setup",
    "ea doctor",
    "ea-install-check",
    "ea-release-artifact-smoke",
    "ea-release-reproducibility",
    "ea-release-supply-chain",
    "ea-release-package",
    "ea-verify-release-package",
    "ea-release-keygen",
    "ea-sign-release-package",
    "ea-verify-release-signature",
    "ea-release-checklist",
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
    status_lines = (
        _run_git(root, ["status", "--short", "--untracked-files=all"]) or ""
    ).splitlines()
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


def iter_release_files(
    root: Path, include_roots: Iterable[str] = DEFAULT_INCLUDE_ROOTS
) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for rel in include_roots:
        path = root / rel
        if not path.exists():
            continue
        candidates = (
            [path]
            if path.is_file()
            else sorted(item for item in path.rglob("*") if item.is_file())
        )
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
        digest.update(
            f"{record['path']}\0{record['sha256']}\0{record['size_bytes']}\n".encode(
                "utf-8"
            )
        )
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
        "schema_version": "1.0",
        "manifest_type": "experimental_assistant_release",
        "repository_root_name": root.name,
        "public_repository": PUBLIC_REPOSITORY,
        "package": metadata,
        "release": {
            "label": RELEASE_LABEL,
            "version": metadata.get("version"),
            "relationship_to_v1": "Full v1.0 release candidate; promotion requires controlled novice/platform trials and external scientific review evidence.",
            "acceptance_matrix_ref": "docs/PUBLIC_ACCEPTANCE_MATRIX.md",
            "release_notes_ref": "docs/V0_9_RELEASE_NOTES.md",
            "known_limitations_ref": "docs/V0_9_KNOWN_LIMITATIONS.md",
            "manual_test_checklist_ref": "docs/V0_9_MANUAL_TEST_CHECKLIST.md",
            "agent_handoff_ref": "docs/V0_9_AGENT_HANDOFF.md",
            "trial_report_ref": "docs/V0_9_7_TRIAL_REPORT.md",
            "issue_disposition_ref": "docs/V0_9_7_ISSUE_DISPOSITION.md",
        },
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
                "primary_skill_validation",
                "compatibility_skill_validation",
                "cli_help",
                "cli_global_version",
                "cli_version_help",
                "cli_install_check_help",
                "cli_codex_install_skill_help",
                "version_identity_check",
                "downloaded_skill_instruction_check",
                "cli_export_help",
                "cli_eval_help",
                "install_check_console_help",
                "public_example_raman_healthcheck",
                "public_example_raman_eval",
                "public_example_ftir_source_healthcheck",
                "public_example_ftir_source_eval",
                "public_example_uv_vis_healthcheck",
                "public_example_uv_vis_eval",
                "public_example_xps_be_healthcheck",
                "public_example_xps_be_eval",
                "release_manifest_help",
                "release_package_help",
                "release_package_verify_help",
                "release_signature_keygen_help",
                "release_signature_sign_help",
                "release_signature_verify_help",
                "release_artifact_smoke_help",
                "release_reproducibility_help",
                "release_supply_chain_help",
                "release_distribution_checklist_help",
                "portability_scan",
            ],
            "skill_validation_targets": ["skills/ea", "skills/ea-v0-2"],
            "portability_scan_scope": [
                "README.md",
                "pyproject.toml",
                "src",
                "skills/ea",
                "skills/ea-v0-2/SKILL.md",
                "skill-registry",
                "examples",
            ],
        },
        "identity_contract": {
            "distribution": DISTRIBUTION_NAME,
            "primary_skill": SKILL_NAME,
            "compatibility_skills": list(LEGACY_SKILL_NAMES),
            "project_format_version": PROJECT_FORMAT_VERSION,
            "supported_python_minors": [
                f"{major}.{minor}" for major, minor in SUPPORTED_PYTHON_MINORS
            ],
        },
        "supply_chain": {
            "sbom_ref": "dist/experimental-assistant-0.9.7-sbom.json",
            "vulnerability_report_ref": "dist/experimental-assistant-0.9.7-vulnerability-report.json",
            "install_smoke_ref": "dist/experimental-assistant-0.9.7-install-smoke.json",
            "reproducibility_ref": "dist/experimental-assistant-0.9.7-reproducibility.json",
            "vulnerability_policy_ref": "docs/RELEASE_SECURITY_POLICY.md",
            "release_constraints_ref": "requirements/release.txt",
        },
        "scientific_evidence": {
            "raman_benchmark_ref": "benchmarks/raman-v1/benchmark.yml",
            "raman_review_ref": "benchmarks/raman-v1/scientific-review.yml",
            "raman_status": "beta_pending_external_reviewer",
        },
        "public_boundaries": PUBLIC_BOUNDARY_NOTES,
        "signature": {
            "status": "not_signed",
            "supported_workflow": "detached_ed25519_user_managed_key",
            "sidecar_suffix": ".sig.yml",
            "note": "This manifest records local file integrity only. Use ea-sign-release-package with an explicit user-managed key to create a detached signature sidecar.",
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
    output_path.write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return output_path, manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate an Experimental Assistant v0.9.7 repository manifest."
    )
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
        output_path, manifest = write_release_manifest(
            root, output=args.output, include_roots=include_roots
        )
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
