# EA Review State Machine

> 版本：v0.1-p0-draft  
> 日期：2026-06-01  
> 优先级：P0  
> 用途：定义 EA v0.1 用户审核状态、转换规则、确认判定和记录方式。  

---

## 1. 核心原则

EA v0.1 的可信度依赖用户审核。

未经用户确认的内容不能进入：

- 正式实验记录。
- project progress。
- confirmed findings。
- decision log。
- 论文素材池中的确认结论。

---

## 2. 通用状态机

```text
working_draft
→ needs_user_review
→ user_confirmed | user_edited | user_rejected | deferred
→ saved | archived
```

状态含义：

| 状态 | 含义 |
|---|---|
| `working_draft` | EA 正在整理，尚未展示给用户确认 |
| `needs_user_review` | 已展示给用户，等待审核 |
| `user_confirmed` | 用户明确确认 |
| `user_edited` | 用户指出错误或给出修改 |
| `user_rejected` | 用户拒绝保存或拒绝该内容 |
| `deferred` | 用户要求稍后再确认 |
| `saved` | 已按确认内容正式保存 |
| `archived` | 被归档，不作为当前有效内容 |

---

## 3. 必须审核的对象

v0.1 必须审核：

- 项目初始信息。
- 项目规则卡关键规则。
- 样品编号规则。
- 样品评价标准。
- 每条实验日志结构化字段。
- Raman x/y 数据列。
- Raman 处理参数。
- Raman 科学解释。
- 记忆写入。
- 阶段冻结，如果 v0.1 生成轻量 freeze manifest。

---

## 4. 用户确认判定

明确确认示例：

- “可以，保存”
- “没问题”
- “可以的”
- “确认”
- “就按这个保存”
- “这版是对的”

不应视为确认：

- “再看看”
- “可能吧”
- “先放着”
- “大概是”
- “你觉得呢”
- “之后再说”

如果用户表达模糊，EA 必须继续确认。

---

## 5. 实验日志审核流程

```text
用户自然语言输入
→ working_draft
→ EA 追问缺失字段
→ EA 展示结构化字段
→ needs_user_review
→ 用户确认 / 修改 / 拒绝 / 延后
```

规则：

- 用户确认后保存为 `ExperimentRecord`。
- 用户修改后，EA 必须更新结构化字段并再次展示。
- 用户拒绝后，不保存正式实验记录。
- 用户延后后，只能保留临时草稿，不进入正式记忆。

---

## 6. 项目规则卡审核

关键规则必须逐项确认：

- 样品编号规则。
- 样品评价标准。
- 原始文件管理策略。
- 默认数据处理偏好。
- 项目记忆写入规则。
- 阶段冻结规则。

用户可以用自然语言确认单项规则，但不能用一句话批量确认全部关键规则。

---

## 7. Raman 审核

Raman workflow 的审核点：

1. 数据列确认。
2. 单位确认。
3. 处理参数确认。
4. 科学解释审核。
5. 记忆写入审核。

列或单位不明确时，不得继续自动分析为正式结果。

参数未确认时，可以生成预览，但不能保存为最终 processing result。

---

## 8. 记忆写入审核

写入以下位置前必须确认：

- `memory/confirmed-findings.md`
- `memory/decision-log.md`
- `memory/paper-materials/key-findings.md`
- `progress/`

不需要用户确认即可保存为草稿的内容：

- `suggestions/` 中的 EA 建议草稿。
- `open-items/` 中的缺失信息项。
- provenance。

但这些草稿不能冒充用户确认内容。

---

## 9. ReviewRecord 格式

每次审核写入：

```yaml
review_id:
target_type:
target_ref:
previous_target_hash:
review_status:
decision:
reviewed_at:
user_original_text:
reviewed_content_hash:
notes:
```

当用户修改内容时：

```yaml
review_status: user_edited
decision: accepted_with_user_edits
```

EA 必须保存用户原话或足够完整的确认语句。

---

## 10. 版本记录

建议规则：

- 每个正式记录保留 `version` 字段。
- 用户修改并重新确认后，版本递增。
- 旧版本不直接删除，至少保留 hash 和 review reference。

v0.1 可采用轻量版本：

```yaml
version: 1
previous_version_ref:
change_reason:
```

---

## 11. 失败场景处理

如果 EA 不确定用户是否确认：

- 不保存正式记录。
- 继续向用户确认。

如果用户指出 EA 结构化错误：

- 标记 `user_edited`。
- 依据用户修改重建结构化字段。
- 再次展示确认。

如果用户拒绝：

- 标记 `user_rejected`。
- 不进入正式记录。
- 可保留 review record 说明拒绝原因。

