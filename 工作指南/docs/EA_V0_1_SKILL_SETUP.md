# EA v0.1 Skill Setup

> 用途：正式构建 EA v0.1 前的 skill 筛选、安装和分配建议。  
> 日期：2026-06-02  
> 状态：pre-build skill config  
> 适用对象：Main Orchestrator、Context Librarian Agent、各构建子 agent。  

---

## 1. 结论

我不能凭记忆知道“当前最新、最热门”的 skill；skill 生态变化很快。因此本轮使用了：

- `npx skills check`
- `npx skills find ...`
- skills.sh / GitHub 搜索
- 本地已安装 skill 列表

综合判断：

- EA v0.1 的核心构建不需要大量新 skill。
- 当前已有的 `planning-with-files`、`diagnose`、`tdd`、`improve-codebase-architecture`、`handoff`、`pdf`、`jupyter-notebook`、`security-best-practices`、GitHub 系列 skill 已经覆盖大部分工程构建需求。
- 真正值得补的是科学/材料/科研图表/文献方向，因此已安装 `K-Dense-AI/scientific-agent-skills`。
- 但 K-Dense 是大科学技能库，不能让所有 agent 默认泛用；EA v0.1 只按需启用其中少数与 Raman、科学数据、图表、文献有关的 skill。

---

## 2. 已执行动作

### 2.1 Skills CLI 状态

确认：

```text
skills CLI latest: 1.5.9
```

执行过：

```bash
npx skills check
```

该命令更新了 5 个已安装 skill：

- `grill-with-docs`
- `improve-codebase-architecture`
- `prototype`
- `to-prd`
- `handoff`

### 2.2 已安装科学技能库

已执行：

```bash
npx skills add K-Dense-AI/scientific-agent-skills
```

实际结果：

```text
installed path: .agents/skills/
skill count: 143
size: 22M
lock file: skills-lock.json
```

说明：

- 该库来自 [K-Dense-AI/scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills)。
- GitHub 搜索显示该 repo 约 26K stars、2.7K forks，README 称包含 138+ scientific / research skills，支持 Codex。
- 本次安装结果为 143 个 skill。
- 安装位置是当前工作区的 `.agents/skills/`，不是全局 `~/.agents/skills/`。
- `skills-lock.json` 记录了每个安装 skill 的来源、路径和 hash，可用于复核安装内容。

注意：

- 如果正式 EA v0.1 构建目录不是当前目录，Main Orchestrator 应在正式构建目录中重新执行安装，或复制 `.agents/skills/`。
- 不建议把 K-Dense 全部 skill 当作 EA v0.1 默认上下文；只在相关子 agent 任务触发时按需使用。

---

## 3. 不建议安装的候选

以下候选已搜索但不建议安装：

| 查询方向 | 候选 | 判断 |
|---|---|---|
| `python testing pytest` | `bobmatnyc/claude-mpm-skills@pytest`，约 905 installs | 安装量不到 1K，非官方；EA 已有 `tdd`，不装 |
| `raman spectroscopy` | `letta-ai/skills@raman-fitting`，约 34 installs | 名字贴合但安装量太低；EA v0.1 不做复杂峰拟合，不装 |
| `scientific data analysis python` | 社区 EDA skill，约 1.4K installs | 被 K-Dense 的 `exploratory-data-analysis` 覆盖，不单独装 |
| `code review architecture best practices` | 多个 code-review skill，多数 <500 installs | 质量和安装量不足；已有 `improve-codebase-architecture`、`diagnose`、`tdd`，不装 |
| `documentation handoff agent` | session handoff skill，约 223 installs | 已有 `handoff` 且刚更新，不装 |
| `multi agent orchestration` | `qodex-ai/ai-agent-skills@multi-agent-orchestration`，约 1.6K installs | 非官方来源；EA 已有自定义 agent-team protocol 和 Codex `spawn_agent`，不装 |

---

## 4. 推荐 Skill 分配

### 4.1 Main Orchestrator

默认使用：

- `planning-with-files`
- `handoff`
- `diagnose`

按需使用：

- `improve-codebase-architecture`：阶段性架构复核时。
- GitHub 系列 skill：需要提交 PR、处理 CI、发布时。

不要默认使用：

- K-Dense 全科学技能库。
- 文献/数据库 skill，除非用户明确进入文献或知识库任务。

### 4.2 Context Librarian Agent

默认使用：

- `planning-with-files`
- `handoff`
- `markdown-mermaid-writing`，仅当需要生成结构图或上下文包图示时。

职责：

- 给子 agent 准备最小上下文包。
- 不把 hidden truth 放进任何构建 agent 的上下文。

### 4.3 Architecture & Schema Agent

默认使用：

- `tdd`
- `improve-codebase-architecture`

按需使用：

- `diagnose`，当 schema 测试或数据写入失败时。

不要使用：

- K-Dense 科学技能库。Schema 架构不应被科学库牵引。

### 4.4 Review Workflow Agent

默认使用：

- `tdd`

按需使用：

- `diagnose`

重点：

- 用户确认判定、状态机转换、review record 写入必须测试先行。

### 4.5 Experiment Log & Sample Agent

默认使用：

- `tdd`
- `diagnose`

按需使用：

- `markdown-mermaid-writing`，用于实验/样品实体关系图。

不要使用：

- K-Dense 的材料/数据库 skill 来替代用户确认。
- 任何会把 test1 hidden truth 推成通用规则的 skill。

### 4.6 Raw Import Agent

默认使用：

- `tdd`
- `diagnose`

按需使用：

- K-Dense `xlsx`：当 raw 或用户材料涉及 Excel / XLSX 时。
- K-Dense `exploratory-data-analysis`：仅用于预览科学数据文件结构，不用于生成正式结论。

重点：

- raw import 的核心仍是本地 deterministic code、hash、metadata 和只读边界。

### 4.7 Raman Pipeline Agent

默认使用：

- `tdd`
- `diagnose`
- K-Dense `matplotlib`
- K-Dense `scientific-visualization`

按需使用：

- K-Dense `exploratory-data-analysis`：用于检查 TXT/CSV/XLSX 文件结构和数据质量。
- K-Dense `xlsx`：读取或转换 Excel 格式 Raman 数据。
- `jupyter-notebook`：只在需要交互式探索 notebook 时使用，不作为 v0.1 默认产物。

不要使用：

- `raman-fitting` 低安装量候选 skill。
- 复杂拟合/自动层数判断 skill。

### 4.8 Report & Scientific Language Agent

默认使用：

- K-Dense `scientific-visualization`
- K-Dense `citation-management`
- K-Dense `paper-lookup`

按需使用：

- K-Dense `literature-review`：只在用户要求系统文献综述时使用。
- K-Dense `markdown-mermaid-writing`：报告需要流程图/架构图时。
- `pdf`：如果要输出或检查 PDF。

重点：

- 文献 skill 只能用于找来源和管理引用，不能把搜索结果直接写成 confirmed finding。

### 4.9 Memory & Provenance Agent

默认使用：

- `planning-with-files`
- `tdd`
- `diagnose`

按需使用：

- `handoff`：阶段交接。

不要使用：

- 文献/科学数据库 skill 自动写入 memory。

### 4.10 Test Harness Agent

默认使用：

- `tdd`
- `diagnose`

按需使用：

- `jupyter-notebook`：若要生成测试探索 notebook。
- K-Dense `exploratory-data-analysis`：用于生成测试数据结构报告。

重点：

- Test Harness Agent 不读 hidden truth，除非被明确改为 Evaluation Agent 且不参与构建。

### 4.11 QA Reviewer Agent

默认使用：

- `diagnose`
- `tdd`
- `improve-codebase-architecture`

按需使用：

- `security-best-practices`：只有用户明确要求安全审查时使用。

不要使用：

- hidden truth。
- K-Dense 大科学技能库，除非 review 的对象是科学图表/报告。

### 4.12 Simulated User / Evaluation Agent

默认使用：

- 不需要额外工程 skill。

按需使用：

- `diagnose`：如果评估流程失败。
- K-Dense `matplotlib` / `scientific-visualization`：如果需要独立复核 Raman 图谱输出质量。

隔离：

- 可读 hidden truth。
- 不参与代码实现。
- 不把 hidden truth 反馈成实现规则。

---

## 5. K-Dense Skill 使用白名单

EA v0.1 推荐白名单：

- `matplotlib`
- `scientific-visualization`
- `exploratory-data-analysis`
- `xlsx`
- `citation-management`
- `paper-lookup`
- `database-lookup`
- `markdown-mermaid-writing`
- `literature-review`
- `pymatgen`
- `sympy`

其中：

- `matplotlib` / `scientific-visualization`：Raman plot 和科研图表。
- `exploratory-data-analysis`：raw 文件结构预览。
- `xlsx`：Excel 数据。
- `citation-management` / `paper-lookup`：文献和 DOI。
- `database-lookup`：后续知识库或材料数据库查询；v0.1 不默认联网查库。
- `pymatgen`：后续材料科学扩展；v0.1 仅作为材料学工具候选。
- `sympy`：需要公式或符号计算时。

EA v0.1 不推荐默认使用：

- 临床、医学诊断、药物发现、生物组学、量子计算、金融、自动实验室设备集成等与 MoS2/Raman v0.1 无直接关系的 K-Dense skill。

---

## 6. 给正式构建窗口的执行要求

Main Orchestrator 启动后应先检查：

```bash
find .agents/skills -maxdepth 1 -mindepth 1 -type d | wc -l
```

如果结果约为 `143`，说明当前工作区已有 K-Dense scientific skills。

如果正式构建目录中没有 `.agents/skills/`，可选择：

```bash
npx skills add K-Dense-AI/scientific-agent-skills
```

或将本工作区的 `.agents/skills/` 复制到正式构建目录。

注意：

- 不要为了“技能多”而默认加载全部 K-Dense skill。
- 子 agent 只有在任务触发时才读取对应 `SKILL.md`。
- 每次使用外部 scientific skill 后，应在交付中说明用了哪个 skill、用于什么、是否影响 v0.1/future 边界。

---

## 7. 最终建议

当前推荐：

- 必装/已装：`K-Dense-AI/scientific-agent-skills`，但白名单式按需使用。
- 已有且应继续使用：`planning-with-files`、`diagnose`、`tdd`、`improve-codebase-architecture`、`handoff`、`pdf`、`jupyter-notebook`、`security-best-practices`、GitHub 系列 skill。
- 暂不安装：低安装量 pytest/code-review/Raman fitting/orchestration 社区 skill。

EA v0.1 的关键不是技能数量，而是：

- schema 和测试硬。
- raw 数据边界硬。
- review/provenance 硬。
- 科学解释审慎。
- 子 agent 只拿最小必要上下文。
