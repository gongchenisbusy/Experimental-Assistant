---
name: ea-v0-2
description: Local-first Experimental Assistant v0.2 for materials-research projects. Use when Codex needs to initialize or continue an EA project, structure experiment logs, import raw characterization data, run review-gated Raman, PL, or XRD analysis, generate editable processing-parameter or batch-manifest templates, run batch characterization manifests, export or verify checksummed report/batch bundles with linked figures/source data/references/provenance, inspect built-in material assignment records, create traceable reports/figures/references, manage local literature-library state, validate EA child-skill manifests, run public-release smoke checks, generate or verify repository release manifests/packages, or preserve project memory/provenance without assuming developer-machine paths or accounts.
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
6. Run `ea healthcheck` and `ea eval project` before handoff or public-demo readiness checks; these now include batch records and material-assignment traceability in addition to raw/report/figure/reference/provenance checks.
7. For repository-level public-release checks, run `ea-public-release-smoke` or `python3 scripts/public_release_smoke.py`, then generate and verify release artifacts with `ea-release-manifest`, `ea-release-package`, `ea-verify-release-package`, or their script equivalents.
8. Put questions that affect future work or scientific judgement at the end of the response.

## CLI Quick Start

Use the repository package when available:

```bash
ea init-project /path/to/ea-project --name "MoS2 mica CVD" --slug mos2-mica-cvd --direction "single-layer MoS2 on mica" --material MoS2 --experiment-type "CVD growth and Raman characterization"
ea config doctor /path/to/ea-project
ea healthcheck /path/to/ea-project
ea eval project /path/to/ea-project
ea export report-bundle /path/to/ea-project --report-id rpt-mos2-mica-cvd-20260630-001 --zip
ea export batch-bundle /path/to/ea-project --batch-id batch-20260630-001 --zip
ea export verify-bundle /path/to/ea-project/exports/report-bundles/rpt-mos2-mica-cvd-20260630-001
ea export verify-archive /path/to/ea-project/exports/report-bundles/rpt-mos2-mica-cvd-20260630-001.zip
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
ea raw import /path/to/ea-project /path/to/raw-xrd.txt --characterization-type xrd --sample-ref sample-001 --experiment-ref exp-001
ea xrd inspect /path/to/ea-project raw/xrd/char-20260630-001/raw-xrd.txt
ea review add /path/to/ea-project --target-type xrd_columns --target-ref raw/xrd/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "x=two_theta, y=intensity, unit=2theta_deg"
ea review add /path/to/ea-project --target-type xrd_parameters --target-ref raw/xrd/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default XRD parameters confirmed"
ea xrd process /path/to/ea-project --metadata raw/xrd/char-20260630-001/metadata.yml --x-column two_theta --y-column intensity --x-unit 2theta_deg --column-review-ref review-20260630-005 --parameter-review-ref review-20260630-006 --sample-ref sample-001
ea xrd report /path/to/ea-project --metadata processed/sample-001/xrd/res-project-xrd-20260630-001/xrd_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
ea materials list
ea materials assignments mos2 --method raman
ea templates parameters raman --output /path/to/ea-project/templates/raman_parameters.yml
ea templates batch-manifest /path/to/ea-project --method raman --method pl --method xrd --output batch_manifest.yml
ea batch validate /path/to/ea-project batch_manifest.yml
ea batch run /path/to/ea-project batch_manifest.yml
ea literature status /path/to/ea-project
ea literature plan /path/to/ea-project --scope ordinary --access-mode open_access_only
ea literature confirm /path/to/ea-project --selected-top-n 50 --user-response "User confirmed top 50."
ea literature handoff /path/to/ea-project --literature-thread-id thread-lit-001
ea literature acquisition-request /path/to/ea-project
ea literature import-acquisition /path/to/ea-project --manifest literature/acquisition_manifest.yml
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

Repository release smoke check:

```bash
ea-public-release-smoke --dry-run
ea-public-release-smoke
ea-release-manifest
ea-release-package
ea-verify-release-package dist/ea-v0-2-0.2.0-abcdef0-release.zip
```

The smoke gate prints JSON and runs pytest, EA v0.2 skill validation, CLI help sanity checks, and a portability scan for accidental developer-machine defaults. The release manifest writes package metadata, git state, console scripts, release input checksums, smoke-gate requirements, and public-user boundary notes. The release package writes a deterministic zip plus `.sha256` sidecar containing the manifest and selected release inputs. The verifier checks the sidecar, embedded manifest, and manifest-listed payload checksums. These release checks do not use Zotero, browser profiles, institution login, or local literature caches.

Built-in child-skill manifests live in `skill-registry/builtins/` and are indexed by `skill-registry/index.yml`. Treat Raman, PL, XRD, image-data, and scientific-figure style entries as concrete initial workflows; treat FTIR, UV-Vis, XPS, electrochemistry, thermal analysis, and literature-library entries as EA contract boundaries until their implementation services exist.

Healthcheck and evaluator reports are the local handoff gate. They audit batch run records under `processed/batches/` and require material assignments with `peak_analysis.assigned_features` to preserve `assignment_source` at result and feature level.

Template commands write editable YAML only. They do not create review records, confirm columns/parameters, or make batch manifests valid until the user supplies real metadata and review refs.

Report bundle export is read-only for analysis state. It copies one indexed report plus linked figures, source data, result metadata, references, local reference files, and provenance into `exports/report-bundles/{report_id}` for handoff. Batch bundle export copies one indexed batch run, its batch records, batch provenance, and nested per-report bundles into `exports/batch-bundles/{batch_id}`. Each bundle writes `bundle_checksums.yml`; use `--zip` or `--zip-output` when a portable archive and `.zip.sha256` sidecar should be created from the same bundle. Use `verify-bundle` and `verify-archive` after copying or before handoff.

## References

- For project structure and workflow, read `references/project-workflow.md`.
- For public-user initialization and forbidden defaults, read `references/public-initialization.md`.
- For child skill manifests and `add-skills`, read `references/module-manifest.md`.
- For report, figure, ID, citation, and confidence standards, read `references/report-figure-reference-standard.md`.
- For scientific figure style infrastructure, read `references/scientific-figure-workflow.md`.
- For evaluator/readiness checks, read `references/evaluator-workflow.md`.
- For repository smoke checks and release manifests, read `references/release-workflow.md`.
- For report bundle export, read `references/export-workflow.md`.
- For editable YAML template generation, read `references/template-workflow.md`.
- For built-in material assignment records, read `references/material-assignment-library.md`.
- For batch Raman/PL/XRD execution, read `references/batch-workflow.md`.
- For literature-library deployment, read `references/local-literature-library.md`.
- For Raman v0.2 behavior, read `references/raman-workflow.md`.
- For PL v0.2 behavior, read `references/pl-workflow.md`.
- For XRD v0.2 behavior, read `references/xrd-workflow.md`.
- For SEM/TEM/optical microscopy image data, read `references/image-data-workflow.md`.
- For review-gated durable project memory, read `references/memory-workflow.md`.

## Scripts

Repository scripts live outside the skill folder. Use `scripts/public_release_smoke.py` for release checks, `scripts/build_release_manifest.py` for release metadata, `scripts/build_release_package.py` for the portable release zip, and `scripts/verify_release_package.py` for zip verification. They are local-only and should not require user-specific Zotero, browser, institution, or cache settings.
