# Experimental Assistant v0.9.5 Known Limitations

These Experimental Assistant v0.9.5 limitations are expected and must be explained during public testing.

## Scientific Boundaries

- EA does not automatically prove material identity, phase identity, layer count, crystallinity, composition, chemical state, optical band gap, electrochemical performance, thermal stability, mechanism, or sample ranking.
- Source-backed candidates are evidence layers. They require registered references, user review, and explicit report or memory integration before they can support a claim.
- Screening calculations are useful for inspection and discussion, not final conclusions without reviewed method assumptions and references.
- Built-in source libraries are starter coverage, not exhaustive literature or database coverage.

## Workflow Boundaries

- Raw data remain protected; EA writes controlled copies and generated artifacts but does not mutate source raw files.
- Review records are required before processing choices, interpretation reuse, and durable memory commitment.
- `ea brief project` is a user-facing summary, not a substitute for traceability, provenance, or healthcheck/eval.
- HTML reports are readable exports of canonical Markdown reports. The Markdown/YAML records remain the authoritative project records.
- Checksums verify local file integrity; they are not authorship proof or scientific validation.

## Literature And Zotero-Codex Boundaries

- EA does not store credentials, cookies, session data, or private account state.
- EA does not bypass publisher, SSO, MFA, paywall, or institution access controls.
- `ea literature zotero-readiness` does not operate Zotero, open browsers, download PDFs, parse full text, or repair records.
- No-Zotero degraded mode can continue from user-supplied metadata and local references, but it is not exhaustive literature coverage.

## Release Follow-Up Gaps To Watch

- Real public users may need clearer onboarding around which method workflow to start with.
- Public examples cover representative paths, not every method combination.
- Larger curated libraries for FTIR, XPS, electrochemistry, and thermal workflows remain future enrichment work.
- The repository package can be optionally signed, but project export bundles currently rely on checksums unless a separate user-managed signing process is used.
