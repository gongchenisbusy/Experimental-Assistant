# Experimental Assistant v0.9.9 Trial Report

Status: `RC3 candidate evidence complete; public release gates pending`

## Evidence Policy

This release uses automated tests, public benchmarks, deterministic Mock fixtures, fresh simulated-agent journeys/reviews, and manual artifact inspection. It does not claim real-user trials, independent expert approval, or live Zotero/institution-account validation.

## Current Results

| Evidence | Type | Status |
|---|---|---|
| Universal literature schema and workflow regression | `automated_test` / `public_benchmark` / `simulated_agent` | pass on RC3; exact ten-type values, review context, DOI identity, and CLI gates checked |
| Chinese dynamic report localization | `automated_test` / `manual_artifact_review` | pass on RC3 |
| Figure-local data and readable report-bound IDs | `automated_test` / `manual_artifact_review` | pass on RC3; one figure-local block, no standalone section, readable unclipped footer |
| Guided first journey | `automated_test` / `simulated_agent` | pass on RC3; 6 focused checks |
| Five-target companion transaction | `mock_fixture` | pass |
| Raman scientific review | `public_benchmark` / `simulated_agent` | pass on RC3; 14 focused tests and 11/11 benchmark checks |
| Full regression | `automated_test` | 446 passed on RC3 |
| Native platform and release-package gates | `automated_test` | pending final public commit and published assets |

Candidate evidence is bound to functional commit `8b6d2c199821f8985c521254065c0b7a89a45ba9`. The final public commit, CI runs, supply-chain checks, release-asset hashes, and downloaded-release verification remain release blockers. All simulated findings are recorded as simulated evidence and are not real-user trials or independent expert approval.
