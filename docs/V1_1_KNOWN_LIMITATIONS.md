# Experimental Assistant v1.1.0 Known Limitations

## Scientific boundaries

- EA organizes evidence and prepares reviewable candidates; it does not independently prove material identity, layer count, phase, mechanism, strain, doping, calibration validity, performance, or cross-paper comparability.
- PL visualization is corrected in v1.1, but built-in local peak fitting is intentionally deferred to issue #27 pending a reviewed model, uncertainty method, poor-fit policy, and benchmark fixtures.
- Composite reports combine reviewed method results; they do not create cross-method scientific conclusions without an explicitly bound confirmed review.
- PDF postflight verifies file structure, page count, declared title/DOI evidence, and hash. It does not prove publisher authenticity, scientific quality, or lawful access.

## Literature and integration boundaries

- A confirmed literature target count is fixed. Duplicate targets, missing selected items, or count drift stop acquisition preparation instead of silently expanding or shrinking scope.
- Supporting information must retain its parent DOI and cannot silently consume an independent top-N article slot.
- Browser/institution session files contain only privacy-safe workflow state. Cookies, credentials, SAML parameters, session tokens, and browsing history are never stored.
- Zotero is optional. EA does not install it, modify its database directly, bypass access controls, or claim exhaustive literature coverage.

## Delivery and compatibility boundaries

- Draft HTML preview is marked `DRAFT / NOT FORMAL`; only promoted reports enter formal report/export indexes.
- Existing v1.0 project format is supported, but old contradictory project records are not auto-repaired. Run health, evaluation, and literature reconciliation and review any proposed repair.
- Native Windows, Ubuntu, and macOS CI plus package/reproducibility checks are release evidence, not proof that every filesystem, ACL, locale, browser, institution, or scientific instrument behaves identically.
