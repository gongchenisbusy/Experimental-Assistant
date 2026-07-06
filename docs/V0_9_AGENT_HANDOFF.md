# Experimental Assistant v0.9.6 Agent Handoff

This file is the handoff anchor for future agents continuing from Experimental Assistant v0.9.6.

## Current State

- Release label: `v0.9.6`
- Package version: `0.9.6`
- Working branch: `codex/eav0.9`
- Skill folder: `skills/ea-v0-2`
- Public install guide: `docs/PUBLIC_INSTALL_AND_CODEX_SKILL_SETUP.md`
- Acceptance matrix: `docs/PUBLIC_ACCEPTANCE_MATRIX.md`
- Release notes: `docs/V0_9_RELEASE_NOTES.md`
- Known limitations: `docs/V0_9_KNOWN_LIMITATIONS.md`
- Manual checklist: `docs/V0_9_MANUAL_TEST_CHECKLIST.md`

## Read First

1. `README.md`
2. `docs/PUBLIC_INSTALL_AND_CODEX_SKILL_SETUP.md`
3. `docs/PUBLIC_ACCEPTANCE_MATRIX.md`
4. `docs/V0_9_RELEASE_NOTES.md`
5. `docs/V0_9_KNOWN_LIMITATIONS.md`
6. `docs/PUBLIC_ONBOARDING.md`
7. `skills/ea-v0-2/SKILL.md`

## Required Gates Before Promotion

```bash
python3 -m pytest -q
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" skills/ea-v0-2
python3 scripts/public_release_smoke.py
python3 scripts/build_release_manifest.py
python3 scripts/build_release_package.py
python3 scripts/verify_release_package.py dist/ea-v0-2-0.9.6-COMMIT-release.zip
python3 scripts/build_distribution_checklist.py
```

Also run at least one project handoff bundle check:

```bash
ea export report-bundle examples/public-ftir-assignment-project \
  --report-id rpt-public-ftir-assignment-example-20260604-001 \
  --include-trace \
  --zip
ea export verify-bundle examples/public-ftir-assignment-project/exports/report-bundles/rpt-public-ftir-assignment-example-20260604-001
ea export verify-archive examples/public-ftir-assignment-project/exports/report-bundles/rpt-public-ftir-assignment-example-20260604-001.zip
```

## Do Not Assume

- Do not assume Zotero, browser sessions, institution access, private caches, signing keys, or local test fixtures.
- Do not treat source-backed suggestions or screening calculations as final claims.
- Do not mutate raw data or commit memory without the review-gated workflow.
- Do not publish v1.0 until the acceptance matrix and manual checklist pass or all failures are documented as accepted limitations.
