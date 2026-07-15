# Literature Acquisition Handoff

Experimental Assistant v0.9.8 uses a small, local sidecar to reconcile lawful full-text acquisition performed by a companion workflow. EA owns project targets, status summaries, downstream evidence extraction, review, and provenance. The `zotero-codex-literature` companion owns Zotero operations, user-managed authorization, attachment validation, and reusable full-text caches.

## Contract

The canonical JSON Schema is [`schemas/literature-acquisition-handoff.schema.json`](../schemas/literature-acquisition-handoff.schema.json). EA accepts the existing `zotero-codex-batch/v1` output and normalizes it to handoff schema `1.0`.

Each target has one status:

- `acquired`
- `cache_verified`
- `needs_login`
- `needs_subscription`
- `blocked`
- `manual_pdf_handoff_ready`
- `invalid_pdf`
- `retryable_error`
- `not_attempted`

Run:

```bash
ea literature import-zotero-status /path/to/ea-project \
  --batch-status literature/zotero_codex_batch_status.json
```

EA writes:

- `literature/external_acquisition_state.yml`: normalized per-target state.
- `literature/acquisition_status_compact.md`: title/DOI/status/reason/next-action table.
- `literature/zotero_codex_status_import.yml`: compatibility aggregate.
- `literature/acquisition_status_update.yml`: local deployment sync input when a local literature deployment exists.

The import works even when the EA local literature library is disabled. In that case `ea brief`, `ea eval`, and `ea literature zotero-readiness` report `external_cache_used` instead of `not_configured` when verified external cache results exist.

## Diagnostics

Status output is split into:

- `current_task_blockers`: only failures matching the current DOI or target set.
- `optional_capabilities`: inactive bridges or helpers that are not required by the completed task.
- `stale_global_state`: old sessions that do not match the current DOI or target set.

An inactive optional bridge or unrelated old session cannot turn a clean current task into a failure.

## Browser Download Event Fallback

EA does not implement browser automation. For publisher pages where a visible, user-authorized browser download is the lawful path, use the companion's bounded fallback:

```bash
python3 scripts/browser_download_handoff.py \
  --doi 10.xxxx/example \
  --url https://publisher.example/article \
  --after-start \
  --watch-seconds 120 \
  --stable-seconds 1 \
  --ingest \
  --json
```

For a ScienceDirect page where the browser PDF viewer holds the authorized PDF, the companion also provides:

```bash
python3 scripts/chrome_pdf_viewer_download.py \
  --doi 10.xxxx/example \
  --url https://www.sciencedirect.com/science/article/pii/... \
  --ingest \
  --compact-json
```

The companion uses a dedicated profile, waits for a new download event, rejects incomplete/non-PDF files, verifies file stability and the `%PDF-` signature, calls the existing ingest/cache path, and records the outcome. The user must complete login, SSO, MFA, CAPTCHA, institution selection, and publisher authorization. Neither EA nor the companion may bypass access controls.

## Privacy

Normal EA output removes signed URL queries, omits session IDs and DevTools payloads, redacts browser profile paths, and converts absolute cache paths to stable privacy-safe references. Full debug evidence remains local and must never include cookies, credentials, passwords, or raw private full text.
