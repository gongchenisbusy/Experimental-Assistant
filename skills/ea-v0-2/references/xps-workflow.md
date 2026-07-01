# XPS Workflow

Use this reference when processing X-ray photoelectron spectroscopy spectra in EA v0.2.

Required gates:

1. Inspect the file and confirm it is XPS binding-energy spectral data.
2. Ask for or verify x/y columns and x-axis unit (`eV` or `unknown`).
3. Ask for or verify binding-energy calibration before analysis. Record `energy_shift_eV`, `calibration_reference`, and `calibration_review_ref`.
4. Ask for or verify processing parameters before analysis.
5. If source-backed XPS parameter suggestions are requested, run `ea xps suggest-parameters` on a user/project-supplied source packet before copying any values into processing parameters; ask the user to review candidate values and register missing references.
6. If component quantification, background-model documentation, numeric background subtraction, component-fit screening, or multi-region project organization is requested, ask the user to confirm `component_quantification`, `background_model`, `background_subtraction`, `component_fit`, and/or `region_records` parameters: reviewed component IDs/labels, survey/core-level/project-region roles, elements/core levels, binding-energy/background windows, calibration group IDs, linked background/fitting/quantification output refs, subtraction method, anchor points/windows, Shirley iteration settings when used, Tougaard U2 `B`/`C_eV2`/integration direction when used, integration baseline, model/background notes, selected intensity/background columns, component-fit peak shapes, initial values, bounds, optional reviewed `spin_orbit_constraints` with anchor/dependent IDs, signed center delta, area ratio, FWHM ratio, parameter origin, source summary, applicability notes, reference IDs, fit-quality thresholds, software/tool provenance, and sensitivity factors when atomic-percent screening is desired.
7. Keep raw data untouched; write processed outputs outside `raw/`.
8. Record baseline handling, smoothing, normalization, detected screening peaks, optional parameter suggestion records, optional component screening, optional reviewed background-model record, optional reviewed background-subtraction record, optional reviewed component-fit screening record, optional reviewed multi-region record, generated figure, report, and provenance.
9. Treat automatic peaks, source-backed parameter suggestions, reviewed background-subtracted columns, component screening estimates, reviewed component-fit outputs, and multi-region records as screening/provenance evidence. Use calibration context, background model, peak model, references, and user review before writing chemical-state conclusions.
10. Write memory candidates only after user confirmation.

Current v0.2 XPS support:

- Raw import uses `ea raw import --characterization-type xps`.
- Inspection identifies common XPS files by path/name, binding-energy metadata, and binding-energy-like ranges.
- Processing supports user-confirmed energy shift, optional rolling-quantile baseline correction, optional Savitzky-Golay smoothing, max-intensity normalization, SciPy peak detection, disabled-by-default `component_quantification` screening from reviewed binding-energy windows, disabled-by-default `background_model` records for reviewed Shirley/Tougaard/linear/local-minimum/rolling-quantile choices, disabled-by-default `background_subtraction` numeric linear, Shirley, or Tougaard U2 subtraction inside reviewed regions with reviewed anchor points/windows, disabled-by-default `component_fit` screening from reviewed regions, explicit components, peak shapes, initial values, bounds, selected intensity/background columns, optional reviewed `spin_orbit_constraints` with source-backed parameter metadata when applicable, references, caveats, and fit-quality thresholds, and disabled-by-default `region_records` for reviewed survey/core-level/project-region organization and provenance.
- `ea xps suggest-parameters` records source-backed `spin_orbit_constraint` and `tougaard_parameter` candidates from user/project-supplied source packets under `suggestions/xps/` without applying them to processing parameters.
- Processed CSV files include `binding_energy_raw`, calibrated `binding_energy_eV`, `raw_intensity`, optional `baseline_signal`, optional `smoothed_intensity`, and `processed_intensity`.
- When `background_subtraction.enabled` is true with method `reviewed_linear_background_subtraction`, `reviewed_shirley_background_subtraction`, or `reviewed_tougaard_u2_background_subtraction`, processed CSV files also include the reviewed background column, background-subtracted intensity column, and region ID column for the supplied binding-energy windows.
- When `component_fit.enabled` is true with method `reviewed_component_fit_screening`, processed CSV files also include the reviewed component-fit intensity column, residual column, and fit-region ID column only for supplied binding-energy windows.
- When `region_records.enabled` is true with method `reviewed_multi_region_project_record`, processed CSV data are not changed; EA writes separate region-record artifacts from reviewed windows and linked refs.
- Peak tables include `binding_energy_eV`, raw energy, prominence, component model status, possible assignment, assignment confidence, and assignment source.
- When `component_quantification.enabled` is true, EA writes `xps_components.csv` with reviewed component windows, integrated area, relative area percent, sensitivity factor, RSF-corrected area, and `relative_atomic_percent_screening` when all included components have valid positive sensitivity factors.
- When `background_model.enabled` is true, EA writes `xps_background.yml` with reviewed background region/model choices, windows, software/tool refs, reference IDs, reviewer notes, caveats, and whether the background had already been applied outside EA.
- When `background_subtraction.enabled` is true, EA writes `xps_background_subtraction.yml` with reviewed subtraction method, regions, left/right anchors, optional Shirley iterations/convergence, optional Tougaard U2 `B`/`C_eV2`/kernel/integration-direction metadata, output columns, references, warnings, caveats, and confidence.
- When `component_fit.enabled` is true, EA writes `xps_component_fit.yml` and `xps_component_fit.csv` with reviewed component IDs, peak shapes, initial/fitted values, bounds, optional reviewed spin-orbit constraint metadata, fit-quality metrics, reference IDs, caveats, confidence, and record/table refs.
- When `suggest-parameters` is run, EA writes `xps_parameter_suggestions.yml` and `xps_parameter_suggestions.csv` with candidate status, target parameter path, source summary, applicability notes, reference IDs, unresolved-reference warnings, and `auto_applied: false`.
- When `region_records.enabled` is true, EA writes `xps_region_records.yml` and `xps_region_records.csv` with reviewed region roles, binding-energy windows, calibration group IDs, linked output refs, reference IDs, caveats, confidence, and record/table refs.
- Reports include an embedded XPS figure, original figure path, calibration/background section, peak table, optional component screening table, optional component-fit section/table, optional multi-region section/table, confidence-labeled possible interpretations, file links, References, and provenance.
- XPS component quantification is screening-only. XPS background model records are provenance only. XPS background subtraction is reviewed numeric preprocessing only. XPS component fitting, including reviewed `spin_orbit_constraints`, is reviewed screening-level numerical modeling only. XPS region records are project organization/provenance only. EA does not perform definitive chemical-state assignment, formal quantitative composition, surface stoichiometry, automatic endpoint/background/component/bounds/peak-shape selection, automatic survey-core-level alignment, silent charge-correction sharing, automatic Tougaard parameter fitting, QUASES/depth-profile modeling, use of unsourced spin-orbit constants, or unreviewed spin-orbit constrained fitting.

CLI path:

```bash
ea raw import /path/to/ea-project /path/to/raw-xps.txt --characterization-type xps --sample-ref sample-001 --experiment-ref exp-001
ea xps inspect /path/to/ea-project raw/xps/char-20260630-001/raw-xps.txt
ea review add /path/to/ea-project --target-type xps_columns --target-ref raw/xps/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "x=binding_energy_eV, y=intensity, unit=eV"
ea review add /path/to/ea-project --target-type xps_calibration --target-ref raw/xps/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "C 1s reference at 284.8 eV; energy_shift_eV=0.0"
ea review add /path/to/ea-project --target-type xps_parameters --target-ref raw/xps/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default XPS parameters confirmed"
ea xps suggest-parameters /path/to/ea-project --source-file xps_parameter_source.yml --related-record raw/xps/char-20260630-001/metadata.yml
ea xps process /path/to/ea-project --metadata raw/xps/char-20260630-001/metadata.yml --x-column binding_energy_eV --y-column intensity --x-unit eV --energy-shift-ev 0.0 --calibration-reference "C 1s 284.8 eV user-confirmed reference" --column-review-ref review-20260630-001 --calibration-review-ref review-20260630-002 --parameter-review-ref review-20260630-003 --sample-ref sample-001
ea xps report /path/to/ea-project --metadata processed/sample-001/xps/res-project-xps-20260630-001/xps_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
```

Optional source-backed parameter suggestion source packet:

```yaml
candidates:
  - candidate_id: xps-param-fe2p-spin-001
    suggestion_type: spin_orbit_constraint
    element: Fe
    core_level: 2p
    constraint_id: xps-spin-fe2p-source-001
    center_delta_eV: 13.4
    area_ratio: 0.5
    fwhm_ratio: 1.0
    parameter_origin: source_suggested
    source_summary: Fe 2p spin-orbit screening values from a registered project XPS reference.
    applicability_notes:
      - Applies only if the user confirms Fe 2p anchor/dependent component IDs and reviewed bounds.
    reference_ids:
      - ref-xps-spin-orbit-001
    confidence: low
    caveats:
      - Candidate constraint only; not chemical-state proof.
  - candidate_id: xps-param-tougaard-u2-001
    suggestion_type: tougaard_parameter
    tougaard_C_eV2: 1643.0
    integration_direction: toward_higher_binding_energy
    parameter_origin: source_suggested
    source_summary: Tougaard U2 parameter candidate from a registered project XPS reference.
    applicability_notes:
      - Requires a user-reviewed background region and method choice before subtraction.
    reference_ids:
      - ref-xps-tougaard-001
    confidence: low
```

Parameter suggestion records can make EA useful as an assistant without pretending that every value came directly from the user. They validate metadata and preserve traceability, but remain advisory until the user reviews them and copies accepted values into processing parameters with the relevant review refs.

Optional reviewed component screening parameters can be supplied with `--parameters-json` or `--parameters-file`:

```yaml
component_quantification:
  enabled: true
  method: reviewed_window_integration
  integration_baseline: local_minimum
  min_points: 5
  source: ea.xps.component_quantification:v0.2
  components:
    - component_id: xps-c1s-001
      label: C 1s reviewed window
      element: C
      core_level: 1s
      binding_energy_window_eV: [282.5, 287.0]
      sensitivity_factor: 1.0
      model: reviewed_window
      background: local_minimum
```

Optional reviewed background-model parameters:

```yaml
background_model:
  enabled: true
  method: reviewed_background_record
  source: ea.xps.background_model:v0.2
  applied_to_processed_data: false
  software:
    name: instrument export
    version: reviewed
  regions:
    - region_id: xps-bg-c1s-001
      label: C 1s Shirley background choice
      background_type: shirley
      binding_energy_window_eV: [280.0, 292.0]
      parameters:
        endpoint_strategy: reviewed_component_edges
      reference_ids:
        - ref-xps-background-001
      reviewer_notes:
        - User confirmed Shirley background choice for C 1s interpretation.
      caveats:
        - EA records this model choice only; no numeric Shirley subtraction was applied.
      confidence: low
```

Background model records preserve reviewed model/provenance choices. They do not make EA apply Shirley/Tougaard subtraction, fit spin-orbit constrained peaks, calculate final composition, or prove chemical states.

Optional reviewed linear background-subtraction parameters:

```yaml
background_subtraction:
  enabled: true
  method: reviewed_linear_background_subtraction
  source: ea.xps.background_subtraction:v0.2
  input_intensity_column: processed_intensity
  background_column: xps_linear_background
  corrected_intensity_column: xps_background_subtracted_intensity
  region_id_column: xps_background_subtraction_region_id
  min_points: 5
  reference_ids:
    - ref-xps-background-001
  regions:
    - region_id: xps-bgsub-c1s-001
      label: C 1s reviewed linear background
      binding_energy_window_eV: [280.0, 292.0]
      left_anchor_window_eV: [280.0, 281.0]
      right_anchor_window_eV: [291.0, 292.0]
      reference_ids:
        - ref-xps-background-001
      reviewer_notes:
        - User confirmed endpoint windows for a linear background preprocessing record.
      caveats:
        - Linear subtraction only; not a Shirley/Tougaard model.
      confidence: low
```

Optional reviewed Shirley background-subtraction parameters:

```yaml
background_subtraction:
  enabled: true
  method: reviewed_shirley_background_subtraction
  source: ea.xps.background_subtraction:v0.2
  input_intensity_column: processed_intensity
  min_points: 5
  max_iterations: 200
  tolerance: 1.0e-5
  reference_ids:
    - ref-xps-background-001
  regions:
    - region_id: xps-shirley-c1s-001
      label: C 1s reviewed Shirley background
      binding_energy_window_eV: [280.0, 292.0]
      left_anchor_window_eV: [280.0, 281.0]
      right_anchor_window_eV: [291.0, 292.0]
      reference_ids:
        - ref-xps-background-001
      reviewer_notes:
        - User confirmed endpoint windows and Shirley iteration settings.
      caveats:
        - Reviewed Shirley preprocessing only; not chemical-state proof.
      confidence: low
```

Linear and Shirley background subtraction write reviewed preprocessing columns and `xps_background_subtraction.yml`. They do not choose endpoints automatically, apply Tougaard subtraction, fit spin-orbit constrained peaks, calculate final composition, or prove chemical states.

Optional reviewed Tougaard U2 background-subtraction parameters:

```yaml
background_subtraction:
  enabled: true
  method: reviewed_tougaard_u2_background_subtraction
  source: ea.xps.background_subtraction:v0.2
  input_intensity_column: processed_intensity
  min_points: 5
  tougaard_B: 1200.0
  tougaard_C_eV2: 1643.0
  integration_direction: toward_higher_binding_energy
  reference_ids:
    - ref-xps-tougaard-001
  regions:
    - region_id: xps-tougaard-c1s-001
      label: C 1s reviewed Tougaard U2 background
      binding_energy_window_eV: [280.0, 292.0]
      left_anchor_window_eV: [280.0, 281.0]
      right_anchor_window_eV: [291.0, 292.0]
      reference_ids:
        - ref-xps-tougaard-001
      reviewer_notes:
        - User confirmed endpoint windows and Tougaard U2 B/C parameters.
      caveats:
        - Reviewed Tougaard U2 preprocessing only; not QUASES depth-profile modeling.
      confidence: low
```

Tougaard U2 subtraction writes reviewed preprocessing columns and `xps_background_subtraction.yml`. It requires a positive user-reviewed `B`; `C_eV2` and integration direction are recorded. EA does not auto-fit `B`, choose endpoints automatically, run QUASES/depth-profile modeling, fit spin-orbit constrained peaks, calculate final composition, or prove chemical states.

Optional reviewed component-fit screening parameters:

```yaml
component_fit:
  enabled: true
  method: reviewed_component_fit_screening
  source: ea.xps.component_fit:v0.2
  input_intensity_column: xps_background_subtracted_intensity
  fit_intensity_column: xps_component_fit_intensity
  residual_column: xps_component_fit_residual
  region_id_column: xps_component_fit_region_id
  min_points: 8
  max_nfev: 5000
  fit_quality_thresholds:
    max_rmse: 0.12
    min_r_squared: 0.70
  reference_ids:
    - ref-xps-fit-001
  regions:
    - region_id: xps-fit-c1s-region-001
      label: C 1s reviewed component-fit region
      binding_energy_window_eV: [282.0, 288.0]
      background_source: reviewed_background_subtraction_column
      components:
        - component_id: xps-fit-c1s-001
          label: C 1s reviewed Gaussian component
          element: C
          core_level: 1s
          peak_shape: gaussian
          initial_center_eV: 284.8
          center_bounds_eV: [283.5, 286.0]
          initial_amplitude: 0.8
          amplitude_bounds: [0.05, 1.5]
          initial_fwhm_eV: 3.2
          fwhm_bounds_eV: [0.8, 6.0]
          reference_ids:
            - ref-xps-fit-001
          reviewer_notes:
            - User confirmed component identity, peak shape, initial values, and bounds.
          caveats:
            - Reviewed component-fit screening only; not chemical-state proof.
          confidence: low
```

Component-fit screening writes reviewed fit/residual/region columns, `xps_component_fit.yml`, and `xps_component_fit.csv`. Spin-orbit constraints may use values reported by the user or values suggested from traceable sources, but source-backed values must preserve `parameter_origin`, source summary, applicability notes, and `reference_ids` before they are used as constraints. EA may discuss such candidate parameters in the report, but it does not choose components, backgrounds, bounds, peak shapes, chemical states, or final composition.

Optional reviewed spin-orbit constraints can be nested under a component-fit region:

```yaml
component_fit:
  enabled: true
  method: reviewed_component_fit_screening
  source: ea.xps.component_fit:v0.2
  input_intensity_column: processed_intensity
  fit_quality_thresholds:
    max_rmse: 0.12
    min_r_squared: 0.70
  regions:
    - region_id: xps-fit-fe2p-region-001
      label: Fe 2p reviewed spin-orbit constrained region
      binding_energy_window_eV: [706.0, 728.0]
      spin_orbit_constraints:
        - constraint_id: xps-spin-fe2p-001
          group_id: xps-spin-fe2p
          anchor_component_id: xps-fit-fe2p3-001
          dependent_component_id: xps-fit-fe2p1-001
          center_delta_eV: 13.4
          area_ratio: 0.5
          fwhm_ratio: 1.0
          parameter_origin: user_confirmed_source_suggested
          source_summary: Fe 2p doublet screening values were checked against the registered XPS reference before user confirmation.
          applicability_notes:
            - Applies only to the reviewed Fe 2p screening model and does not prove chemical state.
          reference_ids:
            - ref-xps-spin-orbit-001
          reviewer_notes:
            - User confirmed the source-backed signed separation, area ratio, and FWHM ratio.
          caveats:
            - Source-backed screening constraint only; not chemical-state proof.
          confidence: low
      components:
        - component_id: xps-fit-fe2p3-001
          label: Fe 2p3/2 reviewed anchor
          element: Fe
          core_level: 2p3/2
          peak_shape: gaussian
          spin_orbit_group_id: xps-spin-fe2p
          initial_center_eV: 711.0
          center_bounds_eV: [709.0, 713.0]
          initial_amplitude: 0.35
          amplitude_bounds: [0.05, 0.80]
          initial_fwhm_eV: 3.0
          fwhm_bounds_eV: [0.8, 5.0]
        - component_id: xps-fit-fe2p1-001
          label: Fe 2p1/2 reviewed dependent
          element: Fe
          core_level: 2p1/2
          peak_shape: gaussian
          spin_orbit_group_id: xps-spin-fe2p
          initial_center_eV: 724.4
          center_bounds_eV: [722.0, 726.5]
          initial_amplitude: 0.18
          amplitude_bounds: [0.02, 0.50]
          initial_fwhm_eV: 3.0
          fwhm_bounds_eV: [0.8, 5.0]
```

Spin-orbit constraints derive the dependent component from the fitted anchor using reviewed signed `center_delta_eV`, `area_ratio`, and `fwhm_ratio`, while intersecting reviewed bounds. The numbers may come from the user, a local reference library, or a source-backed lookup, but source-backed values must carry reference IDs and applicability notes. EA skips invalid constraints rather than silently fitting an unconstrained doublet. EA does not infer doublet identities, choose components, or prove chemical states/composition from the constraint alone.

Optional reviewed multi-region project-record parameters:

```yaml
region_records:
  enabled: true
  method: reviewed_multi_region_project_record
  source: ea.xps.region_records:v0.2
  min_points: 3
  default_calibration_group_id: xps-calibration-c1s-2848
  reference_ids:
    - ref-xps-region-001
  regions:
    - region_id: xps-region-survey-001
      label: Reviewed XPS survey record
      region_role: survey
      binding_energy_window_eV: [0.0, 1200.0]
      calibration_group_id: xps-calibration-c1s-2848
      reference_ids:
        - ref-xps-region-001
      reviewer_notes:
        - User confirmed this file is the survey-level project XPS context.
      caveats:
        - Survey region organization only; not quantitative composition.
      confidence: low
    - region_id: xps-region-c1s-001
      label: Reviewed C 1s core-level record
      region_role: core_level
      element: C
      core_level: 1s
      binding_energy_window_eV: [282.0, 288.0]
      calibration_group_id: xps-calibration-c1s-2848
      component_fit_ref: reviewed-user-note:component-fit-c1s
      reference_ids:
        - ref-xps-region-001
      reviewer_notes:
        - User linked this C 1s region to reviewed component-fit screening.
      caveats:
        - Core-level grouping only; not chemical-state proof.
      confidence: low
```

Region records write `xps_region_records.yml` and `xps_region_records.csv`. They organize reviewed survey/core-level/project-region context and linked output refs, but do not align spectra, share charge correction automatically, calculate formal multi-region composition, prove chemical states, or rank samples.

Future XPS work should add standard reference libraries, broader automated source connectors for suggestion packets, replicate/statistical comparisons, broader formal spin-orbit protocols beyond one-level anchor/dependent pairs, broader Tougaard variants with sourced parameter guidance, and user-confirmed memory-candidate generation from report interpretations.
