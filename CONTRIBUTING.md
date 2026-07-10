# Contributing

Thank you for helping improve Experimental Assistant.

## Before Opening A Change

1. Search existing issues and explain the user or scientific workflow being improved.
2. Keep raw research data, credentials, browser state, private PDFs, and developer-machine paths out of commits and issues.
3. Preserve raw-data protection, review gates, provenance, local-first operation, and lawful literature access.
4. Add focused tests for behavior changes and broader tests when shared contracts are affected.

## Development Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest -q
.venv/bin/python /path/to/quick_validate.py skills/ea
```

Use the platform's equivalent activation and executable paths on Windows.

## Pull Requests

- Keep changes scoped and describe user-visible behavior, compatibility, tests, and known limits.
- Add migration and rollback notes for project-format, package, CLI, or skill changes.
- Label scientific outputs as stable, beta, or experimental according to `docs/CAPABILITY_MATRIX.md`.
- Do not promote a scientific method to stable without an independent benchmark, tolerance, walkthrough, and reviewer record.
- Do not weaken checks merely to make CI pass.

See `SECURITY.md` for private vulnerability reporting and `CODE_OF_CONDUCT.md` for community expectations.
