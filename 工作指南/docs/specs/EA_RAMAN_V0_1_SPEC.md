# EA Raman v0.1 Spec

> 版本：v0.1-p0-draft  
> 日期：2026-06-01  
> 优先级：P0  
> 用途：收窄 EA v0.1 Raman 分析范围，定义文件格式、确认节点、处理参数、输出和失败边界。  

---

## 1. v0.1 范围

v0.1 Raman 支持：

- CSV。
- TXT。
- XLSX。
- 单谱图或简单二维表格数据。
- 用户确认 Raman shift 列和 intensity 列。
- 基础绘图。
- 基础峰识别。
- 处理后 CSV。
- 峰表 CSV。
- metadata YAML/JSON。
- 中文分析报告。

v0.1 不保证：

- 所有仪器厂商私有格式。
- 批量 mapping 数据完整处理。
- 自动多谱图拆分。
- 复杂峰拟合。
- 自动判断材料层数或机制。
- 自动消除所有 cosmic ray。

---

## 2. 输入要求

用户至少需要提供：

- Raman 原始文件。
- 文件对应样品信息，或允许 EA 追问。

EA 应尝试提取：

- 原始文件名。
- 文件格式。
- 表头。
- 数据列。
- Raman shift 候选列。
- intensity 候选列。
- 单位。
- 仪器元数据。

---

## 3. 支持格式

| 格式 | v0.1 支持方式 |
|---|---|
| CSV | 必须支持 |
| TXT | 必须支持常见分隔符，如 tab、space、comma |
| XLSX | 必须支持第一个工作表或用户指定工作表 |
| 其他 | 标记 unsupported，进入 open item |

如果文件有多个 sheet 或多个数据块，EA 必须请求用户确认。

---

## 4. 列识别

EA 可以根据以下线索提出候选：

- 列名包含 Raman、shift、wavenumber、cm。
- 数值范围类似 Raman shift。
- 列名包含 intensity、counts、signal。
- 单调递增或递减的 x 列。

但最终必须用户确认：

```yaml
x_column:
y_column:
x_unit:
```

缺失单位时：

- 标记 `unknown`。
- 请求用户确认。
- 报告中说明单位不确定。

---

## 5. 仪器元数据

尽量提取：

```yaml
laser_wavelength:
laser_power:
integration_time:
objective:
grating:
accumulations:
instrument_model:
```

缺失时不编造。

metadata 中记录：

```yaml
missing_instrument_metadata: []
metadata_parse_confidence: high | medium | low
```

---

## 6. 参数确认

v0.1 默认参数建议：

```yaml
baseline_correction:
  enabled: false
smoothing:
  enabled: false
normalization:
  enabled: true
  method: max_intensity
peak_detection:
  method: scipy_find_peaks
  prominence: auto
  distance: auto
```

必须向用户展示并确认：

- 是否进行 baseline correction。
- 是否进行 smoothing。
- 是否进行 normalization。
- peak detection 方法和关键参数。

如果用户不懂参数，EA 可以给保守默认建议，但仍需用户确认。

---

## 7. 处理流程

```text
导入 raw 副本
→ 读取文件
→ 识别列和元数据
→ 用户确认列与单位
→ 展示参数
→ 用户确认参数
→ 执行处理
→ 绘图
→ 峰识别
→ 输出 processed data、peak table、metadata
→ 生成中文报告
→ 用户审核科学解释
```

---

## 8. 输出文件

推荐输出：

```text
processed/{sample_id}/raman/{result_id}/
├── raman_processed.csv
├── raman_peaks.csv
├── raman_plot.png
├── raman_metadata.yml
└── raman_summary.md
```

报告：

```text
reports/report-YYYYMMDD-NNN.md
```

---

## 9. Peak table 字段

```csv
peak_id,position_cm-1,intensity,height,prominence,width,method,notes
```

如果单位未知：

```csv
peak_id,position_unknown,intensity,height,prominence,width,method,notes
```

---

## 10. 图表规范

图表必须：

- 有标题。
- 有 x/y 轴标签。
- Raman shift 标注为 `cm^-1`，除非未知。
- 区分原始数据和处理后数据。
- 标注峰位时不遮挡主曲线。
- 使用克制、科研风格。
- 避免彩虹色和红绿对比。

---

## 11. 报告边界

报告可以写：

- 观察到的峰位。
- 峰强和峰形变化。
- 与常见 Raman 特征的一致性。
- 数据质量和限制。
- 可能解释。

报告不能写：

- “这证明了……”
- “可以确认机制……”
- “缺陷浓度已经确定……”
- 未提供依据的层数、相变、掺杂、应变强结论。

---

## 12. 人工介入条件

以下情况必须请求用户介入：

- 无法确定 x/y 列。
- 多个候选列置信度相近。
- 单位缺失或不明确。
- 文件包含多个 sheet 或多个谱图。
- 元数据与用户描述冲突。
- 数据异常，如大量非数值、空值、重复 x、大范围跳变。
- 参数选择可能显著影响结果。

---

## 13. Warning 规则

metadata 和报告中应记录 warning：

```yaml
warnings:
  - x_unit_unknown
  - instrument_metadata_missing
  - baseline_not_corrected
  - smoothing_applied
  - normalization_applied
  - peak_detection_needs_review
```

---

## 14. v0.1 验收

v0.1 Raman 通过标准：

- 能读取 CSV/TXT/XLSX。
- 能提出 x/y 列候选。
- 能请求用户确认列、单位和参数。
- 能生成 processed CSV。
- 能生成 peak table。
- 能生成 plot。
- 能生成 metadata。
- 能生成中文报告。
- 不修改 raw。
- 所有输出有 provenance。

