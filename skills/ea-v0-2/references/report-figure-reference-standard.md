# Report, Figure, And Reference Standard

Use this reference when creating analysis reports, plots, references, or figure lookups.

ID forms:

```text
project_id: prj-{project_slug}
raw_data_id: raw-{project_slug}-{yyyymmdd}-{nnn}-{hash8}
result_id: res-{project_slug}-{method}-{yyyymmdd}-{nnn}
report_id: rpt-{project_slug}-{yyyymmdd}-{nnn}
figure_id: fig-{project_slug}-{method}-{yyyymmdd}-{nnn}
```

Reports are Markdown with YAML frontmatter. Include summary, report ID info, samples/raw data, processing steps, embedded figures and original file links, data analysis, possible conclusions with confidence, limitations/questions, References, and Provenance.

Every generated figure needs a stable figure ID and a footer in the lower-right canvas margin:

```text
FigID: fig-example-raman-20260630-001 | Report: rpt-example-20260630-001
```

Generated analysis figures should use the shared Python/matplotlib profile `nature_like_clean` unless the user explicitly selects another reviewed style. The current helper layer lives in `ea.figures` and provides:

- `styled_subplots`: apply publication-oriented rcParams before creating axes.
- `style_axis`: apply title, labels, legend, light grid, and hidden top/right spines.
- `save_styled_figure`: place the lower-right canvas footer, save deterministic PNG output, and close the figure.

Figure index records should include `style_profile` and `source_data_refs` when generated from processed data. Raman, PL, and XRD workflows write these fields so another agent can trace a plotted figure back to processed CSV and peak-table sources.
Run `ea eval project` before handoff to check that generated analysis figures keep this style/source-data metadata.
Use `ea export report-bundle /path/to/ea-project --report-id <report_id>` when a user or later agent needs the report, figure files, source data, result metadata, references, and provenance gathered into one local handoff folder. Use `ea export batch-bundle /path/to/ea-project --batch-id <batch_id>` when a whole batch run and its nested report bundles should travel together. Add `--zip` when the same handoff bundle should also be packaged as an archive with a `.zip.sha256` sidecar. Use `ea export verify-bundle` and `ea export verify-archive` to verify copied handoff artifacts.

References use inline numeric citations at the exact supported text location, then matching entries. Adjacent references use `[1][2]`, not `[1,2]`, so the report validator can map each marker directly.

```text
Layer-related Raman shifts can be affected by strain and doping[1][2].

## References

[1] Author A. Title. Journal volume, pages (year). DOI: ... | Local: ... | Web: ...
```

Register reusable references before report generation when possible:

```bash
ea references add /path/to/ea-project --citation "Author A. Title. Journal volume, pages (year)." --doi 10.xxxx/example --url https://doi.org/10.xxxx/example --local-path literature/fulltext/example.pdf
ea references import-bibtex /path/to/ea-project /path/to/user-exported-references.bib
ea references validate-report /path/to/ea-project reports/rpt-example-20260630-001.md
```

Reference records are stored under `literature/references/{reference_id}.yml` and indexed in `literature/references/index.yml`. Reports should store `reference_ids` and `numbered_references` in YAML frontmatter so another agent can trace each inline marker back to a local PDF, web page, DOI, or literature-library item.

Use BibTeX import only for an explicit user-provided export file. The importer reuses existing reference records when DOI, URL, normalized title, or normalized citation already matches, and its JSON output reports imported, reused, and skipped entries. It must not read Zotero databases, browser profiles, institution login paths, or private cache folders by default.

Confidence labels: high, medium, low, insufficient. In Chinese reports use `高`, `中`, `低`, `不足`.
