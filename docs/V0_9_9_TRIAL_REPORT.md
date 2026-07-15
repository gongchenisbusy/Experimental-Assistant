# Experimental Assistant v0.9.9 Trial Report

Status: `final release candidate verified; publication pending`

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
| Full regression | `automated_test` | 447 passed on final release candidate |
| Native platform CI | `automated_test` | pass on public main commit `37856e3`; Windows, Ubuntu, macOS / Python 3.11–3.13 plus minimum dependencies, packaging, quality, release engineering, and Python 3.14 observation |
| Clean wheel/sdist and reproducibility | `automated_test` | pass; PATH-resolved installs and byte-identical repeated builds |
| Supply chain and release package | `automated_test` | pass; 59-component CycloneDX SBOM, 0 unallowlisted vulnerabilities, 493-file repository package verification, and distribution checklist |

Simulated scientific and persona evidence is bound to functional commit `8b6d2c199821f8985c521254065c0b7a89a45ba9`; final release engineering and public native CI are bound to main commit `37856e36e4e20d4cfc7583b9d1a53f34f373eb6f` and [GitHub Actions run 29450662740](https://github.com/gongchenisbusy/Experimental-Assistant/actions/runs/29450662740). Public release publication and downloaded-asset replay remain delivery steps. All simulated findings remain labeled as simulated evidence and are not real-user trials or independent expert approval.
