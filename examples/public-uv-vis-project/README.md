# Experimental Assistant v0.9.9 Public UV-Vis Example

This folder is a packaged, public-safe EA project example for the UV-Vis reviewed optical-screening workflow. It is meant for inspection, smoke testing, and agent orientation after installing or unpacking an EA v0.9 release-candidate package.

The example contains a minimal review-gated UV-Vis workflow:

- project, rule-card, experiment, and sample records;
- one project-local synthetic UV-Vis source input and a controlled raw copy;
- column and parameter review records;
- processed UV-Vis metadata, CSV, feature table, figure, Tauc table, derivative table, and correction-context record;
- one UV-Vis report displaying reviewed Tauc/Kubelka-Munk screening, derivative screening, and correction context;
- provenance records and an example manifest.

Run local checks from the repository root:

```bash
ea healthcheck examples/public-uv-vis-project
ea eval project examples/public-uv-vis-project --no-write
```

Copy this folder before experimenting with edits. The packaged example is not a product default, does not configure Zotero, browser profiles, institution access, private caches, or signing keys, and should not be treated as a user's real project memory.

Maintainers can regenerate it with:

```bash
python3 scripts/build_public_uv_vis_example_project.py --force
```
