# XRD Workflow

Use this reference when processing X-ray diffraction patterns in the Experimental Assistant v1.1.0 skill.

Required gates:

1. Inspect the file and confirm it is XRD, not Raman, PL, or unknown.
2. Ask for or verify x/y columns and x-axis unit (`2theta_deg` or `unknown`).
3. Ask for or verify processing parameters, including X-ray wavelength when d-spacing is needed.
4. Keep raw data untouched; write processed outputs outside `raw/`.
5. Record smoothing, normalization, peak detection, d-spacing calculation, generated figure, report, and provenance.
6. Mark XRD peaks in figures and put 2theta, optional d-spacing, prominence, and assignment confidence in report tables.
7. Interpret structural features with project context, phase references, and literature references. Use confidence labels rather than definitive phase or mechanism claims.
8. If source-backed XRD assignment candidates are useful, run `ea xrd list-assignment-libraries` to inspect built-in material-profile coverage, 2theta/d-spacing windows, DOI reference hints, filters, next commands, and no-auto-application boundaries before interpreting reflections.
9. When the user wants project-local staging, run `ea xrd build-assignment-packet` to copy built-in, local YAML, editable-template, or explicitly confirmed literature/source-candidate records into `suggestions/xrd/source-packets/` with reference seeds, guidance, provenance, caveats, and next steps.
10. Register or replace packet `reference_seeds` before using source-backed XRD candidates as report evidence.
11. Run `ea xrd suggest-assignments` when a processed peak table should be matched to a reviewed source packet; keep the output as advisory until the user reviews candidates.
12. Run `ea xrd prepare-review` to create grouped YAML/Markdown review context before asking the user which candidate IDs to accept, reject, edit, or defer.
13. Create a confirmed `xrd_assignment_suggestions` ReviewRecord before passing assignment suggestions into `ea xrd report --assignment-suggestion ... --assignment-review-ref ...`.
14. Write memory candidates only after user confirmation.

Current Experimental Assistant v1.1.0 XRD compatibility support:

- Raw import uses `ea raw import --characterization-type xrd`.
- Inspection identifies common two-column XRD files by filename, 2theta axis metadata, degree units, or a 2theta-like x range.
- Processing supports optional Savitzky-Golay smoothing, max-intensity normalization, SciPy peak detection, and Bragg d-spacing calculation when x-axis is confirmed as `2theta_deg` and a wavelength is available.
- Default wavelength is `1.5406 A` (`Cu Kalpha`) and must be covered by the user-confirmed parameter review before processing.
- Processed CSV files include `two_theta`, `raw_intensity`, `processed_intensity`, and `d_spacing_angstrom` when available.
- Peak tables include `two_theta_deg`, `d_spacing_angstrom`, `height`, `prominence`, and phase-assignment fields.
- When a project ID or context matches a built-in material profile, EA uses the material assignment library to mark XRD candidate reflections with medium or low confidence and explicit need for phase-reference review.
- Current built-in XRD profiles include MoS2, WS2, and h-BN. Assignment metadata records `assignment_source`; inspect a rule with commands such as `ea materials assignments hbn --method xrd`.
- `ea xrd list-assignment-libraries` prints a local JSON discovery summary for built-in XRD material-assignment profiles, with candidate counts, feature IDs, 2theta windows, d-spacing windows, DOI reference hints, filters, recommended next commands, and no-auto-application boundaries. It does not create project files, run live lookup, register references, process diffraction patterns, match peaks, create ReviewRecords, inject report citations, write memory, or prove phase identity, material identity, crystallinity, texture, strain, lattice parameters, instrument calibration, or sample quality.
- `ea xrd build-assignment-packet` writes a reviewable XRD assignment source packet from the built-in material assignment library, a project-local YAML library, an editable template, or an explicitly confirmed XRD literature/source-candidate manifest. It preserves filtered `reference_seeds`, `guidance_notes`, source summaries, applicability notes, confidence, caveats, provenance, and next steps, but does not register references, process data, match peaks, create ReviewRecords, inject report citations, apply assignments, write memory, or prove structural claims.
- `ea xrd suggest-assignments` reads processed XRD metadata plus an XRD assignment source packet, matches candidate 2theta/d-spacing windows against the processed peak table, and writes advisory YAML/CSV `assignment_suggestions` under `suggestions/xrd/`. Candidate statuses distinguish ready-for-user-review, missing reference registration, no feature match, and invalid metadata. It does not run live lookup, process raw data, detect new peaks, mutate source packets, register references, create ReviewRecords, inject report citations, auto-apply assignments, write memory, or prove structural claims.
- `ea xrd prepare-review` writes grouped `review_package.yml` and `review_package.md` artifacts next to an XRD assignment suggestion record. The package summarizes ready, unresolved-reference, no-match, and invalid/incomplete candidates with matched peak IDs, 2theta/d-spacing values, source summaries, applicability notes, caveats, reference issues, and suggested review commands. It does not create a ReviewRecord, modify reports/source packets/processed outputs, register references, inject citations, apply assignments, write memory, or prove structural claims.
- `ea xrd report --assignment-suggestion ... --assignment-review-ref ...` reads only existing XRD assignment suggestion records plus matching confirmed ReviewRecords. It displays reviewed source-backed assignment context, matched peak IDs, 2theta/d-spacing values, source summaries, applicability notes, caveats, confidence/status labels, registered citation markers, and unresolved/no-match/invalid warnings. It merges registered suggestion references into report References, but does not create ReviewRecords, mutate suggestions/source packets/processed outputs, register references, auto-apply assignments, write memory, or prove structural claims.
- Reports include XRD peak tables, confidence-labeled possible interpretations, file links, References, and provenance.

CLI path:

```bash
ea raw import /path/to/ea-project /path/to/raw-xrd.txt --characterization-type xrd --sample-ref sample-001 --experiment-ref exp-001
ea xrd inspect /path/to/ea-project raw/xrd/char-20260630-001/raw-xrd.txt
ea xrd list-assignment-libraries --material hbn --feature 002 --two-theta-min-deg 26.4 --two-theta-max-deg 27.0
ea xrd build-assignment-packet /path/to/ea-project --builtin-library builtin_material_assignments --material hbn --feature 002
ea references register-seeds /path/to/ea-project --source-packet suggestions/xrd/source-packets/xrd_assignment_source_packet-20260630-001.yml
ea review add /path/to/ea-project --target-type xrd_columns --target-ref raw/xrd/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "x=two_theta, y=intensity, unit=2theta_deg"
ea review add /path/to/ea-project --target-type xrd_parameters --target-ref raw/xrd/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default XRD parameters confirmed"
ea xrd process /path/to/ea-project --metadata raw/xrd/char-20260630-001/metadata.yml --x-column two_theta --y-column intensity --x-unit 2theta_deg --column-review-ref review-20260630-001 --parameter-review-ref review-20260630-002 --sample-ref sample-001
ea xrd suggest-assignments /path/to/ea-project --metadata processed/sample-001/xrd/res-project-xrd-20260630-001/xrd_metadata.yml --source-file suggestions/xrd/source-packets/xrd_assignment_source_packet-20260630-001.yml
ea xrd prepare-review /path/to/ea-project --suggestion suggestions/xrd/suggestion-20260630-001/xrd_assignment_suggestions.yml
ea review add /path/to/ea-project --target-type xrd_assignment_suggestions --target-ref suggestions/xrd/suggestion-20260630-001/xrd_assignment_suggestions.yml --user-response "可以，保存" --reviewed-content "reviewed XRD assignment suggestion candidates"
ea xrd report /path/to/ea-project --metadata processed/sample-001/xrd/res-project-xrd-20260630-001/xrd_metadata.yml --sample-ref sample-001 --experiment-ref exp-001 --assignment-suggestion suggestions/xrd/suggestion-20260630-001/xrd_assignment_suggestions.yml --assignment-review-ref review-20260630-003
```

Future XRD work should add background subtraction, K-alpha doublet handling, crystallite-size estimates with instrument broadening review, richer phase-reference libraries, batch/replicate comparisons, texture metrics, and user-confirmed memory-candidate generation from report interpretations.
