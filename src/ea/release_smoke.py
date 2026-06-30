from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


FORBIDDEN_PORTABILITY_PATTERNS = [
    "/Users/geecoe",
    "New project 4",
    "zotero.sqlite",
    "Chrome Profile",
    "institution password",
]
DEFAULT_SCAN_ROOTS = ["README.md", "pyproject.toml", "src", "skills/ea-v0-2", "skill-registry"]
DEFAULT_EXCLUDED_SCAN_PATHS = {
    "src/ea/config/service.py",
    "src/ea/release_smoke.py",
}


@dataclass(frozen=True)
class SmokeStep:
    name: str
    command: list[str]


def _repo_root(path: Path | None = None) -> Path:
    return (path or Path.cwd()).resolve()


def _default_quick_validate_path() -> Path:
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    return codex_home / "skills" / ".system" / "skill-creator" / "scripts" / "quick_validate.py"


def _cli_snippet(argv: list[str]) -> str:
    return f"from ea.cli import main; main({argv!r})"


def build_command_steps(
    root: Path,
    *,
    python: str,
    quick_validate: Path,
    skip_tests: bool = False,
    skip_skill_validation: bool = False,
    skip_cli_sanity: bool = False,
) -> list[SmokeStep]:
    steps: list[SmokeStep] = []
    if not skip_tests:
        steps.append(SmokeStep("pytest", [python, "-m", "pytest"]))
    if not skip_skill_validation:
        steps.append(SmokeStep("skill_validation", [python, str(quick_validate), "skills/ea-v0-2"]))
    if not skip_cli_sanity:
        steps.extend(
            [
                SmokeStep("cli_help", [python, "-c", _cli_snippet(["--help"])]),
                SmokeStep("cli_export_help", [python, "-c", _cli_snippet(["export", "--help"])]),
                SmokeStep("cli_eval_help", [python, "-c", _cli_snippet(["eval", "--help"])]),
                SmokeStep("release_manifest_help", [python, "-m", "ea.release_manifest", "--help"]),
                SmokeStep("release_package_help", [python, "-m", "ea.release_package", "--help"]),
                SmokeStep("release_package_verify_help", [python, "-c", "from ea.release_package import verify_main; verify_main(['--help'])"]),
                SmokeStep("release_signature_keygen_help", [python, "-c", "from ea.release_signature import keygen_main; keygen_main(['--help'])"]),
                SmokeStep("release_signature_sign_help", [python, "-c", "from ea.release_signature import sign_main; sign_main(['--help'])"]),
                SmokeStep("release_signature_verify_help", [python, "-c", "from ea.release_signature import verify_main; verify_main(['--help'])"]),
            ]
        )
    return steps


def smoke_env(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    src = str(root / "src")
    env["PYTHONPATH"] = src if not env.get("PYTHONPATH") else f"{src}{os.pathsep}{env['PYTHONPATH']}"
    env["EA_PUBLIC_RELEASE_SMOKE"] = "1"
    return env


def _tail(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def run_command_step(step: SmokeStep, *, root: Path, env: dict[str, str]) -> dict[str, Any]:
    completed = subprocess.run(
        step.command,
        cwd=root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "name": step.name,
        "status": "pass" if completed.returncode == 0 else "fail",
        "returncode": completed.returncode,
        "command": step.command,
        "stdout_tail": _tail(completed.stdout),
        "stderr_tail": _tail(completed.stderr),
    }


def _iter_scan_files(root: Path, scan_roots: Iterable[str], excluded_paths: set[str]) -> Iterable[Path]:
    for rel in scan_roots:
        path = root / rel
        if not path.exists():
            continue
        if path.is_file():
            candidates = [path]
        else:
            candidates = sorted(item for item in path.rglob("*") if item.is_file())
        for candidate in candidates:
            rel_path = candidate.relative_to(root).as_posix()
            if rel_path in excluded_paths:
                continue
            if any(part in {".git", ".venv", "__pycache__", ".pytest_cache"} for part in candidate.parts):
                continue
            yield candidate


def run_portability_scan(
    root: Path,
    *,
    scan_roots: Iterable[str] = DEFAULT_SCAN_ROOTS,
    excluded_paths: set[str] | None = None,
    forbidden_patterns: Iterable[str] = FORBIDDEN_PORTABILITY_PATTERNS,
) -> dict[str, Any]:
    excluded = set(DEFAULT_EXCLUDED_SCAN_PATHS)
    if excluded_paths:
        excluded.update(excluded_paths)
    findings = []
    for path in _iter_scan_files(root, scan_roots, excluded):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in forbidden_patterns:
            if pattern in text:
                findings.append(
                    {
                        "path": path.relative_to(root).as_posix(),
                        "pattern": pattern,
                    }
                )
    return {
        "name": "portability_scan",
        "status": "pass" if not findings else "fail",
        "scan_roots": list(scan_roots),
        "excluded_paths": sorted(excluded),
        "forbidden_patterns": list(forbidden_patterns),
        "findings": findings,
    }


def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    root = _repo_root(args.root)
    quick_validate = args.quick_validate or _default_quick_validate_path()
    command_steps = build_command_steps(
        root,
        python=args.python,
        quick_validate=quick_validate,
        skip_tests=args.skip_tests,
        skip_skill_validation=args.skip_skill_validation,
        skip_cli_sanity=args.skip_cli_sanity,
    )
    if args.dry_run:
        return {
            "schema_version": "0.2",
            "status": "dry_run",
            "root": str(root),
            "commands": [{"name": step.name, "command": step.command} for step in command_steps],
            "portability_scan": not args.skip_portability_scan,
        }

    env = smoke_env(root)
    results = [run_command_step(step, root=root, env=env) for step in command_steps]
    if not args.skip_portability_scan:
        results.append(run_portability_scan(root))
    status = "pass" if all(result["status"] == "pass" for result in results) else "fail"
    return {
        "schema_version": "0.2",
        "status": status,
        "root": str(root),
        "results": results,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run EA v0.2 public-release smoke checks.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--quick-validate", type=Path)
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--skip-skill-validation", action="store_true")
    parser.add_argument("--skip-cli-sanity", action="store_true")
    parser.add_argument("--skip-portability-scan", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_smoke(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] in {"pass", "dry_run"}:
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
