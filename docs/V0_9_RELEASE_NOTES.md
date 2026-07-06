# Experimental Assistant v0.9.6 Release Notes

Experimental Assistant v0.9.6 is a token-efficiency and runtime-lightness update on top of the v0.9.5 stabilization release. It keeps the `ea-v0-2` compatibility line, preserves full scientific/reporting capability, and focuses on router-style skill loading, traceability focus-subgraphs, compact default CLI output, and v0.9.6 release metadata rather than adding a new characterization method.

## Version

- Package version: `0.9.6`
- Release label: `v0.9.6`
- Skill folder: `skills/ea-v0-2`
- Compatibility note: the skill name and package name keep `ea-v0-2` for continuity; release artifacts and docs identify the v0.9.6 release state.

## Major Changes Since v0.9.5

- Added `references/routing-index.yml` so the EA skill can choose the smallest useful reference set for project, method, report, traceability, memory, literature-state, and release/install routes.
- Added explicit traceability entry points: `ea trace index`, `ea trace focus`, and `ea trace export --full`, while preserving `ea trace view` and `ea trace lookup`.
- Made `ea trace ...` and `ea brief project` default terminal output concise; use `--json` for compact structured output and `--json-full` for full automation/debug output.
- Kept comprehensive report generation intact. v0.9.6 does not reduce report depth, split reports into weaker stages, or remove existing analysis capability.
- Updated package, skill, downloaded instructions, release manifest/package/checklist/signature metadata, and public install docs to v0.9.6.

## Relationship To v1.0

v0.9.6 is not the final public v1.0. It should be handed to human testers and future agents to find remaining product, documentation, and scientific-boundary issues before v1.0. v1.0 should only be cut after the acceptance matrix, manual checklist, and real user walkthroughs have no blocking findings or have clear documented limitations.

## Stable Entry Points

- `ea init-project`, `ea config doctor`, `ea healthcheck`, `ea eval project`, `ea brief project`
- Raman/PL/XRD/FTIR/UV-Vis/XPS/electrochemistry/thermal/image-data local workflows when user review gates are satisfied
- `ea export report-html`, `ea export report-bundle`, `ea export batch-bundle`, `ea export verify-bundle`, `ea export verify-archive`
- `ea trace index`, `ea trace focus`, `ea trace view`, `ea trace lookup`, `ea trace export --full`
- release commands: `ea-public-release-smoke`, `ea-release-manifest`, `ea-release-package`, `ea-verify-release-package`, `ea-release-checklist`

## Screening Or Experimental Entry Points

- Material assignment libraries, source packets, suggestion records, and review packages are advisory until reviewed and cited.
- UV-Vis Tauc, derivative, correction, and replicate comparison helpers are screening workflows unless a reviewed method model and references support stronger claims.
- XPS background, component fitting, spin-orbit constraints, Tougaard starting points, and binding-energy candidates remain reviewed screening aids unless the project has enough source-backed evidence.
- Electrochemistry and thermal derived metrics summarize reviewed windows and context; they do not rank performance or prove mechanisms by themselves.
- Zotero-Codex integration is a local handoff/readiness contract; the companion workflow remains user-managed and optional.

## Migration Notes

- Existing legacy EA project folders can continue to be inspected with healthcheck/eval.
- For public handoff, regenerate any report bundles or release packages with the v0.9.6 code so manifests, checksums, and HTML exports use current metadata.
- Keep `skills/ea-v0-2` as the installed skill folder until a future version intentionally renames the skill.
