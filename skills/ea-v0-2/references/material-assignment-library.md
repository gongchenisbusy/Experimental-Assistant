# Material Assignment Library

Use this reference when an EA workflow needs to inspect or extend built-in material assignment records for characterization data.

Current v0.2 scope:

- Built-in records live in `src/ea/materials/assignments.yml`.
- The first profile is `mos2`, with screening records for Raman, PL, and XRD.
- `ea materials list` shows available material profiles.
- `ea materials show mos2` shows the full material profile.
- `ea materials assignments mos2 --method raman` shows method-specific assignment rules. `--method` may be `raman`, `pl`, or `xrd`; omitting it returns all method records.

The library is a deterministic local rule source, not a substitute for scientific review:

- Assignment records provide peak/energy/2theta screening windows and report text for confidence-labeled possible interpretations.
- Generated reports still need registered `reference_ids` when a claim is literature-supported. Built-in `reference_hints` are discovery hints, not automatically cited project references.
- If a project uses a material not present in the library, workflows should keep generic low-confidence interpretation text and avoid invented assignments.
- New material records should include aliases, caveats, method-specific `assignment_source`, feature rules, interpretation text, and regression tests.

Current built-in MoS2 records:

- Raman: E2g-like and A1g-like candidate windows, mode-separation screening, and peak-table assignment fields.
- PL: dominant near-band-edge emission candidate window for eV/nm data where energy can be determined.
- XRD: low-angle layered-reflection candidate window for first-pass 2theta patterns.

When extending the library:

1. Add or revise `src/ea/materials/assignments.yml`.
2. Keep records conservative and sourceable; phrase conclusions as possible assignments with confidence labels.
3. Add matcher tests in `tests/test_material_assignments.py`.
4. Add or update workflow tests if generated metadata or peak-table columns change.
5. Update this reference and any affected method workflow reference.
