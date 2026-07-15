# Raman Workflow

Use this reference when processing Raman spectra in the Experimental Assistant v0.9.9 skill.

Required gates:

1. Inspect file and classify likely Raman/PL/unknown.
2. Ask for or verify x/y columns and x-axis unit.
3. Ask for or verify processing parameters before analysis.
4. Keep raw data untouched; write processed outputs outside `raw/`.
5. Record baseline, smoothing, normalization, spike handling, peak detection, and fitting parameters.
6. Mark peaks clearly in figures and put detailed peak table values in tables or report text.
7. If source-backed Raman assignment candidates are useful, run `ea raman list-assignment-libraries` to inspect built-in material-profile coverage, feature windows, pair-rule context, DOI reference hints, filters, next commands, and no-auto-application boundaries before interpreting peaks.
8. Interpret peaks with project context and literature references. Use confidence labels rather than empty caution.
9. Write memory candidates only after user confirmation.

Current Experimental Assistant v0.9.9 preprocessing compatibility support:

- Baseline correction is optional and uses AsLS when `baseline_correction.enabled` is true.
- Smoothing is optional and uses Savitzky-Golay when `smoothing.enabled` is true.
- Spike diagnostics are optional and use rolling MAD when `spike_detection.enabled` is true.
- Processed CSV files always include `raw_intensity`, `processed_intensity`, and `spike_candidate`.
- When enabled, baseline correction adds `baseline` and `baseline_corrected_intensity`.
- When enabled, smoothing adds `smoothed_intensity`.
- Metadata warnings record applied preprocessing steps, adjusted parameters, skipped steps, and spike-candidate counts.
- Peak tables include automatic peak detection plus local Gaussian fit metrics (`fit_center_cm-1`, `fit_fwhm_cm-1`, `fit_area`, `fit_r2`) when `peak_fitting.enabled` is true.
- `ea raman list-assignment-libraries` prints a local JSON discovery summary for built-in Raman material-assignment profiles, with candidate counts, feature IDs, Raman-shift windows, pair-rule context, reference hints, filters, recommended next commands, and no-auto-application boundaries. It does not create project files, run live lookup, register references, process spectra, match peaks, create ReviewRecords, inject report citations, write memory, or prove material identity, phase identity, layer number, strain/doping, or calibration.
- When a project ID or context matches a built-in material profile, EA uses the material assignment library to assign Raman candidate features when fitted peak centers fall within tolerance and writes confidence-labeled possible interpretations.
- Current built-in Raman profiles include MoS2, WS2, and h-BN. Assignment metadata records `assignment_source` so later agents can inspect the rule source with commands such as `ea materials assignments ws2 --method raman`.

Example:

```bash
ea raman list-assignment-libraries --material mos2 --feature mos2_a1g_like --shift-min-cm1 400 --shift-max-cm1 420
ea materials assignments mos2 --method raman
```

Future Raman work should add replicate handling, batch statistics, additional material records, and user-confirmed memory-candidate generation from report interpretations.
