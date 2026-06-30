# EA 项目规则卡模板

> 用途：每个 EA 项目初始化后生成一份项目规则卡，作为 EA 长期处理实验记录、样品、数据、报告、知识库和记忆的规则参考。  
> 状态：模板草案。正式项目中的规则卡应由 EA 与用户沟通确认后生成。  
> 重要边界：项目规则卡记录项目工作规则，不存放未经审核的科学结论。

---

## 1. 项目基本信息

```yaml
project_id:
project_name:
created_at:
updated_at:
rule_card_version:
default_language: zh
status: draft / user_confirmed / needs_update
```

| 字段 | 内容 | 确认状态 | 备注 |
|---|---|---|---|
| 研究方向 |  | draft / confirmed |  |
| 材料体系 |  | draft / confirmed |  |
| 实验类型 |  | draft / confirmed |  |
| 当前项目阶段 |  | draft / confirmed |  |

关键规则确认方式：

```yaml
key_rules_require_itemized_confirmation: true
allow_single_sentence_bulk_confirmation_for_key_rules: false
```

---

## 2. 用户自然语言项目描述

保留用户原始描述，便于后续追溯 EA 对项目的理解。

```text

```

---

## 3. EA 整理后的项目理解

```text

```

不确定或待确认内容：

| 问题 | 为什么需要确认 | 状态 |
|---|---|---|
|  |  | open / resolved |

---

## 4. 样品编号规则

### 4.1 编号规则说明

```text

```

### 4.2 编号字段定义

| 字段 | 含义 | 示例 | 是否必需 | 备注 |
|---|---|---|---|---|
|  |  |  | yes/no |  |

### 4.3 编号示例

```text

```

规则确认状态：

```yaml
status: draft / user_confirmed / needs_revision
confirmed_at:
confirmed_by:
```

---

## 5. 样品评价标准

### 5.1 当前标准

```text

```

### 5.2 标准来源

| 来源类型 | 来源 | 相关性 | 确认状态 |
|---|---|---|---|
| user / literature / project_data |  |  | draft / confirmed |

### 5.3 使用边界

```text

```

---

## 6. 常见表征手段

EA 应根据项目初始信息和文献资料生成此表，用户可随项目进展修改。

| 表征手段 | 对项目研究的作用 | 适用阶段/问题 | 推荐优先级 | 当前 EA 是否支持分析 | 备注 |
|---|---|---|---|---|---|
|  |  |  | high/medium/low | yes/no/partial |  |

规则：

- 常见表征列表用于帮助用户了解可能选择，不记录“用户已选择/暂不考虑/后续可能使用”等状态。
- 具体表征手段是否执行，由用户后续明确提出或通过项目进度事件体现。

---

## 7. 默认数据处理偏好

| 数据类型 | 默认处理流程 | 必须用户确认的参数 | 备注 |
|---|---|---|---|
| Raman |  | x/y 列、单位、预处理参数、峰识别参数 |  |

---

## 8. 实验日志结构化审核规则

```yaml
experiment_log_requires_user_confirmation_before_save: true
allow_unconfirmed_formal_experiment_record: false
allow_temporary_working_draft: true
```

规则：

- 用户每次提交自然语言实验记录后，EA 必须展示结构化字段。
- 如有不理解或缺失信息，EA 应先追问用户。
- 用户确认后，EA 才能正式保存实验日志。
- 用户指出字段有误时，EA 必须修改后再次确认。

---

## 9. 报告规则

```yaml
default_report_language: zh
default_report_audience: self
include_next_step_suggestions_by_default: false
default_include_sources_for_history_queries: true
```

报告默认要求：

- 清晰、完整、可追溯。
- 区分观察、数据处理结果、解释、假设和用户确认结论。
- 默认不包含下一步实验建议。
- 回答历史查询时默认附带简洁来源。

---

## 10. 下一步建议与项目决策边界

```yaml
next_step_suggestions_have_separate_review_status: true
ea_suggestions_can_be_written_directly_to_decision_log: false
project_progress_requires_user_explicit_confirmation: true
project_progress_uses_event_records_not_complex_status_machine: true
```

规则：

- EA 的下一步实验建议不能直接写入项目决策。
- 用户明确采纳、修改或描述自己的下一步计划后，相关内容才可以进入 decision log。
- 用户明确表示已完成实验、表征或数据提交后，相关内容才可以进入 project progress。
- EA 建议应保留为草稿建议、待验证假设或 decision candidate，直到用户确认。

下一步建议审核状态：

| 状态 | 含义 |
|---|---|
| `draft` | EA 生成的建议，用户尚未确认 |
| `accepted` | 用户明确表示采纳该建议或计划按该方向执行 |
| `modified` | 用户基于 EA 建议做了修改后形成自己的计划 |
| `rejected` | 用户明确拒绝该建议 |

---

## 11. 知识库策略

```yaml
knowledge_base_mode: global_and_project
create_knowledge_base_directories_at_project_init: true
store_fulltext_when_available: true
store_metadata_summary_links_notes: true
allow_auto_sync_between_global_and_project: true
respect_user_no_sync_requests: true
restore_sync_only_on_user_request: true
```

| 知识库类型 | 用途 | 存储内容 |
|---|---|---|
| 全局知识库 | 跨项目复用 | 通用科学知识、表征方法、数据处理方法、通用文献笔记 |
| 项目知识库 | 当前项目溯源与解释 | 项目相关文献、全文、摘要、链接、笔记、项目特定标准 |

不同步内容：

| 内容 | 不同步原因 | 用户确认时间 | 是否允许恢复同步 | 恢复同步时间 |
|---|---|---|---|---|
|  |  |  | only_on_user_request |  |

---

## 12. 原始文件管理策略

```yaml
raw_file_policy: controlled_readonly_copy
record_original_path: true
record_file_hash: true
processed_outputs_directory: processed/
```

规则：

- 原始数据复制到项目 `raw/` 目录作为受控只读副本。
- 处理结果写入 `processed/`。
- provenance 记录原始路径、项目内路径、hash、导入时间和导入方式。

---

## 13. 待补充信息表展示规则

```yaml
show_full_open_items_by_default: false
show_on_user_request: true
show_relevant_blockers_when_needed: true
```

规则：

- 用户主动询问时展示待补充信息表。
- 当前问题受缺失信息影响时，只提示相关缺失项。
- 避免在普通回答中加入冗余待办内容。

---

## 14. 论文素材池组织

论文素材池按以下维度组织：

- 结果图。
- 实验条件。
- 关键结论。
- 失败路径。
- 可引用表述。

---

## 15. 科学解释 reviewer 候选规则

> 状态：候选设计，尚未确认是否进入 v0.1。

候选证据等级：

| 证据等级 | 含义 |
|---|---|
| `observation` | 用户观察或仪器/图像中直接看到的现象 |
| `processed_result` | 脚本处理得到的峰位、图表、峰表、统计结果等 |
| `literature_supported` | 有本地或公开文献支持的解释 |
| `hypothesis` | 基于当前证据提出但尚未验证的假设 |
| `user_confirmed` | 用户明确确认可写入项目记忆的结论 |

规则：

- reviewer skill 不生成新结论，只检查解释是否越界。
- `hypothesis` 不能写入 confirmed findings。
- `user_confirmed` 必须来自用户审核。

---

## 16. 阶段性冻结规则

```yaml
support_stage_freeze: true
stage_freeze_requires_user_confirmation: true
ea_can_suggest_stage_freeze: true
user_can_request_stage_freeze: true
ea_should_not_suggest_stage_freeze_frequently: true
stage_freeze_strategy: manifest_hash_plus_key_text_snapshots
```

冻结快照可包含：

- 项目规则卡版本。
- 已确认实验记录索引。
- 已确认样品列表。
- 已确认报告和处理结果。
- confirmed findings。
- open questions。
- failed attempts。
- decision log。
- 论文素材池当前版本。
- provenance 索引。

EA 可主动建议冻结的典型节点：

- 用户确认阶段性研究成果。
- 项目路线需要明显转向、重启或归档失败路径。
- 完成阶段报告、阶段复盘或论文素材整理后。

冻结策略：

- 生成冻结 manifest 和 hash 指纹。
- 复制关键文本状态文件。
- 大型原始数据和处理结果通过不可变路径和 hash 指向，不默认重复完整复制。
- 用户需要时，可基于 manifest 定位、校验和恢复冻结时的项目状态。

冻结记录：

| 冻结版本 | 冻结时间 | 冻结原因 | 用户确认状态 | manifest 路径 | 快照路径 |
|---|---|---|---|---|---|
|  |  |  | draft / confirmed |  |  |

---

## 17. 项目进度事件规则

项目进度使用事件记录，不使用复杂状态机。

最小字段：

| 字段 | 含义 |
|---|---|
| `progress_id` | 进度事件唯一 ID |
| `recorded_at` | EA 记录该事件的时间 |
| `occurred_at` | 用户描述的实际发生时间，未知则留空 |
| `user_original_text` | 用户原始表述 |
| `ea_summary` | EA 整理后的简洁进度描述 |
| `event_type` | experiment / characterization / data_upload / analysis / report / decision |
| `related_experiments` | 关联实验编号 |
| `related_samples` | 关联样品编号 |
| `related_files` | 关联文件或数据 |
| `source_refs` | 可追溯来源 |
| `uncertainties` | 不确定或待补充信息 |

---

## 18. 来源展示规则

```yaml
history_queries_include_sources_by_default: true
source_display_style: short_parentheses
expand_sources_on_user_request: true
prefer_user_friendly_source_labels: true
source_labels_must_resolve_to_internal_refs: true
```

来源可指向：

- 实验记录。
- 样品记录。
- 原始数据。
- 处理结果。
- 报告。
- 项目记忆。
- 知识库条目。
- provenance 记录。

规则：

- 简短来源优先显示用户友好的实验编号、样品编号、报告标题或数据名称。
- EA 内部必须保留来源标签到真实文件路径、记录 ID 或 provenance ID 的映射。
- 用户要求文件位置、打开文件或提取内容时，EA 必须能准确定位。

格式示例：

```text
该样品目前更适合优先表征（来源：exp-20260527-001）。
```

---

## 19. 规则变更记录

| 时间 | 变更内容 | 原因 | 用户确认状态 |
|---|---|---|---|
|  |  |  | draft / confirmed |
