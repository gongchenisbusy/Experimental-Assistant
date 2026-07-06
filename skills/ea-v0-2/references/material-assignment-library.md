# Material Assignment Library

Use this reference when an EA workflow needs to inspect or extend built-in material assignment records for characterization data.

Current Experimental Assistant v0.9.6 compatibility scope:

- Built-in records live in `src/ea/materials/assignments.yml`.
- Built-in profiles include `mos2` and `ws2` with Raman, PL, and XRD screening records, plus `hbn` with Raman and XRD screening records.
- `ea materials list` shows available material profiles.
- `ea materials audit-assignment-library` audits material/method/candidate counts, DOI reference-hint coverage, any missing-reference candidate IDs, recommended discovery commands, and no-auto-application boundaries. Add `--material` and/or `--method` to narrow the audit.
- `ea materials show mos2`, `ea materials show ws2`, or `ea materials show hbn` shows the full material profile.
- `ea materials assignments mos2 --method raman`, `ea materials assignments ws2 --method pl`, or `ea materials assignments hbn --method xrd` shows method-specific assignment rules. `--method` may be `raman`, `pl`, or `xrd` where that method exists; omitting it returns all method records.

The library is a deterministic local rule source, not a substitute for scientific review:

- Assignment records provide peak/energy/2theta screening windows and report text for confidence-labeled possible interpretations.
- The audit command is read-only metadata inspection. It does not search literature, register references, create project files, process spectra or diffraction patterns, match peaks, create ReviewRecords, inject citations, write memory, or prove scientific claims.
- Generated reports still need registered `reference_ids` when a claim is literature-supported. Built-in `reference_hints` are discovery hints, not automatically cited project references.
- Current built-in Raman/PL/XRD candidates all have method-level DOI reference hints. Future library expansion should keep the audit `ready` or clearly expose missing-reference candidates for follow-up enrichment.
- If a project uses a material not present in the library, workflows should keep generic low-confidence interpretation text and avoid invented assignments.
- New material records should include aliases, caveats, method-specific `assignment_source`, feature rules, interpretation text, and regression tests.
- Generated result metadata with `peak_analysis.assigned_features` must preserve `assignment_source` at both result and feature level; healthcheck treats missing sources as traceability errors.

Current built-in records:

- MoS2 Raman: E2g-like and A1g-like candidate windows, mode-separation screening, and peak-table assignment fields.
- MoS2 PL: dominant near-band-edge emission candidate window for eV/nm data where energy can be determined.
- MoS2 XRD: DOI-backed low-angle layered-reflection candidate window for first-pass 2theta patterns.
- WS2 Raman: E2g/2LA-like and A1g-like candidate windows with an explicit caveat that resonant 2LA(M), excitation wavelength, and calibration affect interpretation.
- WS2 PL: dominant near-band-edge emission candidate window for eV/nm data where energy can be determined.
- WS2 XRD: low-angle layered-reflection candidate window for first-pass 2theta patterns.
- h-BN Raman: single E2g-like candidate window near bulk h-BN, with isotope/layer/strain caveats.
- h-BN XRD: (002)-type layered-reflection candidate window for first-pass 2theta patterns.

When extending the library:

1. Add or revise `src/ea/materials/assignments.yml`.
2. Keep records conservative and sourceable; phrase conclusions as possible assignments with confidence labels.
3. Add matcher tests in `tests/test_material_assignments.py`.
4. Add or update workflow and healthcheck/evaluator tests if generated metadata, peak-table columns, or assignment-source fields change.
5. Update this reference and any affected method workflow reference.
