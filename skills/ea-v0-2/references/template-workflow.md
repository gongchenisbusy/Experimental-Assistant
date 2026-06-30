# Template Workflow

Use this reference when a user needs editable YAML starting points for EA analysis parameters or batch manifests.

Commands:

```bash
ea templates parameters raman --output /path/to/ea-project/templates/raman_parameters.yml
ea templates parameters pl --output /path/to/ea-project/templates/pl_parameters.yml
ea templates parameters xrd --output /path/to/ea-project/templates/xrd_parameters.yml
ea templates parameters ftir --output /path/to/ea-project/templates/ftir_parameters.yml
ea templates batch-manifest /path/to/ea-project --method raman --method pl --method xrd --method ftir --output batch_manifest.yml
```

Processing-parameter templates:

- The written YAML file is the method's parameter dictionary directly.
- It can be passed to `ea raman process`, `ea pl process`, `ea xrd process`, or `ea ftir process` with `--parameters-file`.
- The user still needs a confirmed `{method}_parameters` review record before processing.
- Editing the YAML changes processing behavior only after the user confirms those edited parameters.

Batch manifest templates:

- Relative `--output` paths are written under the EA project root, so `--output batch_manifest.yml` pairs with `ea batch validate /path/to/ea-project batch_manifest.yml`.
- Generated items contain placeholders for `metadata`, `column_review_ref`, and `parameter_review_ref`.
- Replace placeholders with real project metadata and confirmed review refs before validation or execution.
- `processing_parameters: {}` means the batch runner will use each method's current defaults. Add item-level overrides only after user review.

Boundaries:

- Templates do not import raw data.
- Templates do not create reviews.
- Templates do not guess columns, units, or scientific interpretation.
- Templates do not assume developer-machine paths, test fixtures, Zotero/browser settings, or institution access.
