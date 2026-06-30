# EA Agent Team Protocol

> 版本：v0.1-panorama-draft  
> 日期：2026-05-29  
> 用途：定义 EA 搭建时 agent team 的组织方式、职责边界、上下文隔离、交付协议和 review 标准。  

---

## 1. 总原则

主线程 agent 是 EA 搭建工作的总控。

主线程必须：

- 持有全景地图。
- 判断任务是否偏离 EA 目标。
- 分配子 agent 工作。
- 控制测试样本访问边界。
- 审查 v0.1 与后续版本边界。
- 阻止任何违反原始数据安全、用户审核、科学审慎和记忆边界的实现。

子 agent 不得擅自改变 EA 北极星。

---

## 2. 推荐角色

```text
Main orchestrator
├── Architecture agent
├── Raman/script agent
├── Memory/provenance agent
├── Scientific language agent
├── Documentation/test agent
└── Simulated user / evaluation agent
```

这是全景地图中的基线角色。正式构建 EA v0.1 时，应以 `EA_V0_1_AGENT_TEAM_SETUP.md` 的扩展角色、Codex 子 agent 独立上下文协议、agent registry、skill 白名单和 fallback 多窗口方案为准。

---

## 3. 主线程职责

主线程负责：

- 阅读全部 5 份全景地图。
- 制定实现顺序。
- 保持 v0.1 范围。
- 分派子任务。
- 整合子 agent 输出。
- 维护接口一致性。
- 审查是否跳过用户审核。
- 审查是否污染项目记忆。
- 审查是否将 test 内容硬编码。
- 决定何时进入下一阶段。

主线程不得：

- 把测试隐藏真值交给构建 agent。
- 为了速度跳过用户审核节点。
- 允许 LLM 直接解释 raw 数据。
- 放任子 agent 引入 Web/UI 产品路线。

---

## 4. Architecture agent

负责：

- 本地目录结构。
- 项目规则卡 schema。
- 实验记录 schema。
- 样品 schema。
- review decision schema。
- provenance schema。
- progress event schema。
- lightweight stage freeze manifest。
- skill 返回结构。
- v0.1/future 边界落地。

实现前必须对齐：

- `EA_SCHEMA_SPEC.md`
- `EA_REVIEW_STATE_MACHINE.md`
- `EA_MEMORY_BOUNDARY_SPEC.md`
- `EA_PROVENANCE_MINIMUM_SPEC.md`

必须遵守：

- v0.1 一个工作目录一个项目。
- 目录由 EA 创建后告知用户。
- 全局和项目知识库目录初始化时创建。
- raw 数据只读。
- 重要输出必须有 provenance。

---

## 5. Raman/script agent

负责：

- Raman 文件读取。
- txt/csv/xlsx 等格式兼容。
- 表头和列识别。
- 仪器元数据提取。
- 数据列确认流程。
- 参数确认流程。
- 确定性数据处理。
- 绘图。
- 峰识别。
- 输出 processed data、figure、peak table、metadata。

实现前必须对齐：

- `EA_RAMAN_V0_1_SPEC.md`
- `EA_RAW_IMPORT_SPEC.md`
- `EA_PROVENANCE_MINIMUM_SPEC.md`

必须遵守：

- 不修改 raw。
- 不让 LLM 直接解释原始曲线。
- 缺失元数据必须显式标记。
- 处理参数必须记录。
- 图表必须有标题、坐标轴、单位和必要图例。
- Raman shift 单位使用 `cm^-1`。

---

## 6. Memory/provenance agent

负责：

- 项目记忆结构。
- confirmed findings。
- open questions。
- failed attempts。
- decision log。
- paper materials。
- open items。
- progress events。
- provenance。
- review records。
- lightweight stage freeze manifest。

实现前必须对齐：

- `EA_MEMORY_BOUNDARY_SPEC.md`
- `EA_REVIEW_STATE_MACHINE.md`
- `EA_PROVENANCE_MINIMUM_SPEC.md`

必须遵守：

- EA 建议不能写入 decision log。
- 未确认假设不能写入 confirmed findings。
- 项目进度必须来自用户明确描述或提交的文件/数据。
- 每条长期记忆必须可追溯。
- 阶段冻结必须用户确认。

---

## 7. Scientific language agent

负责：

- 报告语言规则。
- 科学解释边界。
- 过度推断检查。
- 不确定性表达。
- 文献依据表达。

v0.1 不强制实现 reviewer 证据等级。

后续版本可考虑简单等级：

- `observation`
- `processed_result`
- `literature_supported`
- `hypothesis`
- `user_confirmed`

必须遵守：

- 不把假设写成结论。
- 不把单一 Raman 数据写成强证明。
- 不编造文献。
- 不编造缺失实验条件。

---

## 8. Documentation/test agent

负责：

- 用户模拟测试样本结构。
- 测试模板。
- 验收标准。
- 用户工作流说明。
- 防过拟合规则。
- 文档一致性检查。

必须遵守：

- test 样本只是评估素材。
- test 样本不能成为通用架构。
- public input 和 hidden truth 必须隔离。

---

## 9. Simulated user / evaluation agent

负责：

- 使用 public conversation 模拟用户。
- 持有 hidden truth。
- 评估 EA 是否满足 v0.1。
- 记录 failure。

不得：

- 参与架构实现。
- 把 hidden truth 交给构建 agent。
- 帮助被测 EA 规避真实用户场景。

---

## 10. 推荐实现顺序

建议顺序：

1. 补齐并冻结 P0 实现规格：schema、review state machine、raw import、Raman v0.1、memory boundary、minimum provenance。
2. 建立本地目录和核心 schema。
3. 实现项目初始化和项目规则卡。
4. 实现实验日志结构化审核与保存。
5. 实现 raw 文件导入和最小 provenance。
6. 实现 Raman 文件读取、列确认和参数确认。
7. 实现 Raman 处理、绘图、峰表、metadata。
8. 实现中文报告生成。
9. 实现 review decision、project memory、progress event。
10. 实现 suggestion 边界。
11. 实现知识库基本目录和条目管理。
12. 预留轻量 stage freeze manifest。
13. 用模拟测试验证闭环。

不要先做：

- 前端。
- 多项目。
- 多表征模块。
- 大规模文献系统。
- 知识库自动同步完整机制。
- 完整阶段冻结恢复系统。
- reviewer 证据等级。

---

## 11. 子任务交付格式

每个子 agent 交付时应说明：

- 改动范围。
- 涉及文件。
- 输入。
- 输出。
- 与全景地图的对应要求。
- 未实现内容。
- 风险。
- 测试方式。
- 是否影响 v0.1/future 边界。

---

## 12. Review checklist

每次 review 检查：

- 是否修改 raw 数据。
- 是否跳过用户确认。
- 是否把 EA 建议写入项目决策。
- 是否把未确认假设写入 confirmed findings。
- 是否缺少 provenance。
- 是否缺少 review record。
- 是否引入 Web/UI。
- 是否把 test 样本硬编码。
- 是否让 LLM 直接解释 raw 数据。
- 是否混淆 v0.1 和后续版本。
- 是否让用户承担不必要的目录设计负担。

---

## 13. 上下文隔离规则

构建 agent 可读：

- 全景地图。
- 通用模板。
- 脱敏样例。
- public 测试输入。

构建 agent 不可读：

- hidden truth。
- evaluation answer key。
- 测试样本最终评分表。

evaluation agent 可读 hidden truth，但不能将其反馈成实现规则。

---

## 14. 变更控制

如果任何 agent 认为需要改变全景地图中的原则，必须：

1. 明确指出冲突。
2. 说明为什么现有原则无法满足需求。
3. 提出替代方案。
4. 标明影响 v0.1 还是后续版本。
5. 请求主线程和用户确认。

未经确认，不得改变核心原则。

---

## 15. 完成定义

EA v0.1 搭建完成的最低定义：

- 可以初始化本地项目。
- 可以生成项目规则卡。
- 可以结构化并确认实验日志。
- 可以保存实验记录、review 和 provenance。
- 可以导入 Raman raw 文件。
- 可以确认数据列和处理参数。
- 可以生成 Raman 图谱、峰表、processed data、metadata。
- 可以生成中文分析报告。
- 可以维护项目记忆。
- 可以区分 EA 建议和用户决策。
- 可以回答历史查询并附简短来源。
- 可以通过 `test-case-001` 用户模拟测试。
- P0 实现规格已被实际实现或明确映射到代码与测试。
