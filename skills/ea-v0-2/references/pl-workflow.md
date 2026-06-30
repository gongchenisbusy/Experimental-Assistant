# PL Workflow

Use this reference when processing photoluminescence spectra in EA v0.2.

Required gates:

1. Inspect the file and confirm it is PL, not Raman or unknown.
2. Ask for or verify x/y columns and x-axis unit (`eV`, `nm`, or `unknown`).
3. Ask for or verify processing parameters before analysis.
4. Keep raw data untouched; write processed outputs outside `raw/`.
5. Record smoothing, normalization, peak detection, generated figure, report, and provenance.
6. Mark PL peaks in figures and put peak position, optional wavelength, prominence, and assignment confidence in report tables.
7. Interpret emission features with project context and literature references. Use confidence labels rather than definitive mechanism claims.
8. Write memory candidates only after user confirmation.

Current v0.2 PL support:

- Raw import uses `ea raw import --characterization-type pl`.
- Inspection reuses the spectrum reader and identifies common PL files by filename, `AxisUnit[1]=eV`, or an eV-like x range.
- Processing supports optional Savitzky-Golay smoothing, max-intensity normalization, and SciPy peak detection.
- Processed CSV files include `pl_axis`, `raw_intensity`, `processed_intensity`, and `wavelength_nm` when available.
- Peak tables include `position`, `position_unit`, `position_eV`, `wavelength_nm`, `height`, `prominence`, and assignment fields.
- For MoS2-like project IDs with eV/nm data, EA uses the built-in material assignment library to mark a dominant near-band-edge PL feature as a possible MoS2-like emission assignment with medium or low confidence.
- Assignment metadata records `assignment_source`; inspect the current rule with `ea materials assignments mos2 --method pl`.
- Reports include PL peak tables, confidence-labeled possible interpretations, file links, References, and provenance.

CLI path:

```bash
ea raw import /path/to/ea-project /path/to/raw-pl.txt --characterization-type pl --sample-ref sample-001 --experiment-ref exp-001
ea pl inspect /path/to/ea-project raw/pl/char-20260630-001/raw-pl.txt
ea review add /path/to/ea-project --target-type pl_columns --target-ref raw/pl/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "x=col_0, y=col_1, unit=eV"
ea review add /path/to/ea-project --target-type pl_parameters --target-ref raw/pl/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default PL parameters confirmed"
ea pl process /path/to/ea-project --metadata raw/pl/char-20260630-001/metadata.yml --x-column col_0 --y-column col_1 --x-unit eV --column-review-ref review-20260630-001 --parameter-review-ref review-20260630-002 --sample-ref sample-001
ea pl report /path/to/ea-project --metadata processed/sample-001/pl/res-project-pl-20260630-001/pl_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
```

Future PL work should add replicate handling, emission deconvolution, temperature/power-dependent PL support, more material records, and user-confirmed memory-candidate generation from report interpretations.
