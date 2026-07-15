# Experimental Assistant v0.9.8 Manual Test Checklist

Record tester, operating system, Python version, commit/tag, date, commands, artifact paths, and each failure. Do not convert an unchecked item into inferred evidence.

## Install And Identity

- [ ] Install the wheel in a clean environment and run PATH-resolved `ea version --json`, `ea capabilities --json`, `ea doctor --json`, and `ea --help`.
- [ ] Repeat from the sdist.
- [ ] Run `ea setup`, restart Codex, and invoke `$ea` in a fresh task.
- [ ] Confirm wheel/sdist setup uses their bundled skills without a repository clone; separately verify the release skill ZIP and SHA-256 sidecar.
- [ ] On native Windows, repeat setup under a path longer than 260 characters and validate Chinese GBK console output without mojibake or `UnicodeDecodeError`.
- [ ] Confirm `$ea-v0-2` routes to `$ea` without loading a second full instruction set.
- [ ] Preview update, rollback, and uninstall; perform them only in a disposable test environment.

## First Project

- [ ] Preview and confirm `ea start` using a non-developer path and Chinese project metadata.
- [ ] Run status, healthcheck, eval, and brief; confirm default output is concise and useful.
- [ ] Preview/import UTF-8 BOM, GB18030/CP936, and comma/tab/semicolon fixtures; reject changed hashes, directories, binaries, and unapproved symlinks.
- [ ] Interrupt a migration or atomic write in a disposable project and verify journal/backup recovery.
- [ ] Exercise consult, record, execute, and audit boundaries and verify blocked commands explain next actions.

## Scientific And Export

- [ ] Run all four packaged examples through healthcheck/eval.
- [ ] Complete one reviewed inspect/process/report path from imported raw data.
- [ ] Export HTML and a traced report bundle; run `ea export verify-bundle` and `ea export verify-archive`.
- [ ] Record the exact `ea export report-bundle ... --include-trace --zip` command used for the handoff artifact.
- [ ] Run Raman golden benchmark and inspect the external-review status without marking it complete.

## Literature

- [ ] Run `ea literature zotero-readiness` in no-Zotero degraded mode and a mixed acquired/blocked five-paper handoff.
- [ ] Import one acquisition v1 handoff through the v2 reader, confirm the source file is unchanged, and resume one partial v2 batch without duplicate targets/cache objects.
- [ ] Run one public OA DOI through resolve, PDF signature/page/hash validation, content-addressed storage, warm-cache reuse, and EA reconciliation.
- [ ] Confirm login/subscription blockers pause for user action and expose no signed URL, cookie, token, profile, or session value.
- [ ] Run the ten-paper evidence-dataset pilot; review accept/reject/edit/defer/not-comparable states.
- [ ] Confirm only accepted/edited values enter plots and the privacy export excludes raw/private full text and absolute source paths.
- [ ] Confirm an image-only PDF produces OCR-required rather than fabricated data.

## Release Engineering

- [ ] Full tests and both skill validations pass.
- [ ] Native CI passes on Windows, Ubuntu, macOS with Python 3.11-3.13; Python 3.14 result is recorded separately.
- [ ] Clean wheel/sdist builds are reproducible under the documented conditions.
- [ ] SBOM exists and vulnerability report status is `pass`.
- [ ] Release manifest, repository package, SHA-256 sidecar, package verification, and distribution checklist pass.
- [ ] Compact skill ZIP and its SHA-256 sidecar pass `skill_distribution.bundle` in the distribution checklist.
- [ ] Public release assets can be downloaded and independently verified/installed.

## v1.0 Promotion

- [ ] Independent novice trials pass on each supported OS family.
- [ ] Independent scientific reviewer signs off Raman benchmark interpretation and literature-dataset evidence fidelity.
- [ ] Public issue #1-#7 disposition is recorded with no unresolved blocker.
- [ ] Known limitations and support policy match observed behavior.
