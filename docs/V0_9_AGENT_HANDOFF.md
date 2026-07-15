# Experimental Assistant v0.9.9 Agent Handoff

## Current State

- Release line: `v0.9.9`, package `experimental-assistant 0.9.9`
- Development branch: post-v0.9.9 pre-v1 development
- Primary skill: `skills/ea` / `$ea`
- Compatibility skill: retired before v1.0; source, package, release bundle, and installed target must be absent
- Capability matrix: `docs/CAPABILITY_MATRIX.md`
- Acceptance and manual evidence: `docs/PUBLIC_ACCEPTANCE_MATRIX.md`, `docs/V0_9_MANUAL_TEST_CHECKLIST.md`

## Required Gates

```bash
python3 -m pytest -q
python3 scripts/validate_skill_packages.py
python3 scripts/check_version_identity.py
python3 scripts/check_downloaded_skill_instructions.py
python3 scripts/public_release_smoke.py
python3 -m build
ea-release-supply-chain
ea-release-skill-bundle
ea-release-manifest
ea-release-package
ea-verify-release-package dist/experimental-assistant-0.9.9-COMMIT-release.zip
ea-release-checklist
```

Also require clean wheel/sdist installs that run bundled-skill setup without network access, native CI, reproducibility evidence, compact skill-bundle checksum verification, public asset download verification, and the project-bundle checks in `docs/PROJECT_BUNDLE_VERIFICATION.md`.

## Evidence Honesty

Require automated tests, public benchmarks, deterministic mock integrations, simulated-agent journeys/reviews, and manual artifact inspection bound to the release candidate. Record their exact evidence types and limitations. Real-user trials, independent expert sign-off, and live-account Zotero tests are optional post-v1 improvement inputs, not v0.9.9 or v1.0 promotion gates.

## Boundaries

- Do not assume Zotero, browser sessions, institution access, private caches, signing keys, or developer paths.
- Do not mutate raw data, bypass access controls, commit memory without review, or turn screening evidence into a definitive claim.
- Do not restore or republish the retired Compatibility skill. Preserve old project identifiers only as read-only provenance where needed.
