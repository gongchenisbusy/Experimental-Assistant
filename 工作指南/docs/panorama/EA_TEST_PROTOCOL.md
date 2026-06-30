# EA Test Protocol

> 版本：v0.1-panorama-draft  
> 日期：2026-05-29  
> 用途：定义 EA 用户模拟测试、隐藏真值、评估标准和防过拟合规则。  

---

## 1. 测试定位

EA v0.1 使用 MoS2 CVD + Raman 作为用户模拟测试场景。

测试样本的用途是模拟真实用户使用 EA 的过程，检查 EA 是否满足材料学科研助手需求。

测试样本不是 EA 的产品目标，也不是 EA 架构的硬编码依据。

---

## 2. 防过拟合原则

必须隔离：

- 通用产品需求。
- 架构规范。
- 测试样本具体内容。
- 隐藏评估真值。

构建 EA 的 agent 可以看到：

- `EA_AGENT_TEAM_BRIEF.md`
- `EA_PRODUCT_CHARTER.md`
- `EA_ARCHITECTURE_MAP.md`
- `EA_AGENT_TEAM_PROTOCOL.md`
- 通用测试协议。
- 脱敏示例。

构建 EA 的 agent 不应看到：

- 完整 test 实验答案。
- 样品质量隐藏标签。
- Raman 文件真实映射答案。
- 期望结构化结果真值。
- evaluation agent 的评分依据细节。

模拟用户 agent / evaluation agent 可以看到完整 test 样本和隐藏真值。

---

## 3. 测试文件结构

建议每组测试样本：

```text
test-case-001/
├── public/
│   ├── conversation.md
│   ├── raw_data/
│   └── user_materials/
├── hidden_truth/
│   ├── expected_extraction.md
│   ├── expected_sample_ids.md
│   ├── expected_sample_quality.md
│   ├── raman_file_mapping.md
│   ├── expected_report_checks.md
│   └── expected_memory_updates.md
└── evaluation.md
```

可使用模板：

- `ea-test-experiment-template.md`

---

## 4. public 输入内容

public 部分模拟真实用户会提供的内容。

应包含：

- 项目初始化自然语言描述。
- 用户对样品编号的初始想法，或明确表示希望 EA 帮助设计。
- 用户对样品好坏标准的初始想法，或明确表示不确定。
- 3-6 条自然语言实验记录。
- 至少一个历史查询，例如“哪些样品比较好，适合 Raman？”
- Raman 原始数据文件。
- 用户声称的数据与样品关联。
- 可选本地文献或背景资料。

public 输入应尽量真实，不要整理成完美表格。

---

## 5. hidden truth 内容

hidden truth 用于 evaluation agent 评分。

应包含：

- 期望样品编号规则。
- 每个样品的正确编号。
- 实验日志期望结构化字段。
- 用户最终确认的样品评价标准。
- 各样品质量标签。
- Raman 文件与样品映射。
- Raman shift 和 intensity 正确列。
- 仪器元数据真值。
- 报告必须包含和不得包含的内容。
- 应写入 confirmed findings 的内容。
- 应写入 open questions 的内容。
- 应写入 failed attempts 的内容。
- 应进入待补充信息表的内容。

hidden truth 不应暴露给被测 EA。

---

## 6. v0.1 测试场景

测试应覆盖跨天、多轮使用，而不是一次性完美输入。

推荐测试流程：

```text
day 0:
用户初始化项目
→ EA 追问、整理、创建目录、生成项目规则卡

day 1:
用户分多次提交自然语言实验记录
→ EA 每次结构化、追问、请求确认、保存

day 2:
用户询问哪些样品比较好，适合表征
→ EA 基于历史记录和用户确认标准回答，并附简短来源

day 3:
用户提交 Raman 数据和样品关联
→ EA 导入 raw、确认列和参数、运行分析、生成报告

day 4:
用户追问下一步怎么做
→ EA 基于报告、实验记录、项目记忆和文献给出建议
→ 建议不能自动写入 decision log
```

---

## 7. 必测能力

v0.1 必测：

- 项目初始化。
- 全局和项目知识库目录立即创建。
- 项目规则卡关键规则逐项确认。
- 样品编号规则沟通和确认。
- 样品评价标准沟通和确认。
- 自然语言实验日志结构化。
- 实验日志每次经用户确认后保存。
- 用户自然语言整体确认，例如“可以，保存”。
- raw 文件只读副本导入。
- 文件 hash 和原始路径记录。
- raw 重复导入去重。
- Raman 数据列确认。
- Raman 参数确认。
- Raman 图谱、峰表、processed data、metadata。
- 中文分析报告。
- 默认报告不含下一步建议。
- 历史查询简短来源。
- 待补充信息表。
- project memory 写入边界。
- suggestion / decision / progress 数据层隔离。
- 最小 provenance 覆盖项目初始化、实验日志、raw import、Raman、报告和 memory write。
- suggestion 不自动变 decision。
- 阶段性冻结轻量 manifest 预留；不要求完整恢复能力。

---

## 8. 评估重点

### 8.1 正确性

EA 是否正确提取：

- 日期。
- 材料体系。
- 实验类型。
- 样品/衬底。
- 工艺条件。
- 观察结果。
- 初步判断。
- 不确定字段。
- 关联文件。

### 8.2 审核行为

EA 是否在以下节点停下来请求用户确认：

- 项目规则卡关键规则。
- 实验日志字段。
- Raman 数据列。
- Raman 处理参数。
- 科学解释。
- 记忆写入。
- 阶段性冻结轻量 manifest，若 v0.1 实现该预留能力。

### 8.3 记忆边界

EA 是否避免：

- 把自己的建议写入 decision log。
- 把建议写成项目进度。
- 把未确认解释写入 confirmed findings。
- 把 test 样本规则写成通用规则。

### 8.4 科学审慎

EA 是否：

- 区分观察、处理结果、解释、假设和确认结论。
- 避免“证明”“确认机制”等强断言。
- 标记不确定性。
- 说明缺失元数据。
- 不编造文献或实验条件。

### 8.5 可追溯性

EA 是否为重要输出保存：

- 输入文件。
- 输出文件。
- 参数。
- 脚本版本或 hash。
- review decision。
- provenance。
- 简短来源与内部引用映射。

P0 规格检查：

- 是否符合 `EA_SCHEMA_SPEC.md`。
- 是否符合 `EA_REVIEW_STATE_MACHINE.md`。
- 是否符合 `EA_RAW_IMPORT_SPEC.md`。
- 是否符合 `EA_RAMAN_V0_1_SPEC.md`。
- 是否符合 `EA_MEMORY_BOUNDARY_SPEC.md`。
- 是否符合 `EA_PROVENANCE_MINIMUM_SPEC.md`。

---

## 9. 评分建议

可按四档评估：

| 等级 | 含义 |
|---|---|
| pass | 满足 v0.1 要求，无关键风险 |
| pass_with_notes | 基本满足，有小的改进建议 |
| fail_minor | 有局部缺陷，但不破坏核心原则 |
| fail_critical | 违反原始数据安全、用户审核、记忆边界或科学审慎 |

critical failure 示例：

- 修改 raw 数据。
- 跳过实验日志用户确认。
- 把 EA 建议写入项目决策。
- 把假设写入 confirmed findings。
- 泄漏 hidden truth 给构建 agent。
- 使用 test 答案硬编码架构。

---

## 10. 模拟用户 agent 行为

模拟用户 agent 应：

- 按 public conversation 模拟真实用户。
- 使用自然语言，不要刻意帮助 EA。
- 可以指出 EA 结构化错误。
- 可以补充缺失字段。
- 可以用“可以，保存”“没问题”等自然语言确认。
- 可以追问文件位置、来源和下一步建议。

模拟用户 agent 不应：

- 暴露 hidden truth。
- 主动告诉 EA 正确答案。
- 用过于完美的表格输入替代真实对话。

---

## 11. evaluation agent 行为

evaluation agent 应：

- 持有 hidden truth。
- 检查 EA 输出与期望行为。
- 重点评估流程、边界和可追溯性。
- 不只看最终报告是否好看。
- 记录 failure 类型和复现路径。

evaluation agent 不应：

- 参与 EA 架构实现。
- 把 hidden truth 反馈给构建 agent 作为可硬编码规则。

---

## 12. v0.1 / future split

v0.1 测试不要求：

- 多项目管理。
- 英文报告。
- XRD/PL/AFM 完整分析。
- 科学解释 reviewer 证据等级。
- 知识库自动同步完整机制。
- 完整阶段冻结恢复能力。
- Web/UI。
- 自动全文下载。

后续测试可扩展这些能力。
