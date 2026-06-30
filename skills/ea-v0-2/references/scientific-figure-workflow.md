# Scientific Figure Workflow

Use this reference when creating or auditing EA report figures.

Current v0.2 support:

- Backend is Python/matplotlib for all built-in EA figure generation.
- Shared helpers live in `ea.figures`:
  - `styled_subplots` applies publication-oriented rcParams before creating axes.
  - `style_axis` applies title, labels, legend, light grid, and hidden top/right spines.
  - `save_styled_figure` places the lower-right canvas footer, saves PNG output, and closes the figure.
- The default style profile is `nature_like_clean`.
- Raman, PL, and XRD workflows register generated figures with `style_profile` and `source_data_refs`.
- Figure records remain traceable through `figures/index.yml`, report backlinks, result IDs, raw data IDs, sample IDs, and provenance records.

Required gates:

1. Confirm plot content when the figure changes scientific interpretation.
2. Confirm style profile when using anything other than `nature_like_clean`.
3. Keep raw data untouched and write generated figures outside `raw/`.
4. Include a stable figure ID and report link in the lower-right canvas footer.
5. Keep source data references in the figure record.
6. Use confidence labels in report text rather than embedding unsupported claims in plot annotations.

Current limitations:

- The helper layer is not yet a full multi-panel manuscript figure composer.
- It does not export SVG/PDF/TIFF bundles by default.
- It does not handle journal-specific figure-size submission packages.
- It does not replace manual review for microscopy integrity, statistical annotation, or panel legends.

Future work should add report-to-figure export bundles, multi-panel templates, SVG/PDF/TIFF export helpers, panel-letter helpers, Source Data package generation, and visual QA checks.
