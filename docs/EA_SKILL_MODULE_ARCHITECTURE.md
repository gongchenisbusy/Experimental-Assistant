# EA 模块化 Skill 架构设计

> 状态：v0.2 设计草案  
> 日期：2026-06-30  
> 用途：定义 EA 作为父级实验助手 skill 时，子 skill 如何接入、单独调用、复用项目记忆并保持统一输出。

## 1. 设计目标

EA 不应被做成一个巨大的单体 skill。更合理的形态是：

```text
EA Orchestrator
├── project / memory / provenance core
├── add-skills governance
├── literature and knowledge skills
├── characterization analysis skills
├── plotting and report skills
└── domain-specific extension skills
```

父级 EA 负责项目上下文、样品/原始数据/报告/记忆/溯源结构，以及跨 skill 的调度。子 skill 负责明确的专业任务。子 skill 可以在 EA 项目内读取长期项目记忆，也可以被用户在一次独立任务中单独调用。

## 2. 子 Skill 推荐目录

### 2.1 项目与记忆核心

- `project-init`: 新项目初始化、项目规则卡、样品编号规则、默认报告语言。
- `experiment-log`: 实验日志结构化、样品与工艺条件抽取、开放问题记录。
- `sample-registry`: 样品、批次、测点和实验条件索引。
- `raw-data-import`: 原始文件受控导入、哈希、元数据、只读副本。
- `provenance-audit`: 引用断链、raw hash、处理参数、报告引用和 review 状态检查。
- `memory-query`: 项目记忆查询、去重、状态变更和证据等级管理。

### 2.2 文献与知识

- `local-literature-library`: 项目文献库部署、检索、下载、缓存和同步。
- `literature-search`: 针对具体问题的文献检索、筛选和引用。
- `paper-reader`: 论文全文阅读、图表摘录、方法和结论抽取。
- `citation-manager`: 报告和回答中的引用编号、参考文献条目和链接管理。

### 2.3 绘图与报告

- `scientific-plotting`: 统一绘图风格、图片 ID、报告 ID、导出格式和索引。
- `analysis-report`: 统一数据报告模板、结论可信度、reference 和 provenance。
- `material-assignment-library`: Raman、PL、XRD 等表征报告可复用的材料特征峰/能量/衍射规则库；规则只提供可追溯的候选解释，不替代文献和用户确认。
- `presentation-export`: 组会或阶段汇报材料生成。

### 2.4 材料表征数据分析

光谱类：

- `raman-analysis`
- `pl-analysis`
- `ftir-ir-analysis`
- `uv-vis-analysis`
- `ellipsometry-analysis`

衍射和散射类：

- `xrd-analysis`
- `gixrd-analysis`
- `saxs-waxs-analysis`

表面、成分和化学态：

- `xps-analysis`
- `ups-analysis`
- `eds-eels-analysis`
- `xrf-icp-analysis`
- `tof-sims-analysis`

显微与形貌：

- `sem-image-analysis`
- `tem-stem-image-analysis`
- `optical-microscopy-analysis`
- `afm-analysis`
- `profilometry-analysis`

电学、器件和电化学：

- `iv-cv-device-analysis`
- `hall-analysis`
- `fet-analysis`
- `eis-analysis`
- `cv-lsv-gcd-electrochem-analysis`

热学、力学和其他物性：

- `tga-dsc-analysis`
- `dma-mechanical-analysis`
- `nanoindentation-analysis`
- `magnetometry-analysis`

材料研究还常需要跨数据综合：

- `batch-comparison`: 多样品、多批次统计比较；v0.2 先提供 Raman/PL/XRD/FTIR/UV-Vis/XPS/electrochemistry 已确认条目的批处理协调和汇总，不替代每个表征方法的 review gates。
- `structure-property-linking`: 结构、成分、工艺和性能之间的证据化关联。
- `doe-analysis`: 实验设计、变量筛选和响应面分析。

这些列表不是一次性全部实现的 v0.2 目标，而是 EA 长期模块化架构的候选能力池。v0.2 只需要先建立规范和少数代表性 skill。

## 3. 子 Skill 接口契约

每个可进入 EA 的子 skill 应声明一个 manifest，例如：

```yaml
ea_skill:
  id: ea.raman-analysis
  version: 0.2.0
  category: characterization.spectrum
  method: raman
  input_artifacts:
    - raw_spectrum
    - sample_context
    - project_context
  output_artifacts:
    - processed_result
    - figure_record
    - report_section
    - provenance_record
    - memory_candidate
  review_gates:
    - confirm_method
    - confirm_processing_parameters
    - confirm_interpretation_before_memory_write
  required_indices:
    - raw/index.yml
    - reports/index.yml
    - figures/index.yml
    - provenance/index.yml
```

统一输入：

- `ProjectContext`: 项目目标、材料体系、规则卡、当前确认记忆。
- `InputArtifact[]`: 原始数据、图片、日志、文献、用户说明。
- `AnalysisIntent`: 用户这次想回答的问题。
- `ReviewState`: 已确认、已拒绝、待追问的内容。

统一输出按类别区分。表征分析类 skill 必须输出：

- `ProcessedResult`: 处理后数据、参数、版本、质量检查。
- `FigureRecord[]`: 图片文件、图片 ID、报告 ID、原始数据来源。
- `ReportSection`: 可嵌入报告的正文和表格。
- `MemoryCandidate[]`: 候选项目记忆，必须等待用户确认。
- `ProvenanceRecord`: 输入、输出、脚本、参数、时间和 review 关系。

非表征类 skill 不应被强行套入 Raman 式输出：

| 类别 | 必需输出 |
| --- | --- |
| `characterization.*` | `processed_result`, `figure_record`, `report_section`, `provenance_record`, `memory_candidate` |
| `literature.*` | `literature_status`, `reference_record`, `report_section`, `provenance_record` |
| `visualization.*` | `figure_record`, `report_section`, `provenance_record` |
| 其他 | `report_section`, `provenance_record` |

## 4. add-skills 子 Skill

`add-skills` 是 EA 的扩展治理模块，不只是复制一个新 skill 文件。它负责判断一个用户自定义 skill 是否能安全进入 EA 架构。

接入流程：

1. 读取新 skill 的 manifest、说明文档、示例输入和示例输出。
2. 判断它属于哪一类任务：文献、绘图、表征分析、报告、记忆、项目管理或其他。
3. 检查输入是否能映射到 EA 的 `ProjectContext`、`InputArtifact` 和 review 模型。
4. 检查输出是否包含 `ProcessedResult`、`FigureRecord`、`ReportSection`、`ProvenanceRecord` 等必要对象。
5. 用最小 fixture 做 dry run，确认不会写坏 raw、不会跳过必要确认、不会生成不可追踪报告。
6. 检查报告段落、图片、参考文献和 ID 是否符合 EA 标准。
7. 写入 `skill-registry/index.yml`，并记录版本、适用范围、限制和测试结果。

`add-skills` 应拒绝或要求修改以下 skill：

- 直接覆盖原始数据而不保留副本。
- 无法说明输入来源、处理参数或输出路径。
- 把模型推测直接写成项目确认结论。
- 生成无法链接到原始数据、报告或样品的图表。
- 引用文献但不提供 reference 条目或链接。
- 需要账号、网络或外部工具却没有清楚的用户确认流程。

## 5. 单独调用与项目内调用

子 skill 单独调用时，应至少输出临时报告和 provenance。若用户随后决定将结果纳入 EA 项目，EA 需要通过 `add-skills` 或导入流程补齐：

- 项目 ID
- 样品 ID
- raw data ID
- report ID
- figure ID
- review record
- provenance record

子 skill 在项目内调用时，可以读取项目记忆，但只能把新结论作为 `MemoryCandidate` 提交，不能绕过用户确认直接写入 confirmed memory。

## 6. v0.2 实施范围

v0.2 建议先实现以下最小架构能力：

- `skill-registry/index.yml` 的格式。
- `add-skills` 的静态检查和 dry-run 检查草案。
- 内置 manifest 目录，至少覆盖 `local-literature-library`、`scientific-figure`、`raman-analysis`、`pl-analysis`、`xrd-analysis`、`ftir-analysis`、`uv-vis-analysis`、`xps-analysis`、`electrochemistry-analysis`、`thermal-analysis` 和 `image-analysis`。
- `scientific-figure` 的统一绘图样式基础设施和 `analysis-report` 的输出契约。
- `material-assignment-library` 的首个 MoS2 Raman/PL/XRD 内置记录和查询命令。
- `raman-analysis`、`pl-analysis`、`xrd-analysis`、`ftir-analysis`、`uv-vis-analysis`、`xps-analysis` 和 `electrochemistry-analysis` 作为第一批可运行表征 workflow 样例。
- `local-literature-library` 作为项目初始化时的知识基础样例。

热分析和更复杂的显微/散射模块可先进入设计和接口测试，不必一次性完整实现。Electrochemistry 当前只覆盖 CV/LSV/chrono/GCD 风格表格数据的 review-gated first-pass workflow，EIS、Tafel、容量/电容和正式性能指标仍应由后续协议化模块实现。
