# EA v0.9 Public Acceptance Matrix

This matrix defines the public-safe acceptance surface for the EA v0.9 release candidate. It is a gate for maintainers and future agents; it does not require Zotero, browser sessions, institution login, private caches, signing keys, or network access unless a row explicitly says the user has chosen that workflow.

## Required Automated Gates

Run these from a fresh checkout or extracted release package after installing developer dependencies:

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest -q
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" skills/ea-v0-2
python3 scripts/public_release_smoke.py
python3 scripts/build_release_manifest.py
python3 scripts/build_release_package.py
python3 scripts/verify_release_package.py dist/ea-v0-2-0.9.0rc1-COMMIT-release.zip
python3 scripts/build_distribution_checklist.py
```

`scripts/public_release_smoke.py` includes pytest, skill validation, CLI help checks, public example `healthcheck` and `eval --no-write`, release helper help checks, portability scan, and sensitive-value scan.

## Public Example Matrix

| Scenario | Fixture | Required commands | Pass condition |
|---|---|---|---|
| Raman first example | `examples/public-raman-project` | `ea healthcheck ...`; `ea eval project ... --no-write`; optional `ea export report-html ...` | 0 health/eval errors; no writes during eval; readable report export succeeds when requested |
| Literature plus source-backed report | `examples/public-ftir-assignment-project` | `ea healthcheck ...`; `ea eval project ... --no-write`; `ea export report-html ...`; `ea export report-bundle ... --include-trace --zip`; `ea export verify-bundle ...`; `ea export verify-archive ...` | registered references, source-backed suggestions, review records, memory candidates, figures, HTML export, and checksummed bundle are present and verifiable |
| Source-backed XPS boundary | `examples/public-xps-be-project` | `ea healthcheck ...`; `ea eval project ... --no-write` | source-backed binding-energy candidates are advisory and reviewed; no chemical-state proof is claimed |
| UV-Vis screening boundary | `examples/public-uv-vis-project` | `ea healthcheck ...`; `ea eval project ... --no-write` | Tauc, derivative, correction, and feature records remain screening evidence, not final band-gap or ranking claims |

## Environment Matrix

| Environment | Expected behavior | Evidence |
|---|---|---|
| Fresh clone or release package | Ordinary install can run `ea --help`; developer install can run tests and smoke | install guide plus smoke result |
| No Zotero installed | Literature readiness reports degraded local mode and next commands without failing core project work | `ea literature zotero-readiness /path/to/project --no-write` |
| Zotero available but no institution access | EA can prepare a handoff/settings request and record missing access as user-managed action | `ea literature zotero-bridge`; `ea literature zotero-readiness` |
| Open-access acquisition chosen by user | EA can import a local acquisition manifest and reconcile local cache/reference state | `ea literature import-acquisition`; `ea literature reconcile-acquisition`; `ea literature acceptance-checklist` |
| Institution login required | EA must pause for user-managed login and record guidance only | `ea literature institution-access-guide` |
| No network or restricted network | Public examples, healthcheck, eval, HTML export, report bundles, release package verification, and no-Zotero literature paths remain local | smoke with no live acquisition commands |
| Different local path | Commands must use user-supplied paths and release scans must reject developer-machine defaults | portability scan passes |
| Project handoff | Report or batch bundle can be exported with trace and verified by checksum | `ea export report-bundle ... --include-trace --zip`; `ea export verify-bundle`; `ea export verify-archive` |

## Blocking Failures

- Any full-test, skill-validation, smoke, public-example healthcheck/eval, release-package verification, or handoff-bundle verification failure.
- Any release-facing developer-machine default, private account path, credential-like value, or token-like literal.
- Any public example that requires live web, Zotero, browser state, institution access, or private cache to pass local checks.
- Any report or memory surface that converts screening or advisory evidence into a definitive material, phase, composition, band-gap, chemical-state, performance, or mechanism claim.
