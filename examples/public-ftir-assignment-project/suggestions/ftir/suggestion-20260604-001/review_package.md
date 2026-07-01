# FTIR Assignment Suggestion Review Package

## Summary
- review_package_id: `suggestion-20260604-001-review-package`
- project_id: `prj-public-ftir-assignment-example`
- suggestion_ref: `suggestions/ftir/suggestion-20260604-001/ftir_assignment_suggestions.yml`
- selected_candidates: `4` / `4`
- status: `review_package_prepared`

## Status Counts
- `ready_for_user_review`: 4

## Candidate Groups
### ready_for_user_review
- candidate_ids: `ftir-builtin-oh-nh-stretching-generic, ftir-builtin-aliphatic-ch-stretching-generic, ftir-builtin-carbonyl-co-stretching-generic, ftir-builtin-sio-stretching-generic`
- recommended_action: Review these candidates with the user; create a ReviewRecord only after explicit confirmation.

## Candidates
### `ftir-builtin-oh-nh-stretching-generic`
- group/status: `ready_for_user_review` / `ready_for_user_review`
- assignment: `broad O-H or N-H stretching candidate` (`functional_group`)
- matched_band_ids: `ftir-band-001`
- matched_wavenumbers_cm-1: `3400.0`
- references: `builtin-ftir-socrates-2001, builtin-ftir-colthup-1990`
- unresolved_references: `not recorded`
- confidence: `low`
- source_summary: Standard group-frequency references list broad O-H and N-H stretching absorptions in this high-wavenumber region, with strong overlap from water and hydrogen bonding.
- applicability_notes: Use only as a broad screening candidate until atmosphere, drying, sample preparation, and chemistry are reviewed., Broadness and band shape matter; a single maximum is weaker evidence than a reviewed broad envelope.
- caveats: Moisture, hydrogen bonding, and sample-preparation artifacts commonly affect this region., This window does not distinguish O-H from N-H without project context and additional evidence.
- recommended_action: Ask the user to accept, reject, or edit this source-backed assignment before report/memory reuse.

### `ftir-builtin-aliphatic-ch-stretching-generic`
- group/status: `ready_for_user_review` / `ready_for_user_review`
- assignment: `aliphatic C-H stretching candidate` (`functional_group`)
- matched_band_ids: `ftir-band-002`
- matched_wavenumbers_cm-1: `2920.0`
- references: `builtin-ftir-socrates-2001, builtin-ftir-colthup-1990`
- unresolved_references: `not recorded`
- confidence: `low`
- source_summary: Standard group-frequency references place aliphatic C-H stretching bands in the 2850-2970 cm^-1 region for many organic materials.
- applicability_notes: Compare with project chemistry and sample history before interpreting as a real material component., Check whether binders, solvents, ligands, or handling residues could explain the feature.
- caveats: Organic contamination and processing residues can produce similar bands., Band-window match alone is not proof of alkyl groups in the target material.
- recommended_action: Ask the user to accept, reject, or edit this source-backed assignment before report/memory reuse.

### `ftir-builtin-carbonyl-co-stretching-generic`
- group/status: `ready_for_user_review` / `ready_for_user_review`
- assignment: `carbonyl C=O stretching candidate` (`functional_group`)
- matched_band_ids: `ftir-band-003`
- matched_wavenumbers_cm-1: `1720.0`
- references: `builtin-ftir-socrates-2001, builtin-ftir-colthup-1990`
- unresolved_references: `not recorded`
- confidence: `low`
- source_summary: Standard group-frequency references place many C=O stretching absorptions in the 1650-1800 cm^-1 region, with position depending strongly on conjugation, hydrogen bonding, and functional group class.
- applicability_notes: Treat this as a candidate family, not a specific carbonyl environment., Use project chemistry, neighboring bands, and references to distinguish ester, acid, amide, carbonate, or other carbonyl-like sources.
- caveats: Water bending, amide bands, C=C modes, and other overlapping bands can affect this region., The candidate does not identify a specific compound or carbonyl environment by itself.
- recommended_action: Ask the user to accept, reject, or edit this source-backed assignment before report/memory reuse.

### `ftir-builtin-sio-stretching-generic`
- group/status: `ready_for_user_review` / `ready_for_user_review`
- assignment: `Si-O or inorganic oxide stretching candidate` (`functional_group`)
- matched_band_ids: `ftir-band-004`
- matched_wavenumbers_cm-1: `1100.0`
- references: `builtin-ftir-socrates-2001, builtin-ftir-colthup-1990`
- unresolved_references: `not recorded`
- confidence: `low`
- source_summary: Standard group-frequency references and common FTIR practice associate strong Si-O or related oxide network stretching bands with the 900-1150 cm^-1 region, but exact positions are system-dependent.
- applicability_notes: Use project material identity and reference spectra to distinguish Si-O from organic fingerprint bands., Check whether the sample, substrate, filler, or support contains silica or other oxides.
- caveats: Organic C-O/C-N fingerprint bands can overlap this region., This candidate is not a definitive oxide-network assignment.
- recommended_action: Ask the user to accept, reject, or edit this source-backed assignment before report/memory reuse.

## Suggested Commands
- create_review_record: `ea review add /path/to/ea-project --target-type ftir_assignment_suggestions --target-ref suggestions/ftir/suggestion-20260604-001/ftir_assignment_suggestions.yml --user-response "可以，保存" --reviewed-content "User reviewed the listed FTIR assignment candidates; record accepted/rejected/edited candidate IDs."`
- report_with_suggestion: `ea ftir report /path/to/ea-project --metadata <ftir_metadata.yml> --assignment-suggestion suggestions/ftir/suggestion-20260604-001/ftir_assignment_suggestions.yml`
- propose_memory_after_review: `ea ftir propose-memory /path/to/ea-project --suggestion suggestions/ftir/suggestion-20260604-001/ftir_assignment_suggestions.yml --review-ref <review-id>`

## Boundaries
- This package prepares review context only; it does not create a ReviewRecord.
- It does not apply FTIR assignments, change processing outputs, inject report citations, write confirmed memory, or prove composition/functional groups.
- Unresolved or invalid candidates remain visible so the user can decide whether to fix, exclude, or discuss them with caveats.
