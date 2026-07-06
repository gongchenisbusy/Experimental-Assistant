from __future__ import annotations

import argparse
import json
import os
import re
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
DEFAULT_SCAN_ROOTS = ["README.md", "pyproject.toml", "src", "docs", "skills/ea-v0-2", "skill-registry", "examples"]
DEFAULT_EXCLUDED_SCAN_PATHS = {
    "src/ea/config/service.py",
    "src/ea/release_smoke.py",
}
PUBLIC_EXAMPLE_PROJECTS = [
    ("public_example_raman", "examples/public-raman-project"),
    ("public_example_ftir_source", "examples/public-ftir-assignment-project"),
    ("public_example_uv_vis", "examples/public-uv-vis-project"),
    ("public_example_xps_be", "examples/public-xps-be-project"),
]
SECRET_KEY_RE = re.compile(
    r"""
    \b
    (?P<key>
      api[_-]?key
      | access[_-]?token
      | refresh[_-]?token
      | auth[_-]?token
      | bearer[_-]?token
      | token
      | password
      | passphrase
      | pwd
      | secret
      | cookie
      | session(?:[_-]?(?:id|token))?
      | authorization
      | credential
    )
    \b
    \s*[:=]\s*
    (?P<quote>['"]?)
    (?P<value>[^'"\s#,\]}]+)
    (?P=quote)
    """,
    re.IGNORECASE | re.VERBOSE,
)
TOKEN_LITERAL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("openai_style_token", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("jwt_token", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
]
PLACEHOLDER_VALUE_FRAGMENTS = {
    "<",
    ">",
    "example",
    "placeholder",
    "redacted",
    "your-",
    "your_",
    "changeme",
    "change-me",
    "xxxx",
    "dummy",
    "sample",
    "not-set",
    "not_applicable",
}
PLACEHOLDER_VALUES = {
    "",
    "none",
    "null",
    "true",
    "false",
    "password",
    "passphrase",
    "token",
    "secret",
    "api_key",
    "apikey",
    "credential",
    "credentials",
    "value",
    "env",
}
VARIABLE_REFERENCE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?(?:\))?$")


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
    return f"from ea.cli import main; raise SystemExit(main({argv!r}))"


def build_command_steps(
    root: Path,
    *,
    python: str,
    quick_validate: Path,
    skip_tests: bool = False,
    skip_skill_validation: bool = False,
    skip_cli_sanity: bool = False,
    skip_public_examples: bool = False,
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
                SmokeStep("cli_global_version", [python, "-c", _cli_snippet(["--version"])]),
                SmokeStep("cli_version_help", [python, "-c", _cli_snippet(["version", "--help"])]),
                SmokeStep("cli_install_check_help", [python, "-c", _cli_snippet(["install-check", "--help"])]),
                SmokeStep("cli_codex_install_skill_help", [python, "-c", _cli_snippet(["codex", "install-skill", "--help"])]),
                SmokeStep("version_identity_check", [python, "scripts/check_version_identity.py"]),
                SmokeStep("downloaded_skill_instruction_check", [python, "scripts/check_downloaded_skill_instructions.py"]),
                SmokeStep("cli_export_help", [python, "-c", _cli_snippet(["export", "--help"])]),
                SmokeStep("cli_eval_help", [python, "-c", _cli_snippet(["eval", "--help"])]),
                SmokeStep("install_check_console_help", [python, "-m", "ea.install_experience", "--help"]),
                SmokeStep("release_manifest_help", [python, "-m", "ea.release_manifest", "--help"]),
                SmokeStep("release_package_help", [python, "-m", "ea.release_package", "--help"]),
                SmokeStep("release_package_verify_help", [python, "-c", "from ea.release_package import verify_main; verify_main(['--help'])"]),
                SmokeStep("release_signature_keygen_help", [python, "-c", "from ea.release_signature import keygen_main; keygen_main(['--help'])"]),
                SmokeStep("release_signature_sign_help", [python, "-c", "from ea.release_signature import sign_main; sign_main(['--help'])"]),
                SmokeStep("release_signature_verify_help", [python, "-c", "from ea.release_signature import verify_main; verify_main(['--help'])"]),
                SmokeStep("release_distribution_checklist_help", [python, "-c", "from ea.release_distribution import main; main(['--help'])"]),
            ]
        )
    if not skip_public_examples:
        for prefix, project in PUBLIC_EXAMPLE_PROJECTS:
            steps.append(SmokeStep(f"{prefix}_healthcheck", [python, "-c", _cli_snippet(["healthcheck", project])]))
            steps.append(
                SmokeStep(
                    f"{prefix}_eval",
                    [python, "-c", _cli_snippet(["eval", "project", project, "--no-write"])],
                )
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


def _line_preview_with_redaction(line: str, start: int, end: int) -> str:
    redacted = f"{line[:start]}[REDACTED]{line[end:]}"
    redacted = redacted.strip()
    return redacted if len(redacted) <= 220 else f"{redacted[:217]}..."


def _normalized_secret_value(value: str) -> str:
    return value.strip().strip("`'\";,)]}")


def _is_placeholder_secret_value(value: str) -> bool:
    normalized = _normalized_secret_value(value)
    lowered = normalized.lower()
    if lowered in PLACEHOLDER_VALUES:
        return True
    return any(fragment in lowered for fragment in PLACEHOLDER_VALUE_FRAGMENTS)


def _looks_like_variable_reference(value: str) -> bool:
    normalized = _normalized_secret_value(value)
    if not normalized:
        return True
    return bool(VARIABLE_REFERENCE_RE.fullmatch(normalized))


def _is_probable_secret_assignment(match: re.Match[str]) -> bool:
    value = _normalized_secret_value(match.group("value"))
    if _is_placeholder_secret_value(value):
        return False
    if any(pattern.search(value) for _, pattern in TOKEN_LITERAL_PATTERNS):
        return False
    if match.group("quote"):
        return len(value) >= 6
    if "(" in value or ")" in value:
        return False
    return not _looks_like_variable_reference(value) and len(value) >= 6


def _secret_assignment_findings(root: Path, path: Path, text: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for match in SECRET_KEY_RE.finditer(line):
            if not _is_probable_secret_assignment(match):
                continue
            findings.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "line": line_number,
                    "detector": "secret_assignment",
                    "key": match.group("key"),
                    "preview": _line_preview_with_redaction(line, match.start("value"), match.end("value")),
                    "remediation": "Remove the value from public artifacts; use a placeholder or user-supplied local config path instead.",
                }
            )
    return findings


def _token_literal_findings(root: Path, path: Path, text: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for detector, pattern in TOKEN_LITERAL_PATTERNS:
            for match in pattern.finditer(line):
                if _is_placeholder_secret_value(match.group(0)):
                    continue
                findings.append(
                    {
                        "path": path.relative_to(root).as_posix(),
                        "line": line_number,
                        "detector": detector,
                        "preview": _line_preview_with_redaction(line, match.start(), match.end()),
                        "remediation": "Remove the token from public artifacts and rotate it if it was real.",
                    }
                )
    return findings


def run_sensitive_value_scan(
    root: Path,
    *,
    scan_roots: Iterable[str] = DEFAULT_SCAN_ROOTS,
    excluded_paths: set[str] | None = None,
) -> dict[str, Any]:
    excluded = set(DEFAULT_EXCLUDED_SCAN_PATHS)
    if excluded_paths:
        excluded.update(excluded_paths)
    findings: list[dict[str, Any]] = []
    for path in _iter_scan_files(root, scan_roots, excluded):
        text = path.read_text(encoding="utf-8", errors="ignore")
        findings.extend(_secret_assignment_findings(root, path, text))
        findings.extend(_token_literal_findings(root, path, text))
    return {
        "name": "sensitive_value_scan",
        "status": "pass" if not findings else "fail",
        "scan_roots": list(scan_roots),
        "excluded_paths": sorted(excluded),
        "detectors": ["secret_assignment", *[name for name, _ in TOKEN_LITERAL_PATTERNS]],
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
        skip_public_examples=args.skip_public_examples,
    )
    if args.dry_run:
        return {
            "schema_version": "0.9",
            "status": "dry_run",
            "root": str(root),
            "commands": [{"name": step.name, "command": step.command} for step in command_steps],
            "portability_scan": not args.skip_portability_scan,
            "sensitive_value_scan": not args.skip_sensitive_value_scan,
        }

    env = smoke_env(root)
    results = [run_command_step(step, root=root, env=env) for step in command_steps]
    if not args.skip_portability_scan:
        results.append(run_portability_scan(root))
    if not args.skip_sensitive_value_scan:
        results.append(run_sensitive_value_scan(root))
    status = "pass" if all(result["status"] == "pass" for result in results) else "fail"
    return {
        "schema_version": "0.9",
        "status": status,
        "root": str(root),
        "results": results,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Experimental Assistant v0.9.6 public-release smoke checks.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--quick-validate", type=Path)
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--skip-skill-validation", action="store_true")
    parser.add_argument("--skip-cli-sanity", action="store_true")
    parser.add_argument("--skip-public-examples", action="store_true")
    parser.add_argument("--skip-portability-scan", action="store_true")
    parser.add_argument("--skip-sensitive-value-scan", action="store_true")
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
