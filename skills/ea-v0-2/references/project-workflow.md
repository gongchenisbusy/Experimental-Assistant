# EA Project Workflow

Use this reference when creating or continuing an EA project.

Core workspace:

```text
ea-project/
├── EA_PROJECT.md
├── PROJECT_RULE_CARD.md
├── .ea/project_config.yml
├── experiments/
├── samples/
├── raw/
├── processed/
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

CLI path for the first Raman workflow:

```bash
ea raw import /path/to/ea-project /path/to/raw-spectrum.txt --characterization-type raman --sample-ref sample-001 --experiment-ref exp-001
ea raman inspect /path/to/ea-project raw/raman/char-20260630-001/raw-spectrum.txt
ea review add /path/to/ea-project --target-type raman_columns --target-ref raw/raman/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "x=col_0, y=col_1, unit=cm^-1"
ea review add /path/to/ea-project --target-type raman_parameters --target-ref raw/raman/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default Raman parameters confirmed"
ea raman process /path/to/ea-project --metadata raw/raman/char-20260630-001/metadata.yml --x-column col_0 --y-column col_1 --x-unit cm^-1 --column-review-ref review-20260630-001 --parameter-review-ref review-20260630-002 --sample-ref sample-001
ea raman report /path/to/ea-project --metadata processed/sample-001/raman/res-project-raman-20260630-001/raman_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
```
