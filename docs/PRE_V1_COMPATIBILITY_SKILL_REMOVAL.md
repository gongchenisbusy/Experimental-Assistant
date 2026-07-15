# Pre-v1 Compatibility Skill Removal

## Decision

The `Experimental Assistant (Compatibility)` Codex skill is removed after the v0.9.8 release and before v1.0. `$ea` is the only supported public skill invocation.

## Rationale

- There is no material legacy-user population that justifies a duplicate visible skill entry.
- The wrapper adds installation, rollback, packaging, release, documentation, and validation surface without adding product capability.
- Removing it before v1.0 gives the stable release one unambiguous identity.

## Implementation Contract

- Delete `skills/ea-v0-2` from source and distribution data.
- Package and validate only `skills/ea`.
- `ea setup` removes a stale `ea-v0-2` skill directory into a recoverable backup.
- `ea doctor` fails while a stale Compatibility skill remains installed.
- Release smoke, artifact smoke, manifest, compact skill bundle, and distribution checklist require only `$ea` and verify that the retired entry is absent.
- Historical project/provenance identifiers remain readable and are not rewritten automatically.

## Release Boundary

The published v0.9.8 tag and its historical evidence remain unchanged. The removal applies to post-v0.9.8 development and must be present in the final v1.0 release candidate.
