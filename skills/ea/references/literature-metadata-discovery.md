# Literature Metadata Discovery

Use this reference for planning, public metadata search, de-duplication, ranking, and selection. It does not authorize PDF acquisition.

## Flow

```bash
ea literature plan /path/to/project --scope ordinary --access-mode open_access_only --keyword strain
ea literature confirm /path/to/project --selected-top-n 50 --user-response "User confirmed top 50."
ea literature search-public /path/to/project --source crossref --source openalex --source arxiv --max-results 20 --page-limit 1
ea literature search-public /path/to/project --resume
ea literature rank-candidates /path/to/project --candidates literature/candidate_results.yml
```

`plan` writes a query/search-log/confirmation package only. `search-public` queries Crossref, OpenAlex, and arXiv public metadata, writes full state under `literature/`, and prints a compact summary by default. Use `--json-full` only for audit detail.

Keep confirmed phrases intact. Apply the required material/application relevance gate before weighted ranking. De-duplicate by DOI, canonical URL, normalized title, and recorded version relationships. Supplements are down-ranked but preserved. Venue/citation metrics must be supplied or source-recorded; never invent journal impact factors.

The selected top N is a user decision. Search/ranking may recommend candidates but does not download PDFs, operate Zotero, open a browser, log into an institution, register final scientific evidence, or prove coverage completeness.
