# Release Workflow

Use this reference when preparing the EA v0.2 repository for public handoff or a release checkpoint.

Commands:

```bash
ea-public-release-smoke
ea-release-manifest
```

Script equivalents:

```bash
python3 scripts/public_release_smoke.py
python3 scripts/build_release_manifest.py
```

Release smoke gate:

- Runs the Python test suite.
- Validates `skills/ea-v0-2` with `quick_validate.py`.
- Checks core CLI help paths.
- Checks the release manifest entry point.
- Runs the public-user portability scan.

Release manifest:

- Writes `dist/ea-v0.2-release-manifest.yml` by default.
- Records package metadata from `pyproject.toml`.
- Records git commit, branch, tags at `HEAD`, and dirty files.
- Records console script entry points.
- Records SHA-256 checksums for selected release inputs: README, pyproject, `src/ea`, `skills/ea-v0-2`, `skill-registry`, `docs`, `tests`, and `scripts`.
- Excludes generated or local-only directories such as `.git`, `.venv`, `dist`, `build`, caches, and `__pycache__`.
- Records the smoke-gate command contract and public-user boundary notes.

Scope limits:

- Do not treat the manifest as a cryptographic signature.
- Do not use it to verify scientific correctness.
- Do not add developer-machine Zotero paths, browser profiles, institution login settings, live web search, PDF downloads, or private literature caches.
- If a signed release is needed, add a separate user-managed key/signature workflow.
