# Experimental Assistant v1.0.0 Publication Verification

Status: `pass`.

Experimental Assistant v1.0.0 was published from release commit `8f0e407c6b54e4e8e69ad62b3ece9498e524b62e` with annotated tag `v1.0.0` at <https://github.com/gongchenisbusy/Experimental-Assistant/releases/tag/v1.0.0>.

## Public asset replay

- Downloaded all 13 GitHub Release assets into a new empty directory.
- Compared every downloaded asset byte-for-byte with its tag-worktree upload source; all 13 matched.
- Verified the Skill ZIP and repository ZIP SHA-256 sidecars.
- Verified the 500-file repository archive and embedded v1 manifest.
- Confirmed install-smoke, reproducibility, vulnerability, and distribution-checklist records report `pass`; vulnerability count is zero.
- Installed the downloaded wheel and sdist into separate fresh Python 3.12 environments; both reported `experimental-assistant 1.0.0`.
- Installed and validated the downloaded `$ea` Skill, then passed `ea doctor` with the downloaded wheel.
- Replayed public v0.9.9 CLI/Skill → public v1.0.0 CLI/Skill → public v0.9.9 rollback successfully.
- Updated the maintainer user environment from v0.9.9 to v1.0.0 with a recoverable Skill backup; `ea doctor` passed.

## Final hashes

| Artifact | SHA-256 |
|---|---|
| Wheel | `1bfe96c6f0c1e52d0a51294f5d7f8d99a3d4ede03b6ac6b2eeffe9f9b8162a26` |
| Source distribution | `0d9b287323127ef11eed9cd49d0a13a85d02d833afba10c17de2ae7c84076b5f` |
| Skill bundle | `722392a4123db39c78852dc1c84cca4d82d3fdcdff1b7d14b1f864cff6a0ca7e` |
| Repository release package | `d1d84d9feef4703ae86e07a349715104724bfae2104f69eb5e2edb6e2e8a7be8` |

The machine-readable record is [V1_0_PUBLICATION_VERIFICATION.yml](V1_0_PUBLICATION_VERIFICATION.yml). Optional detached signing was not performed because no user-managed release key was supplied; PyPI publication was not part of this GitHub Release.
