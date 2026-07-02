# XRD Workflow

Use this reference when processing X-ray diffraction patterns in EA v0.2.

Required gates:

1. Inspect the file and confirm it is XRD, not Raman, PL, or unknown.
2. Ask for or verify x/y columns and x-axis unit (`2theta_deg` or `unknown`).
3. Ask for or verify processing parameters, including X-ray wavelength when d-spacing is needed.
4. Keep raw data untouched; write processed outputs outside `raw/`.
5. Record smoothing, normalization, peak detection, d-spacing calculation, generated figure, report, and provenance.
6. Mark XRD peaks in figures and put 2theta, optional d-spacing, prominence, and assignment confidence in report tables.
7. Interpret structural features with project context, phase references, and literature references. Use confidence labels rather than definitive phase or mechanism claims.
8. If source-backed XRD assignment candidates are useful, run `ea xrd list-assignment-libraries` to inspect built-in material-profile coverage, 2theta/d-spacing windows, DOI reference hints, filters, next commands, and no-auto-application boundaries before interpreting reflections.
9. Write memory candidates only after user confirmation.

Current v0.2 XRD support:

- Raw import uses `ea raw import --characterization-type xrd`.
- Inspection identifies common two-column XRD files by filename, 2theta axis metadata, degree units, or a 2theta-like x range.
- Processing supports optional Savitzky-Golay smoothing, max-intensity normalization, SciPy peak detection, and Bragg d-spacing calculation when x-axis is confirmed as `2theta_deg` and a wavelength is available.
- Default wavelength is `1.5406 A` (`Cu Kalpha`) and must be covered by the user-confirmed parameter review before processing.
- Processed CSV files include `two_theta`, `raw_intensity`, `processed_intensity`, and `d_spacing_angstrom` when available.
- Peak tables include `two_theta_deg`, `d_spacing_angstrom`, `height`, `prominence`, and phase-assignment fields.
- When a project ID or context matches a built-in material profile, EA uses the material assignment library to mark XRD candidate reflections with medium or low confidence and explicit need for phase-reference review.
- Current built-in XRD profiles include MoS2, WS2, and h-BN. Assignment metadata records `assignment_source`; inspect a rule with commands such as `ea materials assignments hbn --method xrd`.
- `ea xrd list-assignment-libraries` prints a local JSON discovery summary for built-in XRD material-assignment profiles, with candidate counts, feature IDs, 2theta windows, d-spacing windows, DOI reference hints, filters, recommended next commands, and no-auto-application boundaries. It does not create project files, run live lookup, register references, process diffraction patterns, match peaks, create ReviewRecords, inject report citations, write memory, or prove phase identity, material identity, crystallinity, texture, strain, lattice parameters, instrument calibration, or sample quality.
- Reports include XRD peak tables, confidence-labeled possible interpretations, file links, References, and provenance.

CLI path:

```bash
ea raw import /path/to/ea-project /path/to/raw-xrd.txt --characterization-type xrd --sample-ref sample-001 --experiment-ref exp-001
ea xrd inspect /path/to/ea-project raw/xrd/char-20260630-001/raw-xrd.txt
ea xrd list-assignment-libraries --material hbn --feature 002 --two-theta-min-deg 26.4 --two-theta-max-deg 27.0
ea review add /path/to/ea-project --target-type xrd_columns --target-ref raw/xrd/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "x=two_theta, y=intensity, unit=2theta_deg"
ea review add /path/to/ea-project --target-type xrd_parameters --target-ref raw/xrd/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default XRD parameters confirmed"
ea xrd process /path/to/ea-project --metadata raw/xrd/char-20260630-001/metadata.yml --x-column two_theta --y-column intensity --x-unit 2theta_deg --column-review-ref review-20260630-001 --parameter-review-ref review-20260630-002 --sample-ref sample-001
ea xrd report /path/to/ea-project --metadata processed/sample-001/xrd/res-project-xrd-20260630-001/xrd_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
```

Future XRD work should add background subtraction, K-alpha doublet handling, crystallite-size estimates with instrument broadening review, richer phase-reference libraries, batch/replicate comparisons, texture metrics, and user-confirmed memory-candidate generation from report interpretations.
