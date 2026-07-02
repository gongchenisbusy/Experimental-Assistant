# PL Workflow

Use this reference when processing photoluminescence spectra in the EA v0.9 RC compatibility skill.

Required gates:

1. Inspect the file and confirm it is PL, not Raman or unknown.
2. Ask for or verify x/y columns and x-axis unit (`eV`, `nm`, or `unknown`).
3. Ask for or verify processing parameters before analysis.
4. Keep raw data untouched; write processed outputs outside `raw/`.
5. Record smoothing, normalization, peak detection, generated figure, report, and provenance.
6. Mark PL peaks in figures and put peak position, optional wavelength, prominence, and assignment confidence in report tables.
7. If source-backed PL assignment candidates are useful, run `ea pl list-assignment-libraries` to inspect built-in material-profile coverage, energy/wavelength windows, DOI reference hints, filters, next commands, and no-auto-application boundaries before interpreting emission features.
8. Interpret emission features with project context and literature references. Use confidence labels rather than definitive mechanism claims.
9. Write memory candidates only after user confirmation.

Current EA v0.9 RC PL compatibility support:

- Raw import uses `ea raw import --characterization-type pl`.
- Inspection reuses the spectrum reader and identifies common PL files by filename, `AxisUnit[1]=eV`, or an eV-like x range.
- Processing supports optional Savitzky-Golay smoothing, max-intensity normalization, and SciPy peak detection.
- Processed CSV files include `pl_axis`, `raw_intensity`, `processed_intensity`, and `wavelength_nm` when available.
- Peak tables include `position`, `position_unit`, `position_eV`, `wavelength_nm`, `height`, `prominence`, and assignment fields.
- `ea pl list-assignment-libraries` prints a local JSON discovery summary for built-in PL material-assignment profiles, with candidate counts, feature IDs, energy/wavelength windows, reference hints, filters, recommended next commands, and no-auto-application boundaries. It does not create project files, run live lookup, register references, process spectra, match peaks, create ReviewRecords, inject report citations, write memory, or prove excitonic mechanism, material identity, layer number, defect origin, strain/doping, substrate effect, or calibration.
- When a project ID or context matches a built-in material profile with PL rules and the energy can be determined, EA uses the material assignment library to mark dominant near-band-edge PL candidates with medium or low confidence.
- Current built-in PL profiles include MoS2 and WS2. Assignment metadata records `assignment_source`; inspect a rule with commands such as `ea materials assignments ws2 --method pl`.
- Reports include PL peak tables, confidence-labeled possible interpretations, file links, References, and provenance.

CLI path:

```bash
ea raw import /path/to/ea-project /path/to/raw-pl.txt --characterization-type pl --sample-ref sample-001 --experiment-ref exp-001
ea pl inspect /path/to/ea-project raw/pl/char-20260630-001/raw-pl.txt
ea pl list-assignment-libraries --material mos2 --energy-min-ev 1.8 --energy-max-ev 1.9
ea review add /path/to/ea-project --target-type pl_columns --target-ref raw/pl/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "x=col_0, y=col_1, unit=eV"
ea review add /path/to/ea-project --target-type pl_parameters --target-ref raw/pl/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default PL parameters confirmed"
ea pl process /path/to/ea-project --metadata raw/pl/char-20260630-001/metadata.yml --x-column col_0 --y-column col_1 --x-unit eV --column-review-ref review-20260630-001 --parameter-review-ref review-20260630-002 --sample-ref sample-001
ea pl report /path/to/ea-project --metadata processed/sample-001/pl/res-project-pl-20260630-001/pl_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
```

Future PL work should add replicate handling, emission deconvolution, temperature/power-dependent PL support, more material records, and user-confirmed memory-candidate generation from report interpretations.
