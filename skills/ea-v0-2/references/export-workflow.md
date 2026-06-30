# Export Workflow

Use this reference when a user needs a local handoff package for one EA report or one EA batch run. For a recipient-facing verification and provenance-audit guide, read `docs/PROJECT_BUNDLE_VERIFICATION.md` from the repository root.

Report bundle command:

```bash
ea export report-bundle /path/to/ea-project --report-id rpt-project-20260630-001
ea export report-bundle /path/to/ea-project --report-id rpt-project-20260630-001 --output exports/report-bundles/custom-name
ea export report-bundle /path/to/ea-project --report-id rpt-project-20260630-001 --zip
ea export report-bundle /path/to/ea-project --report-id rpt-project-20260630-001 --zip-output exports/report-bundles/custom-name.zip
```

Report bundle default output:

```text
exports/report-bundles/{report_id}/
├── bundle_manifest.yml
├── bundle_checksums.yml
├── reports/
├── figures/
├── source-data/
├── results/
├── references/
├── references/files/
├── provenance/
└── provenance-inputs/
```

Optional archive:

```text
exports/report-bundles/{report_id}.zip
exports/report-bundles/{report_id}.zip.sha256
```

`--zip` writes a sibling `.zip` archive for the generated bundle. `--zip-output` writes the archive to a user-selected path and also enables archive creation. The manifest records `archive_created`, `archive_path`, `archive_ref`, `archive_checksum_path`, and `archive_checksum_ref` before the archive is written, so the `bundle_manifest.yml` inside the archive matches the returned CLI JSON.

Batch bundle command:

```bash
ea export batch-bundle /path/to/ea-project --batch-id batch-20260630-001
ea export batch-bundle /path/to/ea-project --batch-id batch-20260630-001 --output exports/batch-bundles/custom-name
ea export batch-bundle /path/to/ea-project --batch-id batch-20260630-001 --zip
ea export batch-bundle /path/to/ea-project --batch-id batch-20260630-001 --zip-output exports/batch-bundles/custom-name.zip
```

Verification command:

```bash
ea export verify-bundle /path/to/ea-project/exports/report-bundles/rpt-project-20260630-001
ea export verify-bundle /path/to/ea-project/exports/batch-bundles/batch-20260630-001
ea export verify-archive /path/to/ea-project/exports/report-bundles/rpt-project-20260630-001.zip
ea export verify-archive /path/to/custom.zip --checksum /path/to/custom.zip.sha256
```

Batch bundle default output:

```text
exports/batch-bundles/{batch_id}/
├── batch_bundle_manifest.yml
├── bundle_checksums.yml
├── batch/
├── report-bundles/
│   └── {report_id}/
│       ├── bundle_manifest.yml
│       └── bundle_checksums.yml
├── provenance/
└── provenance-inputs/
```

`batch_bundle_manifest.yml` records copied batch index/run/summary/source-manifest files, batch provenance refs, item summaries, and nested per-report bundle manifests. `--zip` writes `exports/batch-bundles/{batch_id}.zip` and `exports/batch-bundles/{batch_id}.zip.sha256` by default.

Checksum files:

- `bundle_checksums.yml` records SHA-256 and byte size for files inside the exported bundle folder after the main manifest is written.
- The checksum manifest excludes itself to avoid self-referential hashes.
- If a zip archive is written, the sidecar `*.zip.sha256` records the archive SHA-256.
- These files prove file integrity for handoff; they are not cryptographic signatures and do not prove user identity or authorship.
- `verify-bundle` recomputes the listed bundle file sizes and SHA-256 hashes from `bundle_checksums.yml`.
- `verify-archive` recomputes a zip archive SHA-256 and compares it with the `.sha256` sidecar.
- Verification commands return JSON with `status: pass` or `status: fail`; failed checks return exit code 2 and concrete failure reasons such as `missing_file`, `size_mismatch`, or `sha256_mismatch`.

What the bundle includes:

- The report Markdown from `reports/index.yml`.
- Figure files from `figures/index.yml`.
- Figure `source_data_refs`, such as processed CSV and peak-table files.
- Result metadata found by `result_id` or method-specific `*_result_id`.
- Reference records from `literature/references/index.yml`.
- Project-local reference files when `local_path` exists inside the project.
- Provenance records referenced by the report and result metadata.
- Project-local provenance input records/files, including raw metadata and raw data when provenance records point to them.
- `bundle_checksums.yml` for integrity checks.

Batch bundles additionally include:

- `processed/batches/index.yml`.
- The selected batch run record and batch summary.
- The source batch manifest referenced by the batch index.
- Batch provenance and provenance inputs.
- Nested report bundles for successful items that have `report_ref`.
- Top-level and nested `bundle_checksums.yml` files.

Boundaries:

- Export is read-only for analysis state.
- Export and optional archive creation do not rerun processing, rerun batches, regenerate reports or figures, validate scientific claims, download PDFs, resolve DOIs, or read browser/Zotero state.
- Export skips files outside the project root and records the skip in `bundle_manifest.yml` or `batch_bundle_manifest.yml`.
- Checksum manifests are integrity records, not signatures. EA's built-in detached signing currently applies to repository release packages, not project export bundles; signed project bundles require an external or user-managed signing workflow.
- Verification commands are read-only and local-only; they do not repair files, fetch missing artifacts, or trust absolute paths from another machine.
- A bundle with missing linked project refs returns status `warning`; fix the source project links and re-export before handoff when possible.
