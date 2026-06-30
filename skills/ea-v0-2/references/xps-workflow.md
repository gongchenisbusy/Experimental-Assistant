# XPS Workflow

Use this reference when processing X-ray photoelectron spectroscopy spectra in EA v0.2.

Required gates:

1. Inspect the file and confirm it is XPS binding-energy spectral data.
2. Ask for or verify x/y columns and x-axis unit (`eV` or `unknown`).
3. Ask for or verify binding-energy calibration before analysis. Record `energy_shift_eV`, `calibration_reference`, and `calibration_review_ref`.
4. Ask for or verify processing parameters before analysis.
5. Keep raw data untouched; write processed outputs outside `raw/`.
6. Record baseline handling, smoothing, normalization, detected screening peaks, generated figure, report, and provenance.
7. Treat automatic peaks as screening evidence. Use calibration context, background model, peak model, references, and user review before writing chemical-state conclusions.
8. Write memory candidates only after user confirmation.

Current v0.2 XPS support:

- Raw import uses `ea raw import --characterization-type xps`.
- Inspection identifies common XPS files by path/name, binding-energy metadata, and binding-energy-like ranges.
- Processing supports user-confirmed energy shift, optional rolling-quantile baseline correction, optional Savitzky-Golay smoothing, max-intensity normalization, and SciPy peak detection.
- Processed CSV files include `binding_energy_raw`, calibrated `binding_energy_eV`, `raw_intensity`, optional `baseline_signal`, optional `smoothed_intensity`, and `processed_intensity`.
- Peak tables include `binding_energy_eV`, raw energy, prominence, component model status, possible assignment, assignment confidence, and assignment source.
- Reports include an embedded XPS figure, original figure path, calibration section, peak table, confidence-labeled possible interpretations, file links, References, and provenance.
- First-pass XPS support does not perform chemical-state assignment, quantitative composition, Shirley/Tougaard background modeling, spin-orbit constrained fitting, or sensitivity-factor quantification.

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

Future XPS work should add user-confirmed Shirley/Tougaard background modes, constrained component fitting, spin-orbit pair handling, sensitivity-factor quantification, standard reference libraries, multi-region project records, and user-confirmed memory-candidate generation from report interpretations.
