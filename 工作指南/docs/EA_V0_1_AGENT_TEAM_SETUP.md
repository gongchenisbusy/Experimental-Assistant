# EA v0.1 Agent Team Setup

> 用途：交给正式构建 EA v0.1 的主线程 agent，用于建立、组织和管理 agent team。  
> 状态：pre-build handoff config  
> 日期：2026-06-02  
> 适用范围：EA v0.1 本地 agent-native skill 构建，不适用于 Web/UI/多项目扩展。  

---

## 1. 结论

EA v0.1 推荐采用：

```text
hierarchical orchestrator + bounded specialist agents + independent QA/evaluation
```

也就是：

- 一个主线程 orchestrator 持有完整全景地图、范围边界、任务计划和最终整合权。
- 专家 agent 只处理边界清楚的子任务，不能自行改变 EA 北极星。
- 子 agent 的成果尽量写成文件或结构化交付，主线程通过文件和明确接口整合，避免口头转述造成信息损失。
- review / evaluation 与构建隔离，尤其是 hidden truth 只能给 evaluation agent。
- 在 Codex 环境中，如果存在 `multi_agent_v1.spawn_agent` 一类子 agent 工具，主线程必须用真实子 agent 执行并行/隔离任务；默认使用 `fork_context: false`，只传入最小上下文包，确保子 agent 不继承主线程完整上下文。

不建议采用完全去中心化 swarm，也不建议让多个 agent 同时自由修改同一批核心文件。

---

## 2. 外部 multi-agent 资料参考

本配置参考了以下公开资料，并只吸收适合 EA 的部分：

| 来源 | 对 EA 有用的做法 | EA 中的采用方式 |
|---|---|---|
| Anthropic, [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) | lead agent + specialized subagents；主控分解任务；子 agent 并行探索；子 agent 输出独立 artifact；用评估和 tracing 控制 emergent behavior | 采用主控 + 专家 agent；要求每个子 agent 写文件化交付；主控保留最终整合权 |
| Anthropic, [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) | 先用简单、可组合模式；复杂度只在需要时增加；coding agents 要依赖 tests 和 human review | EA v0.1 不上复杂框架；先做确定性脚本、schema、测试和人工审核 |
| OpenAI Agents SDK, [Agent orchestration](https://openai.github.io/openai-agents-python/multi_agent/) | `agents as tools` 适合 manager 保持最终控制；handoffs 适合 specialist 接管后续交互；需要 shared guardrails | EA 采用 agents-as-tools 风格：专家 agent 解决 bounded subtask，但不接管总对话 |
| LangGraph, [Multi-agent docs](https://langchain-ai.github.io/langgraph/tutorials/multi_agent/multi-agent-collaboration/) | multi-agent 主要价值是 context management、distributed development、parallelization；subagents 适合大上下文和并行专业任务 | 用子 agent 隔离 schema、Raman、memory、test 等上下文，减少主线程过载 |
| Microsoft AutoGen, [AutoGen docs](https://microsoft.github.io/autogen/dev/index.html) | multi-agent conversation 可以组织单 agent 和多 agent 应用；AgentChat 适合 conversational multi-agent applications | 借鉴“角色明确 + 对话式协作”，但 EA 不要求引入 AutoGen 框架 |
| CrewAI, [Processes](https://docs.crewai.com/en/concepts/processes) and [Hierarchical Process](https://docs.crewai.com/en/learn/hierarchical-process) | hierarchical process 用 manager agent 做 planning、delegation、validation；根据 agent 能力分派任务 | EA 主线程扮演 manager，负责任务分派、成果验收和返工 |

Skill 检索结果：

- 已运行 `npx skills find "multi agent orchestration"`。
- 最高结果为 `qodex-ai/ai-agent-skills@multi-agent-orchestration`，约 1.6K installs。
- 由于该 skill 来源不是 EA 当前信任链中的官方框架，且现有 EA 文档与公开资料已足够，本轮不安装额外 skill。
- 另外两个并行 `npx skills find` 查询触发 npm `_npx` 临时目录 `ENOTEMPTY rename` 冲突；该错误不影响本配置文件。

---

## 3. Agent Team 总结构

正式构建 EA v0.1 时建议使用以下团队：

```text
Main Orchestrator
├── Context Librarian Agent
├── Architecture & Schema Agent
├── Review Workflow Agent
├── Experiment Log & Sample Agent
├── Raw Import Agent
├── Raman Pipeline Agent
├── Report & Scientific Language Agent
├── Memory & Provenance Agent
├── Test Harness Agent
├── QA Reviewer Agent
└── Simulated User / Evaluation Agent
```

其中：

- `Main Orchestrator` 是唯一总控。
- `QA Reviewer Agent` 可以参与构建 review，但不持有 hidden truth。
- `Simulated User / Evaluation Agent` 只在测试阶段启用，可持有 hidden truth，但不能参与实现。

---

## 3.1 Codex 子 Agent 操作协议

本节用于确保“agent-team”不是只停留在角色命名，而是在 Codex 新窗口中真正以独立上下文子 agent 的方式落地。

### 3.1.1 启动时必须先检查工具

Main Orchestrator 在正式分派任务前必须：

1. 使用可用的 tool discovery 能力查找 multi-agent / sub-agent 工具。
2. 如果存在 `multi_agent_v1.spawn_agent`、`wait_agent`、`send_input`、`close_agent` 等工具，优先使用这些工具建立子 agent。
3. 如果没有这些工具，不得假装已经建立独立子 agent；必须改用本节的 fallback 方案，并告诉用户限制。

### 3.1.2 独立上下文原则

默认规则：

```yaml
fork_context: false
```

含义：

- 子 agent 不继承主线程完整对话历史。
- 子 agent 只看到主线程通过 `message` 或 `items` 显式交给它的内容。
- 子 agent 的上下文由 Context Librarian Agent 生成的最小上下文包决定。
- hidden truth 不得作为 `message`、`items`、附件、文件路径或摘要传给构建 agent。

仅在以下情况允许 `fork_context: true`：

- 用户明确要求复制主线程上下文。
- 子 agent 的任务是主线程上下文复盘，且不涉及 hidden truth。
- 主线程确认复制上下文不会污染实现。

EA v0.1 构建默认不使用 `fork_context: true`。

### 3.1.3 推荐 spawn 参数

信息探索类子任务：

```yaml
agent_type: explorer
fork_context: false
message: |
  你是 {agent_name}。
  只处理下面这个问题，不要扩展范围。
  允许读取：{allowed_files}
  禁止读取：{forbidden_files}
  输出：{expected_output}
```

代码实现类子任务：

```yaml
agent_type: worker
fork_context: false
message: |
  你是 {agent_name}。
  你不是唯一在代码库中工作的 agent，不要回滚他人的修改。
  你的写入范围：{owned_files_or_modules}
  允许读取：{allowed_files}
  禁止读取：{forbidden_files}
  必须遵守：{constraints}
  完成后列出修改文件、测试结果和风险。
```

模型选择：

- 不要默认覆盖模型；让子 agent 继承主线程模型。
- 只有任务非常简单或用户明确要求时，才考虑更小模型。

### 3.1.4 子 agent 生命周期

Main Orchestrator 必须维护一个简短 agent registry：

```yaml
agents:
  - agent_id:
    nickname:
    role:
    task:
    fork_context: false
    allowed_files: []
    forbidden_files: []
    write_scope: []
    status: running | completed | closed
```

规则：

- 任务完成并整合结果后，调用 `close_agent` 关闭不再需要的子 agent。
- 相关任务需要继续同一上下文时，使用 `send_input` 复用原 agent。
- 不要为同一 unresolved thread 反复创建重复子 agent。
- 不要让两个 worker 同时写同一个文件或模块。

### 3.1.5 并行与阻塞规则

可以并行 spawn：

- Architecture & Schema Agent 和 Review Workflow Agent 做互不重叠的探索。
- Raw Import Agent 和 Raman Pipeline Agent 分别调研 reader/import 边界。
- QA Reviewer Agent 在实现后做独立 review。

不应并行 spawn：

- 两个 worker 同时修改同一 schema 文件。
- 一个 worker 实现，另一个 worker 同时重构同一模块。
- evaluation agent 与构建 agent 同时读取同一 hidden truth 路径。

主线程在等待子 agent 时应继续做不重叠工作；只有下一步被该子 agent 结果阻塞时才 `wait_agent`。

### 3.1.6 文件写入隔离

代码实现类子 agent 必须有明确 write scope：

```yaml
write_scope:
  - src/ea/schema/
  - tests/test_schema.py
```

禁止：

- 未声明写入范围就让 worker 修改代码。
- worker 修改全景地图原则文件。
- worker 修改 hidden truth。
- worker 修改 raw 原始文件。
- worker 为了通过测试硬编码 test1。

### 3.1.7 无子 agent 工具时的 fallback

如果 Codex 新窗口没有可用 sub-agent 工具：

1. 仍可使用本文件作为组织协议，但不能声称已建立独立上下文 agent team。
2. 使用“多窗口 + 文件交付”替代：
   - 每个角色开独立 Codex 窗口。
   - 每个窗口只粘贴自己的角色说明和最小上下文包。
   - 每个窗口只能写入自己负责的文件范围。
   - 所有交付写入 `agent_handoffs/{role}/{timestamp}.md`。
3. Main Orchestrator 汇总 handoff 文件，而不是让各窗口互相共享完整上下文。
4. Evaluation 窗口单独建立，只给 hidden truth，不给构建代码修改权限。

fallback 的稳定性低于真实 `spawn_agent`，但仍可维持上下文隔离。

---

## 4. 主线程 Main Orchestrator

### 4.1 使命

主线程负责把 EA v0.1 从规格推进到可运行实现，并守住以下硬边界：

- 不做 Web/UI/移动端。
- 不做多项目管理。
- 不修改 raw 数据。
- 不跳过用户审核。
- 不让 EA 建议自动进入 decision log 或 progress。
- 不把 hidden truth 交给构建 agent。
- 不把 MoS2 test1 的答案硬编码进架构。

### 4.2 必读文件

按顺序读取：

1. `EA_AGENT_TEAM_BRIEF.md`
2. `EA_PRODUCT_CHARTER.md`
3. `EA_ARCHITECTURE_MAP.md`
4. `EA_AGENT_TEAM_PROTOCOL.md`
5. `EA_TEST_PROTOCOL.md`
6. `EA_SCHEMA_SPEC.md`
7. `EA_REVIEW_STATE_MACHINE.md`
8. `EA_RAW_IMPORT_SPEC.md`
9. `EA_RAMAN_V0_1_SPEC.md`
10. `EA_MEMORY_BOUNDARY_SPEC.md`
11. `EA_PROVENANCE_MINIMUM_SPEC.md`
12. `EA_V0_1_BUILD_PACKAGE_MANIFEST.md`
13. `EA_V0_1_GIT_WORKFLOW.md`
14. `EA_V0_1_PRE_BUILD_TODO.md`
15. `EA_V0_1_SKILL_SETUP.md`
16. 本文件 `EA_V0_1_AGENT_TEAM_SETUP.md`

### 4.3 主线程职责

- 建立 `task_plan.md`、`findings.md`、`progress.md`。
- 初始化 repo、目录、`.gitignore` 和测试结构。
- 按 `EA_V0_1_GIT_WORKFLOW.md` 创建 Stage 0 commit；remote 可用时按阶段 push。
- 按阶段分派任务给专家 agent。
- 为每个子 agent 提供最小必要上下文。
- 收集子 agent 输出，检查接口一致性。
- 要求子 agent 返工，而不是代替子 agent 猜测补齐。
- 在每个里程碑后运行测试。
- 在每个核心阶段后做 QA review。
- 向用户报告能做什么、不能做什么、做完了什么。

### 4.4 主线程不得做

- 不得把完整 hidden truth 放入构建上下文。
- 不得允许多个 agent 同时编辑同一个文件而无合并协议。
- 不得让 Raman/script agent 自行写科学结论到 memory。
- 不得让 Memory/provenance agent 自行决定用户是否已确认。
- 不得把 test1 public input 变成产品默认规则。

---

## 5. 子 Agent 配置

### 5.1 Context Librarian Agent

使命：

- 维护全景地图索引和规格索引。
- 给主线程和子 agent 提供“最小必要上下文包”。
- 防止 context 混入 hidden truth。

可读：

- 全部全景地图。
- P0 specs。
- 通用模板。
- public test 输入。

不可读：

- hidden truth。
- evaluation answer key。

交付：

```text
context-package:
  task:
  allowed_files:
  required_specs:
  forbidden_files:
  key_constraints:
  expected_output:
```

### 5.2 Architecture & Schema Agent

使命：

- 实现本地目录结构。
- 实现核心 schema / frontmatter / metadata 格式。
- 建立 ID 生成规则。
- 建立 Project、ProjectRuleCard、ExperimentRecord、SampleRecord、ReviewRecord、ProvenanceEntry、ProgressEvent、SuggestionRecord、OpenItem 的基础数据结构。

必读：

- `EA_SCHEMA_SPEC.md`
- `EA_ARCHITECTURE_MAP.md`
- `EA_REVIEW_STATE_MACHINE.md`
- `EA_MEMORY_BOUNDARY_SPEC.md`
- `EA_PROVENANCE_MINIMUM_SPEC.md`

交付：

- 文件路径和目录树。
- schema 定义。
- ID 生成策略。
- 最小读写接口。
- 单元测试。
- 与 P0 spec 的映射表。

禁止：

- 不实现数据库，除非用户另行确认。
- 不引入多项目管理。
- 不让 schema 依赖 test1 hidden truth。

### 5.3 Review Workflow Agent

使命：

- 实现用户审核状态机。
- 实现 review record 写入。
- 定义哪些对象必须 `needs_user_review`。
- 定义用户自然语言确认 / 修改 / 拒绝 / 延后的判定规则。

必读：

- `EA_REVIEW_STATE_MACHINE.md`
- `EA_SCHEMA_SPEC.md`
- `EA_MEMORY_BOUNDARY_SPEC.md`

交付：

- review 状态机实现。
- review record schema。
- 用户确认判定 helper。
- 测试用例：确认、模糊、修改、拒绝、延后。

禁止：

- 不把“可能吧”“先放着”“你觉得呢”当作确认。
- 不允许未确认内容进入正式实验记录、progress、confirmed findings 或 decision log。

### 5.4 Experiment Log & Sample Agent

使命：

- 实现自然语言实验日志结构化工作流。
- 管理实验记录和样品记录。
- 实现样品编号规则确认后的应用。
- 实现样品质量标准确认后的候选筛选。

必读：

- `EA_SCHEMA_SPEC.md`
- `EA_REVIEW_STATE_MACHINE.md`
- `EA_ARCHITECTURE_MAP.md`
- `ea-project-rule-card-template.md`

可读：

- test case public conversation。

不可读：

- hidden truth 中的正确结构化答案。
- hidden truth 中的样品质量标签。

交付：

- 实验日志 parser / structured draft 生成逻辑。
- 缺失字段追问规则。
- 保存前 review gate。
- sample index 生成和更新逻辑。
- 历史查询时的简短来源格式。
- 测试用例。

禁止：

- 不直接静默保存用户原话为正式 ExperimentRecord。
- 不把用户初步判断写成 confirmed finding。
- 不把 EA 自己的样品推荐写成用户决策。

### 5.5 Raw Import Agent

使命：

- 实现 raw 文件导入。
- 复制 raw 到受控只读副本。
- 计算 SHA-256。
- 记录原始路径、项目路径、文件大小、mtime、导入时间。
- 处理去重和 alias。

必读：

- `EA_RAW_IMPORT_SPEC.md`
- `EA_SCHEMA_SPEC.md`
- `EA_PROVENANCE_MINIMUM_SPEC.md`

交付：

- raw import API / CLI。
- metadata 写入。
- duplicate alias 逻辑。
- processed 输出不能写入 raw 的保护测试。
- hash 校验测试。

禁止：

- 不修改原始文件。
- 不覆盖 raw。
- 不把 processed data 写入 raw。

### 5.6 Raman Pipeline Agent

使命：

- 实现 Raman v0.1 数据读取、列识别、参数确认、处理、绘图、峰表和 metadata。

必读：

- `EA_RAMAN_V0_1_SPEC.md`
- `EA_RAW_IMPORT_SPEC.md`
- `EA_PROVENANCE_MINIMUM_SPEC.md`

可读：

- Raman public raw 文件。
- public 中用户声称的样品关联。

不可读：

- hidden truth 中的 Raman 文件真实映射答案。
- hidden truth 中的期望峰位答案。

交付：

- CSV/TXT/XLSX reader。
- header / no-header 检测。
- x/y column candidate 识别。
- column confirmation draft。
- processing parameter confirmation draft。
- processed CSV。
- peak table CSV。
- plot PNG。
- Raman metadata YAML/JSON。
- warning 规则。
- 单元测试和 test fixture。

禁止：

- 不自动把 PL 文件当 Raman 文件处理。
- 不编造仪器 metadata。
- 不单凭 Raman 写“证明单层”。
- 不让 LLM 直接解释 raw 曲线。

### 5.7 Report & Scientific Language Agent

使命：

- 生成中文 Raman 分析报告模板。
- 控制科学表达边界。
- 将 observation、processed result、interpretation、hypothesis、confirmed finding 分开写。

必读：

- `EA_PRODUCT_CHARTER.md`
- `EA_ARCHITECTURE_MAP.md`
- `EA_RAMAN_V0_1_SPEC.md`
- `EA_MEMORY_BOUNDARY_SPEC.md`

交付：

- report template。
- report generator 的输入/输出契约。
- 科学表达 checklist。
- 不确定性和 warning 展示规则。
- “不默认包含下一步建议”的检查。

禁止：

- 不使用“证明了”“机制已经确定”“毫无疑问”等强断言。
- 不编造文献。
- 不把报告草稿自动写入 memory。

### 5.8 Memory & Provenance Agent

使命：

- 实现 project memory。
- 实现 provenance。
- 实现 suggestion / decision / progress 数据层隔离。
- 实现 open-items。

必读：

- `EA_MEMORY_BOUNDARY_SPEC.md`
- `EA_PROVENANCE_MINIMUM_SPEC.md`
- `EA_REVIEW_STATE_MACHINE.md`
- `EA_SCHEMA_SPEC.md`

交付：

- memory 目录结构。
- confirmed-findings / open-questions / failed-attempts / decision-log 写入接口。
- progress event 写入接口。
- suggestion record 写入接口。
- provenance entry 写入接口。
- memory write 前后 hash 记录。
- 测试用例。

禁止：

- 不把 `suggestion.accepted` 自动变成 decision。
- 不把 EA 下一步建议自动变成 progress。
- 不把未确认 interpretation 写入 confirmed findings。

### 5.9 Test Harness Agent

使命：

- 设计和实现自动测试、模拟测试结构和验收脚本。
- 维护 public / hidden truth 隔离。
- 确保 EA 能通过 `test-case-001` 用户模拟测试。

必读：

- `EA_TEST_PROTOCOL.md`
- `EA_SCHEMA_SPEC.md`
- `EA_REVIEW_STATE_MACHINE.md`
- `EA_RAW_IMPORT_SPEC.md`
- `EA_RAMAN_V0_1_SPEC.md`
- `EA_MEMORY_BOUNDARY_SPEC.md`
- `EA_PROVENANCE_MINIMUM_SPEC.md`

可读：

- public test input。

不可读：

- hidden truth，除非该 agent 被明确指定为 evaluation agent 且不参与构建。

交付：

- `tests/` 结构。
- unit tests。
- integration tests。
- test fixture policy。
- public test runner。
- evaluation handoff instructions。

禁止：

- 不把 hidden truth 写入 repo 中构建 agent 可读区域。
- 不把 test1 的具体答案硬编码为通用产品规则。

### 5.10 QA Reviewer Agent

使命：

- 作为构建期独立 reviewer，检查实现是否违反 EA 原则。
- 可读构建代码、规格、public tests。
- 不读 hidden truth。

Review checklist：

- 是否修改 raw。
- 是否跳过用户确认。
- 是否缺少 review record。
- 是否缺少 provenance。
- 是否把 suggestion 写成 decision。
- 是否把 hypothesis 写成 confirmed finding。
- 是否引入 Web/UI 或多项目。
- 是否硬编码 test1。
- 是否让 LLM 直接解释 raw。
- 是否缺少测试。

交付格式：

```text
findings:
  - severity:
    file:
    line:
    issue:
    required_fix:
open_questions:
residual_risk:
```

### 5.11 Simulated User / Evaluation Agent

使命：

- 使用 public conversation 模拟真实用户。
- 持有 hidden truth 进行评分。
- 不参与实现。
- 不向构建 agent 泄露 hidden truth。

可读：

- public input。
- hidden truth。
- evaluation rubric。
- 被测 EA 输出。

不可做：

- 不修改代码。
- 不给构建 agent 透露正确答案。
- 不把 test1 答案变成架构建议。

交付：

- pass / pass_with_notes / fail_minor / fail_critical。
- 失败点。
- 对应 rubric。
- 是否违反 critical failure。

---

## 6. 推荐工作阶段

### Stage 0: Repo bootstrap

主线程负责：

- 建立 `EAv0.1-build/`。
- 初始化 Git。
- 创建 `.gitignore`。
- 创建 `docs/panorama/`、`docs/specs/`、`tests/`、`examples/`。
- 复制全景地图和 P0 spec。
- 确保 hidden truth、raw private data、token 不进入 Git。

### Stage 1: Core schema and local project

参与 agent：

- Architecture & Schema Agent。
- Review Workflow Agent。
- Memory & Provenance Agent。
- QA Reviewer Agent。

目标：

- 核心目录结构。
- Project / ProjectRuleCard。
- ReviewRecord。
- ProvenanceEntry。
- 最小测试。

### Stage 2: Experiment log and sample records

参与 agent：

- Experiment Log & Sample Agent。
- Review Workflow Agent。
- Memory & Provenance Agent。
- QA Reviewer Agent。

目标：

- 用户自然语言实验日志结构化。
- 追问缺失字段。
- 用户确认后保存。
- SampleRecord 和 sample index。
- 历史查询简短来源。

### Stage 3: Raw import

参与 agent：

- Raw Import Agent。
- Memory & Provenance Agent。
- QA Reviewer Agent。

目标：

- raw 受控只读副本。
- SHA-256。
- metadata。
- duplicate alias。
- raw / processed 边界测试。

### Stage 4: Raman pipeline

参与 agent：

- Raman Pipeline Agent。
- Raw Import Agent。
- Report & Scientific Language Agent。
- Memory & Provenance Agent。
- QA Reviewer Agent。

目标：

- TXT/CSV/XLSX 读取。
- x/y column candidate。
- 用户确认列和参数。
- processed CSV、peak table、plot、metadata。
- Raman workflow provenance。

### Stage 5: Report and memory

参与 agent：

- Report & Scientific Language Agent。
- Memory & Provenance Agent。
- QA Reviewer Agent。

目标：

- 中文报告。
- 科学解释审核。
- memory write review。
- suggestions / decision / progress 隔离。

### Stage 6: Evaluation

参与 agent：

- Test Harness Agent。
- Simulated User / Evaluation Agent。
- QA Reviewer Agent。
- Main Orchestrator。

目标：

- 使用 `test-case-001` 作为 v0.1 正式 test case。
- hidden truth 只给 Evaluation Agent。
- 输出 evaluation report。
- 对 fail_minor / fail_critical 进入修复循环。

---

## 7. 子任务分派模板

主线程给子 agent 分派任务时使用：

```text
你是 {agent_name}。

任务：
{task_goal}

必须阅读：
{allowed_docs}

允许读取：
{allowed_files}

禁止读取：
{forbidden_files}

必须遵守：
{constraints}

预期输出：
{expected_artifacts}

交付格式：
- 改动范围
- 涉及文件
- 输入
- 输出
- 与 EA spec 的对应关系
- 未实现内容
- 风险
- 测试方式
- 是否影响 v0.1 / future 边界

完成后不要自行扩展范围，等待主线程 review。
```

---

## 8. 子 Agent 交付格式

所有子 agent 交付必须使用：

```text
## Scope

## Files Changed

## Inputs Used

## Outputs Produced

## Spec Mapping

## Tests

## Risks

## Open Questions

## Handoff Notes
```

如果子 agent 写代码，必须说明：

- 新增/修改了哪些文件。
- 是否运行测试。
- 测试结果。
- 哪些行为尚未覆盖。
- 是否有 raw 数据安全风险。
- 是否需要主线程确认。

---

## 9. 上下文隔离规则

### 9.1 构建 agent 可读

- 全景地图。
- P0 specs。
- 通用模板。
- public test input。
- 脱敏样例。
- 构建代码。

### 9.2 构建 agent 不可读

- hidden truth。
- evaluation answer key。
- 样品质量隐藏标签。
- Raman 文件真实映射答案。
- 期望峰位答案。
- final scoring notes。

### 9.3 Evaluation agent 可读

- public test input。
- hidden truth。
- 被测 EA 输出。
- evaluation rubric。

### 9.4 Evaluation agent 不可做

- 不参与实现。
- 不写产品代码。
- 不把 hidden truth 反馈成“实现建议”。

---

## 10. 返工与 review 协议

主线程在以下情况必须要求返工：

- 输出缺少 spec mapping。
- 未说明测试。
- 修改 raw 或可能修改 raw。
- 缺少 provenance。
- 缺少 review record。
- 把用户未确认内容写入正式记录。
- 把建议写成决策。
- 把假设写成 confirmed finding。
- 引入 Web/UI、多项目、大规模 RAG、完整 freeze restore 等 v0.1 非目标。
- 使用 test1 hidden truth 或疑似硬编码 test1。

返工指令格式：

```text
Return to {agent_name}.

Issue:
{specific_issue}

Required fix:
{required_fix}

Do not change:
{protected_files_or_boundaries}

Return with:
{expected_return_format}
```

---

## 11. 推荐启动提示

正式构建 EA v0.1 的新窗口可以使用：

```text
你是 EA v0.1 构建工作的 Main Orchestrator。

请先读取以下文件：
1. docs/EA_V0_1_BUILD_PACKAGE_MANIFEST.md
2. docs/panorama/EA_AGENT_TEAM_BRIEF.md
3. docs/panorama/EA_PRODUCT_CHARTER.md
4. docs/panorama/EA_ARCHITECTURE_MAP.md
5. docs/panorama/EA_AGENT_TEAM_PROTOCOL.md
6. docs/panorama/EA_TEST_PROTOCOL.md
7. docs/specs/EA_SCHEMA_SPEC.md
8. docs/specs/EA_REVIEW_STATE_MACHINE.md
9. docs/specs/EA_RAW_IMPORT_SPEC.md
10. docs/specs/EA_RAMAN_V0_1_SPEC.md
11. docs/specs/EA_MEMORY_BOUNDARY_SPEC.md
12. docs/specs/EA_PROVENANCE_MINIMUM_SPEC.md
13. docs/EA_V0_1_GIT_WORKFLOW.md
14. docs/EA_V0_1_PRE_BUILD_TODO.md
15. docs/EA_V0_1_SKILL_SETUP.md
16. docs/EA_V0_1_AGENT_TEAM_SETUP.md

你的第一步不是写代码，而是：
- 总结 EA v0.1 北极星。
- 按 build package manifest 确认哪些文件可读、哪些只给 Evaluation Agent。
- 按 Git workflow 检查 repo、branch、`.gitignore`、remote、Stage 0 commit 和 push 状态。
- 使用 tool discovery 查找 multi-agent / sub-agent 工具。
- 如果存在 `multi_agent_v1.spawn_agent` 等工具，按本文件 3.1 节建立真实子 agent；默认 `fork_context: false`。
- 如果没有可用子 agent 工具，明确告诉用户无法自动建立独立上下文子 agent，并按 fallback 方案使用多窗口 + 文件交付。
- 建立 agent team registry，记录每个子 agent 的 role、task、allowed_files、forbidden_files、write_scope、fork_context。
- 读取 `EA_V0_1_SKILL_SETUP.md`，说明哪些 skill 已安装、哪些按需启用、哪些不进入 v0.1 默认流程。
- 读取 `EA_V0_1_GIT_WORKFLOW.md`，说明当前是否能 push；不能 push 时不要声称已上传。
- 输出 Stage 0-1 的执行计划。
- 明确哪些 agent 可以读取哪些文件。
- 明确 hidden truth 不给构建 agent。

硬性限制：
- 不实现 Web/UI。
- 不做多项目管理。
- 不修改 raw 数据。
- 不跳过用户审核。
- 不让 EA 建议自动进入项目决策。
- 不让未确认科学解释进入 confirmed findings。
- 不读取 hidden truth，除非你正在扮演独立 evaluation agent。
- 不使用 `fork_context: true`，除非用户明确要求或你已确认不会污染构建上下文。
```

---

## 12. 最低完成定义

agent team 配置生效的最低标准：

- 主线程能说明每个 agent 的职责。
- 主线程已检查是否存在 sub-agent 工具。
- 如存在 sub-agent 工具，主线程已用 `fork_context: false` 建立至少一个真实子 agent，并维护 agent registry。
- 如不存在 sub-agent 工具，主线程已明确告知用户限制，并启用多窗口 + 文件交付 fallback。
- 子 agent 收到任务时只看必要上下文。
- hidden truth 与构建上下文隔离。
- 每个子 agent 有固定交付格式。
- 每个阶段都有 QA review。
- 每个重要输出都有 review/provenance 要求。
- 任何违反 EA 北极星的实现都能被主线程拦截。

EA v0.1 实现完成的最低标准仍以 `EA_AGENT_TEAM_PROTOCOL.md` 第 15 节为准。
