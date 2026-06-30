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
8. Run `ea healthcheck` after creating or modifying raw imports, processed outputs, reports, figures, or provenance.
