# Electrochemistry Workflow

Use this reference when processing tabular electrochemical data in EA v0.2.

Required gates:

1. Inspect the file and confirm it is electrochemical potential/current, time/current, or EIS Nyquist impedance data.
2. Ask for or verify x/y columns, x-axis unit (`V`, `mV`, `s`, `ohm`, or `unknown`), current unit (`A`, `mA`, `uA`, `µA`, or `unknown`), and measurement mode (`cv`, `lsv`, `chrono`, `gcd`, `eis`, or `unknown`). For `eis`, confirm that x/y are real impedance and imaginary or negative-imaginary impedance columns; use `current_unit=unknown`.
3. Ask for or verify electrode/electrolyte/reference-electrode/protocol context before analysis. Record `context_summary`, optional `electrode_area_cm2`, and `context_review_ref`.
4. Ask for or verify processing parameters before analysis.
5. Keep raw data untouched; write processed outputs outside `raw/`.
6. Record unit conversion, optional current-density normalization, smoothing, detected screening features, optional EIS Nyquist screening features, generated figure, report, and provenance.
7. Treat automatic features and EIS screening estimates as screening evidence. Use protocol context, replicates, normalization, reference-electrode correction, frequency order, equivalent-circuit assumptions, and literature before writing performance or mechanism conclusions.
8. Write memory candidates only after user confirmation.

Current v0.2 electrochemistry support:

- Raw import uses `ea raw import --characterization-type electrochemistry`.
- Inspection identifies common electrochemistry files by path/name, metadata, potential/current columns, time/current columns, and mode hints.
- Processing supports current conversion to mA, optional current-density calculation from reviewed electrode area, optional Savitzky-Golay smoothing, SciPy feature detection for CV/LSV-like traces, simple threshold-current summaries, start/end current summaries for chrono/GCD-style data, and EIS Nyquist screening for reviewed two-column impedance data.
- Processed CSV files include `axis_raw`, `current_raw`, converted `current_mA`, optional `potential_V` or `time_s`, optional `current_density_mA_cm-2`, and processed current columns.
- EIS processed CSV files include `z_real_ohm`, signed `z_imag_ohm`, plotted `neg_z_imag_ohm`, impedance magnitude, and an imaginary-column convention record.
- Feature tables include feature ID/type, axis value/unit, potential/time or impedance coordinates when available, current or impedance values, optional current density, prominence, method, confidence, and assignment source.
- Reports include an embedded electrochemistry figure, original figure path, context section, feature table, current or EIS Nyquist summary, confidence-labeled possible interpretations, file links, References, and provenance.
- First-pass support does not perform equivalent-circuit fitting, Randles/Rct assignment, Warburg analysis, Tafel analysis, overpotential extraction, capacitance/capacity calculation, IR correction, reference-electrode conversion, replicate statistics, or device-performance claims.

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

Future electrochemistry work should add dedicated equivalent-circuit fitting, Tafel/overpotential workflows, GCD capacitance/capacity calculations, reference-electrode conversion helpers, IR compensation metadata, replicate comparison, protocol-aware validation, and user-confirmed memory-candidate generation from report interpretations.
