# EA v0.9.7 CLI Command Index

Use this reference only when the task needs concrete command examples. The top-level skill file stays compact so routine EA use does not load the full command catalogue.

## Setup

```bash
ea version
ea mode
ea --mode consult status /path/to/ea-project
ea --mode audit diagnostics collect /path/to/ea-project
ea capabilities
ea capabilities --maturity beta --json
ea diagnostics collect /path/to/ea-project
ea diagnostics collect /path/to/ea-project --output exports/diagnostics/ea-diagnostics.json --log logs/selected.log --debug-json
ea draft stage /path/to/ea-project --source /path/to/generated-draft.md --target reports/final-report.md --yes
ea review add /path/to/ea-project --target-type draft_promotion --target-ref drafts/draft-YYYYMMDD-001/draft.yml --user-response "confirmed" --reviewed-content "promote reviewed draft" --confirm
ea draft promote /path/to/ea-project --draft-id draft-YYYYMMDD-001 --review-ref review-YYYYMMDD-001 --yes
ea codex install-skill
ea onboarding post-install --event install --lang zh
ea install-check
ea init-project /path/to/ea-project --name "Project name" --slug project-slug --direction "Research direction" --material "Material" --experiment-type "Experiment type"
ea config doctor /path/to/ea-project
ea healthcheck /path/to/ea-project
ea eval project /path/to/ea-project
ea brief project /path/to/ea-project
ea brief project /path/to/ea-project --json
```

## Review

```bash
ea review add /path/to/ea-project --target-type raman_columns --target-ref raw/raman/char-YYYYMMDD-001/metadata.yml --user-response "confirmed" --reviewed-content "x=col_0, y=col_1, unit=cm^-1" --confirm
ea review promote /path/to/ea-project --review-ref review-YYYYMMDD-001 --user-response "confirmed for reuse"
```

## Working Memory

```bash
ea memory refresh-project /path/to/ea-project
ea memory show-project /path/to/ea-project
ea memory propose /path/to/ea-project --text "Candidate finding..." --source-ref reports/rpt-example.md --provenance-ref prov-YYYYMMDD-001 --category interpretation --confidence medium
ea memory review /path/to/ea-project --candidate memory/candidates/memcand-YYYYMMDD-001.md --user-response "confirmed"
ea memory commit /path/to/ea-project --candidate memory/candidates/memcand-YYYYMMDD-001.md --review-ref review-YYYYMMDD-001
```

## Literature

```bash
ea literature status /path/to/ea-project
ea literature setup-preflight /path/to/ea-project --lang zh
ea literature plan /path/to/ea-project --scope ordinary --access-mode open_access_only
ea literature confirm /path/to/ea-project --selected-top-n 50 --user-response "confirmed"
ea literature search-public /path/to/ea-project --source crossref --source openalex --source arxiv --max-results 20 --page-limit 1 --confirm-large-work
ea literature rank-candidates /path/to/ea-project --candidates literature/candidate_results.yml --reference-year 2026
ea literature acquisition-request /path/to/ea-project --confirm-large-work
ea literature prepare-source-candidates /path/to/ea-project --method ftir --source-items literature/selected_items.yml --confirm-for-source-packet --user-response "confirmed" --confirm-large-work
ea literature preflight-source-candidates /path/to/ea-project --method ftir --manifest literature/confirmed_ftir_source_candidates.yml
ea literature handoff /path/to/ea-project --literature-thread-id thread-lit-001
ea literature zotero-readiness /path/to/ea-project
ea literature acceptance-checklist /path/to/ea-project
ea literature data-plan /path/to/ea-project --property "electrical conductivity" --kind conductivity --material "two-dimensional materials" --source /path/to/cache-or-searchable.pdf --required-condition temperature --required-condition direction --dataset-id conductivity-pilot --yes
ea literature data-extract /path/to/ea-project --dataset conductivity-pilot --max-sources 10 --yes
ea literature data-review /path/to/ea-project --dataset conductivity-pilot --record rec-source-001-001 --decision accept --note "Verified against page and table." --yes
ea literature data-validate /path/to/ea-project --dataset conductivity-pilot
ea literature data-plot /path/to/ea-project --dataset conductivity-pilot --yes
ea literature data-export /path/to/ea-project --dataset conductivity-pilot --yes
```

## Estimates And Reminders

```bash
ea estimate workflow /path/to/ea-project --workflow literature_acquisition --items 50 --mode standard
ea estimate workflow /path/to/ea-project --workflow literature_data_extraction --items 10 --mode standard
ea estimate workflow /path/to/ea-project --workflow literature_ocr --items 10 --mode standard
ea estimate workflow /path/to/ea-project --workflow literature_digitization --items 10 --mode standard
ea estimate workflow /path/to/ea-project --workflow analysis_report --items 1 --mode full
ea estimate reminders /path/to/ea-project --disable --reason "user requested no large-work reminders"
ea estimate reminders /path/to/ea-project --enable
```

## Characterization

```bash
ea raw import /path/to/ea-project /path/to/raw-spectrum.txt --characterization-type raman --sample-ref sample-001 --experiment-ref exp-001
ea raman inspect /path/to/ea-project raw/raman/char-YYYYMMDD-001/raw-spectrum.txt
ea raman list-assignment-libraries --material mos2 --feature mos2_a1g_like --shift-min-cm1 400 --shift-max-cm1 420
ea raman process /path/to/ea-project --metadata raw/raman/char-YYYYMMDD-001/metadata.yml --x-column col_0 --y-column col_1 --x-unit cm^-1 --column-review-ref review-YYYYMMDD-001 --parameter-review-ref review-YYYYMMDD-002 --sample-ref sample-001
ea raman report /path/to/ea-project --metadata processed/sample-001/raman/res-project-raman-YYYYMMDD-001/raman_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
ea ftir inspect /path/to/ea-project raw/ftir/char-YYYYMMDD-001/raw-ftir.txt
ea ftir list-assignment-libraries --builtin-library generic_materials --assignment-type inorganic_ion --material-scope oxide
ea ftir build-assignment-packet /path/to/ea-project --builtin-library generic_materials
ea references register-seeds /path/to/ea-project --source-packet suggestions/ftir/source-packets/ftir_assignment_source_packet-YYYYMMDD-001.yml
ea ftir process /path/to/ea-project --metadata raw/ftir/char-YYYYMMDD-001/metadata.yml --x-column wavenumber --y-column absorbance --x-unit cm^-1 --signal-mode absorbance --column-review-ref review-YYYYMMDD-001 --parameter-review-ref review-YYYYMMDD-002 --sample-ref sample-001
ea ftir suggest-assignments /path/to/ea-project --metadata processed/sample-001/ftir/res-project-ftir-YYYYMMDD-001/ftir_metadata.yml --source-file suggestions/ftir/source-packets/ftir_assignment_source_packet-YYYYMMDD-001.yml
ea ftir report /path/to/ea-project --metadata processed/sample-001/ftir/res-project-ftir-YYYYMMDD-001/ftir_metadata.yml --assignment-suggestion suggestions/ftir/suggestion-YYYYMMDD-001/ftir_assignment_suggestions.yml
ea ftir propose-memory /path/to/ea-project --suggestion suggestions/ftir/suggestion-YYYYMMDD-001/ftir_assignment_suggestions.yml --review-ref review-YYYYMMDD-003
ea uv-vis inspect /path/to/ea-project raw/uv_vis/char-YYYYMMDD-001/raw-uv-vis.txt
ea uv-vis list-source-libraries --builtin-library generic_optical_interpretation --candidate-type optical_gap_candidate
ea uv-vis build-source-packet /path/to/ea-project --builtin-library generic_optical_interpretation --output suggestions/uv_vis/source-packets/uv_vis_builtin_source_packet.yml
ea uv-vis suggest-interpretations /path/to/ea-project --metadata processed/sample-001/uv_vis/res-project-uv-vis-YYYYMMDD-001/uv_vis_metadata.yml --source-file suggestions/uv_vis/source-packets/uv_vis_source_packet.yml
ea uv-vis prepare-review /path/to/ea-project --suggestion suggestions/uv_vis/suggestion-YYYYMMDD-001/uv_vis_interpretation_suggestions.yml
ea uv-vis report /path/to/ea-project --metadata processed/sample-001/uv_vis/res-project-uv-vis-YYYYMMDD-001/uv_vis_metadata.yml --interpretation-suggestion suggestions/uv_vis/suggestion-YYYYMMDD-001/uv_vis_interpretation_suggestions.yml --interpretation-review-ref review-YYYYMMDD-003
ea uv-vis propose-memory /path/to/ea-project --suggestion suggestions/uv_vis/suggestion-YYYYMMDD-001/uv_vis_interpretation_suggestions.yml --review-ref review-YYYYMMDD-003
ea uv-vis compare-replicates /path/to/ea-project --metadata processed/sample-001/uv_vis/res-project-uv-vis-YYYYMMDD-001/uv_vis_metadata.yml --metadata processed/sample-002/uv_vis/res-project-uv-vis-YYYYMMDD-002/uv_vis_metadata.yml --comparison-label "replicate set" --feature-match-review-ref review-YYYYMMDD-004
ea xps inspect /path/to/ea-project raw/xps/char-YYYYMMDD-001/raw-xps.txt
ea xps list-parameter-libraries --builtin-library generic_xps_parameters --suggestion-type binding_energy_candidate
ea xps build-source-packet /path/to/ea-project --builtin-library oxide_o1s_binding_energy --output suggestions/xps/source-packets/xps_o1s_source_packet.yml
ea xps suggest-parameters /path/to/ea-project --source-file suggestions/xps/source-packets/xps_parameter_source_packet.yml
ea xps process /path/to/ea-project --metadata raw/xps/char-YYYYMMDD-001/metadata.yml --x-column binding_energy_eV --y-column intensity --x-unit eV --column-review-ref review-YYYYMMDD-001 --parameter-review-ref review-YYYYMMDD-002 --sample-ref sample-001
ea xps report /path/to/ea-project --metadata processed/sample-001/xps/res-project-xps-YYYYMMDD-001/xps_metadata.yml --parameter-suggestion suggestions/xps/suggestion-YYYYMMDD-001/xps_parameter_suggestions.yml
ea xps propose-memory /path/to/ea-project --suggestion suggestions/xps/suggestion-YYYYMMDD-001/xps_parameter_suggestions.yml --review-ref review-YYYYMMDD-003
ea electrochemistry inspect /path/to/ea-project raw/electrochemistry/char-YYYYMMDD-001/raw-electrochemistry.txt
ea electrochemistry process /path/to/ea-project --metadata raw/electrochemistry/char-YYYYMMDD-001/metadata.yml --x-column potential_V --y-column current_mA --x-unit V --current-unit mA --measurement-mode cv --column-review-ref review-YYYYMMDD-001 --context-review-ref review-YYYYMMDD-002 --parameter-review-ref review-YYYYMMDD-003 --sample-ref sample-001
ea thermal inspect /path/to/ea-project raw/thermal/char-YYYYMMDD-001/raw-thermal.txt
ea thermal process /path/to/ea-project --metadata raw/thermal/char-YYYYMMDD-001/metadata.yml --temperature-column temperature_C --signal-column mass_percent --temperature-unit C --signal-unit percent --measurement-mode tga --column-review-ref review-YYYYMMDD-001 --context-review-ref review-YYYYMMDD-002 --parameter-review-ref review-YYYYMMDD-003 --sample-ref sample-001
```

Use the matching `pl`, `xrd`, `ftir`, `uv-vis`, `xps`, `electrochemistry`, `thermal`, and `image-data` command groups for other methods. Read the corresponding workflow reference before using method-specific source packets, optional correction records, component fitting, electrochemical metrics, or thermal transition assignment.

## Reports, Traceability, And Export

```bash
ea trace index /path/to/ea-project
ea trace focus /path/to/ea-project reports/rpt-project-YYYYMMDD-001.md --depth 2
ea trace view /path/to/ea-project
ea trace lookup /path/to/ea-project rpt-project-YYYYMMDD-001 --json-full
ea trace export /path/to/ea-project --full
ea export report-html /path/to/ea-project --report-id rpt-project-YYYYMMDD-001
ea export report-bundle /path/to/ea-project --report-id rpt-project-YYYYMMDD-001 --include-trace --zip
ea export batch-bundle /path/to/ea-project --batch-id batch-YYYYMMDD-001 --include-trace --zip
ea export verify-bundle /path/to/ea-project/exports/report-bundles/rpt-project-YYYYMMDD-001
ea export verify-archive /path/to/ea-project/exports/report-bundles/rpt-project-YYYYMMDD-001.zip
```

Default `ea brief project` and `ea trace ...` output is intentionally compact. Use `--json` for compact structured output and `--json-full` only when an automation needs the full trace/brief object in stdout.

## Release

```bash
python3 scripts/check_version_identity.py
python3 scripts/check_downloaded_skill_instructions.py
ea-public-release-smoke
python3 -m build
ea-release-reproducibility
ea-release-artifact-smoke
ea-release-supply-chain
ea-release-manifest
ea-release-package
ea-verify-release-package dist/experimental-assistant-0.9.7-COMMIT-release.zip
ea-release-checklist
```

Optional signing uses only explicit user-managed key paths:

```bash
ea-release-keygen --private-key /path/to/user-release-private.pem --public-key /path/to/user-release-public.pem
ea-sign-release-package dist/experimental-assistant-0.9.7-COMMIT-release.zip --private-key /path/to/user-release-private.pem --public-key /path/to/user-release-public.pem
ea-verify-release-signature dist/experimental-assistant-0.9.7-COMMIT-release.zip --public-key /path/to/user-release-public.pem
```
