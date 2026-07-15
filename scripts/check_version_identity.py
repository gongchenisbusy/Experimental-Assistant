from __future__ import annotations

import json
from pathlib import Path
import sys
import tomllib

import yaml


EXPECTED_VERSION = "v0.9.8"
EXPECTED_PACKAGE_VERSION = "0.9.8"
EXPECTED_DISTRIBUTION = "experimental-assistant"
EXPECTED_PRIMARY_SKILL = "ea"
EXPECTED_COMPATIBILITY_SKILL = "ea-v0-2"
SCAN_ROOTS = [
    "README.md",
    "docs",
    "skills/ea",
    "skills/ea-v0-2/SKILL.md",
    "src/ea",
    "scripts",
    "examples",
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
    "ea-v0-2-0.9.8",
    "ea-v0.9.8-release-manifest",
    "ea-v0.9.8-distribution-checklist",
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
    exact_checks = {
        "pyproject_distribution": pyproject.get("name") == EXPECTED_DISTRIBUTION,
        "pyproject_version": pyproject.get("version") == EXPECTED_PACKAGE_VERSION,
        "pyproject_license": pyproject.get("license") == "Apache-2.0",
        "primary_skill_name": _skill_name(root / "skills" / "ea" / "SKILL.md")
        == EXPECTED_PRIMARY_SKILL,
        "compatibility_skill_name": _skill_name(
            root / "skills" / "ea-v0-2" / "SKILL.md"
        )
        == EXPECTED_COMPATIBILITY_SKILL,
        "source_version": f'__version__ = "{EXPECTED_PACKAGE_VERSION}"'
        in (root / "src" / "ea" / "__init__.py").read_text(encoding="utf-8"),
        "identity_distribution": f'DISTRIBUTION_NAME = "{EXPECTED_DISTRIBUTION}"'
        in (root / "src" / "ea" / "identity.py").read_text(encoding="utf-8"),
        "identity_primary_skill": f'SKILL_NAME = "{EXPECTED_PRIMARY_SKILL}"'
        in (root / "src" / "ea" / "identity.py").read_text(encoding="utf-8"),
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
        "forbidden_findings": findings,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if status == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
