# UV-Vis Workflow

Use this reference when processing UV-Vis absorbance, transmittance, or reflectance spectra in EA v0.2.

Required gates:

1. Inspect the file and confirm it is UV-Vis optical spectral data.
2. Ask for or verify x/y columns, x-axis unit (`nm`, `eV`, or `unknown`), and `signal_mode` (`absorbance`, `transmittance`, or `reflectance`).
3. Ask for or verify processing parameters before analysis.
4. Keep raw data untouched; write processed outputs outside `raw/`.
5. Record smoothing, normalization, feature detection, optional optical edge estimate, optional reviewed Tauc/Kubelka-Munk screening, generated figure, report, and provenance.
6. Mark detected optical features in figures and put position, wavelength, energy, prominence, feature type, assignment source, and confidence in report tables.
7. Treat optical features, threshold edge estimates, and Tauc/Kubelka-Munk intercepts as screening hints. Use sample geometry, substrate/background, references, and user review before writing durable conclusions.
8. Write memory candidates only after user confirmation.

Current v0.2 UV-Vis support:

- Raw import uses `ea raw import --characterization-type uv_vis`.
- Inspection identifies common UV-Vis files by path/name, nm/eV-like ranges, and axis metadata.
- Processing supports optional Savitzky-Golay smoothing, max-absolute normalization, SciPy optical feature detection, a low-confidence normalized-threshold optical edge estimate, and reviewed-parameter Tauc/Kubelka-Munk screening.
- `signal_mode=absorbance` detects maxima; `signal_mode=transmittance` or `reflectance` detects minima.
- Processed CSV files include `uv_vis_axis`, `raw_signal`, optional `smoothed_signal`, `processed_signal`, and wavelength/energy conversions where units allow. When `tauc_analysis.enabled` is reviewed and valid, EA also writes `uv_vis_tauc.csv` with `tauc_energy_eV`, `tauc_alpha_proxy`, `tauc_y`, and `tauc_fit_window`.
- Feature tables include `position`, `position_unit`, `wavelength_nm`, `energy_eV`, `prominence`, `signal_mode`, `feature_type`, `assignment_confidence`, and `assignment_source`.
- Reports include an embedded UV-Vis figure, original figure path, feature tables, optical edge estimate, optional Tauc/Kubelka-Munk screening summary/table link, confidence-labeled possible interpretations, file links, References, and provenance.
- `tauc_analysis` is disabled by default. Enable it only after the user reviews the transform (`absorbance` or `kubelka_munk`), transition assumption, exponent, and `fit_window_eV`. Absorbance Tauc screening requires `signal_mode=absorbance`; Kubelka-Munk screening requires `signal_mode=reflectance`.

CLI path:

```bash
ea raw import /path/to/ea-project /path/to/raw-uv-vis.txt --characterization-type uv_vis --sample-ref sample-001 --experiment-ref exp-001
ea uv-vis inspect /path/to/ea-project raw/uv_vis/char-20260630-001/raw-uv-vis.txt
ea review add /path/to/ea-project --target-type uv_vis_columns --target-ref raw/uv_vis/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "x=wavelength_nm, y=absorbance, unit=nm, signal_mode=absorbance"
ea review add /path/to/ea-project --target-type uv_vis_parameters --target-ref raw/uv_vis/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default UV-Vis parameters confirmed"
ea uv-vis process /path/to/ea-project --metadata raw/uv_vis/char-20260630-001/metadata.yml --x-column wavelength_nm --y-column absorbance --x-unit nm --signal-mode absorbance --column-review-ref review-20260630-001 --parameter-review-ref review-20260630-002 --sample-ref sample-001
ea uv-vis report /path/to/ea-project --metadata processed/sample-001/uv_vis/res-project-uv-vis-20260630-001/uv_vis_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
```

Future UV-Vis work should add derivative analysis, baseline/substrate/reference correction records, replicate comparison, richer diffuse-reflectance metadata, richer material assignment libraries, and user-confirmed memory-candidate generation from report interpretations.
