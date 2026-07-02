# EA v0.9 Release Candidate Verification

This guide is for a release recipient, maintainer, or future agent who needs to verify an EA v0.9 release-candidate repository package before using or redistributing it. All checks are local. None of these commands require Zotero, browser profiles, institution login, live web search, PDF download, private caches, or developer-machine key paths.

For first-time installation and Codex skill setup after verification, read `docs/PUBLIC_INSTALL_AND_CODEX_SKILL_SETUP.md`.

## 1. Expected Artifacts

A normal EA v0.9 release-candidate handoff may include:

- `ea-v0.9-rc-release-manifest.yml`
- `ea-v0-2-0.9.0rc1-COMMIT-release.zip`
- `ea-v0-2-0.9.0rc1-COMMIT-release.zip.sha256`
- optional `ea-v0-2-0.9.0rc1-COMMIT-release.zip.sig.yml`
- optional public key file supplied by the release author
- optional `ea-v0.2-distribution-checklist.json`
- optional `ea-v0.2-distribution-checklist.md`

The manifest and checksum prove local file integrity. The optional detached signature can add authorship or release-intent evidence only when the verifier trusts the supplied public key through an external channel.

## 2. Verification Order

Run checks in this order:

```bash
ea-public-release-smoke
ea-release-manifest
ea-release-package
ea-verify-release-package dist/ea-v0-2-0.9.0rc1-COMMIT-release.zip
ea-release-checklist
```

If a detached signature sidecar is present and the release author supplied a trusted public key:

```bash
ea-verify-release-signature dist/ea-v0-2-0.9.0rc1-COMMIT-release.zip \
  --public-key /path/to/release-public.pem
```

Use the script equivalents when console entry points are not installed:

```bash
python3 scripts/public_release_smoke.py
python3 scripts/build_release_manifest.py
python3 scripts/build_release_package.py
python3 scripts/verify_release_package.py dist/ea-v0-2-0.9.0rc1-COMMIT-release.zip
python3 scripts/build_distribution_checklist.py
python3 scripts/verify_release_signature.py dist/ea-v0-2-0.9.0rc1-COMMIT-release.zip \
  --public-key /path/to/release-public.pem
```

## 3. What Each Check Proves

`ea-public-release-smoke` proves the repository can run the current public gate: tests, skill validation, CLI help, release helper help, portability scan, and sensitive-value scan for accidental credential-like assignments or token literals in release-facing files.

`ea-release-manifest` records package metadata, git state, release input paths, checksums, smoke-gate requirements, public-boundary notes, and optional signing support.

`ea-release-package` builds a deterministic zip archive plus `.sha256` sidecar using the manifest release inputs.

`ea-verify-release-package` checks the `.sha256` sidecar, opens the zip, finds the embedded manifest, and verifies every manifest-listed file by size and SHA-256.

`ea-verify-release-signature` first verifies the package integrity gate, then verifies the detached Ed25519 signature sidecar with the user-supplied public key.

`ea-release-checklist` summarizes whether the default manifest, at least one release package, package verification, optional signature state, git cleanliness, and tag-at-HEAD state are ready for handoff.

## 4. Pass/Fail Expectations

Treat these as blocking failures before public handoff:

- dirty release worktree when generating final artifacts;
- missing default manifest;
- missing release zip;
- missing `.zip.sha256` sidecar;
- release package verification status other than `pass`;
- missing embedded manifest inside the zip;
- manifest-listed payload missing from the zip;
- size or SHA-256 mismatch for any manifest-listed file.

Treat these as warnings or follow-up work:

- no tag at `HEAD`;
- missing optional detached signature;
- signature sidecar present but not verified because no trusted public key was supplied.

Treat this as a trust failure when signing is required:

- detached signature verification status other than `pass`;
- public-key fingerprint mismatch;
- public key supplied through an untrusted channel.

## 5. Scope Limits

Release verification does not prove:

- scientific correctness of reports or material assignments;
- completeness of literature search;
- truth of cited references;
- security of the user's Python environment;
- authorship unless detached signature verification is performed with a trusted public key.

Release verification must not:

- rely on developer-machine Zotero, browser, institution, cache, key, or test paths;
- run live web search or PDF acquisition;
- store credentials;
- bypass SSO, MFA, paywalls, or access controls;
- modify raw project data.

## 6. Recommended Recipient Record

When a recipient verifies a release, save a short note with:

- release archive filename;
- archive SHA-256 from `.zip.sha256`;
- embedded manifest git commit and tags at HEAD;
- `ea-verify-release-package` status;
- `ea-verify-release-signature` status if used;
- `ea-release-checklist` status;
- verification date and verifier name or role.

This note can be stored outside the release package or alongside local deployment records.
