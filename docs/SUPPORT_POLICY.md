# Support And Compatibility Policy

## Supported Runtime Target

v1.0.0 targets Python 3.11, 3.12, and 3.13 on native Windows, Ubuntu, and macOS CI runners. Python 3.14 is observation-only until the complete release gate passes.

Only platform and Python combinations shown as passing in the release checklist are advertised as supported.

## Compatibility

- v0.9.x projects remain readable without automatic destructive rewrites.
- Project-format migrations are explicit, backed up, reversible, and idempotent.
- `$ea` is the only supported Codex skill. The former Compatibility skill is removed before v1.0.
- Historical provenance and project records retain their original version identifiers.

## Support Channels

- Bugs and feature requests: GitHub issues.
- Security vulnerabilities: private email process in `SECURITY.md`.
- Scientific questions: include method, input type, units, assumptions, and a public-safe minimal example.

EA does not guarantee exhaustive literature coverage or autonomous scientific proof. Beta and experimental capabilities have narrower support commitments described in `docs/CAPABILITY_MATRIX.md`.
