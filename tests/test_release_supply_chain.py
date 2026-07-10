from __future__ import annotations

import json
from pathlib import Path

from ea.release_supply_chain import _vulnerability_count, build_cyclonedx_sbom


def test_cyclonedx_sbom_is_deterministic_for_one_environment() -> None:
    first = build_cyclonedx_sbom(Path.cwd())
    second = build_cyclonedx_sbom(Path.cwd())

    assert first == second
    assert first["bomFormat"] == "CycloneDX"
    assert first["specVersion"] == "1.5"
    assert first["metadata"]["component"]["name"] == "experimental-assistant"
    assert first["metadata"]["component"]["version"] == "0.9.7"
    assert first["components"]


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
