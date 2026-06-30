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

References use inline numeric citations at the exact supported text location, then matching entries:

```text
Layer-related Raman shifts can be affected by strain and doping[1,2].

## References

[1] Author A. Title. Journal volume, pages (year). DOI: ... | Local: ... | Web: ...
```

Confidence labels: high, medium, low, insufficient. In Chinese reports use `高`, `中`, `低`, `不足`.
