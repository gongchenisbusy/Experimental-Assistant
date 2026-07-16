# Experimental Assistant v1.0.0 Candidate Trial Report

Status: `candidate evidence and public download replay passed`.

This report binds v1.0 product and scientific trial evidence to tested candidate commit `5736bcdadeb28f93055312f4f92f1fcf200c0018`. Public Release publication and downloaded-asset replay passed separately and are recorded in [V1_0_PUBLICATION_VERIFICATION.yml](V1_0_PUBLICATION_VERIFICATION.yml).

## Candidate identity

- Tested candidate commit: `5736bcdadeb28f93055312f4f92f1fcf200c0018`
- Package: `experimental-assistant 1.0.0`
- Release label: `v1.0.0`
- Skill: `$ea`
- Evidence date: `2026-07-17`
- Full regression: `458 passed`

## Required tracks

| Track | Evidence type | Status | Candidate-bound evidence |
|---|---|---|---|
| Full regression and #19 audit routing | automated | pass | `pytest` 458 passed; `ea.release_smoke` passed; explicit six-test audit validator step passed |
| Raman golden benchmark and tolerances | public benchmark | pass | `scripts/run_scientific_benchmarks.py`; 11 checks passed; promotion status `eligible_for_release` |
| Universal literature schema/extract/review/validate/export | public benchmark + automated | pass | preserved `benchmarks/literature-v0.9.9.yml`; current literature benchmark/extraction/workflow suites passed |
| Eight-method Chinese/English report semantics | automated + artifact | pass | report localization and method workflow suites passed |
| Four packaged public examples | automated | pass | Raman, FTIR, UV-Vis, and XPS health/evaluation replay passed in public release smoke |
| Guided first journey and recovery | simulated persona + automated | pass | onboarding, journey, install recovery, and user-surface suites passed |
| Windows/GBK/long-path, offline/no-Zotero, custom schema | native CI + simulated persona | pass | Windows/Ubuntu/macOS Python 3.11–3.13 CI and minimum-dependency jobs passed |
| Raman and literature scientific boundaries | simulated scientific review | pass | declared simulated reviews plus current benchmark boundary checks passed; not independent expert review |
| Five-target acquisition transaction and blocker states | deterministic Mock | pass | current Mock companion and release-candidate contract suites passed; not a live service transaction |
| Markdown/HTML/PNG/bundle/manifest/download instructions | manual artifact inspection | pass | clean candidate artifacts, 500-file release package, Skill bundle, checksums, and distribution checklist inspected |
| v0.9.9→v1.0.0 update, rollback, and uninstall | isolated lifecycle | pass | public v0.9.9 assets upgraded to candidate wheel/Skill, `doctor` passed, v0.9.9 Skill backup restored, package rolled back, and recoverable uninstall completed |

The evidence types above retain their stated limits: simulated personas are not real users, deterministic Mock tests are not live-service validation, and simulated scientific review is not independent expert approval. Exact release gates are recorded in [V1_0_RELEASE_DOSSIER.yml](V1_0_RELEASE_DOSSIER.yml).
