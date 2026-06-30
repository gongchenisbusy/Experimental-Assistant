# Local Literature Library

Use this reference when initializing or updating project literature.

The literature library is recommended during project initialization but must be user-confirmed before bulk search or full-text acquisition. If `ea init-project` is run without `--enable-literature`, EA writes an `open-items/` record with `item_type: literature_library_decision`; read that open item and ask the user whether to deploy a local literature library. If `--enable-literature` is supplied, EA creates `literature/deployment_status.yml` and records `decision_status: enabled_at_initialization`, but scope, access mode, selected top N, and all Zotero/browser/cache/institution settings still require user confirmation.

Store project state under `literature/`:

```text
literature/
├── library_manifest.yml
├── deployment_status.yml
├── search_queries.yml
├── search_log.md
├── candidates.csv
├── ranking.csv
├── acquisition_handoff.yml
├── acquisition_handoff.md
├── acquisition_request.yml
├── zotero_codex_queries.jsonl
├── zotero_codex_targets.jsonl
├── zotero_codex_batch_status.json
├── acquisition_manifest.yml
├── acquisition_status_update.yml
├── origin_thread_sync.yml
├── selected_items.yml
├── references.bib
├── notes/
└── cache_index.yml
```

Ranking model:

```text
score = 0.45*project_relevance + 0.20*venue_authority + 0.15*recency + 0.10*citation_or_influence + 0.10*fulltext_availability_and_usefulness
```

Recommended top N: narrow project 30, ordinary project 50, review/broad direction 100-200 in batches.

Treat "full web search" as systematic multi-source coverage with a search log, not a guarantee of no omissions. Use journal impact factors only when the user provides a reliable source or a verified source is available.

Use the planning commands before any bulk search or full-text acquisition:

```bash
ea init-project /path/to/ea-project --name "Project name" --slug project-slug --direction "Research direction" --material "Material" --experiment-type "Experiment type" --enable-literature
ea literature plan /path/to/ea-project --scope ordinary --access-mode open_access_only --keyword strain
ea literature confirm /path/to/ea-project --selected-top-n 50 --user-response "User confirmed top 50."
ea literature handoff /path/to/ea-project --literature-thread-id thread-lit-001
ea literature acquisition-request /path/to/ea-project
ea literature import-acquisition /path/to/ea-project --manifest literature/acquisition_manifest.yml
ea literature sync-status /path/to/ea-project --update literature/acquisition_status_update.yml
ea references import-bibtex /path/to/ea-project /path/to/user-exported-references.bib
```

`plan` writes `search_queries.yml`, `search_log.md`, empty `candidates.csv`, empty `ranking.csv`, and `confirmation_request.yml`. It does not run web searches, open Zotero, use browser profiles, or download PDFs. `confirm` records the user's selected top N and moves the deployment state to `confirmed_awaiting_acquisition`.

`handoff` writes an acquisition packet for a dedicated literature workflow after confirmation. It records selected top N, access mode, input/output refs, forbidden actions, and the sync contract. It does not run search, browser automation, Zotero calls, institution login, or PDF downloads.

`acquisition-request` writes `acquisition_request.yml`, `zotero_codex_queries.jsonl`, and `zotero_codex_targets.jsonl` after confirmed top-N selection. If `selected_items.yml` or `ranking.csv` contains selected candidates, the target JSONL is suitable for a dedicated Zotero-Codex workflow to consume with `batch_acquire.py`. If no selected targets exist yet, EA writes only query requests and marks the request as `awaiting_search_results`. This command never runs Zotero, browser automation, live search, DOI resolution, or PDF download.

`import-acquisition` imports a dedicated literature workflow's `acquisition_manifest.yml` into EA. It updates `library_manifest.yml`, `cache_index.yml`, `deployment_status.yml`, and `origin_thread_sync.yml`, and registers reusable project references under `literature/references/` while de-duplicating by DOI, URL, title, or citation. The manifest can include `title`, `authors`, `year`, `venue`, `doi`, `url`, `local_path`, `cache_path`, `zotero_item_key`, and acquisition `status`.

`sync-status` reads `literature/acquisition_status_update.yml` (or `--update`) and merges acquisition progress into `deployment_status.yml` plus `origin_thread_sync.yml`. Use it so the origin project knows candidate counts, deduped counts, downloaded/cached full text, login needs, blockers, and a short status summary.

When the user or a dedicated literature workflow exports references as BibTeX, import them with `ea references import-bibtex`. This registers reusable references under `literature/references/` and de-duplicates by DOI, URL, normalized title, or normalized citation. It is not a Zotero database reader and must not infer local accounts or browser settings.
