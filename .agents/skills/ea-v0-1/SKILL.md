---
name: ea-v0-1
description: User-facing EAv0.1 / eav0.1 / EA v0.1 materials-research assistant. Use to initialize or continue a real local EA project, review-gate experiment logs, import user-provided raw data as read-only copies, run confirmed Raman v0.1 processing, generate Chinese Raman reports, and maintain memory/provenance boundaries. Do not run the bundled public test-case demo unless the user explicitly asks for a demo, test, or validation run.
user-invocable: true
---

# EAv0.1 User Skill

## When To Use

Use EAv0.1 when the user wants a local, single-project scientific assistant for materials research, especially MoS2 CVD experiment records and Raman data analysis.

Use this skill for:

- Initializing a real user EA project workspace.
- Continuing work in an existing EA project workspace.
- Structuring user-provided natural-language experiment logs before user review.
- Saving confirmed experiment records, reviews, and provenance.
- Importing user-provided raw Raman/PL files as controlled read-only copies.
- Running Raman v0.1 inspection, confirmed processing, plots, peak tables, metadata, and Chinese reports.
- Keeping suggestions, decisions, progress, confirmed findings, open items, and provenance separated.

Do not use this skill for Web/UI, multi-project management, hidden evaluation, automatic experimental decisions, automatic scientific conclusions, or full AFM/PL analysis.

## Hard Boundaries

- Default to real user data and the user's chosen local workspace.
- Do not run the bundled public demo by default.
- Run `scripts/run_public_demo.py` only when the user explicitly asks for a demo, test1, smoke test, validation, or to reproduce the public test-case.
- Never read hidden truth, evaluator-only answer keys, or old combined test files.
- Use `工作指南/test_cases/test-case-001/public/` only for explicit developer/demo validation.
- Never modify raw instrument files.
- Never write processed outputs under `raw/`.
- Never skip review gates for experiment logs, Raman columns, Raman parameters, decisions, progress, or confirmed findings.
- Never turn an EA suggestion into a user decision or progress event.
- Never write unconfirmed interpretation or hypothesis into confirmed findings.

## Default Codex Behavior

When the user says things like "use eav0.1", "start EA v0.1", "initialize my EA project", or "analyze my Raman data", treat it as a real user workflow, not as a demo request.

1. Identify the EA implementation repository:
   - If the current directory contains `src/ea` and `pyproject.toml` with package name `ea-v0-1`, use the current directory.
   - Otherwise use `/Users/geecoe/Documents/EAv0.1-build` as the installed implementation repository.
   - If the implementation repository has moved, use the `EA_V0_1_REPO` environment variable to locate it.
2. Identify the target user workspace:
   - If the user gives a path, use that path.
   - If the current directory already has `EA_PROJECT.md`, treat it as the active EA workspace.
   - If no EA workspace exists, initialize one only after collecting the required project fields.
3. Collect only missing required fields for initialization:
   - project name
   - research direction
   - material system
   - experiment type
   - workspace path
4. For experiment logs, produce a review-gated draft and ask the user to confirm before saving.
5. For raw files, import only user-supplied local file paths. Preserve the original files and write controlled read-only copies under the EA workspace.
6. For Raman processing, first inspect the file, show the candidate x/y columns, unit, warnings, and default processing parameters, then wait for explicit user confirmation.
7. Generate Chinese draft reports only after confirmed processing. Do not add next-step suggestions unless the user asks for them.

## User Project Initialization

From the repository root:

```bash
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/ea init /path/to/user-ea-project \
  --name "user project name" \
  --direction "user research direction" \
  --material "MoS2" \
  --experiment-type "CVD growth and Raman characterization"
```

This creates the local EA workspace directories, `EA_PROJECT.md`, and `PROJECT_RULE_CARD.md`. Rule-card key items remain draft/review-gated until explicitly confirmed by the user.

## Core Workflow

1. **Experiment logs**: use `ea.experiments.structure_experiment_log()` to produce a `needs_user_review` draft. Save with `save_confirmed_experiment()` only after a clear confirmation such as `可以，保存`.
2. **Samples**: use `ea.samples.save_sample_record()` after the sample identity/quality basis is traceable; use `recommend_raman_candidates()` for source-labelled candidates.
3. **Raw import**: use `ea.raw_import.import_raw_file()` to copy raw data into `raw/{type}/{characterization_id}/`, write SHA-256 metadata, and preserve duplicate alias or `needs_review` conflict status.
4. **Raman**: use `ea.raman.inspect_spectrum_file()` first. Process only with real confirmed ReviewRecords for x/y columns and processing parameters.
5. **Reports**: use `ea.reports.generate_raman_report()` after processing. Reports are Chinese drafts and default to no next-step suggestions.
6. **Memory/provenance**: use `ea.memory` functions only with confirmed reviews where required. Suggestions stay in `suggestions/`; explicit decisions go to `memory/decision-log.md`; progress goes to `progress/`; confirmed findings require sources, provenance, and review.

## Real Data Raman Flow

Use this flow for user-provided Raman data:

1. Ensure the EA workspace exists.
2. Import the raw file with `ea.raw_import.import_raw_file()`.
3. Inspect the controlled raw copy with `ea.raman.inspect_spectrum_file()`.
4. Present the inspection result to the user:
   - file kind
   - candidate x/y columns
   - candidate x unit
   - warnings
   - default processing parameters
5. Ask for explicit confirmation before writing review records.
6. Process with `ea.raman.process_raman_result()`.
7. Generate the Chinese report with `ea.reports.generate_raman_report()`.
8. Return the report, plot, processed CSV, peak table, metadata, reviews, and provenance paths.

## Developer Demo Only

The bundled public test-case demo is for development validation only. It is not the default user workflow.

Run it from the repository root only when the user explicitly asks for a demo/test/validation run:

```bash
.venv/bin/python .agents/skills/ea-v0-1/scripts/run_public_demo.py \
  --workspace /tmp/ea-v0-1-public-demo \
  --force
```

The demo uses only:

```text
工作指南/test_cases/test-case-001/public/
```

It prints a JSON summary. The generated Raman report path is in `report_path`, typically:

```text
/tmp/ea-v0-1-public-demo/reports/report-YYYYMMDD-NNN.md
```

The Raman figure, processed CSV, peak table, and metadata are under:

```text
/tmp/ea-v0-1-public-demo/processed/{sample_id}/raman/{raman_result_id}/
```

## Validation

After changes to the skill wrapper or core calls, run:

```bash
.venv/bin/python -m pytest tests/test_skill_wrapper.py -q
```

Full v0.1 validation:

```bash
.venv/bin/python -m pytest -q
```
