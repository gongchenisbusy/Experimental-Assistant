# EA 数据报告、图片和引用标准

> 状态：v0.2 设计草案  
> 日期：2026-06-30  
> 用途：规范 EA 中表征分析报告、科学图片、图片 ID、报告 ID、引用格式和可信度表达。

## 1. 总原则

EA 报告应帮助研究者快速判断数据是否可靠、处理是否可复现、结论是否有证据支撑。报告不应只写“无法确定”，而应在科学谨慎的前提下列出可支持的推论、替代解释和可信度。

图片风格默认采用接近 Nature 期刊图件的干净学术风格：白底、少装饰、清晰坐标、可读字体、必要标注、颜色克制、导出质量足够。不同目标期刊可以在后续增加 profile。

## 2. ID 设计

项目级 ID 建议如下：

```text
project_id: prj-{project_slug}
raw_data_id: raw-{project_slug}-{yyyymmdd}-{nnn}-{hash8}
result_id: res-{project_slug}-{method}-{yyyymmdd}-{nnn}
report_id: rpt-{project_slug}-{yyyymmdd}-{nnn}
figure_id: fig-{project_slug}-{method}-{yyyymmdd}-{nnn}
```

示例：

```text
rpt-lm-mos2-20260630-001
fig-lm-mos2-raman-20260630-003
raw-lm-mos2-20260630-014-a1b2c3d4
```

图片文件命名：

```text
fig-lm-mos2-raman-20260630-003__rpt-lm-mos2-20260630-001__sample-s12.png
```

`figures/index.yml` 必须能从图片 ID 找回：

- 图片本地路径
- 所属报告 ID
- 结果 ID
- 原始数据 ID
- 样品 ID
- 实验记录 ID
- 生成脚本和参数
- 创建时间
- caption 和简短用途

用户只给 EA 一个 `figure_id` 时，EA 应能定位原图、报告、原始数据、样品、实验条件和相关项目背景。

## 3. 图片画布标识

每张 EA 生成图必须在图片画布右下角标注：

```text
FigID: fig-lm-mos2-raman-20260630-003 | Report: rpt-lm-mos2-20260630-001
```

要求：

- 标注位于画布右下角的页边距或 footer 区，不覆盖数据区域。
- 字体小于正文坐标字体，颜色使用浅灰。
- 标注随图片导出，不只存在于报告正文。
- 多 panel 图只标一个总 figure ID，panel 使用 `a, b, c`。

## 4. 通用图片规范

默认规范：

- 折线、散点、拟合图优先导出 PDF/SVG，同时提供 PNG。
- 照片、显微图、热图等提供高分辨率 PNG/TIFF。
- 坐标轴必须有物理量和单位。
- 图例只保留解释数据所需内容。
- 处理后的图必须能追溯到处理参数和原始数据。
- 对显微图，优先使用 scale bar，不只写放大倍数。
- 图像亮度、对比度等调整必须统一应用，并在 provenance 中记录。
- 默认使用色盲友好配色，避免彩虹色图作为主图默认色表。

## 5. 方法特异性标注

Raman：

- x 轴为 Raman shift，单位 `cm^-1`。
- y 轴说明 raw、baseline-corrected、normalized 或 fitted intensity。
- 标注主要峰位；峰名、峰心、FWHM、强度比等放在图注或表格中，避免图上拥挤。
- 记录 baseline、平滑、去 spike、拟合模型和参数。
- 对 MoS2 等体系，可在项目上下文支持时标注常用模式名，但不能把体系外峰名硬套到未知样品。

PL：

- 标明激发波长、激发功率、积分时间、温度和归一化方式。
- x 轴可用 wavelength 或 energy；必要时双轴或在表格中给换算值。
- 标注峰心、FWHM、积分强度和多峰拟合结果。

XRD：

- 标明辐射源和波长，例如 Cu K-alpha。
- x 轴为 `2theta`，y 轴说明 raw、background-subtracted 或 normalized intensity。
- 对可确认物相标注 hkl 和参考卡片来源；不能确认时写候选相和可信度。
- 记录背景扣除、平滑、峰搜索、晶粒尺寸或晶格参数计算方法。

FTIR/IR：

- x 轴为 wavenumber，单位 `cm^-1`，按领域习惯可从高到低显示。
- y 轴说明 absorbance、transmittance 或 normalized intensity。
- 标注主要吸收带和归属；不确定归属进入替代解释。

UV-Vis：

- x 轴为 wavelength (`nm`) 或 energy (`eV`)；若进行了换算，表格中保留原始单位和换算值。
- y 轴说明 absorbance、transmittance、reflectance 或 processed signal。
- 标注主要 optical features；threshold edge、Tauc、derivative、Kubelka-Munk 等分析必须写清模型和参数。
- 对 band gap、跃迁类型、缺陷态或膜厚效应的解释必须给出可信度和文献/项目依据。

XPS：

- x 轴为 binding energy，单位 `eV`，按 XPS 习惯可从高到低显示。
- 必须记录 binding-energy calibration 或 charge correction 的用户确认信息，例如参考峰、能量位移和确认来源。
- y 轴说明 counts、normalized intensity 或 background-subtracted intensity。
- 标注主要 peak/region；化学态、价态、组分比例、spin-orbit 约束和灵敏度因子不能由简单自动检峰直接推出。
- 若有 peak fitting，报告中必须写明背景模型、峰形、约束、参考依据和可信度。

Electrochemistry：

- x 轴为 potential (`V`/`mV`)、reviewed converted potential (`V vs target scale`)、reviewed iR-corrected potential (`V`) 或 time (`s`)；y 轴为 current 或 current density，并明确单位。
- 必须记录 measurement mode、current unit、electrode/electrolyte/reference-electrode/protocol context 和用户确认来源。
- 若使用 current density，必须记录电极面积及其 review 来源。
- 标注 peak-like/threshold/current-summary feature；过电位、Tafel slope、电容、容量、稳定性、倍率或机制解释不能由简单自动 feature 直接推出。
- EIS、Tafel、GCD 容量/电容等模型化分析必须写明协议、公式、参数、归一化方式、参考电极校正和可信度；reviewed potential conversion 和 reviewed iR drop correction 只能作为坐标换算/校正记录，不能替代这些模型化分析。

Thermal analysis：

- x 轴为 temperature，单位 `C` 或 `K`；若内部换算为摄氏度，报告中保留原始单位和换算说明。
- y 轴应明确是 mass、mass percent、heat flow、DTG signal 或 processed signal，并标明单位。
- 必须记录 measurement mode、temperature program、atmosphere、sample mass、baseline/reference context 和用户确认来源。
- TGA 可标注 mass-loss threshold 和 DTG-like extrema；DSC/DTG 可标注 heat-flow 或 derivative event，但这些只作为筛查事件。
- Tg、Tm、Tc、分解机理、反应动力学、成分比例和热稳定性排序必须有协议、基线模型、重复性、参考文献或用户确认，不应由简单自动 feature 直接推出。

SEM/TEM/光学显微镜：

- 必须保留原图路径和处理图路径。
- 报告中展示含 scale bar 的版本。
- 记录仪器模式、加速电压、探测器、样品制备、拍摄区域和用户描述。
- 若 EA 对图像内容判断不可靠，应明确采用用户描述作为主证据，并把不确定项放在追问中。

## 6. 报告结构

报告使用 Markdown，顶部保留 YAML frontmatter：

```yaml
---
report_id: rpt-lm-mos2-20260630-001
project_id: prj-lm-mos2
sample_ids: [s12]
raw_data_ids: [raw-lm-mos2-20260630-014-a1b2c3d4]
method: raman
result_ids: [res-lm-mos2-raman-20260630-001]
figure_ids: [fig-lm-mos2-raman-20260630-003]
review_status: draft
created_at: 2026-06-30
---
```

正文结构：

1. 摘要
2. 报告 ID 信息
3. 样品与原始数据
4. 原始数据处理过程
5. 图片与原图链接
6. 数据分析
7. 可能结论与可信度
8. 限制、替代解释和待确认问题
9. References
10. Provenance

图片部分应同时包含嵌入图和原图链接：

```markdown
![Raman spectrum](/absolute/path/to/fig-lm-mos2-raman-20260630-003.png)

原图文件：[fig-lm-mos2-raman-20260630-003.png](/absolute/path/to/fig-lm-mos2-raman-20260630-003.png)
```

## 7. 可信度表达

EA 报告中的推论使用四级可信度：

- 高：数据质量好，处理稳定，重复或独立证据支持，并与项目背景或文献一致。
- 中：数据直接支持该解释，但重复数、对照、单一表征或文献支撑仍有限。
- 低：解释与观察相容，但存在明显替代解释或缺少关键验证。
- 不足：目前只能作为待验证假设，不写成结论。

推荐写法：

```text
推论 A：样品可能存在应变或层数变化。可信度：中。
依据：E/A 峰位差和峰强变化支持该解释，但当前缺少 AFM 或 PL 独立验证。
替代解释：局部掺杂、温升或基底效应也可能造成相似变化。
下一步：建议补充 PL 或 AFM 对同一区域验证。
```

## 8. 引用格式

正文引用统一使用数字编号：

```text
Raman 峰位变化可能与层数、应变或掺杂有关[1][2]。
```

引用编号必须出现在正文中实际使用该文献支撑的位置，并与文末 `References` 的序号一一对应。不能只在文末列 reference，而正文不标注引用来源。若一句话综合了多个文献来源，应在该句或该段对应位置标出多个编号。

报告末尾使用：

```text
## References

[1] Author A, Author B. Title. Journal volume, pages (year). DOI: https://doi.org/xxxxx | Local: /absolute/path/to/paper.pdf | Web: https://...
[2] Author C. Title. arXiv (year). DOI: N/A | Local: zotero://select/items/ITEMKEY | Web: https://arxiv.org/abs/...
```

当 EA 在普通对话中引用本地或网络文献，也使用同样的 `[1]` 编号和文末 References。若只引用项目内部记录，可把来源写成：

```text
[3] EA project record. Experiment exp-20260630-002, sample s12. Local: /absolute/path/to/experiments/...
```

## 9. v0.2 最小实现

v0.2 建议先完成：

- 图片 ID、报告 ID、result ID、raw data ID 的生成规则。
- `figures/index.yml` 和 `reports/index.yml`。
- Markdown 报告模板。
- Matplotlib 默认样式和 footer 标注。
- Raman、PL、XRD、FTIR、UV-Vis、XPS、electrochemistry、thermal analysis 报告的第一版完整模板。
- 对话回答中的 reference 输出约定。

## 10. 外部依据

[1] Nature Portfolio. Formatting guide. Web: https://www.nature.com/nature/for-authors/formatting-guide  
[2] Springer Nature. Artwork submission instructions. Web: https://support.springernature.com/en/support/solutions/articles/6000083109-artwork-submission-instructions  
[3] Nature Portfolio. Image integrity and standards. Web: https://www.nature.com/nature-portfolio/editorial-policies/image-integrity  
[4] Nature Portfolio. Research figure guide. Web: https://research-figure-guide.nature.com/  
