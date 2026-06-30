# XPS Workflow

Use this reference when processing X-ray photoelectron spectroscopy spectra in EA v0.2.

Required gates:

1. Inspect the file and confirm it is XPS binding-energy spectral data.
2. Ask for or verify x/y columns and x-axis unit (`eV` or `unknown`).
3. Ask for or verify binding-energy calibration before analysis. Record `energy_shift_eV`, `calibration_reference`, and `calibration_review_ref`.
4. Ask for or verify processing parameters before analysis.
5. If component quantification is requested, ask the user to confirm `component_quantification` parameters: reviewed component IDs/labels, elements/core levels, binding-energy windows, integration baseline, model/background notes, and sensitivity factors when atomic-percent screening is desired.
6. Keep raw data untouched; write processed outputs outside `raw/`.
7. Record baseline handling, smoothing, normalization, detected screening peaks, optional component screening, generated figure, report, and provenance.
8. Treat automatic peaks and component screening estimates as screening evidence. Use calibration context, background model, peak model, references, and user review before writing chemical-state conclusions.
9. Write memory candidates only after user confirmation.

Current v0.2 XPS support:

- Raw import uses `ea raw import --characterization-type xps`.
- Inspection identifies common XPS files by path/name, binding-energy metadata, and binding-energy-like ranges.
- Processing supports user-confirmed energy shift, optional rolling-quantile baseline correction, optional Savitzky-Golay smoothing, max-intensity normalization, SciPy peak detection, and disabled-by-default `component_quantification` screening from reviewed binding-energy windows.
- Processed CSV files include `binding_energy_raw`, calibrated `binding_energy_eV`, `raw_intensity`, optional `baseline_signal`, optional `smoothed_intensity`, and `processed_intensity`.
- Peak tables include `binding_energy_eV`, raw energy, prominence, component model status, possible assignment, assignment confidence, and assignment source.
- When `component_quantification.enabled` is true, EA writes `xps_components.csv` with reviewed component windows, integrated area, relative area percent, sensitivity factor, RSF-corrected area, and `relative_atomic_percent_screening` when all included components have valid positive sensitivity factors.
- Reports include an embedded XPS figure, original figure path, calibration section, peak table, optional component screening table, confidence-labeled possible interpretations, file links, References, and provenance.
- XPS component quantification is screening-only. EA does not perform definitive chemical-state assignment, formal quantitative composition, surface stoichiometry, Shirley/Tougaard background modeling, or spin-orbit constrained fitting.

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

Future XPS work should add user-confirmed Shirley/Tougaard background modes, constrained peak fitting, spin-orbit pair handling, standard reference libraries, multi-region project records, replicate/statistical comparisons, and user-confirmed memory-candidate generation from report interpretations.
