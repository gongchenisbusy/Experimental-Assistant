# FTIR Workflow

Use this reference when processing Fourier-transform infrared spectra in the EA v0.9 RC compatibility skill.

Required gates:

1. Inspect the file and confirm it is FTIR/IR spectral data.
2. Ask for or verify x/y columns, x-axis unit (`cm^-1` or `unknown`), and `signal_mode` (`absorbance` or `transmittance`).
3. Ask for or verify processing parameters before analysis.
4. Keep raw data untouched; write processed outputs outside `raw/`.
5. If source-backed FTIR assignments are useful, prepare candidate band windows from the built-in `generic_materials` seed library, a reviewed local library, project literature record, user-provided source, or user-confirmed literature/search workflow. Use `ea ftir list-assignment-libraries` to inspect built-in candidate coverage and reference seeds before deciding which packet to build. Use `ea ftir build-assignment-packet` for built-in libraries, local libraries, templates, or a confirmed literature/source-candidate manifest with `--literature-manifest`, then run `ea ftir suggest-assignments` with processed metadata. Use `ea ftir prepare-review` to create a grouped YAML/Markdown review package before asking the user which candidate IDs to accept, reject, edit, or defer; pass reviewed suggestion records to `ea ftir report --assignment-suggestion` when the report should include citation-aware advisory assignment sections.
6. Record baseline handling, smoothing, normalization, band detection, optional reviewed FTIR context, optional assignment suggestion records, generated figure, report, and provenance.
7. Mark detected bands in figures and put wavenumber, prominence, broad band family, assignment source, and confidence in report tables.
8. Treat broad FTIR band-family matches, context records, and source-backed assignment suggestions as screening/provenance hints. Use project chemistry, references, and user review before writing durable conclusions.
9. Write memory candidates only after user confirmation.

Current EA v0.9 RC FTIR compatibility support:

- Raw import uses `ea raw import --characterization-type ftir`.
- Inspection identifies common FTIR files by path/name, wavenumber-like ranges, and axis metadata.
- Processing supports optional rolling-quantile baseline correction, optional Savitzky-Golay smoothing, max-absolute normalization, SciPy band detection, and disabled-by-default context records.
- `signal_mode=absorbance` detects maxima; `signal_mode=transmittance` detects minima.
- Processed CSV files include `wavenumber_cm-1`, `raw_signal`, optional `baseline_signal`, optional `smoothed_signal`, and `processed_signal`.
- Band tables include `wavenumber_cm-1`, `prominence`, `signal_mode`, `band_type`, `possible_band_family`, `assignment_confidence`, and `assignment_source`.
- When `context_record.enabled` is reviewed, EA writes `ftir_context.yml` with instrument/accessory, atmosphere, sample preparation, background, reference, correction notes, confidence, source, boundary, and record ref.
- `ea ftir list-assignment-libraries` prints a local JSON discovery summary for built-in FTIR assignment libraries, with candidate counts, assignment types, material scopes, wavenumber ranges, reference seeds, candidate summaries, filters, recommended next commands, and no-auto-application boundaries. It does not create project files, run live lookup, register references, build source packets, match bands, create ReviewRecords, inject report citations, write memory, or prove composition/functional groups.
- `ea ftir build-assignment-packet` creates standard FTIR assignment source packets from the built-in `generic_materials` seed library, project-local candidate libraries, editable templates, or user-confirmed literature/source-candidate manifests. The `--literature-manifest` path requires explicit confirmation metadata, copies only matching source candidates, and does not run live search, download/parse articles, register references, inject citations, apply assignments, or prove composition/functional groups.
- `ea ftir suggest-assignments` records source-backed band-assignment candidates under `suggestions/ftir/` by matching candidate wavenumber windows to detected FTIR bands without applying them to processing outputs or memory.
- `ea ftir prepare-review` writes grouped `review_package.yml` and `review_package.md` artifacts next to the suggestion record. The package summarizes ready, unresolved-reference, no-match, and invalid/incomplete candidates with source summaries, applicability notes, caveats, reference issues, and suggested review/report/memory commands. It does not create a ReviewRecord.
- `ea ftir propose-memory` turns user-reviewed ready assignment suggestions into draft memory candidates, preserving suggestion/table/provenance refs, matched band IDs/wavenumbers, source summaries, applicability notes, caveats, and reference IDs. It does not commit memory.
- Built-in band-family windows cover broad regions only, including O-H/N-H stretching, adsorbed-water bending, C-H stretching, carbonyl/amide/carboxylate regions, triple-bond and aromatic regions, C-O/C-N fingerprint bands, Si-O/silanol bands, common carbonate/phosphate/sulfate/nitrate inorganic-ion regions, and low-wavenumber metal-oxygen regions. They do not identify compounds by themselves.
- Public release packages include `examples/public-ftir-assignment-project/`, a public-safe runnable example of the built-in `generic_materials` FTIR assignment path from source packet and reference registration through suggestion review package, report display, traceable citations, and draft interpretation memory candidates.
- Reports include an embedded FTIR figure, original figure path, band tables, optional context record summary/link, optional source-backed assignment suggestion sections, confidence-labeled possible interpretations, file links, References, and provenance.
- `context_record` is disabled by default. Enable it only after the user reviews instrument/accessory, atmosphere, sample preparation, background/reference, and correction-note metadata. This record is metadata/provenance only; EA v0.9 RC does not apply automatic background/reference/ATR/atmosphere correction from it.
- FTIR assignment suggestions are advisory. They require source summary, applicability notes, reference IDs, confidence, caveats, and user review before report or memory use. Built-in and confirmed-literature packets may include `reference_seeds`; use `ea references register-seeds` or manual replacement to register those sources in the project reference index before treating seed-backed candidates as report evidence. `ea ftir report --assignment-suggestion` can display these records and merge registered references into the report bibliography. The `suggest-assignments` command does not perform unconfirmed live lookup, auto-apply assignments, or prove composition/functional groups from a band match alone; EA may still prepare source-backed candidates from built-in libraries, project literature, user-provided sources, or user-confirmed search workflows before that command.

CLI path:

```bash
ea raw import /path/to/ea-project /path/to/raw-ftir.txt --characterization-type ftir --sample-ref sample-001 --experiment-ref exp-001
ea ftir inspect /path/to/ea-project raw/ftir/char-20260630-001/raw-ftir.txt
ea review add /path/to/ea-project --target-type ftir_columns --target-ref raw/ftir/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "x=wavenumber, y=absorbance, unit=cm^-1, signal_mode=absorbance"
ea review add /path/to/ea-project --target-type ftir_parameters --target-ref raw/ftir/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default FTIR parameters confirmed"
ea ftir process /path/to/ea-project --metadata raw/ftir/char-20260630-001/metadata.yml --x-column wavenumber --y-column absorbance --x-unit cm^-1 --signal-mode absorbance --column-review-ref review-20260630-001 --parameter-review-ref review-20260630-002 --sample-ref sample-001
ea ftir report /path/to/ea-project --metadata processed/sample-001/ftir/res-project-ftir-20260630-001/ftir_metadata.yml --sample-ref sample-001 --experiment-ref exp-001 --assignment-suggestion suggestions/ftir/suggestion-20260630-001/ftir_assignment_suggestions.yml
ea ftir list-assignment-libraries --builtin-library generic_materials --assignment-type inorganic_ion --material-scope oxide --wavenumber-min-cm1 1300 --wavenumber-max-cm1 1500
ea ftir build-assignment-packet /path/to/ea-project
ea ftir build-assignment-packet /path/to/ea-project --builtin-library generic_materials --include-candidate ftir-builtin-carbonyl-co-stretching-generic
ea references register-seeds /path/to/ea-project --source-packet suggestions/ftir/source-packets/ftir_assignment_source_packet-20260630-001.yml
ea ftir build-assignment-packet /path/to/ea-project --library-file project_ftir_assignment_library.yml
ea ftir build-assignment-packet /path/to/ea-project --literature-manifest literature/confirmed_ftir_source_candidates.yml
ea ftir suggest-assignments /path/to/ea-project --metadata processed/sample-001/ftir/res-project-ftir-20260630-001/ftir_metadata.yml --source-file suggestions/ftir/source-packets/ftir_assignment_source_packet-20260630-001.yml
ea ftir prepare-review /path/to/ea-project --suggestion suggestions/ftir/suggestion-20260630-001/ftir_assignment_suggestions.yml
ea review add /path/to/ea-project --target-type ftir_assignment_suggestions --target-ref suggestions/ftir/suggestion-20260630-001/ftir_assignment_suggestions.yml --user-response "可以，保存" --reviewed-content "reviewed FTIR assignment suggestion candidates"
ea ftir propose-memory /path/to/ea-project --suggestion suggestions/ftir/suggestion-20260630-001/ftir_assignment_suggestions.yml --review-ref review-20260630-003
```

Built-in FTIR assignment seed library:

- Default source-packet generation uses `generic_materials` when neither `--library-file` nor `--write-template` is supplied.
- The built-in library includes common generic O-H/N-H, adsorbed-water, aliphatic C-H, C=O, amide, carboxylate, triple-bond, aromatic C=C, C-O/C-N, Si-O/oxide, silanol, carbonate, phosphate, sulfate, nitrate, and low-wavenumber metal-oxygen candidates. These are proactive source-backed screening seeds for discussion and review, not automatic assignments.
- Built-in candidates are generic screening seeds. They carry `reference_seeds`, but their `reference_ids` still need project registration or replacement before report citations can become numbered references. Use `ea references register-seeds` only when the user or agent explicitly wants those seeds registered in this project.
- Use `ea ftir list-assignment-libraries` with `--include-candidate`, `--assignment-type`, `--material-scope`, `--wavenumber-min-cm1`, and `--wavenumber-max-cm1` to discover the relevant built-in candidates before packet creation; use `--include-candidate`, `--assignment-type`, and `--material-scope` on the packet builder to narrow the packet before matching.

Optional project-local FTIR assignment candidate library:

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

Future FTIR work should add larger curated reference-spectrum libraries, replicate comparison, peak-shape fitting where justified, stronger material-specific assignment libraries, and richer memory-candidate grouping/review helpers for multi-candidate interpretation sets.
