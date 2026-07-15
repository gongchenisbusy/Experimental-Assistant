# Experimental Assistant v0.9.9 Public Acceptance Matrix

This matrix is the maintainer-facing release-candidate contract. A row passes only with evidence bound to the current candidate. Simulated-agent and mock-fixture evidence are labeled as such and are never described as real-user or independent-expert validation.

| Area | Required evidence | v0.9.9 gate |
|---|---|---|
| Identity | `experimental-assistant`, CLI `ea`, single `$ea` skill, retired Compatibility skill absent | Blocking |
| Platforms | Native Windows, Ubuntu, macOS on Python 3.11-3.13; 3.14 observation only | Blocking |
| Install lifecycle | clean wheel and sdist install; setup, doctor, update plan, rollback plan, uninstall plan | Blocking |
| Project safety | migration plan/apply/rollback, atomic writes, interruption recovery, protected raw import | Blocking |
| User surface | guided first journey from project creation through verified bundle, stable errors, mode semantics, local diagnostics | Blocking |
| Scientific workflows | full tests, public examples, health/eval, review and provenance boundaries | Blocking |
| Literature | confirmed query clauses, relevance gates, DOI idempotency, lawful acquisition ledger | Blocking |
| Universal literature data | arbitrary validated schemas, typed values, anchors, review states, schema migration, reviewed-only downstream use | Blocking |
| Raman | deterministic golden/tolerance benchmark plus simulated scientific review | Blocking |
| Supply chain | clean-build SBOM, vulnerability report `pass`, checksums, reproducibility record | Blocking |
| Simulated UX | fresh-agent novice journeys on deterministic public fixtures, with findings fixed or dispositioned | Blocking |
| Simulated scientific review | method and literature-data reviews against public artifacts, with findings fixed or dispositioned | Blocking |
| Mock integration | five-target Zotero/attachment protocol fixture covering success, partial failure, resume, dedup, cache, reconciliation, and blockers | Blocking |

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
ea-verify-release-package dist/experimental-assistant-0.9.9-COMMIT-release.zip
ea-release-checklist
```

## Public Examples

| Scenario | Fixture | Pass condition |
|---|---|---|
| Raman orientation | `examples/public-raman-project` | health/eval pass; no unsupported scientific claim |
| FTIR evidence/report handoff | `examples/public-ftir-assignment-project` | registered evidence, review, trace, HTML and verified bundle |
| UV-Vis screening | `examples/public-uv-vis-project` | Tauc/derivative/correction remain screening evidence |
| XPS candidate boundary | `examples/public-xps-be-project` | binding-energy candidates remain advisory and reviewed |
| Universal literature data | public mixed-domain fixtures | arbitrary schemas, typed fields, source anchors, conflicts retained, reviewed-only downstream use |

## Degraded Environments

- Without Zotero or network access, core projects, examples, health/eval, trace, export, diagnostics, and release-package verification continue locally.
- Subscription/login blockers are recorded as user-managed next actions. EA does not bypass SSO, MFA, paywalls, or publisher controls.
- Scanned PDFs without extractable text produce an explicit OCR-required state; no value is invented.

## Blocking Failures

- Any required automated, native-CI, clean-install, migration/interruption, privacy, package, SBOM, vulnerability, checksum, or reproducibility failure.
- Any hidden developer path, credential, browser/session value, private full text, or raw project data in release artifacts.
- Any conversion of advisory/screening evidence into definitive material, phase, composition, band-gap, chemical-state, performance, or mechanism claims.
- Any evidence record whose type, candidate commit, fixture hash, or limits are absent or misleading.

Real-user trials, external expert sign-off, and a live Zotero account are not v0.9.9 or v1.0 promotion gates. They may be collected after v1.0 as product-improvement evidence.
