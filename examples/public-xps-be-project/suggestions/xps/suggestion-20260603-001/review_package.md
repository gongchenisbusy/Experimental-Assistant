# XPS Parameter Suggestion Review Package

## Summary
- review_package_id: `suggestion-20260603-001-review-package`
- project_id: `prj-public-xps-be-example`
- suggestion_ref: `suggestions/xps/suggestion-20260603-001/xps_parameter_suggestions.yml`
- selected_candidates: `5` / `5`
- status: `review_package_prepared`

## Status Counts
- `ready_for_user_review`: 5

## Candidate Groups
### ready_for_user_review
- candidate_ids: `xps-builtin-c1s-adventitious-cc-binding-energy-candidate, xps-builtin-c1s-c-o-c-binding-energy-candidate, xps-builtin-c1s-o-c-o-binding-energy-candidate, xps-builtin-si2p-elemental-binding-energy-candidate, xps-builtin-si2p-sio2-binding-energy-candidate`
- recommended_action: Review these candidates with the user; create a ReviewRecord only after explicit confirmation.

## Candidates
### `xps-builtin-c1s-adventitious-cc-binding-energy-candidate`
- group/status: `ready_for_user_review` / `ready_for_user_review`
- suggestion_type: `binding_energy_candidate`
- target_parameter_path: `interpretation.binding_energy_candidates`
- element/core_level: `C` / `1s`
- chemical_state_label: `Adventitious or hydrocarbon C-C/C-H C 1s candidate`
- parameter_values: chemical_state_label=Adventitious or hydrocarbon C-C/C-H C 1s candidate; expected_binding_energy_eV=284.8; binding_energy_window_eV=[284.6, 285.0]; calibration_reference=User-reviewed C 1s or instrument calibration context required; the Thermo reference notes C-C is often set to 284.8 eV by default but is not always valid.; charge_reference_assumption=Do not use this candidate to apply charge correction automatically; record the actual project charge-neutralization or BE-referencing procedure before report use.; calibration_group_id=not recorded; overlap_notes=C 1s may overlap Ru 3d, Sr 3p1/2, or K 2p in some systems., Adventitious carbon chemistry and film thickness can shift apparent C 1s position.
- references: `builtin-xps-thermo-c, builtin-xps-charge-reference-guide-2020`
- unresolved_references: `not recorded`
- confidence: `medium`
- source_summary: Thermo's carbon XPS reference lists adventitious-carbon C-C near 284.8 eV and explicitly cautions that this default charge reference is not always valid.
- applicability_notes: Use only for spectra where the user confirms adventitious/hydrocarbon carbon is plausible and the C 1s region is reviewed., Treat this as a BE/reference discussion candidate, not as an instruction to shift the spectrum.
- caveats: Not a universal charge reference., Does not prove surface contamination source, carbon hybridization, or sample composition.
- recommended_action: Ask the user to accept, reject, or edit this source-backed binding-energy candidate before any report or memory discussion; do not treat it as chemical-state proof.

### `xps-builtin-c1s-c-o-c-binding-energy-candidate`
- group/status: `ready_for_user_review` / `ready_for_user_review`
- suggestion_type: `binding_energy_candidate`
- target_parameter_path: `interpretation.binding_energy_candidates`
- element/core_level: `C` / `1s`
- chemical_state_label: `C-O-C / C-O C 1s candidate`
- parameter_values: chemical_state_label=C-O-C / C-O C 1s candidate; expected_binding_energy_eV=286.0; binding_energy_window_eV=[285.7, 286.4]; calibration_reference=Candidate assumes the C 1s energy scale has already been reviewed, commonly relative to a project-approved C-C/C-H reference near 284.8 eV or another documented calibration.; charge_reference_assumption=No charge correction is applied by this candidate; insulating or mixed samples require a separately reviewed referencing procedure.; calibration_group_id=not recorded; overlap_notes=C-N, C-O, and ether/alcohol-like contributions can appear in similar C 1s ranges.
- references: `builtin-xps-thermo-c, builtin-xps-charge-reference-guide-2020`
- unresolved_references: `not recorded`
- confidence: `low`
- source_summary: Thermo's carbon XPS reference lists C-O-C near 286 eV in adventitious carbon and C-O near 286 eV for polymers.
- applicability_notes: Use only after C 1s baseline/background and possible overlapping components are reviewed., Interpret with O 1s, sample chemistry, and project literature before assigning oxygenated carbon.
- caveats: C 1s BE alone cannot distinguish all C-O, C-N, ether, alcohol, or contamination contributions., Not a functional-group or composition proof.
- recommended_action: Ask the user to accept, reject, or edit this source-backed binding-energy candidate before any report or memory discussion; do not treat it as chemical-state proof.

### `xps-builtin-c1s-o-c-o-binding-energy-candidate`
- group/status: `ready_for_user_review` / `ready_for_user_review`
- suggestion_type: `binding_energy_candidate`
- target_parameter_path: `interpretation.binding_energy_candidates`
- element/core_level: `C` / `1s`
- chemical_state_label: `O-C=O / carboxylate-like C 1s candidate`
- parameter_values: chemical_state_label=O-C=O / carboxylate-like C 1s candidate; expected_binding_energy_eV=288.5; binding_energy_window_eV=[288.0, 289.2]; calibration_reference=Candidate assumes the C 1s energy scale has already been reviewed, commonly relative to a project-approved C-C/C-H reference near 284.8 eV or another documented calibration.; charge_reference_assumption=No charge correction is applied by this candidate; document charge neutralization and BE referencing before using it as report evidence.; calibration_group_id=not recorded; overlap_notes=Ester, carboxylate, carbonate, and high-BE contamination contributions can overlap in this region.
- references: `builtin-xps-thermo-c, builtin-xps-charge-reference-guide-2020`
- unresolved_references: `not recorded`
- confidence: `low`
- source_summary: Thermo's carbon XPS reference lists O-C=O near 288.5 eV for adventitious carbon and C=O-style polymer contributions around 288-290 eV.
- applicability_notes: Use only when sample chemistry, O 1s data, and reviewed C 1s fitting context make a carboxylate/ester/carbonyl discussion plausible., Review carbonate/ester overlap risks for oxide or carbonate-containing samples.
- caveats: Not a standalone carboxylate, carbonate, ester, or oxidation proof., Requires project-specific chemistry and references for final assignment.
- recommended_action: Ask the user to accept, reject, or edit this source-backed binding-energy candidate before any report or memory discussion; do not treat it as chemical-state proof.

### `xps-builtin-si2p-elemental-binding-energy-candidate`
- group/status: `ready_for_user_review` / `ready_for_user_review`
- suggestion_type: `binding_energy_candidate`
- target_parameter_path: `interpretation.binding_energy_candidates`
- element/core_level: `Si` / `2p`
- chemical_state_label: `Elemental silicon Si 2p candidate`
- parameter_values: chemical_state_label=Elemental silicon Si 2p candidate; expected_binding_energy_eV=99.4; binding_energy_window_eV=[99.0, 99.8]; calibration_reference=User-reviewed instrument or project BE calibration required; compare with any C 1s referencing only after the user confirms that procedure.; charge_reference_assumption=No charge correction is applied by this candidate; conductive, semiconducting, native-oxide, or insulating contexts must be reviewed separately.; calibration_group_id=not recorded; overlap_notes=Native oxide can add higher-BE Si 2p components and change relative intensities.
- references: `builtin-xps-thermo-si, builtin-xps-charge-reference-guide-2020`
- unresolved_references: `not recorded`
- confidence: `medium`
- source_summary: Thermo's silicon XPS reference lists elemental Si 2p around 99.4 eV and notes that Si 2p spin-orbit splitting is mainly considered for elemental Si.
- applicability_notes: Use for silicon wafer, elemental Si, or reduced Si discussion only after oxide thickness, surface cleaning, and pass-energy context are reviewed., Consider the existing Si 2p spin-orbit candidate when fitting resolved elemental Si doublets.
- caveats: Not a proof of elemental silicon fraction or oxide thickness., Does not automatically choose a resolved Si 2p doublet model.
- recommended_action: Ask the user to accept, reject, or edit this source-backed binding-energy candidate before any report or memory discussion; do not treat it as chemical-state proof.

### `xps-builtin-si2p-sio2-binding-energy-candidate`
- group/status: `ready_for_user_review` / `ready_for_user_review`
- suggestion_type: `binding_energy_candidate`
- target_parameter_path: `interpretation.binding_energy_candidates`
- element/core_level: `Si` / `2p`
- chemical_state_label: `Silicon dioxide Si 2p candidate`
- parameter_values: chemical_state_label=Silicon dioxide Si 2p candidate; expected_binding_energy_eV=103.5; binding_energy_window_eV=[103.0, 104.0]; calibration_reference=Thermo lists silicates and nitride as referenced to C 1s at 284.8 eV; this candidate requires the user to review the actual project calibration/reference method before use.; charge_reference_assumption=No charge correction is applied by this candidate; insulating SiO2 or silicate surfaces require documented charge-neutralization and BE-referencing choices.; calibration_group_id=not recorded; overlap_notes=Silicates, aluminosilicates, SiON, and other oxidized Si environments may fall near this region.
- references: `builtin-xps-thermo-si, builtin-xps-charge-reference-guide-2020`
- unresolved_references: `not recorded`
- confidence: `low`
- source_summary: Thermo's silicon XPS reference lists SiO2 Si 2p around 103.5 eV and notes C 1s 284.8 eV referencing for silicates/nitride examples.
- applicability_notes: Use only when SiO2, native oxide, silicate, or oxide-layer context is plausible and reviewed with sample preparation history., Compare elemental Si and oxide components when substrate/native-oxide thickness matters.
- caveats: Not a standalone SiO2 thickness, stoichiometry, or composition proof., Requires project-specific calibration and model review before final assignment.
- recommended_action: Ask the user to accept, reject, or edit this source-backed binding-energy candidate before any report or memory discussion; do not treat it as chemical-state proof.

## Suggested Commands
- create_review_record: `ea review add /path/to/ea-project --target-type xps_parameter_suggestions --target-ref suggestions/xps/suggestion-20260603-001/xps_parameter_suggestions.yml --user-response "可以，保存" --reviewed-content "User reviewed the listed XPS parameter candidates; record accepted/rejected/edited candidate IDs."`
- report_with_suggestion: `ea xps report /path/to/ea-project --metadata <xps_metadata.yml> --parameter-suggestion suggestions/xps/suggestion-20260603-001/xps_parameter_suggestions.yml`
- propose_memory_after_review: `ea xps propose-memory /path/to/ea-project --suggestion suggestions/xps/suggestion-20260603-001/xps_parameter_suggestions.yml --review-ref <review-id>`

## Boundaries
- This package prepares review context only; it does not create a ReviewRecord.
- It does not apply XPS parameters, run fitting/background subtraction, inject report citations, write confirmed memory, prove chemical state, or calculate composition.
- Unresolved or invalid candidates remain visible so the user can decide whether to fix, exclude, or discuss them with caveats.
