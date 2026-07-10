# Experimental Assistant v0.9.7 Release Verification

This guide defines the maintainer and recipient checks for Experimental Assistant v0.9.7. Repository: <https://github.com/gongchenisbusy/Experimental-Assistant>. Release: <https://github.com/gongchenisbusy/Experimental-Assistant/releases/tag/v0.9.7>.

The checks do not require Zotero, browser profiles, institution login, private literature caches, or developer-machine key paths.

## Expected Artifacts

- `experimental_assistant-0.9.7-py3-none-any.whl`
- `experimental_assistant-0.9.7.tar.gz`
- `experimental-assistant-v0.9.7-release-manifest.yml`
- `experimental-assistant-0.9.7-COMMIT-release.zip`
- `experimental-assistant-0.9.7-COMMIT-release.zip.sha256`
- `experimental-assistant-0.9.7-sbom.json`
- `experimental-assistant-0.9.7-vulnerability-report.json`
- `experimental-assistant-v0.9.7-distribution-checklist.json`
- `experimental-assistant-v0.9.7-distribution-checklist.md`
- optional detached signature sidecar and independently trusted public key

## Maintainer Order

Use a clean checkout at the intended release commit. Build and test wheel and sdist in isolated Python 3.11-3.13 environments, using the PATH-resolved `ea` executable rather than repository imports.

```bash
python3 scripts/check_install_env.py
python3 scripts/validate_skill_packages.py
python3 scripts/check_version_identity.py
python3 scripts/check_downloaded_skill_instructions.py
python3 scripts/public_release_smoke.py
python3 -m build
ea-release-supply-chain
ea-release-manifest
ea-release-package
ea-verify-release-package dist/experimental-assistant-0.9.7-COMMIT-release.zip
ea-release-checklist
```

For each clean wheel/sdist installation, run:

```bash
ea version --json
ea capabilities --json
ea doctor --json
ea --help
```

Repeat clean builds with the same commit and `SOURCE_DATE_EPOCH`; the wheel and release-tool-canonicalized sdist must be byte-identical. Canonicalization fixes archive order, uid/gid, owner names, tar mtimes, and gzip header time without changing payload bytes. The deterministic repository zip, manifest inputs, and checksum sidecars must also match. Record any format-level exception rather than silently accepting different bytes.

## Supply Chain Gate

`ea-release-supply-chain` generates a CycloneDX 1.5 SBOM and `pip-audit` report from the clean release environment. Scanner unavailability, scanner error, or any unallowlisted known vulnerability is release-blocking. The v0.9.7 allowlist is empty. See `docs/RELEASE_SECURITY_POLICY.md` and `requirements/release.txt`.

## What Each Check Proves

- `ea-public-release-smoke`: tests, both skill validations, CLI help, examples, portability scan, and sensitive-value scan.
- `ea-release-supply-chain`: installed-component inventory and known-vulnerability policy result for the clean environment.
- `ea-release-manifest`: exact release inputs, identity, git state, validation contract, scientific evidence refs, and supply-chain refs.
- `ea-release-package`: deterministic repository handoff zip and SHA-256 sidecar.
- `ea-verify-release-package`: sidecar, embedded manifest, file sizes, and manifest-listed SHA-256 values.
- `ea-verify-release-signature`: optional Ed25519 proof of key possession after package verification.
- `ea-release-checklist`: consolidated release status for git, package, supply chain, and artifacts.
- `ea install-check` / `ea doctor`: installed CLI and skill identity, not scientific validity.

## Blocking Failures

- dirty worktree or release tag not at the intended commit;
- failed full tests, skill validation, identity, downloaded-instruction, portability, privacy, or public-example gate;
- wheel or sdist cannot install and run from a clean supported interpreter;
- missing SBOM or vulnerability report;
- vulnerability scan status other than `pass`;
- non-reproducible artifact without an explicit public exception;
- missing archive/checksum/embedded manifest or any size/SHA-256 mismatch;
- unexpected developer paths, credentials, tokens, cookies, signed URLs, browser/session identifiers, raw project data, or private full text in release artifacts.

Independent novice/platform trial and external scientific-review evidence are promotion gates for v1.0. They may remain honestly marked pending for a controlled v0.9.7 release candidate, but must never be recorded as passed without real evidence.

## Optional Signing

```bash
ea-release-keygen --private-key /path/to/release-private.pem --public-key /path/to/release-public.pem
ea-sign-release-package dist/experimental-assistant-0.9.7-COMMIT-release.zip \
  --private-key /path/to/release-private.pem \
  --public-key /path/to/release-public.pem
ea-verify-release-signature dist/experimental-assistant-0.9.7-COMMIT-release.zip \
  --public-key /path/to/release-public.pem
```

A checksum detects corruption. A detached signature proves possession of a key. Publisher identity exists only when the verifier obtains the trusted public-key fingerprint through an independent stable channel.

## Recipient Record

Record the release tag and commit, filenames, SHA-256 values, embedded manifest identity, SBOM component count, vulnerability status, package verification status, optional signature/fingerprint result, verification date, and verifier role.

## Scope Limits

Release verification does not prove scientific correctness, completeness of a literature search, truth of references, lawful access to a user's sources, or authorship without an independently trusted signature. It must not bypass SSO, MFA, subscriptions, publisher controls, or modify protected project data.
