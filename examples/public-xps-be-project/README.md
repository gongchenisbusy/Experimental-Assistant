# Experimental Assistant v1.0.0 Public XPS Binding-Energy Candidate Example

This folder is a packaged, public-safe EA project example for the XPS source-backed binding-energy candidate workflow. It is meant for inspection, smoke testing, and agent orientation after installing or unpacking an EA v0.9 release-candidate package.

The example contains a minimal review-gated XPS workflow:

- project, rule-card, experiment, and sample records;
- one project-local synthetic XPS source input and a controlled raw copy;
- column, calibration, and parameter review records;
- processed XPS metadata, CSV, peak table, and figure;
- a built-in `binding_energy_candidate` source packet for C 1s and Si 2p starter discussion;
- an optional O 1s / oxide-surface source packet from `oxide_o1s_binding_energy`;
- registered source seeds, XPS parameter suggestion records, and grouped review packages;
- one XPS report displaying advisory source-backed BE candidates with registered references;
- draft interpretation memory candidates generated only after confirmed suggestion reviews.

Run local checks from the repository root:

```bash
ea healthcheck examples/public-xps-be-project
ea eval project examples/public-xps-be-project --no-write
```

Copy this folder before experimenting with edits. The packaged example is not a product default, does not configure Zotero, browser profiles, institution access, private caches, or signing keys, and should not be treated as a user's real project memory.

Maintainers can regenerate it with:

```bash
python3 scripts/build_public_xps_be_example_project.py --force
```
