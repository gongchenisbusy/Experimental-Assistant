# Release Workflow

Use this reference when preparing the EA v0.2 repository for public handoff or a release checkpoint.

Commands:

```bash
ea-public-release-smoke
ea-release-manifest
ea-release-package
ea-verify-release-package dist/ea-v0-2-0.2.0-abcdef0-release.zip
```

Script equivalents:

```bash
python3 scripts/public_release_smoke.py
python3 scripts/build_release_manifest.py
python3 scripts/build_release_package.py
python3 scripts/verify_release_package.py dist/ea-v0-2-0.2.0-abcdef0-release.zip
```

Release smoke gate:

- Runs the Python test suite.
- Validates `skills/ea-v0-2` with `quick_validate.py`.
- Checks core CLI help paths.
- Checks the release manifest entry point.
- Checks the release package entry point.
- Checks the release package verifier entry point.
- Runs the public-user portability scan.

Release manifest:

- Writes `dist/ea-v0.2-release-manifest.yml` by default.
- Records package metadata from `pyproject.toml`.
- Records git commit, branch, tags at `HEAD`, and dirty files.
- Records console script entry points.
- Records SHA-256 checksums for selected release inputs: README, pyproject, `src/ea`, `skills/ea-v0-2`, `skill-registry`, `docs`, `tests`, and `scripts`.
- Excludes generated or local-only directories such as `.git`, `.venv`, `dist`, `build`, caches, and `__pycache__`.
- Records the smoke-gate command contract and public-user boundary notes.

Release package:

- Writes `dist/ea-v0-2-0.2.0-{commit}-release.zip` by default.
- Writes a `.zip.sha256` sidecar next to the archive.
- Stores all archive members under one top-level directory.
- Includes `ea-v0.2-release-manifest.yml` inside the archive.
- Includes the same selected release inputs covered by the manifest.
- Uses fixed zip timestamps and sorted input order for deterministic archive metadata.

Release package verification:

- Verifies the `.zip.sha256` sidecar.
- Verifies that the zip opens successfully.
- Finds the embedded `ea-v0.2-release-manifest.yml`.
- Verifies every release input listed by the manifest exists in the archive.
- Verifies each listed payload file size and SHA-256.
- Returns JSON with `status: pass` or `status: fail` and concrete failure records.

Scope limits:

- Do not treat the manifest, package, or sidecar checksum as a cryptographic signature.
- Do not use it to verify scientific correctness.
- Do not add developer-machine Zotero paths, browser profiles, institution login settings, live web search, PDF downloads, or private literature caches.
- If a signed release is needed, add a separate user-managed key/signature workflow.
