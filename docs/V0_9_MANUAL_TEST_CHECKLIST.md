# Experimental Assistant v0.9.6 Manual Test Checklist

Use this checklist after automated gates pass. Record failures as issues before promoting v0.9.6 toward v1.0.

## Install And Skill Setup

- [ ] Clone or unpack the release package in a path that is not the development checkout.
- [ ] Create a new virtual environment and run `python3 -m pip install -e .`.
- [ ] Confirm `ea --help` works without Zotero, browser state, institution access, private caches, or signing keys.
- [ ] Copy `skills/ea-v0-2` into the Codex skills directory and run `quick_validate.py`.
- [ ] Start a fresh Codex thread and confirm the skill can orient from `docs/PUBLIC_ONBOARDING.md`.

## Public Examples

- [ ] Run healthcheck and eval on `examples/public-raman-project`.
- [ ] Run healthcheck and eval on `examples/public-ftir-assignment-project`.
- [ ] Export the FTIR source-backed report as HTML and confirm the figure and references are visible.
- [ ] Export the FTIR source-backed report bundle with trace and zip, then verify the bundle and archive.
- [ ] Run healthcheck and eval on `examples/public-uv-vis-project`.
- [ ] Run healthcheck and eval on `examples/public-xps-be-project`.

## First Real Project Walkthrough

- [ ] Initialize a project with explicit user-provided metadata.
- [ ] Run config doctor, healthcheck, eval, and brief.
- [ ] Import one small raw file, create required review records, process, generate a report, export HTML, and export a report bundle.
- [ ] Confirm the user-facing response can use the brief without dumping JSON, hashes, or review IDs by default.

## Literature Boundary Walkthrough

- [ ] Run a no-Zotero literature readiness check and confirm it gives degraded-mode next actions.
- [ ] Generate a Zotero-Codex bridge/readiness view from placeholder user settings and confirm no credentials or account files are stored.
- [ ] Simulate an acquisition status import from local status artifacts and run reconciliation/acceptance checklist if artifacts are available.
- [ ] Confirm institution access guidance pauses for user-managed login rather than attempting access.

## Release Package Walkthrough

- [ ] Run full pytest.
- [ ] Run skill validation.
- [ ] Run public release smoke.
- [ ] Build release manifest and release package.
- [ ] Verify release package.
- [ ] Build distribution checklist.
- [ ] Confirm the release package includes docs, examples, tests, scripts, skill package, and source code, but excludes `.venv`, `dist`, caches, and local-test-only files.

## Decision

- [ ] No blocking automated failures remain.
- [ ] No public safety boundary failure remains.
- [ ] Known limitations are documented in `docs/V0_9_KNOWN_LIMITATIONS.md`.
- [ ] Any v1.0 follow-up issue is documented with reproduction steps and artifact paths.
