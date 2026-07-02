# Electrochemistry Workflow

Use this reference when processing tabular electrochemical data in the EA v0.9 RC compatibility skill.

Required gates:

1. Inspect the file and confirm it is electrochemical potential/current, time/current, time/voltage GCD, or EIS Nyquist impedance data.
2. Ask for or verify x/y columns, x-axis unit (`V`, `mV`, `s`, `ohm`, or `unknown`), current unit (`A`, `mA`, `uA`, `µA`, or `unknown`), and measurement mode (`cv`, `lsv`, `chrono`, `gcd`, `eis`, or `unknown`). For `eis`, confirm that x/y are real impedance and imaginary or negative-imaginary impedance columns; use `current_unit=unknown`. For time/voltage GCD, confirm `x_unit=s`, `measurement_mode=gcd`, and set `current_unit=unknown`; reviewed discharge current belongs in `gcd_analysis`.
3. Ask for or verify electrode/electrolyte/reference-electrode/protocol context before analysis. Record `context_summary`, optional `electrode_area_cm2`, and `context_review_ref`.
4. Ask for or verify processing parameters before analysis.
5. Keep raw data untouched; write processed outputs outside `raw/`.
6. Record unit conversion, optional current-density normalization, smoothing, optional reviewed potential conversion, optional reviewed iR drop correction, optional reviewed EIS circuit-fit screening, optional reviewed Tafel/overpotential screening fit, optional reviewed GCD discharge metrics, detected screening features, optional EIS Nyquist screening features, optional reviewed correction/reference record, generated figure, report, and provenance.
7. Treat automatic features, EIS screening estimates, EIS circuit-fit screening records, potential-conversion records, iR-drop-correction records, Tafel/overpotential screening records, GCD discharge-metrics records, and correction/reference records as screening/provenance evidence. Use protocol context, replicates, normalization, reference-electrode calibration, frequency order, equivalent-circuit assumptions, and literature before writing performance or mechanism conclusions.
8. Write memory candidates only after user confirmation.

Current EA v0.9 RC electrochemistry compatibility support:

- Raw import uses `ea raw import --characterization-type electrochemistry`.
- Inspection identifies common electrochemistry files by path/name, metadata, potential/current columns, time/current columns, and mode hints.
- Processing supports current conversion to mA, optional current-density calculation from reviewed electrode area, optional Savitzky-Golay smoothing, disabled-by-default reviewed offset potential conversion, disabled-by-default reviewed iR drop correction, disabled-by-default reviewed EIS circuit-fit screening, disabled-by-default reviewed Tafel/overpotential screening fits, disabled-by-default reviewed GCD discharge metrics, SciPy feature detection for CV/LSV-like traces, simple threshold-current summaries, start/end current summaries for chrono/GCD-style data, EIS Nyquist screening for reviewed two-column impedance data, and disabled-by-default correction/reference records.
- Processed CSV files include `axis_raw`, `current_raw`, converted `current_mA`, optional `potential_V` or `time_s`, optional `current_density_mA_cm-2`, and processed current columns. When reviewed `potential_conversion.enabled` is true and `potential_V` exists, EA also writes the configured converted potential column. When reviewed `ir_drop_correction.enabled` is true and valid potential/current/Ru inputs exist, EA writes an iR drop column and corrected potential column. When reviewed `tafel_analysis.enabled` is true and valid potential/current/current-density/window inputs exist, EA writes log-current, fit-potential, and optional overpotential columns. When reviewed `gcd_analysis.enabled` is true and valid time/voltage/current/window inputs exist, EA writes GCD voltage and reviewed-discharge-segment columns.
- EIS processed CSV files include `z_real_ohm`, signed `z_imag_ohm`, plotted `neg_z_imag_ohm`, impedance magnitude, and an imaginary-column convention record. When reviewed `eis_circuit_fit.enabled` is true and valid frequency/model/initial/bound inputs exist, EA also writes reviewed frequency and fitted impedance columns.
- Feature tables include feature ID/type, axis value/unit, potential/time or impedance coordinates when available, current or impedance values, optional current density, prominence, method, confidence, and assignment source.
- When `potential_conversion.enabled` is reviewed, EA writes `electrochemistry_potential_conversion.yml` with input/target scales, numeric offset, equation/provenance notes, output column, reference electrode, references, caveats, confidence, source, boundary, and record ref. The conversion changes processed/plot coordinates only and keeps the raw `potential_V` column.
- When `ir_drop_correction.enabled` is reviewed, EA writes `electrochemistry_ir_drop_correction.yml` with Ru, compensation fraction, sign convention/formula, potential/current input columns, iR drop column, corrected potential column, references, caveats, confidence, source, boundary, and record ref. The correction changes processed/plot coordinates only and keeps prior potential columns.
- When `eis_circuit_fit.enabled` is reviewed, EA writes `electrochemistry_eis_circuit_fit.yml` with frequency/impedance input columns, frequency unit, imaginary convention, circuit model, initial values, parameter bounds, fitted parameters, fit-quality metrics/checks, perturbation/context notes, references, caveats, confidence, source, boundary, and record ref. EA fits only the reviewed model with reviewed inputs and does not choose a circuit automatically.
- When `tafel_analysis.enabled` is reviewed, EA writes `electrochemistry_tafel_analysis.yml` with potential/current input columns, current unit, reviewed fit window, log-current column, optional overpotential reference/column, fit statistics, references, caveats, confidence, source, boundary, and record ref. EA may suggest source-backed kinetic windows, but fits only inside the reviewed window.
- When `gcd_analysis.enabled` is reviewed, EA writes `electrochemistry_gcd_analysis.yml` with time/voltage input columns, voltage unit, reviewed discharge time and voltage windows, reviewed discharge current, mass/area/loading metadata, charge/capacity/capacitance metrics, references, caveats, confidence, source, boundary, and record ref. EA may suggest source-backed charge/discharge segments, but calculates only inside the reviewed discharge window.
- When `correction_record.enabled` is reviewed, EA writes `electrochemistry_correction.yml` with reference electrode, converted potential scale, uncompensated resistance, iR compensation, correction notes, confidence, source, boundary, and record ref.
- Reports include an embedded electrochemistry figure, original figure path, context section, optional potential-conversion summary/link, optional iR-drop-correction summary/link, optional EIS circuit-fit screening summary/link, optional Tafel/overpotential summary/link, optional GCD discharge-metrics summary/link, optional correction/reference record summary/link, feature table, current/EIS Nyquist/GCD summary, confidence-labeled possible interpretations, file links, References, and provenance.
- `correction_record` is disabled by default. Enable it only after the user reviews reference-electrode scale, converted scale/offset, uncompensated resistance, iR compensation status, and correction notes. This record is metadata/provenance only; EA v0.9 RC does not automatically shift potential, apply iR correction, fit circuits, or calculate Tafel/GCD/performance metrics from it.
- `potential_conversion` is disabled by default. Enable it only after the user reviews the input scale, target scale, numeric offset in volts, equation/source, and reference-electrode context. This step is a coordinate transform only; it is not iR compensation, Tafel analysis, equivalent-circuit fitting, GCD performance calculation, catalyst ranking, or mechanistic proof.
- `ir_drop_correction` is disabled by default. Enable it only after the user reviews Ru, compensation fraction, sign convention/formula, current input column/unit, potential input column, and caveats. This step is a coordinate correction only; it is not Tafel analysis, equivalent-circuit fitting, GCD performance calculation, overpotential proof, catalyst ranking, or mechanistic proof.
- `eis_circuit_fit` is disabled by default. Enable it only after the user reviews the frequency column/unit/order, real and imaginary impedance columns, imaginary sign convention, circuit model, initial values, parameter bounds, fit-quality thresholds, perturbation amplitude/context, and caveats. This step is a reviewed screening fit only; it is not automatic circuit selection, Rct/Warburg proof, device-performance proof, replicate statistics, catalyst ranking, Tafel analysis, GCD analysis, or mechanistic proof.
- `tafel_analysis` is disabled by default. Enable it only after the user reviews the potential/current or current-density input columns, current unit, kinetic fit window, reference scale, optional overpotential reference, and caveats. This step is a reviewed screening fit only; it is not automatic kinetic-window selection, exchange-current proof, catalyst ranking, equivalent-circuit fitting, GCD performance calculation, stability assessment, or mechanistic proof.
- `gcd_analysis` is disabled by default. Enable it only after the user reviews the time column, voltage signal column/unit, discharge current magnitude/sign convention, discharge time window, voltage window, and mass/area/loading metadata. This step is a reviewed discharge-window metrics record only; it is not automatic segment selection, current-sign inference, rate-capability/stability assessment, device-performance proof, catalyst ranking, equivalent-circuit fitting, Tafel analysis, or mechanistic proof.
- First-pass support does not perform automatic equivalent-circuit selection, durable Randles/Rct/Warburg assignment, automatic kinetic/discharge-window selection, formal overpotential proof, automatic IR/Ru inference, automatic reference-electrode constant inference, replicate statistics, rate-capability/cycling-stability assessment, or device-performance claims.

CLI path:

```bash
ea raw import /path/to/ea-project /path/to/raw-electrochemistry.txt --characterization-type electrochemistry --sample-ref sample-001 --experiment-ref exp-001
ea electrochemistry inspect /path/to/ea-project raw/electrochemistry/char-20260630-001/raw-electrochemistry.txt
ea review add /path/to/ea-project --target-type electrochemistry_columns --target-ref raw/electrochemistry/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "x=potential_V, y=current_mA, x_unit=V, current_unit=mA, mode=cv"
ea review add /path/to/ea-project --target-type electrochemistry_context --target-ref raw/electrochemistry/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "working electrode area=0.196 cm2; electrolyte/reference/protocol confirmed"
ea review add /path/to/ea-project --target-type electrochemistry_parameters --target-ref raw/electrochemistry/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default electrochemistry parameters confirmed"
ea electrochemistry process /path/to/ea-project --metadata raw/electrochemistry/char-20260630-001/metadata.yml --x-column potential_V --y-column current_mA --x-unit V --current-unit mA --measurement-mode cv --context-summary "0.196 cm2 working electrode; user-confirmed electrolyte/reference/protocol" --electrode-area-cm2 0.196 --column-review-ref review-20260630-001 --context-review-ref review-20260630-002 --parameter-review-ref review-20260630-003 --sample-ref sample-001
ea electrochemistry report /path/to/ea-project --metadata processed/sample-001/electrochemistry/res-project-electrochemistry-20260630-001/electrochemistry_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
```

For EIS Nyquist screening, use reviewed `--x-unit ohm --current-unit unknown --measurement-mode eis` and confirm whether the y column is `Zimag` or `-Zimag`; EA records the convention and plots positive `-Zimag`.

Optional reviewed correction/reference metadata can be supplied with `--parameters-json` or `--parameters-file`:

```yaml
correction_record:
  enabled: true
  method: reviewed_metadata_record
  source: ea.electrochemistry.correction_record:v0.2
  reference_electrode:
    type: Ag/AgCl
    electrolyte: sat_KCl
    status: reviewed
  converted_potential_scale:
    target_scale: RHE
    offset_V: 0.966
    equation: E_RHE = E_AgAgCl + 0.197 + 0.0591*pH
    applied_to_processed_data: false
  uncompensated_resistance:
    ru_ohm: 18.5
    source: EIS high-frequency intercept
    status: reviewed
  ir_compensation:
    status: instrument_applied
    fraction: 0.85
    mode: positive_feedback
  correction_notes:
    - EA records correction metadata only; no potential shift or iR correction is applied.
```

Optional reviewed potential conversion can be supplied with `--parameters-json` or `--parameters-file`:

```yaml
potential_conversion:
  enabled: true
  method: reviewed_offset_conversion
  source: ea.electrochemistry.potential_conversion:v0.2
  input_scale: Ag/AgCl_sat_KCl
  target_scale: RHE
  offset_V: 0.966
  equation: E_RHE = E_AgAgCl + 0.197 + 0.0591*pH
  output_column: potential_RHE_V
  reference_electrode:
    type: Ag/AgCl
    electrolyte: sat_KCl
    status: reviewed
  reference_ids:
    - ref-project-method-001
  reviewer_notes:
    - Numeric offset was user-reviewed for this electrolyte and pH.
  caveats:
    - Confirm reference calibration and pH before comparing overpotential values.
```

Optional reviewed iR drop correction can be supplied with `--parameters-json` or `--parameters-file`:

```yaml
ir_drop_correction:
  enabled: true
  method: reviewed_ir_drop_correction
  source: ea.electrochemistry.ir_drop_correction:v0.2
  potential_input_column: potential_RHE_V
  current_input_column: processed_current_mA
  current_unit: mA
  ru_ohm: 18.5
  compensation_fraction: 0.85
  sign_convention: subtract_i_ru
  formula: E_iR = E_RHE - I_A * Ru * 0.85
  output_column: potential_RHE_iR_corrected_V
  drop_column: ir_drop_V
  reference_ids:
    - ref-project-method-001
  reviewer_notes:
    - Ru and sign convention were user-reviewed for this protocol.
  caveats:
    - Do not use this correction alone as a Tafel, overpotential, or performance claim.
```

Optional reviewed EIS circuit-fit screening can be supplied with `--parameters-json` or `--parameters-file`. This requires a reviewed frequency column in the raw table in addition to reviewed Nyquist x/y columns:

```yaml
eis_circuit_fit:
  enabled: true
  method: reviewed_eis_circuit_fit
  source: ea.electrochemistry.eis_circuit_fit:v0.2
  frequency_input_column: frequency_Hz
  frequency_unit: Hz
  z_real_input_column: z_real_ohm
  z_imag_input_column: z_imag_ohm
  imaginary_input_convention: signed_z_imag_ohm
  circuit_model: series_r_rc
  initial_values:
    rs_ohm: 8.0
    rct_ohm: 72.0
    c_dl_F: 0.001
  bounds:
    rs_ohm:
      min: 0.0
      max: 50.0
    rct_ohm:
      min: 0.0
      max: 500.0
    c_dl_F:
      min: 0.000001
      max: 0.1
  fit_quality_thresholds:
    max_reduced_chi_square_ohm2: 10.0
    min_r_squared_complex: 0.95
  perturbation_amplitude_mV: 10.0
  frequency_order_reviewed: true
  reference_ids:
    - ref-project-method-001
  reviewer_notes:
    - Circuit model, frequency order, initial values, and bounds were reviewed for this protocol.
  caveats:
    - Screening fit only; do not claim mechanism or device performance without replicates and model justification.
```

Optional reviewed Tafel/overpotential screening can be supplied with `--parameters-json` or `--parameters-file`:

```yaml
tafel_analysis:
  enabled: true
  method: reviewed_tafel_linear_fit
  source: ea.electrochemistry.tafel_analysis:v0.2
  potential_input_column: potential_RHE_iR_corrected_V
  current_input_column: processed_current_density_mA_cm-2
  current_unit: mA cm^-2
  fit_window_V:
    min: 1.45
    max: 1.55
  minimum_points: 5
  minimum_log_span_decades: 0.5
  fit_potential_column: tafel_fit_potential_V
  overpotential_reference_V: 1.23
  overpotential_column: overpotential_RHE_V
  reference_scale: RHE
  reference_ids:
    - ref-project-method-001
  reviewer_notes:
    - Kinetic window and normalization were user-reviewed for this protocol.
  caveats:
    - Screening fit only; do not rank catalysts without replicates and protocol review.
```

Optional reviewed GCD discharge metrics can be supplied with `--parameters-json` or `--parameters-file`. For time/voltage GCD data, the generic `y-column` is stored internally as `current_raw`; set `voltage_input_column: current_raw` unless a dedicated processed voltage column is already available:

```yaml
gcd_analysis:
  enabled: true
  method: reviewed_gcd_discharge_metrics
  source: ea.electrochemistry.gcd_analysis:v0.2
  time_input_column: time_s
  voltage_input_column: current_raw
  voltage_unit: V
  voltage_output_column: gcd_voltage_V
  segment_column: gcd_discharge_segment
  discharge_time_window_s:
    start: 0.0
    end: 100.0
  voltage_window_V:
    min: 0.5
    max: 1.0
  discharge_current_mA: 2.0
  current_sign_convention: reviewed_discharge_current_magnitude
  mass_mg: 4.0
  area_cm2: 1.0
  active_material_loading_mg_cm2: 4.0
  reference_ids:
    - ref-project-method-001
  reviewer_notes:
    - Discharge segment, current, mass, and area were user-reviewed for this protocol.
  caveats:
    - Screening metric only; do not claim rate capability or cycling stability without replicates.
```

Future electrochemistry work should add broader equivalent-circuit libraries, replicate comparison, protocol-aware validation, richer reference-electrode/iR/Tafel/GCD/EIS guidance helpers, and user-confirmed memory-candidate generation from report interpretations.
