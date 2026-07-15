from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable

from ea import __version__
from ea.identity import DISTRIBUTION_NAME
from ea.release_artifacts import DEFAULT_OUTPUT as INSTALL_SMOKE_OUTPUT
from ea.release_manifest import (
    DEFAULT_OUTPUT,
    SMOKE_GATE_COMMANDS,
    build_release_manifest,
)
from ea.release_package import _checksum_sidecar_path, verify_release_package
from ea.release_reproducibility import DEFAULT_OUTPUT as REPRODUCIBILITY_OUTPUT
from ea.release_signature import _signature_sidecar_path, verify_release_signature
from ea.release_skill_bundle import verify_skill_bundle
from ea.release_supply_chain import DEFAULT_SBOM_OUTPUT, DEFAULT_VULNERABILITY_OUTPUT


DEFAULT_JSON_OUTPUT = (
    Path("dist") / f"experimental-assistant-v{__version__}-distribution-checklist.json"
)
DEFAULT_MARKDOWN_OUTPUT = (
    Path("dist") / f"experimental-assistant-v{__version__}-distribution-checklist.md"
)


def _repo_root(path: Path | None = None) -> Path:
    return (path or Path.cwd()).resolve()


def _resolve_under_root(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _display_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _check(
    code: str, description: str, status: str, *, evidence: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "code": code,
        "description": description,
        "status": status,
        "evidence": evidence or {},
    }


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, "missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, str(exc)
    return (
        (payload, None)
        if isinstance(payload, dict)
        else (None, "JSON root must be an object")
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _discover_archives(
    root: Path,
    dist_dir: Path,
    archive_paths: Iterable[Path] | None,
    *,
    package_name: str | None = None,
    package_version: str | None = None,
) -> list[Path]:
    if archive_paths:
        return sorted(
            (_resolve_under_root(root, path).resolve() for path in archive_paths),
            key=lambda item: item.as_posix(),
        )
    if not dist_dir.exists():
        return []
    archives = sorted(
        path.resolve()
        for path in dist_dir.glob("*.zip")
        if path.is_file() and not path.name.endswith("-skills.zip")
    )
    if package_name and package_version:
        current_prefix = f"{package_name}-{package_version}-"
        current_archives = [
            path
            for path in archives
            if path.name.startswith(current_prefix)
            and path.name.endswith("-release.zip")
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
    public_key = (
        _resolve_under_root(root, public_key_path).resolve()
        if public_key_path
        else None
    )
    manifest = build_release_manifest(root)
    manifest_path = (root / DEFAULT_OUTPUT).resolve()
    sbom_path = (root / DEFAULT_SBOM_OUTPUT).resolve()
    vulnerability_path = (root / DEFAULT_VULNERABILITY_OUTPUT).resolve()
    install_smoke_path = (root / INSTALL_SMOKE_OUTPUT).resolve()
    reproducibility_path = (root / REPRODUCIBILITY_OUTPUT).resolve()
    skill_bundle_path = (
        root / "dist" / f"experimental-assistant-{__version__}-skills.zip"
    ).resolve()
    constraints_path = (root / "requirements" / "release.txt").resolve()
    normalized = DISTRIBUTION_NAME.replace("-", "_")
    wheel_paths = (
        sorted(dist_dir.glob(f"{normalized}-{__version__}-*.whl"))
        if dist_dir.exists()
        else []
    )
    sdist_paths = (
        sorted(dist_dir.glob(f"{normalized}-{__version__}.tar.gz"))
        if dist_dir.exists()
        else []
    )
    sbom, sbom_error = _read_json(sbom_path)
    vulnerability, vulnerability_error = _read_json(vulnerability_path)
    install_smoke, install_smoke_error = _read_json(install_smoke_path)
    reproducibility, reproducibility_error = _read_json(reproducibility_path)
    reproducible_hashes = {
        str(item.get("artifact")): str((item.get("first") or {}).get("sha256") or "")
        for item in (reproducibility or {}).get("artifacts", [])
        if isinstance(item, dict)
    }
    current_python_artifacts = [*wheel_paths, *sdist_paths]
    reproducible_artifacts_match = bool(current_python_artifacts) and all(
        reproducible_hashes.get(path.name) == _sha256(path)
        for path in current_python_artifacts
    )
    sbom_valid = bool(
        sbom
        and sbom.get("bomFormat") == "CycloneDX"
        and sbom.get("specVersion") == "1.5"
        and (sbom.get("metadata") or {}).get("component", {}).get("name")
        == DISTRIBUTION_NAME
        and (sbom.get("metadata") or {}).get("component", {}).get("version")
        == __version__
    )
    vulnerability_valid = bool(
        vulnerability
        and vulnerability.get("status") == "pass"
        and vulnerability.get("vulnerability_count") == 0
    )
    install_smoke_valid = bool(
        install_smoke
        and install_smoke.get("status") == "pass"
        and install_smoke.get("distribution") == DISTRIBUTION_NAME
        and install_smoke.get("version") == __version__
    )
    reproducibility_valid = bool(
        reproducibility
        and reproducibility.get("status") == "pass"
        and reproducibility.get("distribution") == DISTRIBUTION_NAME
        and reproducibility.get("version") == __version__
        and reproducible_artifacts_match
    )
    skill_bundle_verification = verify_skill_bundle(skill_bundle_path)
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
            evidence={
                "dirty": manifest["git"]["dirty"],
                "dirty_files": manifest["git"]["dirty_files"],
            },
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
            evidence={
                "path": _display_path(root, manifest_path),
                "exists": manifest_path.exists(),
            },
        ),
        _check(
            "release_package.archive_present",
            "At least one release zip archive is present.",
            "pass" if archives else "fail",
            evidence={
                "dist_dir": _display_path(root, dist_dir),
                "archives": [_display_path(root, path) for path in archives],
            },
        ),
        _check(
            "python_distribution.wheel_present",
            "Current-version wheel is present.",
            "pass" if wheel_paths else "fail",
            evidence={"artifacts": [_display_path(root, path) for path in wheel_paths]},
        ),
        _check(
            "python_distribution.sdist_present",
            "Current-version sdist is present.",
            "pass" if sdist_paths else "fail",
            evidence={"artifacts": [_display_path(root, path) for path in sdist_paths]},
        ),
        _check(
            "skill_distribution.bundle",
            "Compact Codex skill bundle and checksum contain only the public $ea skill.",
            "pass" if skill_bundle_verification["status"] == "pass" else "fail",
            evidence={
                "path": _display_path(root, skill_bundle_path),
                "verification": skill_bundle_verification,
            },
        ),
        _check(
            "python_distribution.clean_install_smoke",
            "Wheel and sdist pass clean PATH-resolved CLI installation smoke.",
            "pass" if install_smoke_valid else "fail",
            evidence={
                "path": _display_path(root, install_smoke_path),
                "error": install_smoke_error,
                "status": (install_smoke or {}).get("status"),
            },
        ),
        _check(
            "python_distribution.reproducibility",
            "Repeated wheel and sdist builds are byte-identical under the declared scope.",
            "pass" if reproducibility_valid else "fail",
            evidence={
                "path": _display_path(root, reproducibility_path),
                "error": reproducibility_error,
                "status": (reproducibility or {}).get("status"),
                "current_artifact_hashes_match": reproducible_artifacts_match,
            },
        ),
        _check(
            "supply_chain.release_constraints",
            "Tested release constraints are present.",
            "pass" if constraints_path.is_file() else "fail",
            evidence={
                "path": _display_path(root, constraints_path),
                "exists": constraints_path.is_file(),
            },
        ),
        _check(
            "supply_chain.sbom",
            "CycloneDX 1.5 SBOM matches the current distribution identity.",
            "pass" if sbom_valid else "fail",
            evidence={
                "path": _display_path(root, sbom_path),
                "error": sbom_error,
                "valid": sbom_valid,
            },
        ),
        _check(
            "supply_chain.vulnerability_scan",
            "Known-vulnerability scan completed with zero unallowlisted findings.",
            "pass" if vulnerability_valid else "fail",
            evidence={
                "path": _display_path(root, vulnerability_path),
                "error": vulnerability_error,
                "status": (vulnerability or {}).get("status"),
                "vulnerability_count": (vulnerability or {}).get("vulnerability_count"),
            },
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
            signature_verification = verify_release_signature(
                archive, public_key_path=public_key, signature_path=signature_path
            )
            signature_record["status"] = signature_verification["status"]
            signature_record["public_key_path"] = _display_path(root, public_key)
            signature_record["verification"] = signature_verification
        elif signature_path.exists():
            signature_record["status"] = "present_unverified"
            signature_record["note"] = (
                "Provide --public-key to verify the detached release signature."
            )
        else:
            signature_record["note"] = (
                "Optional detached signature sidecar is not present."
            )
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
    optional_signature_statuses = [
        record["signature"]["status"] for record in archive_records
    ]
    recommendations = []
    if "not_present" in optional_signature_statuses:
        recommendations.append(
            "Optional release signing is available; use ea-release-keygen and ea-sign-release-package when authorship/intent evidence is needed."
        )
    if "present_unverified" in optional_signature_statuses:
        recommendations.append(
            "A signature sidecar is present but was not verified because no public key was supplied."
        )

    return {
        "schema_version": "1.0",
        "check_type": "experimental_assistant_release_distribution_checklist",
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
            "ea-release-artifact-smoke",
            "ea-release-reproducibility",
            "ea-release-supply-chain",
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
            "wheel": [_display_path(root, path) for path in wheel_paths],
            "sdist": [_display_path(root, path) for path in sdist_paths],
            "skill_bundle": _display_path(root, skill_bundle_path),
            "skill_bundle_checksum": _display_path(
                root, skill_bundle_path.with_suffix(".zip.sha256")
            ),
            "install_smoke": _display_path(root, install_smoke_path),
            "reproducibility": _display_path(root, reproducibility_path),
            "sbom": _display_path(root, sbom_path),
            "vulnerability_report": _display_path(root, vulnerability_path),
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
        f"# Experimental Assistant v{__version__} Distribution Checklist",
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
        lines.append(
            f"- [{marker}] `{check['code']}`: {check['description']} ({check['status']})"
        )
    lines.extend(["", "## Release Artifacts", ""])
    manifest = checklist["release_artifacts"]["manifest"]
    lines.append(
        f"- Manifest: `{manifest['path']}` ({'present' if manifest['exists'] else 'missing'})"
    )
    lines.append(
        f"- Wheel: `{', '.join(checklist['release_artifacts']['wheel']) or 'missing'}`"
    )
    lines.append(
        f"- sdist: `{', '.join(checklist['release_artifacts']['sdist']) or 'missing'}`"
    )
    lines.append(
        f"- Codex skill bundle: `{checklist['release_artifacts']['skill_bundle']}`"
    )
    lines.append(
        f"- Skill bundle checksum: `{checklist['release_artifacts']['skill_bundle_checksum']}`"
    )
    lines.append(
        f"- Clean-install evidence: `{checklist['release_artifacts']['install_smoke']}`"
    )
    lines.append(
        f"- Reproducibility evidence: `{checklist['release_artifacts']['reproducibility']}`"
    )
    lines.append(f"- SBOM: `{checklist['release_artifacts']['sbom']}`")
    lines.append(
        f"- Vulnerability report: `{checklist['release_artifacts']['vulnerability_report']}`"
    )
    for archive in checklist["release_artifacts"]["archives"]:
        lines.append(
            f"- Archive: `{archive['path']}` ({archive['verification']['status']})"
        )
        checksum = archive["checksum_sidecar"]
        lines.append(
            f"  - Checksum sidecar: `{checksum['path']}` ({'present' if checksum['exists'] else 'missing'})"
        )
        signature = archive["signature"]
        lines.append(
            f"  - Optional signature: `{signature['path']}` ({signature['status']})"
        )
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
    json_path.write_text(
        json.dumps(checklist, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    md_path.write_text(render_distribution_markdown(checklist), encoding="utf-8")
    return json_path, md_path, checklist


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"Generate an Experimental Assistant v{__version__} package distribution checklist."
    )
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
