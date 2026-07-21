# Experimental Assistant v1.1.0 Command Contract

The central command-effect registry classifies leaf commands as read-only or state-changing. Consult/audit allow read-only commands; record/execute remain required for writes and external actions.

## New and repaired v1.1 surfaces

| Workflow | Command shape | Effect |
|---|---|---|
| Method-aware preview | `ea import preview PROJECT FILE --characterization-type pl|raman` | read-only |
| Method inspection | `ea raman inspect FILE`, `ea pl inspect FILE` | read-only |
| Run records | `ea experiment add|update PROJECT ...`, `ea experiment runs PROJECT` | add/update write; runs read-only |
| Samples | `ea sample add PROJECT ...`, `ea sample select-best PROJECT SAMPLE_ID` | state-changing |
| Draft lifecycle | `ea draft confirm-promote PROJECT DRAFT_ID --user-response TEXT` | one confirmed write; ambiguous replies write nothing |
| Composite delivery | `ea composite-report PROJECT --result-id ... --review-id ...` | formal report/provenance write followed by HTML export |
| Draft HTML | `ea export report-html PROJECT --draft-id DRAFT_ID --preview` | preview artifact only; no formal report/index transition |
| Literature status | `ea literature acquisition-status PROJECT` | read-only |
| Zotero choice | `ea literature zotero-choice PROJECT --choice existing|skip|later` | idempotent local decision write |
| Institution state | `ea literature acquisition-session PROJECT --target-id ID ...` | privacy-safe local state write; no login automation |
| Local PDFs | `ea literature ingest-local-pdf PROJECT --pdf FILE --doi DOI` | validated, content-addressed local library/reference write |

## Invariants

- A command documented as read-only must not create, update, chmod, or delete project files.
- Ambiguous review/confirmation language must not create a deferred artifact as a side effect of the attempted promotion.
- Formal consumers must reject unrelated confirmed reviews when an expected type/reference/hash is supplied.
- Protected imports and exports either complete consistently or leave no new partial state.
- Literature `selected_top_n`, selected item count, request count, canonical run count, run target count, and target-manifest count must agree.
- A declared local PDF is not counted as downloaded unless the file exists and passes PDF plus metadata postflight.
