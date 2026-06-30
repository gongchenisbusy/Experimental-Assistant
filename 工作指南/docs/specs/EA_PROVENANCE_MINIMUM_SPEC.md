# EA Provenance Minimum Spec

> 版本：v0.1-p0-draft  
> 日期：2026-06-01  
> 优先级：P0  
> 用途：定义 EA v0.1 最小 provenance 要求，确保实验记录、数据处理、报告和记忆写入可追溯。  

---

## 1. 核心原则

每个重要输出都必须能回答：

- 输入是什么？
- 输出是什么？
- 谁或哪个 skill 生成？
- 用了什么参数？
- 是否经过用户审核？
- 文件在哪里？
- 是否有 warning？

---

## 2. ProvenanceEntry 格式

文件位置：

```text
provenance/prov-YYYYMMDD-NNN.yml
```

最小字段：

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
source_refs: []
```

建议字段：

```yaml
scripts:
  - path:
    version:
    hash:
environment:
  python_version:
  package_versions:
notes:
```

---

## 3. 必须覆盖的 workflow

v0.1 必须为以下 workflow 写 provenance：

- project_initialization。
- project_rule_card_update。
- experiment_log_save。
- raw_file_import。
- raman_column_confirmation。
- raman_processing。
- report_generation。
- memory_write。
- suggestion_generation。
- progress_event_write。

---

## 4. Project initialization provenance

记录：

- 用户原始项目描述。
- EA 提取的初始信息。
- 用户确认 review。
- 创建的目录。
- 创建的规则卡。

---

## 5. Experiment log provenance

记录：

- 用户原始文本。
- EA 结构化字段。
- 追问和用户补充。
- 用户确认 review。
- 保存的 ExperimentRecord。

---

## 6. Raw import provenance

记录：

- 原始路径。
- 项目内 raw 路径。
- SHA-256。
- 文件大小。
- 导入状态。
- duplicate alias 信息。
- warning。

---

## 7. Raman processing provenance

记录：

- CharacterizationFile ref。
- x/y 列。
- 单位。
- 用户确认 review。
- 处理参数。
- 脚本路径和 hash。
- 输出文件。
- warning。

---

## 8. Report generation provenance

记录：

- 使用的实验记录。
- 使用的样品记录。
- 使用的 processed result。
- 使用的知识库条目。
- 报告路径。
- 科学解释审核 review。

---

## 9. Memory write provenance

记录：

- 写入目标。
- 写入内容摘要。
- 来源记录。
- 用户确认 review。
- 写入前 hash。
- 写入后 hash。

---

## 10. Warning 规范

warning 应使用稳定标识：

```yaml
warnings:
  - code: x_unit_unknown
    message: Raman shift unit is unknown and requires user confirmation.
    severity: medium
```

severity：

- low
- medium
- high

high warning 不能静默忽略。

---

## 11. v0.1 验收

必须验证：

- 每条正式 ExperimentRecord 有 provenance。
- 每个 raw import 有 provenance。
- 每个 Raman result 有 provenance。
- 每个 report 有 provenance。
- 每次 memory write 有 provenance。
- provenance 中 review refs 能指向 ReviewRecord。

