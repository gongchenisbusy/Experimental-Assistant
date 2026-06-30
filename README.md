# EA v0.2 Build

EA v0.2 is the clean implementation workspace for the local-first Experimental Assistant.

Active design references are in `docs/`. The runnable Python core is in `src/ea/`. The agent skill package is in `skills/ea-v0-2/`.

## Public Setup

EA must initialize projects for unknown users without assuming developer-machine Zotero, browser, institution login, cache, or test paths. Use:

```bash
ea init-project /path/to/ea-project --name "Project name" --slug project-slug --direction "Research direction" --material "Material" --experiment-type "Experiment type"
ea config doctor /path/to/ea-project
ea healthcheck /path/to/ea-project
ea raw import /path/to/ea-project /path/to/raw-spectrum.txt --characterization-type raman --sample-ref sample-001 --experiment-ref exp-001
ea raman inspect /path/to/ea-project raw/raman/char-20260630-001/raw-spectrum.txt
ea review add /path/to/ea-project --target-type raman_columns --target-ref raw/raman/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "x=col_0, y=col_1, unit=cm^-1"
ea review add /path/to/ea-project --target-type raman_parameters --target-ref raw/raman/char-20260630-001/metadata.yml --user-response "可以，保存" --reviewed-content "default Raman parameters confirmed"
ea raman process /path/to/ea-project --metadata raw/raman/char-20260630-001/metadata.yml --x-column col_0 --y-column col_1 --x-unit cm^-1 --column-review-ref review-20260630-001 --parameter-review-ref review-20260630-002 --sample-ref sample-001
ea raman report /path/to/ea-project --metadata processed/sample-001/raman/res-project-raman-20260630-001/raman_metadata.yml --sample-ref sample-001 --experiment-ref exp-001
ea literature plan /path/to/ea-project --scope ordinary --access-mode open_access_only
ea literature handoff /path/to/ea-project --literature-thread-id thread-lit-001
ea literature sync-status /path/to/ea-project --update literature/acquisition_status_update.yml
ea add-skills dry-run /path/to/manifest.yml --workspace /path/to/ea-project --sample-output /path/to/sample-output.yml
ea image-data record /path/to/ea-project --metadata raw/sem/char-20260630-001/metadata.yml --method sem --description "User-confirmed image notes" --description-review-ref review-20260630-001 --confidence low
ea references add /path/to/ea-project --citation "Author A. Title. Journal volume, pages (year)." --doi 10.xxxx/example --url https://doi.org/10.xxxx/example
ea references import-bibtex /path/to/ea-project /path/to/user-exported-references.bib
ea references validate-report /path/to/ea-project reports/rpt-example.md
ea memory propose /path/to/ea-project --text "Candidate finding..." --source-ref reports/rpt-example.md --provenance-ref prov-20260630-001 --category interpretation --confidence medium
```

Enable Zotero, browser assist, literature cache, or institution access only when the user supplies those settings.
BibTeX import uses an explicit user-provided `.bib` export and de-duplicates references by DOI, URL, title, or citation before creating new project records.
Built-in child-skill manifests live in `skill-registry/builtins/` and are indexed by `skill-registry/index.yml`; contract placeholders define future module boundaries without claiming full algorithm support.

`ea healthcheck` audits project config, raw hashes, provenance links, figure/report backlinks, registered references, report citation numbering, and review-gated memory indices.

## Developer Setup

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" skills/ea-v0-2
```

## Local Test Fixtures

Public workflow tests use `tests/fixtures/public/`. Local integration tests that touch real Zotero, browser profiles, institution login, or user caches must be marked `local-test-only` and kept out of product defaults.
