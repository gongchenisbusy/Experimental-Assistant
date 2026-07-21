# Local Literature Library Router

Use this router when a task concerns literature planning, metadata discovery, acquisition, Zotero, reconciliation, cache use, or evidence datasets. Load only the reference for the current stage.

## Non-negotiable boundaries

- Planning, metadata search, acquisition, and scientific interpretation are separate stages.
- Bulk search or full-text acquisition requires a user-confirmed scope. Use `ea estimate workflow` for large work.
- Keep the confirmed count fixed across `selected_items.yml`, `acquisition_request.yml`, `run.yml`, and `zotero_codex_targets.jsonl`. Stop on empty, duplicate, or mismatched scope instead of silently changing target count.
- Treat public metadata coverage as source- and query-limited; never claim exhaustive search.
- Use source-verified venue metrics when available; never present an inferred or stale metric as verified.
- For impact-factor filtering, do not invent IF values; record the source and retrieval date or leave the metric unknown.
- A metadata-only step must not look up or invent journal impact factors without a verified, dated source.
- Do not infer accounts, credentials, browser profiles, institution access, Zotero libraries, or private cache locations.
- Do not bypass paywalls, CAPTCHA, SSO, MFA, license terms, robots controls, or publisher access controls.
- Keep private full text and caches local. Reports and exports contain citations, hashes, evidence anchors, and permitted source-data—not restricted PDFs.
- Scientific conclusions, plots, and durable memory remain review-gated.

## Route by stage

| Current task | Load next |
|---|---|
| Plan a library, confirm scope, query Crossref/OpenAlex/arXiv, rank metadata | `references/literature-metadata-discovery.md` |
| Resolve lawful OA copies, validate PDFs, or run a resumable acquisition | `references/literature-oa-acquisition.md` |
| Prepare or inspect Zotero/browser/institution companion handoff | `references/literature-zotero-handoff.md` |
| Import status/manifests, reconcile partial work, or render acceptance state | `references/literature-reconciliation.md` |
| Inspect local cached full text, targeted chunks, quality, or evidence anchors | `references/literature-cache-reading.md` |
| Extract/review/plot cross-paper property data | `references/literature-data-extraction.md` plus `references/literature-cache-reading.md` |

Do not preload all stage references. Return here only when the state moves to a different stage.

## Stable compatibility anchors

- Initialization records `decision_status: enabled_at_initialization` or creates a scoped item under `open-items/`.
- Metadata commands remain `search-public`, `rank-candidates`, `prepare-source-candidates`, and `preflight-source-candidates`.
- Method handoff remains available through `ea uv-vis build-source-packet`; `optical_gap_candidate` stays advisory and review-gated.
- Audit artifacts retain `source_candidates_preflight.yml`, `institution_access_guidance.yml`, `zotero_codex_bridge.yml`, `zotero_codex_status_import.yml`, `acquisition_reconciliation.yml`, `acquisition_reconciliation.md`, and `acceptance_checklist.yml`.
- A rejected candidate remains explicit as `include_in_source_packet: false`; unresolved setup is reported under `questions_for_user`.

## Compact continuation

Start from these small state surfaces before opening broad artifacts:

```bash
ea literature status /path/to/project
ea literature acquisition-status /path/to/project
ea literature search-public /path/to/project --resume
ea literature zotero-choice /path/to/project --choice existing
ea literature ingest-local-pdf /path/to/project --pdf /path/to/paper.pdf --doi 10.xxxx/example
ea literature zotero-readiness /path/to/project
ea literature reconcile-acquisition /path/to/project
ea brief project /path/to/project --no-write
```

Default CLI output is compact. Use `--json-full` or the artifact refs only when audit detail is needed. Never paste complete metadata, full-text chunks, or nested state into the conversation by default.

## Project state

EA owns the project-side records under `literature/`: query plan, candidates, ranking, selected items, canonical `run.yml`, acquisition request/handoff, imported companion status, reconciliation, local reference records, cache index, evidence datasets, and origin-thread summary. A literature companion may own browser/Zotero/OA execution, but must return a versioned, redacted, resumable status artifact that EA can import.

Zotero is a one-time explicit `existing`, `skip`, or `later` choice. Local PDF ingest does not require Zotero and accepts only verified PDFs with page count, title/DOI match, and SHA-256. Institution session state stores no credentials, cookies, SAML parameters, session tokens, URL queries, fragments, or browser history.

Prefer DOI, then canonical URL, then normalized title for identity. Preserve versions and supplementary relationships instead of silently deleting them.
