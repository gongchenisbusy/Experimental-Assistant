# Release Security Policy

Experimental Assistant v1.1.0 release candidates must be built in a clean virtual environment from the declared dependency ranges and the fully resolved `requirements/release.txt` constraints. The same constraints are passed into isolated build-backend installation.

The official sdist is passed through `ea-release-reproducibility`, which normalizes archive metadata and verifies it against a second build before publication. The wheel must already be byte-identical without post-processing.

Before publication, maintainers generate:

- `experimental-assistant-1.1.0-sbom.json`, CycloneDX 1.5 inventory of the clean release environment.
- `experimental-assistant-1.1.0-vulnerability-report.json`, `pip-audit` results for that environment.
- wheel, sdist, repository release archive, and SHA-256 sidecars.

Any known vulnerability reported by the release scanner is blocking unless a public release allowlist records the vulnerability ID, affected scope, owner, technical rationale, compensating control, and expiry date. The v1.1.0 allowlist is empty. Scanner failure or an unavailable scanner is also blocking.

The optional Ed25519 detached signature proves possession of a user-managed release key only when users obtain the trusted public-key fingerprint through an independent stable channel. Checksums detect corruption but do not establish publisher identity by themselves.

Report suspected vulnerabilities through `SECURITY.md`, not a public issue containing exploit or private-project details.
