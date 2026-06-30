# EA Project Workflow

Use this reference when creating or continuing an EA project.

Core workspace:

```text
ea-project/
├── EA_PROJECT.md
├── PROJECT_RULE_CARD.md
├── .ea/project_config.yml
├── experiments/
├── evaluation/
├── exports/
│   ├── batch-bundles/
│   └── report-bundles/
├── samples/
├── raw/
├── templates/
├── processed/
│   └── batches/
├── figures/
├── reports/
├── literature/
├── skill-registry/
├── reviews/
├── provenance/
├── memory/
├── suggestions/
├── progress/
└── open-items/
```

Workflow:

1. Open or initialize the project.
2. Check whether `literature/deployment_status.yml` exists. If not, read the initialization-created `open-items/` literature-library decision record and ask whether the user wants to deploy a local literature library.
3. Preserve user input as source text when structuring logs.
4. Import raw files as controlled read-only copies with hashes.
5. Run deterministic processing scripts after review gates are satisfied.
6. Write reports, figure records, provenance, and review records.
7. Save new findings as memory candidates until the user confirms them.
8. Keep open questions in `open-items/` when they matter but do not block the current step.
9. Run `ea healthcheck` after creating or modifying raw imports, processed outputs, reports, figures, provenance, references, or memory.
10. Run `ea eval project` before handoff, public-demo readiness checks, or long context transitions.

CLI path for the first Raman workflow:

```bash
ea raw import /path/to/ea-project /path/to/raw-spectrum.txt --characterization-type raman --sample-ref sample-001 --experiment-ref exp-001
ea raman inspect /path/to/ea-project raw/raman/char-20260630-001/raw-spectrum.txt
ea review add /path/to/ea-project --target-type raman_columns --target-ref raw/raman/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "x=col_0, y=col_1, unit=cm^-1"
ea review add /path/to/ea-project --target-type raman_parameters --target-ref raw/raman/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default Raman parameters confirmed"
ea raman process /path/to/ea-project --metadata raw/raman/char-20260630-001/metadata.yml --x-column col_0 --y-column col_1 --x-unit cm^-1 --column-review-ref review-20260630-001 --parameter-review-ref review-20260630-002 --sample-ref sample-001
ea raman report /path/to/ea-project --metadata processed/sample-001/raman/res-project-raman-20260630-001/raman_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
```

CLI path for the first PL workflow:

```bash
ea raw import /path/to/ea-project /path/to/raw-pl.txt --characterization-type pl --sample-ref sample-001 --experiment-ref exp-001
ea pl inspect /path/to/ea-project raw/pl/char-20260630-001/raw-pl.txt
ea review add /path/to/ea-project --target-type pl_columns --target-ref raw/pl/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "x=col_0, y=col_1, unit=eV"
ea review add /path/to/ea-project --target-type pl_parameters --target-ref raw/pl/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default PL parameters confirmed"
ea pl process /path/to/ea-project --metadata raw/pl/char-20260630-001/metadata.yml --x-column col_0 --y-column col_1 --x-unit eV --column-review-ref review-20260630-003 --parameter-review-ref review-20260630-004 --sample-ref sample-001
ea pl report /path/to/ea-project --metadata processed/sample-001/pl/res-project-pl-20260630-001/pl_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
```

CLI path for the first XRD workflow:

```bash
ea raw import /path/to/ea-project /path/to/raw-xrd.txt --characterization-type xrd --sample-ref sample-001 --experiment-ref exp-001
ea xrd inspect /path/to/ea-project raw/xrd/char-20260630-001/raw-xrd.txt
ea review add /path/to/ea-project --target-type xrd_columns --target-ref raw/xrd/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "x=two_theta, y=intensity, unit=2theta_deg"
ea review add /path/to/ea-project --target-type xrd_parameters --target-ref raw/xrd/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default XRD parameters confirmed"
ea xrd process /path/to/ea-project --metadata raw/xrd/char-20260630-001/metadata.yml --x-column two_theta --y-column intensity --x-unit 2theta_deg --column-review-ref review-20260630-005 --parameter-review-ref review-20260630-006 --sample-ref sample-001
ea xrd report /path/to/ea-project --metadata processed/sample-001/xrd/res-project-xrd-20260630-001/xrd_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
```

CLI path for the first FTIR workflow:

```bash
ea raw import /path/to/ea-project /path/to/raw-ftir.txt --characterization-type ftir --sample-ref sample-001 --experiment-ref exp-001
ea ftir inspect /path/to/ea-project raw/ftir/char-20260630-001/raw-ftir.txt
ea review add /path/to/ea-project --target-type ftir_columns --target-ref raw/ftir/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "x=wavenumber, y=absorbance, unit=cm^-1, signal_mode=absorbance"
ea review add /path/to/ea-project --target-type ftir_parameters --target-ref raw/ftir/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default FTIR parameters confirmed"
ea ftir process /path/to/ea-project --metadata raw/ftir/char-20260630-001/metadata.yml --x-column wavenumber --y-column absorbance --x-unit cm^-1 --signal-mode absorbance --column-review-ref review-20260630-007 --parameter-review-ref review-20260630-008 --sample-ref sample-001
ea ftir report /path/to/ea-project --metadata processed/sample-001/ftir/res-project-ftir-20260630-001/ftir_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
```

CLI path for the first UV-Vis workflow:

```bash
ea raw import /path/to/ea-project /path/to/raw-uv-vis.txt --characterization-type uv_vis --sample-ref sample-001 --experiment-ref exp-001
ea uv-vis inspect /path/to/ea-project raw/uv_vis/char-20260630-001/raw-uv-vis.txt
ea review add /path/to/ea-project --target-type uv_vis_columns --target-ref raw/uv_vis/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "x=wavelength_nm, y=absorbance, unit=nm, signal_mode=absorbance"
ea review add /path/to/ea-project --target-type uv_vis_parameters --target-ref raw/uv_vis/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default UV-Vis parameters confirmed"
ea uv-vis process /path/to/ea-project --metadata raw/uv_vis/char-20260630-001/metadata.yml --x-column wavelength_nm --y-column absorbance --x-unit nm --signal-mode absorbance --column-review-ref review-20260630-009 --parameter-review-ref review-20260630-010 --sample-ref sample-001
ea uv-vis report /path/to/ea-project --metadata processed/sample-001/uv_vis/res-project-uv-vis-20260630-001/uv_vis_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
```

CLI path for the first XPS workflow:

```bash
ea raw import /path/to/ea-project /path/to/raw-xps.txt --characterization-type xps --sample-ref sample-001 --experiment-ref exp-001
ea xps inspect /path/to/ea-project raw/xps/char-20260630-001/raw-xps.txt
ea review add /path/to/ea-project --target-type xps_columns --target-ref raw/xps/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "x=binding_energy_eV, y=intensity, unit=eV"
ea review add /path/to/ea-project --target-type xps_calibration --target-ref raw/xps/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "C 1s reference at 284.8 eV; energy_shift_eV=0.0"
ea review add /path/to/ea-project --target-type xps_parameters --target-ref raw/xps/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default XPS parameters confirmed"
ea xps process /path/to/ea-project --metadata raw/xps/char-20260630-001/metadata.yml --x-column binding_energy_eV --y-column intensity --x-unit eV --energy-shift-ev 0.0 --calibration-reference "C 1s 284.8 eV user-confirmed reference" --column-review-ref review-20260630-011 --calibration-review-ref review-20260630-012 --parameter-review-ref review-20260630-013 --sample-ref sample-001
ea xps report /path/to/ea-project --metadata processed/sample-001/xps/res-project-xps-20260630-001/xps_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
```

CLI path for the first electrochemistry workflow:

```bash
ea raw import /path/to/ea-project /path/to/raw-electrochemistry.txt --characterization-type electrochemistry --sample-ref sample-001 --experiment-ref exp-001
ea electrochemistry inspect /path/to/ea-project raw/electrochemistry/char-20260630-001/raw-electrochemistry.txt
ea review add /path/to/ea-project --target-type electrochemistry_columns --target-ref raw/electrochemistry/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "x=potential_V, y=current_mA, x_unit=V, current_unit=mA, mode=cv"
ea review add /path/to/ea-project --target-type electrochemistry_context --target-ref raw/electrochemistry/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "electrode/electrolyte/reference-electrode/protocol confirmed"
ea review add /path/to/ea-project --target-type electrochemistry_parameters --target-ref raw/electrochemistry/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default electrochemistry parameters confirmed"
ea electrochemistry process /path/to/ea-project --metadata raw/electrochemistry/char-20260630-001/metadata.yml --x-column potential_V --y-column current_mA --x-unit V --current-unit mA --measurement-mode cv --context-summary "user-confirmed electrode/electrolyte/reference/protocol" --electrode-area-cm2 0.196 --column-review-ref review-20260630-014 --context-review-ref review-20260630-015 --parameter-review-ref review-20260630-016 --sample-ref sample-001
ea electrochemistry report /path/to/ea-project --metadata processed/sample-001/electrochemistry/res-project-electrochemistry-20260630-001/electrochemistry_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
```

CLI path for the first thermal analysis workflow:

```bash
ea raw import /path/to/ea-project /path/to/raw-tga.txt --characterization-type thermal_analysis --sample-ref sample-001 --experiment-ref exp-001
ea thermal inspect /path/to/ea-project raw/thermal_analysis/char-20260630-001/raw-tga.txt
ea review add /path/to/ea-project --target-type thermal_columns --target-ref raw/thermal_analysis/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "temperature=temperature_C, signal=mass_percent, temperature_unit=C, signal_unit=%, mode=tga"
ea review add /path/to/ea-project --target-type thermal_context --target-ref raw/thermal_analysis/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "temperature program, atmosphere, sample mass, and baseline reviewed"
ea review add /path/to/ea-project --target-type thermal_parameters --target-ref raw/thermal_analysis/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default thermal parameters confirmed"
ea thermal process /path/to/ea-project --metadata raw/thermal_analysis/char-20260630-001/metadata.yml --temperature-column temperature_C --signal-column mass_percent --temperature-unit C --signal-unit % --measurement-mode tga --context-summary "N2 atmosphere; 10 C/min; sample mass and baseline reviewed" --column-review-ref review-20260630-017 --context-review-ref review-20260630-018 --parameter-review-ref review-20260630-019 --sample-ref sample-001
ea thermal report /path/to/ea-project --metadata processed/sample-001/thermal_analysis/res-project-thermal-analysis-20260630-001/thermal_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
```

Editable templates:

```bash
ea templates parameters raman --output /path/to/ea-project/templates/raman_parameters.yml
ea templates parameters ftir --output /path/to/ea-project/templates/ftir_parameters.yml
ea templates parameters uv_vis --output /path/to/ea-project/templates/uv_vis_parameters.yml
ea templates parameters xps --output /path/to/ea-project/templates/xps_parameters.yml
ea templates parameters electrochemistry --output /path/to/ea-project/templates/electrochemistry_parameters.yml
ea templates parameters thermal_analysis --output /path/to/ea-project/templates/thermal_parameters.yml
ea templates batch-manifest /path/to/ea-project --method raman --method pl --method xrd --method ftir --method uv_vis --method xps --method electrochemistry --method thermal_analysis --output batch_manifest.yml
```

Parameter templates are directly usable with `--parameters-file` after the user confirms the parameter content. Batch manifest templates still need real metadata and confirmed review refs before validation.

Project readiness evaluation:

```bash
ea healthcheck /path/to/ea-project
ea eval project /path/to/ea-project
ea eval project /path/to/ea-project --no-write
```

Repository public-release smoke check:

```bash
ea-public-release-smoke --dry-run
ea-public-release-smoke
ea-release-manifest
ea-release-package
ea-verify-release-package dist/ea-v0-2-0.2.0-abcdef0-release.zip
```

Use the smoke check before publishing or handing off the EA v0.2 repository itself, then generate and verify the release manifest/package. This is separate from project readiness: it runs tests, skill validation, CLI help sanity checks, records package/git/checksum metadata, builds a portable archive with a checksum sidecar, verifies package payload integrity, and scans for portability without relying on Zotero, browser profiles, institution access, or developer-machine paths.

Report bundle export:

```bash
ea export report-bundle /path/to/ea-project --report-id rpt-project-20260630-001 --zip
ea export batch-bundle /path/to/ea-project --batch-id batch-20260630-001 --zip
ea export verify-bundle /path/to/ea-project/exports/report-bundles/rpt-project-20260630-001
ea export verify-archive /path/to/ea-project/exports/report-bundles/rpt-project-20260630-001.zip
```

Report bundles are written under `exports/report-bundles/{report_id}` by default and copy linked report, figure, source-data, result, reference, and provenance artifacts for handoff. Batch bundles are written under `exports/batch-bundles/{batch_id}` and include batch records plus nested per-report bundles. Both bundle types write `bundle_checksums.yml`; use `--zip` or `--zip-output` when the same bundle should also be archived with a `.zip.sha256` sidecar for transfer. Run verification after copying or before handoff.

Batch characterization after individual item review gates exist:

```bash
ea batch validate /path/to/ea-project batch_manifest.yml
ea batch run /path/to/ea-project batch_manifest.yml
```

Batch manifests can coordinate Raman, PL, XRD, FTIR, UV-Vis, XPS, electrochemistry, and thermal analysis items. They do not replace column, unit, signal-mode, calibration, electrochemistry context, thermal temperature-program/sample/atmosphere context, mode, or parameter confirmation; each item must reference confirmed review records. Healthcheck/evaluator treat `processed/batches/index.yml`, each `batch_run.yml`, batch summaries, item result/report refs, and batch provenance refs as handoff-critical project state.
