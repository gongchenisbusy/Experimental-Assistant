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

v0.2 starts from the v0.1 deterministic core and should progressively add baseline correction, smoothing, spike diagnostics, peak fitting, replicate handling, and batch statistics.
