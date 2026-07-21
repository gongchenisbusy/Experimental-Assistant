# Experimental Assistant v1.1.0 Issue Disposition

| Public issue | v1.1 disposition | Primary evidence |
|---|---|---|
| #23 Literature integrity and resumability | Resolved for v1.1 | fixed-scope request gates; canonical run/resume; per-target reconciliation; parent DOI checks; local PDF and postflight tests |
| #24 Characterization blocker and workflow friction | Resolved for v1.1 | protected-copy rollback; command-effect registry; method-aware preview; direct run/sample commands; stage-aware memory; EA-feedback companion update |
| #25 HTML delivery stops at Markdown | Resolved for v1.1 | composite report immediately exports HTML; explicit non-formal draft HTML preview; lifecycle regressions |
| #26 Review/export/PL/composite regressions | Resolved for v1.1, with optional PL fitting split to #27 | strong review binding; export-wide deduplication; dual-axis PL; reviewed composite report; read-only policy tests |

Optional reviewed PL peak fitting is not silently marked complete. It is separated into #27 with model-selection, uncertainty, low-SNR, overlap, poor-fit, provenance, and review acceptance criteria.

EA-feedback is released from its independent public repository and pinned by exact commit in `skill-registry/companion-compatibility.yml`. Its v1.1 compatibility tests cover active-install-only discovery, local collection without GitHub authentication, structured warning severity, duplicate finding merge, and multilingual submission intent.
