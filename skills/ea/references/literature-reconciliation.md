# Literature Acquisition Reconciliation

Use this reference after an external acquisition run or when partial/stale status needs inspection.

```bash
ea literature import-zotero-status /path/to/project --batch-status literature/zotero_codex_batch_status.json
ea literature import-acquisition /path/to/project --manifest literature/acquisition_manifest.yml
ea literature reconcile-acquisition /path/to/project
ea literature render-reconciliation /path/to/project --reconciliation literature/acquisition_reconciliation.yml
ea literature acceptance-checklist /path/to/project
ea literature sync-status /path/to/project --update literature/acquisition_status_update.yml
ea references import-bibtex /path/to/project /user/exported/references.bib
```

Accept protocol v1 and v2 inputs; normalize v1 into an in-memory v2 view without rewriting the original. Separate current blockers, optional capability gaps, stale global state, resolved historical failures, and unknowns.

Reconciliation is an audit operation. It records finding codes, source refs, repair suggestions, questions, counts, hashes, and the next action. It does not auto-repair records, download PDFs, operate Zotero/browser, or upgrade uncertain evidence to success.
