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
5. Generate reports with IDs, inline numeric citations, figure links, confidence labels, and provenance. Save candidate memory as review-gated suggestions, not confirmed findings.
6. Put questions that affect future work or scientific judgement at the end of the response.

## CLI Quick Start

Use the repository package when available:

```bash
ea init-project /path/to/ea-project --name "MoS2 mica CVD" --slug mos2-mica-cvd --direction "single-layer MoS2 on mica" --material MoS2 --experiment-type "CVD growth and Raman characterization"
ea config doctor /path/to/ea-project
ea healthcheck /path/to/ea-project
ea literature status /path/to/ea-project
ea add-skills check /path/to/child-skill-manifest.yml
ea lookup-figure /path/to/ea-project fig-project-raman-20260630-001
```

The legacy `ea init` command remains as a compatibility alias. Prefer `ea init-project` for v0.2 work.

## References

- For project structure and workflow, read `references/project-workflow.md`.
- For public-user initialization and forbidden defaults, read `references/public-initialization.md`.
- For child skill manifests and `add-skills`, read `references/module-manifest.md`.
- For report, figure, ID, citation, and confidence standards, read `references/report-figure-reference-standard.md`.
- For literature-library deployment, read `references/local-literature-library.md`.
- For Raman v0.2 behavior, read `references/raman-workflow.md`.

## Scripts

`scripts/run_public_demo.py` runs a developer/demo workflow only when a fixture root is explicitly supplied. Do not run it for real user projects unless the user asks for a demo or validation run.
