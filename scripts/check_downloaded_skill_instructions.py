from __future__ import annotations

import json
from pathlib import Path
import sys


REQUIRED_FILES = [
    Path("skills/ea/SKILL.md"),
    Path("skills/ea/agents/openai.yaml"),
    Path("skills/ea/references/cli-command-index.md"),
    Path("skills/ea/references/routing-index.yml"),
    Path("skills/ea/references/capability-maturity.md"),
    Path("skills/ea/references/literature-data-extraction.md"),
    Path("docs/PUBLIC_INSTALL_AND_CODEX_SKILL_SETUP.md"),
]
REQUIRED_STRINGS = [
    "Experimental Assistant v0.9.8",
    "$ea",
    "ea setup",
    "ea doctor",
    "ea update",
    "ea rollback",
    "ea import preview",
    "ea migrate plan",
    "ea literature setup-preflight",
    "ea brief project",
    "references/routing-index.yml",
    "references/literature-data-extraction.md",
]
FORBIDDEN_STRINGS = ["EA v0.9 RC", "v0.9 RC", "v0.9-rc1", "0.9.0rc1", "0.9rc1"]


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    root = Path(args[0]).resolve() if args else Path.cwd().resolve()
    missing_files = [
        path.as_posix() for path in REQUIRED_FILES if not (root / path).is_file()
    ]
    combined = ""
    files = []
    for path in REQUIRED_FILES:
        full = root / path
        if not full.is_file():
            continue
        text = full.read_text(encoding="utf-8", errors="ignore")
        combined += f"\n\n<!-- {path.as_posix()} -->\n{text}"
        files.append({"path": path.as_posix(), "size_bytes": full.stat().st_size})
    missing_strings = [value for value in REQUIRED_STRINGS if value not in combined]
    forbidden_findings = [
        {"forbidden": value} for value in FORBIDDEN_STRINGS if value in combined
    ]
    status = (
        "pass"
        if not missing_files and not missing_strings and not forbidden_findings
        else "fail"
    )
    print(
        json.dumps(
            {
                "check": "downloaded_skill_instructions",
                "status": status,
                "files": files,
                "missing_files": missing_files,
                "missing_strings": missing_strings,
                "forbidden_findings": forbidden_findings,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if status == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
