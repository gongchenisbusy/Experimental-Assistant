# EA Agent Team Brief

> 版本：v0.1-panorama-draft  
> 日期：2026-05-29  
> 用途：交给 agent team 主线程的入口文档。  
> 读者：负责搭建 EA 的主线程 agent、架构 agent、脚本 agent、文档/test agent、memory/provenance agent。  

---

## 1. 一句话定义

Experimental Assistant（EA）是一个本地优先、agent-native、面向材料学实验研究的科研 skill 系统。

EA 帮助研究者通过现有 agent 记录实验、管理样品、保护原始数据、处理表征数据、生成可追溯报告，并维护长期项目记忆。

EA 不是 Web app，不是聊天机器人，不是自动科学家，也不是会替用户做科研决策的系统。

---

## 2. 主线程优先阅读顺序

主线程 agent 必须按以下顺序阅读全景地图：

1. `EA_AGENT_TEAM_BRIEF.md`
   - 建立项目北极星、v0.1 范围、不可违反原则和文档索引。

2. `EA_PRODUCT_CHARTER.md`
   - 理解目标用户、产品边界、科研表达风格和版本边界。

3. `EA_ARCHITECTURE_MAP.md`
   - 理解实体、目录结构、schema、工作流、审核节点和 skill 边界。

4. `EA_AGENT_TEAM_PROTOCOL.md`
   - 理解主线程与子 agent 的分工、上下文隔离、review 和交付协议。

5. `EA_TEST_PROTOCOL.md`
   - 理解用户模拟测试、隐藏真值、评估标准和防过拟合要求。

实现前 P0 规格，主线程和相关子 agent 必须阅读：

- `EA_SCHEMA_SPEC.md`
- `EA_REVIEW_STATE_MACHINE.md`
- `EA_RAW_IMPORT_SPEC.md`
- `EA_RAMAN_V0_1_SPEC.md`
- `EA_MEMORY_BOUNDARY_SPEC.md`
- `EA_PROVENANCE_MINIMUM_SPEC.md`

构建启动文件：

- `EA_V0_1_BUILD_PACKAGE_MANIFEST.md`
- `EA_V0_1_PRE_BUILD_TODO.md`
- `EA_V0_1_AGENT_TEAM_SETUP.md`
- `EA_V0_1_GIT_WORKFLOW.md`
- `EA_V0_1_SKILL_SETUP.md`
- `skills-lock.json`

辅助模板与背景文件：

- `ea-project-rule-card-template.md`
- `ea-test-experiment-template.md`
- `EA_IMPLEMENTATION_SPEC_TODO.md`
- `ea-panorama-working-notes.md`
- `ea-brief-agent-native-zh.md`

测试资源：

- `test_cases/test-case-001/public/conversation.md`
- `test_cases/test-case-001/public/raw_data/`
- `test_cases/test-case-001/hidden_truth/evaluation_truth.md`：仅 Evaluation Agent 可读。
- `test_cases/test-case-001/evaluation.md`：仅 Evaluation Agent 可读。

旧合并稿 `ea-test-experiment-test1.md` 仅作为内部归档，不得提供给构建 agent。

---

## 3. EA 的北极星

EA 的首要目标是成为一个可靠、准确、可追溯、符合材料学科研工作流的实验助手 skill。

EA v0.1 必须跑通一个最小但完整的科研闭环：

```text
项目初始化
→ 建立项目规则卡和目录结构
→ 用户提交自然语言实验日志
→ EA 结构化字段并请求用户确认
→ 用户确认后保存实验日志
→ 用户提交 Raman 原始数据和样品关联信息
→ EA 导入 raw 只读副本
→ EA 请求确认数据列和处理参数
→ EA 运行 Raman 数据处理
→ EA 输出图谱、峰表、处理后数据、metadata、中文分析报告
→ 用户审核科学解释和记忆写入
→ EA 更新项目记忆、provenance 和必要索引
```

这个闭环的关键不是功能数量，而是：

- 原始数据安全。
- 数据处理可复现。
- 科学解释审慎。
- 用户审核可追踪。
- 项目记忆可长期积累。

---

## 4. v0.1 必须做到

v0.1 必做：

- 一个 EA 工作目录对应一个科研项目。
- 项目初始化时，用户以自然语言提供研究方向、材料体系、实验类型。
- EA 创建本地目录结构、全局知识库目录、项目知识库目录，并告知用户。
- EA 与用户确认项目规则卡。
- EA 帮助用户确认样品编号规则。
- EA 帮助用户确认样品评价标准。
- 每次自然语言实验日志都必须结构化并经用户确认后保存。
- 原始数据导入为 `raw/` 中的受控只读副本。
- Raman 数据分析支持列确认、参数确认、处理、绘图、峰表、metadata 和中文分析报告。
- 按 `EA_SCHEMA_SPEC.md`、`EA_REVIEW_STATE_MACHINE.md`、`EA_RAW_IMPORT_SPEC.md`、`EA_RAMAN_V0_1_SPEC.md`、`EA_MEMORY_BOUNDARY_SPEC.md`、`EA_PROVENANCE_MINIMUM_SPEC.md` 落实 P0 工程边界。
- 默认报告面向用户自己阅读，不默认包含下一步实验建议。
- 用户追问时，EA 可以基于报告、实验记录、项目记忆和文献给出下一步建议。
- EA 的建议不能直接写入项目决策。
- 项目进度必须来自用户明确描述或用户提交的数据/文件。
- 历史查询默认附带简短来源。
- 本地知识库分为全局知识库和项目知识库。
- 保留完整 provenance 和 review decision。

---

## 5. v0.1 不做

v0.1 不做：

- Web、UI、移动端、云服务。
- 多项目管理。
- 自动实验决策。
- 实验室设备控制。
- 大规模 RAG。
- 模型微调。
- 自动在线论文大规模抓取。
- 知识库自动同步完整机制。
- 阶段性冻结完整恢复和快照管理。
- XRD、PL、AFM、SEM/TEM 等完整分析 skill。
- 英文报告默认支持。
- 科学解释 reviewer 证据等级强制落地。
- 自动把 EA 建议写入项目决策。

---

## 6. 后续版本方向

后续版本可以考虑：

- 多项目管理。
- 中英文报告。
- XRD、PL、AFM、电化学、SEM/TEM 等表征 skill。
- 科学解释 reviewer skill 和简单证据等级。
- 更强的文献知识库。
- 知识库自动同步和不同步恢复机制。
- 完整阶段冻结、校验和恢复能力。
- 文件夹监听和自动导入。
- 组会报告、阶段报告、论文素材整理增强。
- 多材料体系扩展。

后续方向必须在 v0.1 本地闭环稳定后再推进。

---

## 7. 不可违反原则

所有 agent 必须遵守：

- 原始数据绝不能被修改。
- 未经用户确认的实验日志不能正式保存。
- 未经用户确认的科学解释不能写入 confirmed findings。
- EA 建议不能直接成为项目决策。
- EA 建议不能直接成为项目进度。
- 项目主体记忆必须来自用户确认、用户明确表达或可追溯文件。
- LLM 不得直接自由解释原始数据；数据处理优先使用确定性脚本。
- test 实验只是模拟测试素材，不能被硬编码进 EA 架构。
- MoS2 是 v0.1 的唯一材料体系，但 EA 核心架构不能 MoS2 专用化。
- 目录、schema、workflow 必须服务长期可追溯，而不是短期 demo。

---

## 8. Agent Team 建议角色

建议采用：

```text
主线程 orchestrator
├── Architecture agent
├── Raman/script agent
├── Memory/provenance agent
├── Scientific language agent
├── Documentation/test agent
└── Simulated user / evaluation agent
```

以上是全景地图中的基线角色。正式构建 EA v0.1 时，应以 `EA_V0_1_AGENT_TEAM_SETUP.md` 的扩展 agent-team、Codex 子 agent 操作协议、skill 白名单和访问边界为准。

主线程负责持有全景地图、分配任务、控制上下文、判断偏离风险和整合结果。

子 agent 只处理自己的边界任务，不应擅自改变 EA 北极星或核心原则。

---

## 9. 当前最高风险

构建时最容易做偏的地方：

- 把 EA 做成通用聊天机器人。
- 把 EA 做成 Web/UI 产品。
- 把 MoS2 test 样本硬编码成通用规则。
- 为了演示方便跳过用户审核。
- 把 EA 的下一步建议写成用户项目决策。
- 把未确认假设写入 confirmed findings。
- 让 LLM 直接解释原始曲线。
- 忽略 provenance、review decision 和 raw 数据不可变。

主线程 agent 的首要职责之一，就是在这些风险出现时立刻阻止。
