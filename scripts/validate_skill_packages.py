from __future__ import annotations

import json
from pathlib import Path
import re
import sys

import yaml


SKILLS = {"ea": 10 * 1024, "ea-v0-2": 2 * 1024}
REFERENCE_RE = re.compile(r"`(references/[^`]+)`")


def _validate_skill(root: Path, name: str, byte_budget: int) -> dict:
    skill_root = root / "skills" / name
    skill_md = skill_root / "SKILL.md"
    failures: list[str] = []
    if not skill_md.is_file():
        return {"skill": name, "status": "fail", "failures": ["missing_SKILL.md"]}
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        failures.append("missing_frontmatter")
        frontmatter = {}
    else:
        try:
            frontmatter = yaml.safe_load(text.split("---\n", 2)[1]) or {}
        except (IndexError, yaml.YAMLError):
            frontmatter = {}
            failures.append("invalid_frontmatter")
    if frontmatter.get("name") != name:
        failures.append("name_folder_mismatch")
    description = str(frontmatter.get("description") or "")
    if not description or len(description) > 1024:
        failures.append("invalid_description")
    if skill_md.stat().st_size > byte_budget:
        failures.append("byte_budget_exceeded")
    if len(text.splitlines()) > 500:
        failures.append("line_budget_exceeded")
    agent_path = skill_root / "agents" / "openai.yaml"
    if not agent_path.is_file():
        failures.append("missing_agents_openai_yaml")
    else:
        interface = (yaml.safe_load(agent_path.read_text(encoding="utf-8")) or {}).get("interface", {})
        for field in ("display_name", "short_description", "default_prompt"):
            if not interface.get(field):
                failures.append(f"missing_interface_{field}")
    missing_references = sorted(
        reference for reference in set(REFERENCE_RE.findall(text)) if not (skill_root / reference).is_file()
    )
    failures.extend(f"missing_reference:{reference}" for reference in missing_references)
    return {
        "skill": name,
        "status": "pass" if not failures else "fail",
        "size_bytes": skill_md.stat().st_size,
        "line_count": len(text.splitlines()),
        "byte_budget": byte_budget,
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    root = Path(args[0]).resolve() if args else Path.cwd().resolve()
    results = [_validate_skill(root, name, budget) for name, budget in SKILLS.items()]
    status = "pass" if all(result["status"] == "pass" for result in results) else "fail"
    print(json.dumps({"check": "skill_packages", "status": status, "results": results}, indent=2))
    return 0 if status == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
