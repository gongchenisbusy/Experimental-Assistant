# FTIR Workflow

Use this reference when processing Fourier-transform infrared spectra in EA v0.2.

Required gates:

1. Inspect the file and confirm it is FTIR/IR spectral data.
2. Ask for or verify x/y columns, x-axis unit (`cm^-1` or `unknown`), and `signal_mode` (`absorbance` or `transmittance`).
3. Ask for or verify processing parameters before analysis.
4. Keep raw data untouched; write processed outputs outside `raw/`.
5. Record baseline handling, smoothing, normalization, band detection, generated figure, report, and provenance.
6. Mark detected bands in figures and put wavenumber, prominence, broad band family, assignment source, and confidence in report tables.
7. Treat broad FTIR band-family matches as screening hints. Use project chemistry, references, and user review before writing durable conclusions.
8. Write memory candidates only after user confirmation.

Current v0.2 FTIR support:

- Raw import uses `ea raw import --characterization-type ftir`.
- Inspection identifies common FTIR files by path/name, wavenumber-like ranges, and axis metadata.
- Processing supports optional rolling-quantile baseline correction, optional Savitzky-Golay smoothing, max-absolute normalization, and SciPy band detection.
- `signal_mode=absorbance` detects maxima; `signal_mode=transmittance` detects minima.
- Processed CSV files include `wavenumber_cm-1`, `raw_signal`, optional `baseline_signal`, optional `smoothed_signal`, and `processed_signal`.
- Band tables include `wavenumber_cm-1`, `prominence`, `signal_mode`, `band_type`, `possible_band_family`, `assignment_confidence`, and `assignment_source`.
- Built-in band-family windows cover broad regions only, such as O-H/N-H stretching, C-H stretching, carbonyl/amide-adjacent regions, fingerprint regions, and low-wavenumber metal-oxygen regions. They do not identify compounds by themselves.
- Reports include an embedded FTIR figure, original figure path, band tables, confidence-labeled possible interpretations, file links, References, and provenance.

CLI path:

```bash
ea raw import /path/to/ea-project /path/to/raw-ftir.txt --characterization-type ftir --sample-ref sample-001 --experiment-ref exp-001
ea ftir inspect /path/to/ea-project raw/ftir/char-20260630-001/raw-ftir.txt
ea review add /path/to/ea-project --target-type ftir_columns --target-ref raw/ftir/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "x=wavenumber, y=absorbance, unit=cm^-1, signal_mode=absorbance"
ea review add /path/to/ea-project --target-type ftir_parameters --target-ref raw/ftir/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default FTIR parameters confirmed"
ea ftir process /path/to/ea-project --metadata raw/ftir/char-20260630-001/metadata.yml --x-column wavenumber --y-column absorbance --x-unit cm^-1 --signal-mode absorbance --column-review-ref review-20260630-001 --parameter-review-ref review-20260630-002 --sample-ref sample-001
ea ftir report /path/to/ea-project --metadata processed/sample-001/ftir/res-project-ftir-20260630-001/ftir_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
```

Future FTIR work should add instrument-mode metadata, atmosphere/background records, reference-spectrum libraries, replicate comparison, peak-shape fitting where justified, and user-confirmed memory-candidate generation from report interpretations.
