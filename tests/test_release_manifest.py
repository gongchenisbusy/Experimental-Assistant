from __future__ import annotations

import json
import hashlib
from pathlib import Path

import yaml

from ea.release_manifest import build_release_manifest, main, write_release_manifest
from ea.release_skill_bundle import build_skill_bundle


def _minimal_release_root(root: Path) -> Path:
    (root / "src" / "ea").mkdir(parents=True)
    (root / "skills" / "ea").mkdir(parents=True)
    (root / "skill-registry").mkdir()
    (root / "requirements").mkdir()
    (root / "docs").mkdir()
    (root / "examples").mkdir()
    (root / "tests").mkdir()
    (root / "scripts").mkdir()
    (root / "dist").mkdir()
    (root / ".venv").mkdir()
    (root / "src" / "ea" / "__pycache__").mkdir()
    (root / "pyproject.toml").write_text(
        """
[project]
name = "experimental-assistant"
version = "0.9.8"
description = "Release test"
requires-python = ">=3.11"
dependencies = ["cryptography>=42", "pyyaml>=6.0"]

[project.optional-dependencies]
dev = ["pytest>=8.2"]

[project.scripts]
ea = "ea.cli:main"
ea-public-release-smoke = "ea.release_smoke:main"
ea-release-manifest = "ea.release_manifest:main"
ea-release-package = "ea.release_package:main"
ea-verify-release-package = "ea.release_package:verify_main"
ea-release-keygen = "ea.release_signature:keygen_main"
ea-sign-release-package = "ea.release_signature:sign_main"
ea-verify-release-signature = "ea.release_signature:verify_main"
ea-release-checklist = "ea.release_distribution:main"
ea-release-supply-chain = "ea.release_supply_chain:main"
ea-release-artifact-smoke = "ea.release_artifacts:main"
ea-release-reproducibility = "ea.release_reproducibility:main"
ea-install-check = "ea.install_experience:install_check_main"
ea-release-skill-bundle = "ea.release_skill_bundle:main"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text("# EA\n", encoding="utf-8")
    (root / "src" / "ea" / "__init__.py").write_text(
        "__version__ = '0.9.8'\n", encoding="utf-8"
    )
    (root / "src" / "ea" / "__pycache__" / "ignored.pyc").write_bytes(b"ignored")
    (root / "skills" / "ea" / "SKILL.md").write_text(
        "---\nname: ea\ndescription: test\n---\n", encoding="utf-8"
    )
    (root / "skill-registry" / "index.yml").write_text("skills: []\n", encoding="utf-8")
    (root / "docs" / "release.md").write_text("# Release\n", encoding="utf-8")
    (root / "docs" / "PUBLIC_ONBOARDING.md").write_text(
        "# Experimental Assistant v0.9.8 Public Onboarding\n", encoding="utf-8"
    )
    (root / "docs" / "RELEASE_VERIFICATION.md").write_text(
        "# Experimental Assistant v0.9.8 Release Verification\n", encoding="utf-8"
    )
    (root / "docs" / "PUBLIC_ACCEPTANCE_MATRIX.md").write_text(
        "# Experimental Assistant v0.9.8 Public Acceptance Matrix\n", encoding="utf-8"
    )
    (root / "docs" / "V0_9_RELEASE_NOTES.md").write_text(
        "# Experimental Assistant v0.9.8 Release Notes\n", encoding="utf-8"
    )
    (root / "docs" / "V0_9_KNOWN_LIMITATIONS.md").write_text(
        "# Experimental Assistant v0.9.8 Known Limitations\n", encoding="utf-8"
    )
    (root / "docs" / "V0_9_MANUAL_TEST_CHECKLIST.md").write_text(
        "# Experimental Assistant v0.9.8 Manual Test Checklist\n", encoding="utf-8"
    )
    (root / "docs" / "V0_9_AGENT_HANDOFF.md").write_text(
        "# Experimental Assistant v0.9.8 Agent Handoff\n", encoding="utf-8"
    )
    (root / "docs" / "PROJECT_BUNDLE_VERIFICATION.md").write_text(
        "# Experimental Assistant v0.9.8 Project Bundle Verification\n",
        encoding="utf-8",
    )
    (root / "examples" / "example_manifest.yml").write_text(
        "example_id: minimal\n", encoding="utf-8"
    )
    (root / "tests" / "test_demo.py").write_text(
        "def test_demo():\n    assert True\n", encoding="utf-8"
    )
    (root / "scripts" / "demo.py").write_text("print('demo')\n", encoding="utf-8")
    (root / "dist" / "ignored.yml").write_text("ignored: true\n", encoding="utf-8")
    build_skill_bundle(repository_root=root)
    (root / "dist" / "experimental-assistant-0.9.8-sbom.json").write_text(
        json.dumps(
            {
                "bomFormat": "CycloneDX",
                "specVersion": "1.5",
                "metadata": {
                    "component": {"name": "experimental-assistant", "version": "0.9.8"}
                },
                "components": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (
        root / "dist" / "experimental-assistant-0.9.8-vulnerability-report.json"
    ).write_text(
        json.dumps({"scanner": "pip-audit", "status": "pass", "vulnerability_count": 0})
        + "\n",
        encoding="utf-8",
    )
    (root / "dist" / "experimental-assistant-0.9.8-install-smoke.json").write_text(
        json.dumps(
            {
                "status": "pass",
                "distribution": "experimental-assistant",
                "version": "0.9.8",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    wheel = root / "dist" / "experimental_assistant-0.9.8-py3-none-any.whl"
    sdist = root / "dist" / "experimental_assistant-0.9.8.tar.gz"
    wheel.write_bytes(b"wheel")
    sdist.write_bytes(b"sdist")
    (root / "dist" / "experimental-assistant-0.9.8-reproducibility.json").write_text(
        json.dumps(
            {
                "status": "pass",
                "distribution": "experimental-assistant",
                "version": "0.9.8",
                "artifacts": [
                    {
                        "artifact": wheel.name,
                        "first": {
                            "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest()
                        },
                    },
                    {
                        "artifact": sdist.name,
                        "first": {
                            "sha256": hashlib.sha256(sdist.read_bytes()).hexdigest()
                        },
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "requirements" / "release.txt").write_text(
        "pip-audit==2.9.0\n", encoding="utf-8"
    )
    (root / ".venv" / "ignored.txt").write_text("ignored\n", encoding="utf-8")
    return root


def test_release_manifest_collects_package_metadata_and_checksums(
    tmp_path: Path,
) -> None:
    root = _minimal_release_root(tmp_path)

    manifest = build_release_manifest(root)
    paths = {record["path"] for record in manifest["release_inputs"]["files"]}

    assert manifest["package"]["name"] == "experimental-assistant"
    assert (
        manifest["package"]["console_scripts"]["ea-release-manifest"]
        == "ea.release_manifest:main"
    )
    assert (
        manifest["package"]["console_scripts"]["ea-release-package"]
        == "ea.release_package:main"
    )
    assert (
        manifest["package"]["console_scripts"]["ea-verify-release-package"]
        == "ea.release_package:verify_main"
    )
    assert (
        manifest["package"]["console_scripts"]["ea-release-keygen"]
        == "ea.release_signature:keygen_main"
    )
    assert (
        manifest["package"]["console_scripts"]["ea-sign-release-package"]
        == "ea.release_signature:sign_main"
    )
    assert (
        manifest["package"]["console_scripts"]["ea-verify-release-signature"]
        == "ea.release_signature:verify_main"
    )
    assert (
        manifest["package"]["console_scripts"]["ea-release-checklist"]
        == "ea.release_distribution:main"
    )
    assert (
        manifest["package"]["console_scripts"]["ea-release-supply-chain"]
        == "ea.release_supply_chain:main"
    )
    assert (
        manifest["package"]["console_scripts"]["ea-release-artifact-smoke"]
        == "ea.release_artifacts:main"
    )
    assert (
        manifest["package"]["console_scripts"]["ea-release-reproducibility"]
        == "ea.release_reproducibility:main"
    )
    assert (
        manifest["package"]["console_scripts"]["ea-install-check"]
        == "ea.install_experience:install_check_main"
    )
    assert "pyproject.toml" in paths
    assert "docs/PUBLIC_ONBOARDING.md" in paths
    assert "docs/RELEASE_VERIFICATION.md" in paths
    assert "docs/PUBLIC_ACCEPTANCE_MATRIX.md" in paths
    assert "docs/V0_9_RELEASE_NOTES.md" in paths
    assert "docs/V0_9_KNOWN_LIMITATIONS.md" in paths
    assert "docs/V0_9_MANUAL_TEST_CHECKLIST.md" in paths
    assert "docs/V0_9_AGENT_HANDOFF.md" in paths
    assert "docs/PROJECT_BUNDLE_VERIFICATION.md" in paths
    assert "examples/example_manifest.yml" in paths
    assert "src/ea/__init__.py" in paths
    assert "src/ea/__pycache__/ignored.pyc" not in paths
    assert "dist/ignored.yml" not in paths
    assert ".venv/ignored.txt" not in paths
    assert manifest["release_inputs"]["aggregate_sha256"]
    assert (
        "release_manifest_help"
        in manifest["validation_contract"]["required_smoke_steps"]
    )
    assert (
        "cli_global_version" in manifest["validation_contract"]["required_smoke_steps"]
    )
    assert "cli_version_help" in manifest["validation_contract"]["required_smoke_steps"]
    assert (
        "cli_install_check_help"
        in manifest["validation_contract"]["required_smoke_steps"]
    )
    assert (
        "cli_codex_install_skill_help"
        in manifest["validation_contract"]["required_smoke_steps"]
    )
    assert (
        "version_identity_check"
        in manifest["validation_contract"]["required_smoke_steps"]
    )
    assert (
        "downloaded_skill_instruction_check"
        in manifest["validation_contract"]["required_smoke_steps"]
    )
    assert (
        "install_check_console_help"
        in manifest["validation_contract"]["required_smoke_steps"]
    )
    assert (
        "public_example_raman_healthcheck"
        in manifest["validation_contract"]["required_smoke_steps"]
    )
    assert (
        "public_example_ftir_source_eval"
        in manifest["validation_contract"]["required_smoke_steps"]
    )
    assert (
        "release_package_help"
        in manifest["validation_contract"]["required_smoke_steps"]
    )
    assert (
        "release_package_verify_help"
        in manifest["validation_contract"]["required_smoke_steps"]
    )
    assert (
        "release_signature_keygen_help"
        in manifest["validation_contract"]["required_smoke_steps"]
    )
    assert (
        "release_signature_sign_help"
        in manifest["validation_contract"]["required_smoke_steps"]
    )
    assert (
        "release_signature_verify_help"
        in manifest["validation_contract"]["required_smoke_steps"]
    )
    assert (
        "release_distribution_checklist_help"
        in manifest["validation_contract"]["required_smoke_steps"]
    )


def test_write_release_manifest_creates_yaml_manifest(tmp_path: Path) -> None:
    root = _minimal_release_root(tmp_path)

    output, manifest = write_release_manifest(root, output=Path("dist/release.yml"))
    loaded = yaml.safe_load(output.read_text(encoding="utf-8"))

    assert output == root / "dist" / "release.yml"
    assert loaded["manifest_type"] == "experimental_assistant_release"
    assert (
        loaded["release_inputs"]["aggregate_sha256"]
        == manifest["release_inputs"]["aggregate_sha256"]
    )


def test_release_manifest_cli_writes_summary_json(tmp_path: Path, capsys) -> None:
    root = _minimal_release_root(tmp_path)

    exit_code = main(["--root", str(root), "--output", "dist/custom-release.yml"])
    summary = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert summary["status"] == "complete"
    assert summary["package"] == {"name": "experimental-assistant", "version": "0.9.8"}
    assert Path(summary["manifest"]).exists()
    assert summary["file_count"] > 0


def test_release_manifest_cli_no_write_can_print_manifest(
    tmp_path: Path, capsys
) -> None:
    root = _minimal_release_root(tmp_path)

    exit_code = main(["--root", str(root), "--no-write", "--print-manifest"])
    summary = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert summary["manifest"] is None
    assert summary["release_manifest"]["signature"]["status"] == "not_signed"
    assert (
        summary["release_manifest"]["signature"]["supported_workflow"]
        == "detached_ed25519_user_managed_key"
    )
