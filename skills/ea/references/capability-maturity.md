# Capability Maturity

Use this maintainer-only reference for release governance or when the user explicitly asks for the internal capability contract. Do not reproduce these maturity labels in ordinary user answers or routine command output; state concrete supported inputs, review requirements, limits, and next actions instead.

## Stable Core

- Installation lifecycle after release gates pass.
- Project creation, migration, and recovery.
- Protected raw import and duplicate detection.
- Review, provenance, references, health, evaluation, brief, and traceability.
- HTML reports and checksum-verified exports.

Raman is stable only after its public benchmark, numeric tolerances, simulated release-candidate scientific review, and artifact inspection pass with no unresolved blocking finding.

## Beta

- Raman pending release-candidate review, PL, XRD, FTIR, UV-Vis, XPS, electrochemistry, thermal, and batch workflows.
- Public literature metadata search/ranking.
- Literature evidence datasets and review-gated plotting.

Treat these outputs as candidates or screening results. State inputs, units, assumptions, evidence, uncertainty, and unsupported uses.

## Experimental Or Companion

- Zotero/browser/institution acquisition orchestration.
- Broad full-text acquisition and cache management.
- Advanced image interpretation.

Keep these integrations optional and independently diagnosable. Never bypass access controls or expose credentials, browser state, restricted full text, or private research data.

The repository-wide authoritative table is `docs/CAPABILITY_MATRIX.md`.
