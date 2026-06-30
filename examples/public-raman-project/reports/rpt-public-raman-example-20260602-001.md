---
schema_version: '0.2'
created_at: '2026-06-02T17:20:00'
updated_at: '2026-06-02T17:20:00'
status: draft
source_refs: []
provenance_refs:
- prov-20260602-005
review_refs: []
report_id: rpt-public-raman-example-20260602-001
project_id: prj-public-raman-example
report_type: raman_analysis
language: zh
audience: self
related_experiments:
- exp-20260516-001
related_samples:
- sample-example-mos2-001
related_results:
- res-public-raman-example-raman-20260602-001
figure_ids:
- fig-public-raman-example-raman-20260602-001
include_next_step_suggestions: false
reference_ids: []
numbered_references: []
---

# Raman 分析报告

## 报告 ID 信息

- report_id: `rpt-public-raman-example-20260602-001`
- project_id: `prj-public-raman-example`
- result_ids: `res-public-raman-example-raman-20260602-001`
- figure_ids: `fig-public-raman-example-raman-20260602-001`

## 数据来源

本报告基于 Raman processing result `res-public-raman-example-raman-20260602-001` 生成，关联样品为 `sample-example-mos2-001`。原始数据、处理结果和图谱路径均通过 provenance 保留。

## 数据列与处理参数

用户确认的 x 列为 `col_0`，y 列为 `col_1`，Raman shift 单位记录为 `cm^-1`。处理参数为 `{'baseline_correction': {'enabled': False, 'method': 'asls', 'lambda': 100000.0, 'p': 0.01, 'niter': 10}, 'smoothing': {'enabled': False, 'method': 'savitzky_golay', 'window_length': 9, 'polyorder': 2}, 'normalization': {'enabled': True, 'method': 'max_intensity'}, 'spike_detection': {'enabled': False, 'method': 'rolling_mad', 'window': 7, 'mad_threshold': 8.0}, 'peak_detection': {'method': 'scipy_find_peaks', 'prominence': 'auto', 'distance': 'auto'}, 'peak_fitting': {'enabled': True, 'method': 'local_gaussian', 'window_cm-1': 'auto', 'min_points': 7}}`。

## 主要观察

自动检峰给出的主要峰位包括：316.3 cm^-1、321.6 cm^-1、331.9 cm^-1、348.1 cm^-1、386.2 cm^-1、405.9 cm^-1。这些峰位是脚本处理得到的 processed result，仍需要结合样品形貌、实验记录和用户审核进行解释。

## 拟合峰参数

| peak_id | position (cm^-1) | fit center (cm^-1) | FWHM (cm^-1) | prominence | assignment |
|---|---:|---:|---:|---:|---|
| peak-006 | 405.9 | 405.85 | 3.16 | 0.765 | MoS2 A1g-like |
| peak-005 | 386.2 | 386.09 | 1.61 | 0.478 | MoS2 E2g-like |
| peak-007 | 446.8 | 446.89 | 0.18 | 0.128 | unassigned |
| peak-008 | 455.0 | 456.91 | 14.97 | 0.128 | unassigned |
| peak-001 | 316.3 | 316.14 | 0.19 | 0.111 | unassigned |
| peak-003 | 331.9 | 331.85 | 0.09 | 0.0761 | unassigned |
| peak-009 | 487.9 | 488.07 | 0.18 | 0.0761 | unassigned |
| peak-002 | 321.6 | 321.66 | 0.51 | 0.0727 | unassigned |

## 可能结论与可信度

- Detected E2g-like and A1g-like candidate peaks form a MoS2-like Raman pair; the mode separation is more consistent with a thin-layer MoS2 signal than with a large bulk-like separation.
  - confidence: `medium`；evidence peaks: `peak-005, peak-006`；mode separation: `19.76 cm^-1`
- 上述自动解释尚未绑定外部文献；若用于正式结论，应补充 reference_ids 并让用户审核。
  - confidence: `insufficient`

## 谨慎解释

在当前数据范围内，自动峰位与拟合结果只能支持“可能解释”，不能仅凭本次 Raman 数据直接确认层数、缺陷机制或生长机理。相关解释尚未绑定外部文献引用。任何科学解释进入项目记忆前都需要用户审核。

## 不确定性与限制

Intensity normalized by processing parameters.；No baseline correction was applied.

## 输出文件

- processed CSV: `processed/sample-example-mos2-001/raman/res-public-raman-example-raman-20260602-001/raman_processed.csv`
- peak table: `processed/sample-example-mos2-001/raman/res-public-raman-example-raman-20260602-001/raman_peaks.csv`
- plot: `processed/sample-example-mos2-001/raman/res-public-raman-example-raman-20260602-001/fig-public-raman-example-raman-20260602-001.png`
- metadata: `processed/sample-example-mos2-001/raman/res-public-raman-example-raman-20260602-001/raman_metadata.yml`

## References

本报告当前未引用外部文献。若后续加入文献解释，正文对应位置必须使用 `[1]` 形式标注，并在本节列出 DOI、本地 PDF 或网页链接。

## 溯源

本报告草稿引用 Raman result `res-public-raman-example-raman-20260602-001`，对应 provenance 将在报告生成后写入。
