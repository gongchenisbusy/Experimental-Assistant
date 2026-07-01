# UV-Vis Workflow

Use this reference when processing UV-Vis absorbance, transmittance, or reflectance spectra in EA v0.2.

Required gates:

1. Inspect the file and confirm it is UV-Vis optical spectral data.
2. Ask for or verify x/y columns, x-axis unit (`nm`, `eV`, or `unknown`), and `signal_mode` (`absorbance`, `transmittance`, or `reflectance`).
3. Ask for or verify processing parameters before analysis.
4. Keep raw data untouched; write processed outputs outside `raw/`.
5. Record smoothing, normalization, feature detection, optional optical edge estimate, optional reviewed Tauc/Kubelka-Munk screening, optional reviewed derivative screening, optional reviewed correction context, generated figure, report, and provenance.
6. Mark detected optical features in figures and put position, wavelength, energy, prominence, feature type, assignment source, and confidence in report tables.
7. Treat optical features, threshold edge estimates, Tauc/Kubelka-Munk intercepts, derivative extrema/inflection hints, and correction-context records as screening/provenance hints. Use sample geometry, substrate/background/reference context, references, and user review before writing durable conclusions.
8. Write memory candidates only after user confirmation.

Current v0.2 UV-Vis support:

- Raw import uses `ea raw import --characterization-type uv_vis`.
- Inspection identifies common UV-Vis files by path/name, nm/eV-like ranges, and axis metadata.
- Processing supports optional Savitzky-Golay smoothing, max-absolute normalization, SciPy optical feature detection, a low-confidence normalized-threshold optical edge estimate, reviewed-parameter Tauc/Kubelka-Munk screening, disabled-by-default derivative screening, and disabled-by-default correction-context records.
- `signal_mode=absorbance` detects maxima; `signal_mode=transmittance` or `reflectance` detects minima.
- Processed CSV files include `uv_vis_axis`, `raw_signal`, optional `smoothed_signal`, `processed_signal`, and wavelength/energy conversions where units allow. When `tauc_analysis.enabled` is reviewed and valid, EA also writes `uv_vis_tauc.csv` with `tauc_energy_eV`, `tauc_alpha_proxy`, `tauc_y`, and `tauc_fit_window`. When `derivative_analysis.enabled` is reviewed and valid, EA writes `uv_vis_derivative.csv` with derivative axis, wavelength/energy coordinates, processed signal, first derivative, second derivative, method, and assignment source. When `correction_context.enabled` is reviewed, EA writes `uv_vis_correction_context.yml` with sample geometry, substrate, reference, background, diffuse-reflectance context, notes, confidence, source, boundary, and record ref.
- Feature tables include `position`, `position_unit`, `wavelength_nm`, `energy_eV`, `prominence`, `signal_mode`, `feature_type`, `assignment_confidence`, and `assignment_source`.
- Reports include an embedded UV-Vis figure, original figure path, feature tables, optical edge estimate, optional Tauc/Kubelka-Munk screening summary/table link, optional derivative screening summary/table link, confidence-labeled possible interpretations, file links, References, and provenance.
- Public users can inspect `examples/public-uv-vis-project/` for a synthetic reviewed optical-screening walkthrough with Tauc screening, derivative screening, correction-context provenance, report, figure, healthcheck/eval, and traceability. It is not a source-backed suggestion example.
- Literature source-candidate staging supports `ea literature prepare-source-candidates --method uv_vis` and `ea literature preflight-source-candidates --method uv_vis` for confirmed local literature manifests. Candidate types are `optical_transition_model`, `optical_gap_candidate`, `optical_feature_assignment`, and `correction_context_candidate`. `ea uv-vis build-source-packet` can write an editable template or copy reviewed local/confirmed-literature candidates into traceable staging packets under `suggestions/uv_vis/source-packets/`. `ea uv-vis suggest-interpretations` consumes a processed UV-Vis metadata file plus a source packet and writes advisory `uv_vis_interpretation_suggestions.yml` / `.csv` under `suggestions/uv_vis/`, preserving source summary, applicability notes, confidence, caveats, registered/unresolved `reference_ids`, and links to processed feature/Tauc/edge/derivative/correction-context evidence where available. `ea uv-vis prepare-review` writes grouped `review_package.yml` / `.md` files for ready, unresolved-reference, no-evidence-match, and invalid candidates. These review packages do not create ReviewRecords, inject report citations, auto-apply Tauc/Kubelka-Munk/correction models, or prove band gaps/transition mechanisms.
- `tauc_analysis` is disabled by default. Enable it only after the user reviews the transform (`absorbance` or `kubelka_munk`), transition assumption, exponent, and `fit_window_eV`. Absorbance Tauc screening requires `signal_mode=absorbance`; Kubelka-Munk screening requires `signal_mode=reflectance`.
- `derivative_analysis` is disabled by default. Enable it only after the user reviews or accepts the derivative axis (`auto`, `energy_eV`, `wavelength_nm`, or `uv_vis_axis`) and understands that derivative extrema/inflection hints are screening-only.
- `correction_context` is disabled by default. Enable it only after the user reviews substrate/reference/background/sample-geometry/diffuse-reflectance metadata. This record is metadata/provenance only; EA does not apply automatic numeric correction from it in v0.2.

CLI path:

```bash
ea raw import /path/to/ea-project /path/to/raw-uv-vis.txt --characterization-type uv_vis --sample-ref sample-001 --experiment-ref exp-001
ea uv-vis inspect /path/to/ea-project raw/uv_vis/char-20260630-001/raw-uv-vis.txt
ea review add /path/to/ea-project --target-type uv_vis_columns --target-ref raw/uv_vis/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "x=wavelength_nm, y=absorbance, unit=nm, signal_mode=absorbance"
ea review add /path/to/ea-project --target-type uv_vis_parameters --target-ref raw/uv_vis/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default UV-Vis parameters confirmed"
ea uv-vis process /path/to/ea-project --metadata raw/uv_vis/char-20260630-001/metadata.yml --x-column wavelength_nm --y-column absorbance --x-unit nm --signal-mode absorbance --column-review-ref review-20260630-001 --parameter-review-ref review-20260630-002 --sample-ref sample-001
ea uv-vis report /path/to/ea-project --metadata processed/sample-001/uv_vis/res-project-uv-vis-20260630-001/uv_vis_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
ea literature prepare-source-candidates /path/to/ea-project --method uv_vis --source-items literature/selected_items.yml --confirm-for-source-packet --user-response "User confirmed UV-Vis source-candidate manifest staging."
ea literature preflight-source-candidates /path/to/ea-project --method uv_vis --manifest literature/confirmed_uv_vis_source_candidates.yml
ea uv-vis build-source-packet /path/to/ea-project --literature-manifest literature/confirmed_uv_vis_source_candidates.yml --output suggestions/uv_vis/source-packets/uv_vis_source_packet.yml
ea uv-vis suggest-interpretations /path/to/ea-project --metadata processed/sample-001/uv_vis/res-project-uv-vis-20260630-001/uv_vis_metadata.yml --source-file suggestions/uv_vis/source-packets/uv_vis_source_packet.yml
ea uv-vis prepare-review /path/to/ea-project --suggestion suggestions/uv_vis/suggestion-20260630-001/uv_vis_interpretation_suggestions.yml
```

Optional reviewed derivative parameters can be supplied with `--parameters-json` or `--parameters-file`:

```yaml
derivative_analysis:
  enabled: true
  method: numpy_gradient
  axis: energy_eV
  min_points: 20
  source: ea.uv_vis.derivative_screening:v0.2
```

Optional reviewed correction context can be supplied with `--parameters-json` or `--parameters-file`:

```yaml
correction_context:
  enabled: true
  method: reviewed_metadata_record
  source: ea.uv_vis.correction_context:v0.2
  sample_geometry:
    sample_form: thin_film
    path_length: not_applicable
  substrate:
    material: quartz
    subtraction: not_applied
    status: reviewed
  reference:
    reference_type: blank_quartz
    reference_ref: user-reviewed blank spectrum
    status: reviewed
  background:
    background_ref: instrument dark baseline
    numeric_correction: instrument_applied
    status: reviewed
  diffuse_reflectance:
    integrating_sphere: false
    kubelka_munk_context: not_used
  correction_notes:
    - EA records context only; no automatic numeric correction is applied.
```

Future UV-Vis work should add report-integration and memory-candidate commands for reviewed source-backed suggestions, plus numeric baseline/substrate/reference correction algorithms after review, replicate comparison, and richer material assignment libraries.
