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
ea healthcheck examples/public-raman-project
ea eval project examples/public-raman-project --no-write
ea export report-bundle /path/to/ea-project --report-id rpt-project-slug-20260630-001 --zip
ea export batch-bundle /path/to/ea-project --batch-id batch-20260630-001 --zip
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
ea ftir report /path/to/ea-project --metadata processed/sample-001/ftir/res-project-ftir-20260630-001/ftir_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
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
ea literature rank-candidates /path/to/ea-project --candidates literature/candidate_results.yml --reference-year 2026
ea literature handoff /path/to/ea-project --literature-thread-id thread-lit-001
ea literature acquisition-request /path/to/ea-project
ea literature import-acquisition /path/to/ea-project --manifest literature/acquisition_manifest.yml
ea literature sync-status /path/to/ea-project --update literature/acquisition_status_update.yml
ea add-skills dry-run /path/to/manifest.yml --workspace /path/to/ea-project --sample-output /path/to/sample-output.yml
ea image-data record /path/to/ea-project --metadata raw/sem/char-20260630-001/metadata.yml --method sem --description "User-confirmed image notes" --description-review-ref review-20260630-001 --confidence low
ea references add /path/to/ea-project --citation "Author A. Title. Journal volume, pages (year)." --doi 10.xxxx/example --url https://doi.org/10.xxxx/example
ea references import-bibtex /path/to/ea-project /path/to/user-exported-references.bib
ea references validate-report /path/to/ea-project reports/rpt-example.md
ea memory propose /path/to/ea-project --text "Candidate finding..." --source-ref reports/rpt-example.md --provenance-ref prov-20260630-001 --category interpretation --confidence medium
```

`ea init-project` writes an `open-items/` literature-library decision record unless `--enable-literature` is supplied. Use `--enable-literature` only when the user explicitly wants a project literature status record created during initialization; all Zotero, browser, cache, proxy/VPN, and institution settings still remain user-supplied.

Enable Zotero, browser assist, literature cache, or institution access only when the user supplies those settings.
BibTeX import uses an explicit user-provided `.bib` export and de-duplicates references by DOI, URL, title, or citation before creating new project records.
Built-in child-skill manifests live in `skill-registry/builtins/` and are indexed by `skill-registry/index.yml`; Raman, PL, XRD, FTIR, UV-Vis, XPS, electrochemistry, thermal analysis, image-data, scientific-figure style infrastructure, and local-literature-library planning/ranking/import/status infrastructure have concrete initial workflows, while other contract placeholders define future module boundaries without claiming full algorithm support.
Built-in material assignment records live in `src/ea/materials/assignments.yml`; use `ea materials list/show/assignments` to inspect the current MoS2 and WS2 Raman/PL/XRD screening rules, h-BN Raman/XRD screening rules, and their caveats.
Template helpers write editable YAML for processing parameter files and batch manifests. They do not create review records or replace user confirmation.
Batch characterization records live under `processed/batches/`; `ea batch validate/run` coordinates already-reviewed Raman, PL, XRD, FTIR, UV-Vis, XPS, electrochemistry, and thermal items without guessing columns, calibration, context, mode, temperature program, or parameters. Batch index records, summaries, item result/report refs, review refs, and batch provenance refs are audited by healthcheck.

`ea healthcheck` audits project config, raw hashes, provenance links, figure/report backlinks, registered references, report citation numbering, review-gated memory indices, batch records, and material-assignment traceability.
`ea eval project` wraps healthcheck/config checks and adds deterministic handoff/readiness summaries for figure style/source-data traces, report citations, batch runs, material assignments, and persisted evaluation records under `evaluation/`.
`ea export report-bundle` copies one report plus linked figures, source data, result metadata, references, local reference files, and provenance into `exports/report-bundles/` for handoff. `ea export batch-bundle` copies one batch run plus nested per-report bundles into `exports/batch-bundles/`. Each bundle writes `bundle_checksums.yml`; add `--zip` or `--zip-output` when the handoff should include a portable archive plus `.zip.sha256` sidecar. Use `ea export verify-bundle` and `ea export verify-archive` to verify local handoff integrity after copying. For provenance audit and checksum/signature boundaries, read `docs/PROJECT_BUNDLE_VERIFICATION.md`.

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
