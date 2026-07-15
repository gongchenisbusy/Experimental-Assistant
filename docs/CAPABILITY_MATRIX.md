# Experimental Assistant Capability Matrix

This is a maintainer-facing release-governance contract for v0.9.9. Ordinary user responses and normal command results describe concrete limits and next actions instead of exposing maturity labels.

Run `ea capabilities` for the installed machine-readable contract.

## Stable Core

| Capability | Supported result | Required evidence |
|---|---|---|
| Installation lifecycle | setup, doctor, update, rollback, uninstall | clean package and failure-injection tests on supported platforms |
| Project lifecycle | create, inspect, migrate, recover | backward compatibility, atomic-write, interruption, and rollback tests |
| Protected raw import | validated controlled copy and duplicate detection | encoding, path, permission, hash, and source-protection tests |
| Review and provenance | explicit review records and linked evidence | schema, idempotency, and traceability tests |
| Health, evaluation, brief, trace | compact status with full local audit records | read-only and output-budget tests |
| Reports and exports | HTML reports and checksum-verified bundles | public examples and package verification |

Raman enters this table only after its public golden benchmark, numeric tolerances, walkthrough, regression tests, and a recorded simulated scientific review all pass with no unresolved blocking finding. The simulated review tests the release contract; it is not represented as independent expert validation.

## Beta

- Raman until its public benchmark, simulated scientific review, and artifact inspection are recorded for the release candidate.
- PL and XRD analysis.
- FTIR source-backed assignment support.
- UV-Vis screening and replicate comparison.
- XPS processing, fitting, and interpretation aids.
- Electrochemistry and thermal derived metrics.
- Batch workflows.
- Public literature metadata search and ranking.
- Literature evidence datasets and reviewed plotting.

Beta outputs remain review-gated and must state assumptions, units, limitations, and unsupported uses.

## Experimental Or Companion

- Zotero, browser, and institution-access acquisition orchestration.
- Broad full-text acquisition and reusable cache management.
- Advanced image interpretation beyond structured records.
- Automatically generated interpretation candidates without public benchmark evidence and explicit review boundaries.

These integrations may be disabled without breaking the stable core. They must not bypass access controls or expose credentials, browser state, private full text, or raw research data.

## Promotion Rule

A capability becomes stable only when it has:

1. declared supported inputs and invalid-use cases;
2. a public or redistributable benchmark dataset and expected outputs;
3. numeric tolerances where applicable;
4. an ordinary-user walkthrough;
5. a recorded release-candidate scientific review, which may be a clearly labeled simulated-agent review;
6. passing platform, privacy, and regression tests.
