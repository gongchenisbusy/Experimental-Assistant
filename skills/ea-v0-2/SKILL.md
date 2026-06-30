---
name: ea-v0-2
description: Local-first Experimental Assistant v0.2 for materials-research projects. Use when Codex needs to initialize or continue an EA project, structure experiment logs, import raw characterization data, run review-gated Raman analysis, create traceable reports/figures/references, manage local literature-library state, validate EA child-skill manifests, or preserve project memory/provenance without assuming developer-machine paths or accounts.
---

# EA v0.2

## Overview

EA is a local-first research workspace for experimental scientists. It keeps project records, raw data, processed results, figures, reports, literature state, memory, review records, and provenance linked so later agents can reconstruct what happened.

Do not assume developer-machine Zotero, browser, institution, cache, or test paths. Public-user initialization must ask for or explicitly disable environment-specific settings.

## Default Workflow

1. Read the project root files first: `EA_PROJECT.md`, `PROJECT_RULE_CARD.md`, `.ea/project_config.yml`, `progress/`, `memory/`, `provenance/`, and relevant indices.
2. If no project exists, run or emulate `ea init-project` and ask only for settings that affect the next work. Keep Zotero, browser, institution, and cache settings disabled or null unless the user provides them.
3. Treat raw files as protected assets. Import them as controlled copies and write generated outputs under `processed/`, `figures/`, `reports/`, `literature/`, or other non-raw directories.
4. Before running analysis that changes interpretation, ensure the relevant user review gates exist or ask at the end for the missing confirmation.
5. Generate reports with IDs, inline numeric citations, figure links, confidence labels, and provenance. Save possible durable memory as review-gated memory candidates, not confirmed findings.
6. Put questions that affect future work or scientific judgement at the end of the response.

## CLI Quick Start

Use the repository package when available:

```bash
ea init-project /path/to/ea-project --name "MoS2 mica CVD" --slug mos2-mica-cvd --direction "single-layer MoS2 on mica" --material MoS2 --experiment-type "CVD growth and Raman characterization"
ea config doctor /path/to/ea-project
ea healthcheck /path/to/ea-project
ea raw import /path/to/ea-project /path/to/raw-spectrum.txt --characterization-type raman --sample-ref sample-001 --experiment-ref exp-001
ea raman inspect /path/to/ea-project raw/raman/char-20260630-001/raw-spectrum.txt
ea review add /path/to/ea-project --target-type raman_columns --target-ref raw/raman/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "x=col_0, y=col_1, unit=cm^-1"
ea review add /path/to/ea-project --target-type raman_parameters --target-ref raw/raman/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default Raman parameters confirmed"
ea raman process /path/to/ea-project --metadata raw/raman/char-20260630-001/metadata.yml --x-column col_0 --y-column col_1 --x-unit cm^-1 --column-review-ref review-20260630-001 --parameter-review-ref review-20260630-002 --sample-ref sample-001
ea raman report /path/to/ea-project --metadata processed/sample-001/raman/res-project-raman-20260630-001/raman_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
ea raw import /path/to/ea-project /path/to/raw-pl.txt --characterization-type pl --sample-ref sample-001 --experiment-ref exp-001
ea pl inspect /path/to/ea-project raw/pl/char-20260630-001/raw-pl.txt
ea review add /path/to/ea-project --target-type pl_columns --target-ref raw/pl/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "x=col_0, y=col_1, unit=eV"
ea review add /path/to/ea-project --target-type pl_parameters --target-ref raw/pl/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default PL parameters confirmed"
ea pl process /path/to/ea-project --metadata raw/pl/char-20260630-001/metadata.yml --x-column col_0 --y-column col_1 --x-unit eV --column-review-ref review-20260630-003 --parameter-review-ref review-20260630-004 --sample-ref sample-001
ea pl report /path/to/ea-project --metadata processed/sample-001/pl/res-project-pl-20260630-001/pl_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
ea literature status /path/to/ea-project
ea literature plan /path/to/ea-project --scope ordinary --access-mode open_access_only
ea literature confirm /path/to/ea-project --selected-top-n 50 --user-response "User confirmed top 50."
ea literature handoff /path/to/ea-project --literature-thread-id thread-lit-001
ea literature sync-status /path/to/ea-project --update literature/acquisition_status_update.yml
ea add-skills check /path/to/child-skill-manifest.yml
ea add-skills dry-run /path/to/child-skill-manifest.yml --workspace /path/to/ea-project --sample-output /path/to/sample-output.yml
ea add-skills register /path/to/child-skill-manifest.yml --workspace /path/to/ea-project --sample-output /path/to/sample-output.yml
ea image-data record /path/to/ea-project --metadata raw/sem/char-20260630-001/metadata.yml --method sem --description "User-confirmed image notes" --description-review-ref review-20260630-001 --confidence low
ea image-data report /path/to/ea-project --metadata processed/sample-001/sem/res-project-sem-20260630-001/image_metadata.yml --reference-id ref-20260630-001
ea references add /path/to/ea-project --citation "Author A. Title. Journal volume, pages (year)." --doi 10.xxxx/example --url https://doi.org/10.xxxx/example
ea references import-bibtex /path/to/ea-project /path/to/user-exported-references.bib
ea references validate-report /path/to/ea-project reports/rpt-example.md
ea memory propose /path/to/ea-project --text "Candidate finding..." --source-ref reports/rpt-example.md --provenance-ref prov-20260630-001 --category interpretation --confidence medium
ea memory review /path/to/ea-project --candidate memory/candidates/memcand-20260630-001.md --user-response "可以，保存"
ea memory commit /path/to/ea-project --candidate memory/candidates/memcand-20260630-001.md --review-ref review-20260630-001
ea lookup-figure /path/to/ea-project fig-project-raman-20260630-001
```

The legacy `ea init` command remains as a compatibility alias. Prefer `ea init-project` for v0.2 work.

Built-in child-skill manifests live in `skill-registry/builtins/` and are indexed by `skill-registry/index.yml`. Treat PL, XRD, FTIR, UV-Vis, XPS, electrochemistry, thermal analysis, literature-library, and scientific-figure entries as EA contract boundaries unless a concrete implementation service is present.

## References

- For project structure and workflow, read `references/project-workflow.md`.
- For public-user initialization and forbidden defaults, read `references/public-initialization.md`.
- For child skill manifests and `add-skills`, read `references/module-manifest.md`.
- For report, figure, ID, citation, and confidence standards, read `references/report-figure-reference-standard.md`.
- For literature-library deployment, read `references/local-literature-library.md`.
- For Raman v0.2 behavior, read `references/raman-workflow.md`.
- For PL v0.2 behavior, read `references/pl-workflow.md`.
- For SEM/TEM/optical microscopy image data, read `references/image-data-workflow.md`.
- For review-gated durable project memory, read `references/memory-workflow.md`.

## Scripts

`scripts/run_public_demo.py` runs a developer/demo workflow only when a fixture root is explicitly supplied. Do not run it for real user projects unless the user asks for a demo or validation run.
