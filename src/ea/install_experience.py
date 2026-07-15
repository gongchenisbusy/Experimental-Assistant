from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
from importlib import metadata
import json
import locale
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from ea.companion import inspect_ea_feedback_companion
from urllib.request import urlopen
import uuid
import zipfile

import yaml

from ea import __version__
from ea.identity import (
    DISPLAY_VERSION,
    DISTRIBUTION_NAME,
    LEGACY_DISTRIBUTION_NAMES,
    LEGACY_SKILL_INVOCATIONS,
    LEGACY_SKILL_NAMES,
    PRODUCT_NAME,
    PUBLIC_VERSION,
    RELEASE_LABEL,
    REPOSITORY_URL,
    SKILL_INVOCATION,
    SKILL_NAME,
    SUPPORTED_PYTHON_MINORS,
)


PACKAGE_NAME = DISTRIBUTION_NAME
PACKAGE_COMPATIBILITY_NAME = LEGACY_DISTRIBUTION_NAMES[0]
MIN_PYTHON = (3, 11)


def _decode_subprocess_output(value: bytes) -> str:
    """Decode CLI output emitted by UTF-8 or a common Windows console code page."""
    encodings = ["utf-8", locale.getpreferredencoding(False), "gb18030", "cp1252"]
    for encoding in dict.fromkeys(encodings):
        try:
            return value.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return value.decode("utf-8", errors="replace")


def _python_version_tuple() -> tuple[int, int, int]:
    return sys.version_info[:3]


def _python_version_label() -> str:
    return ".".join(str(part) for part in _python_version_tuple())


def _package_version() -> str:
    return __version__


def _installed_distribution_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in (DISTRIBUTION_NAME, *LEGACY_DISTRIBUTION_NAMES):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
    return versions


def _installed_distribution_version() -> str | None:
    return _installed_distribution_versions().get(DISTRIBUTION_NAME)


def identity_record() -> dict[str, Any]:
    installed = _installed_distribution_versions()
    official_installed = installed.get(DISTRIBUTION_NAME)
    record: dict[str, Any] = {
        "schema_version": "1.0",
        "product": PRODUCT_NAME,
        "display_name": PRODUCT_NAME,
        "display_version": PUBLIC_VERSION,
        "public_version": PUBLIC_VERSION,
        "distribution_name": DISTRIBUTION_NAME,
        "package_name": DISTRIBUTION_NAME,
        "package_compatibility_name": PACKAGE_COMPATIBILITY_NAME,
        "compatibility_id": PACKAGE_COMPATIBILITY_NAME,
        "legacy_distribution_names": list(LEGACY_DISTRIBUTION_NAMES),
        "package_version": _package_version(),
        "installed_distributions": installed,
        "release_label": RELEASE_LABEL,
        "skill_folder": SKILL_NAME,
        "skill_invocation": SKILL_INVOCATION,
        "legacy_skill_folders": list(LEGACY_SKILL_NAMES),
        "legacy_skill_invocations": list(LEGACY_SKILL_INVOCATIONS),
        "repository_url": REPOSITORY_URL,
    }
    warnings: list[str] = []
    if official_installed and official_installed != record["package_version"]:
        warnings.append(
            f"Installed {DISTRIBUTION_NAME} metadata is {official_installed}, but running code is {record['package_version']}."
        )
    for legacy_name in LEGACY_DISTRIBUTION_NAMES:
        if legacy_name in installed:
            warnings.append(
                f"Legacy distribution {legacy_name} {installed[legacy_name]} is installed; remove it after the v0.9.8 migration is verified."
            )
    if warnings:
        record["identity_warnings"] = warnings
    return record


def python_preflight_record() -> dict[str, Any]:
    version = _python_version_tuple()
    minor = version[:2]
    ok = minor in SUPPORTED_PYTHON_MINORS
    return {
        "name": "python_version",
        "status": "pass" if ok else "fail",
        "python": sys.executable,
        "version": _python_version_label(),
        "supported": [
            f"{major}.{minor_version}"
            for major, minor_version in SUPPORTED_PYTHON_MINORS
        ],
        "message": (
            "Python version is in the supported v0.9.8 matrix."
            if ok
            else "EA v0.9.8 supports Python 3.11, 3.12, and 3.13."
        ),
        "next_steps": []
        if ok
        else [
            "Install a supported Python, for example: uv python install 3.12",
            f"Then install EA with: uv tool install --python 3.12 git+{REPOSITORY_URL}.git@{RELEASE_LABEL}",
        ],
    }


def codex_home(default: Path | None = None) -> Path:
    return Path(
        os.environ.get("CODEX_HOME") or default or Path.home() / ".codex"
    ).expanduser()


def codex_skills_dir(codex_home_path: Path | None = None) -> Path:
    return (codex_home_path or codex_home()) / "skills"


def default_skill_target(codex_home_path: Path | None = None) -> Path:
    return codex_skills_dir(codex_home_path) / SKILL_NAME


def _repo_root_candidates(start: Path | None = None) -> list[Path]:
    roots: list[Path] = []
    cwd = (start or Path.cwd()).resolve()
    roots.extend([cwd, *cwd.parents])
    roots.extend(Path(__file__).resolve().parents)
    deduped: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if root not in seen:
            seen.add(root)
            deduped.append(root)
    return deduped


def find_local_skill_source(start: Path | None = None) -> Path | None:
    for root in _repo_root_candidates(start):
        candidate = root / "skills" / SKILL_NAME
        if (candidate / "SKILL.md").is_file():
            return candidate
    return None


def find_bundled_skill_source() -> Path | None:
    """Locate the skill payload installed by the current wheel/sdist."""
    try:
        distribution = metadata.distribution(DISTRIBUTION_NAME)
    except metadata.PackageNotFoundError:
        return None
    suffix = "share/experimental-assistant/skills/ea/SKILL.md"
    for entry in distribution.files or []:
        normalized = str(entry).replace("\\", "/")
        if not normalized.endswith(suffix):
            continue
        skill_md = Path(distribution.locate_file(entry)).resolve()
        if skill_md.is_file():
            return skill_md.parent
    return None


def quick_validate_path(codex_home_path: Path | None = None) -> Path | None:
    home = codex_home_path or codex_home()
    candidates = [
        home / "skills" / ".system" / "skill-creator" / "scripts" / "quick_validate.py",
        Path.home()
        / ".codex"
        / "skills"
        / ".system"
        / "skill-creator"
        / "scripts"
        / "quick_validate.py",
    ]
    return next((path for path in candidates if path.is_file()), None)


def validate_skill(
    skill_path: Path, *, validator: Path | None = None
) -> dict[str, Any]:
    validator_path = validator or quick_validate_path()
    if validator_path is None:
        return {
            "name": "codex_skill_validation",
            "status": "warning",
            "path": str(skill_path),
            "validator": None,
            "message": "Codex quick_validate.py was not found.",
        }
    env = dict(os.environ)
    env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    completed = subprocess.run(
        [sys.executable, str(validator_path), str(skill_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=env,
    )
    stdout = _decode_subprocess_output(completed.stdout)
    stderr = _decode_subprocess_output(completed.stderr)
    return {
        "name": "codex_skill_validation",
        "status": "pass" if completed.returncode == 0 else "fail",
        "path": str(skill_path),
        "validator": str(validator_path),
        "returncode": completed.returncode,
        "stdout": stdout.strip(),
        "stderr": stderr.strip(),
    }


def _skill_manifest(path: Path) -> dict[str, Any]:
    skill_md = path / "SKILL.md"
    if not skill_md.is_file():
        return {}
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    try:
        frontmatter = text.split("---\n", 2)[1]
        return yaml.safe_load(frontmatter) or {}
    except (IndexError, yaml.YAMLError):
        return {}


def inspect_skill_identity(path: Path, *, expected_name: str) -> dict[str, Any]:
    manifest = _skill_manifest(path)
    actual_name = manifest.get("name")
    description = str(manifest.get("description") or "")
    version_ok = DISPLAY_VERSION in description
    status = "pass" if actual_name == expected_name and version_ok else "fail"
    return {
        "name": "codex_skill_identity",
        "status": status,
        "path": str(path),
        "expected_name": expected_name,
        "actual_name": actual_name,
        "version_detected": DISPLAY_VERSION if version_ok else None,
        "next_steps": []
        if status == "pass"
        else ["Run `ea codex install-skill` to replace the mismatched skill."],
    }


def _fetch_compact_skill_bundle(
    release_ref: str,
) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    temp = tempfile.TemporaryDirectory(prefix="ea-skill-install-")
    version = release_ref.removeprefix("v")
    filename = f"experimental-assistant-{version}-skills.zip"
    base_url = f"{REPOSITORY_URL}/releases/download/{release_ref}"
    bundle_path = Path(temp.name) / filename
    try:
        with urlopen(f"{base_url}/{filename}", timeout=30) as response:  # noqa: S310 - fixed public release host
            bundle_path.write_bytes(response.read())
        with urlopen(f"{base_url}/{filename}.sha256", timeout=30) as response:  # noqa: S310 - fixed public release host
            checksum_text = response.read().decode("utf-8")
    except Exception as exc:  # noqa: BLE001 - converted to one actionable install error
        temp.cleanup()
        raise RuntimeError(
            f"Could not fetch compact EA skill bundle for {release_ref}: {exc}"
        ) from exc
    expected = checksum_text.split()[0] if checksum_text.split() else ""
    actual = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    if len(expected) != 64 or expected.lower() != actual:
        temp.cleanup()
        raise RuntimeError(f"EA skill bundle checksum mismatch for {release_ref}.")
    extract_root = Path(temp.name) / "bundle"
    with zipfile.ZipFile(bundle_path) as archive:
        for member in archive.infolist():
            destination = (extract_root / member.filename).resolve()
            if (
                extract_root.resolve() not in destination.parents
                and destination != extract_root.resolve()
            ):
                temp.cleanup()
                raise RuntimeError("EA skill bundle contains an unsafe path.")
        archive.extractall(extract_root)
    source = extract_root / "skills" / SKILL_NAME
    if not (source / "SKILL.md").is_file():
        temp.cleanup()
        raise FileNotFoundError(
            f"Compact release bundle does not contain skills/{SKILL_NAME}/SKILL.md"
        )
    return temp, source


def _installed_skill_snapshot(skills_dir: Path) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    for name in (SKILL_NAME, *LEGACY_SKILL_NAMES):
        target = skills_dir / name
        snapshot[name] = {
            "exists": target.is_dir(),
            "identity": inspect_skill_identity(target, expected_name=name)
            if target.is_dir()
            else None,
        }
    return snapshot


def _write_install_journal(
    skills_dir: Path,
    *,
    transaction_id: str,
    status: str,
    source_origin: str,
    before: dict[str, Any],
    after: dict[str, Any],
    restored_previous: bool,
    error: str | None = None,
) -> Path:
    journal_root = skills_dir / ".transactions"
    journal_root.mkdir(parents=True, exist_ok=True)
    path = journal_root / f"{transaction_id}.json"
    payload = {
        "schema_version": "1.0",
        "transaction_id": transaction_id,
        "operation": "install_codex_skills",
        "status": status,
        "source_origin": source_origin,
        "before": before,
        "after": after,
        "restored_previous": restored_previous,
        "error": error,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


def _normalize_primary_source(source: Path) -> Path:
    resolved = source.resolve()
    checkout_skill = resolved / "skills" / SKILL_NAME
    if (checkout_skill / "SKILL.md").is_file():
        return checkout_skill
    if resolved.name in LEGACY_SKILL_NAMES:
        sibling = resolved.parent / SKILL_NAME
        if sibling.is_dir():
            return sibling
    return resolved


def _skill_sources(primary: Path) -> list[tuple[str, Path]]:
    sources = [(SKILL_NAME, primary)]
    for legacy_name in LEGACY_SKILL_NAMES:
        legacy = primary.parent / legacy_name
        if not (legacy / "SKILL.md").is_file():
            raise FileNotFoundError(f"Compatibility skill source is missing: {legacy}")
        sources.append((legacy_name, legacy))
    return sources


def _backup_path(skills_dir: Path, name: str, stamp: str) -> Path:
    backup_root = skills_dir / ".backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    candidate = backup_root / f"{name}-{stamp}"
    counter = 1
    while candidate.exists():
        candidate = backup_root / f"{name}-{stamp}-{counter}"
        counter += 1
    return candidate


def install_codex_skill(
    *,
    source: Path | None = None,
    codex_home_path: Path | None = None,
    validator: Path | None = None,
    backup_existing: bool = True,
    allow_github_fetch: bool = True,
    release_ref: str = RELEASE_LABEL,
    now: datetime | None = None,
) -> dict[str, Any]:
    home = codex_home_path or codex_home()
    skills_dir = codex_skills_dir(home)
    source_path = (
        _normalize_primary_source(source) if source else find_bundled_skill_source()
    )
    temp_checkout: tempfile.TemporaryDirectory[str] | None = None
    source_origin = "explicit" if source else "bundled_distribution"
    if source_path is None and allow_github_fetch:
        try:
            temp_checkout, source_path = _fetch_compact_skill_bundle(release_ref)
            source_origin = f"github_release_skill_bundle:{release_ref}"
        except RuntimeError:
            source_path = None
    if source_path is None:
        source_path = find_local_skill_source()
        source_origin = "developer_checkout"
    if source_path is None:
        raise FileNotFoundError(
            f"Could not locate skills/{SKILL_NAME}; pass --source or allow GitHub fetch."
        )

    skills_dir.mkdir(parents=True, exist_ok=True)
    stage_root = skills_dir / ".staging" / f"ea-{uuid.uuid4().hex}"
    rollback_root = stage_root / ".rollback"
    staged: dict[str, Path] = {}
    validations: dict[str, dict[str, Any]] = {}
    backups: dict[str, str | None] = {}
    replaced: list[str] = []
    installed: list[str] = []
    touched: list[str] = []
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    transaction_id = f"ea-skill-install-{stamp}-{uuid.uuid4().hex[:8]}"
    before = _installed_skill_snapshot(skills_dir)

    try:
        for name, skill_source in _skill_sources(source_path):
            stage = stage_root / name
            stage.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(skill_source, stage)
            validation = validate_skill(stage, validator=validator)
            identity = inspect_skill_identity(stage, expected_name=name)
            validations[name] = {"structure": validation, "identity": identity}
            if validation["status"] == "fail" or identity["status"] == "fail":
                journal_path = _write_install_journal(
                    skills_dir,
                    transaction_id=transaction_id,
                    status="fail",
                    source_origin=source_origin,
                    before=before,
                    after=_installed_skill_snapshot(skills_dir),
                    restored_previous=True,
                    error="staged_validation_failed",
                )
                return {
                    "schema_version": "1.0",
                    "check_type": "ea_codex_skill_install",
                    "status": "fail",
                    "identity": identity_record(),
                    "source": {"path": str(source_path), "origin": source_origin},
                    "target": str(default_skill_target(home)),
                    "targets": {},
                    "backups": {},
                    "validation": validation,
                    "validations": validations,
                    "restored_previous": True,
                    "transaction_journal": str(journal_path),
                    "next_steps": [
                        "Fix the staged skill validation failure; the existing installation was not changed."
                    ],
                }
            staged[name] = stage

        for name, _ in _skill_sources(source_path):
            target = skills_dir / name
            rollback = rollback_root / name
            backup: Path | None = None
            if target.exists():
                replaced.append(name)
                rollback.parent.mkdir(parents=True, exist_ok=True)
                if backup_existing:
                    backup = _backup_path(skills_dir, name, stamp)
                    shutil.move(str(target), str(backup))
                else:
                    shutil.move(str(target), str(rollback))
            touched.append(name)
            backups[name] = str(backup) if backup else None
            os.replace(staged[name], target)
            installed.append(name)

        for name in installed:
            target = skills_dir / name
            post_validation = validate_skill(target, validator=validator)
            post_identity = inspect_skill_identity(target, expected_name=name)
            if post_validation["status"] == "fail" or post_identity["status"] == "fail":
                raise RuntimeError(f"Post-install validation failed for {name}")
            validations[name]["post_install"] = post_validation

        journal_path = _write_install_journal(
            skills_dir,
            transaction_id=transaction_id,
            status="pass",
            source_origin=source_origin,
            before=before,
            after=_installed_skill_snapshot(skills_dir),
            restored_previous=False,
        )
        return {
            "schema_version": "1.0",
            "check_type": "ea_codex_skill_install",
            "status": "pass",
            "identity": identity_record(),
            "source": {"path": str(source_path), "origin": source_origin},
            "codex_home": str(home),
            "target": str(default_skill_target(home)),
            "targets": {name: str(skills_dir / name) for name in installed},
            "backup": backups.get(SKILL_NAME),
            "backups": backups,
            "replaced_existing": bool(replaced),
            "replaced_skills": replaced,
            "validation": validations[SKILL_NAME]["post_install"],
            "validations": validations,
            "restored_previous": False,
            "transaction_journal": str(journal_path),
            "next_steps": [
                "Restart Codex before using the updated skill in a new task.",
                f"Use the public invocation: {SKILL_INVOCATION}",
                "Run `ea doctor` to verify CLI and skill identity.",
            ],
        }
    except BaseException as exc:
        for name in reversed(touched):
            target = skills_dir / name
            if target.exists():
                shutil.rmtree(target)
            backup_value = backups.get(name)
            backup = Path(backup_value) if backup_value else rollback_root / name
            if backup.exists():
                shutil.move(str(backup), str(target))
        _write_install_journal(
            skills_dir,
            transaction_id=transaction_id,
            status="fail",
            source_origin=source_origin,
            before=before,
            after=_installed_skill_snapshot(skills_dir),
            restored_previous=True,
            error=str(exc),
        )
        raise
    finally:
        if stage_root.exists():
            shutil.rmtree(stage_root, ignore_errors=True)
        if temp_checkout is not None:
            temp_checkout.cleanup()


def _latest_backup(skills_dir: Path, name: str) -> Path | None:
    backup_root = skills_dir / ".backups"
    if not backup_root.exists():
        return None
    candidates = sorted(
        (path for path in backup_root.glob(f"{name}-*") if path.is_dir()),
        key=lambda path: path.stat().st_mtime,
    )
    return candidates[-1] if candidates else None


def rollback_codex_skills(
    *,
    codex_home_path: Path | None = None,
    validator: Path | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    home = codex_home_path or codex_home()
    skills_dir = codex_skills_dir(home)
    selected = {
        name: _latest_backup(skills_dir, name)
        for name in (SKILL_NAME, *LEGACY_SKILL_NAMES)
    }
    missing = [name for name, backup in selected.items() if backup is None]
    if missing:
        raise FileNotFoundError(
            f"No rollback backup is available for: {', '.join(missing)}"
        )
    if not confirmed:
        return {
            "schema_version": "1.0",
            "status": "needs_confirmation",
            "will_restore": {name: str(path) for name, path in selected.items()},
            "will_replace": {name: str(skills_dir / name) for name in selected},
        }
    stage = skills_dir / ".staging" / f"rollback-{uuid.uuid4().hex}"
    current = stage / ".current"
    restored: list[str] = []
    try:
        for name, backup in selected.items():
            staged = stage / name
            shutil.copytree(backup, staged)
            validation = validate_skill(staged, validator=validator)
            identity = inspect_skill_identity(staged, expected_name=name)
            if validation["status"] == "fail" or identity["status"] == "fail":
                raise RuntimeError(f"Rollback backup validation failed for {name}")
        for name in selected:
            target = skills_dir / name
            if target.exists():
                (current / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(target), str(current / name))
            os.replace(stage / name, target)
            restored.append(name)
        return {
            "schema_version": "1.0",
            "status": "completed",
            "restored": restored,
            "sources": {name: str(path) for name, path in selected.items()},
        }
    except BaseException:
        for name in restored:
            target = skills_dir / name
            if target.exists():
                shutil.rmtree(target)
            previous = current / name
            if previous.exists():
                shutil.move(str(previous), str(target))
        raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def uninstall_codex_skills(
    *,
    codex_home_path: Path | None = None,
    confirmed: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    home = codex_home_path or codex_home()
    skills_dir = codex_skills_dir(home)
    targets = [
        skills_dir / name
        for name in (SKILL_NAME, *LEGACY_SKILL_NAMES)
        if (skills_dir / name).exists()
    ]
    if not confirmed:
        return {
            "schema_version": "1.0",
            "status": "needs_confirmation",
            "will_remove": [str(path) for path in targets],
        }
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    backups: dict[str, str] = {}
    for target in targets:
        backup = _backup_path(skills_dir, target.name, f"uninstall-{stamp}")
        shutil.move(str(target), str(backup))
        backups[target.name] = str(backup)
    return {
        "schema_version": "1.0",
        "status": "completed",
        "removed": [path.name for path in targets],
        "backups": backups,
    }


def _ea_executable() -> str | None:
    return shutil.which("ea")


def read_ea_executable_identity(executable: str | None = None) -> dict[str, Any]:
    path = executable or _ea_executable()
    if not path:
        return {
            "status": "fail",
            "path": None,
            "identity": {},
            "returncode": None,
            "stderr": "EA CLI was not found on PATH.",
        }
    try:
        completed = subprocess.run(
            [path, "version", "--json"],
            text=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=20,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "status": "fail",
            "path": path,
            "identity": {},
            "returncode": None,
            "stderr": str(exc),
        }
    try:
        stdout = completed.stdout.decode("utf-8", errors="replace")
        stderr = completed.stderr.decode("utf-8", errors="replace")
        detected = json.loads(stdout) if stdout.strip() else {}
    except json.JSONDecodeError:
        detected = {}
        stderr = completed.stderr.decode("utf-8", errors="replace")
    return {
        "status": "pass" if completed.returncode == 0 and detected else "fail",
        "path": path,
        "identity": detected,
        "returncode": completed.returncode,
        "stderr": stderr.strip(),
    }


def inspect_ea_executable(executable: str | None = None) -> dict[str, Any]:
    raw = read_ea_executable_identity(executable)
    path = raw["path"]
    if not path:
        return {
            "name": "ea_cli",
            "status": "fail",
            "path": None,
            "code": "EA-INSTALL-CLI-NOT-FOUND",
            "message": "EA CLI was not found on PATH.",
            "next_steps": [
                f"Install with: uv tool install --python 3.12 git+{REPOSITORY_URL}.git@{RELEASE_LABEL}"
            ],
        }
    if raw["status"] == "fail":
        return {
            "name": "ea_cli",
            "status": "fail",
            "path": path,
            "code": "EA-INSTALL-CLI-EXECUTION-FAILED",
            "message": f"PATH-resolved EA CLI could not be executed: {raw['stderr']}",
            "next_steps": [
                f"Repair or remove the stale executable at `{path}`, then reinstall {DISTRIBUTION_NAME}."
            ],
        }
    detected = raw["identity"]
    expected = identity_record()
    matches = (
        raw["returncode"] == 0
        and detected.get("package_version") == expected["package_version"]
        and detected.get("distribution_name") == DISTRIBUTION_NAME
        and detected.get("release_label") == RELEASE_LABEL
        and detected.get("skill_invocation") == SKILL_INVOCATION
    )
    return {
        "name": "ea_cli",
        "status": "pass" if matches else "fail",
        "path": path,
        "returncode": raw["returncode"],
        "detected_identity": detected,
        "expected_identity": {
            "distribution_name": DISTRIBUTION_NAME,
            "package_version": __version__,
            "release_label": RELEASE_LABEL,
            "skill_invocation": SKILL_INVOCATION,
        },
        "stderr": raw["stderr"],
        "code": None if matches else "EA-INSTALL-CLI-IDENTITY-MISMATCH",
        "message": "PATH-resolved EA CLI identity matches."
        if matches
        else "PATH resolves to a missing, stale, or mismatched EA CLI.",
        "next_steps": []
        if matches
        else [
            f"Reinstall {DISTRIBUTION_NAME} {__version__} and ensure `{path}` is the intended executable."
        ],
    }


def _repo_example_path(start: Path | None = None) -> Path | None:
    for root in _repo_root_candidates(start):
        candidate = root / "examples" / "public-raman-project"
        if candidate.exists():
            return candidate
    return None


def run_public_example_check(example_workspace: Path | None = None) -> dict[str, Any]:
    workspace = example_workspace or _repo_example_path()
    if workspace is None or not workspace.exists():
        return {
            "name": "public_example_healthcheck",
            "status": "warning",
            "workspace": str(workspace) if workspace else None,
        }
    from ea.healthcheck import run_healthcheck

    result = run_healthcheck(workspace)
    return {
        "name": "public_example_healthcheck",
        "status": "pass" if result.get("status") == "pass" else "fail",
        "workspace": str(workspace),
        "healthcheck_status": result.get("status"),
        "error_count": result.get("error_count"),
        "warning_count": result.get("warning_count"),
    }


def install_check(
    *,
    codex_home_path: Path | None = None,
    skill_path: Path | None = None,
    validator: Path | None = None,
    run_example: bool = False,
    example_workspace: Path | None = None,
    skip_codex_skill: bool = False,
    executable: str | None = None,
) -> dict[str, Any]:
    identity = identity_record()
    home = codex_home_path or codex_home()
    target = skill_path or default_skill_target(home)
    checks: list[dict[str, Any]] = [python_preflight_record()]

    installed = identity["installed_distributions"]
    official_version = installed.get(DISTRIBUTION_NAME)
    legacy_installed = {
        name: installed[name] for name in LEGACY_DISTRIBUTION_NAMES if name in installed
    }
    package_status = (
        "pass" if official_version == __version__ and not legacy_installed else "fail"
    )
    checks.append(
        {
            "name": "ea_distribution",
            "status": package_status,
            "distribution": DISTRIBUTION_NAME,
            "expected_version": __version__,
            "installed_version": official_version,
            "legacy_installed": legacy_installed,
            "code": None
            if package_status == "pass"
            else "EA-INSTALL-DISTRIBUTION-MISMATCH",
            "next_steps": []
            if package_status == "pass"
            else [
                f"Install {DISTRIBUTION_NAME} {__version__} and remove legacy distributions after verification."
            ],
        }
    )
    checks.append(inspect_ea_executable(executable))
    checks.append(inspect_ea_feedback_companion(home))

    if not skip_codex_skill:
        for name in (SKILL_NAME, *LEGACY_SKILL_NAMES):
            path = target if name == SKILL_NAME else target.parent / name
            exists = path.is_dir()
            checks.append(
                {
                    "name": f"codex_skill_path:{name}",
                    "status": "pass" if exists else "fail",
                    "path": str(path),
                    "next_steps": [] if exists else ["Run `ea codex install-skill`."],
                }
            )
            if exists:
                checks.append(inspect_skill_identity(path, expected_name=name))
                checks.append(validate_skill(path, validator=validator))
    if run_example:
        checks.append(run_public_example_check(example_workspace))

    failures = [check for check in checks if check["status"] == "fail"]
    warnings = [check for check in checks if check["status"] == "warning"]
    status = "fail" if failures else "warning" if warnings else "pass"
    return {
        "schema_version": "1.0",
        "check_type": "ea_install_check",
        "status": status,
        "identity": identity,
        "codex_home": str(home),
        "skill_path": None if skip_codex_skill else str(target),
        "checks": checks,
        "next_steps": [
            "Resolve every failed identity check before using mutating workflows.",
            f"Use {SKILL_INVOCATION} in a new Codex task after checks pass.",
        ],
    }


def setup_installation(
    *,
    source: Path | None = None,
    codex_home_path: Path | None = None,
    validator: Path | None = None,
    release_ref: str = RELEASE_LABEL,
    lang: str = "zh",
) -> dict[str, Any]:
    installed = install_codex_skill(
        source=source,
        codex_home_path=codex_home_path,
        validator=validator,
        release_ref=release_ref,
    )
    return {
        "schema_version": "1.0",
        "status": installed["status"],
        "skill_install": installed,
        "onboarding": onboarding_post_install_record(event="install", lang=lang),
        "next_command": "ea doctor",
    }


def lifecycle_update_plan(*, release_ref: str = RELEASE_LABEL) -> dict[str, Any]:
    previous = read_ea_executable_identity()
    previous_ref = previous.get("identity", {}).get("release_label")
    return {
        "schema_version": "1.0",
        "status": "ready",
        "release_ref": release_ref,
        "previous_release_ref": previous_ref,
        "will_write": [
            "installed CLI environment",
            "Codex skills/ea",
            "Codex skills/ea-v0-2",
        ],
        "cli_command": [
            "uv",
            "tool",
            "install",
            "--force",
            "--python",
            "3.12",
            f"git+{REPOSITORY_URL}.git@{release_ref}",
        ],
        "skill_command": ["ea", "codex", "install-skill", "--release-ref", release_ref],
        "rollback_command": ["ea", "rollback", "--yes"],
        "read_only": True,
    }


def _run_lifecycle_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    completed = subprocess.run(
        command,
        text=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=env,
    )
    completed.stdout = _decode_subprocess_output(completed.stdout)
    completed.stderr = _decode_subprocess_output(completed.stderr)
    return completed


def _write_lifecycle_journal(
    *,
    skills_dir: Path,
    operation: str,
    status: str,
    before: dict[str, Any],
    after: dict[str, Any],
    restored_previous: bool,
    stage: str,
    error: str | None = None,
) -> Path:
    transaction_id = f"ea-{operation}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    journal_root = skills_dir / ".transactions"
    journal_root.mkdir(parents=True, exist_ok=True)
    path = journal_root / f"{transaction_id}.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "transaction_id": transaction_id,
                "operation": operation,
                "status": status,
                "stage": stage,
                "before": before,
                "after": after,
                "restored_previous": restored_previous,
                "error": error,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def update_installation(
    *,
    release_ref: str = RELEASE_LABEL,
    confirmed: bool = False,
    uv_executable: str | None = None,
    command_runner=None,
    codex_home_path: Path | None = None,
) -> dict[str, Any]:
    plan = lifecycle_update_plan(release_ref=release_ref)
    if not confirmed:
        return {**plan, "status": "needs_confirmation"}
    uv = uv_executable or shutil.which("uv")
    if not uv:
        raise FileNotFoundError(
            "uv was not found; install uv or perform the documented manual package transaction."
        )
    runner = command_runner or _run_lifecycle_command
    skills_dir = codex_skills_dir(codex_home_path)
    before = {
        "cli": read_ea_executable_identity(),
        "skills": _installed_skill_snapshot(skills_dir),
    }
    previous_ref = plan.get("previous_release_ref") or "v0.9.7"
    python_minor = f"{sys.version_info.major}.{sys.version_info.minor}"
    install_command = [
        uv,
        "tool",
        "install",
        "--force",
        "--python",
        python_minor,
        f"git+{REPOSITORY_URL}.git@{release_ref}",
    ]
    rollback_command = [
        uv,
        "tool",
        "install",
        "--force",
        "--python",
        python_minor,
        f"git+{REPOSITORY_URL}.git@{previous_ref}",
    ]
    package_result = runner(install_command)
    if package_result.returncode != 0:
        after = {
            "cli": read_ea_executable_identity(),
            "skills": _installed_skill_snapshot(skills_dir),
        }
        journal_path = _write_lifecycle_journal(
            skills_dir=skills_dir,
            operation="update_installation",
            status="fail",
            stage="cli_update",
            before=before,
            after=after,
            restored_previous=True,
            error=package_result.stderr.strip(),
        )
        return {
            **plan,
            "status": "fail",
            "stage": "cli_update",
            "command": install_command,
            "stderr": package_result.stderr.strip(),
            "restored_previous": True,
            "journal_path": str(journal_path),
        }
    executable = _ea_executable()
    skill_command = [
        executable or "ea",
        "codex",
        "install-skill",
        "--release-ref",
        release_ref,
        "--json",
    ]
    skill_result = runner(skill_command)
    if skill_result.returncode != 0:
        rollback_result = runner(rollback_command)
        restored = rollback_result.returncode == 0
        after = {
            "cli": read_ea_executable_identity(),
            "skills": _installed_skill_snapshot(skills_dir),
        }
        journal_path = _write_lifecycle_journal(
            skills_dir=skills_dir,
            operation="update_installation",
            status="fail",
            stage="skill_update",
            before=before,
            after=after,
            restored_previous=restored,
            error=skill_result.stderr.strip(),
        )
        return {
            **plan,
            "status": "fail",
            "stage": "skill_update",
            "command": skill_command,
            "stderr": skill_result.stderr.strip(),
            "rollback_command": rollback_command,
            "restored_previous": restored,
            "rollback_stderr": rollback_result.stderr.strip(),
            "journal_path": str(journal_path),
        }
    after = {
        "cli": read_ea_executable_identity(),
        "skills": _installed_skill_snapshot(skills_dir),
    }
    journal_path = _write_lifecycle_journal(
        skills_dir=skills_dir,
        operation="update_installation",
        status="completed",
        stage="complete",
        before=before,
        after=after,
        restored_previous=False,
    )
    return {
        **plan,
        "status": "completed",
        "cli_command": install_command,
        "skill_command": skill_command,
        "previous_release_ref": previous_ref,
        "rollback_command": rollback_command,
        "restored_previous": False,
        "journal_path": str(journal_path),
    }


def rollback_installation(
    *,
    release_ref: str = "v0.9.7",
    confirmed: bool = False,
    uv_executable: str | None = None,
    command_runner=None,
) -> dict[str, Any]:
    return update_installation(
        release_ref=release_ref,
        confirmed=confirmed,
        uv_executable=uv_executable,
        command_runner=command_runner,
    )


def uninstall_installation(
    *,
    codex_home_path: Path | None = None,
    confirmed: bool = False,
    uv_executable: str | None = None,
    command_runner=None,
) -> dict[str, Any]:
    skill_plan = uninstall_codex_skills(
        codex_home_path=codex_home_path, confirmed=False
    )
    uv = uv_executable or shutil.which("uv")
    cli_command = [uv or "uv", "tool", "uninstall", DISTRIBUTION_NAME]
    if not confirmed:
        return {
            "schema_version": "1.0",
            "status": "needs_confirmation",
            "skill_plan": skill_plan,
            "cli_command": cli_command,
            "read_only": True,
        }
    if not uv:
        raise FileNotFoundError(
            "uv was not found; uninstall the CLI manually after removing the Codex skills."
        )
    skills_result = uninstall_codex_skills(
        codex_home_path=codex_home_path, confirmed=True
    )
    runner = command_runner or _run_lifecycle_command
    cli_result = runner(cli_command)
    if cli_result.returncode != 0:
        try:
            rollback_codex_skills(codex_home_path=codex_home_path, confirmed=True)
            restored = True
        except (OSError, RuntimeError, FileNotFoundError):
            restored = False
        return {
            "schema_version": "1.0",
            "status": "fail",
            "stage": "cli_uninstall",
            "stderr": cli_result.stderr.strip(),
            "restored_previous": restored,
        }
    return {
        "schema_version": "1.0",
        "status": "completed",
        "skill_uninstall": skills_result,
        "cli_command": cli_command,
    }


def onboarding_post_install_record(
    *, event: str = "install", lang: str = "zh"
) -> dict[str, Any]:
    if event not in {"install", "update"}:
        raise ValueError("event must be install or update")
    if lang not in {"zh", "en"}:
        raise ValueError("lang must be zh or en")
    return {
        "schema_version": "1.0",
        "message_type": "ea_post_install_onboarding",
        "event": event,
        "language": lang,
        "identity": identity_record(),
        "capabilities": [
            "consult_without_project_writes",
            "guided_project_creation",
            "protected_raw_import_and_review_gated_analysis",
            "traceable_reports_exports_and_project_status",
            "permission_gated_literature_and_review_gated_evidence_datasets",
        ],
        "recommended_first_checks": [
            "ea version --json",
            "ea doctor --json",
            "ea start --help",
        ],
        "confirmation_phrase": "确定配置" if lang == "zh" else "Confirm setup",
        "boundaries": [
            "Onboarding does not create project files.",
            "Zotero, browser, institution access, and full-text acquisition remain opt-in.",
            "Scientific decisions and durable memory remain review-gated.",
        ],
        "compatibility": {
            "legacy_distribution_names": list(LEGACY_DISTRIBUTION_NAMES),
            "legacy_skill_invocations": list(LEGACY_SKILL_INVOCATIONS),
            "note": "Use $ea for new work; historical compatibility identifiers remain readable.",
        },
    }


def render_onboarding_post_install(record: dict[str, Any]) -> str:
    identity = record["identity"]
    if record["language"] == "en":
        return "\n".join(
            [
                f"{identity['public_version']} is ready.",
                "Use $ea for new work. Consult mode writes no project files.",
                "Run `ea doctor` to verify CLI, distribution, and both skill identities.",
                "Run `ea start` when you want a guided first project.",
                "Literature acquisition requires explicit permission; scientific evidence remains review-gated.",
            ]
        )
    return "\n".join(
        [
            f"{identity['public_version']} 已就绪。",
            "新任务请使用 `$ea`；咨询模式不会写入项目文件。",
            "运行 `ea doctor` 检查 CLI、distribution 和两个 skill 身份。",
            "准备创建首个项目时运行 `ea start`。",
            "文献获取需要明确授权；科学证据仍需人工复核。",
        ]
    )


def render_install_summary(result: dict[str, Any]) -> str:
    lines = [
        f"{PRODUCT_NAME} doctor: {result['status']}",
        f"Version: {result['identity']['public_version']}",
        "Checks:",
    ]
    for check in result.get("checks", []):
        detail = (
            check.get("message")
            or check.get("path")
            or check.get("installed_version")
            or ""
        )
        lines.append(f"- {check.get('name')}: {check.get('status')} {detail}".rstrip())
        for step in check.get("next_steps", []):
            lines.append(f"  next: {step}")
    return "\n".join(lines)


def render_install_skill_summary(result: dict[str, Any]) -> str:
    lines = [
        f"Installed {result['identity']['public_version']} Codex skills.",
        f"Primary invocation: {SKILL_INVOCATION}",
        f"Primary target: {result['target']}",
        f"Validation: {result['validation']['status']}",
    ]
    for name, backup in result.get("backups", {}).items():
        if backup:
            lines.append(f"Previous {name} backup: {backup}")
    lines.extend(["Restart Codex.", "Run `ea doctor` before a mutating workflow."])
    return "\n".join(lines)


def build_install_check_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"Check {PUBLIC_VERSION} installation readiness."
    )
    parser.add_argument("--codex-home", type=Path)
    parser.add_argument("--skill-path", type=Path)
    parser.add_argument("--quick-validate", type=Path)
    parser.add_argument("--run-example-check", action="store_true")
    parser.add_argument("--example-workspace", type=Path)
    parser.add_argument("--skip-codex-skill", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def install_check_main(argv: list[str] | None = None) -> int:
    args = build_install_check_parser().parse_args(argv)
    result = install_check(
        codex_home_path=args.codex_home,
        skill_path=args.skill_path,
        validator=args.quick_validate,
        run_example=args.run_example_check,
        example_workspace=args.example_workspace,
        skip_codex_skill=args.skip_codex_skill,
    )
    print(
        json.dumps(result, ensure_ascii=False, indent=2)
        if args.json
        else render_install_summary(result)
    )
    return 0 if result["status"] != "fail" else 2


if __name__ == "__main__":
    raise SystemExit(install_check_main())
