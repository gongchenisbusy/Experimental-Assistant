from __future__ import annotations

import json
from pathlib import Path

import pytest

from ea import __version__
from ea.cli import main
from ea.identity import DISTRIBUTION_NAME
from ea.install_experience import (
    _decode_subprocess_output,
    identity_record,
    inspect_ea_executable,
    install_check,
    install_codex_skill,
    onboarding_post_install_record,
    python_preflight_record,
    rollback_codex_skills,
    uninstall_codex_skills,
    update_installation,
    validate_skill,
)


def test_windows_gbk_validator_output_decodes_without_mojibake() -> None:
    assert _decode_subprocess_output("验证通过".encode("gbk")) == "验证通过"


def _write_validator(path: Path, *, fail_for: str | None = None) -> Path:
    validator = path / "quick_validate.py"
    validator.write_text(
        "from __future__ import annotations\n"
        "import pathlib\n"
        "import sys\n"
        "target = pathlib.Path(sys.argv[1])\n"
        f"fail_for = {fail_for!r}\n"
        "print(f'Validated: {target}')\n"
        "raise SystemExit(2 if fail_for and target.name == fail_for else 0)\n",
        encoding="utf-8",
    )
    return validator


def _install_sources(codex_home: Path) -> None:
    skills = codex_home / "skills"
    target = skills / "ea"
    target.mkdir(parents=True, exist_ok=True)
    (target / "SKILL.md").write_text(
        Path("skills/ea/SKILL.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def _install_retired_skill(codex_home: Path) -> Path:
    target = codex_home / "skills" / "ea-v0-2"
    target.mkdir(parents=True, exist_ok=True)
    (target / "SKILL.md").write_text(
        "---\nname: ea-v0-2\ndescription: Retired Experimental Assistant v0.9.9 entry.\n---\n",
        encoding="utf-8",
    )
    return target


def _passing_cli_check() -> dict:
    return {
        "name": "ea_cli",
        "status": "pass",
        "path": "/test/bin/ea",
        "detected_identity": identity_record(),
        "next_steps": [],
    }


def test_python_preflight_has_actionable_supported_matrix_guidance(monkeypatch) -> None:
    monkeypatch.setattr(
        "ea.install_experience._python_version_tuple", lambda: (3, 9, 6)
    )

    result = python_preflight_record()

    assert result["status"] == "fail"
    assert "3.11, 3.12, and 3.13" in result["message"]
    assert any("uv python install 3.12" in step for step in result["next_steps"])


def test_identity_uses_public_distribution_and_ea_skill(monkeypatch) -> None:
    monkeypatch.setattr(
        "ea.install_experience._installed_distribution_versions",
        lambda: {DISTRIBUTION_NAME: __version__},
    )

    result = identity_record()

    assert result["public_version"] == "Experimental Assistant v1.0.0"
    assert result["distribution_name"] == "experimental-assistant"
    assert result["skill_folder"] == "ea"
    assert result["skill_invocation"] == "$ea"
    assert "legacy_skill_invocations" not in result


def test_version_human_output_hides_legacy_compatibility_name(
    capsys, monkeypatch
) -> None:
    monkeypatch.setattr(
        "ea.install_experience._installed_distribution_versions",
        lambda: {DISTRIBUTION_NAME: __version__},
    )

    assert main(["version"]) == 0
    output = capsys.readouterr().out

    assert "Distribution: experimental-assistant 1.0.0" in output
    assert "Codex skill invocation: $ea" in output
    assert "ea-v0-2" not in output


def test_capability_contract_is_queryable(capsys) -> None:
    assert main(["capabilities", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)

    assert "maturity" not in json.dumps(result).lower()
    assert "beta" not in json.dumps(result).lower()
    assert (
        "user_defined_literature_data_collection"
        in result["contract"]["supported_workflows"]
    )
    assert "scientific_interpretations" in result["contract"]["review_required"]


def test_codex_install_stages_primary_and_removes_retired_skill(
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex"
    _install_sources(codex_home)
    _install_retired_skill(codex_home)
    v0_1 = codex_home / "skills" / "ea-v0-1"
    v0_1.mkdir(parents=True)
    (v0_1 / "SKILL.md").write_text("legacy-v0-1\n", encoding="utf-8")
    for name in ("ea", "ea-v0-2"):
        (codex_home / "skills" / name / "marker.txt").write_text(
            "old\n", encoding="utf-8"
        )

    result = install_codex_skill(
        source=Path("skills/ea"),
        codex_home_path=codex_home,
        validator=_write_validator(tmp_path),
    )

    assert result["status"] == "pass"
    assert result["identity"]["skill_invocation"] == "$ea"
    assert set(result["targets"]) == {"ea"}
    assert all(Path(path).exists() for path in result["backups"].values())
    assert result["retired_skills_removed"] == ["ea-v0-2"]
    assert not (codex_home / "skills" / "ea" / "marker.txt").exists()
    assert not (codex_home / "skills" / "ea-v0-2").exists()
    assert (v0_1 / "SKILL.md").read_text(encoding="utf-8") == "legacy-v0-1\n"


def test_codex_install_accepts_repository_root_as_source(tmp_path: Path) -> None:
    result = install_codex_skill(
        source=Path.cwd(),
        codex_home_path=tmp_path / "codex",
        validator=_write_validator(tmp_path),
    )

    assert result["status"] == "pass"
    assert Path(result["targets"]["ea"], "SKILL.md").is_file()
    assert not (tmp_path / "codex" / "skills" / "ea-v0-2").exists()


def test_staged_validation_failure_leaves_previous_skills_untouched(
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex"
    _install_sources(codex_home)
    _install_retired_skill(codex_home)
    for name in ("ea", "ea-v0-2"):
        (codex_home / "skills" / name / "marker.txt").write_text(
            "working\n", encoding="utf-8"
        )

    result = install_codex_skill(
        source=Path("skills/ea"),
        codex_home_path=codex_home,
        validator=_write_validator(tmp_path, fail_for="ea"),
    )

    assert result["status"] == "fail"
    assert result["restored_previous"] is True
    assert (codex_home / "skills" / "ea" / "marker.txt").read_text(
        encoding="utf-8"
    ) == "working\n"
    assert (codex_home / "skills" / "ea-v0-2" / "marker.txt").read_text(
        encoding="utf-8"
    ) == "working\n"
    journal = Path(result["transaction_journal"])
    assert journal.is_file()
    transaction = json.loads(journal.read_text(encoding="utf-8"))
    assert transaction["status"] == "fail"
    assert transaction["restored_previous"] is True


def test_validator_forces_utf8_and_round_trips_non_ascii_output(tmp_path: Path) -> None:
    skill = tmp_path / "技能-ea"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# 技能 → `EA`\n", encoding="utf-8")
    validator = tmp_path / "quick_validate.py"
    validator.write_text(
        "from __future__ import annotations\nprint('中文 — 箭头 → `code`')\n",
        encoding="utf-8",
    )

    result = validate_skill(skill, validator=validator)

    assert result["status"] == "pass"
    assert result["stdout"] == "中文 — 箭头 → `code`"


def test_install_prefers_bundled_distribution_and_never_clones_repository(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "ea.install_experience.find_bundled_skill_source", lambda: Path("skills/ea")
    )
    monkeypatch.setattr(
        "ea.install_experience.find_local_skill_source",
        lambda start=None: (_ for _ in ()).throw(
            AssertionError("developer checkout used")
        ),
    )
    monkeypatch.setattr(
        "ea.install_experience._fetch_compact_skill_bundle",
        lambda release_ref: (_ for _ in ()).throw(AssertionError("network used")),
    )

    result = install_codex_skill(
        codex_home_path=tmp_path / "codex",
        validator=_write_validator(tmp_path),
    )

    assert result["status"] == "pass"
    assert result["source"]["origin"] == "bundled_distribution"
    assert Path(result["transaction_journal"]).is_file()


def test_swap_failure_restores_every_previous_skill(
    tmp_path: Path, monkeypatch
) -> None:
    codex_home = tmp_path / "codex"
    _install_sources(codex_home)
    _install_retired_skill(codex_home)
    for name in ("ea", "ea-v0-2"):
        (codex_home / "skills" / name / "marker.txt").write_text(
            f"old-{name}\n", encoding="utf-8"
        )
    real_move = __import__("shutil").move

    def fail_retired_removal(source, destination):
        if Path(source).name == "ea-v0-2":
            raise OSError("injected retired-skill removal failure")
        return real_move(source, destination)

    monkeypatch.setattr("ea.install_experience.shutil.move", fail_retired_removal)

    with pytest.raises(OSError, match="injected retired-skill removal failure"):
        install_codex_skill(
            source=Path("skills/ea"),
            codex_home_path=codex_home,
            validator=_write_validator(tmp_path),
        )

    assert (codex_home / "skills" / "ea" / "marker.txt").read_text(
        encoding="utf-8"
    ) == "old-ea\n"
    assert (codex_home / "skills" / "ea-v0-2" / "marker.txt").read_text(
        encoding="utf-8"
    ) == "old-ea-v0-2\n"


def test_install_check_requires_exact_distribution_cli_and_only_primary_skill(
    tmp_path: Path, monkeypatch
) -> None:
    codex_home = tmp_path / "codex"
    _install_sources(codex_home)
    monkeypatch.setattr(
        "ea.install_experience._installed_distribution_versions",
        lambda: {DISTRIBUTION_NAME: __version__},
    )
    monkeypatch.setattr(
        "ea.install_experience.inspect_ea_executable",
        lambda executable=None: _passing_cli_check(),
    )
    monkeypatch.setattr(
        "ea.install_experience.python_preflight_record",
        lambda: {"name": "python_version", "status": "pass"},
    )

    result = install_check(
        codex_home_path=codex_home, validator=_write_validator(tmp_path)
    )

    assert result["status"] == "pass"
    statuses = {check["name"]: check["status"] for check in result["checks"]}
    assert statuses["ea_distribution"] == "pass"
    assert statuses["ea_cli"] == "pass"
    assert statuses["codex_skill_path:ea"] == "pass"
    assert statuses["retired_codex_skill:ea-v0-2"] == "pass"


def test_install_check_rejects_retired_compatibility_skill(
    tmp_path: Path, monkeypatch
) -> None:
    codex_home = tmp_path / "codex"
    _install_sources(codex_home)
    _install_retired_skill(codex_home)
    monkeypatch.setattr(
        "ea.install_experience._installed_distribution_versions",
        lambda: {DISTRIBUTION_NAME: __version__},
    )
    monkeypatch.setattr(
        "ea.install_experience.inspect_ea_executable",
        lambda executable=None: _passing_cli_check(),
    )
    monkeypatch.setattr(
        "ea.install_experience.python_preflight_record",
        lambda: {"name": "python_version", "status": "pass"},
    )

    result = install_check(
        codex_home_path=codex_home, validator=_write_validator(tmp_path)
    )

    assert result["status"] == "fail"
    statuses = {check["name"]: check["status"] for check in result["checks"]}
    assert statuses["retired_codex_skill:ea-v0-2"] == "fail"


def test_missing_or_stale_path_cli_is_a_structured_failure(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "ea.install_experience._ea_executable", lambda: str(tmp_path / "missing" / "ea")
    )

    result = inspect_ea_executable()

    assert result["status"] == "fail"
    assert result["code"] == "EA-INSTALL-CLI-EXECUTION-FAILED"
    assert str(tmp_path / "missing" / "ea") == result["path"]


def test_rollback_and_uninstall_are_confirmation_gated(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex"
    _install_sources(codex_home)
    validator = _write_validator(tmp_path)
    install_codex_skill(
        source=Path("skills/ea"), codex_home_path=codex_home, validator=validator
    )

    rollback_plan = rollback_codex_skills(
        codex_home_path=codex_home, validator=validator
    )
    uninstall_plan = uninstall_codex_skills(codex_home_path=codex_home)

    assert rollback_plan["status"] == "needs_confirmation"
    assert set(rollback_plan["will_restore"]) == {"ea"}
    assert uninstall_plan["status"] == "needs_confirmation"
    assert len(uninstall_plan["will_remove"]) == 1


@pytest.mark.parametrize("legacy_version", ["v0.9.7", "v0.9.8", "v0.9.9"])
def test_rollback_restores_supported_legacy_skill_backup(
    tmp_path: Path, legacy_version: str
) -> None:
    codex_home = tmp_path / "codex"
    _install_sources(codex_home)
    target = codex_home / "skills" / "ea" / "SKILL.md"
    target.write_text(
        target.read_text(encoding="utf-8").replace("v1.0.0", legacy_version),
        encoding="utf-8",
    )
    validator = _write_validator(tmp_path)
    install_codex_skill(
        source=Path("skills/ea"), codex_home_path=codex_home, validator=validator
    )

    result = rollback_codex_skills(
        codex_home_path=codex_home, validator=validator, confirmed=True
    )

    assert result["status"] == "completed"
    assert result["restored"] == ["ea"]
    assert legacy_version in target.read_text(encoding="utf-8")


def test_rollback_rejects_unsupported_legacy_skill_backup(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex"
    _install_sources(codex_home)
    target = codex_home / "skills" / "ea" / "SKILL.md"
    target.write_text(
        target.read_text(encoding="utf-8").replace("v1.0.0", "v0.9.6"),
        encoding="utf-8",
    )
    validator = _write_validator(tmp_path)
    install_codex_skill(
        source=Path("skills/ea"), codex_home_path=codex_home, validator=validator
    )

    with pytest.raises(RuntimeError, match="Rollback backup validation failed for ea"):
        rollback_codex_skills(
            codex_home_path=codex_home, validator=validator, confirmed=True
        )


def test_cli_version_install_and_onboarding_use_v097_identity(
    tmp_path: Path, capsys
) -> None:
    with pytest.raises(SystemExit) as version_exit:
        main(["--version"])
    assert version_exit.value.code == 0
    assert "v1.0.0" in capsys.readouterr().out

    assert main(["version", "--json"]) == 0
    identity = json.loads(capsys.readouterr().out)
    assert identity["distribution_name"] == "experimental-assistant"
    assert identity["skill_invocation"] == "$ea"

    validator = _write_validator(tmp_path)
    codex_home = tmp_path / "codex"
    assert (
        main(
            [
                "codex",
                "install-skill",
                "--source",
                "skills/ea",
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
    assert installed["identity"]["skill_invocation"] == "$ea"

    onboarding = onboarding_post_install_record(event="update", lang="zh")
    assert onboarding["identity"]["display_version"] == "Experimental Assistant v1.0.0"
    assert "compatibility" not in onboarding


def test_update_plan_is_read_only_until_confirmed(monkeypatch) -> None:
    monkeypatch.setattr(
        "ea.install_experience.read_ea_executable_identity",
        lambda executable=None: {
            "status": "pass",
            "path": "/old/ea",
            "identity": {"release_label": "v0.9.9"},
        },
    )

    result = update_installation(release_ref="v1.0.0", confirmed=False)

    assert result["status"] == "needs_confirmation"
    assert result["previous_release_ref"] == "v0.9.9"
    assert result["release_ref"] == "v1.0.0"
    assert result["read_only"] is True


def test_update_rolls_back_cli_when_new_skill_install_fails(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "ea.install_experience.read_ea_executable_identity",
        lambda executable=None: {
            "status": "pass",
            "path": "/old/ea",
            "identity": {"release_label": "v0.9.6"},
        },
    )
    monkeypatch.setattr("ea.install_experience._ea_executable", lambda: "/new/ea")
    calls: list[list[str]] = []

    class Result:
        def __init__(self, returncode: int, stderr: str = "") -> None:
            self.returncode = returncode
            self.stderr = stderr
            self.stdout = ""

    def runner(command: list[str]):
        calls.append(command)
        if command[0] == "/new/ea":
            return Result(2, "skill failed")
        return Result(0)

    result = update_installation(
        release_ref="v1.0.0",
        confirmed=True,
        uv_executable="/test/uv",
        command_runner=runner,
        codex_home_path=tmp_path,
    )

    assert result["status"] == "fail"
    assert result["stage"] == "skill_update"
    assert result["restored_previous"] is True
    assert calls[-1][-1].endswith("@v0.9.6")
    journal = json.loads(Path(result["journal_path"]).read_text(encoding="utf-8"))
    assert journal["stage"] == "skill_update"
    assert journal["restored_previous"] is True
    assert set(journal) >= {"before", "after"}


def test_public_lifecycle_commands_are_discoverable(capsys) -> None:
    for command in ("setup", "doctor", "update", "rollback", "uninstall"):
        with pytest.raises(SystemExit) as exit_info:
            main([command, "--help"])
        assert exit_info.value.code == 0
        assert command in capsys.readouterr().out.lower()
