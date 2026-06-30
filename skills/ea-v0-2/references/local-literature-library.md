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
ea literature search-public /path/to/ea-project --source crossref --source openalex --source arxiv --max-results 20 --page-limit 1
ea literature rank-candidates /path/to/ea-project --candidates literature/candidate_results.yml --reference-year 2026
ea literature handoff /path/to/ea-project --literature-thread-id thread-lit-001
ea literature acquisition-request /path/to/ea-project
ea literature institution-access-guide /path/to/ea-project --institution-name "Institution" --access-method library_proxy --access-url https://library.example.edu/login --browser-name Chrome --browser-profile browser-profiles/project
ea literature zotero-bridge /path/to/ea-project --zotero-config config/zotero-codex.json --project-collection "Project collection"
ea literature import-zotero-status /path/to/ea-project --batch-status literature/zotero_codex_batch_status.json --sidecar-verification literature/zotero_codex_sidecars_verify.json
ea literature import-acquisition /path/to/ea-project --manifest literature/acquisition_manifest.yml
ea literature reconcile-acquisition /path/to/ea-project
ea literature sync-status /path/to/ea-project --update literature/acquisition_status_update.yml
ea references import-bibtex /path/to/ea-project /path/to/user-exported-references.bib
```

`plan` writes `search_queries.yml`, `search_log.md`, empty `candidates.csv`, empty `ranking.csv`, and `confirmation_request.yml`. It does not run web searches, open Zotero, use browser profiles, or download PDFs. `confirm` records the user's selected top N and moves the deployment state to `confirmed_awaiting_acquisition`.

`search-public` explicitly queries public metadata APIs such as Crossref, OpenAlex, and arXiv, writes `public_search_candidates.yml`, `search_coverage.yml`, `public_search_state.yml`, appends `search_log.md`, and feeds the same ranking workflow. Use `--page-limit`, `--delay-seconds`, and `--resume` for longer resumable runs. It does not use Zotero, browser profiles, institution login, credentials, paywall access, DOI full-text resolution, or PDF download. Treat the result as source-limited metadata coverage, not exhaustive web coverage.

`rank-candidates` consumes a user- or dedicated-workflow-supplied CSV/YAML/JSON candidate file, de-duplicates by DOI/URL/title, scores project relevance, venue authority, recency, citation/influence, and full-text availability, writes `ranking.csv`, and refreshes `selected_items.yml`. It does not run live web search, look up journal impact factors, use Zotero/browser access, log into institutions, or download PDFs.

`handoff` writes an acquisition packet for a dedicated literature workflow after confirmation. It records selected top N, access mode, input/output refs, forbidden actions, and the sync contract. It does not run search, browser automation, Zotero calls, institution login, or PDF downloads.

`acquisition-request` writes `acquisition_request.yml`, `zotero_codex_queries.jsonl`, and `zotero_codex_targets.jsonl` after confirmed top-N selection. If `selected_items.yml` or `ranking.csv` contains selected candidates, the target JSONL is suitable for a dedicated Zotero-Codex workflow to consume with `batch_acquire.py`. If no selected targets exist yet, EA writes only query requests and marks the request as `awaiting_search_results`. This command never runs Zotero, browser automation, live search, DOI resolution, or PDF download.

`institution-access-guide` writes `institution_access_guidance.yml` and `institution_access_guidance.md` for user-managed authenticated acquisition. It records user-supplied institution name, access method, access URL or manual instructions, browser name/profile, Zotero-Codex config, cache root, authorization status, required inputs, safe manual steps, and next EA commands. It does not open browsers, operate Zotero, run Zotero-Codex scripts, store credentials, probe URLs, resolve DOI pages, download PDFs, parse full text, or assume developer-machine settings.

`zotero-bridge` reads `acquisition_request.yml` and writes `zotero_codex_bridge.yml`, `zotero_codex_bridge.md`, and `zotero_codex_settings_request.yml`. It records user-supplied or user-confirmed Zotero-Codex config, cache root, project collection, browser assist, browser profile, and institution access settings, then emits safe commands for `literature_doctor.py`, `batch_acquire.py`, status rendering, sidecar writing/verification, and EA sync/import. It does not run Zotero-Codex scripts, operate Zotero, open browsers, resolve DOI pages, download PDFs, store credentials, or assume developer-machine accounts.

`import-zotero-status` reads `zotero_codex_batch_status.json` plus optional sidecar verification and rendered status refs, writes `zotero_codex_status_import.yml` and `acquisition_status_update.yml`, then syncs `deployment_status.yml` and `origin_thread_sync.yml`. It normalizes cached/downloaded counts, login needs, and blocked items. It imports status artifacts only; it does not run Zotero-Codex scripts, operate Zotero, open browsers, resolve DOI pages, download PDFs, parse full text, or store credentials.

`reconcile-acquisition` writes `acquisition_reconciliation.yml` by comparing acquisition manifest, Zotero-Codex status import, library manifest, cache index, reference index, deployment status, and origin-thread sync records when present. It reports pass/warnings/fail with finding codes, source refs, per-finding `repair_suggestion`, top-level `repair_actions`, and `questions_for_user` for uncertainties that affect the next repair step. It reads local artifacts only; it does not auto-repair records, run Zotero-Codex scripts, operate Zotero, open browsers, resolve DOI pages, download PDFs, parse full text, or store credentials.

`import-acquisition` imports a dedicated literature workflow's `acquisition_manifest.yml` into EA. It updates `library_manifest.yml`, `cache_index.yml`, `deployment_status.yml`, and `origin_thread_sync.yml`, and registers reusable project references under `literature/references/` while de-duplicating by DOI, URL, title, or citation. The manifest can include `title`, `authors`, `year`, `venue`, `doi`, `url`, `local_path`, `cache_path`, `zotero_item_key`, and acquisition `status`.

`sync-status` reads `literature/acquisition_status_update.yml` (or `--update`) and merges acquisition progress into `deployment_status.yml` plus `origin_thread_sync.yml`. Use it so the origin project knows candidate counts, deduped counts, downloaded/cached full text, login needs, blockers, and a short status summary.

When the user or a dedicated literature workflow exports references as BibTeX, import them with `ea references import-bibtex`. This registers reusable references under `literature/references/` and de-duplicates by DOI, URL, normalized title, or normalized citation. It is not a Zotero database reader and must not infer local accounts or browser settings.
