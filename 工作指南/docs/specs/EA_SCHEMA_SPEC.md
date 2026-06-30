# EA Schema Spec

> 版本：v0.1-p0-draft  
> 日期：2026-06-01  
> 优先级：P0  
> 用途：定义 EA v0.1 核心实体、文件位置、字段、ID 和引用关系。  

---

## 1. 通用约定

v0.1 采用本地文件作为主要存储形态。

推荐格式：

- 人类可读记录：Markdown + YAML frontmatter。
- 机器索引与 metadata：YAML 或 JSON。
- 表格型结果：CSV。
- 图像：PNG，必要时另存 SVG/PDF 作为后续扩展。

通用字段：

```yaml
id:
schema_version: "0.1"
created_at:
updated_at:
status:
source_refs: []
provenance_refs: []
review_refs: []
```

通用状态原则：

- 未经用户确认的内容不得进入正式记录。
- 正式记录必须可追溯到用户输入、文件或 review decision。
- v0.1 不要求数据库。

---

## 2. ID 规则

推荐 ID 格式：

| 对象 | 格式 |
|---|---|
| Project | `project-YYYYMMDD-slug` |
| ExperimentRecord | `exp-YYYYMMDD-NNN` |
| SampleRecord | 使用项目规则卡中的样品编号 |
| CharacterizationFile | `char-YYYYMMDD-NNN` |
| RamanProcessingResult | `raman-result-YYYYMMDD-NNN` |
| ReportRecord | `report-YYYYMMDD-NNN` |
| ReviewRecord | `review-YYYYMMDD-NNN` |
| ProvenanceEntry | `prov-YYYYMMDD-NNN` |
| ProgressEvent | `progress-YYYYMMDD-NNN` |
| SuggestionRecord | `suggestion-YYYYMMDD-NNN` |
| DecisionLogEntry | `decision-YYYYMMDD-NNN` |
| KnowledgeItem | `knowledge-YYYYMMDD-NNN` |
| OpenItem | `openitem-YYYYMMDD-NNN` |

`NNN` 为项目内同日递增编号。

---

## 3. Project

文件位置：

```text
EA_PROJECT.md
```

必填字段：

```yaml
project_id:
project_name:
research_direction:
material_system:
experiment_type:
created_at:
default_language: zh
workspace_mode: single_project
rule_card_ref:
knowledge_global_dir: knowledge/global/
knowledge_project_dir: knowledge/project/
```

可选字段：

```yaml
current_stage:
description:
owner:
notes:
```

v0.1：

- 必须实现。
- 一个 EA 工作目录只对应一个 Project。

---

## 4. ProjectRuleCard

文件位置：

```text
PROJECT_RULE_CARD.md
```

必填字段：

```yaml
rule_card_id:
project_id:
version:
status: draft | user_confirmed | needs_update
research_direction:
material_system:
experiment_type:
sample_id_rule_ref:
sample_quality_rule_ref:
default_report_language: zh
raw_file_policy: controlled_readonly_copy
knowledge_policy_ref:
created_at:
updated_at:
review_refs: []
```

关键规则必须逐项确认。

v0.1：

- 必须实现。

---

## 5. ExperimentRecord

文件位置：

```text
experiments/exp-YYYYMMDD-NNN.md
```

必填字段：

```yaml
experiment_id:
project_id:
experiment_date:
material_system:
experiment_type:
status: user_confirmed
user_original_text:
structured_by:
review_refs: []
provenance_refs: []
```

建议字段：

```yaml
sample_refs: []
process_conditions:
  substrate:
  temperature:
  duration:
  atmosphere:
  flow_rate:
  source_materials:
observations: []
initial_judgement:
uncertainties: []
related_files: []
```

规则：

- 只有用户确认后才能保存为正式 ExperimentRecord。
- 用户自然语言确认如“可以，保存”“没问题”“可以的”可视为确认。

v0.1：

- 必须实现。

---

## 6. SampleRecord

文件位置：

```text
samples/{sample_id}.md
```

必填字段：

```yaml
sample_id:
project_id:
material_system:
created_from_experiment:
status:
review_refs: []
source_refs: []
```

建议字段：

```yaml
substrate:
sample_type:
morphology_observations: []
quality_notes: []
quality_status: unknown | candidate_good | candidate_medium | candidate_poor
characterization_refs: []
report_refs: []
```

规则：

- `quality_status` 不是 confirmed finding。
- 样品评价标准必须来自项目规则卡，或用户明确标注。

v0.1：

- 必须实现基础记录。

---

## 7. CharacterizationFile

文件位置：

```text
raw/{characterization_id}/metadata.yml
```

必填字段：

```yaml
characterization_id:
project_id:
sample_refs: []
characterization_type: raman
original_source_path:
project_raw_path:
sha256:
file_size_bytes:
imported_at:
import_status: imported | duplicate_alias | needs_review
provenance_refs: []
```

可选字段：

```yaml
original_filename:
aliases: []
instrument_metadata:
  laser_wavelength:
  laser_power:
  integration_time:
  objective:
column_candidates: []
notes:
```

v0.1：

- Raman 必须实现。

---

## 8. RamanProcessingResult

文件位置：

```text
processed/{experiment_id or sample_id}/raman/{raman_result_id}/metadata.yml
```

必填字段：

```yaml
raman_result_id:
project_id:
characterization_file_ref:
sample_refs: []
status: success | warning | failed
x_column:
y_column:
x_unit: cm^-1 | unknown
processing_parameters:
outputs:
  figure:
  peak_table:
  processed_csv:
  metadata:
warnings: []
review_refs: []
provenance_refs: []
```

v0.1：

- 必须实现。

---

## 9. ReportRecord

文件位置：

```text
reports/report-YYYYMMDD-NNN.md
```

必填字段：

```yaml
report_id:
project_id:
report_type: raman_analysis
language: zh
audience: self
related_experiments: []
related_samples: []
related_results: []
include_next_step_suggestions: false
status: draft | user_reviewed
review_refs: []
provenance_refs: []
```

规则：

- v0.1 默认不包含下一步实验建议。

---

## 10. ReviewRecord

文件位置：

```text
reviews/review-YYYYMMDD-NNN.yml
```

必填字段：

```yaml
review_id:
target_type:
target_ref:
review_status: user_confirmed | user_edited | user_rejected | deferred
decision:
reviewed_at:
user_original_text:
reviewed_content_hash:
```

可选字段：

```yaml
notes:
previous_review_ref:
replacement_target_ref:
```

v0.1：

- 必须实现。

---

## 11. ProvenanceEntry

文件位置：

```text
provenance/prov-YYYYMMDD-NNN.yml
```

必填字段：

```yaml
provenance_id:
workflow:
created_at:
skill_name:
skill_version:
inputs:
  records: []
  files: []
outputs:
  records: []
  files: []
parameters:
review_refs: []
warnings: []
```

可选字段：

```yaml
scripts:
  - path:
    version:
    hash:
source_refs: []
```

v0.1：

- 必须实现最小版本。

---

## 12. ProgressEvent

文件位置：

```text
progress/progress-YYYYMMDD-NNN.yml
```

必填字段：

```yaml
progress_id:
recorded_at:
user_original_text:
ea_summary:
event_type: experiment | characterization | data_upload | analysis | report | decision
source_refs: []
review_refs: []
```

可选字段：

```yaml
occurred_at:
related_experiments: []
related_samples: []
related_files: []
uncertainties: []
```

规则：

- 只能来自用户明确表达或用户提交文件/数据。
- EA 建议不能成为 progress event。

---

## 13. SuggestionRecord

文件位置：

```text
suggestions/suggestion-YYYYMMDD-NNN.md
```

必填字段：

```yaml
suggestion_id:
project_id:
status: draft | accepted | modified | rejected
created_at:
trigger:
related_records: []
source_refs: []
```

规则：

- Suggestion 不能自动进入 decision log。
- 用户明确决策后另建 DecisionLogEntry。

---

## 14. DecisionLogEntry

文件位置：

```text
memory/decision-log.md
```

条目字段：

```yaml
decision_id:
decided_at:
user_original_text:
ea_summary:
related_suggestion_ref:
source_refs: []
review_refs: []
```

规则：

- 必须来自用户明确决策表达。

---

## 15. KnowledgeItem

文件位置：

```text
knowledge/global/literature/{knowledge_id}.yml
knowledge/project/literature/{knowledge_id}.yml
```

必填字段：

```yaml
knowledge_id:
scope: global | project
title:
source_type: paper | book | webpage | note | other
created_at:
source_url:
storage_refs: []
summary:
notes:
```

可选字段：

```yaml
authors: []
year:
doi:
relevance:
fulltext_status: available | unavailable | user_needed
sync_status: synced | project_only | global_only | no_sync
```

v0.1：

- 目录和基础条目建议实现。
- 自动同步复杂策略后置。

---

## 16. OpenItem

文件位置：

```text
open-items/openitem-YYYYMMDD-NNN.yml
```

必填字段：

```yaml
open_item_id:
created_at:
item_type:
description:
related_records: []
priority: high | medium | low
status: open | resolved | deferred
source_refs: []
```

规则：

- 默认不在每次对话展示完整表。
- 当前回答受影响时，只提示相关项。

---

## 17. v0.1 必做清单

v0.1 必须实现：

- Project
- ProjectRuleCard
- ExperimentRecord
- SampleRecord 基础版
- CharacterizationFile for Raman
- RamanProcessingResult
- ReportRecord
- ReviewRecord
- ProvenanceEntry 最小版
- ProgressEvent
- SuggestionRecord
- DecisionLogEntry
- OpenItem

KnowledgeItem 基础目录和条目建议实现；复杂同步后置。

