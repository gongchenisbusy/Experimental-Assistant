# EA Implementation Spec TODO

> 版本：v0.1-implementation-prep-draft  
> 日期：2026-06-01  
> 状态：待办清单，不是正式全景地图正文  
> 用途：记录在正式搭建 EA v0.1 前需要补齐的工程规格，来源包括外部 agent 修改意见和当前设计复核。

---

## 1. 定位

这份文件是 `EA_AGENT_TEAM_BRIEF.md`、`EA_PRODUCT_CHARTER.md`、`EA_ARCHITECTURE_MAP.md`、`EA_TEST_PROTOCOL.md`、`EA_AGENT_TEAM_PROTOCOL.md` 之后的实现准备清单。

它不直接修改全景地图，而是列出进入实现前应补充的更细规格。

目标是避免 agent team 在搭建时遇到这些问题：

- schema 不够具体，导致各模块输出不一致。
- 用户审核状态不清晰，导致未确认内容进入正式记忆。
- raw 数据导入规则不完整，导致重复文件、改名文件或 hash 记录混乱。
- Raman v0.1 范围过宽，导致实现失控。
- EA 建议和用户决策只靠 prompt 区分，缺少数据层隔离。
- 知识库和阶段冻结在 v0.1 中过度展开，挤占核心闭环实现精力。

---

## 2. 总体采纳判断

外部 agent 提出的修改意见总体合理。

建议采纳的方向：

- 补齐核心 schema。
- 补齐用户审核状态机。
- 补齐 raw 文件导入规则。
- 收窄 Raman v0.1 scope。
- 在数据层强制区分 suggestion、decision log、project progress。
- 将完整阶段冻结能力后移，v0.1 只做设计预留或轻量 manifest。
- 将知识库自动同步策略后移，v0.1 先做目录、条目和本地笔记。

需要微调的方向：

- `memory/provenance` 不能完全放到最后补。它们是 EA 的可信度基础，至少 schema 和最小写入接口应在早期设计。
- 阶段冻结可以后置，但 `freezes/` 目录和 manifest 草案可保留。

---

## 3. 优先级定义

| 优先级 | 含义 |
|---|---|
| P0 | v0.1 实现前必须补齐，否则 agent team 容易做错 |
| P1 | v0.1 建议补齐，可降低实现风险 |
| P2 | 后续版本或 v0.1 预留，不阻塞核心闭环 |

---

## 4. 待补规格一览

| 文件 | 优先级 | 目的 |
|---|---|---|
| `EA_SCHEMA_SPEC.md` | P0 | 定义核心实体字段、ID、存储格式和示例 |
| `EA_REVIEW_STATE_MACHINE.md` | P0 | 定义用户审核状态、转换、确认判定和版本记录 |
| `EA_RAW_IMPORT_SPEC.md` | P0 | 定义 raw 文件导入、hash、去重、更名和只读策略 |
| `EA_RAMAN_V0_1_SPEC.md` | P0 | 收窄 Raman v0.1 文件格式、参数、输出和人工介入边界 |
| `EA_MEMORY_BOUNDARY_SPEC.md` | P0 | 在数据层区分 suggestion、decision、progress、confirmed finding |
| `EA_PROVENANCE_MINIMUM_SPEC.md` | P0 | 定义 v0.1 最小 provenance 要求 |
| `EA_KNOWLEDGE_BASE_V0_1_SPEC.md` | P1 | 定义 v0.1 知识库目录、文献条目、全文、摘要和笔记 |
| `EA_STAGE_FREEZE_SPEC.md` | P2 | 将阶段冻结定义为后续增强或 v0.1 轻量预留 |
| `EA_IMPLEMENTATION_SEQUENCE.md` | P1 | 给 agent team 排实现顺序和验收门槛 |

---

## 5. P0: `EA_SCHEMA_SPEC.md`

需要定义的对象：

- `Project`
- `ProjectRuleCard`
- `ExperimentRecord`
- `SampleRecord`
- `CharacterizationFile`
- `RamanProcessingResult`
- `ReportRecord`
- `ProgressEvent`
- `SuggestionRecord`
- `DecisionLogEntry`
- `ProvenanceEntry`
- `ReviewRecord`
- `KnowledgeItem`
- `OpenItem`

每个对象至少定义：

- 文件位置。
- 文件格式，建议 YAML frontmatter + Markdown body，或 JSON/YAML。
- ID 规则。
- 必填字段。
- 可选字段。
- 与其他对象的引用关系。
- 示例记录。
- v0.1 是否必须实现。

重点：

- schema 要足够具体，agent team 可以直接据此写脚本和测试。
- 不要把 MoS2 test 样本字段写成通用必填字段。

---

## 6. P0: `EA_REVIEW_STATE_MACHINE.md`

需要定义：

```text
working_draft
→ needs_user_review
→ user_confirmed | user_edited | user_rejected | deferred
→ saved | archived
```

必须覆盖：

- 实验日志结构化审核。
- 项目规则卡关键规则审核。
- Raman 数据列审核。
- Raman 参数审核。
- 科学解释审核。
- 记忆写入审核。
- 阶段冻结审核。

需要明确：

- 什么文本算用户确认，例如“可以，保存”“没问题”“可以的”。
- 用户指出错误后如何回到编辑状态。
- 用户修改内容如何覆盖 EA 原输出。
- 审核记录如何保存。
- 是否需要版本号。
- 未确认草稿不能进入正式记录、project progress 或 confirmed memory。

---

## 7. P0: `EA_RAW_IMPORT_SPEC.md`

需要定义：

- raw 文件导入流程。
- 支持的来源路径类型。
- 导入后项目内路径规则。
- 文件 hash 算法，建议 SHA-256。
- 文件大小、mtime、原始路径记录。
- 重复导入处理。
- 文件更名后的关联方式。
- hash 冲突处理。
- 只读保护策略。
- raw 与 processed 的边界。

建议规则：

- 相同 hash 的文件不重复复制，只新增 import alias 或 source reference。
- 文件名变化不改变 raw 数据身份。
- processed 输出永远不能写回 `raw/`。
- hash 冲突极低概率，但如果发生，应同时比较 size、mtime、文件头和原始路径，并标记人工审核。

---

## 8. P0: `EA_RAMAN_V0_1_SPEC.md`

v0.1 Raman scope 建议收窄为：

- 文件格式：CSV、TXT、XLSX。
- 必须支持用户确认 Raman shift 列和 intensity 列。
- 必须记录单位；缺失单位时标记 unknown 并请求确认。
- 必须提取可得仪器元数据，例如激光波长、功率、积分时间、物镜倍数。
- 必须输出图谱、峰表、processed CSV、metadata、中文报告。

需要定义：

- 默认读取策略。
- 表头识别策略。
- 数据列候选识别。
- 何时必须用户手工介入。
- 默认处理参数。
- 可选 baseline correction、smoothing、normalization 的确认方式。
- peak detection 默认方法。
- 失败和 warning 处理。

建议：

- v0.1 默认不要做过于激进的数据处理。
- 如果 baseline/smoothing/normalization 被启用，必须记录参数并在报告中说明。
- 解析失败、列不明确、单位缺失、元数据缺失时，必须请求用户确认或在报告中标记。

---

## 9. P0: `EA_MEMORY_BOUNDARY_SPEC.md`

该规格用于把“EA 建议”和“用户决策”从数据层强制隔离。

需要定义并分开存储：

- `SuggestionRecord`
- `DecisionLogEntry`
- `ProgressEvent`
- `ConfirmedFinding`
- `OpenQuestion`
- `FailedAttempt`

核心规则：

- EA 生成的下一步建议只能进入 `suggestions/`。
- `accepted` 或 `modified` 的 suggestion 也不能自动进入 `decision-log.md`。
- 只有用户明确表达“我决定/计划/采用/下一步做……”时，才能写入 decision log。
- 只有用户明确表示已完成某实验、表征或数据提交时，才能写入 progress event。
- `hypothesis` 不能进入 confirmed findings。

Suggestion 状态继续使用简单枚举：

```text
draft
accepted
modified
rejected
```

---

## 10. P0: `EA_PROVENANCE_MINIMUM_SPEC.md`

需要定义 v0.1 最小 provenance，而不是等最后补。

每个重要 workflow 至少记录：

- workflow id。
- skill name。
- skill version。
- input records。
- input files。
- output files。
- parameters。
- scripts 或 commands。
- warnings。
- review refs。
- created_at。

必须覆盖：

- 项目初始化。
- 实验日志保存。
- raw 文件导入。
- Raman 数据处理。
- 报告生成。
- memory 写入。

---

## 11. P1: `EA_KNOWLEDGE_BASE_V0_1_SPEC.md`

建议 v0.1 只做基础知识库能力：

- 初始化时创建 `knowledge/global/` 和 `knowledge/project/`。
- 保存文献条目。
- 保存 PDF/HTML 全文。
- 保存摘要、链接、笔记。
- 标记是否与当前项目相关。

暂缓：

- 自动同步复杂策略。
- 不同步标签完整机制。
- 恢复同步机制。
- 自动下载全文。
- 大规模 RAG。

保留设计方向：

- 全局知识库服务跨项目复用。
- 项目知识库服务当前项目溯源和解释。
- 用户明确“不需要同步”的内容必须尊重。

---

## 12. P2: `EA_STAGE_FREEZE_SPEC.md`

当前全景地图中已经设计了阶段冻结，但外部意见认为 v0.1 可暂缓。

建议调整为：

- v0.1 保留 `freezes/` 目录。
- v0.1 可以生成轻量 freeze manifest 草稿。
- v0.1 不强制实现完整恢复、校验、快照管理。
- 完整阶段冻结作为后续版本增强。

如果保留 v0.1 轻量能力，至少记录：

- freeze id。
- freeze reason。
- user confirmation。
- included record refs。
- key file hashes。
- snapshot notes。

---

## 13. P1: `EA_IMPLEMENTATION_SEQUENCE.md`

建议实现顺序：

1. 核心 schema 和目录结构。
2. 项目初始化与项目规则卡。
3. 实验日志结构化、审核和保存。
4. raw 导入和最小 provenance。
5. Raman 文件读取、列确认、参数确认。
6. Raman 处理、图谱、峰表、metadata。
7. 中文分析报告。
8. project memory、progress event、suggestion boundary。
9. knowledge base 基础条目。
10. 阶段冻结轻量预留。
11. 用户模拟测试。

关键调整：

- `memory/provenance` 不能完全最后补，至少 schema 和最小写入接口要前置。
- `freeze` 和复杂知识库同步可以后置。

---

## 14. 建议的下一步

建议下一步先写三份 P0 规格：

1. `EA_SCHEMA_SPEC.md`
2. `EA_REVIEW_STATE_MACHINE.md`
3. `EA_RAMAN_V0_1_SPEC.md`

然后再补：

4. `EA_RAW_IMPORT_SPEC.md`
5. `EA_MEMORY_BOUNDARY_SPEC.md`
6. `EA_PROVENANCE_MINIMUM_SPEC.md`

这些完成后，agent team 就可以进入更可控的 v0.1 实装阶段。

---

## 15. 当前完成状态

已完成并整合进全景地图的 P0 规格：

- `EA_SCHEMA_SPEC.md`
- `EA_REVIEW_STATE_MACHINE.md`
- `EA_RAW_IMPORT_SPEC.md`
- `EA_RAMAN_V0_1_SPEC.md`
- `EA_MEMORY_BOUNDARY_SPEC.md`
- `EA_PROVENANCE_MINIMUM_SPEC.md`

已更新的全景地图文档：

- `EA_AGENT_TEAM_BRIEF.md`
- `EA_PRODUCT_CHARTER.md`
- `EA_ARCHITECTURE_MAP.md`
- `EA_TEST_PROTOCOL.md`
- `EA_AGENT_TEAM_PROTOCOL.md`

仍作为后续可选补充：

- `EA_KNOWLEDGE_BASE_V0_1_SPEC.md`
- `EA_STAGE_FREEZE_SPEC.md`
- `EA_IMPLEMENTATION_SEQUENCE.md`
