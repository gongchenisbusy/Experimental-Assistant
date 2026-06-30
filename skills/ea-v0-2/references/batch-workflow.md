# Batch Characterization Workflow

Use this reference when running multiple already-reviewed Raman, PL, XRD, FTIR, UV-Vis, or XPS analyses from one manifest.

Scope:

- Batch workflows coordinate existing method services; they do not guess columns, parameters, units, or scientific interpretation.
- Every item must carry user-confirmed `column_review_ref` and `parameter_review_ref`.
- Raw files must already be imported as controlled project copies.
- Batch outputs are written under `processed/batches/{batch_id}/` with `batch_run.yml`, `batch_summary.md`, and `processed/batches/index.yml`.
- Healthcheck audits the batch index, run record, summary, item `metadata_ref`, successful item `result_metadata_ref`, optional `report_ref`, item review refs, and batch `provenance_refs`.

CLI:

```bash
ea batch validate /path/to/ea-project batch_manifest.yml
ea batch run /path/to/ea-project batch_manifest.yml
```

Generate an editable skeleton:

```bash
ea templates batch-manifest /path/to/ea-project --method raman --method pl --method xrd --method ftir --method uv_vis --method xps --output batch_manifest.yml
```

The generated skeleton uses placeholders for raw metadata and review refs. Fill those with real project values before running `ea batch validate`.

Minimal manifest:

```yaml
batch:
  project_id: prj-example
  create_reports: true
  continue_on_error: true
  items:
    - item_id: raman-001
      method: raman
      metadata: raw/raman/char-20260630-001/metadata.yml
      sample_refs: [sample-001]
      experiment_refs: [exp-001]
      x_column: col_0
      y_column: col_1
      x_unit: cm^-1
      column_review_ref: review-20260630-001
      parameter_review_ref: review-20260630-002
      processing_parameters: {}
    - item_id: pl-001
      method: pl
      metadata: raw/pl/char-20260630-002/metadata.yml
      sample_refs: [sample-001]
      experiment_refs: [exp-001]
      x_column: col_0
      y_column: col_1
      x_unit: eV
      column_review_ref: review-20260630-003
      parameter_review_ref: review-20260630-004
    - item_id: ftir-001
      method: ftir
      metadata: raw/ftir/char-20260630-003/metadata.yml
      sample_refs: [sample-001]
      experiment_refs: [exp-001]
      x_column: wavenumber
      y_column: absorbance
      x_unit: cm^-1
      signal_mode: absorbance
      column_review_ref: review-20260630-005
      parameter_review_ref: review-20260630-006
      processing_parameters: {}
    - item_id: uv-vis-001
      method: uv_vis
      metadata: raw/uv_vis/char-20260630-004/metadata.yml
      sample_refs: [sample-001]
      experiment_refs: [exp-001]
      x_column: wavelength_nm
      y_column: absorbance
      x_unit: nm
      signal_mode: absorbance
      column_review_ref: review-20260630-007
      parameter_review_ref: review-20260630-008
      processing_parameters: {}
    - item_id: xps-001
      method: xps
      metadata: raw/xps/char-20260630-005/metadata.yml
      sample_refs: [sample-001]
      experiment_refs: [exp-001]
      x_column: binding_energy_eV
      y_column: intensity
      x_unit: eV
      energy_shift_eV: 0.0
      calibration_reference: C 1s 284.8 eV user-confirmed reference
      column_review_ref: review-20260630-009
      calibration_review_ref: review-20260630-010
      parameter_review_ref: review-20260630-011
      processing_parameters: {}
```

Notes:

- `method` must be `raman`, `pl`, `xrd`, `ftir`, `uv_vis`, or `xps`; `uv-vis` is accepted and normalized by the CLI/batch runner where relevant.
- `x_unit` must match the method's allowed units.
- FTIR items also require `signal_mode` as `absorbance` or `transmittance`.
- UV-Vis items require `signal_mode` as `absorbance`, `transmittance`, or `reflectance`.
- XPS items require `calibration_review_ref`; use `energy_shift_eV` and `calibration_reference` to record reviewed binding-energy calibration metadata.
- `processing_parameters` are merged over each method's default parameters.
- `parameters_file` or `processing_parameters_file` may point to a project-local YAML parameter override.
- Set `create_reports: false` for processing-only batches.
- Set item-level `create_report: false` to skip only one report.
- Failed items are recorded in `batch_run.yml`; with `continue_on_error: true`, later items still run.

After running a batch, run:

```bash
ea healthcheck /path/to/ea-project
ea eval project /path/to/ea-project
```

Evaluation notes:

- A fully traceable batch with no failed items should keep `ea eval project` at `pass` if the rest of the project is clean.
- A batch with failed items is not a broken audit trail, but evaluator reports it as a readiness `warning` so the next agent can decide whether to rerun, exclude, or document the failed items.
