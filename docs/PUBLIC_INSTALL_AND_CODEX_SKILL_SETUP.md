# EA Public Install And Codex Skill Setup

This guide is the shortest public path from GitHub to a working Experimental Assistant CLI and Codex skill.

Product identity: `Experimental Assistant v0.9.5` with package compatibility name `ea-v0-2`. The Python package name and Codex skill folder intentionally remain `ea-v0-2` for compatibility with existing projects and skill installs. That name is not the public release version.

Public repository: `https://github.com/gongchenisbusy/Experimental-Assistant`

Release assets: `https://github.com/gongchenisbusy/Experimental-Assistant/releases/tag/v0.9.5`

## Quick Start For Users

Recommended public install from the fixed release tag:

```bash
uv tool install --python 3.12 git+https://github.com/gongchenisbusy/Experimental-Assistant.git@v0.9.5
ea codex install-skill
ea install-check
```

Expected result:

```text
Installed Experimental Assistant v0.9.5.
Package compatibility name: ea-v0-2 0.9.5.
Codex invocation: $ea-v0-2
Restart Codex before using this skill in a new thread.
```

After restarting Codex, open a new thread and invoke EA as `$ea-v0-2`. This is the compatibility skill name for Experimental Assistant v0.9.5.

## Requirements

- Python 3.11 or newer. Python 3.12 is recommended.
- `uv` for the shortest public install path, or Git plus Python 3.11+ for an editable checkout.
- Codex, when you want the EA skill available in future Codex threads.
- A local folder where you are allowed to create EA project workspaces.

If your system `python3` is older than 3.11, do not continue with `python3 -m pip install`. Use:

```bash
uv python install 3.12
uv tool install --python 3.12 git+https://github.com/gongchenisbusy/Experimental-Assistant.git@v0.9.5
```

From a repository checkout, you can run the standalone preflight before installing dependencies:

```bash
python3 scripts/check_install_env.py
```

## What Gets Installed

EA installation has two layers:

- Layer 1: EA CLI. This provides the `ea` command and release helper commands.
- Layer 2: Codex skill. This copies `skills/ea-v0-2` into `${CODEX_HOME:-$HOME/.codex}/skills/ea-v0-2` so new Codex threads can load the EA workflow.

Installing the Codex skill alone does not install the `ea` CLI. Installing the CLI alone does not make the skill available to new Codex threads. `ea install-check` verifies both layers.

## Codex Skill Setup

Use the built-in installer:

```bash
ea codex install-skill
```

The installer:

- locates the local checkout skill or fetches the `v0.9.5` skill from GitHub;
- installs it to `${CODEX_HOME:-$HOME/.codex}/skills/ea-v0-2`;
- backs up an existing `ea-v0-2` folder by default;
- does not delete `ea-v0-1`;
- runs Codex skill validation when `quick_validate.py` is available;
- prints the product name, public version, compatibility package name, skill path, invocation name, and restart guidance.

If you are running from a checkout and want to force a local source:

```bash
ea codex install-skill --source skills/ea-v0-2
```

Advanced manual copy is still possible, but it is no longer the default public path:

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
cp -R skills/ea-v0-2 "${CODEX_HOME:-$HOME/.codex}/skills/ea-v0-2"
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" \
  "${CODEX_HOME:-$HOME/.codex}/skills/ea-v0-2"
```

## Verify The Install

Run:

```bash
ea version
ea install-check
```

For a repository checkout, also run the public example check:

```bash
ea install-check --run-example-check
```

The install check reports:

- Python version and repair commands when Python is too old;
- EA package compatibility name and package version;
- `ea` executable path;
- Codex skill path;
- Codex skill validation result;
- optional public Raman example healthcheck;
- the Codex invocation string `$ea-v0-2`;
- whether a Codex restart is required.

## Editable Checkout Install

Use this path for development validation, local contribution, or when you want the examples and tests in a checkout:

```bash
git clone https://github.com/gongchenisbusy/Experimental-Assistant.git ea
cd ea
git checkout v0.9.5
python3 scripts/check_install_env.py
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e .
ea codex install-skill --source skills/ea-v0-2
ea install-check --run-example-check
```

The `python3` used here must be Python 3.11 or newer.

## Release Package Install

Use the GitHub Release zip when you need a fixed handoff package rather than a git checkout. Download `ea-v0-2-0.9.5-COMMIT-release.zip` and its `.sha256` sidecar from the release page, verify them, then install from the extracted folder:

```bash
shasum -a 256 -c ea-v0-2-0.9.5-COMMIT-release.zip.sha256
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e .
ea codex install-skill --source skills/ea-v0-2
ea install-check --run-example-check
```

## Existing EA Skills

Experimental Assistant v0.9.5 uses the `ea-v0-2` compatibility skill folder. Older `ea-v0-1` skills may remain installed for old workflows. The v0.9.5 installer does not remove `ea-v0-1` and does not modify existing project folders.

Use `$ea-v0-2` for new Experimental Assistant v0.9.5 work. Existing project folders from the EA compatibility line can be inspected with `ea healthcheck` and `ea eval project`.

## First Real Project

Create a project with explicit local metadata:

```bash
ea init-project /path/to/ea-project \
  --name "Project name" \
  --slug project-slug \
  --direction "Research direction" \
  --material "Material system" \
  --experiment-type "Experiment type"

ea config doctor /path/to/ea-project
ea healthcheck /path/to/ea-project
ea eval project /path/to/ea-project
```

Only enable Zotero, browser assistance, institution login, literature caches, full-text acquisition, or release signing after you explicitly confirm the boundary and supply your own local paths or settings.

## Developer And Release Maintenance

Use the developer extra only when you intend to run tests or release checks:

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest -q
python3 scripts/public_release_smoke.py
python3 scripts/build_release_manifest.py
python3 scripts/build_release_package.py
python3 scripts/verify_release_package.py dist/ea-v0-2-0.9.5-COMMIT-release.zip
python3 scripts/build_distribution_checklist.py
```

Optional signing must use explicit user-managed key paths. EA must not search for private keys or assume a developer key location.
