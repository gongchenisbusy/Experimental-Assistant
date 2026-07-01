# XPS Workflow

Use this reference when processing X-ray photoelectron spectroscopy spectra in EA v0.2.

Required gates:

1. Inspect the file and confirm it is XPS binding-energy spectral data.
2. Ask for or verify x/y columns and x-axis unit (`eV` or `unknown`).
3. Ask for or verify binding-energy calibration before analysis. Record `energy_shift_eV`, `calibration_reference`, and `calibration_review_ref`.
4. Ask for or verify processing parameters before analysis.
5. If component quantification, background-model documentation, or numeric linear background subtraction is requested, ask the user to confirm `component_quantification`, `background_model`, and/or `background_subtraction` parameters: reviewed component IDs/labels, elements/core levels, binding-energy/background windows, linear-subtraction anchor points/windows, integration baseline, model/background notes, software/tool provenance, and sensitivity factors when atomic-percent screening is desired.
6. Keep raw data untouched; write processed outputs outside `raw/`.
7. Record baseline handling, smoothing, normalization, detected screening peaks, optional component screening, optional reviewed background-model record, optional reviewed linear background-subtraction record, generated figure, report, and provenance.
8. Treat automatic peaks, reviewed linear background-subtracted columns, and component screening estimates as screening evidence. Use calibration context, background model, peak model, references, and user review before writing chemical-state conclusions.
9. Write memory candidates only after user confirmation.

Current v0.2 XPS support:

- Raw import uses `ea raw import --characterization-type xps`.
- Inspection identifies common XPS files by path/name, binding-energy metadata, and binding-energy-like ranges.
- Processing supports user-confirmed energy shift, optional rolling-quantile baseline correction, optional Savitzky-Golay smoothing, max-intensity normalization, SciPy peak detection, disabled-by-default `component_quantification` screening from reviewed binding-energy windows, disabled-by-default `background_model` records for reviewed Shirley/Tougaard/linear/local-minimum/rolling-quantile choices, and disabled-by-default `background_subtraction` numeric linear subtraction inside reviewed regions with reviewed anchor points/windows.
- Processed CSV files include `binding_energy_raw`, calibrated `binding_energy_eV`, `raw_intensity`, optional `baseline_signal`, optional `smoothed_intensity`, and `processed_intensity`.
- When `background_subtraction.enabled` is true with method `reviewed_linear_background_subtraction`, processed CSV files also include the reviewed background column, background-subtracted intensity column, and region ID column for the supplied binding-energy windows.
- Peak tables include `binding_energy_eV`, raw energy, prominence, component model status, possible assignment, assignment confidence, and assignment source.
- When `component_quantification.enabled` is true, EA writes `xps_components.csv` with reviewed component windows, integrated area, relative area percent, sensitivity factor, RSF-corrected area, and `relative_atomic_percent_screening` when all included components have valid positive sensitivity factors.
- When `background_model.enabled` is true, EA writes `xps_background.yml` with reviewed background region/model choices, windows, software/tool refs, reference IDs, reviewer notes, caveats, and whether the background had already been applied outside EA.
- When `background_subtraction.enabled` is true, EA writes `xps_background_subtraction.yml` with reviewed linear subtraction regions, left/right anchors, output columns, references, warnings, caveats, and confidence.
- Reports include an embedded XPS figure, original figure path, calibration/background section, peak table, optional component screening table, confidence-labeled possible interpretations, file links, References, and provenance.
- XPS component quantification is screening-only. XPS background model records are provenance only. XPS linear background subtraction is reviewed numeric preprocessing only. EA does not perform definitive chemical-state assignment, formal quantitative composition, surface stoichiometry, automatic Shirley/Tougaard subtraction, or spin-orbit constrained fitting.

CLI path:

```bash
ea raw import /path/to/ea-project /path/to/raw-xps.txt --characterization-type xps --sample-ref sample-001 --experiment-ref exp-001
ea xps inspect /path/to/ea-project raw/xps/char-20260630-001/raw-xps.txt
ea review add /path/to/ea-project --target-type xps_columns --target-ref raw/xps/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "x=binding_energy_eV, y=intensity, unit=eV"
ea review add /path/to/ea-project --target-type xps_calibration --target-ref raw/xps/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "C 1s reference at 284.8 eV; energy_shift_eV=0.0"
ea review add /path/to/ea-project --target-type xps_parameters --target-ref raw/xps/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default XPS parameters confirmed"
ea xps process /path/to/ea-project --metadata raw/xps/char-20260630-001/metadata.yml --x-column binding_energy_eV --y-column intensity --x-unit eV --energy-shift-ev 0.0 --calibration-reference "C 1s 284.8 eV user-confirmed reference" --column-review-ref review-20260630-001 --calibration-review-ref review-20260630-002 --parameter-review-ref review-20260630-003 --sample-ref sample-001
ea xps report /path/to/ea-project --metadata processed/sample-001/xps/res-project-xps-20260630-001/xps_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
```

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

Linear background subtraction writes reviewed preprocessing columns and `xps_background_subtraction.yml`. It does not choose endpoints automatically, apply Shirley/Tougaard subtraction, fit spin-orbit constrained peaks, calculate final composition, or prove chemical states.

Future XPS work should add numeric user-confirmed Shirley/Tougaard subtraction workflows, constrained peak fitting, spin-orbit pair handling, standard reference libraries, multi-region project records, replicate/statistical comparisons, and user-confirmed memory-candidate generation from report interpretations.
