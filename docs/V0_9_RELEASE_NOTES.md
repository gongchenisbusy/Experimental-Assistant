# EA v0.9 Release Notes

EA v0.9 is a release candidate from the `ea-v0-2` compatibility line. It focuses on stability, public installability, agent-native handoff, report delivery, Zotero-Codex readiness, public examples, and release packaging rather than adding a new characterization method.

## Version

- Package version: `0.9.0rc1`
- Release label: `v0.9-rc1`
- Skill folder: `skills/ea-v0-2`
- Compatibility note: the skill name and package name keep `ea-v0-2` for continuity; release artifacts and docs identify the v0.9 release-candidate state.

## Major Changes Since v0.2 Baseline

- Stabilized known v0.2 issues around project dates, review ID collisions, bilingual confirmations, deferred memory-candidate healthcheck legality, figure report footers, Raman raw/processed plotting, inherited warnings, user-facing CLI boundary errors, and memory review output.
- Added a public install and Codex skill setup guide for fresh clones and release packages.
- Added `ea brief project` for concise agent-facing project summaries and next actions.
- Added `ea export report-html` for readable HTML reports with embedded figures, canonical Markdown traceability, references, and provenance audit metadata.
- Added `ea literature zotero-readiness` for local Zotero-Codex handoff/status readiness without operating Zotero, browsers, credentials, or downloads.
- Promoted public examples to release smoke gates: Raman, FTIR source-backed assignment, UV-Vis screening, and XPS binding-energy candidate examples must pass healthcheck and eval.
- Updated release manifest, package, verification, optional signing, and distribution checklist surfaces for v0.9 RC handoff.

## Relationship To v1.0

v0.9 is not the final public v1.0. It is the candidate that should be handed to human testers and future agents to find remaining product, documentation, and scientific-boundary issues before v1.0. v1.0 should only be cut after the acceptance matrix, manual checklist, and real user walkthroughs have no blocking findings or have clear documented limitations.

## Stable Entry Points

- `ea init-project`, `ea config doctor`, `ea healthcheck`, `ea eval project`, `ea brief project`
- Raman/PL/XRD/FTIR/UV-Vis/XPS/electrochemistry/thermal/image-data local workflows when user review gates are satisfied
- `ea export report-html`, `ea export report-bundle`, `ea export batch-bundle`, `ea export verify-bundle`, `ea export verify-archive`
- `ea trace view`, `ea trace lookup`
- release commands: `ea-public-release-smoke`, `ea-release-manifest`, `ea-release-package`, `ea-verify-release-package`, `ea-release-checklist`

## Screening Or Experimental Entry Points

- Material assignment libraries, source packets, suggestion records, and review packages are advisory until reviewed and cited.
- UV-Vis Tauc, derivative, correction, and replicate comparison helpers are screening workflows unless a reviewed method model and references support stronger claims.
- XPS background, component fitting, spin-orbit constraints, Tougaard starting points, and binding-energy candidates remain reviewed screening aids unless the project has enough source-backed evidence.
- Electrochemistry and thermal derived metrics summarize reviewed windows and context; they do not rank performance or prove mechanisms by themselves.
- Zotero-Codex integration is a local handoff/readiness contract; the companion workflow remains user-managed and optional.

## Migration Notes

- Existing legacy EA project folders can continue to be inspected with healthcheck/eval.
- For public handoff, regenerate any report bundles or release packages with the v0.9 RC code so manifests, checksums, and HTML exports use current metadata.
- Keep `skills/ea-v0-2` as the installed skill folder until a future version intentionally renames the skill.
