# XPS Parameter Suggestion Review Package

## Summary
- review_package_id: `suggestion-20260603-002-review-package`
- project_id: `prj-public-xps-be-example`
- suggestion_ref: `suggestions/xps/suggestion-20260603-002/xps_parameter_suggestions.yml`
- selected_candidates: `4` / `4`
- status: `review_package_prepared`

## Status Counts
- `ready_for_user_review`: 4

## Candidate Groups
### ready_for_user_review
- candidate_ids: `xps-builtin-o1s-lattice-oxide-binding-energy-candidate, xps-builtin-o1s-hydroxyl-adsorbed-oxygen-binding-energy-candidate, xps-builtin-o1s-carbonate-carbonyl-binding-energy-candidate, xps-builtin-o1s-silica-organic-co-binding-energy-candidate`
- recommended_action: Review these candidates with the user; create a ReviewRecord only after explicit confirmation.

## Candidates
### `xps-builtin-o1s-lattice-oxide-binding-energy-candidate`
- group/status: `ready_for_user_review` / `ready_for_user_review`
- suggestion_type: `binding_energy_candidate`
- target_parameter_path: `interpretation.binding_energy_candidates`
- element/core_level: `O` / `1s`
- chemical_state_label: `Lattice oxygen / metal oxide O 1s candidate`
- parameter_values: chemical_state_label=Lattice oxygen / metal oxide O 1s candidate; expected_binding_energy_eV=529.8; binding_energy_window_eV=[529.0, 531.0]; calibration_reference=Candidate assumes reviewed O 1s energy calibration; source examples commonly reference C 1s at 284.8 eV, but the project must document its actual charge-neutralization and BE-referencing procedure and should cross-check a relevant metal core level when possible.; charge_reference_assumption=No charge correction is applied by this candidate; differential charging and incorrect BE correction can move O 1s intensity between candidate regions.; calibration_group_id=not recorded; overlap_notes=O 1s may overlap Na KLL, Sb 3d, Pd 3p, or V 2p regions depending on the sample., The high-binding-energy side of oxide O 1s can overlap hydroxyl, carbonate, adsorbed water, organic oxygen, loss features, or asymmetric conducting-oxide line shapes.
- references: `builtin-xps-thermo-o, builtin-xps-cardiff-o1s-reference, builtin-xps-o1s-metal-oxide-insight-2025, builtin-xps-charge-reference-guide-2020`
- unresolved_references: `not recorded`
- confidence: `medium`
- source_summary: Thermo and Cardiff public O 1s references list metal oxide / M-O O 1s around 529-530 eV, while recent O 1s guidance describes lattice oxygen in transition-metal oxides around 529.5-531 eV and stresses calibration and corroborating evidence.
- applicability_notes: Use only when a metal oxide or oxide-surface context is plausible and the user has reviewed sample handling, calibration, background, and metal core-level context., Treat a lattice-oxide candidate as an interpretation hypothesis for report discussion, not as an automatic oxide stoichiometry or phase assignment.
- caveats: Not a standalone proof of oxide phase, oxide stoichiometry, oxide thickness, oxygen deficiency, or catalytic activity., Requires project-specific metal core-level, C 1s, calibration, and sample-history evidence before final assignment.
- recommended_action: Ask the user to accept, reject, or edit this source-backed binding-energy candidate before any report or memory discussion; do not treat it as chemical-state proof.

### `xps-builtin-o1s-hydroxyl-adsorbed-oxygen-binding-energy-candidate`
- group/status: `ready_for_user_review` / `ready_for_user_review`
- suggestion_type: `binding_energy_candidate`
- target_parameter_path: `interpretation.binding_energy_candidates`
- element/core_level: `O` / `1s`
- chemical_state_label: `Hydroxyl / adsorbed oxygen-like O 1s candidate`
- parameter_values: chemical_state_label=Hydroxyl / adsorbed oxygen-like O 1s candidate; expected_binding_energy_eV=531.5; binding_energy_window_eV=[531.0, 532.2]; calibration_reference=Candidate assumes reviewed O 1s calibration and charge compensation; compare with lattice O 1s, C 1s, and relevant metal core levels before interpretation.; charge_reference_assumption=No charge correction is applied by this candidate; poor charge correction or differential charging can mimic a higher-BE shoulder.; calibration_group_id=not recorded; overlap_notes=Carbonate, organic C=O/C-O, adsorbed water, silica/silicone contamination, and some fitted defect labels can occupy similar O 1s ranges., If the candidate is being used to discuss oxygen vacancies, require independent evidence and keep the O 1s evidence low-confidence unless the experiment is specifically designed for that question.
- references: `builtin-xps-o1s-metal-oxide-insight-2025, builtin-xps-o1s-oxygen-vacancy-critical-2025, builtin-xps-charge-reference-guide-2020`
- unresolved_references: `not recorded`
- confidence: `low`
- source_summary: Recent O 1s guidance describes hydroxide / adsorbed oxygen contributions near 531-532 eV, while warning that this region overlaps carbonate, organics, water, and oxygen-vacancy labels used in the literature.
- applicability_notes: Use when sample storage, air/water exposure, surface treatment, or reaction environment makes hydroxylated or adsorbed oxygen species plausible., Ask for C 1s, metal core-level, vacuum/transfer history, and any in situ or ex situ context before promoting the candidate in a report.
- caveats: Not an oxygen-vacancy proof., Not a standalone hydroxyl quantification; fitting model, FWHM, background, sample history, and corroborating spectra must be reviewed.
- recommended_action: Ask the user to accept, reject, or edit this source-backed binding-energy candidate before any report or memory discussion; do not treat it as chemical-state proof.

### `xps-builtin-o1s-carbonate-carbonyl-binding-energy-candidate`
- group/status: `ready_for_user_review` / `ready_for_user_review`
- suggestion_type: `binding_energy_candidate`
- target_parameter_path: `interpretation.binding_energy_candidates`
- element/core_level: `O` / `1s`
- chemical_state_label: `Carbonate / carbonyl-like O 1s candidate`
- parameter_values: chemical_state_label=Carbonate / carbonyl-like O 1s candidate; expected_binding_energy_eV=531.8; binding_energy_window_eV=[531.0, 532.5]; calibration_reference=Candidate assumes the O 1s and C 1s energy scales have been reviewed; carbonate discussion should be cross-checked against a C 1s carbonate/carboxylate-like contribution near 289-290 eV when available.; charge_reference_assumption=No charge correction is applied by this candidate; document the project BE reference and charge neutralization before report use.; calibration_group_id=not recorded; overlap_notes=Hydroxyl, adsorbed oxygen, organic oxygen, and carbonate contributions can overlap strongly around 531-532 eV., O 1s alone generally cannot separate carbonate from carbonyl/organic oxygen without C 1s and sample-context evidence.
- references: `builtin-xps-thermo-o, builtin-xps-cardiff-o1s-reference, builtin-xps-o1s-metal-oxide-insight-2025, builtin-xps-charge-reference-guide-2020`
- unresolved_references: `not recorded`
- confidence: `low`
- source_summary: Thermo and Cardiff list metal carbonate O 1s around 531-532 eV, and Thermo also places organic C=O near 531.5-532 eV; Cardiff guidance recommends checking C 1s near 289-290 eV for carbonate evidence.
- applicability_notes: Use when sample exposure, carbonate precursor, ambient aging, CO2/H2O exposure, or C 1s evidence makes carbonate or carbonyl-like oxygen plausible., Treat carbonate and carbonyl as competing explanations unless project chemistry or registered references separate them.
- caveats: Not a standalone carbonate, carbonyl, or contamination proof., Do not quantify carbonate versus hydroxyl from O 1s without a reviewed fitting protocol and corroborating C 1s evidence.
- recommended_action: Ask the user to accept, reject, or edit this source-backed binding-energy candidate before any report or memory discussion; do not treat it as chemical-state proof.

### `xps-builtin-o1s-silica-organic-co-binding-energy-candidate`
- group/status: `ready_for_user_review` / `ready_for_user_review`
- suggestion_type: `binding_energy_candidate`
- target_parameter_path: `interpretation.binding_energy_candidates`
- element/core_level: `O` / `1s`
- chemical_state_label: `Silica / organic C-O high-BE O 1s candidate`
- parameter_values: chemical_state_label=Silica / organic C-O high-BE O 1s candidate; expected_binding_energy_eV=532.9; binding_energy_window_eV=[532.5, 533.5]; calibration_reference=Candidate assumes reviewed O 1s calibration; compare with Si 2p, C 1s, instrument/sample contamination history, and any project-approved charge-reference method before interpretation.; charge_reference_assumption=No charge correction is applied by this candidate; insulating silica or polymer/organic surfaces require documented charge-neutralization and BE-referencing choices.; calibration_group_id=not recorded; overlap_notes=SiO2, organic C-O, adsorbed water, silicone contamination, and high-BE shoulders can overlap in this range., High-BE O 1s intensity can also be affected by loss features or line-shape asymmetry in some conducting oxides.
- references: `builtin-xps-thermo-o, builtin-xps-cardiff-o1s-reference, builtin-xps-o1s-metal-oxide-insight-2025, builtin-xps-charge-reference-guide-2020`
- unresolved_references: `not recorded`
- confidence: `low`
- source_summary: Thermo and Cardiff list SiO2 O 1s near 532.9 eV and organic C-O oxygen near about 533 eV; Thermo cautions that water and organic contamination can overlap directly with SiO2 in O 1s.
- applicability_notes: Use when silica, silicate, silicone/lab contamination, polymer, adsorbed organic oxygen, or high-BE O 1s context is plausible., Cross-check Si 2p and C 1s before choosing between silica-like and organic C-O interpretations.
- caveats: Not a standalone proof of SiO2, silicate, organic C-O, adsorbed water, or contamination source., Requires project-specific Si 2p/C 1s evidence, background/fitting review, and sample-history context before final assignment.
- recommended_action: Ask the user to accept, reject, or edit this source-backed binding-energy candidate before any report or memory discussion; do not treat it as chemical-state proof.

## Suggested Commands
- create_review_record: `ea review add /path/to/ea-project --target-type xps_parameter_suggestions --target-ref suggestions/xps/suggestion-20260603-002/xps_parameter_suggestions.yml --user-response "可以，保存" --reviewed-content "User reviewed the listed XPS parameter candidates; record accepted/rejected/edited candidate IDs."`
- report_with_suggestion: `ea xps report /path/to/ea-project --metadata <xps_metadata.yml> --parameter-suggestion suggestions/xps/suggestion-20260603-002/xps_parameter_suggestions.yml`
- propose_memory_after_review: `ea xps propose-memory /path/to/ea-project --suggestion suggestions/xps/suggestion-20260603-002/xps_parameter_suggestions.yml --review-ref <review-id>`

## Boundaries
- This package prepares review context only; it does not create a ReviewRecord.
- It does not apply XPS parameters, run fitting/background subtraction, inject report citations, write confirmed memory, prove chemical state, or calculate composition.
- Unresolved or invalid candidates remain visible so the user can decide whether to fix, exclude, or discuss them with caveats.
