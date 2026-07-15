# Universal literature-data public benchmark

This deterministic synthetic fixture exercises all ten public field types in the
v0.9.9 schema contract. It is public benchmark evidence generated and reviewed by
simulated agents; it is not a real-user study or external expert validation.

- `schema.yml` declares ten complete, recursive field contracts.
- `source/chunks.jsonl` is searchable synthetic source text with page/chunk anchors.
- `source/metadata.json` supplies a stable public source identity.
- `expected.yml` records the acceptance expectations and fixture hashes.

The automated test creates a temporary EA project, runs plan and extraction, and
checks typed values, evidence anchors, and source-failure count. Separate RC1 tests
cover reviewed-only gating, custom conditions, normalized deduplication, conflict
policies, schema-change refusal, privacy-safe export, and unsupported plotting.

