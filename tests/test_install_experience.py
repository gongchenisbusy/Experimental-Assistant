from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from ea import __version__
from ea.cli import main
from ea.install_experience import install_check, install_codex_skill, onboarding_post_install_record, python_preflight_record


def _write_validator(path: Path) -> Path:
    validator = path / "quick_validate.py"
    validator.write_text(
        "from __future__ import annotations\n"
        "import sys\n"
        "target = sys.argv[1]\n"
        "print(f'Skill is valid: {target}')\n",
        encoding="utf-8",
    )
    return validator


def test_python_preflight_has_actionable_low_version_guidance(monkeypatch) -> None:
    monkeypatch.setattr("ea.install_experience._python_version_tuple", lambda: (3, 9, 6))

    result = python_preflight_record()

    assert result["status"] == "fail"
    assert "Python 3.11 or newer" in result["message"]
    assert any("uv python install 3.12" in step for step in result["next_steps"])


def test_codex_install_skill_backs_up_existing_skill_and_preserves_v0_1(tmp_path: Path) -> None:
    source = Path("skills/ea-v0-2").resolve()
    codex_home = tmp_path / "codex"
    existing = codex_home / "skills" / "ea-v0-2"
    legacy = codex_home / "skills" / "ea-v0-1"
    existing.mkdir(parents=True)
    legacy.mkdir(parents=True)
    (existing / "SKILL.md").write_text("---\nname: old\ndescription: old\n---\n", encoding="utf-8")
    (legacy / "SKILL.md").write_text("---\nname: ea-v0-1\ndescription: legacy\n---\n", encoding="utf-8")
    validator = _write_validator(tmp_path)

    result = install_codex_skill(source=source, codex_home_path=codex_home, validator=validator)

    assert result["status"] == "pass"
    assert result["identity"]["product"] == "Experimental Assistant"
    assert result["identity"]["public_version"] == "Experimental Assistant v0.9.5"
    assert result["identity"]["display_version"] == "Experimental Assistant v0.9.5"
    assert result["identity"]["package_compatibility_name"] == "ea-v0-2"
    assert result["identity"]["compatibility_id"] == "ea-v0-2"
    assert result["identity"]["skill_invocation"] == "$ea-v0-2"
    assert result["backup"]
    assert Path(result["backup"]).exists()
    assert (codex_home / "skills" / "ea-v0-2" / "SKILL.md").exists()
    assert (codex_home / "skills" / "ea-v0-1" / "SKILL.md").exists()
    assert result["legacy_skill_detected"] is True
    assert "old projects and old skills were not modified" in result["legacy_skill_note"]
    assert result["validation"]["status"] == "pass"


def test_install_check_reports_cli_skill_validation_and_example(tmp_path: Path, monkeypatch) -> None:
    codex_home = tmp_path / "codex"
    skill = codex_home / "skills" / "ea-v0-2"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(Path("skills/ea-v0-2/SKILL.md").read_text(encoding="utf-8"), encoding="utf-8")
    validator = _write_validator(tmp_path)
    monkeypatch.setattr("ea.install_experience._ea_executable", lambda: "/tmp/bin/ea")

    result = install_check(
        codex_home_path=codex_home,
        validator=validator,
        run_example=True,
        example_workspace=Path("examples/public-raman-project"),
    )

    assert result["status"] == "pass"
    statuses = {check["name"]: check["status"] for check in result["checks"]}
    assert statuses["python_version"] == "pass"
    assert statuses["ea_cli"] == "pass"
    assert statuses["codex_skill_path"] == "pass"
    assert statuses["codex_skill_validation"] == "pass"
    assert statuses["public_example_healthcheck"] == "pass"


def test_cli_version_and_install_commands(tmp_path: Path, capsys, monkeypatch) -> None:
    with pytest.raises(SystemExit) as version_exit:
        main(["--version"])
    assert version_exit.value.code == 0
    version_output = capsys.readouterr().out
    assert "Experimental Assistant" in version_output
    assert __version__ in version_output
    assert "v0.9.5" in version_output

    assert main(["version", "--json"]) == 0
    identity = json.loads(capsys.readouterr().out)
    assert identity["product"] == "Experimental Assistant"
    assert identity["public_version"] == "Experimental Assistant v0.9.5"
    assert identity["display_version"] == "Experimental Assistant v0.9.5"
    assert identity["package_compatibility_name"] == "ea-v0-2"

    validator = _write_validator(tmp_path)
    codex_home = tmp_path / "codex"
    assert (
        main(
            [
                "codex",
                "install-skill",
                "--source",
                "skills/ea-v0-2",
                "--codex-home",
                str(codex_home),
                "--quick-validate",
                str(validator),
                "--json",
            ]
        )
        == 0
    )
    installed = json.loads(capsys.readouterr().out)
    assert installed["status"] == "pass"
    assert installed["identity"]["skill_invocation"] == "$ea-v0-2"

    monkeypatch.setattr("ea.install_experience._ea_executable", lambda: sys.executable)
    assert (
        main(
            [
                "install-check",
                "--codex-home",
                str(codex_home),
                "--quick-validate",
                str(validator),
                "--json",
            ]
        )
        == 0
    )
    checked = json.loads(capsys.readouterr().out)
    assert checked["status"] == "pass"
    assert checked["identity"]["public_version"] == "Experimental Assistant v0.9.5"


def test_post_install_onboarding_is_version_bound_and_permission_gated() -> None:
    record = onboarding_post_install_record(event="update", lang="zh")

    assert record["identity"]["display_version"] == "Experimental Assistant v0.9.5"
    assert record["event"] == "update"
    assert record["confirmation_phrase"] == "确定配置"
    assert record["compatibility"]["compatibility_id"] == "ea-v0-2"
    assert "manage_local_literature_state_with_user_permission" in record["capabilities"]
