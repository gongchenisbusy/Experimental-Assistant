from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

from ea.release_manifest import DEFAULT_OUTPUT, SMOKE_GATE_COMMANDS, build_release_manifest
from ea.release_package import _checksum_sidecar_path, verify_release_package
from ea.release_signature import _signature_sidecar_path, verify_release_signature


DEFAULT_JSON_OUTPUT = Path("dist") / "ea-v0.9.6-distribution-checklist.json"
DEFAULT_MARKDOWN_OUTPUT = Path("dist") / "ea-v0.9.6-distribution-checklist.md"


def _repo_root(path: Path | None = None) -> Path:
    return (path or Path.cwd()).resolve()


def _resolve_under_root(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _display_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _check(code: str, description: str, status: str, *, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "description": description,
        "status": status,
        "evidence": evidence or {},
    }


def _discover_archives(
    root: Path,
    dist_dir: Path,
    archive_paths: Iterable[Path] | None,
    *,
    package_name: str | None = None,
    package_version: str | None = None,
) -> list[Path]:
    if archive_paths:
        return sorted((_resolve_under_root(root, path).resolve() for path in archive_paths), key=lambda item: item.as_posix())
    if not dist_dir.exists():
        return []
    archives = sorted(path.resolve() for path in dist_dir.glob("*.zip") if path.is_file())
    if package_name and package_version:
        current_prefix = f"{package_name}-{package_version}-"
        current_archives = [
            path
            for path in archives
            if path.name.startswith(current_prefix) and path.name.endswith("-release.zip")
        ]
        if current_archives:
            return current_archives
    return archives


def build_distribution_checklist(
    root: Path,
    *,
    dist_dir: Path | None = None,
    archive_paths: Iterable[Path] | None = None,
    public_key_path: Path | None = None,
) -> dict[str, Any]:
    root = _repo_root(root)
    dist_dir = _resolve_under_root(root, dist_dir or Path("dist")).resolve()
    public_key = _resolve_under_root(root, public_key_path).resolve() if public_key_path else None
    manifest = build_release_manifest(root)
    manifest_path = (root / DEFAULT_OUTPUT).resolve()
    archives = _discover_archives(
        root,
        dist_dir,
        archive_paths,
        package_name=str(manifest["package"].get("name") or ""),
        package_version=str(manifest["package"].get("version") or ""),
    )

    checks: list[dict[str, Any]] = [
        _check(
            "git.clean_worktree",
            "Git worktree is clean for release handoff.",
            "pass" if not manifest["git"]["dirty"] else "fail",
            evidence={"dirty": manifest["git"]["dirty"], "dirty_files": manifest["git"]["dirty_files"]},
        ),
        _check(
            "git.tag_at_head",
            "HEAD has at least one release tag.",
            "pass" if manifest["git"]["tags_at_head"] else "warning",
            evidence={"tags_at_head": manifest["git"]["tags_at_head"]},
        ),
        _check(
            "release_manifest.file_present",
            "Default release manifest file is present in dist/.",
            "pass" if manifest_path.exists() else "fail",
            evidence={"path": _display_path(root, manifest_path), "exists": manifest_path.exists()},
        ),
        _check(
            "release_package.archive_present",
            "At least one release zip archive is present.",
            "pass" if archives else "fail",
            evidence={"dist_dir": _display_path(root, dist_dir), "archives": [_display_path(root, path) for path in archives]},
        ),
    ]

    archive_records = []
    for archive in archives:
        checksum_path = _checksum_sidecar_path(archive)
        package_verification = verify_release_package(archive)
        archive_status = "pass" if package_verification["status"] == "pass" else "fail"
        checks.append(
            _check(
                "release_package.verify",
                f"Release package verifies: {_display_path(root, archive)}",
                archive_status,
                evidence={
                    "archive": _display_path(root, archive),
                    "checksum_sidecar": _display_path(root, checksum_path),
                    "package_verification_status": package_verification["status"],
                },
            )
        )
        signature_path = _signature_sidecar_path(archive)
        signature_record: dict[str, Any] = {
            "path": _display_path(root, signature_path),
            "exists": signature_path.exists(),
            "required": False,
            "status": "not_present",
        }
        if signature_path.exists() and public_key:
            signature_verification = verify_release_signature(archive, public_key_path=public_key, signature_path=signature_path)
            signature_record["status"] = signature_verification["status"]
            signature_record["public_key_path"] = _display_path(root, public_key)
            signature_record["verification"] = signature_verification
        elif signature_path.exists():
            signature_record["status"] = "present_unverified"
            signature_record["note"] = "Provide --public-key to verify the detached release signature."
        else:
            signature_record["note"] = "Optional detached signature sidecar is not present."
        archive_records.append(
            {
                "path": _display_path(root, archive),
                "exists": archive.exists(),
                "checksum_sidecar": {
                    "path": _display_path(root, checksum_path),
                    "exists": checksum_path.exists(),
                },
                "verification": package_verification,
                "signature": signature_record,
            }
        )

    failures = [check for check in checks if check["status"] == "fail"]
    optional_signature_statuses = [record["signature"]["status"] for record in archive_records]
    recommendations = []
    if "not_present" in optional_signature_statuses:
        recommendations.append("Optional release signing is available; use ea-release-keygen and ea-sign-release-package when authorship/intent evidence is needed.")
    if "present_unverified" in optional_signature_statuses:
        recommendations.append("A signature sidecar is present but was not verified because no public key was supplied.")

    return {
        "schema_version": "0.9",
        "check_type": "ea_v0_9_6_release_distribution_checklist",
        "status": "fail" if failures else "pass",
        "root": str(root),
        "package": {
            "name": manifest["package"]["name"],
            "version": manifest["package"]["version"],
        },
        "git": manifest["git"],
        "required_commands": SMOKE_GATE_COMMANDS,
        "recommended_handoff_commands": [
            "ea-public-release-smoke",
            "ea-release-manifest",
            "ea-release-package",
            "ea-verify-release-package <release.zip>",
            "ea-release-keygen --private-key <private.pem> --public-key <public.pem>",
            "ea-sign-release-package <release.zip> --private-key <private.pem> --public-key <public.pem>",
            "ea-verify-release-signature <release.zip> --public-key <public.pem>",
            "ea-release-checklist",
        ],
        "public_boundaries": manifest["public_boundaries"],
        "required_checks": checks,
        "release_artifacts": {
            "manifest": {
                "path": _display_path(root, manifest_path),
                "exists": manifest_path.exists(),
            },
            "archives": archive_records,
        },
        "optional_signature": {
            "required": False,
            "statuses": optional_signature_statuses,
        },
        "recommendations": recommendations,
        "failures": failures,
    }


def render_distribution_markdown(checklist: dict[str, Any]) -> str:
    lines = [
        "# Experimental Assistant v0.9.6 Distribution Checklist",
        "",
        f"- Status: `{checklist['status']}`",
        f"- Package: `{checklist['package']['name']} {checklist['package']['version']}`",
        f"- Git commit: `{checklist['git']['commit']}`",
        f"- Git branch: `{checklist['git']['branch']}`",
        f"- Tags at HEAD: `{', '.join(checklist['git']['tags_at_head']) or 'none'}`",
        "",
        "## Required Checks",
        "",
    ]
    for check in checklist["required_checks"]:
        marker = "x" if check["status"] == "pass" else " "
        lines.append(f"- [{marker}] `{check['code']}`: {check['description']} ({check['status']})")
    lines.extend(["", "## Release Artifacts", ""])
    manifest = checklist["release_artifacts"]["manifest"]
    lines.append(f"- Manifest: `{manifest['path']}` ({'present' if manifest['exists'] else 'missing'})")
    for archive in checklist["release_artifacts"]["archives"]:
        lines.append(f"- Archive: `{archive['path']}` ({archive['verification']['status']})")
        checksum = archive["checksum_sidecar"]
        lines.append(f"  - Checksum sidecar: `{checksum['path']}` ({'present' if checksum['exists'] else 'missing'})")
        signature = archive["signature"]
        lines.append(f"  - Optional signature: `{signature['path']}` ({signature['status']})")
    if not checklist["release_artifacts"]["archives"]:
        lines.append("- Archive: missing")
    lines.extend(["", "## Recommended Commands", ""])
    for command in checklist["recommended_handoff_commands"]:
        lines.append(f"- `{command}`")
    if checklist["recommendations"]:
        lines.extend(["", "## Recommendations", ""])
        for recommendation in checklist["recommendations"]:
            lines.append(f"- {recommendation}")
    lines.extend(["", "## Public Boundaries", ""])
    for note in checklist["public_boundaries"]:
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


def write_distribution_checklist(
    root: Path,
    *,
    output_json: Path | None = None,
    output_md: Path | None = None,
    dist_dir: Path | None = None,
    archive_paths: Iterable[Path] | None = None,
    public_key_path: Path | None = None,
) -> tuple[Path, Path, dict[str, Any]]:
    root = _repo_root(root)
    checklist = build_distribution_checklist(
        root,
        dist_dir=dist_dir,
        archive_paths=archive_paths,
        public_key_path=public_key_path,
    )
    json_path = _resolve_under_root(root, output_json or DEFAULT_JSON_OUTPUT)
    md_path = _resolve_under_root(root, output_md or DEFAULT_MARKDOWN_OUTPUT)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(checklist, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_distribution_markdown(checklist), encoding="utf-8")
    return json_path, md_path, checklist


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate an Experimental Assistant v0.9.6 package distribution checklist.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--dist-dir", type=Path, default=Path("dist"))
    parser.add_argument("--archive", type=Path, action="append", default=[])
    parser.add_argument("--public-key", type=Path)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_MARKDOWN_OUTPUT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--print-checklist", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = _repo_root(args.root)
    archive_paths = args.archive or None
    if args.no_write:
        checklist = build_distribution_checklist(
            root,
            dist_dir=args.dist_dir,
            archive_paths=archive_paths,
            public_key_path=args.public_key,
        )
        json_path = None
        md_path = None
    else:
        json_path, md_path, checklist = write_distribution_checklist(
            root,
            output_json=args.output_json,
            output_md=args.output_md,
            dist_dir=args.dist_dir,
            archive_paths=archive_paths,
            public_key_path=args.public_key,
        )
    summary: dict[str, Any] = {
        "status": checklist["status"],
        "check_type": checklist["check_type"],
        "json_path": str(json_path) if json_path else None,
        "markdown_path": str(md_path) if md_path else None,
        "package": checklist["package"],
        "git": checklist["git"],
        "failure_count": len(checklist["failures"]),
        "archive_count": len(checklist["release_artifacts"]["archives"]),
        "recommendations": checklist["recommendations"],
    }
    if args.print_checklist:
        summary["distribution_checklist"] = checklist
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if checklist["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
