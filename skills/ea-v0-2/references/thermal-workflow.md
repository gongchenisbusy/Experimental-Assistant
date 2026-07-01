# Thermal Analysis Workflow

Use this reference when processing tabular TGA, DSC, or DTG-style thermal analysis data in EA v0.2.

Required gates:

1. Inspect the file and confirm it is thermal analysis temperature/signal data.
2. Ask for or verify temperature/signal columns, temperature unit (`C`, `K`, or `unknown`), signal unit (`%`, `mg`, `mW`, `W/g`, `mW/mg`, or `unknown`), and measurement mode (`tga`, `dsc`, `dtg`, or `unknown`).
3. Ask for or verify temperature program, atmosphere, sample mass, DSC sign convention, and baseline/reference context before analysis. Record `context_summary` and `context_review_ref`.
4. Ask for or verify processing parameters before analysis.
5. Keep raw data untouched; write processed outputs outside `raw/`.
6. Record temperature conversion, optional smoothing, optional reviewed `baseline_correction`, derivative/mass-loss summaries, detected screening events, optional reviewed `transition_analysis`, optional reviewed `context_record`, generated figure, report, and provenance.
7. Treat automatic events as screening evidence. Use protocol context, baselines, replicates, instrument settings, and literature before writing decomposition, transition, kinetic, composition, or thermal-stability conclusions.
8. Write memory candidates only after user confirmation.

Current v0.2 thermal support:

- Raw import uses `ea raw import --characterization-type thermal_analysis`.
- Inspection identifies common thermal files by path/name, metadata, temperature columns, mass/heat-flow columns, and mode hints.
- Processing supports `C`/`K` temperature handling, TGA mass-percent normalization from `%` or `mg`, optional Savitzky-Golay smoothing, optional reviewed linear baseline correction for DSC/DTG-style traces, optional reviewed-window transition screening for DSC Tg/Tm/Tc-style candidates, mass derivative summaries, SciPy event detection for TGA/DSC/DTG traces, and simple mass-loss threshold summaries.
- Processed CSV files include `temperature_raw`, `temperature_C`, `signal_raw`, `processed_signal`, and method-specific processed columns such as `processed_mass_percent`, `mass_derivative_percent_per_C`, `processed_heat_flow`, or `processed_dtg_signal`. When reviewed baseline correction is enabled, they also include `baseline_estimate` and `baseline_corrected_signal`.
- Feature tables include event ID/type, temperature, signal value, mass percent, derivative, heat-flow/DTG values when available, prominence, method, confidence, and assignment source.
- Optional disabled-by-default `context_record` preserves reviewed DSC sign convention, baseline/reference handling, sample context, atmosphere/program context, and correction notes in `thermal_context.yml`.
- Optional disabled-by-default `baseline_correction` applies a reviewed two-point linear baseline to DSC/DTG-style traces and records `thermal_baseline.yml`.
- Optional disabled-by-default `transition_analysis` screens user-reviewed DSC windows for Tg/Tm/Tc-style candidate metrics and records `thermal_transitions.csv` plus `thermal_transitions.yml`.
- Reports include an embedded thermal figure, original figure path, context section, optional baseline-correction section, optional transition-screening section, optional context-record section, event table, mass/signal summary, confidence-labeled possible interpretations, file links, References, and provenance.
- First-pass support does not perform formal glass-transition assignment, melting/crystallization assignment, decomposition mechanism identification, kinetic modeling, non-linear/reference correction, replicate statistics, or formal thermal-stability ranking.

CLI path:

```bash
ea raw import /path/to/ea-project /path/to/raw-tga.txt --characterization-type thermal_analysis --sample-ref sample-001 --experiment-ref exp-001
ea thermal inspect /path/to/ea-project raw/thermal_analysis/char-20260630-001/raw-tga.txt
ea review add /path/to/ea-project --target-type thermal_columns --target-ref raw/thermal_analysis/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "temperature=temperature_C, signal=mass_percent, temperature_unit=C, signal_unit=%, mode=tga"
ea review add /path/to/ea-project --target-type thermal_context --target-ref raw/thermal_analysis/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "N2 atmosphere; 10 C/min; sample mass and baseline reviewed"
ea review add /path/to/ea-project --target-type thermal_parameters --target-ref raw/thermal_analysis/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default thermal parameters confirmed"
ea thermal process /path/to/ea-project --metadata raw/thermal_analysis/char-20260630-001/metadata.yml --temperature-column temperature_C --signal-column mass_percent --temperature-unit C --signal-unit % --measurement-mode tga --context-summary "N2 atmosphere; 10 C/min; sample mass and baseline reviewed" --column-review-ref review-20260630-001 --context-review-ref review-20260630-002 --parameter-review-ref review-20260630-003 --sample-ref sample-001
ea thermal report /path/to/ea-project --metadata processed/sample-001/thermal_analysis/res-project-thermal-analysis-20260630-001/thermal_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
```

Optional context-record parameters:

```yaml
context_record:
  enabled: true
  dsc_sign_convention:
    exotherm_direction: up
    endotherm_direction: down
    status: reviewed
  baseline_reference:
    baseline_method: instrument_linear_baseline
    reference_pan: empty aluminum pan
    numeric_correction: instrument_applied
  sample_context:
    sample_mass_mg: 5.2
    pan: sealed aluminum
  atmosphere_program:
    atmosphere: N2
    heating_rate_C_min: 10
  correction_notes:
    - Record context only; do not auto-assign Tg/Tm/Tc or kinetics from this metadata.
```

The context record is metadata/provenance only. It does not invert DSC signs, apply baseline/reference correction, assign Tg/Tm/Tc, fit kinetics, or prove decomposition/melting/crystallization mechanisms.

Optional baseline-correction parameters:

```yaml
baseline_correction:
  enabled: true
  method: linear_two_point
  anchor_strategy: reviewed_trace_edges
  anchor_temperatures_C:
    - 25.0
    - 300.0
```

Baseline correction is a reviewed numeric processing step for DSC/DTG-style traces. It does not assign Tg/Tm/Tc, fit kinetics, rank thermal stability, or prove decomposition/melting/crystallization mechanisms.

Optional transition-screening parameters:

```yaml
transition_analysis:
  enabled: true
  method: reviewed_window_screening
  transitions:
    - transition_id: tg-001
      transition_type: Tg
      temperature_window_C: [85.0, 105.0]
      signal_direction: auto
    - transition_id: tm-001
      transition_type: Tm
      temperature_window_C: [135.0, 155.0]
      signal_direction: endotherm_down
    - transition_id: tc-001
      transition_type: Tc
      temperature_window_C: [200.0, 220.0]
      signal_direction: exotherm_up
```

Transition screening extracts candidate metrics only inside reviewed DSC windows. It does not make formal Tg/Tm/Tc assignments, fit kinetics, rank thermal stability, or prove decomposition/melting/crystallization mechanisms.

Future thermal work should add formal user-confirmed transition assignment workflows, non-linear/reference correction workflows, kinetic models, replicate comparison, reference libraries, and user-confirmed memory-candidate generation from report interpretations.
