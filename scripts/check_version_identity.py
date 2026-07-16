from __future__ import annotations

import json
from pathlib import Path
import sys
import tomllib

import yaml


EXPECTED_VERSION = "v1.0.0"
EXPECTED_PACKAGE_VERSION = "1.0.0"
EXPECTED_DISTRIBUTION = "experimental-assistant"
EXPECTED_PRIMARY_SKILL = "ea"
SCAN_ROOTS = [
    "README.md",
    "CITATION.cff",
    "docs",
    "skills/ea",
    "src/ea",
    "scripts",
    "examples",
    "skill-registry",
    ".github/workflows",
]
EXCLUDED_PATHS = {
    "src/ea/release_smoke.py",
    "scripts/check_version_identity.py",
    "scripts/check_downloaded_skill_instructions.py",
}
FORBIDDEN_STRINGS = [
    "EA v0.9 RC",
    "v0.9 RC",
    "v0.9-rc1",
    "0.9.0rc1",
    "0.9rc1",
    "EAv0-2",
    "eav0-2",
    "EA v0.2 Public",
    "ea-v0-2-0.9.9",
    "ea-v0.9.9-release-manifest",
    "ea-v0.9.9-distribution-checklist",
]


def _iter_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for rel in SCAN_ROOTS:
        path = root / rel
        if not path.exists():
            continue
        candidates = (
            [path]
            if path.is_file()
            else sorted(item for item in path.rglob("*") if item.is_file())
        )
        for candidate in candidates:
            relative = candidate.relative_to(root).as_posix()
            if relative in EXCLUDED_PATHS:
                continue
            if any(
                part in {".git", ".venv", "__pycache__", ".pytest_cache"}
                for part in candidate.parts
            ):
                continue
            if candidate.suffix in {".pyc", ".zip", ".png", ".jpg", ".pdf"}:
                continue
            files.append(candidate)
    return files


def _skill_name(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None
    try:
        return (yaml.safe_load(text.split("---\n", 2)[1]) or {}).get("name")
    except (IndexError, yaml.YAMLError):
        return None


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    root = Path(args[0]).resolve() if args else Path.cwd().resolve()
    findings: list[dict[str, str]] = []
    expected_hits = {"version": 0, "package_version": 0, "distribution": 0}
    for path in _iter_files(root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        relative = path.relative_to(root).as_posix()
        expected_hits["version"] += text.count(EXPECTED_VERSION)
        expected_hits["package_version"] += text.count(EXPECTED_PACKAGE_VERSION)
        expected_hits["distribution"] += text.count(EXPECTED_DISTRIBUTION)
        for forbidden in FORBIDDEN_STRINGS:
            if forbidden in text:
                findings.append({"path": relative, "forbidden": forbidden})

    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    release_package_text = (root / "src" / "ea" / "release_package.py").read_text(
        encoding="utf-8"
    )
    release_signature_text = (root / "src" / "ea" / "release_signature.py").read_text(
        encoding="utf-8"
    )
    citation = yaml.safe_load((root / "CITATION.cff").read_text(encoding="utf-8"))
    skill_text = (root / "skills" / "ea" / "SKILL.md").read_text(encoding="utf-8")
    skill_agent = yaml.safe_load(
        (root / "skills" / "ea" / "agents" / "openai.yaml").read_text(encoding="utf-8")
    )
    historical_checks = {
        "v0_9_9_release_notes_preserved": "Experimental Assistant v0.9.9"
        in (root / "docs" / "V0_9_9_RELEASE_NOTES.md").read_text(encoding="utf-8"),
        "v0_9_9_literature_benchmark_preserved": "literature-pipeline-v0.9.9"
        in (root / "benchmarks" / "literature-v0.9.9.yml").read_text(encoding="utf-8"),
        "v0_9_9_readiness_dossier_preserved": "release_candidate: v0.9.9"
        in (root / "docs" / "V1_0_READINESS_DOSSIER.yml").read_text(encoding="utf-8"),
        "v0_9_9_adr_preserved": "v0.9.9"
        in (
            root
            / "docs"
            / "adr"
            / "0001-v0.9.9-universal-literature-data-and-report-contract.md"
        ).read_text(encoding="utf-8"),
    }
    exact_checks = {
        "pyproject_distribution": pyproject.get("name") == EXPECTED_DISTRIBUTION,
        "pyproject_version": pyproject.get("version") == EXPECTED_PACKAGE_VERSION,
        "pyproject_license": pyproject.get("license") == "Apache-2.0",
        "pyproject_stable_classifier": "Development Status :: 5 - Production/Stable"
        in pyproject.get("classifiers", []),
        "citation_version": str(citation.get("version")) == EXPECTED_PACKAGE_VERSION,
        "citation_release_date": str(citation.get("date-released")) == "2026-07-17",
        "primary_skill_name": _skill_name(root / "skills" / "ea" / "SKILL.md")
        == EXPECTED_PRIMARY_SKILL,
        "primary_skill_version": "Experimental Assistant v1.0.0" in skill_text,
        "primary_skill_agent_version": "v1.0.0"
        in str((skill_agent.get("interface") or {}).get("short_description") or ""),
        "compatibility_skill_removed": not (root / "skills" / "ea-v0-2").exists(),
        "source_version": f'__version__ = "{EXPECTED_PACKAGE_VERSION}"'
        in (root / "src" / "ea" / "__init__.py").read_text(encoding="utf-8"),
        "identity_distribution": f'DISTRIBUTION_NAME = "{EXPECTED_DISTRIBUTION}"'
        in (root / "src" / "ea" / "identity.py").read_text(encoding="utf-8"),
        "identity_primary_skill": f'SKILL_NAME = "{EXPECTED_PRIMARY_SKILL}"'
        in (root / "src" / "ea" / "identity.py").read_text(encoding="utf-8"),
        "release_package_check_type": 'CURRENT_RELEASE_PACKAGE_TYPE = "ea_v1_release_package"'
        in release_package_text,
        "release_package_legacy_type": '"0.9.9": "ea_v0_9_9_release_package"'
        in release_package_text,
        "release_signature_type": 'SIGNATURE_TYPE = "ea_v1_release_package_signature"'
        in release_signature_text,
        "release_signature_legacy_type": '"ea_v0_9_9_release_package_signature"'
        in release_signature_text,
        "release_signature_check_type": '"check_type": SIGNATURE_TYPE'
        in release_signature_text,
        **historical_checks,
    }
    status = (
        "pass"
        if not findings and all(expected_hits.values()) and all(exact_checks.values())
        else "fail"
    )
    result = {
        "check": "version_identity",
        "status": status,
        "expected_version": EXPECTED_VERSION,
        "expected_package_version": EXPECTED_PACKAGE_VERSION,
        "expected_distribution": EXPECTED_DISTRIBUTION,
        "expected_hits": expected_hits,
        "exact_checks": exact_checks,
        "historical_identity_checks": historical_checks,
        "forbidden_findings": findings,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if status == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
