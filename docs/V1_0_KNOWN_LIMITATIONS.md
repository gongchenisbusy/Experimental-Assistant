# Experimental Assistant v1.0.0 Known Limitations

## Scientific boundaries

- Stable Raman support is bounded by the public golden benchmark, declared numeric tolerances, explicit review gates, and traceable report artifacts. It does not prove material identity, phase, layer count, mechanism, calibration, strain/doping, or unbenchmarked advanced interpretations.
- PL, XRD, FTIR, UV-Vis, XPS, electrochemistry, thermal, batch, image-data, public metadata search, and literature evidence datasets remain review-gated within their documented inputs and unsupported-use boundaries.
- EA does not provide autonomous scientific proof, exhaustive literature coverage, or automatic cross-paper comparability.
- Scanned PDFs and complex table/figure digitization may require user-authorized OCR or external tools; EA does not silently validate those transformations.

## Integration boundaries

- Zotero, browser, publisher, institution, SSO, MFA, CAPTCHA, license, and GUI operations are optional and user-authorized. Mock coverage does not establish live-service compatibility.
- EA never bypasses access controls or stores credentials, cookies, browser profiles, authorization headers, signed session URLs, or restricted full text in public release artifacts.
- Python 3.14 is observation-only. The supported matrix is Python 3.11–3.13 on Windows, Ubuntu, and macOS.

## Evidence boundaries

- Simulated personas and scientific reviews are not real users or independent experts.
- Deterministic Mock acquisition tests are not live Zotero/publisher/institution transactions.
- Historical v0.9.x identifiers remain visible where changing them would damage provenance. Use migration/lifecycle commands instead of editing records by hand.
- Detached Ed25519 signing is optional and requires an explicitly supplied user-managed key; checksums and manifests are not signatures.

