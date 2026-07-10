# Experimental Assistant v0.9.7 Release Notes

v0.9.7 is the full engineering candidate for v1.0. It focuses on ordinary-user safety, cross-platform release quality, stable identity, literature evidence collection, and honest capability maturity while preserving existing scientific workflows.

## Version

- Package version: `0.9.7`
- Release label: `v0.9.7`
- Distribution: `experimental-assistant`
- CLI: `ea`
- Primary Codex skill: `$ea`
- Compatibility: `$ea-v0-2` thin wrapper through v1.0.x
- License: Apache-2.0

## Major Changes Since v0.9.6

- Unified the public identity around Experimental Assistant / `ea` / `$ea`; legacy names remain diagnostic compatibility metadata only.
- Added transactional setup, doctor, update, rollback, and uninstall flows with exact PATH identity checks.
- Added project-format migration planning, backups, journals, rollback, atomic writes, and stale-lock recovery.
- Added two-stage protected import with UTF-8 BOM/UTF-8/GB18030/CP936/CP1252 and delimiter detection.
- Added ordinary-user start/status/analyze/report routes, stable structured errors, explicit consult/record/execute/audit semantics, review-gated draft promotion, and privacy-safe local diagnostics.
- Added a machine-readable stable/beta/experimental capability contract and Python/platform CI matrix.
- Hardened literature queries, relevance checks, DOI deduplication, acquisition status normalization, Zotero companion handoff, redaction, and compact outputs.
- Added the beta literature data-plan/extract/review/validate/plot/export workflow with evidence anchors, typed electrical properties, resumable checkpoints, conflict retention, reviewed-only outputs, and privacy-scoped bundles.
- Added a deterministic Raman golden benchmark and external scientific-review evidence surface; Raman remains beta pending sign-off.
- Added Apache-2.0 governance, security, support, contribution, citation, SBOM, vulnerability, constraints, checksum, signature, and reproducibility policies.

## Relationship To v1.0

The v0.9.7 code is intended to become v1.0 without feature expansion if controlled trials find no blockers. Promotion still requires real independent novice trials on the supported platforms and independent scientific review of the beta evidence surfaces. Pending evidence is not treated as a pass.

## Maturity

- Stable: project lifecycle, protected import, implemented characterization methods, review/provenance, health/eval, trace, reports and bundle exports.
- Beta: Raman benchmarked analysis and literature evidence datasets.
- Experimental/companion: browser-assisted lawful acquisition and external Zotero coordination.

See `docs/CAPABILITY_MATRIX.md`, `docs/V0_9_KNOWN_LIMITATIONS.md`, and `docs/PUBLIC_ACCEPTANCE_MATRIX.md`.

## Migration

Run `ea migrate status` and `ea migrate plan` before changing an existing project. Use `$ea` for new Codex tasks. Existing `$ea-v0-2` invocation and historical records remain supported during v1.0.x and are not rewritten merely for naming.
