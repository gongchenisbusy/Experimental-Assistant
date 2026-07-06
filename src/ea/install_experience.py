from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from importlib import metadata
from pathlib import Path
from typing import Any

from ea import __version__


PRODUCT_NAME = "Experimental Assistant"
DISPLAY_VERSION = "v0.9.6"
PUBLIC_VERSION = f"{PRODUCT_NAME} {DISPLAY_VERSION}"
PACKAGE_NAME = "ea-v0-2"
RELEASE_LABEL = "v0.9.6"
SKILL_NAME = "ea-v0-2"
SKILL_INVOCATION = "$ea-v0-2"
REPOSITORY_URL = "https://github.com/gongchenisbusy/Experimental-Assistant"
MIN_PYTHON = (3, 11)


def _python_version_tuple() -> tuple[int, int, int]:
    return sys.version_info[:3]


def _python_version_label() -> str:
    return ".".join(str(part) for part in _python_version_tuple())


def _package_version() -> str:
    return __version__


def _installed_distribution_version() -> str | None:
    try:
        return metadata.version(PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        return None


def identity_record() -> dict[str, Any]:
    record = {
        "product": PRODUCT_NAME,
        "display_name": PRODUCT_NAME,
        "display_version": PUBLIC_VERSION,
        "public_version": PUBLIC_VERSION,
        "package_compatibility_name": PACKAGE_NAME,
        "compatibility_id": PACKAGE_NAME,
        "package_version": _package_version(),
        "release_label": RELEASE_LABEL,
        "skill_folder": SKILL_NAME,
        "skill_invocation": SKILL_INVOCATION,
        "repository_url": REPOSITORY_URL,
    }
    installed_version = _installed_distribution_version()
    if installed_version and installed_version != record["package_version"]:
        record["installed_distribution_version"] = installed_version
        record["version_warning"] = (
            "Installed package metadata differs from EA code version; reinstall the EA CLI if this persists outside a development checkout."
        )
    return record


def python_preflight_record() -> dict[str, Any]:
    version = _python_version_tuple()
    ok = version >= MIN_PYTHON
    return {
        "name": "python_version",
        "status": "pass" if ok else "fail",
        "python": sys.executable,
        "version": _python_version_label(),
        "required": f">={MIN_PYTHON[0]}.{MIN_PYTHON[1]}",
        "message": (
            "Python version is compatible."
            if ok
            else "Python 3.11 or newer is required before installing EA dependencies."
        ),
        "next_steps": []
        if ok
        else [
            "Install a newer Python, for example: uv python install 3.12",
            f"Then install EA with: uv tool install --python 3.12 git+{REPOSITORY_URL}.git@{RELEASE_LABEL}",
            "If using a venv, create it with a Python 3.11+ interpreter before running pip install.",
        ],
    }


def codex_home(default: Path | None = None) -> Path:
    return Path(os.environ.get("CODEX_HOME") or default or Path.home() / ".codex").expanduser()


def codex_skills_dir(codex_home_path: Path | None = None) -> Path:
    return (codex_home_path or codex_home()) / "skills"


def default_skill_target(codex_home_path: Path | None = None) -> Path:
    return codex_skills_dir(codex_home_path) / SKILL_NAME


def _repo_root_candidates(start: Path | None = None) -> list[Path]:
    roots: list[Path] = []
    cwd = (start or Path.cwd()).resolve()
    roots.extend([cwd, *cwd.parents])
    package_root = Path(__file__).resolve()
    roots.extend(package_root.parents)
    deduped: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if root not in seen:
            seen.add(root)
            deduped.append(root)
    return deduped


def find_local_skill_source(start: Path | None = None) -> Path | None:
    for root in _repo_root_candidates(start):
        candidate = root / "skills" / SKILL_NAME
        if (candidate / "SKILL.md").exists():
            return candidate
    return None


def quick_validate_path(codex_home_path: Path | None = None) -> Path | None:
    home = codex_home_path or codex_home()
    candidates = [
        home / "skills" / ".system" / "skill-creator" / "scripts" / "quick_validate.py",
        Path.home() / ".codex" / "skills" / ".system" / "skill-creator" / "scripts" / "quick_validate.py",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def validate_skill(skill_path: Path, *, validator: Path | None = None) -> dict[str, Any]:
    validator_path = validator or quick_validate_path()
    if validator_path is None or not validator_path.exists():
        return {
            "name": "codex_skill_validation",
            "status": "warning",
            "path": str(skill_path),
            "validator": None,
            "message": "Codex skill quick_validate.py was not found; copied skill could not be automatically validated.",
        }
    completed = subprocess.run(
        [sys.executable, str(validator_path), str(skill_path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "name": "codex_skill_validation",
        "status": "pass" if completed.returncode == 0 else "fail",
        "path": str(skill_path),
        "validator": str(validator_path),
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def _clone_skill_source(release_ref: str) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    temp = tempfile.TemporaryDirectory(prefix="ea-skill-install-")
    checkout = Path(temp.name) / "Experimental-Assistant"
    completed = subprocess.run(
        ["git", "clone", "--depth", "1", "--branch", release_ref, f"{REPOSITORY_URL}.git", str(checkout)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        temp.cleanup()
        raise RuntimeError(
            "Could not fetch the EA skill from GitHub. "
            "Run from a repository checkout or pass --source /path/to/skills/ea-v0-2.\n"
            f"git stderr: {completed.stderr.strip()}"
        )
    source = checkout / "skills" / SKILL_NAME
    if not (source / "SKILL.md").exists():
        temp.cleanup()
        raise FileNotFoundError(f"Fetched repository does not contain skills/{SKILL_NAME}/SKILL.md")
    return temp, source


def install_codex_skill(
    *,
    source: Path | None = None,
    codex_home_path: Path | None = None,
    validator: Path | None = None,
    backup_existing: bool = True,
    allow_github_fetch: bool = True,
    release_ref: str = RELEASE_LABEL,
    now: datetime | None = None,
) -> dict[str, Any]:
    identity = identity_record()
    home = codex_home_path or codex_home()
    skills_dir = codex_skills_dir(home)
    target = default_skill_target(home)
    source_path = source.resolve() if source else find_local_skill_source()
    temp_checkout: tempfile.TemporaryDirectory[str] | None = None
    source_origin = "local"
    if source_path is None and allow_github_fetch:
        temp_checkout, source_path = _clone_skill_source(release_ref)
        source_origin = f"github:{release_ref}"
    if source_path is None:
        raise FileNotFoundError(
            f"Could not locate skills/{SKILL_NAME}. Run from an EA checkout, pass --source, "
            "or allow GitHub fetch."
        )
    if not (source_path / "SKILL.md").exists():
        raise FileNotFoundError(f"Skill source is missing SKILL.md: {source_path}")

    try:
        skills_dir.mkdir(parents=True, exist_ok=True)
        backup_path: Path | None = None
        replaced_existing = target.exists()
        if replaced_existing:
            if backup_existing:
                stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
                backup_root = skills_dir / ".backups"
                backup_root.mkdir(parents=True, exist_ok=True)
                backup_path = backup_root / f"{SKILL_NAME}-{stamp}"
                counter = 1
                while backup_path.exists():
                    backup_path = backup_root / f"{SKILL_NAME}-{stamp}-{counter}"
                    counter += 1
                shutil.move(str(target), str(backup_path))
            else:
                shutil.rmtree(target)
        shutil.copytree(source_path, target)
        validation = validate_skill(target, validator=validator)
        legacy_skill = skills_dir / "ea-v0-1"
        checks = [validation]
        status = "fail" if any(check["status"] == "fail" for check in checks) else "pass"
        return {
            "schema_version": "0.9",
            "check_type": "ea_codex_skill_install",
            "status": status,
            "identity": identity,
            "source": {"path": str(source_path), "origin": source_origin},
            "codex_home": str(home),
            "target": str(target),
            "backup": str(backup_path) if backup_path else None,
            "replaced_existing": replaced_existing,
            "legacy_skill_detected": legacy_skill.exists(),
            "legacy_skill_note": (
                f"Detected existing ea-v0-1. {PUBLIC_VERSION} uses the ea-v0-2 internal compatibility skill path; old projects and old skills were not modified."
                if legacy_skill.exists()
                else None
            ),
            "validation": validation,
            "next_steps": [
                f"Restart Codex before using {PRODUCT_NAME} in a new thread.",
                f"In a new Codex thread, invoke the compatibility skill as: {SKILL_INVOCATION}",
                "Run `ea onboarding post-install` for the stable first-run summary.",
                "Run `ea install-check` to verify CLI and Codex skill readiness.",
            ],
        }
    finally:
        if temp_checkout is not None:
            temp_checkout.cleanup()


def _ea_executable() -> str | None:
    return shutil.which("ea")


def _repo_example_path(start: Path | None = None) -> Path | None:
    for root in _repo_root_candidates(start):
        candidate = root / "examples" / "public-raman-project"
        if candidate.exists():
            return candidate
    return None


def run_public_example_check(example_workspace: Path | None = None) -> dict[str, Any]:
    workspace = example_workspace or _repo_example_path()
    if workspace is None or not workspace.exists():
        return {
            "name": "public_example_healthcheck",
            "status": "warning",
            "workspace": str(example_workspace) if example_workspace else None,
            "message": "Public Raman example was not found. Run this check from a repository checkout or pass --example-workspace.",
        }
    from ea.healthcheck import run_healthcheck

    result = run_healthcheck(workspace)
    return {
        "name": "public_example_healthcheck",
        "status": "pass" if result.get("status") == "pass" else "fail",
        "workspace": str(workspace),
        "healthcheck_status": result.get("status"),
        "error_count": result.get("error_count"),
        "warning_count": result.get("warning_count"),
    }


def install_check(
    *,
    codex_home_path: Path | None = None,
    skill_path: Path | None = None,
    validator: Path | None = None,
    run_example: bool = False,
    example_workspace: Path | None = None,
    skip_codex_skill: bool = False,
) -> dict[str, Any]:
    identity = identity_record()
    home = codex_home_path or codex_home()
    target = skill_path or default_skill_target(home)
    checks: list[dict[str, Any]] = []

    checks.append(python_preflight_record())
    checks.append(
        {
            "name": "ea_package",
            "status": "pass",
            "package": PACKAGE_NAME,
            "version": _package_version(),
            "installed_distribution_version": _installed_distribution_version(),
            "public_version": PUBLIC_VERSION,
            "release_label": RELEASE_LABEL,
        }
    )
    exe = _ea_executable()
    checks.append(
        {
            "name": "ea_cli",
            "status": "pass" if exe else "fail",
            "path": exe,
            "message": "EA CLI is on PATH." if exe else "EA CLI was not found on PATH.",
            "next_steps": []
            if exe
            else [f"Install with: uv tool install --python 3.12 git+{REPOSITORY_URL}.git@{RELEASE_LABEL}"],
        }
    )
    if not skip_codex_skill:
        exists = target.exists()
        checks.append(
            {
                "name": "codex_skill_path",
                "status": "pass" if exists else "fail",
                "path": str(target),
                "message": "Codex skill folder exists." if exists else "Codex skill folder is missing.",
                "next_steps": [] if exists else ["Run `ea codex install-skill`."],
            }
        )
        if exists:
            checks.append(validate_skill(target, validator=validator))
    if run_example:
        checks.append(run_public_example_check(example_workspace))

    failures = [check for check in checks if check["status"] == "fail"]
    warnings = [check for check in checks if check["status"] == "warning"]
    status = "fail" if failures else "warning" if warnings else "pass"
    return {
        "schema_version": "0.9",
        "check_type": "ea_install_check",
        "status": status,
        "identity": identity,
        "codex_home": str(home),
        "skill_path": None if skip_codex_skill else str(target),
        "checks": checks,
        "next_steps": [
            f"In a new Codex thread, invoke the compatibility skill as: {SKILL_INVOCATION}",
            "Run `ea onboarding post-install` for the stable first-run summary.",
            "Restart Codex after installing or replacing the skill.",
            "Use `ea init-project` for the first real project after the install check passes.",
        ],
    }


def render_install_summary(result: dict[str, Any]) -> str:
    identity = result["identity"]
    lines = [
        f"{PRODUCT_NAME} installation check: {result['status']}",
        "",
        f"Product: {identity['product']}",
        f"Version: {identity['display_version']}",
        f"Package version: {identity['package_version']}",
        f"Internal compatibility id: {identity['compatibility_id']}",
        f"Codex compatibility invocation: {identity['skill_invocation']}",
        "",
        "Checks:",
    ]
    for check in result.get("checks", []):
        label = check.get("name", "check")
        detail = check.get("message") or check.get("path") or check.get("version") or ""
        lines.append(f"- {label}: {check.get('status')} {detail}".rstrip())
    lines.extend(["", "Next steps:"])
    for step in result.get("next_steps", []):
        lines.append(f"- {step}")
    return "\n".join(lines)


def render_install_skill_summary(result: dict[str, Any]) -> str:
    identity = result["identity"]
    lines = [
        f"Installed {identity['product']} ({identity['public_version']}).",
        f"Package version: {identity['package_version']}.",
        f"Internal compatibility id: {identity['compatibility_id']}.",
        f"Codex skill: {result['target']}",
        f"Codex compatibility invocation: {identity['skill_invocation']}",
        f"Validation: {result['validation']['status']}",
    ]
    if result.get("backup"):
        lines.append(f"Previous {SKILL_NAME} backup: {result['backup']}")
    if result.get("legacy_skill_note"):
        lines.append(result["legacy_skill_note"])
    lines.append("Restart Codex before using this skill in a new thread.")
    lines.append("Run `ea onboarding post-install` to see the stable first-run summary.")
    return "\n".join(lines)


def onboarding_post_install_record(*, event: str = "install", lang: str = "zh") -> dict[str, Any]:
    if event not in {"install", "update"}:
        raise ValueError("event must be install or update")
    if lang not in {"zh", "en"}:
        raise ValueError("lang must be zh or en")
    identity = identity_record()
    return {
        "schema_version": "0.9.6",
        "message_type": "ea_post_install_onboarding",
        "event": event,
        "language": lang,
        "identity": identity,
        "capabilities": [
            "consult_or_plan_without_project_writes_by_default",
            "record_review_gated_project_artifacts_after_confirmation",
            "process_raman_pl_xrd_ftir_uv_vis_xps_electrochemistry_thermal_and_image_records",
            "generate_reports_exports_traceability_and_project_briefs",
            "manage_local_literature_state_with_user_permission",
            "maintain_lightweight_project_working_memory",
        ],
        "recommended_first_checks": [
            "ea version --json",
            "ea install-check --json",
            "ea literature setup-preflight /path/to/ea-project",
        ],
        "confirmation_phrase": "确定配置" if lang == "zh" else "Confirm setup",
        "boundaries": [
            "Post-install onboarding does not create EA project files.",
            "Zotero, browser assistance, institution login, and full-text acquisition stay opt-in.",
            "Scientific memory remains review-gated; project working memory is a compact continuation aid.",
            "Large literature/report jobs may ask for confirmation when the estimated work is unusually large.",
        ],
        "compatibility": {
            "compatibility_id": PACKAGE_NAME,
            "skill_folder": SKILL_NAME,
            "skill_invocation": SKILL_INVOCATION,
            "note": "Compatibility identifiers are install paths, not the public EA version.",
        },
    }


def render_onboarding_post_install(record: dict[str, Any]) -> str:
    identity = record["identity"]
    lang = record.get("language", "zh")
    if lang == "en":
        lines = [
            f"{identity['display_version']} is ready.",
            "",
            "What EA can do:",
            "- Answer research workflow questions in consult mode without creating project files by default.",
            "- Initialize and maintain local EA projects after explicit confirmation.",
            "- Process reviewed characterization data and write traceable reports, exports, briefs, and memory candidates.",
            "- Help configure a local literature workflow only after you confirm the scope and access mode.",
            "",
            "Recommended checks:",
        ]
        lines.extend(f"- {command}" for command in record["recommended_first_checks"])
        lines.extend(
            [
                "",
                f"To configure literature support later, say `{record['confirmation_phrase']}` or run the preflight command.",
                f"Internal compatibility id: `{identity['compatibility_id']}`; public version: `{identity['display_version']}`.",
            ]
        )
        return "\n".join(lines)
    lines = [
        f"{identity['display_version']} 已就绪。",
        "",
        "EA 可以做什么：",
        "- 默认先以咨询模式回答研究流程问题，不会自动创建项目文件。",
        "- 在你明确确认后，初始化并维护本地 EA 项目。",
        "- 处理已审核的表征数据，并写入可追踪报告、导出包、项目简报和记忆候选。",
        "- 在你确认范围和访问方式后，协助配置本地文献工作流。",
        "",
        "建议先检查：",
    ]
    lines.extend(f"- `{command}`" for command in record["recommended_first_checks"])
    lines.extend(
        [
            "",
            f"之后如果要配置文献支持，可以回复 `{record['confirmation_phrase']}`，或运行文献预检命令。",
            f"内部兼容标识：`{identity['compatibility_id']}`；公开版本：`{identity['display_version']}`。",
        ]
    )
    return "\n".join(lines)


def build_install_check_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"Check {PUBLIC_VERSION} installation readiness.")
    parser.add_argument("--codex-home", type=Path)
    parser.add_argument("--skill-path", type=Path)
    parser.add_argument("--quick-validate", type=Path)
    parser.add_argument("--run-example-check", action="store_true")
    parser.add_argument("--example-workspace", type=Path)
    parser.add_argument("--skip-codex-skill", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def install_check_main(argv: list[str] | None = None) -> int:
    args = build_install_check_parser().parse_args(argv)
    result = install_check(
        codex_home_path=args.codex_home,
        skill_path=args.skill_path,
        validator=args.quick_validate,
        run_example=args.run_example_check,
        example_workspace=args.example_workspace,
        skip_codex_skill=args.skip_codex_skill,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_install_summary(result))
    return 0 if result["status"] != "fail" else 2


if __name__ == "__main__":
    raise SystemExit(install_check_main())
