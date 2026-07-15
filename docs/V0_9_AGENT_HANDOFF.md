# Experimental Assistant v0.9.8 Agent Handoff

## Current State

- Release line: `v0.9.8`, package `experimental-assistant 0.9.8`
- Development branch: `codex/eav0.9.8`
- Primary skill: `skills/ea` / `$ea`
- Compatibility wrapper: `skills/ea-v0-2` / `$ea-v0-2` through v1.0.x
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
ea-verify-release-package dist/experimental-assistant-0.9.8-COMMIT-release.zip
ea-release-checklist
```

Also require clean wheel/sdist installs that run bundled-skill setup without network access, native CI, reproducibility evidence, compact skill-bundle checksum verification, public asset download verification, and the project-bundle checks in `docs/PROJECT_BUNDLE_VERIFICATION.md`.

## Evidence Honesty

Do not mark independent novice/platform trials or external scientific review as passed without an actual tester/reviewer record. v0.9.8 may be published as a controlled candidate with these items pending; v1.0 promotion may not.

## Boundaries

- Do not assume Zotero, browser sessions, institution access, private caches, signing keys, or developer paths.
- Do not mutate raw data, bypass access controls, commit memory without review, or turn screening evidence into a definitive claim.
- Do not duplicate full instructions in `skills/ea-v0-2`; it is only a compatibility router.
