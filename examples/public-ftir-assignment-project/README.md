# EA v0.2 Public FTIR Assignment Example

This folder is a packaged, public-safe EA project example for the FTIR source-backed assignment workflow. It is meant for inspection, smoke testing, and agent orientation after installing or unpacking an EA v0.9 release-candidate package.

The example contains a minimal review-gated FTIR workflow:

- project, rule-card, experiment, and sample records;
- one project-local synthetic FTIR source input and a controlled raw copy;
- column and parameter review records;
- processed FTIR metadata, CSV, band table, and figure;
- a built-in `generic_materials` assignment source packet with selected public-safe candidates;
- registered source seeds, an FTIR assignment suggestion record, and a grouped review package;
- one FTIR report displaying advisory source-backed assignment candidates with registered references;
- draft interpretation memory candidates generated only after a confirmed suggestion review.

Run local checks from the repository root:

```bash
ea healthcheck examples/public-ftir-assignment-project
ea eval project examples/public-ftir-assignment-project --no-write
```

Copy this folder before experimenting with edits. The packaged example is not a product default, does not configure Zotero, browser profiles, institution access, private caches, or signing keys, and should not be treated as a user's real project memory.

Maintainers can regenerate it with:

```bash
python3 scripts/build_public_ftir_assignment_example_project.py --force
```
