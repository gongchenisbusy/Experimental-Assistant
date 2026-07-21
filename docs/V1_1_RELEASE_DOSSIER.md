# Experimental Assistant v1.1.0 Release Dossier

This dossier links the issue-derived implementation to public release gates. Machine-readable final gate results are in `docs/V1_1_RELEASE_DOSSIER.yml`.

## Required gates

- Full pytest and issue-focused regressions.
- `$ea` and EA-feedback Skill structural validation plus task-like forward testing.
- Version identity, downloaded-Skill instructions, documentation links, and public example health/evaluation.
- Clean build, wheel/sdist install smoke, release package verification, content checksums, detached signature verification, SBOM, vulnerability audit, artifact smoke, and reproducibility.
- GitHub PR checks, merge to `main`, v1.1.0 tag/Release assets, public download replay, and issue disposition verification.

The release is not complete while any required gate is pending or while public `main`, tag, package/Skill identity, and downloadable assets disagree.
