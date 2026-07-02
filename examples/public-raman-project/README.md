# EA v0.2 Public Raman Example Project

This folder is a packaged, public-safe EA project example. It is meant for inspection, smoke testing, and agent orientation after installing or unpacking an EA v0.9 release-candidate package.

The example contains a minimal review-gated Raman workflow:

- project and rule-card records;
- one confirmed experiment record;
- one sample record;
- one project-local source input and a controlled raw copy;
- column and parameter review records;
- processed Raman metadata, CSV, peak table, and figure;
- one Raman report;
- provenance records and an example manifest.

Run local checks from the repository root:

```bash
ea healthcheck examples/public-raman-project
ea eval project examples/public-raman-project --no-write
```

Copy this folder before experimenting with edits. The packaged example is not a product default, does not configure Zotero, browser profiles, institution access, private caches, or signing keys, and should not be treated as a user's real project memory.

Maintainers can regenerate it with:

```bash
python3 scripts/build_packaged_example_project.py --force
```
