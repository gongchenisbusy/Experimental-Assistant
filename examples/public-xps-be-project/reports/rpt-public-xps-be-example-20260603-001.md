---
schema_version: '0.2'
created_at: '2026-06-03T09:28:00'
updated_at: '2026-06-03T09:28:00'
status: draft
source_refs: []
provenance_refs:
- prov-20260603-011
review_refs: []
report_id: rpt-public-xps-be-example-20260603-001
project_id: prj-public-xps-be-example
report_type: xps_analysis
language: zh
audience: self
related_experiments:
- exp-20260603-001
related_samples:
- sample-example-si-sio2-xps-001
related_results:
- res-public-xps-be-example-xps-20260603-001
figure_ids:
- fig-public-xps-be-example-xps-20260603-001
include_next_step_suggestions: false
reference_ids:
- builtin-xps-charge-reference-guide-2020
- builtin-xps-thermo-c
- builtin-xps-thermo-si
- builtin-xps-cardiff-o1s-reference
- builtin-xps-o1s-metal-oxide-insight-2025
- builtin-xps-o1s-oxygen-vacancy-critical-2025
- builtin-xps-thermo-o
numbered_references:
- number: 1
  reference_id: builtin-xps-charge-reference-guide-2020
  entry: '[1] Baer, D. R.; Artyushkova, K.; Cohen, H.; Easton, C. D.; Engelhard, M.;
    Gengenbach, T. R.; Greczynski, G.; Mack, P.; Morgan, D. J.; Roberts, A. XPS guide:
    Charge neutralization and binding energy referencing for insulating samples. Journal
    of Vacuum Science & Technology A 38, 031204 (2020). | DOI: 10.1116/6.0000057 |
    Web: https://doi.org/10.1116/6.0000057'
- number: 2
  reference_id: builtin-xps-thermo-c
  entry: '[2] Thermo Fisher Scientific. Carbon XPS periodic table reference page.
    | Web: https://www.thermofisher.com/us/en/home/materials-science/learning-center/periodic-table/non-metal/carbon.html'
- number: 3
  reference_id: builtin-xps-thermo-si
  entry: '[3] Thermo Fisher Scientific. Silicon XPS periodic table reference page.
    | Web: https://www.thermofisher.com/us/en/home/materials-science/learning-center/periodic-table/metalloid/silicon.html'
- number: 4
  reference_id: builtin-xps-cardiff-o1s-reference
  entry: '[4] Cardiff University XPS Analysis. Oxygen reference page. | Web: https://sites.cardiff.ac.uk/xpsaccess/reference/oxygen/'
- number: 5
  reference_id: builtin-xps-o1s-metal-oxide-insight-2025
  entry: '[5] Graf, A.; Isaacs, M. A.; Morgan, D. J. Insight Notes: Considerations
    in the XPS Analysis of O1s Spectra for Metal Oxides. Surface and Interface Analysis
    (2025). | DOI: 10.1002/sia.70036 | Web: https://doi.org/10.1002/sia.70036'
- number: 6
  reference_id: builtin-xps-o1s-oxygen-vacancy-critical-2025
  entry: '[6] Easton, C. D.; Morgan, D. J. Critical examination of the use of x-ray
    photoelectron spectroscopy (XPS) O 1s to characterize oxygen vacancies in catalytic
    materials and beyond. Journal of Vacuum Science & Technology A 43, 053205 (2025).
    | DOI: 10.1116/6.0004686 | Web: https://doi.org/10.1116/6.0004686'
- number: 7
  reference_id: builtin-xps-thermo-o
  entry: '[7] Thermo Fisher Scientific. Oxygen XPS periodic table reference page.
    | Web: https://www.thermofisher.com/us/en/home/materials-science/learning-center/periodic-table/non-metal/oxygen.html'
---

# XPS 分析报告

## 报告 ID 信息

- report_id: `rpt-public-xps-be-example-20260603-001`
- project_id: `prj-public-xps-be-example`
- result_ids: `res-public-xps-be-example-xps-20260603-001`
- figure_ids: `fig-public-xps-be-example-xps-20260603-001`

## 数据来源

本报告基于 XPS processing result `res-public-xps-be-example-xps-20260603-001` 生成，关联样品为 `sample-example-si-sio2-xps-001`。原始数据、处理结果和图谱路径均通过 provenance 保留。

## 数据列、校准与处理参数

用户确认的 x 列为 `binding_energy_eV`，y 列为 `intensity`，XPS x 轴单位记录为 `eV`。本次处理记录的 binding-energy shift 为 `0.000 eV`；calibration reference 为 `Synthetic public example; no automatic charge correction. C 1s/Si 2p BE candidates are advisory discussion starters only.`；confidence: `low`。处理参数为 `{'baseline_correction': {'enabled': False, 'method': 'rolling_quantile', 'window_points': 101, 'quantile': 0.05}, 'smoothing': {'enabled': False, 'method': 'savitzky_golay', 'window_length': 9, 'polyorder': 2}, 'normalization': {'enabled': True, 'method': 'max_intensity'}, 'peak_detection': {'method': 'scipy_find_peaks', 'prominence': 'auto', 'distance': 'auto', 'max_features': 12, 'source': 'ea.xps.peak_detection:v0.2'}, 'component_quantification': {'enabled': False, 'method': 'reviewed_window_integration', 'integration_baseline': 'local_minimum', 'min_points': 5, 'source': 'ea.xps.component_quantification:v0.2', 'components': []}, 'component_fit': {'enabled': False, 'method': 'reviewed_component_fit_screening', 'source': 'ea.xps.component_fit:v0.2', 'input_intensity_column': 'processed_intensity', 'fit_intensity_column': 'xps_component_fit_intensity', 'residual_column': 'xps_component_fit_residual', 'region_id_column': 'xps_component_fit_region_id', 'min_points': 8, 'max_nfev': 5000, 'fit_quality_thresholds': {'max_rmse': None, 'min_r_squared': None}, 'spin_orbit_constraints': [], 'regions': [], 'reference_ids': [], 'reviewer_notes': [], 'caveats': []}, 'region_records': {'enabled': False, 'method': 'reviewed_multi_region_project_record', 'source': 'ea.xps.region_records:v0.2', 'min_points': 3, 'default_calibration_group_id': None, 'regions': [], 'reference_ids': [], 'reviewer_notes': [], 'caveats': []}, 'background_model': {'enabled': False, 'method': 'reviewed_background_record', 'source': 'ea.xps.background_model:v0.2', 'regions': [], 'applied_to_processed_data': False, 'software': {}, 'reference_ids': [], 'reviewer_notes': [], 'caveats': []}, 'background_subtraction': {'enabled': False, 'method': 'reviewed_linear_background_subtraction', 'source': 'ea.xps.background_subtraction:v0.2', 'input_intensity_column': 'processed_intensity', 'background_column': 'xps_linear_background', 'corrected_intensity_column': 'xps_background_subtracted_intensity', 'region_id_column': 'xps_background_subtraction_region_id', 'min_points': 5, 'tougaard_B': None, 'tougaard_C_eV2': 1643.0, 'integration_direction': 'toward_higher_binding_energy', 'regions': [], 'reference_ids': [], 'reviewer_notes': [], 'caveats': []}}`。

## XPS background model record

当前没有启用或记录 XPS background model record。

当前没有可展示的 XPS background model region。

## XPS reviewed background subtraction

当前没有启用或记录 XPS background subtraction。

当前没有可展示的 XPS background subtraction region。

## 图谱

![XPS spectrum](../processed/sample-example-si-sio2-xps-001/xps/res-public-xps-be-example-xps-20260603-001/fig-public-xps-be-example-xps-20260603-001.png)

原图文件：`processed/sample-example-si-sio2-xps-001/xps/res-public-xps-be-example-xps-20260603-001/fig-public-xps-be-example-xps-20260603-001.png`

## 主要观察

自动检测给出的主要 XPS peak binding energy 包括：103.50 eV、285.00 eV、532.50 eV。这些 peak 来自自动处理结果，仍需要结合能量校准、背景扣除、拟合模型、元素窗口、样品制备、仪器设置和用户审核进行解释。

## XPS peak 参数

| peak_id | binding energy (eV) | raw energy | prominence | component model | assignment | confidence |
|---|---:|---:|---:|---|---|---|
| xps-peak-001 | 103.50 | 103.50 | 0.915 | not_fitted | unassigned | insufficient |
| xps-peak-002 | 285.00 | 285.00 | 0.738 | not_fitted | unassigned | insufficient |
| xps-peak-003 | 532.50 | 532.50 | 0.666 | not_fitted | unassigned | insufficient |

## XPS component quantification screening

当前未启用 XPS component quantification screening；如需组分面积/RSF 筛查，应先由用户确认 component windows、背景/模型和 sensitivity factors。

当前没有可展示的 XPS component quantification screening 结果。

## XPS reviewed component fit screening

当前没有启用或记录 XPS component_fit。

当前没有可展示的 XPS component_fit component。

## XPS reviewed multi-region records

当前没有启用或记录 XPS region_records。

当前没有可展示的 XPS region_records region。

## 可能结论与可信度

- Detected XPS peak(s) indicate photoelectron spectral structure in the reviewed binding-energy window; treat them as screening evidence only until calibration, background model, component fitting, and references are user-confirmed.[1][2][3][4][5][6][7]
  - confidence: `low`；evidence peaks: `xps-peak-001, xps-peak-002, xps-peak-003`；assignment_source: `ea.xps.peak_detection:v0.2`

## Source-backed XPS parameter suggestions

- suggestion_record: `suggestions/xps/suggestion-20260603-001/xps_parameter_suggestions.yml`；suggestion_id: `suggestion-20260603-001`；status: `ready_for_user_review`；candidate_count: `5`；auto_applied: `false`。
  - `xps-builtin-c1s-adventitious-cc-binding-energy-candidate`: binding_energy_candidate[2][1]
    - target_parameter_path: `interpretation.binding_energy_candidates`；review_state: `ready_for_user_review`；confidence: `medium`；parameter_origin: `source_suggested`
    - values: chemical_state_label=Adventitious or hydrocarbon C-C/C-H C 1s candidate；expected_binding_energy_eV=284.8；binding_energy_window_eV=[284.6, 285.0]；calibration_reference=User-reviewed C 1s or instrument calibration context required; the Thermo reference notes C-C is often set to 284.8 eV by default but is not always valid.；charge_reference_assumption=Do not use this candidate to apply charge correction automatically; record the actual project charge-neutralization or BE-referencing procedure before report use.；overlap_notes=C 1s may overlap Ru 3d, Sr 3p1/2, or K 2p in some systems.；Adventitious carbon chemistry and film thickness can shift apparent C 1s position.
    - source_summary: Thermo's carbon XPS reference lists adventitious-carbon C-C near 284.8 eV and explicitly cautions that this default charge reference is not always valid.
    - applicability: Use only for spectra where the user confirms adventitious/hydrocarbon carbon is plausible and the C 1s region is reviewed.；Treat this as a BE/reference discussion candidate, not as an instruction to shift the spectrum.
    - caveats: Not a universal charge reference.；Does not prove surface contamination source, carbon hybridization, or sample composition.
    - unresolved_reference_ids: `无`
  - `xps-builtin-c1s-c-o-c-binding-energy-candidate`: binding_energy_candidate[2][1]
    - target_parameter_path: `interpretation.binding_energy_candidates`；review_state: `ready_for_user_review`；confidence: `low`；parameter_origin: `source_suggested`
    - values: chemical_state_label=C-O-C / C-O C 1s candidate；expected_binding_energy_eV=286.0；binding_energy_window_eV=[285.7, 286.4]；calibration_reference=Candidate assumes the C 1s energy scale has already been reviewed, commonly relative to a project-approved C-C/C-H reference near 284.8 eV or another documented calibration.；charge_reference_assumption=No charge correction is applied by this candidate; insulating or mixed samples require a separately reviewed referencing procedure.；overlap_notes=C-N, C-O, and ether/alcohol-like contributions can appear in similar C 1s ranges.
    - source_summary: Thermo's carbon XPS reference lists C-O-C near 286 eV in adventitious carbon and C-O near 286 eV for polymers.
    - applicability: Use only after C 1s baseline/background and possible overlapping components are reviewed.；Interpret with O 1s, sample chemistry, and project literature before assigning oxygenated carbon.
    - caveats: C 1s BE alone cannot distinguish all C-O, C-N, ether, alcohol, or contamination contributions.；Not a functional-group or composition proof.
    - unresolved_reference_ids: `无`
  - `xps-builtin-c1s-o-c-o-binding-energy-candidate`: binding_energy_candidate[2][1]
    - target_parameter_path: `interpretation.binding_energy_candidates`；review_state: `ready_for_user_review`；confidence: `low`；parameter_origin: `source_suggested`
    - values: chemical_state_label=O-C=O / carboxylate-like C 1s candidate；expected_binding_energy_eV=288.5；binding_energy_window_eV=[288.0, 289.2]；calibration_reference=Candidate assumes the C 1s energy scale has already been reviewed, commonly relative to a project-approved C-C/C-H reference near 284.8 eV or another documented calibration.；charge_reference_assumption=No charge correction is applied by this candidate; document charge neutralization and BE referencing before using it as report evidence.；overlap_notes=Ester, carboxylate, carbonate, and high-BE contamination contributions can overlap in this region.
    - source_summary: Thermo's carbon XPS reference lists O-C=O near 288.5 eV for adventitious carbon and C=O-style polymer contributions around 288-290 eV.
    - applicability: Use only when sample chemistry, O 1s data, and reviewed C 1s fitting context make a carboxylate/ester/carbonyl discussion plausible.；Review carbonate/ester overlap risks for oxide or carbonate-containing samples.
    - caveats: Not a standalone carboxylate, carbonate, ester, or oxidation proof.；Requires project-specific chemistry and references for final assignment.
    - unresolved_reference_ids: `无`
  - `xps-builtin-si2p-elemental-binding-energy-candidate`: binding_energy_candidate[3][1]
    - target_parameter_path: `interpretation.binding_energy_candidates`；review_state: `ready_for_user_review`；confidence: `medium`；parameter_origin: `source_suggested`
    - values: chemical_state_label=Elemental silicon Si 2p candidate；expected_binding_energy_eV=99.4；binding_energy_window_eV=[99.0, 99.8]；calibration_reference=User-reviewed instrument or project BE calibration required; compare with any C 1s referencing only after the user confirms that procedure.；charge_reference_assumption=No charge correction is applied by this candidate; conductive, semiconducting, native-oxide, or insulating contexts must be reviewed separately.；overlap_notes=Native oxide can add higher-BE Si 2p components and change relative intensities.
    - source_summary: Thermo's silicon XPS reference lists elemental Si 2p around 99.4 eV and notes that Si 2p spin-orbit splitting is mainly considered for elemental Si.
    - applicability: Use for silicon wafer, elemental Si, or reduced Si discussion only after oxide thickness, surface cleaning, and pass-energy context are reviewed.；Consider the existing Si 2p spin-orbit candidate when fitting resolved elemental Si doublets.
    - caveats: Not a proof of elemental silicon fraction or oxide thickness.；Does not automatically choose a resolved Si 2p doublet model.
    - unresolved_reference_ids: `无`
  - `xps-builtin-si2p-sio2-binding-energy-candidate`: binding_energy_candidate[3][1]
    - target_parameter_path: `interpretation.binding_energy_candidates`；review_state: `ready_for_user_review`；confidence: `low`；parameter_origin: `source_suggested`
    - values: chemical_state_label=Silicon dioxide Si 2p candidate；expected_binding_energy_eV=103.5；binding_energy_window_eV=[103.0, 104.0]；calibration_reference=Thermo lists silicates and nitride as referenced to C 1s at 284.8 eV; this candidate requires the user to review the actual project calibration/reference method before use.；charge_reference_assumption=No charge correction is applied by this candidate; insulating SiO2 or silicate surfaces require documented charge-neutralization and BE-referencing choices.；overlap_notes=Silicates, aluminosilicates, SiON, and other oxidized Si environments may fall near this region.
    - source_summary: Thermo's silicon XPS reference lists SiO2 Si 2p around 103.5 eV and notes C 1s 284.8 eV referencing for silicates/nitride examples.
    - applicability: Use only when SiO2, native oxide, silicate, or oxide-layer context is plausible and reviewed with sample preparation history.；Compare elemental Si and oxide components when substrate/native-oxide thickness matters.
    - caveats: Not a standalone SiO2 thickness, stoichiometry, or composition proof.；Requires project-specific calibration and model review before final assignment.
    - unresolved_reference_ids: `无`
- suggestion_record: `suggestions/xps/suggestion-20260603-002/xps_parameter_suggestions.yml`；suggestion_id: `suggestion-20260603-002`；status: `ready_for_user_review`；candidate_count: `4`；auto_applied: `false`。
  - `xps-builtin-o1s-carbonate-carbonyl-binding-energy-candidate`: binding_energy_candidate[7][4][5][1]
    - target_parameter_path: `interpretation.binding_energy_candidates`；review_state: `ready_for_user_review`；confidence: `low`；parameter_origin: `source_suggested`
    - values: chemical_state_label=Carbonate / carbonyl-like O 1s candidate；expected_binding_energy_eV=531.8；binding_energy_window_eV=[531.0, 532.5]；calibration_reference=Candidate assumes the O 1s and C 1s energy scales have been reviewed; carbonate discussion should be cross-checked against a C 1s carbonate/carboxylate-like contribution near 289-290 eV when available.；charge_reference_assumption=No charge correction is applied by this candidate; document the project BE reference and charge neutralization before report use.；overlap_notes=Hydroxyl, adsorbed oxygen, organic oxygen, and carbonate contributions can overlap strongly around 531-532 eV.；O 1s alone generally cannot separate carbonate from carbonyl/organic oxygen without C 1s and sample-context evidence.
    - source_summary: Thermo and Cardiff list metal carbonate O 1s around 531-532 eV, and Thermo also places organic C=O near 531.5-532 eV; Cardiff guidance recommends checking C 1s near 289-290 eV for carbonate evidence.
    - applicability: Use when sample exposure, carbonate precursor, ambient aging, CO2/H2O exposure, or C 1s evidence makes carbonate or carbonyl-like oxygen plausible.；Treat carbonate and carbonyl as competing explanations unless project chemistry or registered references separate them.
    - caveats: Not a standalone carbonate, carbonyl, or contamination proof.；Do not quantify carbonate versus hydroxyl from O 1s without a reviewed fitting protocol and corroborating C 1s evidence.
    - unresolved_reference_ids: `无`
  - `xps-builtin-o1s-hydroxyl-adsorbed-oxygen-binding-energy-candidate`: binding_energy_candidate[5][6][1]
    - target_parameter_path: `interpretation.binding_energy_candidates`；review_state: `ready_for_user_review`；confidence: `low`；parameter_origin: `source_suggested`
    - values: chemical_state_label=Hydroxyl / adsorbed oxygen-like O 1s candidate；expected_binding_energy_eV=531.5；binding_energy_window_eV=[531.0, 532.2]；calibration_reference=Candidate assumes reviewed O 1s calibration and charge compensation; compare with lattice O 1s, C 1s, and relevant metal core levels before interpretation.；charge_reference_assumption=No charge correction is applied by this candidate; poor charge correction or differential charging can mimic a higher-BE shoulder.；overlap_notes=Carbonate, organic C=O/C-O, adsorbed water, silica/silicone contamination, and some fitted defect labels can occupy similar O 1s ranges.；If the candidate is being used to discuss oxygen vacancies, require independent evidence and keep the O 1s evidence low-confidence unless the experiment is specifically designed for that question.
    - source_summary: Recent O 1s guidance describes hydroxide / adsorbed oxygen contributions near 531-532 eV, while warning that this region overlaps carbonate, organics, water, and oxygen-vacancy labels used in the literature.
    - applicability: Use when sample storage, air/water exposure, surface treatment, or reaction environment makes hydroxylated or adsorbed oxygen species plausible.；Ask for C 1s, metal core-level, vacuum/transfer history, and any in situ or ex situ context before promoting the candidate in a report.
    - caveats: Not an oxygen-vacancy proof.；Not a standalone hydroxyl quantification; fitting model, FWHM, background, sample history, and corroborating spectra must be reviewed.
    - unresolved_reference_ids: `无`
  - `xps-builtin-o1s-lattice-oxide-binding-energy-candidate`: binding_energy_candidate[7][4][5][1]
    - target_parameter_path: `interpretation.binding_energy_candidates`；review_state: `ready_for_user_review`；confidence: `medium`；parameter_origin: `source_suggested`
    - values: chemical_state_label=Lattice oxygen / metal oxide O 1s candidate；expected_binding_energy_eV=529.8；binding_energy_window_eV=[529.0, 531.0]；calibration_reference=Candidate assumes reviewed O 1s energy calibration; source examples commonly reference C 1s at 284.8 eV, but the project must document its actual charge-neutralization and BE-referencing procedure and should cross-check a relevant metal core level when possible.；charge_reference_assumption=No charge correction is applied by this candidate; differential charging and incorrect BE correction can move O 1s intensity between candidate regions.；overlap_notes=O 1s may overlap Na KLL, Sb 3d, Pd 3p, or V 2p regions depending on the sample.；The high-binding-energy side of oxide O 1s can overlap hydroxyl, carbonate, adsorbed water, organic oxygen, loss features, or asymmetric conducting-oxide line shapes.
    - source_summary: Thermo and Cardiff public O 1s references list metal oxide / M-O O 1s around 529-530 eV, while recent O 1s guidance describes lattice oxygen in transition-metal oxides around 529.5-531 eV and stresses calibration and corroborating evidence.
    - applicability: Use only when a metal oxide or oxide-surface context is plausible and the user has reviewed sample handling, calibration, background, and metal core-level context.；Treat a lattice-oxide candidate as an interpretation hypothesis for report discussion, not as an automatic oxide stoichiometry or phase assignment.
    - caveats: Not a standalone proof of oxide phase, oxide stoichiometry, oxide thickness, oxygen deficiency, or catalytic activity.；Requires project-specific metal core-level, C 1s, calibration, and sample-history evidence before final assignment.
    - unresolved_reference_ids: `无`
  - `xps-builtin-o1s-silica-organic-co-binding-energy-candidate`: binding_energy_candidate[7][4][5][1]
    - target_parameter_path: `interpretation.binding_energy_candidates`；review_state: `ready_for_user_review`；confidence: `low`；parameter_origin: `source_suggested`
    - values: chemical_state_label=Silica / organic C-O high-BE O 1s candidate；expected_binding_energy_eV=532.9；binding_energy_window_eV=[532.5, 533.5]；calibration_reference=Candidate assumes reviewed O 1s calibration; compare with Si 2p, C 1s, instrument/sample contamination history, and any project-approved charge-reference method before interpretation.；charge_reference_assumption=No charge correction is applied by this candidate; insulating silica or polymer/organic surfaces require documented charge-neutralization and BE-referencing choices.；overlap_notes=SiO2, organic C-O, adsorbed water, silicone contamination, and high-BE shoulders can overlap in this range.；High-BE O 1s intensity can also be affected by loss features or line-shape asymmetry in some conducting oxides.
    - source_summary: Thermo and Cardiff list SiO2 O 1s near 532.9 eV and organic C-O oxygen near about 533 eV; Thermo cautions that water and organic contamination can overlap directly with SiO2 in O 1s.
    - applicability: Use when silica, silicate, silicone/lab contamination, polymer, adsorbed organic oxygen, or high-BE O 1s context is plausible.；Cross-check Si 2p and C 1s before choosing between silica-like and organic C-O interpretations.
    - caveats: Not a standalone proof of SiO2, silicate, organic C-O, adsorbed water, or contamination source.；Requires project-specific Si 2p/C 1s evidence, background/fitting review, and sample-history context before final assignment.
    - unresolved_reference_ids: `无`
- 上述 XPS parameter suggestions 是 source-backed advisory records；它们可以帮助组织 spin-orbit、Tougaard/background、component/bounds/peak-shape 或 binding-energy/chemical-state 候选讨论，但不会自动写入 processing parameters、不会静默校准谱图或应用荷电校正，不能单独证明化学态、组成或正式定量。

## 谨慎解释

在当前数据范围内，自动 XPS peak 只能支持“谱图结构筛查”。不能仅凭本次自动检峰直接确认化学态、价态、元素组成、表面污染、充电校正正确性或拟合组分；正式 XPS 结论需要用户确认校准参考、背景模型、spin-orbit/峰形/约束、灵敏度因子和文献依据。相关解释应与已登记文献、标准谱库或项目参考谱对应位置共同阅读[1][2][3][4][5][6][7]。任何科学解释进入项目记忆前都需要用户审核。

## 不确定性与限制

XPS intensity normalized by processing parameters.

## 输出文件

- processed CSV: `processed/sample-example-si-sio2-xps-001/xps/res-public-xps-be-example-xps-20260603-001/xps_processed.csv`
- peak table: `processed/sample-example-si-sio2-xps-001/xps/res-public-xps-be-example-xps-20260603-001/xps_peaks.csv`
- component table: `processed/sample-example-si-sio2-xps-001/xps/res-public-xps-be-example-xps-20260603-001/xps_components.csv`
- component fit: `未生成`
- component fit table: `未生成`
- region records: `未生成`
- region records table: `未生成`
- background model: `未生成`
- background subtraction: `未生成`
- plot: `processed/sample-example-si-sio2-xps-001/xps/res-public-xps-be-example-xps-20260603-001/fig-public-xps-be-example-xps-20260603-001.png`
- metadata: `processed/sample-example-si-sio2-xps-001/xps/res-public-xps-be-example-xps-20260603-001/xps_metadata.yml`

## References

[1] Baer, D. R.; Artyushkova, K.; Cohen, H.; Easton, C. D.; Engelhard, M.; Gengenbach, T. R.; Greczynski, G.; Mack, P.; Morgan, D. J.; Roberts, A. XPS guide: Charge neutralization and binding energy referencing for insulating samples. Journal of Vacuum Science & Technology A 38, 031204 (2020). | DOI: 10.1116/6.0000057 | Web: https://doi.org/10.1116/6.0000057
[2] Thermo Fisher Scientific. Carbon XPS periodic table reference page. | Web: https://www.thermofisher.com/us/en/home/materials-science/learning-center/periodic-table/non-metal/carbon.html
[3] Thermo Fisher Scientific. Silicon XPS periodic table reference page. | Web: https://www.thermofisher.com/us/en/home/materials-science/learning-center/periodic-table/metalloid/silicon.html
[4] Cardiff University XPS Analysis. Oxygen reference page. | Web: https://sites.cardiff.ac.uk/xpsaccess/reference/oxygen/
[5] Graf, A.; Isaacs, M. A.; Morgan, D. J. Insight Notes: Considerations in the XPS Analysis of O1s Spectra for Metal Oxides. Surface and Interface Analysis (2025). | DOI: 10.1002/sia.70036 | Web: https://doi.org/10.1002/sia.70036
[6] Easton, C. D.; Morgan, D. J. Critical examination of the use of x-ray photoelectron spectroscopy (XPS) O 1s to characterize oxygen vacancies in catalytic materials and beyond. Journal of Vacuum Science & Technology A 43, 053205 (2025). | DOI: 10.1116/6.0004686 | Web: https://doi.org/10.1116/6.0004686
[7] Thermo Fisher Scientific. Oxygen XPS periodic table reference page. | Web: https://www.thermofisher.com/us/en/home/materials-science/learning-center/periodic-table/non-metal/oxygen.html

## 溯源

本报告草稿引用 XPS result `res-public-xps-be-example-xps-20260603-001`，对应 provenance 将在报告生成后写入。
