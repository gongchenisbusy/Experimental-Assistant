# Experimental Assistant v0.9.8 Release Notes

v0.9.8 is an integration and non-regression release on the v1.0-candidate line. It closes the version gap between the Python CLI and Codex skills, turns literature discovery/acquisition/cache reading into a compact recoverable pipeline, and makes briefs, report language, figures, and feedback evidence consistent while preserving v0.9.7 project and protocol readers.

## Version

- Package version: `0.9.8`
- Release label: `v0.9.8`
- Distribution: `experimental-assistant`
- CLI: `ea`
- Primary Codex skill: `$ea`
- Compatibility: `$ea-v0-2` thin wrapper through v1.0.x
- License: Apache-2.0

## Major Changes Since v0.9.7

- Wheel and sdist artifacts now carry the exact `$ea` and `$ea-v0-2` skill payloads. Release pages also carry a compact deterministic skill ZIP and SHA-256 sidecar. Setup prefers explicit or bundled sources and no longer requires an ordinary user to clone the repository.
- Skill replacement and CLI update flows record before/after identity and restoration state. Validator and lifecycle subprocess output is decoded safely under UTF-8 and common Windows GBK code pages; native CI covers deep paths and clean bundled-skill setup.
- Literature commands use a short stage router and compact default output, with full audit state retained on disk or exposed explicitly. Acquisition handoff v2 adds per-stage attempts, canonical targets, Zotero parent/attachment identity, PDF/cache hashes, blockers, transactions, and recovery while retaining the v1 reader.
- Crossref, OpenAlex, and arXiv run through a shared discovery adapter; Unpaywall resolution, bounded retrieval, PDF validation, SHA-256 content-addressed storage, SQLite FTS5/BM25 retrieval, auto-widening evidence reads, and a versioned non-regression benchmark are available without claiming exhaustive coverage.
- Project dashboard and brief now share one read-only state aggregator. An optional decision summary puts the current question, evidence gates, top action, project home, and latest reports on the first screen.
- Raman, PL, XRD, FTIR, UV-Vis, XPS, electrochemistry, and thermal reports use the configured Chinese or English catalog while preserving identical numeric values, units, evidence refs, confidence enums, citations, and warning codes.
- New figures keep a footer-free base and produce immutable report-bound renderings with exactly one final `FigID`/`Report` footer. Structured processed source-data roles, purposes, columns, and portable links are verified during export; historical figures are not silently rewritten.
- The optional `ea-feedback` compatibility manifest pins a tested companion commit with UTF-8 I/O, execution-event reconciliation, project `.venv` CLI discovery, and distinct prepared/verified draft states.

## Relationship To v1.0

The v0.9.8 code remains a controlled v1.0 candidate. Promotion still requires real independent novice trials on supported platforms and independent scientific review of beta evidence surfaces. Internal automation and the public OA trial do not substitute for that evidence.

## Maturity

- Stable: project lifecycle, protected import, implemented characterization methods, review/provenance, health/eval, trace, reports and bundle exports.
- Beta: Raman benchmarked analysis and literature evidence datasets.
- Experimental/companion: browser-assisted lawful acquisition and external Zotero coordination.

See `docs/CAPABILITY_MATRIX.md`, `docs/V0_9_KNOWN_LIMITATIONS.md`, and `docs/PUBLIC_ACCEPTANCE_MATRIX.md`.

## Migration

Run `ea migrate status` and `ea migrate plan` before changing an existing project. Use `$ea` for new Codex tasks. Existing `$ea-v0-2` invocation and historical records remain supported during v1.0.x and are not rewritten merely for naming.
