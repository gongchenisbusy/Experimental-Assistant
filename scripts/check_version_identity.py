from __future__ import annotations

import json
import sys
from pathlib import Path


EXPECTED_VERSION = "v0.9.5"
EXPECTED_PACKAGE_VERSION = "0.9.5"
SCAN_ROOTS = [
    "README.md",
    "docs",
    "skills/ea-v0-2",
    "src/ea",
    "scripts",
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
    "ea-v0.9-rc",
    "EAv0-2",
    "eav0-2",
]


def _iter_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for rel in SCAN_ROOTS:
        path = root / rel
        if not path.exists():
            continue
        candidates = [path] if path.is_file() else sorted(item for item in path.rglob("*") if item.is_file())
        for candidate in candidates:
            rel_path = candidate.relative_to(root).as_posix()
            if rel_path in EXCLUDED_PATHS:
                continue
            if any(part in {".git", ".venv", "__pycache__", ".pytest_cache"} for part in candidate.parts):
                continue
            if candidate.suffix in {".pyc", ".zip", ".png", ".jpg", ".pdf"}:
                continue
            files.append(candidate)
    return files


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    root = Path(args[0]).resolve() if args else Path.cwd().resolve()
    findings = []
    expected_hits = {"version": 0, "package_version": 0}
    for path in _iter_files(root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = path.relative_to(root).as_posix()
        expected_hits["version"] += text.count(EXPECTED_VERSION)
        expected_hits["package_version"] += text.count(EXPECTED_PACKAGE_VERSION)
        for forbidden in FORBIDDEN_STRINGS:
            if forbidden in text:
                findings.append({"path": rel, "forbidden": forbidden})
    result = {
        "check": "version_identity",
        "status": "pass" if not findings and all(expected_hits.values()) else "fail",
        "expected_version": EXPECTED_VERSION,
        "expected_package_version": EXPECTED_PACKAGE_VERSION,
        "expected_hits": expected_hits,
        "forbidden_findings": findings,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
