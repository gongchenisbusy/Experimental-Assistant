---
schema_version: '0.2'
created_at: '2026-06-05T11:24:00'
updated_at: '2026-06-05T11:24:00'
status: draft
source_refs: []
provenance_refs:
- prov-20260605-005
review_refs: []
report_id: rpt-public-uv-vis-example-20260605-001
project_id: prj-public-uv-vis-example
report_type: uv_vis_analysis
language: zh
audience: self
related_experiments:
- exp-20260605-001
related_samples:
- sample-example-semiconductor-film-uv-vis-001
related_results:
- res-public-uv-vis-example-uv-vis-20260605-001
figure_ids:
- fig-public-uv-vis-example-uv-vis-20260605-001
include_next_step_suggestions: false
reference_ids: []
numbered_references: []
---

# UV-Vis 分析报告

## 报告 ID 信息

- report_id: `rpt-public-uv-vis-example-20260605-001`
- project_id: `prj-public-uv-vis-example`
- result_ids: `res-public-uv-vis-example-uv-vis-20260605-001`
- figure_ids: `fig-public-uv-vis-example-uv-vis-20260605-001`

## 数据来源

本报告基于 UV-Vis processing result `res-public-uv-vis-example-uv-vis-20260605-001` 生成，关联样品为 `sample-example-semiconductor-film-uv-vis-001`。原始数据、处理结果和图谱路径均通过 provenance 保留。

## 数据列与处理参数

用户确认的 x 列为 `energy_eV`，y 列为 `absorbance`，UV-Vis x 轴单位记录为 `eV`，信号模式为 `absorbance`。处理参数为 `{'smoothing': {'enabled': False, 'method': 'savitzky_golay', 'window_length': 9, 'polyorder': 2}, 'normalization': {'enabled': True, 'method': 'max_abs'}, 'feature_detection': {'method': 'scipy_find_peaks', 'prominence': 'auto', 'distance': 'auto', 'max_features': 10, 'source': 'ea.uv_vis.feature_detection:v0.2'}, 'edge_estimate': {'enabled': True, 'method': 'normalized_threshold', 'threshold_fraction': 0.5, 'source': 'ea.uv_vis.edge_threshold:v0.2'}, 'tauc_analysis': {'enabled': True, 'method': 'linear_window', 'transform': 'absorbance', 'transition': 'direct_allowed', 'exponent': 2.0, 'fit_window_eV': [2.18, 2.52], 'min_points': 16, 'min_r2_for_low_confidence': 0.9, 'source': 'ea.uv_vis.tauc_screening:v0.2'}, 'derivative_analysis': {'enabled': True, 'method': 'numpy_gradient', 'axis': 'energy_eV', 'min_points': 20, 'source': 'ea.uv_vis.derivative_screening:v0.2'}, 'correction_context': {'enabled': True, 'method': 'reviewed_metadata_record', 'source': 'ea.uv_vis.correction_context:v0.2', 'sample_geometry': {'sample_form': 'thin_film', 'path_length': 'not_applicable'}, 'substrate': {'material': 'quartz', 'status': 'reviewed', 'subtraction': 'not_applied'}, 'reference': {'reference_type': 'blank_quartz', 'reference_ref': 'synthetic public blank context', 'status': 'reviewed'}, 'background': {'background_ref': 'synthetic instrument dark baseline context', 'status': 'reviewed', 'numeric_correction': 'not_applied_by_ea'}, 'diffuse_reflectance': {'integrating_sphere': False, 'kubelka_munk_context': 'not_used'}, 'correction_notes': ['No substrate, reference, or background numeric correction is applied by EA in this public example.', 'Correction context is recorded only to make interpretation assumptions visible.']}}`。

## Correction context 记录

Correction context 状态为 `reviewed_correction_context_recorded`；reviewed fields: `sample_geometry、substrate、reference、background、diffuse_reflectance、correction_notes`；record: `processed/sample-example-semiconductor-film-uv-vis-001/uv_vis/res-public-uv-vis-example-uv-vis-20260605-001/uv_vis_correction_context.yml`；confidence: `low`；assignment_source: `ea.uv_vis.correction_context:v0.2`。

- sample geometry: `sample_form=thin_film; path_length=not_applicable`
- substrate: `material=quartz; status=reviewed; subtraction=not_applied`
- reference: `reference_type=blank_quartz; reference_ref=synthetic public blank context; status=reviewed`
- background: `background_ref=synthetic instrument dark baseline context; status=reviewed; numeric_correction=not_applied_by_ea`
- diffuse reflectance: `integrating_sphere=False; kubelka_munk_context=not_used`
- correction notes: `No substrate, reference, or background numeric correction is applied by EA in this public example.; Correction context is recorded only to make interpretation assumptions visible.`

该记录只保存已审核的基底、参比、背景、样品几何或漫反射语境；本阶段不执行自动数值校正，也不把这些 metadata 单独作为 optical mechanism 或 band gap 结论。

## 图谱

![UV-Vis spectrum](../processed/sample-example-semiconductor-film-uv-vis-001/uv_vis/res-public-uv-vis-example-uv-vis-20260605-001/fig-public-uv-vis-example-uv-vis-20260605-001.png)

原图文件：`processed/sample-example-semiconductor-film-uv-vis-001/uv_vis/res-public-uv-vis-example-uv-vis-20260605-001/fig-public-uv-vis-example-uv-vis-20260605-001.png`

## 主要观察

自动检测给出的主要 UV-Vis 光学特征位于：453 nm / 2.73 eV、380 nm / 3.26 eV。这些光学特征来自自动处理结果，仍需要结合样品厚度、透射/反射/吸收模式、基底背景、积分球或薄膜几何、其他表征结果和用户审核进行解释。

## UV-Vis feature 参数

| feature_id | position | wavelength (nm) | energy (eV) | prominence | feature type | confidence |
|---|---:|---:|---:|---:|---|---|
| uvvis-feature-001 | 2.734 eV | 453.5 | 2.734 | 0.115 | absorbance_maximum | low |
| uvvis-feature-002 | 3.262 eV | 380.1 | 3.262 | 0.0872 | absorbance_maximum | low |

## Optical edge 估计

自动阈值法记录的 optical edge 估计为 `554.5 nm` / `2.236 eV`；confidence: `low`；assignment_source: `ea.uv_vis.edge_threshold:v0.2`。

## Tauc/Kubelka-Munk screening

Reviewed-parameter Tauc/Kubelka-Munk screening 使用 `absorbance` transform、`direct_allowed` transition (exponent `2.0`)，fit window 为 `2.18-2.52 eV`，线性外推截距为 `2.047 eV`，R2 为 `0.999`；confidence: `low`；assignment_source: `ea.uv_vis.tauc_screening:v0.2`。该值只作为筛查记录，不等同于最终 optical band gap。

## Derivative screening

Derivative screening 状态为 `screening_derivative_recorded`；axis: `energy_eV` (`eV`)；最大一阶导数绝对值附近坐标为 `2.056 eV`，对应 `603.0 nm` / `2.056 eV`，first_derivative: `10.88`；confidence: `low`；assignment_source: `ea.uv_vis.derivative_screening:v0.2`。该记录只用于提示谱肩、边缘或拐点候选区域，不等同于最终 optical transition 或 band gap 结论。

## 可能结论与可信度

- Detected UV-Vis feature(s) are consistent with optical absorption/attenuation structure in the reviewed spectrum; treat them as screening evidence, not a band-gap or mechanism claim.
  - confidence: `low`；evidence features: `uvvis-feature-001, uvvis-feature-002`；assignment_source: `ea.uv_vis.feature_detection:v0.2`
- A threshold-based optical edge estimate was recorded for orientation only; formal band-gap analysis requires user-confirmed method context such as Tauc model, sample geometry, and references.
  - confidence: `low`；evidence features: `edge_estimate`；assignment_source: `ea.uv_vis.edge_threshold:v0.2`
- A screening absorbance Tauc/Kubelka-Munk linear-window intercept was recorded at 2.047 eV. Treat this as reviewed-model screening evidence only, not a definitive optical band gap.
  - confidence: `low`；evidence features: `tauc_analysis`；assignment_source: `ea.uv_vis.tauc_screening:v0.2`
- A UV-Vis derivative screening table was recorded; the strongest first-derivative magnitude occurs near 2.056 eV. Treat derivative extrema as shoulder/edge orientation only, not a definitive optical transition or band-gap conclusion.
  - confidence: `low`；evidence features: `derivative_analysis`；assignment_source: `ea.uv_vis.derivative_screening:v0.2`
- Reviewed UV-Vis correction context was recorded for sample_geometry, substrate, reference, background, diffuse_reflectance, correction_notes. Use it to interpret optical features and screening fits, but do not treat the metadata record as a numeric correction or a standalone mechanism claim.
  - confidence: `low`；evidence features: `correction_context`；assignment_source: `ea.uv_vis.correction_context:v0.2`
- 上述 UV-Vis 自动解释尚未绑定外部文献或项目参考谱；若用于正式结论，应补充 reference_ids 并让用户审核。
  - confidence: `insufficient`

## 谨慎解释

在当前数据范围内，自动 UV-Vis 特征和阈值 edge 只能支持“光学响应筛查”。不能仅凭本次处理结果直接确认带隙、跃迁类型、缺陷态、膜厚效应或吸收机制；正式 Tauc/derivative/Kubelka-Munk 等分析需要用户确认模型、样品形态和文献依据。相关解释尚未绑定外部文献或项目参考谱引用。任何科学解释进入项目记忆前都需要用户审核。

## 不确定性与限制

UV-Vis signal normalized by processing parameters.

## 输出文件

- processed CSV: `processed/sample-example-semiconductor-film-uv-vis-001/uv_vis/res-public-uv-vis-example-uv-vis-20260605-001/uv_vis_processed.csv`
- feature table: `processed/sample-example-semiconductor-film-uv-vis-001/uv_vis/res-public-uv-vis-example-uv-vis-20260605-001/uv_vis_features.csv`
- Tauc/Kubelka-Munk table: `processed/sample-example-semiconductor-film-uv-vis-001/uv_vis/res-public-uv-vis-example-uv-vis-20260605-001/uv_vis_tauc.csv`
- derivative table: `processed/sample-example-semiconductor-film-uv-vis-001/uv_vis/res-public-uv-vis-example-uv-vis-20260605-001/uv_vis_derivative.csv`
- correction context: `processed/sample-example-semiconductor-film-uv-vis-001/uv_vis/res-public-uv-vis-example-uv-vis-20260605-001/uv_vis_correction_context.yml`
- plot: `processed/sample-example-semiconductor-film-uv-vis-001/uv_vis/res-public-uv-vis-example-uv-vis-20260605-001/fig-public-uv-vis-example-uv-vis-20260605-001.png`
- metadata: `processed/sample-example-semiconductor-film-uv-vis-001/uv_vis/res-public-uv-vis-example-uv-vis-20260605-001/uv_vis_metadata.yml`

## References

本报告当前未引用外部文献。若后续加入文献解释，正文对应位置必须使用 `[1]` 形式标注，并在本节列出 DOI、本地 PDF 或网页链接。

## 溯源

本报告草稿引用 UV-Vis result `res-public-uv-vis-example-uv-vis-20260605-001`，对应 provenance 将在报告生成后写入。
