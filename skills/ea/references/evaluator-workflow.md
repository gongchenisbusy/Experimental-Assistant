# Evaluator Workflow

Use this reference before handing an EA project to another agent, preparing a public demo, or checking whether a local project is ready for continued work.

Command:

```bash
ea eval project /path/to/ea-project
ea eval project /path/to/ea-project --no-write
```

Default behavior:

- Runs local project config portability checks.
- Runs `ea healthcheck` and includes its findings with `healthcheck.`-prefixed codes.
- Checks generated analysis figures for `style_profile` and `source_data_refs`.
- Checks report citation numbering and References entries.
- Checks report provenance refs and project-level readiness signals.
- Summarizes batch workflow records under `batches`, including batch count, item count, failed items, and provenance-backed batches.
- Summarizes material assignment traceability under `material_assignments`, including assigned result/feature counts and missing assignment-source counts.
- Writes `evaluation/eval-{yyyymmdd}-{nnn}.yml` unless `--no-write` is used.

Status meanings:

- `pass`: no errors or warnings.
- `warning`: no blocking errors, but some handoff/readiness metadata is incomplete.
- `fail`: at least one blocking error, such as a missing source-data file or failed healthcheck finding.

Batch/material notes:

- Failed batch items produce evaluator warnings when the batch records are otherwise traceable.
- Missing material assignment sources are blocking errors because later agents cannot reconstruct which rule/library produced the assignment.

Scope limits:

- Do not treat evaluator output as scientific truth scoring.
- Do not use it for live literature search, DOI resolution, PDF download, Zotero database reads, browser profile access, or institution-login checks.
- Use it as a deterministic local readiness report that later agents can inspect.

Repository release gate:

- For publishing or handing off the Experimental Assistant v1.1.0 repository itself, run `ea-public-release-smoke` after project-level readiness checks.
- The smoke gate is broader than `ea eval project`: it runs the test suite, validates the Experimental Assistant skill package, confirms the retired Compatibility skill is absent, checks core CLI help commands, scans product files for accidental developer-machine defaults, and checks release-facing files for credential-like assignments or token literals.
- After the smoke gate passes, run `ea-release-manifest` to write package metadata, git state, console scripts, release-input checksums, smoke-gate requirements, and public-user boundary notes under `dist/`.
- Run `ea-release-package` when the handoff should include a portable repository archive and `.zip.sha256` sidecar.
- Run `ea-verify-release-package ARCHIVE.zip` after copying or before handoff to verify the sidecar, embedded manifest, and manifest-listed payload checksums.
- The smoke gate should remain local and deterministic; it must not require Zotero, browser profiles, institution login, live web search, or private literature caches.

Recommended use:

1. Run workflow-specific tests or commands.
2. Run `ea healthcheck`.
3. Run `ea eval project`.
4. Run `ea-public-release-smoke` when the repository is being prepared for public release or broad handoff.
5. Run `ea-release-manifest` after release checks pass.
6. Run `ea-release-package` if a zip archive should be handed off.
7. Run `ea-verify-release-package ARCHIVE.zip` before handoff or after copying.
8. Fix `fail` items before handoff.
9. Either fix `warning` items or record why the warning is acceptable for the current stage.
