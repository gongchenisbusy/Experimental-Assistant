# EA Project Workflow

Use this reference when creating or continuing an EA project.

Core workspace:

```text
ea-project/
├── EA_PROJECT.md
├── PROJECT_RULE_CARD.md
├── .ea/project_config.yml
├── experiments/
├── evaluation/
├── exports/
│   ├── batch-bundles/
│   └── report-bundles/
├── samples/
├── raw/
├── templates/
├── processed/
│   └── batches/
├── figures/
├── reports/
├── literature/
├── skill-registry/
├── reviews/
├── provenance/
├── memory/
├── suggestions/
├── progress/
└── open-items/
```

Workflow:

1. Open or initialize the project.
2. Preserve user input as source text when structuring logs.
3. Import raw files as controlled read-only copies with hashes.
4. Run deterministic processing scripts after review gates are satisfied.
5. Write reports, figure records, provenance, and review records.
6. Save new findings as memory candidates until the user confirms them.
7. Keep open questions in `open-items/` when they matter but do not block the current step.
8. Run `ea healthcheck` after creating or modifying raw imports, processed outputs, reports, figures, provenance, references, or memory.
9. Run `ea eval project` before handoff, public-demo readiness checks, or long context transitions.

CLI path for the first Raman workflow:

```bash
ea raw import /path/to/ea-project /path/to/raw-spectrum.txt --characterization-type raman --sample-ref sample-001 --experiment-ref exp-001
ea raman inspect /path/to/ea-project raw/raman/char-20260630-001/raw-spectrum.txt
ea review add /path/to/ea-project --target-type raman_columns --target-ref raw/raman/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "x=col_0, y=col_1, unit=cm^-1"
ea review add /path/to/ea-project --target-type raman_parameters --target-ref raw/raman/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default Raman parameters confirmed"
ea raman process /path/to/ea-project --metadata raw/raman/char-20260630-001/metadata.yml --x-column col_0 --y-column col_1 --x-unit cm^-1 --column-review-ref review-20260630-001 --parameter-review-ref review-20260630-002 --sample-ref sample-001
ea raman report /path/to/ea-project --metadata processed/sample-001/raman/res-project-raman-20260630-001/raman_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
```

CLI path for the first PL workflow:

```bash
ea raw import /path/to/ea-project /path/to/raw-pl.txt --characterization-type pl --sample-ref sample-001 --experiment-ref exp-001
ea pl inspect /path/to/ea-project raw/pl/char-20260630-001/raw-pl.txt
ea review add /path/to/ea-project --target-type pl_columns --target-ref raw/pl/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "x=col_0, y=col_1, unit=eV"
ea review add /path/to/ea-project --target-type pl_parameters --target-ref raw/pl/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default PL parameters confirmed"
ea pl process /path/to/ea-project --metadata raw/pl/char-20260630-001/metadata.yml --x-column col_0 --y-column col_1 --x-unit eV --column-review-ref review-20260630-003 --parameter-review-ref review-20260630-004 --sample-ref sample-001
ea pl report /path/to/ea-project --metadata processed/sample-001/pl/res-project-pl-20260630-001/pl_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
```

CLI path for the first XRD workflow:

```bash
ea raw import /path/to/ea-project /path/to/raw-xrd.txt --characterization-type xrd --sample-ref sample-001 --experiment-ref exp-001
ea xrd inspect /path/to/ea-project raw/xrd/char-20260630-001/raw-xrd.txt
ea review add /path/to/ea-project --target-type xrd_columns --target-ref raw/xrd/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "x=two_theta, y=intensity, unit=2theta_deg"
ea review add /path/to/ea-project --target-type xrd_parameters --target-ref raw/xrd/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default XRD parameters confirmed"
ea xrd process /path/to/ea-project --metadata raw/xrd/char-20260630-001/metadata.yml --x-column two_theta --y-column intensity --x-unit 2theta_deg --column-review-ref review-20260630-005 --parameter-review-ref review-20260630-006 --sample-ref sample-001
ea xrd report /path/to/ea-project --metadata processed/sample-001/xrd/res-project-xrd-20260630-001/xrd_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
```

Editable templates:

```bash
ea templates parameters raman --output /path/to/ea-project/templates/raman_parameters.yml
ea templates batch-manifest /path/to/ea-project --method raman --method pl --method xrd --output batch_manifest.yml
```

Parameter templates are directly usable with `--parameters-file` after the user confirms the parameter content. Batch manifest templates still need real metadata and confirmed review refs before validation.

Project readiness evaluation:

```bash
ea healthcheck /path/to/ea-project
ea eval project /path/to/ea-project
ea eval project /path/to/ea-project --no-write
```

Report bundle export:

```bash
ea export report-bundle /path/to/ea-project --report-id rpt-project-20260630-001 --zip
ea export batch-bundle /path/to/ea-project --batch-id batch-20260630-001 --zip
```

Report bundles are written under `exports/report-bundles/{report_id}` by default and copy linked report, figure, source-data, result, reference, and provenance artifacts for handoff. Batch bundles are written under `exports/batch-bundles/{batch_id}` and include batch records plus nested per-report bundles. Use `--zip` or `--zip-output` when the same bundle should also be archived for transfer.

Batch characterization after individual item review gates exist:

```bash
ea batch validate /path/to/ea-project batch_manifest.yml
ea batch run /path/to/ea-project batch_manifest.yml
```

Batch manifests can coordinate Raman, PL, and XRD items. They do not replace column, unit, or parameter confirmation; each item must reference confirmed review records. Healthcheck/evaluator treat `processed/batches/index.yml`, each `batch_run.yml`, batch summaries, item result/report refs, and batch provenance refs as handoff-critical project state.
