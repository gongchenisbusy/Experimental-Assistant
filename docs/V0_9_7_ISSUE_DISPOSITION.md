# v0.9.7 Public Issue Disposition

Reviewed against the public issue list on 2026-07-10. An issue can remain open when it mixes completed work with external-trial or companion-software follow-up. “Implemented” means code/docs/tests exist in v0.9.7; it does not mean independent user evidence has been fabricated.

| Issue | Disposition for v0.9.7 | Evidence / residual work |
|---|---|---|
| [#1 EA practice UX](https://github.com/gongchenisbusy/Experimental-Assistant/issues/1) | Implemented; novice wording validation pending | `$ea` router, consult/record/execute/audit, guided start, literature prompt, review promotion, draft promotion, compact status, CLI-owned IDs/writes, numbered questions, and confirmed-only `ea-feedback` suggestion. External novice trial remains. |
| [#2 missing environments/companions](https://github.com/gongchenisbusy/Experimental-Assistant/issues/2) | Partially implemented; safe companion limits retained | `ea setup`, `ea doctor`, update/rollback and literature setup preflight diagnose exact blockers and preserve resumable state. EA intentionally does not accept licenses, install arbitrary GUI software, bypass OS controls, or sign into accounts; Zotero/Connector GUI automation remains companion/user-managed. |
| [#3 post-install onboarding](https://github.com/gongchenisbusy/Experimental-Assistant/issues/3) | Implemented | Version-bound setup/onboarding, exact identity doctor, first-project path, optional integration preflight, and tests. |
| [#4 short-test context pressure](https://github.com/gongchenisbusy/Experimental-Assistant/issues/4) | Implemented; native CI confirmation pending | 10 KB router budget, 2 KB wrapper budget, draft/status layer, explicit modes, compact output tests, UTF-8/Chinese import fixtures, and Windows CI. Public CI result is required before platform evidence is marked pass. |
| [#5 literature token/context pressure](https://github.com/gongchenisbusy/Experimental-Assistant/issues/5) | Implemented | Progressive disclosure, compact/full separation, project/literature summaries, optional Zotero states, context-cost proxies, and output/artifact budgets. |
| [#6 literature/Zotero correctness](https://github.com/gongchenisbusy/Experimental-Assistant/issues/6) | Implemented | Exact confirmed phrases, material/application relevance gate, sandbox-vs-connection taxonomy, DOI-idempotent targets, duplicate/missing attachment states, file-only cache validation, compact output, and regressions. |
| [#7 acquisition UX and reconciliation](https://github.com/gongchenisbusy/Experimental-Assistant/issues/7) | Implemented across EA and companion | v1 handoff schema, mixed status ledger, external-cache brief/eval, current/optional/stale diagnostics, redacted compact output, documented browser-download-event fallback, and read-only `ea-feedback` acquisition summary collector. Companion commit `c20752c` is public on `ea-feedback/main`. |

## Release Decision

No issue contains an unresolved EA-core P0 implementation blocker. #2 retains deliberate GUI/account permission boundaries, and #1/#4 require real novice/native evidence for v1.0 promotion. The #7 companion collector update is public and independently verified at `c20752c`.
