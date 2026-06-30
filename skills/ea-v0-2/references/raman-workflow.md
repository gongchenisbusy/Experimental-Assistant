# Raman Workflow

Use this reference when processing Raman spectra in EA v0.2.

Required gates:

1. Inspect file and classify likely Raman/PL/unknown.
2. Ask for or verify x/y columns and x-axis unit.
3. Ask for or verify processing parameters before analysis.
4. Keep raw data untouched; write processed outputs outside `raw/`.
5. Record baseline, smoothing, normalization, spike handling, peak detection, and fitting parameters.
6. Mark peaks clearly in figures and put detailed peak table values in tables or report text.
7. Interpret peaks with project context and literature references. Use confidence labels rather than empty caution.
8. Write memory candidates only after user confirmation.

Current v0.2 preprocessing support:

- Baseline correction is optional and uses AsLS when `baseline_correction.enabled` is true.
- Smoothing is optional and uses Savitzky-Golay when `smoothing.enabled` is true.
- Spike diagnostics are optional and use rolling MAD when `spike_detection.enabled` is true.
- Processed CSV files always include `raw_intensity`, `processed_intensity`, and `spike_candidate`.
- When enabled, baseline correction adds `baseline` and `baseline_corrected_intensity`.
- When enabled, smoothing adds `smoothed_intensity`.
- Metadata warnings record applied preprocessing steps, adjusted parameters, skipped steps, and spike-candidate counts.
- Peak tables include automatic peak detection plus local Gaussian fit metrics (`fit_center_cm-1`, `fit_fwhm_cm-1`, `fit_area`, `fit_r2`) when `peak_fitting.enabled` is true.
- For MoS2-like project IDs, EA assigns simple E2g-like and A1g-like candidate features when fitted peak centers fall within tolerance, computes their separation, and writes possible interpretations with confidence labels.

Future Raman work should add replicate handling, batch statistics, material-specific assignment libraries beyond MoS2, and user-confirmed memory-candidate generation from report interpretations.
