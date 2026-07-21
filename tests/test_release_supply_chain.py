from __future__ import annotations

from pathlib import Path
import subprocess

from ea.release_supply_chain import (
    _vulnerability_count,
    build_cyclonedx_sbom,
    installed_components,
)


def test_cyclonedx_sbom_is_deterministic_for_one_environment() -> None:
    first = build_cyclonedx_sbom(Path.cwd())
    second = build_cyclonedx_sbom(Path.cwd())

    assert first == second
    assert first["bomFormat"] == "CycloneDX"
    assert first["specVersion"] == "1.5"
    assert first["metadata"]["component"]["name"] == "experimental-assistant"
    assert first["metadata"]["component"]["version"] == "1.1.0"
    assert first["components"]


def test_installed_components_does_not_require_pip(monkeypatch, tmp_path: Path) -> None:
    observed: list[str] = []

    def fake_run(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
        observed.extend(args)
        return subprocess.CompletedProcess(
            args,
            0,
            stdout='[{"name": "Example_Package", "version": "1.2.3"}]',
            stderr="",
        )

    monkeypatch.setattr("ea.release_supply_chain._run", fake_run)

    components = installed_components(tmp_path, python_executable="python")

    assert observed[:2] == ["python", "-c"]
    assert "importlib.metadata" in observed[2]
    assert components == [
        {
            "type": "library",
            "name": "Example_Package",
            "version": "1.2.3",
            "purl": "pkg:pypi/example-package@1.2.3",
        }
    ]


def test_vulnerability_report_parser_keeps_fix_versions() -> None:
    count, findings = _vulnerability_count(
        {
            "dependencies": [
                {
                    "name": "example",
                    "version": "1.0",
                    "vulns": [
                        {
                            "id": "PYSEC-TEST",
                            "fix_versions": ["1.1"],
                            "aliases": ["CVE-TEST"],
                        }
                    ],
                }
            ]
        }
    )

    assert count == 1
    assert findings == [
        {
            "package": "example",
            "version": "1.0",
            "id": "PYSEC-TEST",
            "fix_versions": ["1.1"],
            "aliases": ["CVE-TEST"],
        }
    ]
