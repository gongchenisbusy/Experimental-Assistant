---
name: ea-v0-2
description: Experimental Assistant v0.9.5 local-first materials-research skill. Use when Codex needs to initialize or continue EA projects, structure experiment logs, import protected raw data, run review-gated characterization workflows, manage literature state, preserve lightweight project working memory, generate reports or export bundles, build report-memory traceability views, validate release packages, install/check the EA CLI or Codex skill, or maintain provenance without developer-machine paths or accounts.
---

# Experimental Assistant v0.9.5

## Overview

Experimental Assistant is a local-first research workspace for experimental scientists. It keeps project records, raw data, processed results, figures, reports, literature state, memory, review records, and provenance linked so future agents can reconstruct what happened.

Internal compatibility id: the skill folder, Python package name, and Codex invocation remain `ea-v0-2` / `$ea-v0-2` so existing installs and project records continue to work. Do not present `ea-v0-2` as the current public version; the user-facing product/version is Experimental Assistant v0.9.5.

Do not assume developer-machine Zotero, browser, institution, cache, or test paths. Also do not assume keys or credentials. Public-user initialization must ask for or explicitly leave environment-specific settings disabled.

Scientific caution means evidence layering, not silence. Do not require every numeric value to be typed by the user. EA may proactively gather or discuss source-backed candidates from built-in libraries, registered references, local literature, public metadata, user-provided sources, or user-confirmed searches. A no-live-lookup or no-auto-application boundary is not a ban on source-backed assistant work; it means lookup, source registration, report citation, processing-parameter use, and memory commitment remain explicit and traceable. Preserve source, applicability, confidence, review state, and provenance, and never silently apply values that change processing or conclusions.

## Default Modes

Start in consult mode unless the user clearly asks you to modify a project or run a command. Use record mode for local file updates that are requested or required by the workflow. Use execute mode for analysis, download/acquisition, report generation, batch runs, or release tasks after the relevant review and permission gates are satisfied.

When information is missing, ask only for the next decision that changes behavior. Put scientific judgement or future-work questions at the end of the response.

## Core Workflow

1. Read the project root files first: `EA_PROJECT.md`, `PROJECT_RULE_CARD.md`, `.ea/project_config.yml`, `memory/project-working-memory.md`, `progress/`, `memory/`, `provenance/`, and relevant indices.
2. If no project exists, run or emulate `ea init-project`. Initialization creates a compact `memory/project-working-memory.md` skeleton and leaves Zotero, browser, institution, cache, and credential settings disabled unless the user supplies them.
3. Treat raw files as protected assets. Import them as controlled copies and write generated outputs under non-raw directories.
4. Before processing or report claims that change interpretation, ensure the relevant ReviewRecords exist. Use `ea review add --confirm` only for explicit parameter/field/suggestion confirmation. Use `ea review promote` when earlier advisory review evidence needs explicit user promotion.
5. Generate reports with IDs, inline numeric citations, figure links, confidence labels, and provenance. Save durable scientific findings as review-gated memory candidates, not as automatic confirmed memory.
6. Refresh compact project continuity with `ea memory refresh-project` after meaningful project changes and read it with `ea memory show-project` when resuming long work. This file stores pointers and current state, not full raw/report content.
7. Run `ea healthcheck`, `ea eval project`, and `ea brief project` before handoff or user-facing summaries. Use `ea trace view` and `ea trace lookup` when the user needs compact report-memory traceability across figures, reports, ReviewRecords, registered references, reference seeds, built-in/source-library refs, provenance, and memory. Use the brief first; keep detailed JSON, hashes, refs, review records, and trace graphs in local files unless the user asks for audit detail.

## Setup And Onboarding

Use these after installing from GitHub or a release package:

```bash
ea version
ea codex install-skill
ea onboarding post-install --event install --lang zh
ea install-check
```

The installer uses the `$ea-v0-2` compatibility invocation, backs up an existing `ea-v0-2` skill by default, does not delete `ea-v0-1`, and validates the downloaded skill when Codex `quick_validate.py` is available.

Run `ea literature setup-preflight /path/to/ea-project --lang zh` before literature acquisition or Zotero/browser handoff. It reports what is already configured, what the user must supply, and what cannot be configured automatically; it does not launch Zotero, open browsers, inspect credentials, download PDFs, or use institution access.

## Large Work Gates

Before literature acquisition, broad public metadata searches, source-candidate preparation, long report bundles, or other expensive workflows, estimate the task with `ea estimate workflow`. EA v0.9.5 uses a fixed large-work threshold of `100` Codex-credit-equivalent units, based on the approved v0.9.5 planning estimate of about 20% of a practical Plus/GPT-5.5 five-hour window.

If `ea estimate workflow` or `ea literature ...` reports `needs_confirmation`, summarize the expected work and ask whether to continue. Users may disable this reminder preference with `ea estimate reminders /path/to/ea-project --disable --reason "user requested no large-work reminders"`; safety, permission, and review gates still apply.

Relevant commands:

```bash
ea estimate workflow /path/to/ea-project --workflow literature_acquisition --items 50 --mode standard
ea estimate reminders /path/to/ea-project --disable --reason "user requested no large-work reminders"
ea literature search-public /path/to/ea-project --source crossref --source openalex --max-results 20 --confirm-large-work
ea literature acquisition-request /path/to/ea-project --confirm-large-work
ea literature prepare-source-candidates /path/to/ea-project --method ftir --source-items literature/selected_items.yml --confirm-large-work
```

## Command Index

For the command catalogue, read `references/cli-command-index.md` only when the task needs concrete CLI examples. Keep the top-level skill context compact during ordinary use.

## Release Checks

For repository-level public-release checks, run `ea-public-release-smoke` or `python3 scripts/public_release_smoke.py`, then generate and verify release artifacts with `ea-release-manifest`, `ea-release-package`, `ea-verify-release-package`, and `ea-release-checklist`.

The smoke gate runs tests, validates the skill package, checks CLI help, scans portability/sensitive values, checks version identity, and verifies the downloaded skill instructions mention the current public version and v0.9.5 onboarding/literature/memory/estimate commands.

## References

- For project structure and workflow, read `references/project-workflow.md`.
- For public-user installation and forbidden defaults, read `references/public-initialization.md`.
- For interaction modes and question style, read `references/interaction-modes.md`.
- For CLI examples, read `references/cli-command-index.md`.
- For post-install and downloaded-skill onboarding, read `references/onboarding-workflow.md`.
- For large-work estimation and reminder preferences, read `references/token-economy-workflow.md`.
- For compact long-running project continuity, read `references/project-working-memory.md`.
- For child skill manifests and `add-skills`, read `references/module-manifest.md`.
- For report, figure, ID, citation, and confidence standards, read `references/report-figure-reference-standard.md`.
- For evaluator/readiness checks, read `references/evaluator-workflow.md`.
- For repository smoke checks and release manifests, read `references/release-workflow.md`.
- For report bundle export, read `references/export-workflow.md`.
- For literature-library deployment, read `references/local-literature-library.md`.
- For Raman workflow behavior, read `references/raman-workflow.md`.
- For PL workflow behavior, read `references/pl-workflow.md`.
- For XRD workflow behavior, read `references/xrd-workflow.md`.
- For FTIR workflow behavior, read `references/ftir-workflow.md`.
- For UV-Vis workflow behavior, read `references/uv-vis-workflow.md`.
- For XPS workflow behavior, read `references/xps-workflow.md`.
- For electrochemistry workflow behavior, read `references/electrochemistry-workflow.md`.
- For thermal workflow behavior, read `references/thermal-workflow.md`.
- For SEM/TEM/microscopy image data, read `references/image-data-workflow.md`.
- For scientific figures, templates, batches, material assignments, and review-gated memory, read the corresponding reference file in `references/`.
