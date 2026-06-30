# EA v0.2 Build

EA v0.2 is the clean implementation workspace for the local-first Experimental Assistant.

Active design references are in `docs/`. The runnable Python core is in `src/ea/`. The agent skill package is in `skills/ea-v0-2/`.

## Public Setup

EA must initialize projects for unknown users without assuming developer-machine Zotero, browser, institution login, cache, or test paths. Use:

```bash
ea init-project /path/to/ea-project --name "Project name" --slug project-slug --direction "Research direction" --material "Material" --experiment-type "Experiment type"
ea config doctor /path/to/ea-project
ea healthcheck /path/to/ea-project
ea literature plan /path/to/ea-project --scope ordinary --access-mode open_access_only
ea add-skills dry-run /path/to/manifest.yml --workspace /path/to/ea-project --sample-output /path/to/sample-output.yml
```

Enable Zotero, browser assist, literature cache, or institution access only when the user supplies those settings.

## Developer Setup

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" skills/ea-v0-2
```

## Local Test Fixtures

Public workflow tests use `tests/fixtures/public/`. Local integration tests that touch real Zotero, browser profiles, institution login, or user caches must be marked `local-test-only` and kept out of product defaults.
