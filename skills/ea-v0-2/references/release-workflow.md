# Release Workflow

Use this reference when preparing the EA v0.2 repository for public handoff or a release checkpoint.

Commands:

```bash
ea-public-release-smoke
ea-release-manifest
ea-release-package
ea-verify-release-package dist/ea-v0-2-0.2.0-abcdef0-release.zip
ea-release-keygen --private-key /path/to/user-release-private.pem --public-key /path/to/user-release-public.pem
ea-sign-release-package dist/ea-v0-2-0.2.0-abcdef0-release.zip --private-key /path/to/user-release-private.pem --public-key /path/to/user-release-public.pem
ea-verify-release-signature dist/ea-v0-2-0.2.0-abcdef0-release.zip --public-key /path/to/user-release-public.pem
ea-release-checklist
```

Script equivalents:

```bash
python3 scripts/public_release_smoke.py
python3 scripts/build_release_manifest.py
python3 scripts/build_release_package.py
python3 scripts/verify_release_package.py dist/ea-v0-2-0.2.0-abcdef0-release.zip
python3 scripts/generate_release_keypair.py --private-key /path/to/user-release-private.pem --public-key /path/to/user-release-public.pem
python3 scripts/sign_release_package.py dist/ea-v0-2-0.2.0-abcdef0-release.zip --private-key /path/to/user-release-private.pem --public-key /path/to/user-release-public.pem
python3 scripts/verify_release_signature.py dist/ea-v0-2-0.2.0-abcdef0-release.zip --public-key /path/to/user-release-public.pem
python3 scripts/build_distribution_checklist.py
```

Release smoke gate:

- Runs the Python test suite.
- Validates `skills/ea-v0-2` with `quick_validate.py`.
- Checks core CLI help paths.
- Checks the release manifest entry point.
- Checks the release package entry point.
- Checks the release package verifier entry point.
- Checks the release signature keygen/sign/verify help entry points without requiring real user keys.
- Checks the release distribution checklist help entry point.
- Runs the public-user portability scan.

Release manifest:

- Writes `dist/ea-v0.2-release-manifest.yml` by default.
- Records package metadata from `pyproject.toml`.
- Records git commit, branch, tags at `HEAD`, and dirty files.
- Records console script entry points.
- Records SHA-256 checksums for selected release inputs: README, pyproject, `src/ea`, `skills/ea-v0-2`, `skill-registry`, `docs`, `tests`, and `scripts`.
- Excludes generated or local-only directories such as `.git`, `.venv`, `dist`, `build`, caches, and `__pycache__`.
- Records the smoke-gate command contract and public-user boundary notes.
- Records that detached Ed25519 signing is supported as an optional user-managed workflow while the generated manifest itself remains unsigned unless separately signed.

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

Optional release package signing:

- Generates a user-controlled Ed25519 keypair only when the user explicitly supplies private/public key output paths.
- Signs an existing release zip into a detached `.sig.yml` sidecar.
- Includes archive filename, archive size, archive SHA-256, optional checksum-sidecar hash, public-key fingerprint, key id, timestamp, and signed-payload hash in the sidecar.
- Verifies the `.sha256` package integrity gate and then verifies the detached signature with the user-supplied public key.
- Returns JSON with `status: pass` or `status: fail` and concrete failure records.
- Supports encrypted private-key PEM files when the passphrase is supplied through `--passphrase-env`.

Distribution checklist:

- Writes `dist/ea-v0.2-distribution-checklist.json` and `dist/ea-v0.2-distribution-checklist.md` by default.
- Summarizes current package metadata, git state, tags at `HEAD`, required release commands, public boundary notes, required artifact presence, package verification state, and optional signature state.
- Reads existing `dist/` artifacts; it does not build packages, generate keys, sign archives, upload releases, or use network access.
- Treats detached signatures as optional. If a signature is present and the user supplies `--public-key`, the checklist verifies it; otherwise it records that the signature is absent or unverified.
- Returns non-zero only when required distribution artifacts or required verification checks fail.

Scope limits:

- Do not treat the manifest, package, or sidecar checksum as a cryptographic signature.
- Do not use it to verify scientific correctness.
- Do not add developer-machine Zotero paths, browser profiles, institution login settings, live web search, PDF downloads, or private literature caches.
- Do not assume developer-machine release key paths. Ask the user for key paths or use paths the user explicitly provides.
