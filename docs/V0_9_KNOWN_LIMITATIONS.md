# Experimental Assistant v0.9.8 Known Limitations

## Scientific Boundaries

- EA does not automatically prove material or phase identity, layer count, crystallinity, composition, chemical state, optical band gap, electrochemical performance, thermal stability, mechanism, or sample ranking.
- Source-backed candidates and screening calculations require applicable references, explicit review, and traceable report integration.
- Built-in libraries and public-search results are starter coverage, not exhaustive literature or database coverage.
- Raman has a deterministic machine benchmark but remains beta until independent scientific sign-off is recorded.

## Literature Evidence Dataset Beta

- Extraction quality depends on searchable full text, table/caption structure, and a sufficiently narrow user-defined schema.
- Scanned PDFs are marked OCR-required. v0.9.8 does not silently perform or validate OCR inside the core workflow.
- Plot digitization and complex supplementary-file parsing are not general automatic capabilities.
- Conductivity, resistivity, sheet resistance/conductance, contact resistance, and mobility are never treated as interchangeable. Missing geometry or conditions can make records not comparable.
- Only accepted or edited records enter datasets and plots; this improves reviewability but does not prove that a paper's reported value is scientifically valid.
- Default discovery covers Crossref, OpenAlex, and arXiv metadata. Unpaywall is the default OA resolver; CORE, Semantic Scholar, Scopus, Web of Science, CNKI, Wanfang, and publisher/institution-specific adapters are not general built-in coverage.
- FTS retrieval widens when evidence is weak or conflicting, but poor extraction quality, missing page anchors, multi-column layout, formulas, tables, and scanned pages can still require manual original-PDF review.

## Integration Boundaries

- EA stores no credentials, cookies, browser profiles, or private account state and does not bypass publisher, SSO, MFA, paywall, or institution controls.
- Zotero/browser acquisition is an optional companion workflow. Core EA can continue in degraded local mode.
- Acquisition protocol v2 records Zotero parent/attachment transaction identities, but a real independent five-target Zotero parent-plus-PDF-child transaction remains external companion evidence rather than a stable-core claim.
- Diagnostics are local-only and do not submit reports automatically.

## Release Evidence

- Automated local tests are not native Windows/Linux/macOS evidence; the repository CI matrix provides that evidence only after it runs successfully on the public commit.
- Independent novice and expert trials are pending until real testers complete and record them. v1.0 promotion is blocked while they remain pending.
- Checksums verify integrity, not publisher identity or scientific correctness. Detached signatures require an independently trusted key fingerprint.

## Compatibility

- `$ea-v0-2` remains a thin compatibility entry through v1.0.x. Removal requires a later announced deprecation window.
- Historical project schema/version strings are preserved where rewriting would damage provenance; use the migration commands rather than manual edits.
