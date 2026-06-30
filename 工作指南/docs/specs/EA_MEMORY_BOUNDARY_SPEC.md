# EA Memory Boundary Spec

> 版本：v0.1-p0-draft  
> 日期：2026-06-01  
> 优先级：P0  
> 用途：定义 EA v0.1 中 suggestion、decision、progress、confirmed finding、hypothesis 的数据层隔离。  

---

## 1. 核心原则

EA 是实验助手，不是项目决策者。

EA 可以提出建议，但不能把建议写成用户决策。

EA 可以整理项目进度，但不能把未发生的建议写成已完成进度。

---

## 2. 存储分区

```text
suggestions/
progress/
memory/
├── confirmed-findings.md
├── open-questions.md
├── failed-attempts.md
├── decision-log.md
└── paper-materials/
```

分区规则：

| 内容 | 存储位置 | 是否需要用户确认 |
|---|---|---|
| EA 下一步建议 | `suggestions/` | 生成不需要，采纳需要 |
| 用户项目决策 | `memory/decision-log.md` | 必须 |
| 用户完成的项目进度 | `progress/` | 必须来自用户表达或文件提交 |
| 已确认发现 | `memory/confirmed-findings.md` | 必须 |
| 待验证假设 | `memory/open-questions.md` | 不作为结论 |
| 失败实验/路径 | `memory/failed-attempts.md` | 需要用户确认或来源明确 |

---

## 3. SuggestionRecord

状态：

```text
draft
accepted
modified
rejected
```

字段：

```yaml
suggestion_id:
status:
created_at:
trigger:
suggestion_text:
evidence_refs: []
related_records: []
user_response:
review_refs: []
```

规则：

- `draft` 是默认状态。
- `accepted` 表示用户愿意采纳方向，但仍不自动进入 decision log。
- `modified` 表示用户基于建议形成了修改版计划。
- `rejected` 表示用户拒绝。

---

## 4. DecisionLogEntry

只能来自用户明确决策表达。

明确表达示例：

- “我采用你的建议”
- “我下一步计划……”
- “接下来我决定……”
- “这条路线先暂停”
- “我们改成……”

字段：

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

- `accepted` suggestion 不能自动生成 DecisionLogEntry。
- 必须保留用户原话。

---

## 5. ProgressEvent

ProgressEvent 记录已经发生或用户明确提交的项目进度。

可以写入的触发：

- 用户说“我今天做了……”
- 用户提交实验记录并确认保存。
- 用户提交 Raman 数据。
- 用户确认报告生成或分析完成。

不能写入的触发：

- EA 建议“可以做 Raman”。
- EA 预测“下一步可能会……”。
- 未确认草稿。

---

## 6. ConfirmedFinding

ConfirmedFinding 必须满足：

- 有实验、数据、报告或文献来源。
- 有用户确认。
- 有 provenance 或 review reference。

不能写入：

- 未确认解释。
- 待验证假设。
- EA 自行判断的机制解释。

---

## 7. OpenQuestion

OpenQuestion 用于保存：

- 待验证假设。
- 后续实验问题。
- 数据不足导致的疑问。
- 文献不足导致的解释空白。

OpenQuestion 不是失败，也不是结论。

---

## 8. FailedAttempt

FailedAttempt 保存：

- 失败实验。
- 异常样品。
- 无效参数。
- 被用户确认不再继续的路径。

规则：

- 失败路径也要可追溯。
- 不要删除失败尝试，它们是论文素材和项目复盘资产。

---

## 9. 论文素材池边界

论文素材池可以引用：

- confirmed findings。
- failed attempts。
- 结果图。
- 实验条件。
- 可引用表述。

但必须标记：

- 草稿表达。
- 用户确认表达。
- 待验证表达。

---

## 10. v0.1 验收

必须验证：

- suggestion 不会自动进入 decision log。
- EA 建议不会自动生成 progress event。
- 未确认 hypothesis 不会进入 confirmed findings。
- 用户明确决策能写入 decision log。
- 用户明确完成事项能写入 progress event。

