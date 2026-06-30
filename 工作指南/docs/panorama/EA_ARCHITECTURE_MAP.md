# EA Architecture Map

> 版本：v0.1-panorama-draft  
> 日期：2026-05-29  
> 用途：定义 EA 的本地架构、核心实体、目录结构、schema、workflow、skill 边界和审核节点。  

---

## 1. 架构总览

EA 是 agent-native skill 包。

推荐结构：

```text
EA Skill
├── EA Orchestrator
├── Sub-skills
│   ├── project_initialization
│   ├── experiment_log
│   ├── generic_data_preview
│   ├── raman_analysis
│   ├── report_generation
│   ├── project_memory
│   ├── knowledge_base
│   └── provenance
├── Deterministic scripts
│   ├── file importers
│   ├── data readers
│   ├── Raman processors
│   ├── plotting scripts
│   ├── peak detection scripts
│   └── metadata writers
├── Knowledge files
│   ├── scientific language rules
│   ├── Raman analysis guidance
│   ├── material-system notes
│   └── figure style guidance
└── Templates
    ├── project rule card
    ├── experiment record
    ├── review record
    ├── report
    └── provenance record
```

LLM 负责组织、解释和写作。确定性脚本负责数据读取、处理、绘图和元数据写入。

实现前 P0 规格：

- `EA_SCHEMA_SPEC.md`
- `EA_REVIEW_STATE_MACHINE.md`
- `EA_RAW_IMPORT_SPEC.md`
- `EA_RAMAN_V0_1_SPEC.md`
- `EA_MEMORY_BOUNDARY_SPEC.md`
- `EA_PROVENANCE_MINIMUM_SPEC.md`

这些规格是本架构地图的工程落地细则。实现时以这些 P0 文档为字段、状态和验收依据。

---

## 2. v0.1 本地项目结构

v0.1 一个 EA 工作目录对应一个科研项目。

推荐目录：

```text
ea-project/
├── EA_PROJECT.md
├── PROJECT_RULE_CARD.md
├── experiments/
├── samples/
├── raw/
├── processed/
├── reports/
├── memory/
├── provenance/
├── reviews/
├── knowledge/
│   ├── global/
│   └── project/
├── open-items/
├── suggestions/
├── progress/
└── freezes/
```

目录职责：

| 路径 | 职责 |
|---|---|
| `EA_PROJECT.md` | 项目总览、研究目标、当前阶段 |
| `PROJECT_RULE_CARD.md` | 项目规则卡 |
| `experiments/` | 用户确认后的结构化实验记录 |
| `samples/` | 样品索引和样品状态 |
| `raw/` | 原始数据受控只读副本 |
| `processed/` | 处理后数据、图谱、峰表、metadata |
| `reports/` | 分析报告、阶段报告 |
| `memory/` | 项目主线记忆 |
| `provenance/` | 溯源记录 |
| `reviews/` | 用户审核记录 |
| `knowledge/global/` | 跨项目复用知识库 |
| `knowledge/project/` | 当前项目知识库 |
| `open-items/` | 待补充信息表 |
| `suggestions/` | EA 建议草稿和审核状态 |
| `progress/` | 用户确认的项目进度事件 |
| `freezes/` | 阶段性冻结轻量 manifest 预留 |

项目初始化时，EA 直接创建合理目录结构并告知用户。用户可以后续要求修改。

---

## 3. 核心实体

| 实体 | 含义 | v0.1 |
|---|---|---|
| Project | 顶层科研项目 | 必做 |
| Project Rule Card | 项目规则卡 | 必做 |
| Experiment | 用户确认后的结构化实验记录 | 必做 |
| Sample | 物理样品或衬底样品 | 必做 |
| Material System | 材料体系，v0.1 为 MoS2 | 必做 |
| Process Condition | 温度、时间、气氛、流速、衬底等实验条件 | 必做 |
| Characterization File | Raman 等原始表征文件 | Raman 必做 |
| Data Processing Result | 图谱、峰表、处理后数据、metadata | Raman 必做 |
| Report | Markdown/HTML 分析报告 | 必做 |
| Project Memory | 研究主线和论文素材池 | 必做 |
| Review Decision | 用户确认、修改、拒绝、延后 | 必做 |
| Provenance Record | 输入、输出、参数、脚本、审核链条 | 必做 |
| Knowledge Item | 文献、资料、摘要、笔记、全文 | 必做 |
| Open Item | 待补充信息 | 必做 |
| Suggestion | EA 下一步建议 | 必做 |
| Progress Event | 用户确认的项目进度事件 | 必做 |
| Stage Freeze | 阶段快照 | 必做 |

---

## 4. 关键语义边界

### 4.1 Experiment

Experiment 是用户确认后的结构化实验记录。

不是：

- 原始聊天文本本身。
- 未确认草稿。
- EA 推测出的实验事实。

### 4.2 Sample

Sample 是可追踪的物理样品或衬底样品。

Sample ID 必须来自已确认编号规则，或经用户确认后生成。

### 4.3 Raw Data

Raw data 是原始表征文件的受控只读副本。

规则：

- 可以复制到 `raw/`。
- 可以 hash。
- 可以读取。
- 不能覆盖。
- 不能清洗后写回。

### 4.4 Processed Data

Processed data 是由脚本处理产生的输出。

必须写入 `processed/`，并附 metadata 和 provenance。

### 4.5 Observation / Result / Interpretation / Hypothesis / Confirmed Finding

| 类型 | 含义 | 能否进 confirmed findings |
|---|---|---|
| Observation | 用户或仪器直接观察 | 需用户确认 |
| Processed Result | 脚本处理得到的结果 | 需用户确认 |
| Interpretation | 基于结果和知识的解释 | 需用户确认 |
| Hypothesis | 待验证假设 | 不能直接进入 |
| Confirmed Finding | 用户确认的发现 | 可以 |

v0.1 不强制实现 reviewer 证据等级，但必须遵守这些边界。

### 4.6 EA Suggestion vs User Decision

EA suggestion 不是项目决策。

只有用户明确表达采纳、计划或决定后，才能写入 decision log。

---

## 5. 项目初始化 workflow

```text
用户自然语言描述项目
→ EA 提取研究方向、材料体系、实验类型
→ EA 追问缺失项
→ 用户确认项目初始信息
→ EA 创建目录结构
→ EA 创建 global/project 知识库目录
→ EA 生成项目规则卡草稿
→ EA 与用户逐项确认关键规则
→ EA 写入 PROJECT_RULE_CARD.md 和初始化 provenance
```

最低输入：

- 研究方向。
- 材料体系。
- 实验类型。

项目规则卡关键规则必须逐项确认。

---

## 6. 实验日志 workflow

```text
用户提交自然语言实验记录
→ EA 解析字段
→ EA 追问缺失或不确定字段
→ EA 展示结构化字段
→ 用户确认 / 修改 / 拒绝
→ EA 根据用户反馈修正
→ 用户明确确认
→ EA 保存正式实验记录
→ EA 写 review decision 和 provenance
```

用户确认可以是自然语言整体确认，例如：

- “可以，保存”
- “没问题”
- “可以的”

但 EA 必须先展示结构化字段。

未确认内容只能是临时工作草稿，不能进入正式实验记录、项目进度或 confirmed memory。

---

## 7. Raman workflow

```text
用户提交 Raman 文件和样品关联信息
→ EA 导入 raw 受控只读副本
→ EA 记录原始路径、项目内路径、hash、导入时间
→ EA 读取文件并识别表头、列名、单位、数值范围、元数据
→ EA 请求用户确认 Raman shift 列和 intensity 列
→ EA 展示处理参数并请求确认
→ 确定性脚本执行处理和绘图
→ 输出图谱、峰表、处理后数据、metadata
→ LLM 基于结构化结果生成中文分析报告
→ 用户审核科学解释和是否写入记忆
→ EA 写 review decision 和 provenance
```

Raman metadata 尽量提取：

- 激光波长。
- 功率。
- 积分时间。
- 物镜倍数。
- 数据列。
- 单位。
- 处理参数。

缺失或不确定时必须标记。

---

## 8. 报告生成 workflow

默认 Raman/原始数据分析报告包含：

1. 实验背景。
2. 样品与工艺条件。
3. 原始数据来源。
4. 数据列和处理参数。
5. Raman 图谱和峰表。
6. 主要观察结果。
7. 谨慎解释。
8. 不确定性和限制。
9. 溯源记录。

默认不包含下一步实验建议。

用户追问下一步时，EA 另行生成建议，并进入 suggestion 审核流。

---

## 9. Suggestion workflow

EA 下一步建议状态：

| 状态 | 含义 |
|---|---|
| `draft` | EA 生成，用户未确认 |
| `accepted` | 用户明确表示采纳或计划按该方向执行 |
| `modified` | 用户基于 EA 建议修改形成自己的计划 |
| `rejected` | 用户明确拒绝 |

重要规则：

- `accepted` 或 `modified` 不自动等于正式项目决策。
- 只有用户明确表达“我决定/计划/采用/下一步做……”后，才能写 decision log。
- EA 不能把建议写成 progress event。

---

## 10. Project memory

推荐结构：

```text
memory/
├── project-summary.md
├── confirmed-findings.md
├── open-questions.md
├── failed-attempts.md
├── material-system-notes.md
├── decision-log.md
└── paper-materials/
    ├── figures.md
    ├── experiment-conditions.md
    ├── key-findings.md
    ├── failed-paths.md
    └── quotable-statements.md
```

规则：

- `confirmed-findings.md` 只能写用户确认后的发现。
- `open-questions.md` 存放待验证假设。
- `failed-attempts.md` 存放失败实验和异常结果。
- `decision-log.md` 只存用户明确决策。
- 论文素材池必须保留来源链条。

---

## 11. Progress event schema

进度事件最小字段：

```yaml
progress_id:
recorded_at:
occurred_at:
user_original_text:
ea_summary:
event_type: experiment | characterization | data_upload | analysis | report | decision
related_experiments: []
related_samples: []
related_files: []
source_refs: []
uncertainties: []
```

项目进度不使用复杂状态机。

EA 通过事件记录回答用户“项目做到哪一步了”。

---

## 12. Review decision schema

```yaml
review_id:
target_type:
target_ref:
review_status: user_confirmed | user_edited | user_rejected | deferred
decision:
reviewed_at:
reviewed_by:
user_original_text:
notes:
```

强制 review 节点：

- 项目规则卡关键规则。
- 实验日志结构化字段。
- 样品编号规则。
- 样品评价标准。
- Raman 数据列。
- Raman 处理参数。
- 科学解释。
- 记忆写入。
- 阶段性冻结。

---

## 13. Provenance schema

```yaml
provenance_id:
workflow:
created_at:
skill_name:
skill_version:
inputs:
  raw_files: []
  records: []
outputs:
  files: []
parameters:
scripts:
  - path:
    version:
    hash:
review_refs: []
warnings: []
source_refs: []
```

每个重要输出必须有 provenance。

最小要求见 `EA_PROVENANCE_MINIMUM_SPEC.md`。

---

## 14. Knowledge base

项目初始化时创建：

```text
knowledge/
├── global/
│   ├── literature/
│   ├── methods/
│   └── notes/
└── project/
    ├── literature/
    ├── fulltext/
    ├── notes/
    └── relevance-index.md
```

规则：

- v0.1 初始化时创建全局知识库和项目知识库目录。
- v0.1 支持基础文献条目、全文、摘要、链接和笔记存储。
- 全局知识库用于跨项目复用，项目知识库用于当前项目溯源与解释。
- 自动同步、不同步标签完整机制和恢复同步机制作为后续版本增强，不作为 v0.1 完整实现要求。

---

## 15. Stage freeze

v0.1 阶段性冻结采用轻量预留策略：

```text
manifest + hash 指纹 + 关键文本状态文件副本
```

大型 raw 和 processed 文件不默认重复复制，用不可变路径和 hash 指向。v0.1 不强制实现完整恢复、校验和快照管理。

freeze manifest 至少记录：

```yaml
freeze_id:
created_at:
freeze_reason:
user_confirmation:
included_records:
file_paths:
file_hashes:
source_labels:
snapshot_notes:
```

EA 可在以下节点建议冻结：

- 用户确认阶段性成果。
- 项目路线需要明显转向、重启或归档失败路径。
- 完成阶段报告、阶段复盘或论文素材整理。

EA 不应频繁打扰用户。

完整阶段冻结、校验和恢复能力属于后续版本。

---

## 16. Source strategy

历史查询默认附带简短来源。

规则：

- 优先显示用户友好的实验编号、样品编号、报告标题或数据名称。
- 内部必须能解析到真实文件路径、记录 ID 或 provenance ID。
- 用户要求文件位置或打开文件时，EA 必须能定位。

示例：

```text
该样品目前更适合优先表征（来源：exp-20260527-001）。
```

---

## 17. v0.1 / future split

| 架构能力 | v0.1 | 后续 |
|---|---|---|
| 一个工作目录一个项目 | 必做 | 可扩展多项目 |
| 项目初始化与规则卡 | 必做 | 增强 |
| 实验日志逐次确认 | 必做 | 保留 |
| Raman 分析 | 必做 | 增强 |
| P0 工程规格 | 必做 | 持续细化 |
| 科学解释 reviewer 等级 | 不做 | 可加入 |
| 多表征 skill | 不做 | 可加入 |
| 多项目管理 | 不做 | 可加入 |
| 英文报告 | 不做 | 可加入 |
| 知识库自动同步完整机制 | 不做 | 可加入 |
| 完整阶段冻结恢复 | 不做，仅轻量预留 | 可加入 |
