# Literature Evidence Dataset Workflow

Use this reference for cross-paper collection of a user-defined property and measurement context.

## Boundary

Accept user-provided PDFs or verified lawful caches. Do not bypass publisher or institution controls. Extracted values are candidates until reviewed. Do not send unreviewed records into plots, statistics, reports, or durable memory.

## Workflow

1. Define the property, required condition fields, accepted units, and comparability rules.
2. Select sources with DOI/reference and verified cache identity.
3. Search metadata and chunk/page/table indexes before reading text.
4. Extract reported values, units, conditions, and precise evidence anchors.
5. Preserve reported and normalized values separately; record every conversion.
6. Review each record as accept, reject, edit, defer, conflicting, or not comparable.
7. Validate duplicates, units, required context, evidence anchors, and plot eligibility.
8. Plot or export reviewed records only, with source-data and provenance references.

## Commands

```bash
ea literature data-plan /path/to/ea-project \
  --property "electrical conductivity" \
  --kind conductivity \
  --material "two-dimensional materials" \
  --required-condition temperature \
  --required-condition direction \
  --required-condition instrument_or_method \
  --source /path/to/verified-cache-or-searchable.pdf \
  --dataset-id conductivity-pilot \
  --yes

ea literature data-extract /path/to/ea-project --dataset conductivity-pilot --max-sources 10 --yes
ea literature data-review /path/to/ea-project --dataset conductivity-pilot --record rec-source-001-001 --decision accept --note "Verified against page and table." --yes
ea literature data-validate /path/to/ea-project --dataset conductivity-pilot
ea literature data-plot /path/to/ea-project --dataset conductivity-pilot --yes
ea literature data-export /path/to/ea-project --dataset conductivity-pilot --yes
```

Run `data-plan` without `--yes` for a zero-write preview. `data-extract`, `data-review`, `data-plot`, and `data-export` are mutating and confirmation-gated. `data-validate --no-write` is read-only.

## Artifacts

Each dataset lives under `literature/data-extractions/<dataset-id>/` and contains `extraction_spec.yml`, `source_manifest.yml`, compact checkpoint state, candidate YAML/CSV, per-source short evidence anchors, review YAML/Markdown, reviewed YAML/CSV, validation, plots/source data, and a report. Reviewed exports intentionally exclude raw PDFs, private full text, absolute source paths, credentials, and unreviewed candidates.

## Electrical Pilot

Keep conductivity, resistivity, sheet resistance, sheet conductance, contact resistance, and mobility distinct. Record probe geometry, direction, temperature, thickness, substrate, doping, and contact/device context when reported. Use `not_reported`; never infer a missing condition.

Direct searchable PDFs use `pypdf`; verified Zotero-Codex caches prefer `chunks.jsonl` and preserve page/table/figure/caption/chunk anchors. Empty scanned sources are checkpointed as `ocr_required`. OCR and complex figure digitization remain separate higher-cost workflows and are not silently attempted.

## Context Economy

Process about 10 to 20 papers per resumable batch. Checkpoint each paper, reuse verified caches, and keep normal output to counts, warnings, next actions, and artifact references. Full text and bulky evidence remain local.

Use `ea estimate workflow --workflow literature_data_extraction`, `literature_ocr`, or `literature_digitization` before unusually large work. These are planning proxies based on papers/items, not exact model-token measurements.
