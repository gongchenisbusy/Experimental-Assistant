from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from ea import __version__
from ea.identity import DISTRIBUTION_NAME, REPOSITORY_URL
from ea.storage.files import atomic_write_text


DEFAULT_SBOM_OUTPUT = Path("dist") / "experimental-assistant-0.9.7-sbom.json"
DEFAULT_VULNERABILITY_OUTPUT = (
    Path("dist") / "experimental-assistant-0.9.7-vulnerability-report.json"
)

_INSTALLED_DISTRIBUTIONS_SCRIPT = """
import importlib.metadata as metadata
import json

packages = {}
for distribution in metadata.distributions():
    name = distribution.metadata.get("Name")
    if not name:
        continue
    key = name.lower().replace("_", "-")
    packages[key] = {"name": name, "version": distribution.version}
print(json.dumps(list(packages.values()), sort_keys=True))
""".strip()


def _run(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _commit_timestamp(root: Path) -> str:
    completed = _run(["git", "show", "-s", "--format=%cI", "HEAD"], cwd=root)
    return (
        completed.stdout.strip()
        if completed.returncode == 0 and completed.stdout.strip()
        else "1970-01-01T00:00:00Z"
    )


def installed_components(root: Path, *, python_executable: str) -> list[dict[str, Any]]:
    completed = _run(
        [python_executable, "-c", _INSTALLED_DISTRIBUTIONS_SCRIPT], cwd=root
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Could not list clean-environment packages: {completed.stderr.strip()}"
        )
    packages = json.loads(completed.stdout)
    return [
        {
            "type": "library",
            "name": str(item["name"]),
            "version": str(item["version"]),
            "purl": f"pkg:pypi/{str(item['name']).lower().replace('_', '-')}@{item['version']}",
        }
        for item in sorted(packages, key=lambda value: str(value["name"]).lower())
    ]


def build_cyclonedx_sbom(
    root: Path, *, python_executable: str = sys.executable
) -> dict[str, Any]:
    root = root.resolve()
    components = installed_components(root, python_executable=python_executable)
    identity = "\n".join(f"{item['name']}=={item['version']}" for item in components)
    serial = uuid.uuid5(
        uuid.NAMESPACE_URL, f"{REPOSITORY_URL}@{__version__}\n{identity}"
    )
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "timestamp": _commit_timestamp(root),
            "component": {
                "type": "application",
                "name": DISTRIBUTION_NAME,
                "version": __version__,
                "purl": f"pkg:pypi/{DISTRIBUTION_NAME}@{__version__}",
                "externalReferences": [{"type": "vcs", "url": REPOSITORY_URL}],
            },
            "properties": [
                {"name": "ea:environment", "value": "clean-release-venv"},
                {"name": "ea:generator", "value": "ea.release_supply_chain"},
            ],
        },
        "components": components,
    }


def _vulnerability_count(payload: Any) -> tuple[int, list[dict[str, Any]]]:
    dependencies = payload.get("dependencies") if isinstance(payload, dict) else payload
    if not isinstance(dependencies, list):
        return 0, []
    findings: list[dict[str, Any]] = []
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            continue
        package = dependency.get("name") or (dependency.get("metadata") or {}).get(
            "name"
        )
        version = dependency.get("version") or (dependency.get("metadata") or {}).get(
            "version"
        )
        for vulnerability in (
            dependency.get("vulns") or dependency.get("vulnerabilities") or []
        ):
            if not isinstance(vulnerability, dict):
                continue
            findings.append(
                {
                    "package": package,
                    "version": version,
                    "id": vulnerability.get("id") or vulnerability.get("name"),
                    "fix_versions": vulnerability.get("fix_versions")
                    or vulnerability.get("fixVersions")
                    or [],
                    "aliases": vulnerability.get("aliases") or [],
                }
            )
    return len(findings), findings


def run_vulnerability_scan(
    root: Path, *, python_executable: str = sys.executable
) -> dict[str, Any]:
    completed = _run([python_executable, "-m", "pip_audit", "--format=json"], cwd=root)
    try:
        raw = json.loads(completed.stdout) if completed.stdout.strip() else {}
    except json.JSONDecodeError:
        raw = {}
    count, findings = _vulnerability_count(raw)
    tool_missing = "No module named pip_audit" in completed.stderr
    if tool_missing:
        status = "tool_unavailable"
    elif completed.returncode not in {0, 1}:
        status = "scan_error"
    else:
        status = "pass" if count == 0 else "fail"
    return {
        "schema_version": "1.0",
        "scanner": "pip-audit",
        "status": status,
        "returncode": completed.returncode,
        "vulnerability_count": count,
        "findings": findings,
        "policy": {
            "unallowlisted_known_vulnerabilities": "release_blocking",
            "allowlist_requirements": [
                "written rationale",
                "scope",
                "owner",
                "expiry date",
                "compensating control",
            ],
            "allowlist": [],
        },
        "stderr": completed.stderr.strip()[:2000]
        if status in {"tool_unavailable", "scan_error"}
        else "",
    }


def write_supply_chain_evidence(
    root: Path,
    *,
    python_executable: str = sys.executable,
    sbom_output: Path = DEFAULT_SBOM_OUTPUT,
    vulnerability_output: Path = DEFAULT_VULNERABILITY_OUTPUT,
) -> dict[str, Any]:
    root = root.resolve()
    sbom = build_cyclonedx_sbom(root, python_executable=python_executable)
    vulnerability = run_vulnerability_scan(root, python_executable=python_executable)
    sbom_path = sbom_output if sbom_output.is_absolute() else root / sbom_output
    vulnerability_path = (
        vulnerability_output
        if vulnerability_output.is_absolute()
        else root / vulnerability_output
    )
    atomic_write_text(sbom_path, json.dumps(sbom, ensure_ascii=False, indent=2) + "\n")
    atomic_write_text(
        vulnerability_path,
        json.dumps(vulnerability, ensure_ascii=False, indent=2) + "\n",
    )
    return {
        "status": "pass" if vulnerability["status"] == "pass" else "fail",
        "sbom_path": str(sbom_path),
        "sbom_component_count": len(sbom["components"]),
        "vulnerability_report_path": str(vulnerability_path),
        "vulnerability_status": vulnerability["status"],
        "vulnerability_count": vulnerability["vulnerability_count"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate EA CycloneDX SBOM and pip-audit release evidence."
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--sbom-output", type=Path, default=DEFAULT_SBOM_OUTPUT)
    parser.add_argument(
        "--vulnerability-output", type=Path, default=DEFAULT_VULNERABILITY_OUTPUT
    )
    args = parser.parse_args(argv)
    result = write_supply_chain_evidence(
        args.root,
        python_executable=args.python,
        sbom_output=args.sbom_output,
        vulnerability_output=args.vulnerability_output,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
