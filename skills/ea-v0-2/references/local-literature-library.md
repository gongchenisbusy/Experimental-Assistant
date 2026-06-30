# Local Literature Library

Use this reference when initializing or updating project literature.

The literature library is recommended during project initialization but must be user-confirmed before bulk search or full-text acquisition. Store project state under `literature/`:

```text
literature/
├── library_manifest.yml
├── deployment_status.yml
├── search_queries.yml
├── search_log.md
├── candidates.csv
├── ranking.csv
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
