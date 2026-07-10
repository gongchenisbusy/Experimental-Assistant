# Experimental Assistant v0.9.7

Experimental Assistant (EA) is a local-first materials-research assistant. It helps organize projects, protect imported raw data, run review-gated characterization workflows, trace reports back to evidence, and coordinate literature work without assuming developer-machine accounts or paths.

Public identity: `Experimental Assistant`, CLI `ea`, Codex skill `$ea`, Python distribution `experimental-assistant`.

Naming note: `$ea-v0-2` is a deprecated compatibility identifier retained through the v1.0.x line. New users and documentation use `$ea`.

Repository: <https://github.com/gongchenisbusy/Experimental-Assistant>

Release: <https://github.com/gongchenisbusy/Experimental-Assistant/releases/tag/v0.9.7>

中文用户可直接阅读 [docs/QUICKSTART_ZH.md](docs/QUICKSTART_ZH.md)。稳定错误码与处理建议见 [docs/ERROR_CATALOG.md](docs/ERROR_CATALOG.md)。

## Install

Python 3.11, 3.12, or 3.13 is supported. Python 3.12 is recommended.

```bash
uv tool install --python 3.12 git+https://github.com/gongchenisbusy/Experimental-Assistant.git@v0.9.7
ea setup
ea doctor
```

Restart Codex, open a new task, and invoke `$ea`. The complete public install, update, rollback, and removal guide is [docs/PUBLIC_INSTALL_AND_CODEX_SKILL_SETUP.md](docs/PUBLIC_INSTALL_AND_CODEX_SKILL_SETUP.md).

## First Project

`ea start` previews the project before writing. Add `--yes` only after checking the proposed location and metadata.

```bash
ea start /path/to/project \
  --name "2D material study" \
  --material "MoS2" \
  --direction "electrical and spectroscopic characterization"
ea start /path/to/project \
  --name "2D material study" \
  --material "MoS2" \
  --direction "electrical and spectroscopic characterization" \
  --yes
ea status /path/to/project
```

Preview a data file without writing, then apply only the exact reviewed hash:

```bash
ea import preview /path/to/spectrum.csv
ea import apply /path/to/project /path/to/spectrum.csv --characterization-type raman --preview-hash SHA256 --yes
ea analyze /path/to/project raw/raman/RECORD/spectrum.csv --method raman
```

EA separates inspection, parameter/review decisions, processing, and reporting. It does not silently infer scientific identity, apply unreviewed parameters, or overwrite protected raw data.

## Interaction Modes

Use `ea mode` for the exact contract.

- `--mode consult`: read-only advice and previews.
- `--mode record`: project notes and review records, but no analysis/report execution.
- `--mode execute`: confirmed processing and artifact creation.
- `--mode audit`: read-only health, provenance, and trace checks.

Mutating commands show a plan or require explicit confirmation. Stable errors report the cause, retry safety, written artifacts, next steps, and a local debug-log reference.

## Everyday Checks

```bash
ea capabilities
ea status /path/to/project
ea healthcheck /path/to/project
ea eval project /path/to/project --no-write
ea brief project /path/to/project
ea diagnostics collect /path/to/project --output /path/to/ea-diagnostics.json
```

Diagnostics are local-only, redact common secrets and signed/session URLs, and exclude raw data, processed data, private full text, and credential stores.

## Characterization Workflows

The ordinary pattern is `inspect -> review -> process -> report`. Detailed commands and scientific boundaries live in `skills/ea/references/cli-command-index.md` and the matching workflow reference.

Command groups include:

```text
ea raman inspect
ea pl inspect
ea xrd inspect
ea ftir inspect
ea uv-vis inspect
ea xps inspect
ea electrochemistry inspect
ea thermal inspect
```

Source-backed candidate discovery remains advisory. Useful expert entry points include `ea ftir list-assignment-libraries`, `ea uv-vis list-source-libraries`, `ea uv-vis build-source-packet`, `ea uv-vis suggest-interpretations`, `ea uv-vis prepare-review`, `ea uv-vis propose-memory`, `ea uv-vis compare-replicates --feature-match-tolerance-ev`, `ea xps list-parameter-libraries`, and the report option `--interpretation-suggestion`.

## Literature Work

EA preserves confirmed query phrases, applies material/application relevance gates, and records acquisition state. It does not bypass subscriptions, authentication, or publisher controls.

```bash
ea literature setup-preflight /path/to/project
ea literature plan /path/to/project
ea literature search-public /path/to/project
ea literature rank-candidates /path/to/project
ea literature prepare-source-candidates /path/to/project
ea literature preflight-source-candidates /path/to/project
ea literature zotero-readiness /path/to/project
ea literature acceptance-checklist /path/to/project
```

The literature-library decision record, `public_search_state.yml`, `institution-access-guide`, and `zotero-bridge` describe local and companion boundaries. `import-zotero-status`, `reconcile-acquisition`, and `render-reconciliation` normalize current acquisition evidence and expose actionable `repair_actions`.

Confirmed source-candidate manifests such as `confirmed_ftir_source_candidates.yml`, `confirmed_uv_vis_source_candidates.yml`, and `confirmed_xps_source_candidates.yml` can feed method-specific packet builders after review.

### Evidence Dataset Beta

The v0.9.7 beta can extract narrowly defined values from lawfully available full text, keep reported and normalized values separate, review each candidate, validate the reviewed dataset, make a source-data-backed plot, and export a privacy-scoped bundle.

```bash
ea literature data-plan /path/to/project --help
ea literature data-extract /path/to/project --help
ea literature data-review /path/to/project --help
ea literature data-validate /path/to/project --help
ea literature data-plot /path/to/project --help
ea literature data-export /path/to/project --help
```

Conductivity, resistivity, sheet resistance, sheet conductance, contact resistance, and mobility remain distinct quantity types. Only accepted/edited review records can enter plots or exports. See [docs/CAPABILITY_MATRIX.md](docs/CAPABILITY_MATRIX.md) and `skills/ea/references/literature-data-extraction.md` for maturity and scope.

## Trace And Export

```bash
ea trace index /path/to/project
ea trace focus /path/to/project REPORT_OR_RECORD_ID
ea trace view /path/to/project --focus REPORT_OR_RECORD_REF
ea trace lookup /path/to/project RECORD_ID
ea trace export /path/to/project --full
ea export report-html /path/to/project --report-id REPORT_ID
ea export report-bundle /path/to/project --report-id REPORT_ID --include-trace --zip
ea export verify-archive /path/to/report-bundle.zip
```

Compact metadata is stored in `traceability/index.yml`; explicit full export writes `traceability/full_trace.yml`. The graph links reports to registered references, reference seeds, built-in/source-library refs, review records, provenance, and memory. Project-bundle verification is documented in [docs/PROJECT_BUNDLE_VERIFICATION.md](docs/PROJECT_BUNDLE_VERIFICATION.md).

## Capability Maturity

- Stable: project lifecycle, protected import, review/provenance, implemented characterization workflows, health/evaluation, trace, report and bundle export.
- Beta: Raman reproducibility benchmark surface and literature evidence datasets.
- Experimental/companion: browser-assisted lawful acquisition and external Zotero coordination.

Machine tests do not replace scientific review. Raman remains beta until independent scientific sign-off is recorded. External novice and expert trial evidence is also required before promotion to v1.0.

## Compatibility And Updates

Existing `$ea-v0-2` installs continue to route to `$ea` during v1.0.x. Historical project records are not rewritten merely to change the product name.

```bash
ea migrate status /path/to/project
ea migrate plan /path/to/project
ea update
ea rollback --release-ref v0.9.6
ea uninstall
```

All lifecycle commands preview by default and require `--yes` for replacement or removal.

## Developers

```bash
python3 -m pip install -e ".[dev,release]"
python3 -m pytest -q
python3 scripts/validate_skill_packages.py
python3 scripts/check_version_identity.py
python3 scripts/check_downloaded_skill_instructions.py
python3 scripts/public_release_smoke.py
ea-release-supply-chain
ea-release-manifest
ea-release-package
ea-verify-release-package dist/experimental-assistant-0.9.7-COMMIT-release.zip
ea-release-checklist
```

Release policy, SBOM/vulnerability requirements, checksums, signature trust limits, and clean-build verification are in [docs/RELEASE_SECURITY_POLICY.md](docs/RELEASE_SECURITY_POLICY.md) and [docs/RELEASE_VERIFICATION.md](docs/RELEASE_VERIFICATION.md).

Apache-2.0 license. See [LICENSE](LICENSE), [NOTICE](NOTICE), [SECURITY.md](SECURITY.md), [CONTRIBUTING.md](CONTRIBUTING.md), [GOVERNANCE.md](GOVERNANCE.md), and [docs/SUPPORT_POLICY.md](docs/SUPPORT_POLICY.md).
