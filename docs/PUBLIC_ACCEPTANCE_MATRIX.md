# Experimental Assistant v0.9.8 Public Acceptance Matrix

This matrix is the release-candidate contract for ordinary users. A row is passed only by current evidence; automated tests do not substitute for novice usability or independent scientific review.

| Area | Required evidence | v0.9.8 gate |
|---|---|---|
| Identity | `experimental-assistant 0.9.8`, CLI `ea`, primary `$ea`, thin `$ea-v0-2` wrapper | Blocking |
| Platforms | Native Windows, Ubuntu, macOS on Python 3.11-3.13; 3.14 observation only | Blocking |
| Install lifecycle | clean wheel and sdist install; setup, doctor, update plan, rollback plan, uninstall plan | Blocking |
| Project safety | migration plan/apply/rollback, atomic writes, interruption recovery, protected raw import | Blocking |
| User surface | start/status/import/analyze/report/export, stable errors, mode semantics, local diagnostics | Blocking |
| Scientific workflows | full tests, public examples, health/eval, review and provenance boundaries | Blocking |
| Literature | confirmed query clauses, relevance gates, DOI idempotency, lawful acquisition ledger | Blocking |
| Evidence dataset beta | ten-paper pilot, anchors, review states, reviewed-only plot/export, OCR failure state | Blocking for beta claim |
| Raman beta | deterministic golden/tolerance benchmark | Blocking for beta claim |
| Supply chain | clean-build SBOM, vulnerability report `pass`, checksums, reproducibility record | Blocking |
| Novice UX | independent first-install/first-project trials on Windows, Ubuntu, macOS | Required for v1.0 promotion |
| Scientific review | independent Raman and evidence-dataset review | Required for v1.0 promotion |

## Automated Commands

```bash
python3 -m pip install -e ".[dev,release]"
python3 -m pytest -q
python3 scripts/validate_skill_packages.py
python3 scripts/check_version_identity.py
python3 scripts/check_downloaded_skill_instructions.py
python3 scripts/public_release_smoke.py
ea-public-release-smoke
python3 -m build
ea-release-supply-chain
ea-release-manifest
ea-release-package
ea-verify-release-package dist/experimental-assistant-0.9.8-COMMIT-release.zip
ea-release-checklist
```

## Public Examples

| Scenario | Fixture | Pass condition |
|---|---|---|
| Raman orientation | `examples/public-raman-project` | health/eval pass; no unsupported scientific claim |
| FTIR evidence/report handoff | `examples/public-ftir-assignment-project` | registered evidence, review, trace, HTML and verified bundle |
| UV-Vis screening | `examples/public-uv-vis-project` | Tauc/derivative/correction remain screening evidence |
| XPS candidate boundary | `examples/public-xps-be-project` | binding-energy candidates remain advisory and reviewed |
| Conductivity dataset beta | synthetic ten-paper test fixture | source anchors, quantity separation, conflicts retained, reviewed-only plot/export |

## Degraded Environments

- Without Zotero or network access, core projects, examples, health/eval, trace, export, diagnostics, and release-package verification continue locally.
- Subscription/login blockers are recorded as user-managed next actions. EA does not bypass SSO, MFA, paywalls, or publisher controls.
- Scanned PDFs without extractable text produce an explicit OCR-required state; no value is invented.

## Blocking Failures

- Any required automated, native-CI, clean-install, migration/interruption, privacy, package, SBOM, vulnerability, checksum, or reproducibility failure.
- Any hidden developer path, credential, browser/session value, private full text, or raw project data in release artifacts.
- Any conversion of advisory/screening evidence into definitive material, phase, composition, band-gap, chemical-state, performance, or mechanism claims.
- Any claim that an external novice or scientific review passed without real recorded evidence.

External trials may remain `pending` for a controlled v0.9.8 candidate. They must pass before the same commit is promoted to v1.0.
