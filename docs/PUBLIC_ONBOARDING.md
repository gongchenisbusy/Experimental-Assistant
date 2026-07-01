# EA v0.2 Public Onboarding

This guide is for a new public user or a fresh agent starting from an EA v0.2 release package. It avoids developer-machine assumptions and uses placeholders that the user must replace with local paths.

## 1. Install

Requirements:

- Python 3.11 or newer.
- A local folder where the user can create EA project workspaces.
- Optional: Zotero, a browser, institution access, and release-signing keys only when the user explicitly chooses those workflows.

From a repository checkout or an extracted release package:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e ".[dev]"
ea --help
```

For normal use without test tools, install the package in the user's preferred Python environment and run `ea --help` to confirm the console entry point is available.

The release package also includes `examples/public-raman-project/`, a public-safe Raman project artifact that can be inspected without configuring Zotero, browser assistance, institution access, private caches, or signing keys.

## 2. Create A First Project

Choose a project folder and initialize it with explicit project metadata:

```bash
ea init-project /path/to/ea-project \
  --name "Project name" \
  --slug project-slug \
  --direction "Research direction" \
  --material "Material system" \
  --experiment-type "Experiment type"

ea config doctor /path/to/ea-project
ea healthcheck /path/to/ea-project
ea eval project /path/to/ea-project
```

The initialization step writes `EA_PROJECT.md`, `PROJECT_RULE_CARD.md`, `.ea/project_config.yml`, and the project directory structure. It also writes an `open-items/` literature-library decision record when `--enable-literature` is not supplied, so the next agent asks whether to deploy a local literature library instead of silently skipping it. It does not assume a Zotero database, browser profile, institution login, literature cache, or test fixture path.

To create the literature status record during initialization, add `--enable-literature`. Still ask the user to confirm search scope, access mode, selected top N, and any Zotero/browser/cache/institution settings before planning or acquisition.

To inspect the packaged example before creating a real project:

```bash
ea healthcheck examples/public-raman-project
ea eval project examples/public-raman-project --no-write
```

Copy the example folder before making experimental edits. It is an orientation artifact, not a template that stores a user's real project memory.

## 3. Import And Analyze Characterization Data

Raw files should be imported as controlled project copies before processing. EA v0.2 currently has concrete workflows for Raman, PL, XRD, FTIR, UV-Vis, XPS, electrochemistry, thermal analysis, and image-style characterization records.

Minimal Raman path:

```bash
ea raw import /path/to/ea-project /path/to/raw-raman.txt \
  --characterization-type raman \
  --sample-ref sample-001 \
  --experiment-ref exp-001

ea raman inspect /path/to/ea-project raw/raman/char-YYYYMMDD-001/raw-raman.txt

ea review add /path/to/ea-project \
  --target-type raman_columns \
  --target-ref raw/raman/char-YYYYMMDD-001/metadata.yml \
  --user-response "confirmed" \
  --reviewed-content "x=col_0, y=col_1, unit=cm^-1"

ea review add /path/to/ea-project \
  --target-type raman_parameters \
  --target-ref raw/raman/char-YYYYMMDD-001/metadata.yml \
  --user-response "confirmed" \
  --reviewed-content "default Raman parameters confirmed"

ea raman process /path/to/ea-project \
  --metadata raw/raman/char-YYYYMMDD-001/metadata.yml \
  --x-column col_0 \
  --y-column col_1 \
  --x-unit cm^-1 \
  --column-review-ref review-YYYYMMDD-001 \
  --parameter-review-ref review-YYYYMMDD-002 \
  --sample-ref sample-001

ea raman report /path/to/ea-project \
  --metadata processed/sample-001/raman/res-project-slug-raman-YYYYMMDD-001/raman_metadata.yml \
  --sample-ref sample-001 \
  --experiment-ref exp-001
```

Use the matching `pl`, `xrd`, `ftir`, `uv-vis`, `xps`, `electrochemistry`, or `thermal` commands for PL, XRD, FTIR, UV-Vis, XPS, electrochemical, and thermal data. FTIR processing requires a user-confirmed `signal_mode` (`absorbance` or `transmittance`) so the workflow detects peaks or valleys correctly; optional `context_record` preserves reviewed instrument/accessory, atmosphere, sample preparation, background/reference, and correction-note metadata for provenance only, and does not prove chemical composition or apply automatic correction. UV-Vis processing requires a user-confirmed `signal_mode` (`absorbance`, `transmittance`, or `reflectance`) and treats optical features/edge estimates as screening evidence until a method model and references are reviewed; optional Tauc/Kubelka-Munk screening requires reviewed `tauc_analysis` parameters, optional derivative screening requires reviewed `derivative_analysis` axis settings, and optional `correction_context` records reviewed substrate/reference/background/sample-geometry/diffuse-reflectance metadata for provenance only. None of these optional UV-Vis records by itself proves a band gap, transition mechanism, or numeric correction. XPS processing requires user-confirmed binding-energy calibration metadata and treats automatic peaks as screening evidence until background, component model, references, and chemical-state interpretation are reviewed; optional `component_quantification` uses reviewed component windows and sensitivity factors for screening only, not definitive composition; optional `background_model` preserves reviewed Shirley/Tougaard/linear/local-minimum choices for provenance only; optional `background_subtraction` writes reviewed linear, Shirley, or Tougaard U2 background and corrected-intensity preprocessing columns only inside user-confirmed binding-energy regions, and Tougaard U2 requires reviewed `B`, `C_eV2`, and integration direction; optional `component_fit` fits reviewed components inside reviewed binding-energy regions from explicit peak shapes, initial values, bounds, selected intensity/background columns, references, caveats, fit-quality thresholds, and optional reviewed `spin_orbit_constraints`. Spin-orbit parameters may be reported by the user or proposed from source-backed references, but source-backed values must preserve `parameter_origin`, source summary, applicability notes, and `reference_ids` before they are used as constraints. Optional `region_records` preserves reviewed survey/core-level/project-region organization, calibration-group labels, linked output refs, references, and caveats for provenance only. EA may help gather or suggest source-backed XPS endpoints, backgrounds, components, bounds, peak shapes, Tougaard/spin-orbit parameters, and chemical-state candidates when the sample context and references support them; the workflow must not silently apply those values, align survey/core-level spectra without review, silently share charge correction, fit Tougaard parameters without a reviewed protocol, run QUASES/depth-profile modeling, prove composition, assign chemical states as facts, use unsourced constants, or perform unreviewed constrained spin-orbit fitting. Electrochemistry processing requires user-confirmed current unit, measurement mode, electrode/electrolyte/reference-electrode/protocol context, and optional electrode area before current-density normalization; automatic features are summaries, not standalone performance or mechanism claims. Optional electrochemistry `potential_conversion` applies a user-reviewed numeric offset to processed voltammetry coordinates and records the source scale, target scale, output column, and provenance; it is a coordinate transform only. Optional electrochemistry `ir_drop_correction` applies a user-reviewed Ru/fraction/sign-convention coordinate correction and records the corrected-potential column/provenance; it is not a Tafel, overpotential, performance, or mechanism claim. Optional electrochemistry `eis_circuit_fit` fits only a user-reviewed EIS circuit model from confirmed frequency column/order, perturbation, initial values, bounds, and fit-quality thresholds; it is not automatic circuit selection, Rct/Warburg proof, device-performance proof, or mechanism proof. Optional electrochemistry `tafel_analysis` fits log-current versus reviewed potential only inside the user-confirmed kinetic window and records slope/overpotential screening metadata; it is not automatic kinetic-window selection, catalyst ranking, performance proof, or mechanism proof. Optional electrochemistry `gcd_analysis` calculates discharge-window capacity/capacitance metrics only after the user confirms the voltage signal, time window, voltage window, discharge current, and mass/area/loading metadata; it is not automatic segment selection, rate capability, cycling stability, device-performance proof, or mechanism proof. Optional electrochemistry `correction_record` preserves reviewed reference-electrode, converted-scale, uncompensated-resistance, and iR-compensation metadata for provenance only, and does not itself shift potentials, apply iR correction, or prove mechanism/performance. EIS Nyquist screening uses reviewed `measurement_mode=eis`, `x_unit=ohm`, and `current_unit=unknown`; reviewed circuit-fit screening is available only when explicitly enabled and does not prove Rct/mechanisms by itself. Thermal processing requires user-confirmed temperature/signal units, method mode, temperature program, atmosphere, sample mass, and baseline/reference context; optional `baseline_correction` applies reviewed DSC/DTG linear baseline processing, optional `transition_analysis` extracts Tg/Tm/Tc-style candidate metrics only inside reviewed DSC windows, optional `transition_assignment` preserves user-confirmed transition interpretation records, and optional `context_record` preserves reviewed DSC sign convention, baseline/reference, sample, atmosphere/program, and correction-note metadata for provenance only; automatic events are summaries, not standalone Tg/Tm/decomposition/kinetic claims, and thermal baseline/transition/assignment/context records do not fit kinetics, rank thermal stability, automatically infer transition assignments, or prove mechanisms. Use `ea image-data record` and `ea image-data report` for SEM, TEM, optical microscopy, and related image-style data where user description and confidence labels are part of the record.

For XPS source-backed parameter work, EA may first help gather candidate values from built-in `generic_xps_parameters` seeds, project literature, a local candidate library, user-provided sources, or a user-confirmed literature/search workflow. Use `ea xps build-source-packet` with no library arguments for the built-in starter packet, `--builtin-library generic_xps_parameters` for explicit built-in selection, or `--library-file`/`--write-template` for project-local libraries and editable templates; then use `ea xps suggest-parameters` before copying any values into processing parameters. XPS source packets may carry `reference_seeds` and `guidance_reference_ids` for filtered candidates and charge/reference guidance; run `ea references register-seeds --source-packet ...` only when those seeds should become project reference records. The helper does not inject report citations, download PDFs, or apply XPS parameters. Use `ea xps prepare-review --suggestion ...` to generate grouped YAML/Markdown review packages that show ready, unresolved-reference, and invalid candidates with source summaries, applicability notes, caveats, and suggested review/report/memory commands; this does not create a ReviewRecord. Pass reviewed suggestion records to `ea xps report --parameter-suggestion ...` when the report should display advisory source-backed parameter candidates; registered suggestion references are merged into References while unresolved IDs remain visible as registration issues. After the user confirms a suggestion record, use `ea xps propose-memory --suggestion ... --review-ref ...` to create draft method-note memory candidates from ready candidates only; the standard memory review/commit flow is still required before anything becomes durable project memory. The build/suggest/prepare-review/report/memory integration does not perform unconfirmed live lookup inside the command and never auto-applies values to fitting, charge correction, or background subtraction.

For FTIR source-backed assignment work, use `ea ftir build-assignment-packet` to turn the built-in `generic_materials` seed library, a project-local band-assignment library, or an editable template into a standard source packet, then use `ea ftir suggest-assignments` with processed FTIR metadata. The workflow matches reviewed candidate wavenumber windows against detected FTIR features, records source summary, applicability notes, confidence, caveats, matched band IDs, and registered/missing `reference_ids`, and never treats a band match alone as composition or functional-group proof. Built-in packets include `reference_seeds`; users or agents should register/replace those sources in the project before treating suggestions as report evidence. Use `ea references register-seeds --source-packet ...` only when those seeds should become project reference records; this helper does not inject citations into reports. The no-live-lookup command boundary means FTIR suggestion commands avoid unconfirmed lookup during deterministic processing, while EA may still prepare sourced assignment candidates from reviewed literature, local libraries, or confirmed searches before the packet/suggestion step. Use `ea ftir prepare-review --suggestion ...` to write grouped YAML/Markdown review packages before asking the user which candidate IDs to accept, reject, edit, or defer; this does not create a ReviewRecord or confirmed interpretation. When generating a report, pass reviewed suggestion records with `ea ftir report --assignment-suggestion ...`; registered suggestion references are merged into the report References while unresolved IDs remain visible as items needing registration. After the user confirms a suggestion record, use `ea ftir propose-memory --suggestion ... --review-ref ...` to create draft memory candidates from ready candidates only; the standard memory review/commit flow is still required before anything becomes durable project memory.

## 4. Review Gates And Reports

EA is intentionally review-gated:

- Confirm columns before processing.
- Confirm processing parameters before processing.
- Register references before citing literature-supported claims.
- Save durable findings through memory candidates and user review, not automatic report text.

Reports should contain report IDs, sample/raw/result references, embedded figure links, confidence-labeled interpretations, inline numeric citations such as `[1][2]`, References entries, and provenance links.

## 5. Literature Library Setup

Literature deployment is recommended, but it is optional and user-controlled. New projects initialized without `--enable-literature` contain an `open-items/` decision record asking whether to create a local literature library. If the user agrees later, start with `ea literature plan`; if the project was initialized with `--enable-literature`, check `literature/deployment_status.yml` before planning.

Start with a plan:

```bash
ea literature plan /path/to/ea-project --scope ordinary --access-mode open_access_only
```

Then review the generated confirmation request before acquisition:

```bash
ea literature confirm /path/to/ea-project \
  --selected-top-n 50 \
  --user-response "confirmed"
```

If a dedicated literature workflow or the user has exported candidate metadata, rank it locally before generating acquisition targets:

```bash
ea literature search-public /path/to/ea-project \
  --source crossref \
  --source openalex \
  --source arxiv \
  --max-results 20 \
  --page-limit 1
ea literature rank-candidates /path/to/ea-project \
  --candidates literature/candidate_results.yml \
  --reference-year 2026
ea literature acquisition-request /path/to/ea-project
ea literature institution-access-guide /path/to/ea-project \
  --institution-name "Institution" \
  --access-method library_proxy \
  --access-url https://library.example.edu/login \
  --browser-name Chrome \
  --browser-profile browser-profiles/project
ea literature zotero-bridge /path/to/ea-project \
  --zotero-config config/zotero-codex.json \
  --project-collection "Project collection"
ea literature import-zotero-status /path/to/ea-project \
  --batch-status literature/zotero_codex_batch_status.json \
  --sidecar-verification literature/zotero_codex_sidecars_verify.json
ea literature reconcile-acquisition /path/to/ea-project
ea literature render-reconciliation /path/to/ea-project \
  --reconciliation literature/acquisition_reconciliation.yml
```

`search-public` queries public metadata APIs only when explicitly run, writes `literature/public_search_candidates.yml`, `literature/search_coverage.yml`, and `literature/public_search_state.yml`, then ranks candidates. Use `--page-limit`, `--delay-seconds`, and `--resume` for longer resumable runs. It does not use Zotero, browser profiles, institution login, credentials, paywall access, DOI full-text resolution, or PDF downloads, and it must not be described as exhaustive web coverage. `rank-candidates` only scores supplied metadata and writes `literature/ranking.csv` plus `literature/selected_items.yml`; it does not look up impact factors, open Zotero, use browser profiles, log into institutions, or download PDFs. `institution-access-guide` writes a public-safe guidance packet for user-managed institution access; it records user-supplied route/browser/profile status but does not open browsers, store credentials, probe URLs, or fetch papers. `zotero-bridge` writes a Zotero-Codex runbook and settings request for a dedicated literature workflow; it emits commands but does not run Zotero, open browsers, resolve DOI pages, download PDFs, or assume local accounts. `import-zotero-status` reads dedicated-workflow batch status artifacts and writes EA sync records; it does not run Zotero-Codex scripts or fetch papers. `reconcile-acquisition` checks local acquisition/status/library/cache/reference records and writes YAML plus Markdown audit reports with advisory `repair_actions` and `questions_for_user`, but it does not auto-repair records or read full text. `render-reconciliation` regenerates the Markdown audit view from an existing reconciliation YAML without repairing records. Only after confirmation should a dedicated literature workflow create acquisition requests, use Zotero or browser assistance, or import acquisition manifests. EA must not store credentials or bypass access controls. If institution access is needed, the user handles login manually in their own environment.

## 6. Traceability And Handoff Checks

Before handing a project to another user or agent, run:

```bash
ea healthcheck /path/to/ea-project
ea eval project /path/to/ea-project
```

For a single report handoff:

```bash
ea export report-bundle /path/to/ea-project \
  --report-id rpt-project-slug-YYYYMMDD-001 \
  --zip

ea export verify-bundle /path/to/ea-project/exports/report-bundles/rpt-project-slug-YYYYMMDD-001
ea export verify-archive /path/to/ea-project/exports/report-bundles/rpt-project-slug-YYYYMMDD-001.zip
```

For batch work, use `ea export batch-bundle` and the same verification helpers.

For project-bundle provenance audit, checksum interpretation, and the boundary between bundle checksums and external signatures, read `docs/PROJECT_BUNDLE_VERIFICATION.md`.

## 7. Repository Release Checks

Before sharing an EA v0.2 repository package:

```bash
ea-public-release-smoke
ea-release-manifest
ea-release-package
ea-verify-release-package dist/ea-v0-2-0.2.0-COMMIT-release.zip
ea-release-checklist
```

For recipient-side artifact verification details, read `docs/RELEASE_VERIFICATION.md`.

Optional signing uses explicit user-managed keys:

```bash
ea-release-keygen \
  --private-key /path/to/user-release-private.pem \
  --public-key /path/to/user-release-public.pem

ea-sign-release-package dist/ea-v0-2-0.2.0-COMMIT-release.zip \
  --private-key /path/to/user-release-private.pem \
  --public-key /path/to/user-release-public.pem

ea-verify-release-signature dist/ea-v0-2-0.2.0-COMMIT-release.zip \
  --public-key /path/to/user-release-public.pem
```

These commands verify packaging and local integrity. They do not verify scientific correctness, literature truth, or authorship unless the optional detached signature is created and checked with a trusted public key.

## 8. What To Ask The User

Ask only when the answer affects the next work or a scientific judgment:

- Which project folder should be initialized or continued?
- Which material system, sample, experiment, and method does this raw file belong to?
- Are the detected columns and units correct?
- Are the processing parameters acceptable?
- Should literature deployment be enabled, and what top N should be acquired?
- Are reported interpretations acceptable as durable memory candidates?
- Which export or release artifacts should be produced and signed?
