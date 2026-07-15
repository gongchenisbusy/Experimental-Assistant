# EA v0.9.8 issue disposition

This document is the human-readable companion to `docs/V0_9_8_ISSUE_DISPOSITION.yml`. It maps public feedback to release evidence without claiming that external companion or independent-user work is complete.

## Compatibility contract

- v0.9.7 projects must open successfully in read-only workflows.
- Legacy `source_data_refs` remains readable while v0.9.8 adds structured `source_data`.
- Acquisition protocol v1 remains readable and is normalized to a v2 in-memory view without modifying the source file.
- The published v0.9.8 artifacts included the compatibility router. A post-release decision removes that visible skill before v1.0 while preserving historical identifiers read-only.
- Historical provenance and version IDs are never rewritten automatically.

## Disposition summary

| Issue | v0.9.8 disposition | Blocking evidence | Residual work |
|---|---|---|---|
| #2 | Keep open, partially addressed | install transaction/doctor and companion compatibility tests | GUI installers, licenses, OS permissions, and account login remain user-authorized |
| #7 | Keep open, partially addressed | acquisition v1/v2, partial/recovery, OA cache, reconciliation tests | real five-target Zotero parent+PDF-child transaction and publisher variants |
| #8 | Close only after release artifacts pass | bundled wheel skills, compact checksum bundle, complete setup/update journal | none within the issue’s CLI+skill scope |
| #9 | Keep open, partially addressed | Windows/GBK fixtures, bounded OA resolver, structured ea-feedback events and verified fallback | independent Windows five-paper Zotero trial and user-controlled browser login evidence |
| #10 | Close only after release artifacts pass | shared project-state aggregator, decision-oriented brief, historical finding reconciliation, `.venv` discovery | none within the issue’s acceptance criteria |
| #11 | Keep open, partially addressed | compact output, staged router, adapter/Unpaywall/CAS/FTS benchmark, zh/en parity, source-data links, single footer | optional source adapters and independent novice/scientific review remain deferred |

## Frozen red fixtures

The v0.9.8 suite fixes regressions for Windows-style deep paths, GBK validator output, skill/CLI mismatch, five-item compact search/resume, legacy double/pending footers, zh/en semantic parity, decision evidence gates, and partial acquisition batches. Baseline v0.9.7 remains reproducible from commit `99741d8` with 360 passing tests.

Issue state is changed only after the public release commit, CI, downloadable artifacts, and clean-install verification agree with this table.
