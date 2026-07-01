# FTIR Workflow

Use this reference when processing Fourier-transform infrared spectra in EA v0.2.

Required gates:

1. Inspect the file and confirm it is FTIR/IR spectral data.
2. Ask for or verify x/y columns, x-axis unit (`cm^-1` or `unknown`), and `signal_mode` (`absorbance` or `transmittance`).
3. Ask for or verify processing parameters before analysis.
4. Keep raw data untouched; write processed outputs outside `raw/`.
5. If source-backed FTIR assignments are useful, prepare candidate band windows from a reviewed local library, project literature record, user-provided source, or user-confirmed literature/search workflow. Use `ea ftir build-assignment-packet` for local libraries/templates, then run `ea ftir suggest-assignments` with processed metadata before using assignments in reports or memory.
6. Record baseline handling, smoothing, normalization, band detection, optional reviewed FTIR context, optional assignment suggestion records, generated figure, report, and provenance.
7. Mark detected bands in figures and put wavenumber, prominence, broad band family, assignment source, and confidence in report tables.
8. Treat broad FTIR band-family matches, context records, and source-backed assignment suggestions as screening/provenance hints. Use project chemistry, references, and user review before writing durable conclusions.
9. Write memory candidates only after user confirmation.

Current v0.2 FTIR support:

- Raw import uses `ea raw import --characterization-type ftir`.
- Inspection identifies common FTIR files by path/name, wavenumber-like ranges, and axis metadata.
- Processing supports optional rolling-quantile baseline correction, optional Savitzky-Golay smoothing, max-absolute normalization, SciPy band detection, and disabled-by-default context records.
- `signal_mode=absorbance` detects maxima; `signal_mode=transmittance` detects minima.
- Processed CSV files include `wavenumber_cm-1`, `raw_signal`, optional `baseline_signal`, optional `smoothed_signal`, and `processed_signal`.
- Band tables include `wavenumber_cm-1`, `prominence`, `signal_mode`, `band_type`, `possible_band_family`, `assignment_confidence`, and `assignment_source`.
- When `context_record.enabled` is reviewed, EA writes `ftir_context.yml` with instrument/accessory, atmosphere, sample preparation, background, reference, correction notes, confidence, source, boundary, and record ref.
- `ea ftir build-assignment-packet` creates standard FTIR assignment source packets from project-local candidate libraries or editable templates; local-literature or confirmed search connectors may generate the same packet schema.
- `ea ftir suggest-assignments` records source-backed band-assignment candidates under `suggestions/ftir/` by matching candidate wavenumber windows to detected FTIR bands without applying them to processing outputs or memory.
- Built-in band-family windows cover broad regions only, such as O-H/N-H stretching, C-H stretching, carbonyl/amide-adjacent regions, fingerprint regions, and low-wavenumber metal-oxygen regions. They do not identify compounds by themselves.
- Reports include an embedded FTIR figure, original figure path, band tables, optional context record summary/link, confidence-labeled possible interpretations, file links, References, and provenance.
- `context_record` is disabled by default. Enable it only after the user reviews instrument/accessory, atmosphere, sample preparation, background/reference, and correction-note metadata. This record is metadata/provenance only; EA does not apply automatic background/reference/ATR/atmosphere correction from it in v0.2.
- FTIR assignment suggestions are advisory. They require source summary, applicability notes, reference IDs, confidence, caveats, and user review before report or memory use. EA does not run live lookup inside `suggest-assignments`, auto-apply assignments, or prove composition/functional groups from a band match alone.

CLI path:

```bash
ea raw import /path/to/ea-project /path/to/raw-ftir.txt --characterization-type ftir --sample-ref sample-001 --experiment-ref exp-001
ea ftir inspect /path/to/ea-project raw/ftir/char-20260630-001/raw-ftir.txt
ea review add /path/to/ea-project --target-type ftir_columns --target-ref raw/ftir/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "x=wavenumber, y=absorbance, unit=cm^-1, signal_mode=absorbance"
ea review add /path/to/ea-project --target-type ftir_parameters --target-ref raw/ftir/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default FTIR parameters confirmed"
ea ftir process /path/to/ea-project --metadata raw/ftir/char-20260630-001/metadata.yml --x-column wavenumber --y-column absorbance --x-unit cm^-1 --signal-mode absorbance --column-review-ref review-20260630-001 --parameter-review-ref review-20260630-002 --sample-ref sample-001
ea ftir report /path/to/ea-project --metadata processed/sample-001/ftir/res-project-ftir-20260630-001/ftir_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
ea ftir build-assignment-packet /path/to/ea-project --library-file project_ftir_assignment_library.yml
ea ftir suggest-assignments /path/to/ea-project --metadata processed/sample-001/ftir/res-project-ftir-20260630-001/ftir_metadata.yml --source-file suggestions/ftir/source-packets/ftir_assignment_source_packet-20260630-001.yml
```

Optional source-backed FTIR assignment candidate library:

```yaml
candidates:
  - candidate_id: ftir-assignment-carbonyl-001
    assignment_type: functional_group
    assignment_label: ester/carbonyl C=O stretching
    band_label: carbonyl stretching band
    material_scope: polymer composite film
    sample_scope: reviewed sample preparation where carbonyl-containing groups are plausible
    wavenumber_window_cm1: [1700, 1745]
    expected_feature: absorbance_maximum
    source_summary: Project reference spectrum or literature table supports this window.
    applicability_notes:
      - Applies only when project chemistry and sample preparation support oxygen-containing organic groups.
      - Overlaps with other carbonyl-like environments; user review is required.
    reference_ids:
      - ref-registered-ftir-001
    confidence: medium
    caveats:
      - Band-window match alone is not composition proof.
```

Optional reviewed FTIR context can be supplied with `--parameters-json` or `--parameters-file`:

```yaml
context_record:
  enabled: true
  method: reviewed_metadata_record
  source: ea.ftir.context_record:v0.2
  instrument_accessory:
    instrument: user-provided instrument name
    accessory: ATR
    crystal: diamond
    status: reviewed
  atmosphere:
    purge: dry_air
    co2_h2o_status: background_reviewed
  sample_preparation:
    sample_form: thin_film
    contact_quality: user_reviewed
  background:
    background_ref: fresh ATR background
    numeric_correction: instrument_applied
    status: reviewed
  reference:
    reference_type: project reference spectrum pending
    status: not_applied
  correction_notes:
    - EA records context only; no automatic FTIR correction is applied.
```

Future FTIR work should add larger curated reference-spectrum libraries, replicate comparison, peak-shape fitting where justified, stronger material-specific assignment libraries, and user-confirmed memory-candidate generation from report interpretations.
