# Governance

Experimental Assistant is maintained in the public repository owned by `@gongchenisbusy`.

## Roles And Publication Ownership

- **Maintainer and release owner:** the public repository owner, `@gongchenisbusy`, reviews changes, owns repository settings, verifies the release checklist, and publishes tags and assets.
- **Security triage owner:** the repository owner receives private reports through `ea_feedback@163.com` and coordinates disclosure.
- **Scientific reviewer:** an independent domain expert reviews declared inputs, units, tolerances, limitations, and claims before a capability can be labelled stable.

The maintainer may delegate a specific release operation in writing, but the resulting tag/assets remain owned by the public repository. A release owner may not self-approve the independent scientific-review gate. Release evidence must identify who performed each approval.

## Decisions

- Routine changes use pull requests and automated checks.
- Changes to raw-data protection, project migration, review gates, provenance, literature-access boundaries, or stable scientific claims require maintainer review.
- Stable capability promotion requires benchmark evidence and a recorded scientific review.
- A public release requires all mandatory checks in `docs/PUBLIC_ACCEPTANCE_MATRIX.md` and `docs/RELEASE_VERIFICATION.md`.

## Compatibility

- The public CLI and skill names are `ea` and `$ea`.
- `$ea-v0-2` remains a compatibility entry point through the v1.0.x release line.
- Historical project records are read without rewriting their recorded package or skill identity.
- Deprecations require one release-line notice, a migration path, and rollback instructions.
