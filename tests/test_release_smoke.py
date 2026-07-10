from __future__ import annotations

import subprocess
from pathlib import Path

from ea.release_smoke import (
    SmokeStep,
    build_command_steps,
    run_command_step,
    run_portability_scan,
    run_sensitive_value_scan,
    smoke_env,
)


def test_public_release_smoke_builds_expected_command_steps(tmp_path: Path) -> None:
    steps = build_command_steps(
        tmp_path, python="python", quick_validate=Path("/tools/quick_validate.py")
    )
    commands = {step.name: step.command for step in steps}

    assert commands["pytest"] == ["python", "-m", "pytest"]
    assert commands["primary_skill_validation"] == [
        "python",
        "/tools/quick_validate.py",
        "skills/ea",
    ]
    assert commands["compatibility_skill_validation"] == [
        "python",
        "/tools/quick_validate.py",
        "skills/ea-v0-2",
    ]
    assert "raise SystemExit(main(['--help']))" in commands["cli_help"][2]
    assert "raise SystemExit(main(['--version']))" in commands["cli_global_version"][2]
    assert (
        "raise SystemExit(main(['version', '--help']))"
        in commands["cli_version_help"][2]
    )
    assert (
        "raise SystemExit(main(['install-check', '--help']))"
        in commands["cli_install_check_help"][2]
    )
    assert (
        "raise SystemExit(main(['codex', 'install-skill', '--help']))"
        in commands["cli_codex_install_skill_help"][2]
    )
    assert (
        "raise SystemExit(main(['export', '--help']))" in commands["cli_export_help"][2]
    )
    assert "raise SystemExit(main(['eval', '--help']))" in commands["cli_eval_help"][2]
    assert commands["public_example_raman_healthcheck"][2] == (
        "from ea.cli import main; raise SystemExit(main(['healthcheck', 'examples/public-raman-project']))"
    )
    assert commands["public_example_raman_eval"][2] == (
        "from ea.cli import main; raise SystemExit(main(['eval', 'project', 'examples/public-raman-project', '--no-write']))"
    )
    assert commands["public_example_ftir_source_healthcheck"][2] == (
        "from ea.cli import main; raise SystemExit(main(['healthcheck', 'examples/public-ftir-assignment-project']))"
    )
    assert commands["public_example_ftir_source_eval"][2] == (
        "from ea.cli import main; raise SystemExit(main(['eval', 'project', 'examples/public-ftir-assignment-project', '--no-write']))"
    )
    assert commands["public_example_uv_vis_healthcheck"][2] == (
        "from ea.cli import main; raise SystemExit(main(['healthcheck', 'examples/public-uv-vis-project']))"
    )
    assert commands["public_example_uv_vis_eval"][2] == (
        "from ea.cli import main; raise SystemExit(main(['eval', 'project', 'examples/public-uv-vis-project', '--no-write']))"
    )
    assert commands["public_example_xps_be_healthcheck"][2] == (
        "from ea.cli import main; raise SystemExit(main(['healthcheck', 'examples/public-xps-be-project']))"
    )
    assert commands["public_example_xps_be_eval"][2] == (
        "from ea.cli import main; raise SystemExit(main(['eval', 'project', 'examples/public-xps-be-project', '--no-write']))"
    )
    assert commands["install_check_console_help"] == [
        "python",
        "-m",
        "ea.install_experience",
        "--help",
    ]
    assert commands["release_manifest_help"] == [
        "python",
        "-m",
        "ea.release_manifest",
        "--help",
    ]
    assert commands["release_package_help"] == [
        "python",
        "-m",
        "ea.release_package",
        "--help",
    ]
    assert commands["release_package_verify_help"] == [
        "python",
        "-c",
        "from ea.release_package import verify_main; verify_main(['--help'])",
    ]
    assert commands["release_signature_keygen_help"] == [
        "python",
        "-c",
        "from ea.release_signature import keygen_main; keygen_main(['--help'])",
    ]
    assert commands["release_signature_sign_help"] == [
        "python",
        "-c",
        "from ea.release_signature import sign_main; sign_main(['--help'])",
    ]
    assert commands["release_signature_verify_help"] == [
        "python",
        "-c",
        "from ea.release_signature import verify_main; verify_main(['--help'])",
    ]
    assert commands["release_artifact_smoke_help"] == [
        "python",
        "-m",
        "ea.release_artifacts",
        "--help",
    ]
    assert commands["release_reproducibility_help"] == [
        "python",
        "-m",
        "ea.release_reproducibility",
        "--help",
    ]
    assert commands["release_supply_chain_help"] == [
        "python",
        "-m",
        "ea.release_supply_chain",
        "--help",
    ]
    assert commands["release_distribution_checklist_help"] == [
        "python",
        "-c",
        "from ea.release_distribution import main; main(['--help'])",
    ]


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


def test_sensitive_value_scan_reports_secret_assignments_with_redacted_preview(
    tmp_path: Path,
) -> None:
    source = tmp_path / "docs" / "bad.md"
    source.parent.mkdir(parents=True)
    source.write_text('api_key = "live-private-key-12345"\n', encoding="utf-8")

    result = run_sensitive_value_scan(
        tmp_path, scan_roots=["docs"], excluded_paths=set()
    )

    assert result["status"] == "fail"
    assert result["findings"] == [
        {
            "path": "docs/bad.md",
            "line": 1,
            "detector": "secret_assignment",
            "key": "api_key",
            "preview": 'api_key = "[REDACTED]"',
            "remediation": "Remove the value from public artifacts; use a placeholder or user-supplied local config path instead.",
        }
    ]
    assert "live-private-key" not in result["findings"][0]["preview"]


def test_sensitive_value_scan_allows_placeholders_prose_and_variable_references(
    tmp_path: Path,
) -> None:
    docs = tmp_path / "docs" / "safe.md"
    docs.parent.mkdir(parents=True)
    docs.write_text(
        "\n".join(
            [
                'api_key = "<your-api-key>"',
                "Do not store passwords, cookies, session tokens, or credentials in public artifacts.",
            ]
        ),
        encoding="utf-8",
    )
    source = tmp_path / "src" / "safe.py"
    source.parent.mkdir(parents=True)
    source.write_text("load_private_key(path, password=passphrase)\n", encoding="utf-8")

    result = run_sensitive_value_scan(
        tmp_path, scan_roots=["docs", "src"], excluded_paths=set()
    )

    assert result["status"] == "pass"
    assert result["findings"] == []


def test_sensitive_value_scan_reports_token_literals(tmp_path: Path) -> None:
    source = tmp_path / "README.md"
    source.write_text(
        "temporary token: ghp_1234567890abcdefghijklmnopQRSTUV\n", encoding="utf-8"
    )

    result = run_sensitive_value_scan(
        tmp_path, scan_roots=["README.md"], excluded_paths=set()
    )

    assert result["status"] == "fail"
    assert result["findings"][0]["detector"] == "github_token"
    assert result["findings"][0]["preview"] == "temporary token: [REDACTED]"
    assert "ghp_" not in result["findings"][0]["preview"]


def test_command_step_reports_failure(monkeypatch, tmp_path: Path) -> None:
    class Completed:
        returncode = 2
        stdout = "short output"
        stderr = "bad thing happened"

    def fake_run(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        return Completed()

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = run_command_step(
        SmokeStep("example", ["python", "-m", "pytest"]), root=tmp_path, env={}
    )

    assert result["status"] == "fail"
    assert result["returncode"] == 2
    assert result["stdout_tail"] == "short output"
    assert result["stderr_tail"] == "bad thing happened"
