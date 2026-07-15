# Experimental Assistant v0.9.9 Acceptance Mapping

This file maps the approved v0.9.9 plan to executable or inspectable evidence. A checked item requires current-target evidence; a passing v0.9.8 test is not sufficient by itself.

| Contract | Red evidence on v0.9.8 | Target evidence |
|---|---|---|
| One public skill identity | v0.9.8 packaged `$ea-v0-2` | single-skill package, stale-entry backup/rollback tests, clean install smoke |
| User-defined literature fields | unknown `property_kind` raises an allowlist error | schema validation plus custom-field plan → extract → review → validate → export test |
| Six electrical presets | property-specific constants implement the workflow | golden compatibility tests through the schema engine |
| Zero-write schema preview | no schema input or semantic hash exists | preview/persisted semantic-hash parity and changed-hash stale tests |
| Typed evidence records | only one numeric electrical shape is supported | number, range, uncertainty, text, enum, boolean, date/time, list, and nested validation tests |
| Dynamic report localization | unrecognized English interpretation is emitted unchanged | eight-method locale catalog/lint/snapshot and semantic-equivalence tests |
| Figure-local source data | canonical Markdown appends `## 图下数据` | single/multi/no-figure Markdown and HTML component tests; no standalone section |
| Readable report-bound IDs | fixed `ImageFont.load_default()` footer | display-scale font metadata, bounding-box, contrast, long-ID and deterministic-render tests |
| Guided first journey | commands exist but are not one resumable journey contract | install/start/import/review/analyze/report/export persona and automated journey evidence |
| Compatibility | legacy readers exist | v0.9.7/v0.9.8 project, source-data, acquisition v1/v2, and historical-render tests |
| Simulated release evidence | no v0.9.9 evidence ledger | RC-bound persona, reviewer, mock companion, issue ledger, and RC1 retest artifacts |
| Release identity | current package and artifacts identify v0.9.8 | commit/tag/Release/manifest/wheel/sdist/skill asset/download identity parity |

## Release blockers

1. Every approved Must has code, documentation, red/green evidence, and applicable final-artifact review.
2. The full test suite and release-package checks pass from clean wheel and sdist installations.
3. Native Windows, Ubuntu, and macOS CI passes for Python 3.11–3.13.
4. The simulated issue ledger has no open P0/P1 findings.
5. The readiness dossier records evidence types honestly and sets `v1_promotion_ready: true` only after every defined gate passes.

