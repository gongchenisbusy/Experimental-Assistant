# EA Public Install And Codex Skill Setup

This guide is the shortest public path from a fresh checkout or release package to a working EA CLI and Codex skill. It separates ordinary use, development checks, and local integration tests so public defaults must not inherit a developer machine.

Version naming note: EA is currently distributed as EA v0.9 RC (`0.9.0rc1`, release label `v0.9-rc1`). The Python package/archive prefix and Codex skill folder still use `ea-v0-2` as a compatibility identifier, so users should not read that folder name as the public release version.

## 1. Requirements

- Python 3.11 or newer.
- Git, when installing from a GitHub repository checkout.
- Codex, when the user wants the EA skill available in future Codex threads.
- A local folder where the user is allowed to create EA project workspaces.
- Optional Zotero, browser assistance, institution access, or signing keys only after the user explicitly chooses those workflows.

Do not configure developer-machine Zotero databases, browser profiles, institution routes, private caches, credentials, cookies, or test fixture paths as public defaults.

## 2. Ordinary User Install

From the public GitHub repository:

```bash
git clone https://github.com/gongchenisbusy/Experimental-Assistant.git ea
cd ea
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e .
ea --help
```

Release packages are published at `https://github.com/gongchenisbusy/Experimental-Assistant/releases/tag/v0.9-rc1`. Download the `ea-v0-2-0.9.0rc1-COMMIT-release.zip` archive and matching `.sha256` sidecar from that page when you want a fixed packaged handoff instead of a git clone.

From an extracted release package:

```bash
cd /path/to/extracted/ea-release
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e .
ea --help
```

The command `ea --help` is the first sanity check. It should print the available EA commands without requiring Zotero, a browser, institution login, live web access, private caches, or signing keys.

## 3. Developer Install

Use the developer extra only when the user intends to run tests or release checks:

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest -q
python3 scripts/public_release_smoke.py --dry-run
```

Before publishing or redistributing a repository package, run:

```bash
python3 scripts/public_release_smoke.py
python3 scripts/build_release_manifest.py
python3 scripts/build_release_package.py
python3 scripts/verify_release_package.py dist/ea-v0-2-0.9.0rc1-COMMIT-release.zip
python3 scripts/build_distribution_checklist.py
```

Optional signing must use explicit user-managed key paths. EA must not search for private keys or assume a developer key location.

## 4. Codex Skill Setup

The repository contains the EA skill package at `skills/ea-v0-2/`. Install it into Codex's skill directory by copying the whole folder:

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
rm -rf "${CODEX_HOME:-$HOME/.codex}/skills/ea-v0-2"
cp -R skills/ea-v0-2 "${CODEX_HOME:-$HOME/.codex}/skills/ea-v0-2"
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" \
  "${CODEX_HOME:-$HOME/.codex}/skills/ea-v0-2"
```

If Codex is running from this repository directly, an agent can also use the repository skill path `skills/ea-v0-2/` without copying it. Copying is the public install path because it makes the skill available to new Codex threads outside this checkout.

When opening a new Codex thread, ask the agent to use `$ea-v0-2` to initialize or continue a local EA project. The agent should first read `docs/PUBLIC_ONBOARDING.md` for the user workflow, then load only method-specific references as needed.

## 5. First Public Example

Run packaged examples before touching a real project:

```bash
ea healthcheck examples/public-raman-project
ea eval project examples/public-raman-project --no-write
ea healthcheck examples/public-ftir-assignment-project
ea eval project examples/public-ftir-assignment-project --no-write
ea healthcheck examples/public-uv-vis-project
ea eval project examples/public-uv-vis-project --no-write
ea healthcheck examples/public-xps-be-project
ea eval project examples/public-xps-be-project --no-write
```

These examples are public-safe orientation artifacts. Copy an example folder before experimenting; do not treat it as the user's real project memory.

## 6. First Real Project

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

Only enable Zotero, browser assistance, institution login, literature caches, full-text acquisition, or release signing after the user explicitly confirms the boundary and supplies their own local paths or settings.

## 7. Local Integration Tests

Local integration tests may use real Zotero, browser sessions, institution login, or private caches only when they are explicitly marked local-test-only and kept out of release-facing defaults. Public documentation, release manifests, examples, and skill package defaults must remain runnable without those resources.
