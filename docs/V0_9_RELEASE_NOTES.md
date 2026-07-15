# Experimental Assistant v0.9.9 Release Notes

v0.9.9 is the final planned feature release before v1.0. It makes literature data collection schema-driven, closes the Chinese-report and figure-delivery issues found in the test1 run, provides a single guided first-project journey, and removes the retired Compatibility skill while preserving historical project readers.

## Version

- Package version: `0.9.9`
- Release label: `v0.9.9`
- Distribution: `experimental-assistant`
- CLI: `ea`
- Public Codex skill: `$ea` only
- License: Apache-2.0

## Major Changes Since v0.9.8

- Literature data collection now accepts any user-requested category through a validated schema. Numeric, range, uncertainty, text, enum, boolean, date/time, list, and nested fields share one plan → extract → review → validate → plot/export engine. The six electrical-property presets remain convenient templates, not an allowlist.
- Schema semantic hashes, evidence requirements, comparison/conflict policies, and explicit migration states prevent silent reinterpretation. Only accepted or edited records can reach downstream statistics, figures, reports, or exports.
- All eight characterization report paths use keyed Chinese/English dynamic messages. Unknown generated English sentences degrade to a localized review-bound candidate instead of leaking into a Chinese report.
- Figure source data is rendered with its figure and no longer repeated as a report-level “图下数据” block. Friendly HTML omits the audit appendix by default; audit details are opt-in.
- Report-bound PNG footers use scalable fonts, minimum display-size checks, wrapping, contrast and clipping metadata so long `FigID`/`Report` values remain readable.
- `ea journey` provides one read-only next action at a time from project creation through verified export, while preserving expert commands and interaction-mode boundaries.
- The former `Experimental Assistant (Compatibility)` skill is absent from source, packages, setup targets, and release artifacts. Historical project/protocol identifiers remain readable.
- Release acceptance uses automated tests, public benchmarks, deterministic mock integration, fresh simulated-agent journeys/scientific reviews, and manual artifact inspection. Evidence types are explicit and cannot be represented as real-user or independent-expert validation.

## Relationship To v1.0

Real-user trials, external expert sign-off, and a live Zotero account are no longer pre-v1 promotion gates. v1.0 promotion instead requires the current-candidate automated/platform/package gates, public benchmarks, five-target Mock integration, candidate-bound simulated reviews, issue disposition, and a truthful readiness dossier with no unresolved blocker. External trials may be collected after v1.0 as improvement evidence.

## Concrete Limits

EA organizes reviewable evidence; it does not independently prove material identity, phase, composition, mechanism, performance, or literature completeness. Arbitrary schemas make data categories representable but do not guarantee that every PDF is extractable or every reported value is comparable. Zotero/browser/institution operations remain optional, user-authorized integrations and never bypass access controls.

## Migration

Run `ea migrate status` and `ea migrate plan` before changing an existing project. Use `$ea` for every new Codex task. Old project records are not rewritten merely to change version or product naming.
