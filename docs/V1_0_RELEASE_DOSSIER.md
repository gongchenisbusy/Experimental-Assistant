# Experimental Assistant v1.0.0 Release Dossier

Current status: `released and public download replay passed`.

The machine-readable authority is [V1_0_RELEASE_DOSSIER.yml](V1_0_RELEASE_DOSSIER.yml). This dossier is new for v1.0 and does not overwrite the historical [V1_0_READINESS_DOSSIER.yml](V1_0_READINESS_DOSSIER.yml), which records the v0.9.9 promotion snapshot.

Tested candidate `5736bcdadeb28f93055312f4f92f1fcf200c0018` passed the full 458-test regression, public release smoke, Raman golden benchmark, native Windows/Ubuntu/macOS Python 3.11–3.13 CI, minimum dependencies, quality checks, clean install/update/rollback/uninstall lifecycle, reproducible distributions, SBOM and vulnerability checks, and release-package/Skill-bundle verification.

Release commit `8f0e407c6b54e4e8e69ad62b3ece9498e524b62e` was tagged `v1.0.0`; all 13 public assets were downloaded into a fresh directory and passed byte comparison, checksums, clean wheel/sdist installation, Skill/doctor validation, and public v0.9.9 update/rollback replay. See [V1_0_PUBLICATION_VERIFICATION.md](V1_0_PUBLICATION_VERIFICATION.md).
