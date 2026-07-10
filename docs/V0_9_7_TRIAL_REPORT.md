# Experimental Assistant v0.9.7 Trial Report

## Candidate

- Product/distribution: `Experimental Assistant` / `experimental-assistant`
- Version: `0.9.7`
- Primary/compatibility skills: `$ea` / `$ea-v0-2`
- Local validation: macOS arm64; CPython 3.11.15 minimum dependencies, Python 3.12 development environment, and CPython 3.14.4 observation
- Public native CI: pass at candidate commit `27747bb` ([run 29102557775](https://github.com/gongchenisbusy/Experimental-Assistant/actions/runs/29102557775))

## Automated Local Evidence

| Gate | Result |
|---|---|
| Full pytest | pass, 360 tests in the local development, minimum-dependency, and Python 3.14 observation environments |
| Version/distribution/skill identity | pass |
| Downloaded instruction synchronization | pass |
| Primary skill budget/validation | pass, below 10 KB |
| Compatibility wrapper budget/validation | pass, below 2 KB |
| Serious Ruff lint classes | pass |
| Selected v0.9.7 format surface | pass |
| Local Markdown links | pass |
| Raman machine benchmark | pass; external review pending |
| Ten-paper literature dataset pilot | pass in focused tests; external domain review pending |
| Windows/Ubuntu/macOS Python 3.11-3.13 | pass in public native CI |
| Wheel/sdist clean PATH smoke | pass on Windows, Ubuntu, and macOS in public native CI |
| Repeated-build reproducibility | pass in public native CI |
| CycloneDX SBOM and pip-audit | pass in public native CI; zero known vulnerabilities in the tested release environment |

Final counts and artifact hashes are updated from the release commit after clean builds.

## Required Public/External Evidence

| Evidence | Current status | Promotion effect |
|---|---|---|
| Windows/Ubuntu/macOS Python 3.11-3.13 CI | pass; [run 29102557775](https://github.com/gongchenisbusy/Experimental-Assistant/actions/runs/29102557775) | supported-platform automated gate passed |
| Python 3.14 observation | pass in public CI and local CPython 3.14.4 validation | non-blocking observation passed; 3.14 is not yet in the supported contract |
| Clean wheel and sdist PATH smoke | pass on all three operating systems in public CI; regenerate from the final tag | final tagged artifacts must match the validated source |
| Repeated-build reproducibility | pass in public CI; regenerate from the final tag | final tagged artifact hashes must match the reproducibility report |
| SBOM and vulnerability report | pass in public CI with zero findings; regenerate from the final tag | final tagged evidence remains release-blocking if its result differs |
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
