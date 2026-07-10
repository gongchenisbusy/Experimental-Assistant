# EA Public Install And Codex Skill Setup

Product identity: `Experimental Assistant v0.9.7`. The CLI is `ea`, the Python distribution is `experimental-assistant`, and the primary Codex skill is `$ea`.

Naming note: `$ea-v0-2` is the deprecated compatibility identifier retained through v1.0.x. It is installed beside `$ea` so older tasks continue to route correctly; new users should invoke `$ea`.

Repository: <https://github.com/gongchenisbusy/Experimental-Assistant>

Release: <https://github.com/gongchenisbusy/Experimental-Assistant/releases/tag/v0.9.7>

Chinese quick start: `docs/QUICKSTART_ZH.md`. Stable error catalog: `docs/ERROR_CATALOG.md`.

## Quick Start For Users

EA supports Python 3.11, 3.12, and 3.13. Python 3.12 is recommended.

```bash
uv tool install --python 3.12 git+https://github.com/gongchenisbusy/Experimental-Assistant.git@v0.9.7
ea setup
ea doctor
```

`ea setup` installs both Codex skill entries transactionally. Restart Codex, create a new task, and invoke `$ea`.

Expected identity:

```text
Product: Experimental Assistant
Version: 0.9.7
Distribution: experimental-assistant
Primary skill: $ea
Compatibility skill: $ea-v0-2
```

## Installation Layers

- Layer 1: EA CLI. The `experimental-assistant` distribution provides `ea` and release helpers.
- Layer 2: Codex skill. `ea setup` installs `skills/ea` and the thin `skills/ea-v0-2` wrapper under `${CODEX_HOME:-$HOME/.codex}/skills`.

Installing only the skill does not provide the CLI. Installing only the CLI does not make `$ea` available to Codex. `ea doctor` checks the exact executable, distribution, version, both skills, and validation state.

## Verify The Install

```bash
ea version
ea capabilities
ea doctor
ea install-check --run-example-check
```

If another `ea` executable appears earlier on `PATH`, the doctor reports its path and identity mismatch instead of accepting it.

## First Project

Preview first, then confirm:

```bash
ea start /path/to/project \
  --name "Project name" \
  --direction "Research direction" \
  --material "Material system" \
  --experiment-type "Experiment type"

ea start /path/to/project \
  --name "Project name" \
  --direction "Research direction" \
  --material "Material system" \
  --experiment-type "Experiment type" \
  --yes

ea status /path/to/project
ea healthcheck /path/to/project
ea brief project /path/to/project
```

The older `ea init-project` command remains available for scripted compatibility.

## Import And Migration

Preview the encoding, delimiter, columns, units, and source hash without writing:

```bash
ea import preview /path/to/data.csv
ea import apply /path/to/project /path/to/data.csv --characterization-type raman --preview-hash SHA256 --yes
```

Inspect an existing project before changing its format:

```bash
ea migrate status /path/to/project
ea migrate plan /path/to/project
ea migrate apply /path/to/project --yes
ea migrate rollback /path/to/project --backup BACKUP_PATH --yes
```

Migration uses backups, operation journals, atomic replacement, and explicit confirmation.

## Update, Rollback, And Uninstall

These commands show a plan unless `--yes` is provided:

```bash
ea update
ea update --release-ref v0.9.7 --yes
ea rollback --release-ref v0.9.6
ea rollback --release-ref v0.9.6 --yes
ea uninstall
ea uninstall --yes
```

CLI/skill replacement is staged and validated before the installed skill directories are swapped. Rollback restores a verified release. Uninstall creates recoverable skill backups and does not delete EA project folders.

## Developer And Release Maintenance

Use an editable checkout for contribution, local validation, or release work.

```bash
git clone https://github.com/gongchenisbusy/Experimental-Assistant.git ea
cd ea
git checkout v0.9.7
python3 scripts/check_install_env.py
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e .
ea setup --source .
ea doctor
```

For development and release checks:

```bash
python3 -m pip install -e ".[dev,release]"
python3 -m pytest -q
python3 scripts/validate_skill_packages.py
python3 scripts/public_release_smoke.py
```

## Manual Skill Copy

The built-in transactional installer is preferred. A maintainer diagnosing a local checkout may manually copy and validate both entries:

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
cp -R skills/ea "${CODEX_HOME:-$HOME/.codex}/skills/ea"
cp -R skills/ea-v0-2 "${CODEX_HOME:-$HOME/.codex}/skills/ea-v0-2"
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" \
  "${CODEX_HOME:-$HOME/.codex}/skills/ea"
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" \
  "${CODEX_HOME:-$HOME/.codex}/skills/ea-v0-2"
```

The installer preserves unrelated skills such as `ea-v0-1`; it does not delete `ea-v0-1` or project data.

## Release Package Install

Download the release archive and `.sha256` sidecar from the v0.9.7 release page. Verify before extraction:

```bash
shasum -a 256 -c experimental-assistant-0.9.7-COMMIT-release.zip.sha256
python3 scripts/verify_release_package.py experimental-assistant-0.9.7-COMMIT-release.zip
```

Then install the extracted checkout with the editable-checkout steps above. Checksums detect corruption; publisher identity requires a trusted release/signing channel as explained in `docs/RELEASE_SECURITY_POLICY.md`.

## Troubleshooting

- `ea: command not found`: restart the shell or add the `uv tool` binary directory to `PATH`.
- Wrong product/version from `ea version`: run `command -v ea`, then reinstall with `uv tool install --force ...` and rerun `ea doctor`.
- `$ea` unavailable after setup: restart Codex and confirm `ea doctor` reports both skills as valid.
- Existing project format differs: run `ea migrate status` and `ea migrate plan`; do not edit project metadata by hand.
- Literature integration blocked: run `ea literature setup-preflight`; EA supports a no-Zotero degraded mode and does not assume accounts or institution access.

EA never searches for private release keys, browser profiles, credentials, or institutional login secrets. Optional integrations require explicit user-owned paths and lawful access.
