# Experimental Assistant v0.9.7 Trial Report

## Candidate

- Product/distribution: `Experimental Assistant` / `experimental-assistant`
- Version: `0.9.7`
- Primary/compatibility skills: `$ea` / `$ea-v0-2`
- Local development platform: macOS arm64, Python 3.12
- Public native CI: pending until the candidate commit is pushed

## Automated Local Evidence

| Gate | Result |
|---|---|
| Full pytest | pass, 355 tests |
| Version/distribution/skill identity | pass |
| Downloaded instruction synchronization | pass |
| Primary skill budget/validation | pass, below 10 KB |
| Compatibility wrapper budget/validation | pass, below 2 KB |
| Serious Ruff lint classes | pass |
| Selected v0.9.7 format surface | pass |
| Local Markdown links | pass |
| Raman machine benchmark | pass; external review pending |
| Ten-paper literature dataset pilot | pass in focused tests; external domain review pending |

Final counts and artifact hashes are updated from the release commit after clean builds.

## Required Public/External Evidence

| Evidence | Current status | Promotion effect |
|---|---|---|
| Windows/Ubuntu/macOS Python 3.11-3.13 CI | pending public run | blocks supported-platform release claim until pass |
| Python 3.14 observation | pending public run | non-blocking observation |
| Clean wheel and sdist PATH smoke | pending final artifacts | blocks v0.9.7 release |
| Repeated-build reproducibility | pending final artifacts | blocks v0.9.7 release |
| SBOM and vulnerability report | pending clean release environment | blocks v0.9.7 release |
| At least five independent novice trials | pending | blocks v1.0 promotion, not an honestly labeled controlled v0.9.7 candidate |
| At least two independent scientific reviews | pending | blocks stable-method promotion and v1.0 promotion |

## Controlled Trial Protocol

1. Install the wheel or sdist in a clean non-development path.
2. Run `ea setup`, restart Codex, and invoke `$ea` without reading maintainer docs.
3. Create a first project, preview/import a Chinese-encoded fixture, inspect one method, record reviews, generate a report, and verify an export bundle.
4. Run no-Zotero degraded literature status and a mixed five-paper acquisition handoff.
5. Run the ten-paper property extraction pilot and confirm only reviewed comparable values enter a plot.
6. Record confusion, failed commands, output size, artifacts, sensitive-data findings, and whether the tester completed the task without developer intervention.

## Honest Release Boundary

This document does not claim external trials have occurred. v0.9.7 can be released only after its automated/public artifact gates pass and must remain labeled a full v1.0 release candidate. Promotion to v1.0 requires the pending independent novice and scientific evidence with no unresolved blocker.
