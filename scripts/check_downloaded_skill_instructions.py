from __future__ import annotations

import json
import sys
from pathlib import Path


REQUIRED_FILES = [
    Path("skills/ea-v0-2/SKILL.md"),
    Path("skills/ea-v0-2/agents/openai.yaml"),
    Path("skills/ea-v0-2/references/cli-command-index.md"),
    Path("docs/PUBLIC_INSTALL_AND_CODEX_SKILL_SETUP.md"),
]
REQUIRED_STRINGS = [
    "Experimental Assistant v0.9.5",
    "Internal compatibility id",
    "ea onboarding post-install",
    "ea literature setup-preflight",
    "ea memory refresh-project",
    "ea memory show-project",
    "ea estimate workflow",
    "ea estimate reminders",
    "ea review promote",
    "--confirm-large-work",
]
FORBIDDEN_STRINGS = [
    "EA v0.9 RC",
    "v0.9 RC",
    "v0.9-rc1",
    "0.9.0rc1",
    "0.9rc1",
]


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    root = Path(args[0]).resolve() if args else Path.cwd().resolve()
    missing_files = [path.as_posix() for path in REQUIRED_FILES if not (root / path).exists()]
    combined = ""
    file_records = []
    for path in REQUIRED_FILES:
        full_path = root / path
        if not full_path.exists():
            continue
        text = full_path.read_text(encoding="utf-8", errors="ignore")
        combined += f"\n\n<!-- {path.as_posix()} -->\n{text}"
        file_records.append({"path": path.as_posix(), "size_bytes": full_path.stat().st_size})
    missing_strings = [item for item in REQUIRED_STRINGS if item not in combined]
    forbidden_findings = [
        {"forbidden": item}
        for item in FORBIDDEN_STRINGS
        if item in combined
    ]
    result = {
        "check": "downloaded_skill_instructions",
        "status": "pass" if not missing_files and not missing_strings and not forbidden_findings else "fail",
        "files": file_records,
        "missing_files": missing_files,
        "missing_strings": missing_strings,
        "forbidden_findings": forbidden_findings,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
