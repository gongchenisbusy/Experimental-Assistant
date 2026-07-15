# Experimental Assistant v0.9.8 Trial Report

## Candidate

- Product/distribution: `Experimental Assistant` / `experimental-assistant`
- Version: `0.9.8`
- Baseline: public `v0.9.7` commit `99741d8`, 360 passing tests
- Primary/compatibility skills: `$ea` / `$ea-v0-2`
- Companion contract: `skill-registry/companion-compatibility.yml`; accepted `ea-feedback` commit `9bb8ca5916fc307eb322fc7f45cb629b3eadf5b8`
- Local development validation: macOS arm64, Python 3.12; native platform claims require the public CI record for the release commit
- Public candidate CI: pass at `825f535` ([PR run 29430136013](https://github.com/gongchenisbusy/Experimental-Assistant/actions/runs/29430136013)); the duplicate push run also passed

## Implemented Regression Evidence

| Area | Evidence |
|---|---|
| Local release smoke | pass on Python 3.12 with 395 tests, both skill validators, identity/instruction checks, four public examples, portability scan, and sensitive-value scan |
| Native public CI | pass on Windows, Ubuntu, and macOS with Python 3.11–3.13; Python 3.14 observation, minimum dependencies, clean wheel/sdist setup, and release engineering also passed |
| Complete installation | wheel/sdist package both skills; setup source priority is explicit, bundled distribution, verified compact release asset, then developer checkout |
| Update recovery | CLI and two-skill before/after identities, failure stage, and restored state are written to transaction journals |
| Windows portability | deep-path project lifecycle fixture and GBK validator-output decoding fixture; native confirmation is delegated to Windows CI |
| Literature output | stage router below the frozen byte budget; compact search/resume output with explicit full-state access |
| Acquisition compatibility | protocol v2 writer plus v1 reader normalized in memory without source mutation; partial/recovery/no-Zotero fixtures |
| Literature quality | versioned discovery/resolution/cache/FTS benchmark covering recall, precision, duplicates, supplements, warm-cache reuse, and page anchors |
| Brief/report/figure | shared project state, decision gate summary, eight-method zh/en semantic parity, structured source data, one immutable final footer |
| Feedback companion | UTF-8 I/O, execution-event reconciliation, project `.venv` discovery, and prepared-versus-verified fallback states at the pinned commit |

## Public OA End-to-End Trial

The release implementation was exercised against the openly available DOI `10.1371/journal.pone.0000308` without Zotero or private credentials.

- Discovery/access: resolved through Unpaywall to the public PLOS PDF route.
- Retrieval checks: HTTP/MIME and `%PDF-` signature passed; the PDF parsed as 5 pages and 91,408 bytes.
- Content identity: SHA-256 `b52ca44dfd09d240543b80315f0cd43fe9ba7946f2b5650d5580213ed5d9186c`.
- Cache behavior: a second run reused the same content-addressed object rather than creating a duplicate.
- Privacy: the disposable cache lived outside the repository and is not included in release artifacts.

This single OA trial verifies one public route and cache-reuse behavior. It does not prove coverage for all publishers, institutions, Zotero configurations, or paper layouts.

## Release Gates

The candidate source records its exact full-test count and native CI URL above. The tagged release must still add clean wheel/sdist evidence, reproducibility hashes, SBOM/vulnerability result, release-asset download verification, and distribution-checklist result before issue closure. A failed or absent gate remains pending rather than inferred as passed.

## External Evidence Still Pending

- Independent novice trials on the supported OS families.
- Independent scientific review of beta evidence surfaces.
- A real independent five-target Zotero parent-plus-PDF-child transaction with partial-failure recovery.
- User-controlled publisher/institution login variants.

These items block v1.0 promotion or broader companion claims; they do not invalidate an honestly scoped v0.9.8 controlled release when all automated and downloadable-artifact gates pass.
