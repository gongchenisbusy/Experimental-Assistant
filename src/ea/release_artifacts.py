from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from ea import __version__
from ea.identity import DISTRIBUTION_NAME
from ea.storage.files import atomic_write_text


DEFAULT_OUTPUT = Path("dist") / "experimental-assistant-0.9.8-install-smoke.json"


def _run(
    args: list[str], *, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _venv_executable(venv_root: Path, name: str) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    folder = "Scripts" if os.name == "nt" else "bin"
    return venv_root / folder / f"{name}{suffix}"


def _install_env(constraints: Path) -> dict[str, str]:
    env = os.environ.copy()
    if constraints.is_file():
        env["PIP_CONSTRAINT"] = str(constraints.resolve())
    else:
        env.pop("PIP_CONSTRAINT", None)
    return env


def discover_distribution_artifacts(root: Path) -> list[Path]:
    dist = root / "dist"
    normalized = DISTRIBUTION_NAME.replace("-", "_")
    wheels = sorted(dist.glob(f"{normalized}-{__version__}-*.whl"))
    sdists = sorted(dist.glob(f"{normalized}-{__version__}.tar.gz"))
    return [*wheels, *sdists]


def smoke_install_artifact(
    root: Path, artifact: Path, *, python_executable: str = sys.executable
) -> dict[str, Any]:
    root = root.resolve()
    artifact = artifact.resolve()
    with tempfile.TemporaryDirectory(prefix="ea-artifact-smoke-") as temporary:
        temporary_root = Path(temporary)
        venv_root = temporary_root / "venv"
        create = _run(
            [python_executable, "-m", "venv", str(venv_root)], cwd=temporary_root
        )
        if create.returncode != 0:
            return {
                "artifact": artifact.name,
                "status": "fail",
                "stage": "create_venv",
                "detail": (create.stderr or create.stdout).strip()[:2000],
            }

        python = _venv_executable(venv_root, "python")
        ea = _venv_executable(venv_root, "ea")
        constraints = root / "requirements" / "release.txt"
        install_args = [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
        ]
        if constraints.is_file():
            install_args.extend(["-c", str(constraints)])
        install_args.append(str(artifact))
        install = _run(install_args, cwd=temporary_root, env=_install_env(constraints))
        if install.returncode != 0:
            return {
                "artifact": artifact.name,
                "status": "fail",
                "stage": "install",
                "detail": (install.stderr or install.stdout).strip()[-2000:],
            }

        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env["PATH"] = str(ea.parent) + os.pathsep + env.get("PATH", "")
        resolved = shutil.which("ea", path=env["PATH"])
        commands = {
            "version": ["ea", "version", "--json"],
            "capabilities": ["ea", "capabilities", "--json"],
            "help": ["ea", "--help"],
            "bundled_skill_setup": [
                "ea",
                "setup",
                "--codex-home",
                str(temporary_root / "codex-home"),
                "--json",
            ],
        }
        results: dict[str, Any] = {}
        for name, command in commands.items():
            completed = _run(command, cwd=temporary_root, env=env)
            results[name] = {
                "returncode": completed.returncode,
                "stdout_bytes": len(completed.stdout.encode("utf-8")),
                "stderr": completed.stderr.strip()[:1000],
            }
            if name == "version" and completed.returncode == 0:
                try:
                    identity = json.loads(completed.stdout)
                except json.JSONDecodeError:
                    identity = {}
                results[name]["identity"] = {
                    "product": identity.get("product"),
                    "distribution_name": identity.get("distribution_name"),
                    "package_version": identity.get("package_version"),
                    "skill_folder": identity.get("skill_folder"),
                }

        identity = results.get("version", {}).get("identity", {})
        commands_pass = all(item["returncode"] == 0 for item in results.values())
        identity_pass = (
            identity.get("distribution_name") == DISTRIBUTION_NAME
            and identity.get("package_version") == __version__
            and identity.get("skill_folder") == "ea"
        )
        skill_setup_pass = all(
            (
                temporary_root / "codex-home" / "skills" / skill_name / "SKILL.md"
            ).is_file()
            for skill_name in ("ea", "ea-v0-2")
        )
        return {
            "artifact": artifact.name,
            "artifact_kind": "wheel" if artifact.suffix == ".whl" else "sdist",
            "status": "pass"
            if commands_pass and identity_pass and skill_setup_pass
            else "fail",
            "stage": "complete",
            "path_resolved_ea": bool(
                resolved and Path(resolved).resolve() == ea.resolve()
            ),
            "commands": results,
            "bundled_skills_installed": skill_setup_pass,
        }


def build_install_smoke_report(
    root: Path,
    *,
    artifacts: list[Path] | None = None,
    python_executable: str = sys.executable,
) -> dict[str, Any]:
    root = root.resolve()
    selected = artifacts or discover_distribution_artifacts(root)
    records = [
        smoke_install_artifact(root, item, python_executable=python_executable)
        for item in selected
    ]
    kinds = {
        record.get("artifact_kind")
        for record in records
        if record.get("status") == "pass"
    }
    return {
        "schema_version": "1.0",
        "check_type": "experimental_assistant_clean_artifact_install",
        "status": "pass"
        if kinds == {"wheel", "sdist"}
        and all(record["status"] == "pass" for record in records)
        else "fail",
        "distribution": DISTRIBUTION_NAME,
        "version": __version__,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "required_artifact_kinds": ["wheel", "sdist"],
        "artifacts": records,
    }


def write_install_smoke_report(
    root: Path,
    *,
    artifacts: list[Path] | None = None,
    python_executable: str = sys.executable,
    output: Path = DEFAULT_OUTPUT,
) -> tuple[Path, dict[str, Any]]:
    root = root.resolve()
    report = build_install_smoke_report(
        root, artifacts=artifacts, python_executable=python_executable
    )
    output_path = output if output.is_absolute() else root / output
    atomic_write_text(
        output_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    return output_path, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Install EA wheel and sdist in clean environments and run PATH-resolved CLI smoke checks."
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--artifact", type=Path, action="append", default=[])
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    artifacts = [
        item if item.is_absolute() else args.root / item for item in args.artifact
    ] or None
    output, report = write_install_smoke_report(
        args.root,
        artifacts=artifacts,
        python_executable=args.python,
        output=args.output,
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "output": str(output),
                "artifacts": report["artifacts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
