# Export Workflow

Use this reference when a user needs a readable report export, a local handoff package for one EA report, or one EA batch run. For a recipient-facing verification and provenance-audit guide, read `docs/PROJECT_BUNDLE_VERIFICATION.md` from the repository root.

User-readable report command:

```bash
ea export report-html /path/to/ea-project --report-id rpt-project-20260630-001
ea export report-html /path/to/ea-project --report-id rpt-project-20260630-001 --output exports/user-reports/custom-report.html
ea export report-html /path/to/ea-project --report-id rpt-project-20260630-001 --no-embed-images
ea export report-html /path/to/ea-project --report-id rpt-project-20260630-001 --include-audit
ea export report-html /path/to/ea-project --draft-id draft-20260722-001 --preview
ea composite-report /path/to/ea-project --result-id res-raman-001 --result-id res-pl-001 --sample-ref sample-001 --user-response "确认生成综合报告"
```

HTML export default output:

```text
exports/user-reports/{report_id}.html
exports/user-reports/{report_id}.html.yml
```

The HTML report is a friendly rendering of the canonical Markdown report from `reports/index.yml`. It embeds linked figures as data URIs by default, adds a Figures section from `figures/index.yml` so images remain visible even when the Markdown only lists file paths, preserves figure IDs, captions, original project-local paths, report IDs, reference records, citation-number checks, provenance summaries, and an audit appendix. The sidecar YAML records `canonical_report_ref`, figure/reference/provenance metadata, missing refs if any, and the same boundaries. Use this for a user-readable report first; use `report-bundle` when the recipient also needs copied source data, result metadata, references, checksums, and optional focused traceability records.

`--draft-id ... --preview` renders a staged draft with a `DRAFT / NOT FORMAL` banner. It does not add a report to `reports/index.yml`, create a formal report/provenance record, or satisfy a requested formal-delivery lifecycle. `composite-report` accepts multiple reviewed results, writes one composite report/provenance record with multi-report figure backlinks, and immediately returns the HTML delivery path.

`--no-embed-images` keeps project-local image refs rather than data URIs. Audit details are omitted by default; `--include-audit` adds the detailed provenance appendix when explicitly needed.

Report bundle command:

```bash
ea export report-bundle /path/to/ea-project --report-id rpt-project-20260630-001
ea export report-bundle /path/to/ea-project --report-id rpt-project-20260630-001 --output exports/report-bundles/custom-name
ea export report-bundle /path/to/ea-project --report-id rpt-project-20260630-001 --include-trace
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
├── traceability/        # only when --include-trace is used
└── provenance-inputs/
```

Optional archive:

```text
exports/report-bundles/{report_id}.zip
exports/report-bundles/{report_id}.zip.sha256
```

`--zip` writes a sibling `.zip` archive for the generated bundle. `--zip-output` writes the archive to a user-selected path and also enables archive creation. The manifest records `archive_created`, `archive_path`, `archive_ref`, `archive_checksum_path`, and `archive_checksum_ref` before the archive is written, so the `bundle_manifest.yml` inside the archive matches the returned CLI JSON.

`--include-trace` writes a focused report traceability YAML/Markdown pair under the bundle's `traceability/` directory and records it under `artifacts.traceability` plus `trace_export` in `bundle_manifest.yml`. The trace view is an audit artifact only: it does not mutate reports, create ReviewRecords, commit memory, register references, inject citations, generate source packets/suggestions, or prove scientific conclusions.

Batch bundle command:

```bash
ea export batch-bundle /path/to/ea-project --batch-id batch-20260630-001
ea export batch-bundle /path/to/ea-project --batch-id batch-20260630-001 --output exports/batch-bundles/custom-name
ea export batch-bundle /path/to/ea-project --batch-id batch-20260630-001 --include-trace
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

For batch bundles, `--include-trace` passes focused trace view generation into each nested report bundle. The top-level batch manifest records `trace_export.strategy: nested_report_focused_trace_views`; Experimental Assistant v1.1.0 does not emit a batch-level trace graph until the traceability service models batch nodes.

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
- Optional focused report traceability YAML/Markdown when `--include-trace` is used.
- `bundle_checksums.yml` for integrity checks.

Batch bundles additionally include:

- `processed/batches/index.yml`.
- The selected batch run record and batch summary.
- The source batch manifest referenced by the batch index.
- Batch provenance and provenance inputs.
- Nested report bundles for successful items that have `report_ref`.
- Optional focused traceability YAML/Markdown inside nested report bundles when `--include-trace` is used.
- Top-level and nested `bundle_checksums.yml` files.

Boundaries:

- Export is read-only for analysis state.
- HTML export, bundle export, and optional archive creation do not rerun processing, rerun batches, regenerate reports or figures, validate scientific claims, download PDFs, resolve DOIs, or read browser/Zotero state.
- HTML export does not mutate canonical Markdown/YAML reports; it records traceability back to the canonical report in the sidecar YAML.
- Export skips files outside the project root and records the skip in `bundle_manifest.yml` or `batch_bundle_manifest.yml`.
- Checksum manifests are integrity records, not signatures. EA's built-in detached signing currently applies to repository release packages, not project export bundles; signed project bundles require an external or user-managed signing workflow.
- Verification commands are read-only and local-only; they do not repair files, fetch missing artifacts, or trust absolute paths from another machine.
- A bundle with missing linked project refs returns status `warning`; fix the source project links and re-export before handoff when possible.
