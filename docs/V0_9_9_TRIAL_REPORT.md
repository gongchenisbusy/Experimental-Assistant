# Experimental Assistant v0.9.9 Trial Report

Status: `RC0 evidence preparation`

## Evidence Policy

This release uses automated tests, public benchmarks, deterministic Mock fixtures, fresh simulated-agent journeys/reviews, and manual artifact inspection. It does not claim real-user trials, independent expert approval, or live Zotero/institution-account validation.

## Current Results

| Evidence | Type | Status |
|---|---|---|
| Universal literature schema and workflow regression | `automated_test` / `public_benchmark` | pass locally; final candidate rerun pending |
| Chinese dynamic report localization | `automated_test` | pass locally; final artifact review pending |
| Figure-local data and readable report-bound IDs | `automated_test` | pass locally; final artifact review pending |
| Guided first journey | `automated_test` | pass locally; fresh persona run pending |
| Five-target companion transaction | `mock_fixture` | pass |
| Raman and literature-data scientific review | `simulated_agent` | pending RC0 |
| Native platform and release-package gates | `automated_test` | pending final public commit |

Every simulated finding must be fixed or explicitly dispositioned before release. The final counts, commit, artifact hashes, CI runs, and downloaded-release verification will replace this RC0 status.
