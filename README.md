# EA v0.2 Build

EA v0.2 is the clean implementation workspace for the local-first Experimental Assistant.

Active design references are in `docs/`. The runnable Python core is in `src/ea/`. The agent skill package is in `skills/ea-v0-2/`.

New public users should start with `docs/PUBLIC_ONBOARDING.md`; it gives the shortest path from installation to a first review-gated project without assuming developer-machine Zotero, browser, institution, cache, key, or test paths. A packaged public-safe example project lives in `examples/public-raman-project/`. Use `docs/PROJECT_BUNDLE_VERIFICATION.md` when handing off report or batch export bundles, and `docs/RELEASE_VERIFICATION.md` before installing or redistributing a repository release package.

## Public Setup

EA must initialize projects for unknown users without assuming developer-machine Zotero, browser, institution login, cache, or test paths. Use:

```bash
ea init-project /path/to/ea-project --name "Project name" --slug project-slug --direction "Research direction" --material "Material" --experiment-type "Experiment type"
ea config doctor /path/to/ea-project
ea healthcheck /path/to/ea-project
ea eval project /path/to/ea-project
ea trace view /path/to/ea-project
ea healthcheck examples/public-raman-project
ea eval project examples/public-raman-project --no-write
ea export report-bundle /path/to/ea-project --report-id rpt-project-slug-20260630-001 --include-trace --zip
ea export batch-bundle /path/to/ea-project --batch-id batch-20260630-001 --include-trace --zip
ea export verify-bundle /path/to/ea-project/exports/report-bundles/rpt-project-slug-20260630-001
ea export verify-archive /path/to/ea-project/exports/report-bundles/rpt-project-slug-20260630-001.zip
ea-release-keygen --private-key /path/to/user-release-private.pem --public-key /path/to/user-release-public.pem
ea-sign-release-package dist/ea-v0-2-0.2.0-abcdef0-release.zip --private-key /path/to/user-release-private.pem --public-key /path/to/user-release-public.pem
ea-verify-release-signature dist/ea-v0-2-0.2.0-abcdef0-release.zip --public-key /path/to/user-release-public.pem
ea-release-checklist
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
ea xps process /path/to/ea-project --metadata raw/xps/char-20260630-001/metadata.yml --x-column binding_energy_eV --y-column intensity --x-unit eV --energy-shift-ev 0.0 --calibration-reference "C 1s 284.8 eV user-confirmed reference" --column-review-ref review-20260630-011 --calibration-review-ref review-20260630-012 --parameter-review-ref review-20260630-013 --sample-ref sample-001
ea xps report /path/to/ea-project --metadata processed/sample-001/xps/res-project-xps-20260630-001/xps_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
ea xps build-source-packet /path/to/ea-project --builtin-library generic_xps_parameters --output suggestions/xps/source-packets/xps_parameter_source_packet.yml
ea xps build-source-packet /path/to/ea-project --literature-manifest literature/confirmed_xps_source_candidates.yml --output suggestions/xps/source-packets/xps_parameter_source_packet.yml
ea references register-seeds /path/to/ea-project --source-packet suggestions/xps/source-packets/xps_parameter_source_packet.yml
ea xps suggest-parameters /path/to/ea-project --source-file suggestions/xps/source-packets/xps_parameter_source_packet.yml --related-record raw/xps/char-20260630-001/metadata.yml
ea xps prepare-review /path/to/ea-project --suggestion suggestions/xps/suggestion-20260630-001/xps_parameter_suggestions.yml
ea review add /path/to/ea-project --target-type xps_parameter_suggestions --target-ref suggestions/xps/suggestion-20260630-001/xps_parameter_suggestions.yml --user-response "可以，保存" --reviewed-content "reviewed XPS parameter suggestion candidates"
ea xps propose-memory /path/to/ea-project --suggestion suggestions/xps/suggestion-20260630-001/xps_parameter_suggestions.yml --review-ref review-20260630-014
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
ea add-skills dry-run /path/to/manifest.yml --workspace /path/to/ea-project --sample-output /path/to/sample-output.yml
ea image-data record /path/to/ea-project --metadata raw/sem/char-20260630-001/metadata.yml --method sem --description "User-confirmed image notes" --description-review-ref review-20260630-001 --confidence low
ea references add /path/to/ea-project --citation "Author A. Title. Journal volume, pages (year)." --doi 10.xxxx/example --url https://doi.org/10.xxxx/example
ea references import-bibtex /path/to/ea-project /path/to/user-exported-references.bib
ea references register-seeds /path/to/ea-project --source-packet suggestions/ftir/source-packets/ftir_assignment_source_packet-20260630-001.yml
ea references validate-report /path/to/ea-project reports/rpt-example.md
ea memory propose /path/to/ea-project --text "Candidate finding..." --source-ref reports/rpt-example.md --provenance-ref prov-20260630-001 --category interpretation --confidence medium
ea trace view /path/to/ea-project --focus reports/rpt-example.md
```

Use `ea literature search-public --page-limit N --delay-seconds S --resume` for longer public metadata runs that should write and reuse `literature/public_search_state.yml`.
Use `ea literature prepare-source-candidates` after ranking or literature import when selected literature items should become editable FTIR/XPS source-candidate manifests. It writes `literature/draft_<method>_source_candidates.yml` or, with explicit `--confirm-for-source-packet --user-response`, `literature/confirmed_<method>_source_candidates.yml`; candidate stubs remain disabled until method fields are filled and `include_in_source_packet: true` is set. Use `ea literature preflight-source-candidates` before `ea ftir build-assignment-packet --literature-manifest ...` or `ea xps build-source-packet --literature-manifest ...`. These helpers read local YAML only and do not search, download or parse full text, register references, inject citations, build source packets by themselves, or apply assignments/parameters.
Use `ea literature institution-access-guide` before authenticated acquisition to write `literature/institution_access_guidance.yml` and `.md` with user-supplied institution route, browser/profile, authorization status, safe manual-login steps, and no stored credentials.
Use `ea literature zotero-bridge` after `acquisition-request` to write `literature/zotero_codex_bridge.yml`, `literature/zotero_codex_bridge.md`, and `literature/zotero_codex_settings_request.yml` for a dedicated Zotero-Codex workflow. The bridge emits commands and required user settings; it does not run Zotero, open browsers, resolve DOI pages, download PDFs, or assume local accounts.
Use `ea literature import-zotero-status` after a dedicated Zotero-Codex workflow writes batch status artifacts; it converts status JSON and optional sidecar verification into `literature/acquisition_status_update.yml` and syncs EA project status without running Zotero or downloading files.
Use `ea literature reconcile-acquisition` to write `literature/acquisition_reconciliation.yml` and `literature/acquisition_reconciliation.md`, check whether acquisition/status/library/cache/reference records agree, and include advisory `repair_actions` plus `questions_for_user` for mismatches. Use `ea literature render-reconciliation` to regenerate the Markdown audit view from an existing reconciliation YAML without repairing records.

`ea init-project` writes an `open-items/` literature-library decision record unless `--enable-literature` is supplied. Use `--enable-literature` only when the user explicitly wants a project literature status record created during initialization; all Zotero, browser, cache, proxy/VPN, and institution settings still remain user-supplied.

Enable Zotero, browser assist, literature cache, or institution access only when the user supplies those settings.
BibTeX import uses an explicit user-provided `.bib` export and de-duplicates references by DOI, URL, title, or citation before creating new project records. Source-packet `reference_seeds` can be registered explicitly with `ea references register-seeds`; this creates project reference records only and does not inject citations into reports.
Built-in child-skill manifests live in `skill-registry/builtins/` and are indexed by `skill-registry/index.yml`; Raman, PL, XRD, FTIR, UV-Vis, XPS, electrochemistry, thermal analysis, image-data, scientific-figure style infrastructure, and local-literature-library planning/public-metadata-search/ranking/import/status infrastructure have concrete initial workflows, while other contract placeholders define future module boundaries without claiming full algorithm support. XPS now includes `build-source-packet` for built-in `generic_xps_parameters` seeds, local XPS parameter candidate libraries, editable templates, or user-confirmed literature/source-candidate manifests via `--literature-manifest`, source-backed `suggest-parameters` records under `suggestions/xps/`, grouped review packages via `ea xps prepare-review`, optional `component_quantification` screening from reviewed windows/RSF values, optional `background_model` records for reviewed Shirley/Tougaard/linear/local-minimum choices, optional reviewed linear, Shirley, or Tougaard U2 `background_subtraction` preprocessing columns, optional reviewed `component_fit` screening from user-confirmed regions, peak shapes, initial values, bounds, selected intensity columns, references, caveats, fit-quality thresholds, and reviewed `spin_orbit_constraints` with recorded `parameter_origin`, source summary, applicability notes, and reference IDs when source-backed parameters are used, plus optional reviewed `region_records` for survey/core-level/project-region organization and provenance. The expanded built-in XPS library includes reviewable spin-orbit starter candidates for common materials-analysis core levels including Fe 2p, Si 2p, Cu 2p, Ti 2p, Ni 2p, Co 2p, Zn 2p, Mo 3d, W 4f, S 2p, and P 2p, plus a Tougaard U2-style background starting point; project-local and confirmed-literature packets may add structured `binding_energy_candidate` entries with a chemical-state label, BE center/window, calibration reference, charge-reference assumption, source summary, applicability notes, caveats, confidence, and reference IDs. Built-in/local/confirmed-literature XPS source packets may carry filtered `reference_seeds` and `guidance_reference_ids`; use `ea references register-seeds` explicitly to create project reference records before treating seed-backed suggestions or guidance as report evidence. XPS reports can attach `--parameter-suggestion` records to display advisory source-backed candidate parameters or binding-energy candidates and merge registered suggestion references into the bibliography, and confirmed suggestion records can feed draft method-note or interpretation memory candidates through `ea xps propose-memory`. XPS source packets, review packages, suggestion records, and memory candidates are advisory and never auto-applied; their no-live-lookup command boundary does not prevent EA from preparing source-backed candidates from reviewed literature, built-in seed libraries, local libraries, user-provided sources, or user-confirmed searches. Confirmed-literature manifests are copied only after explicit confirmation metadata and do not run live search/download/full-text parsing, register references, or inject citations by themselves. EA may proactively gather or suggest source-backed endpoint/background/component/bounds/peak-shape, spin-orbit, Tougaard, or binding-energy/chemical-state candidates when project context and references support them, but XPS does not silently apply those values, use unsourced constants, silently calibrate spectra, apply charge correction, claim definitive composition or chemical-state assignment, silently share charge correction, align survey/core-level spectra without review, fit Tougaard parameters without a reviewed protocol, run QUASES/depth-profile modeling, commit memory without the standard memory review/commit flow, or run unreviewed spin-orbit constrained fitting.
Built-in material assignment records live in `src/ea/materials/assignments.yml`; use `ea materials list/show/assignments` to inspect the current MoS2 and WS2 Raman/PL/XRD screening rules, h-BN Raman/XRD screening rules, and their caveats.
Template helpers write editable YAML for processing parameter files and batch manifests. They do not create review records or replace user confirmation.
FTIR templates include disabled-by-default `context_record` settings; enable them only after the user reviews instrument/accessory, atmosphere, sample preparation, background/reference, and correction-note metadata. Context records are metadata/provenance only and do not apply automatic FTIR background/reference correction or prove chemical composition. FTIR also includes `build-assignment-packet` for built-in `generic_materials` seeds, local assignment candidate libraries, editable templates, or user-confirmed literature/source-candidate manifests via `--literature-manifest`, plus source-backed `suggest-assignments` records under `suggestions/ftir/`; the expanded built-in library covers common broad organic bands plus adsorbed water, silanol/Si-O, carbonate, phosphate, sulfate, nitrate, carboxylate, amide, and low-wavenumber metal-oxygen starter candidates for materials projects. These records match reviewed candidate band windows to detected FTIR features, preserve source/applicability/reference metadata, can be summarized as grouped review packages with `ea ftir prepare-review`, can be attached to `ea ftir report` with `--assignment-suggestion`, and can feed draft memory candidates through `ea ftir propose-memory` after a confirmed review. The confirmed-literature manifest path copies only explicitly confirmed candidate metadata and does not perform live search, download or parse articles, register references, inject report citations, auto-apply assignments, or prove composition/functional groups. The review package and memory bridge write advisory artifacts only and never auto-create ReviewRecords, auto-commit confirmed memory, auto-apply assignments, or prove composition/functional groups by themselves. Built-in and confirmed-literature FTIR packets may carry `reference_seeds`; use `ea references register-seeds` to register/replace the cited sources in the project before using suggestions as report evidence.
UV-Vis templates include disabled-by-default `tauc_analysis`, `derivative_analysis`, and `correction_context` settings; enable them only after the user reviews the transform/transition/window, derivative axis, or substrate/reference/background/sample-geometry/diffuse-reflectance metadata. The resulting Tauc/Kubelka-Munk intercepts and derivative extrema are screening records, and correction-context records are metadata/provenance only; they are not definitive band-gap, transition, mechanism, or numeric-correction claims.
Electrochemistry processing supports reviewed `measurement_mode=eis` for two-column Nyquist screening with `x_unit=ohm` and `current_unit=unknown`; the default output is a traceable impedance summary, not an Rct/mechanism claim. Electrochemistry templates also include disabled-by-default `correction_record` settings for reviewed reference-electrode, converted-scale, uncompensated-resistance, and iR-compensation metadata, disabled-by-default `potential_conversion` settings for user-reviewed offset conversion, disabled-by-default `ir_drop_correction` settings for user-reviewed Ru/fraction/sign-convention coordinate correction, disabled-by-default `eis_circuit_fit` settings for user-reviewed series-R-RC screening fits from reviewed frequency/model/initial/bound inputs, disabled-by-default `tafel_analysis` settings for reviewed kinetic-window Tafel/overpotential screening fits, and disabled-by-default `gcd_analysis` settings for reviewed discharge-window capacity/capacitance metrics. Correction records are provenance only; potential conversion and iR drop correction write coordinate columns/records only; EIS circuit-fit, Tafel, and GCD analysis use only reviewed model/window inputs and do not perform automatic model/segment selection, formal performance proof, ranking, stability assessment, or mechanism claims.
Thermal templates include disabled-by-default `baseline_correction` settings for reviewed DSC/DTG linear baseline processing, disabled-by-default `transition_analysis` settings for reviewed DSC Tg/Tm/Tc-style candidate windows, disabled-by-default `transition_assignment` settings for user-confirmed transition interpretation records, and disabled-by-default `context_record` settings for reviewed DSC sign convention, baseline/reference, sample, atmosphere/program, and correction-note metadata. Thermal baseline correction is a numeric processing step, transition screening is candidate extraction inside reviewed windows, transition assignment records preserve user-confirmed interpretation/provenance, and thermal context records are metadata/provenance only; none of these records automatically infers Tg/Tm/Tc, fits kinetics, ranks thermal stability, or proves decomposition/melting/crystallization mechanisms.
Batch characterization records live under `processed/batches/`; `ea batch validate/run` coordinates already-reviewed Raman, PL, XRD, FTIR, UV-Vis, XPS, electrochemistry, and thermal items without guessing columns, calibration, context, mode, temperature program, or parameters. Batch index records, summaries, item result/report refs, review refs, and batch provenance refs are audited by healthcheck.

`ea healthcheck` audits project config, raw hashes, provenance links, figure/report backlinks, registered references, report citation numbering, review-gated memory indices, batch records, and material-assignment traceability.
`ea eval project` wraps healthcheck/config checks and adds deterministic handoff/readiness summaries for figure style/source-data traces, report citations, batch runs, material assignments, and persisted evaluation records under `evaluation/`.
`ea trace view` writes `traceability/project_trace.yml` and `.md` by linking reports, figures, source packets, source-backed suggestion records, review packages, ReviewRecords, provenance, memory candidates, and committed memory. Use `--focus <report-or-record-ref>` to render one connected subgraph. It is a read-only audit view except for its own trace files; it does not mutate reports, create ReviewRecords, commit memory, register references, inject citations, generate source packets/suggestions, or prove scientific conclusions.
`ea export report-bundle` copies one report plus linked figures, source data, result metadata, references, local reference files, and provenance into `exports/report-bundles/` for handoff. Add `--include-trace` to include a focused report traceability YAML/Markdown view inside the bundle. `ea export batch-bundle` copies one batch run plus nested per-report bundles into `exports/batch-bundles/`; with `--include-trace`, each nested report bundle includes its own focused trace view. Each bundle writes `bundle_checksums.yml`; add `--zip` or `--zip-output` when the handoff should include a portable archive plus `.zip.sha256` sidecar. Use `ea export verify-bundle` and `ea export verify-archive` to verify local handoff integrity after copying. For provenance audit and checksum/signature boundaries, read `docs/PROJECT_BUNDLE_VERIFICATION.md`.

## Developer Setup

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" skills/ea-v0-2
python3 scripts/public_release_smoke.py --dry-run
python3 scripts/public_release_smoke.py
python3 scripts/build_release_manifest.py
python3 scripts/build_release_package.py
python3 scripts/verify_release_package.py dist/ea-v0-2-0.2.0-abcdef0-release.zip
python3 scripts/build_packaged_example_project.py --force
python3 scripts/generate_release_keypair.py --private-key /path/to/user-release-private.pem --public-key /path/to/user-release-public.pem
python3 scripts/sign_release_package.py dist/ea-v0-2-0.2.0-abcdef0-release.zip --private-key /path/to/user-release-private.pem --public-key /path/to/user-release-public.pem
python3 scripts/verify_release_signature.py dist/ea-v0-2-0.2.0-abcdef0-release.zip --public-key /path/to/user-release-public.pem
python3 scripts/build_distribution_checklist.py
```

`scripts/public_release_smoke.py` is the repository-level public-release gate. It prints JSON and runs tests, EA v0.2 skill validation, CLI help sanity checks, and a portability scan for accidental developer-machine defaults. The installed console entry point is `ea-public-release-smoke`.
`scripts/build_release_manifest.py` writes `dist/ea-v0.2-release-manifest.yml` with package metadata, git state, console scripts, release input checksums, smoke-gate requirements, and public-user boundary notes. The installed console entry point is `ea-release-manifest`.
`scripts/build_release_package.py` writes a deterministic release zip plus `.sha256` sidecar under `dist/`. The archive includes the release manifest and selected repository inputs. The installed console entry point is `ea-release-package`.
`scripts/verify_release_package.py` verifies a release zip sidecar, embedded manifest, and manifest-listed payload checksums. The installed console entry point is `ea-verify-release-package`.
`scripts/build_packaged_example_project.py` regenerates the public-safe Raman example project under `examples/public-raman-project/`; the example is included in default release manifests/packages and should pass `ea healthcheck` and `ea eval project --no-write`.
`scripts/generate_release_keypair.py`, `scripts/sign_release_package.py`, and `scripts/verify_release_signature.py` implement an optional detached Ed25519 signature workflow for release packages. Private/public key paths must be supplied explicitly by the user; EA does not assume or search developer-machine key locations. The installed console entry points are `ea-release-keygen`, `ea-sign-release-package`, and `ea-verify-release-signature`.
`scripts/build_distribution_checklist.py` writes `dist/ea-v0.2-distribution-checklist.json` and `.md`, summarizing required release commands, current git/package state, manifest/package artifacts, package verification, optional signature status, and public-user boundary notes. The installed console entry point is `ea-release-checklist`.

## Local Test Fixtures

Public workflow tests use `tests/fixtures/public/`. Local integration tests that touch real Zotero, browser profiles, institution login, or user caches must be marked `local-test-only` and kept out of product defaults.
