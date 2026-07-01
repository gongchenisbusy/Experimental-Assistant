# EA v0.2 Project Bundle Verification

This guide is for users, collaborators, and future agents who receive an EA project export bundle for one report or one batch run. It explains how to verify local file integrity, audit provenance coverage, and record signature evidence when a lab requires it.

Project bundle verification is different from repository release verification. Repository release packages can use EA's optional detached Ed25519 signing workflow. Project export bundles currently provide checksum-based integrity records only.

## 1. Expected Bundle Artifacts

A report bundle created by `ea export report-bundle` normally contains:

- `bundle_manifest.yml`
- `bundle_checksums.yml`
- `reports/`
- `figures/`
- `source-data/`
- `results/`
- `references/`
- `references/files/`
- `provenance/`
- `provenance-inputs/`
- optional `traceability/` YAML/Markdown focused on the exported report when `--include-trace` was used

A batch bundle created by `ea export batch-bundle` normally contains:

- `batch_bundle_manifest.yml`
- `bundle_checksums.yml`
- `batch/`
- `report-bundles/` with nested report bundle manifests and checksum records
- `provenance/`
- `provenance-inputs/`
- optional nested report traceability YAML/Markdown files when `--include-trace` was used

When `--zip` or `--zip-output` is used, EA also writes a portable `.zip` archive and a `.zip.sha256` sidecar.

## 2. Verification Order

Before export, check the source project:

```bash
ea healthcheck /path/to/ea-project
ea eval project /path/to/ea-project
```

Create and verify a report bundle:

```bash
ea export report-bundle /path/to/ea-project \
  --report-id rpt-project-slug-YYYYMMDD-001 \
  --include-trace \
  --zip

ea export verify-bundle /path/to/ea-project/exports/report-bundles/rpt-project-slug-YYYYMMDD-001
ea export verify-archive /path/to/ea-project/exports/report-bundles/rpt-project-slug-YYYYMMDD-001.zip
```

Create and verify a batch bundle:

```bash
ea export batch-bundle /path/to/ea-project \
  --batch-id batch-YYYYMMDD-001 \
  --include-trace \
  --zip

ea export verify-bundle /path/to/ea-project/exports/batch-bundles/batch-YYYYMMDD-001
ea export verify-archive /path/to/ea-project/exports/batch-bundles/batch-YYYYMMDD-001.zip
```

Use an explicit checksum sidecar when the archive was renamed:

```bash
ea export verify-archive /path/to/exported-bundle.zip \
  --checksum /path/to/exported-bundle.zip.sha256
```

## 3. What The Checks Prove

`ea healthcheck` audits the source project for missing config, broken provenance links, raw hash issues, report citation issues, figure backlinks, batch records, and material-assignment traceability.

`ea eval project` summarizes whether the project is ready for handoff, including figure/source-data traces, report citations, batch runs, and persisted evaluation records.

`ea export report-bundle` copies one report and its linked figures, source data, result metadata, references, local reference files, provenance records, and project-local provenance inputs.

With `--include-trace`, report bundles also include a focused traceability YAML/Markdown pair under `traceability/`. Batch bundles pass that option to nested report bundles and record `trace_export.strategy: nested_report_focused_trace_views`; v0.2 does not emit a separate batch-level trace graph.

`ea export batch-bundle` copies one batch run, its batch records and summaries, batch provenance inputs, and nested per-report bundles for successful items with reports.

`bundle_checksums.yml` records SHA-256 and byte size for files in the exported bundle folder. `ea export verify-bundle` recomputes those records after a copy or handoff.

`.zip.sha256` records the SHA-256 of the portable archive. `ea export verify-archive` recomputes the archive hash and compares it with the sidecar.

These checks prove local integrity of the exported files. They do not prove scientific correctness, complete literature coverage, user identity, authorship, or release intent.

## 4. Provenance Audit

For a report bundle, inspect `bundle_manifest.yml` and confirm that the manifest lists the expected report, result metadata, figures, source data, references, provenance records, and skipped files if any.

For a batch bundle, inspect `batch_bundle_manifest.yml` and confirm that it lists the expected batch run, batch summary, source batch manifest, item summaries, nested report bundles, batch provenance records, and skipped files if any.

Treat missing or skipped project refs as follow-up work before handoff. Fix the source project links, rerun `ea healthcheck`, rerun `ea eval project`, and export again.

Do not edit raw data inside an exported bundle to make verification pass. If a source artifact is wrong, correct the project through the normal EA workflow and export a new bundle.

## 5. Signature Boundary

EA v0.2 does not provide a built-in detached signing command for project export bundles. The built-in signing workflow is limited to repository release packages.

If a lab or collaborator requires signed project bundles, use an external or user-managed signing workflow after `ea export verify-bundle` and `ea export verify-archive` pass. Record the signature evidence alongside the bundle, not inside private EA defaults.

A minimal signature record should include:

- bundle folder or archive filename;
- archive SHA-256 from `.zip.sha256` when a zip exists;
- signature file name;
- signing algorithm and tool;
- signer name or role;
- public-key fingerprint;
- trusted public-key delivery channel;
- verification date;
- verifier name or role.

Do not store private keys, institution credentials, browser profiles, or access tokens in the EA project or exported bundle.

## 6. Recommended Handoff Record

When a recipient verifies a project bundle, save a short note with:

- bundle type: report or batch;
- report ID or batch ID;
- source project name or slug;
- `ea healthcheck` status before export if known;
- `ea eval project` status before export if known;
- `ea export verify-bundle` status;
- `ea export verify-archive` status if a zip exists;
- any missing or skipped refs from the bundle manifest;
- external signature status if used;
- verification date and verifier name or role.

This record can live beside the exported bundle or in the receiving lab's own project log.
