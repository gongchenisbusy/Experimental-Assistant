from __future__ import annotations

import subprocess
from pathlib import Path

from ea.release_smoke import (
    SmokeStep,
    build_command_steps,
    run_command_step,
    run_portability_scan,
    smoke_env,
)


def test_public_release_smoke_builds_expected_command_steps(tmp_path: Path) -> None:
    steps = build_command_steps(tmp_path, python="python", quick_validate=Path("/tools/quick_validate.py"))
    commands = {step.name: step.command for step in steps}

    assert commands["pytest"] == ["python", "-m", "pytest"]
    assert commands["skill_validation"] == ["python", "/tools/quick_validate.py", "skills/ea-v0-2"]
    assert "main(['--help'])" in commands["cli_help"][2]
    assert "main(['export', '--help'])" in commands["cli_export_help"][2]
    assert "main(['eval', '--help'])" in commands["cli_eval_help"][2]


def test_public_release_smoke_env_prefers_repo_src(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PYTHONPATH", "/existing")
    env = smoke_env(tmp_path)

    assert env["PYTHONPATH"].startswith(str(tmp_path / "src"))
    assert env["PYTHONPATH"].endswith("/existing")
    assert env["EA_PUBLIC_RELEASE_SMOKE"] == "1"


def test_portability_scan_reports_forbidden_public_defaults(tmp_path: Path) -> None:
    source = tmp_path / "src" / "bad.py"
    source.parent.mkdir(parents=True)
    source.write_text('DEFAULT = "/Users/geecoe/private-cache"\n', encoding="utf-8")

    result = run_portability_scan(tmp_path, scan_roots=["src"], excluded_paths=set())

    assert result["status"] == "fail"
    assert result["findings"] == [{"path": "src/bad.py", "pattern": "/Users/geecoe"}]


def test_command_step_reports_failure(monkeypatch, tmp_path: Path) -> None:
    class Completed:
        returncode = 2
        stdout = "short output"
        stderr = "bad thing happened"

    def fake_run(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        return Completed()

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = run_command_step(SmokeStep("example", ["python", "-m", "pytest"]), root=tmp_path, env={})

    assert result["status"] == "fail"
    assert result["returncode"] == 2
    assert result["stdout_tail"] == "short output"
    assert result["stderr_tail"] == "bad thing happened"
