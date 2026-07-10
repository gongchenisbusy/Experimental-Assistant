# Capability Maturity

Use this reference when describing support, selecting a workflow, or deciding whether an output may be presented as production-ready.

## Stable Core

- Installation lifecycle after release gates pass.
- Project creation, migration, and recovery.
- Protected raw import and duplicate detection.
- Review, provenance, references, health, evaluation, brief, and traceability.
- HTML reports and checksum-verified exports.

Raman is stable only after the release's independent benchmark and reviewer record pass.

## Beta

- Raman pending sign-off, PL, XRD, FTIR, UV-Vis, XPS, electrochemistry, thermal, and batch workflows.
- Public literature metadata search/ranking.
- Literature evidence datasets and review-gated plotting.

Treat beta outputs as candidates or screening results. State inputs, units, assumptions, evidence, uncertainty, and unsupported uses.

## Experimental Or Companion

- Zotero/browser/institution acquisition orchestration.
- Broad full-text acquisition and cache management.
- Advanced image interpretation.

Keep these integrations optional and independently diagnosable. Never bypass access controls or expose credentials, browser state, restricted full text, or private research data.

The repository-wide authoritative table is `docs/CAPABILITY_MATRIX.md`.
