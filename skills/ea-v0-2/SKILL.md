---
name: ea-v0-2
description: Local-first Experimental Assistant v0.2 for materials-research projects. Use when Codex needs to initialize or continue an EA project, structure experiment logs, import raw characterization data, run review-gated Raman, PL, XRD, FTIR, UV-Vis, XPS, electrochemistry, or thermal analysis, generate editable processing-parameter or batch-manifest templates, run batch characterization manifests, export or verify checksummed report/batch bundles with linked figures/source data/references/provenance, inspect built-in material assignment records, create traceable reports/figures/references, build report-memory traceability views, manage local literature-library state, validate EA child-skill manifests, run public-release smoke checks, generate, verify, optionally sign repository release manifests/packages, produce distribution checklists with user-managed keys when supplied, or preserve project memory/provenance without assuming developer-machine paths or accounts.
---

# EA v0.2

## Overview

EA is a local-first research workspace for experimental scientists. It keeps project records, raw data, processed results, figures, reports, literature state, memory, review records, and provenance linked so later agents can reconstruct what happened.

Do not assume developer-machine Zotero, browser, institution, cache, or test paths. Public-user initialization must ask for or explicitly disable environment-specific settings.

Scientific caution means evidence layering, not silence. If project context and references are clear, EA may proactively gather, look up, and discuss source-backed parameters, assignments, model windows, or interpretation candidates from built-in libraries, registered references, local literature, public databases, user-provided sources, or user-confirmed/agent-led search workflows. Do not require every numeric value to be typed by the user; instead preserve source, applicability, confidence, review state, and provenance, and never silently apply values that change processing or conclusions. A no-live-lookup or no-auto-application boundary on a deterministic command is not a ban on source-backed assistant work; it means lookup, source registration, report citation, processing-parameter use, and memory commitment remain explicit and traceable steps.

## Default Workflow

1. Read the project root files first: `EA_PROJECT.md`, `PROJECT_RULE_CARD.md`, `.ea/project_config.yml`, `progress/`, `memory/`, `provenance/`, and relevant indices.
2. If no project exists, run or emulate `ea init-project` and ask only for settings that affect the next work. Keep Zotero, browser, institution, and cache settings disabled or null unless the user provides them. If literature is not enabled at initialization, read the generated `open-items/*literature*` decision record and ask the user whether to deploy a local literature library before broad literature work.
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
ea trace view /path/to/ea-project
ea export report-bundle /path/to/ea-project --report-id rpt-mos2-mica-cvd-20260630-001 --include-trace --zip
ea export batch-bundle /path/to/ea-project --batch-id batch-20260630-001 --include-trace --zip
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
ea raw import /path/to/ea-project /path/to/raw-ftir.txt --characterization-type ftir --sample-ref sample-001 --experiment-ref exp-001
ea ftir inspect /path/to/ea-project raw/ftir/char-20260630-001/raw-ftir.txt
ea review add /path/to/ea-project --target-type ftir_columns --target-ref raw/ftir/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "x=wavenumber, y=absorbance, unit=cm^-1, signal_mode=absorbance"
ea review add /path/to/ea-project --target-type ftir_parameters --target-ref raw/ftir/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default FTIR parameters confirmed"
ea ftir process /path/to/ea-project --metadata raw/ftir/char-20260630-001/metadata.yml --x-column wavenumber --y-column absorbance --x-unit cm^-1 --signal-mode absorbance --column-review-ref review-20260630-007 --parameter-review-ref review-20260630-008 --sample-ref sample-001
ea ftir report /path/to/ea-project --metadata processed/sample-001/ftir/res-project-ftir-20260630-001/ftir_metadata.yml --sample-ref sample-001 --experiment-ref exp-001 --assignment-suggestion suggestions/ftir/suggestion-20260630-001/ftir_assignment_suggestions.yml
ea ftir build-assignment-packet /path/to/ea-project
ea ftir build-assignment-packet /path/to/ea-project --builtin-library generic_materials --include-candidate ftir-builtin-carbonyl-co-stretching-generic
ea ftir build-assignment-packet /path/to/ea-project --library-file project_ftir_assignment_library.yml
ea ftir build-assignment-packet /path/to/ea-project --literature-manifest literature/confirmed_ftir_source_candidates.yml
ea ftir suggest-assignments /path/to/ea-project --metadata processed/sample-001/ftir/res-project-ftir-20260630-001/ftir_metadata.yml --source-file suggestions/ftir/source-packets/ftir_assignment_source_packet-20260630-001.yml
ea ftir prepare-review /path/to/ea-project --suggestion suggestions/ftir/suggestion-20260630-001/ftir_assignment_suggestions.yml
ea review add /path/to/ea-project --target-type ftir_assignment_suggestions --target-ref suggestions/ftir/suggestion-20260630-001/ftir_assignment_suggestions.yml --user-response "可以，保存" --reviewed-content "reviewed FTIR assignment suggestion candidates"
ea ftir propose-memory /path/to/ea-project --suggestion suggestions/ftir/suggestion-20260630-001/ftir_assignment_suggestions.yml --review-ref review-20260630-009
ea raw import /path/to/ea-project /path/to/raw-uv-vis.txt --characterization-type uv_vis --sample-ref sample-001 --experiment-ref exp-001
ea uv-vis inspect /path/to/ea-project raw/uv_vis/char-20260630-001/raw-uv-vis.txt
ea review add /path/to/ea-project --target-type uv_vis_columns --target-ref raw/uv_vis/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "x=wavelength_nm, y=absorbance, unit=nm, signal_mode=absorbance"
ea review add /path/to/ea-project --target-type uv_vis_parameters --target-ref raw/uv_vis/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default UV-Vis parameters confirmed"
ea uv-vis process /path/to/ea-project --metadata raw/uv_vis/char-20260630-001/metadata.yml --x-column wavelength_nm --y-column absorbance --x-unit nm --signal-mode absorbance --column-review-ref review-20260630-009 --parameter-review-ref review-20260630-010 --sample-ref sample-001
ea uv-vis report /path/to/ea-project --metadata processed/sample-001/uv_vis/res-project-uv-vis-20260630-001/uv_vis_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
ea raw import /path/to/ea-project /path/to/raw-xps.txt --characterization-type xps --sample-ref sample-001 --experiment-ref exp-001
ea xps inspect /path/to/ea-project raw/xps/char-20260630-001/raw-xps.txt
ea review add /path/to/ea-project --target-type xps_columns --target-ref raw/xps/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "x=binding_energy_eV, y=intensity, unit=eV"
ea review add /path/to/ea-project --target-type xps_calibration --target-ref raw/xps/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "C 1s reference at 284.8 eV; energy_shift_eV=0.0"
ea review add /path/to/ea-project --target-type xps_parameters --target-ref raw/xps/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default XPS parameters confirmed"
ea xps build-source-packet /path/to/ea-project --builtin-library generic_xps_parameters --output suggestions/xps/source-packets/xps_parameter_source_packet.yml
ea xps build-source-packet /path/to/ea-project --builtin-library oxide_o1s_binding_energy --suggestion-type binding_energy_candidate --output suggestions/xps/source-packets/xps_o1s_oxide_source_packet.yml
ea xps build-source-packet /path/to/ea-project --literature-manifest literature/confirmed_xps_source_candidates.yml --output suggestions/xps/source-packets/xps_parameter_source_packet.yml
ea references register-seeds /path/to/ea-project --source-packet suggestions/xps/source-packets/xps_parameter_source_packet.yml
ea xps suggest-parameters /path/to/ea-project --source-file suggestions/xps/source-packets/xps_parameter_source_packet.yml --related-record raw/xps/char-20260630-001/metadata.yml
ea xps prepare-review /path/to/ea-project --suggestion suggestions/xps/suggestion-20260630-001/xps_parameter_suggestions.yml
ea review add /path/to/ea-project --target-type xps_parameter_suggestions --target-ref suggestions/xps/suggestion-20260630-001/xps_parameter_suggestions.yml --user-response "可以，保存" --reviewed-content "reviewed XPS parameter suggestion candidates"
ea xps propose-memory /path/to/ea-project --suggestion suggestions/xps/suggestion-20260630-001/xps_parameter_suggestions.yml --review-ref review-20260630-014
ea xps process /path/to/ea-project --metadata raw/xps/char-20260630-001/metadata.yml --x-column binding_energy_eV --y-column intensity --x-unit eV --energy-shift-ev 0.0 --calibration-reference "C 1s 284.8 eV user-confirmed reference" --column-review-ref review-20260630-011 --calibration-review-ref review-20260630-012 --parameter-review-ref review-20260630-013 --sample-ref sample-001
ea xps report /path/to/ea-project --metadata processed/sample-001/xps/res-project-xps-20260630-001/xps_metadata.yml --sample-ref sample-001 --experiment-ref exp-001 --parameter-suggestion suggestions/xps/suggestion-20260630-001/xps_parameter_suggestions.yml
ea raw import /path/to/ea-project /path/to/raw-electrochemistry.txt --characterization-type electrochemistry --sample-ref sample-001 --experiment-ref exp-001
ea electrochemistry inspect /path/to/ea-project raw/electrochemistry/char-20260630-001/raw-electrochemistry.txt
ea review add /path/to/ea-project --target-type electrochemistry_columns --target-ref raw/electrochemistry/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "x=potential_V, y=current_mA, x_unit=V, current_unit=mA, mode=cv"
ea review add /path/to/ea-project --target-type electrochemistry_context --target-ref raw/electrochemistry/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "electrode/electrolyte/reference-electrode/protocol confirmed"
ea review add /path/to/ea-project --target-type electrochemistry_parameters --target-ref raw/electrochemistry/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default electrochemistry parameters confirmed"
ea electrochemistry process /path/to/ea-project --metadata raw/electrochemistry/char-20260630-001/metadata.yml --x-column potential_V --y-column current_mA --x-unit V --current-unit mA --measurement-mode cv --context-summary "user-confirmed electrode/electrolyte/reference/protocol" --electrode-area-cm2 0.196 --column-review-ref review-20260630-014 --context-review-ref review-20260630-015 --parameter-review-ref review-20260630-016 --sample-ref sample-001
ea electrochemistry report /path/to/ea-project --metadata processed/sample-001/electrochemistry/res-project-electrochemistry-20260630-001/electrochemistry_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
ea raw import /path/to/ea-project /path/to/raw-tga.txt --characterization-type thermal_analysis --sample-ref sample-001 --experiment-ref exp-001
ea thermal inspect /path/to/ea-project raw/thermal_analysis/char-20260630-001/raw-tga.txt
ea review add /path/to/ea-project --target-type thermal_columns --target-ref raw/thermal_analysis/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "temperature=temperature_C, signal=mass_percent, temperature_unit=C, signal_unit=%, mode=tga"
ea review add /path/to/ea-project --target-type thermal_context --target-ref raw/thermal_analysis/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "temperature program, atmosphere, sample mass, and baseline reviewed"
ea review add /path/to/ea-project --target-type thermal_parameters --target-ref raw/thermal_analysis/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default thermal parameters confirmed"
ea thermal process /path/to/ea-project --metadata raw/thermal_analysis/char-20260630-001/metadata.yml --temperature-column temperature_C --signal-column mass_percent --temperature-unit C --signal-unit % --measurement-mode tga --context-summary "N2 atmosphere; 10 C/min; sample mass and baseline reviewed" --column-review-ref review-20260630-017 --context-review-ref review-20260630-018 --parameter-review-ref review-20260630-019 --sample-ref sample-001
ea thermal report /path/to/ea-project --metadata processed/sample-001/thermal_analysis/res-project-thermal-analysis-20260630-001/thermal_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
ea materials list
ea materials assignments mos2 --method raman
ea materials assignments ws2 --method pl
ea materials assignments hbn --method xrd
ea templates parameters raman --output /path/to/ea-project/templates/raman_parameters.yml
ea templates parameters ftir --output /path/to/ea-project/templates/ftir_parameters.yml
ea templates parameters uv_vis --output /path/to/ea-project/templates/uv_vis_parameters.yml
ea templates parameters xps --output /path/to/ea-project/templates/xps_parameters.yml
ea templates parameters electrochemistry --output /path/to/ea-project/templates/electrochemistry_parameters.yml
ea templates parameters thermal_analysis --output /path/to/ea-project/templates/thermal_parameters.yml
ea templates batch-manifest /path/to/ea-project --method raman --method pl --method xrd --method ftir --method uv_vis --method xps --method electrochemistry --method thermal_analysis --output batch_manifest.yml
ea batch validate /path/to/ea-project batch_manifest.yml
ea batch run /path/to/ea-project batch_manifest.yml
ea literature status /path/to/ea-project
ea literature plan /path/to/ea-project --scope ordinary --access-mode open_access_only
ea literature confirm /path/to/ea-project --selected-top-n 50 --user-response "User confirmed top 50."
ea literature search-public /path/to/ea-project --source crossref --source openalex --source arxiv --max-results 20 --page-limit 1
ea literature rank-candidates /path/to/ea-project --candidates literature/candidate_results.yml --reference-year 2026
ea literature prepare-source-candidates /path/to/ea-project --method ftir --source-items literature/selected_items.yml --confirm-for-source-packet --user-response "User confirmed FTIR source-candidate manifest staging."
ea literature preflight-source-candidates /path/to/ea-project --method ftir --manifest literature/confirmed_ftir_source_candidates.yml
ea literature prepare-source-candidates /path/to/ea-project --method xps --source-items literature/selected_items.yml --confirm-for-source-packet --user-response "User confirmed XPS source-candidate manifest staging."
ea literature preflight-source-candidates /path/to/ea-project --method xps --manifest literature/confirmed_xps_source_candidates.yml
ea literature handoff /path/to/ea-project --literature-thread-id thread-lit-001
ea literature acquisition-request /path/to/ea-project
ea literature institution-access-guide /path/to/ea-project --institution-name "Institution" --access-method library_proxy --access-url https://library.example.edu/login --browser-name Chrome --browser-profile browser-profiles/project
ea literature zotero-bridge /path/to/ea-project --zotero-config config/zotero-codex.json --project-collection "Project collection"
ea literature import-zotero-status /path/to/ea-project --batch-status literature/zotero_codex_batch_status.json --sidecar-verification literature/zotero_codex_sidecars_verify.json
ea literature import-acquisition /path/to/ea-project --manifest literature/acquisition_manifest.yml
ea literature reconcile-acquisition /path/to/ea-project
ea literature render-reconciliation /path/to/ea-project --reconciliation literature/acquisition_reconciliation.yml
ea literature sync-status /path/to/ea-project --update literature/acquisition_status_update.yml
ea add-skills check /path/to/child-skill-manifest.yml
ea add-skills dry-run /path/to/child-skill-manifest.yml --workspace /path/to/ea-project --sample-output /path/to/sample-output.yml
ea add-skills register /path/to/child-skill-manifest.yml --workspace /path/to/ea-project --sample-output /path/to/sample-output.yml
ea image-data record /path/to/ea-project --metadata raw/sem/char-20260630-001/metadata.yml --method sem --description "User-confirmed image notes" --description-review-ref review-20260630-001 --confidence low
ea image-data report /path/to/ea-project --metadata processed/sample-001/sem/res-project-sem-20260630-001/image_metadata.yml --reference-id ref-20260630-001
ea references add /path/to/ea-project --citation "Author A. Title. Journal volume, pages (year)." --doi 10.xxxx/example --url https://doi.org/10.xxxx/example
ea references import-bibtex /path/to/ea-project /path/to/user-exported-references.bib
ea references register-seeds /path/to/ea-project --source-packet suggestions/ftir/source-packets/ftir_assignment_source_packet-20260630-001.yml
ea references validate-report /path/to/ea-project reports/rpt-example.md
ea memory propose /path/to/ea-project --text "Candidate finding..." --source-ref reports/rpt-example.md --provenance-ref prov-20260630-001 --category interpretation --confidence medium
ea memory review /path/to/ea-project --candidate memory/candidates/memcand-20260630-001.md --user-response "可以，保存"
ea memory commit /path/to/ea-project --candidate memory/candidates/memcand-20260630-001.md --review-ref review-20260630-001
ea trace view /path/to/ea-project --focus reports/rpt-example.md
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
ea-release-keygen --private-key /path/to/user-release-private.pem --public-key /path/to/user-release-public.pem
ea-sign-release-package dist/ea-v0-2-0.2.0-abcdef0-release.zip --private-key /path/to/user-release-private.pem --public-key /path/to/user-release-public.pem
ea-verify-release-signature dist/ea-v0-2-0.2.0-abcdef0-release.zip --public-key /path/to/user-release-public.pem
ea-release-checklist
```

The smoke gate prints JSON and runs pytest, EA v0.2 skill validation, CLI help sanity checks, and a portability scan for accidental developer-machine defaults. The release manifest writes package metadata, git state, console scripts, release input checksums, smoke-gate requirements, and public-user boundary notes. The release package writes a deterministic zip plus `.sha256` sidecar containing the manifest and selected release inputs. The verifier checks the sidecar, embedded manifest, and manifest-listed payload checksums. Optional release signing writes a detached `.sig.yml` sidecar using an explicit user-managed Ed25519 keypair. The distribution checklist writes JSON/Markdown summaries of required release commands, artifacts, verification state, optional signature state, and public boundaries. These release checks do not use Zotero, browser profiles, institution login, local literature caches, or implicit developer-machine key paths.

Built-in child-skill manifests live in `skill-registry/builtins/` and are indexed by `skill-registry/index.yml`. Treat Raman, PL, XRD, FTIR, UV-Vis, XPS, electrochemistry, thermal analysis, image-data, scientific-figure style, and local-literature-library entries as concrete initial workflows. The literature workflow covers initialization decisions, planning, confirmation, explicit public metadata search, supplied-candidate ranking, FTIR/XPS source-candidate manifest preparation and preflight, handoff/request generation, import, and status sync; Zotero, browser, institution login, and PDF acquisition still run only after user confirmation in a dedicated or explicit workflow. Source-candidate manifest helpers are local deterministic staging only: fill candidate fields and run preflight before using the confirmed manifest with `ea ftir build-assignment-packet --literature-manifest ...` or `ea xps build-source-packet --literature-manifest ...`.

Healthcheck and evaluator reports are the local handoff gate. They audit batch run records under `processed/batches/` and require material assignments with `peak_analysis.assigned_features` to preserve `assignment_source` at result and feature level. Use `ea trace view` when the user or a future agent needs a compact YAML/Markdown map from a report or suggestion to figures, source packets, review packages, ReviewRecords, registered references, reference seeds, built-in/source-library refs, provenance, memory candidates, and committed memory. Trace views are read-only audit artifacts except for their own files under `traceability/`; they do not create reviews, commit memory, register references, inject citations, or prove scientific conclusions.

Template commands write editable YAML only. They do not create review records, confirm columns/parameters, or make batch manifests valid until the user supplies real metadata and review refs.

Report bundle export is read-only for analysis state. It copies one indexed report plus linked figures, source data, result metadata, references, local reference files, and provenance into `exports/report-bundles/{report_id}` for handoff. Use `--include-trace` when the handoff should include focused traceability YAML/Markdown for the exported report. Batch bundle export copies one indexed batch run, its batch records, batch provenance, and nested per-report bundles into `exports/batch-bundles/{batch_id}`; `--include-trace` passes focused trace views into nested report bundles. Each bundle writes `bundle_checksums.yml`; use `--zip` or `--zip-output` when a portable archive and `.zip.sha256` sidecar should be created from the same bundle. Use `verify-bundle` and `verify-archive` after copying or before handoff.

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
- For batch Raman/PL/XRD/FTIR/UV-Vis/XPS/electrochemistry/thermal execution, read `references/batch-workflow.md`.
- For literature-library deployment, read `references/local-literature-library.md`.
- For Raman v0.2 behavior, read `references/raman-workflow.md`.
- For PL v0.2 behavior, read `references/pl-workflow.md`.
- For XRD v0.2 behavior, read `references/xrd-workflow.md`.
- For FTIR v0.2 behavior, read `references/ftir-workflow.md`.
- For UV-Vis v0.2 behavior, read `references/uv-vis-workflow.md`.
- For XPS v0.2 behavior, read `references/xps-workflow.md`.
- For electrochemistry v0.2 behavior, read `references/electrochemistry-workflow.md`.
- For thermal analysis v0.2 behavior, read `references/thermal-workflow.md`.
- For SEM/TEM/optical microscopy image data, read `references/image-data-workflow.md`.
- For review-gated durable project memory, read `references/memory-workflow.md`.

## Scripts

Repository scripts live outside the skill folder. Use `scripts/public_release_smoke.py` for release checks, `scripts/build_release_manifest.py` for release metadata, `scripts/build_release_package.py` for the portable release zip, `scripts/verify_release_package.py` for zip verification, `scripts/build_packaged_example_project.py` to regenerate `examples/public-raman-project/`, the release-signature scripts for optional user-managed detached signatures, and `scripts/build_distribution_checklist.py` for final handoff checklist artifacts. They are local-only and should not require user-specific Zotero, browser, institution, cache, or key settings unless the user explicitly supplies them.
