# Export Workflow

Use this reference when a user needs a local handoff package for one EA report.

Command:

```bash
ea export report-bundle /path/to/ea-project --report-id rpt-project-20260630-001
ea export report-bundle /path/to/ea-project --report-id rpt-project-20260630-001 --output exports/report-bundles/custom-name
ea export report-bundle /path/to/ea-project --report-id rpt-project-20260630-001 --zip
ea export report-bundle /path/to/ea-project --report-id rpt-project-20260630-001 --zip-output exports/report-bundles/custom-name.zip
```

Default output:

```text
exports/report-bundles/{report_id}/
├── bundle_manifest.yml
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
```

`--zip` writes a sibling `.zip` archive for the generated bundle. `--zip-output` writes the archive to a user-selected path and also enables archive creation. The manifest records `archive_created`, `archive_path`, and `archive_ref` before the archive is written, so the `bundle_manifest.yml` inside the archive matches the returned CLI JSON.

What the bundle includes:

- The report Markdown from `reports/index.yml`.
- Figure files from `figures/index.yml`.
- Figure `source_data_refs`, such as processed CSV and peak-table files.
- Result metadata found by `result_id` or method-specific `*_result_id`.
- Reference records from `literature/references/index.yml`.
- Project-local reference files when `local_path` exists inside the project.
- Provenance records referenced by the report and result metadata.
- Project-local provenance input records/files, including raw metadata and raw data when provenance records point to them.

Boundaries:

- Export is read-only for analysis state.
- Export and optional archive creation do not rerun processing, regenerate figures, validate scientific claims, download PDFs, resolve DOIs, or read browser/Zotero state.
- Export skips files outside the project root and records the skip in `bundle_manifest.yml`.
- A bundle with missing linked project refs returns status `warning`; fix the source project links and re-export before handoff when possible.
