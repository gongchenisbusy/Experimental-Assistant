# Experimental Assistant v1.0.0

Experimental Assistant (EA) is a local-first materials-research assistant. It helps organize projects, protect imported raw data, run review-gated characterization workflows, trace reports back to evidence, and coordinate literature work without assuming developer-machine accounts or paths.

Public identity: `Experimental Assistant`, CLI `ea`, the single Codex skill `$ea`, and Python distribution `experimental-assistant`.

Repository: <https://github.com/gongchenisbusy/Experimental-Assistant>

Release: <https://github.com/gongchenisbusy/Experimental-Assistant/releases/tag/v1.0.0>

中文用户可直接阅读 [docs/QUICKSTART_ZH.md](docs/QUICKSTART_ZH.md)。稳定错误码与处理建议见 [docs/ERROR_CATALOG.md](docs/ERROR_CATALOG.md)。

## Install

Python 3.11, 3.12, or 3.13 is supported. Python 3.12 is recommended.

```bash
uv tool install --python 3.12 git+https://github.com/gongchenisbusy/Experimental-Assistant.git@v1.0.0
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
ea journey /path/to/project
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

The literature-library decision record, `public_search_state.yml`, `institution-access-guide`, and `zotero-bridge` describe what EA runs locally and what remains an optional external integration. `import-zotero-status`, `reconcile-acquisition`, and `render-reconciliation` normalize current acquisition evidence and expose actionable `repair_actions`.

Confirmed source-candidate manifests such as `confirmed_ftir_source_candidates.yml`, `confirmed_uv_vis_source_candidates.yml`, and `confirmed_xps_source_candidates.yml` can feed method-specific packet builders after review.

### User-Defined Literature Data Collection

v1.0.0 can collect any user-requested literature data category described by a validated schema. The six earlier electrical-property templates remain available as conveniences, not as an allowlist. A schema can declare numeric values, ranges, values with uncertainty, text, enums, booleans, dates, lists, and nested fields, together with units, aliases, evidence requirements, comparison rules, and conflict policy. EA keeps reported and normalized values separate, requires item-level review, validates the accepted dataset, plots compatible fields where meaningful, and exports a privacy-scoped bundle.

```bash
ea literature data-template --help
ea literature data-schema validate /path/to/schema.yml
ea literature data-plan /path/to/project --schema /path/to/schema.yml
ea literature data-extract /path/to/project --help
ea literature data-review /path/to/project --help
ea literature data-validate /path/to/project --help
ea literature data-plot /path/to/project --help
ea literature data-export /path/to/project --help
```

Only accepted or edited review records can enter downstream statistics, plots, reports, or exports. Numeric values are never converted or compared unless their schema and unit rules permit it. See `skills/ea/references/literature-data-extraction.md` for schema examples and concrete limits.

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

## Scientific And Integration Boundaries

EA produces reviewable evidence and candidate interpretations; it does not independently prove material identity, mechanism, performance, or literature completeness. Browser, Zotero, and institution-login operations remain optional integrations and never bypass access controls. v1.0.0 release acceptance uses automated tests, public benchmarks, deterministic mock integrations, simulated-agent journeys/reviews, and manual artifact inspection. These records are labeled by evidence type and are not represented as real-user or independent-expert validation.

## Migration And Updates

The former `Experimental Assistant (Compatibility)` skill was retired after v0.9.8 and is not part of the pre-v1 or v1.0 public surface. `ea setup` removes a stale compatibility-skill directory if one is present. Historical project records remain readable and are not rewritten merely to change the product name.

```bash
ea migrate status /path/to/project
ea migrate plan /path/to/project
ea update
ea rollback --release-ref v0.9.7
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
ea-verify-release-package dist/experimental-assistant-1.0.0-COMMIT-release.zip
ea-release-checklist
```

Release policy, SBOM/vulnerability requirements, checksums, signature trust limits, and clean-build verification are in [docs/RELEASE_SECURITY_POLICY.md](docs/RELEASE_SECURITY_POLICY.md) and [docs/RELEASE_VERIFICATION.md](docs/RELEASE_VERIFICATION.md).

Apache-2.0 license. See [LICENSE](LICENSE), [NOTICE](NOTICE), [SECURITY.md](SECURITY.md), [CONTRIBUTING.md](CONTRIBUTING.md), [GOVERNANCE.md](GOVERNANCE.md), and [docs/SUPPORT_POLICY.md](docs/SUPPORT_POLICY.md).
