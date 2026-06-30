# Experimental Assistant (EA) 项目简报：Agent-Native Skill 版

> 版本：v0.2-agent-native-draft  
> 日期：2026-05-11  
> 目标读者：Claude Code、Codex 或其他 coding agent，以及参与 EA 设计和实现的人类协作者。  
> 相关文档：`docs/ea-new-direction-zh.md`

---

## 1. EA 是什么

**Experimental Assistant（EA，实验助手）** 是一个本地优先、人机协作、面向实验科学研究者的 Agent-native 科研 skill 系统，首个应用场景从材料科学和 Raman 数据分析切入。

一句话概括：

**EA 帮助实验科学研究者通过现有 agent 组织实验日志、处理原始数据、调用模块化科学子 skill、生成可追溯分析报告，并维护本地项目主线记忆。**

EA 的确定形态是一个综合型 skill 包，运行在 Claude Code、Codex 等现有 agent 环境中。当前项目不再规划 Web、UI 或其他前端产品形态。

---

## 2. EA 不是什么

EA 不是：

- 完全自主的科学家
- 独立 Web 应用或前端产品
- 单一巨大提示词
- 只会聊天的 AI 窗口
- 只会跑脚本的工具集合
- 实验室设备控制器
- 自动做实验决策的系统
- 会修改原始数据的处理程序

**原始数据绝不能被修改。**

---

## 3. 核心目标

EA v0.1 的目标是跑通一个最小但完整的科研闭环：

```text
用户提交实验日志
→ EA 结构化实验日志并保存到本地
→ 用户审核结构化字段
→ 用户提交 Raman 原始数据
→ EA 读取数据并提出处理方案
→ 用户确认数据列和处理参数
→ EA 运行 Raman 分析
→ EA 输出图谱、峰表、处理后数据、草稿解释
→ 用户审核科学解释
→ EA 生成分析报告
→ 用户确认是否写入项目记忆
→ EA 保存报告、确认结论和溯源记录
```

这个闭环的关键不是功能数量，而是：

- 原始数据安全
- 数据处理可复现
- 科学解释审慎
- 用户审核可追踪
- 本地项目记忆可长期积累

---

## 4. 五大核心原则

| # | 原则 | 含义 |
|---|---|---|
| 1 | 人机协作优先 | AI 辅助而不替代研究者，关键判断必须由用户确认 |
| 2 | Agent-native | 依赖 Claude Code、Codex 等现有 agent 运行，项目形态确定为 skill 包 |
| 3 | 以实验为中心 | 基本单位是项目、实验、样品、材料体系、原始数据和处理结果 |
| 4 | 可追溯性 | 每个重要输出都保留来源链条：文件、脚本、参数、技能、结果、审核决策 |
| 5 | 本地优先 | 数据本地保存，原始文件只读，研究者掌握控制权 |

---

## 5. 核心竞争力

EA 的核心竞争力不是通用 AI 对话能力，而是**从实验科学研究者专业视角设计科研工作流**。

EA 必须理解和尊重：

- 真实实验记录习惯
- 样品编号和材料体系之间的关系
- 工艺条件对表征结果的影响
- 表征数据处理的可复现性要求
- 科学解释中的证据等级
- 失败实验和异常数据的长期价值
- 科研图表、报告和语言的专业规范

EA 的评价标准：

- 研究者是否觉得它可靠
- 研究者是否觉得它准确
- 研究者是否愿意长期使用
- 它是否减少低价值整理工作
- 它是否帮助研究者找回实验线索
- 它是否避免把假设包装成结论

---

## 6. 科研审美与表达规则

EA 的科研审美不是装饰性的视觉风格，而是专业、克制、可信、可复用的整体感。

### 6.1 图表规则

- 图表必须包含标题、坐标轴、单位和必要图例
- Raman 位移单位必须标注为 `cm^-1`
- 峰位标注应清晰但不遮挡数据
- 原始数据、处理后数据、拟合或峰识别结果应明确区分
- 如果使用平滑、归一化、基线校正，必须记录参数
- 不使用花哨、营销式或装饰性图表风格

### 6.2 报告语言规则

推荐表达：

- “可能表明”
- “与……一致”
- “可能与……相关”
- “需要进一步确认”
- “在当前数据范围内”
- “该解释仍需结合其他表征验证”

禁止或谨慎使用：

- “这证明了”
- “这确认了”
- “这个机制是确定的”
- “毫无疑问”
- “可以完全说明”

### 6.3 科学解释规则

EA 必须始终区分：

- 观察结果
- 计算结果
- 数据处理结果
- 文献支持
- 可能解释
- 待验证假设
- 用户确认结论

未经用户审核的解释不能写入长期项目记忆中的已确认发现。

---

## 7. 领域实体

EA 理解和操作以下核心实体：

| 实体 | 说明 |
|---|---|
| Project | 顶层研究项目容器 |
| Experiment | 结构化实验记录 |
| Sample | 物理样品，包含样品 ID |
| Material System | 材料体系，例如 MoS2 |
| Process Condition | 温度、时间、气氛、功率、基底等实验参数 |
| Characterization File | Raman、PL、XRD 等原始表征文件，只读 |
| Data Processing Result | 图表、峰表、处理后 CSV、元数据、摘要 |
| Report | Markdown/HTML 分析报告，必须包含溯源 |
| Project Memory | 项目主线记忆，包括确认发现、开放问题和失败尝试 |
| Review Decision | 用户在审核节点做出的确认、编辑、拒绝或延后 |
| Skill | 已注册、可调用的功能单元 |

实体关系：

```text
Project
├── Experiment
│   ├── Sample
│   │   └── Material System
│   ├── Process Condition
│   ├── Characterization File
│   │   └── Data Processing Result
│   ├── Report
│   └── Review Decision
├── Project Memory
└── Provenance Records

Skill
└── produces Data Processing Result / Report / Memory Update
```

审核状态流转：

```text
draft → needs_review → user_confirmed | user_rejected | user_edited → archived
```

---

## 8. Agent-Native 架构

EA 是一个综合型 skill 包，内部由总控和子 skill 组成。

### 8.1 架构层次

```text
EA Skill
├── EA Orchestrator
├── Sub-skills
│   ├── experiment_log
│   ├── generic_data_plot
│   ├── raman_analysis
│   ├── report_generation
│   ├── project_memory
│   └── provenance
├── Deterministic scripts
│   ├── data readers
│   ├── plotting scripts
│   ├── peak detection scripts
│   └── metadata writers
├── Knowledge files
│   ├── scientific language rules
│   ├── Raman analysis guidance
│   └── material-system notes
└── Templates
    ├── experiment record template
    ├── report template
    └── review record template
```

### 8.2 子 skill 职责

| 子 skill | 职责 |
|---|---|
| `experiment_log` | 解析自由文本实验日志，生成结构化实验记录 |
| `generic_data_plot` | 读取 CSV/TXT/XLSX，预览数据列，用户确认后绘图 |
| `raman_analysis` | 处理 Raman 数据，生成图谱、峰表、处理元数据和审慎解释草稿 |
| `report_generation` | 生成带溯源的 Markdown/HTML 报告 |
| `project_memory` | 管理项目主线记忆，区分确认发现、开放问题和失败尝试 |
| `provenance` | 记录输入、输出、参数、技能版本、审核决策和警告 |

### 8.3 重要架构约束

- 不要把 EA 做成一个巨大 prompt
- 不要设计或实现 Web、UI、移动端等前端产品形态
- 不要让 LLM 直接自由解释原始数据
- 数据处理优先使用确定性 Python 脚本
- LLM 只基于结构化结果和明确证据边界生成解释
- 所有审核结果必须写入本地文件

---

## 9. 本地项目结构

建议 EA 项目目录结构：

```text
ea-project/
├── EA_PROJECT.md
├── experiments/
├── raw/
├── processed/
├── reports/
├── memory/
└── provenance/
```

### 9.1 目录职责

| 路径 | 职责 |
|---|---|
| `EA_PROJECT.md` | 项目总览、研究目标、材料体系、当前进展 |
| `experiments/` | 每个实验的结构化记录 |
| `raw/` | 原始文件，只读，不允许覆盖 |
| `processed/` | 处理后数据、图谱、峰表、元数据 |
| `reports/` | 分析报告和阶段报告 |
| `memory/` | 项目主线记忆 |
| `provenance/` | 工作流运行记录、审核记录、参数和输出索引 |

### 9.2 项目记忆结构

```text
memory/
├── project-summary.md
├── confirmed-findings.md
├── open-questions.md
├── failed-attempts.md
├── material-system-notes.md
└── decision-log.md
```

规则：

- `confirmed-findings.md` 只能写入用户确认后的发现
- `open-questions.md` 存放待验证假设和后续问题
- `failed-attempts.md` 记录失败实验、异常结果和无效参数
- `decision-log.md` 记录用户做出的方向性判断
- 每条记忆必须能追溯到实验、报告或 provenance 记录

---

## 10. v0.1 工作流

### 10.1 实验日志结构化

输入：

- 用户自由文本实验日志
- 可选样品 ID
- 可选日期
- 可选关联数据文件路径

输出：

- 结构化实验记录
- 审核请求
- provenance 初始记录

EA 应提取：

- 实验日期
- 样品 ID
- 材料体系
- 工艺条件
- 实验目的
- 观察结果
- 关联文件
- 不确定字段

### 10.2 Raman 原始数据处理

输入：

- Raman 原始数据文件，CSV/TXT/XLSX
- 用户确认的数据列
- 用户确认或默认的数据处理参数

输出：

- Raman 图谱
- 峰表
- 处理后 CSV
- 元数据 JSON/YAML
- 处理警告
- 审慎分析草稿

处理步骤：

1. 读取文件
2. 检测表头、列名、数据范围和潜在单位
3. 请求用户确认 x/y 列
4. 展示默认处理参数
5. 请求用户确认参数
6. 执行处理
7. 绘图
8. 检峰
9. 输出峰表与元数据
10. 生成审慎解释草稿

### 10.3 报告生成

报告必须包含：

1. 实验背景
2. 样品与工艺条件
3. 原始数据来源
4. 数据处理方法
5. Raman 图谱和峰表
6. 主要观察结果
7. 可能解释
8. 不确定性和限制
9. 下一步建议
10. 溯源记录

### 10.4 项目记忆更新

写入项目记忆前，EA 必须请求用户确认。

可写入内容包括：

- 已确认发现
- 开放问题
- 待验证假设
- 失败尝试
- 关键用户决策

未经确认的解释只能写入草稿、报告待审核区或 open questions，不能写入 confirmed findings。

---

## 11. 强制审核节点

EA 在以下节点必须停下来请求用户输入：

| # | 审核节点 | 审核内容 |
|---|---|---|
| 1 | 任务计划审核 | 多步工作流执行前展示计划和预期输出 |
| 2 | 字段审核 | 实验日志结构化后展示可编辑字段 |
| 3 | 数据列审核 | 读取数据文件后确认 x/y 列和单位 |
| 4 | 参数审核 | 确认平滑、归一化、基线校正、检峰参数 |
| 5 | 科学解释审核 | 区分观察、计算、解释、假设和结论 |
| 6 | 记忆写入审核 | 写入长期项目记忆前征得用户同意 |

审核记录示例：

```yaml
review_id: review-20260511-001
target_type: raman_interpretation
target_file: reports/exp-001-raman-report.md
review_status: user_confirmed
decision: accepted_with_edits
reviewed_at: 2026-05-11
notes: 用户确认主要峰位，但要求删除关于缺陷浓度变化的强推断。
```

---

## 12. 数据与存储规则

1. 原始数据只能读取，不能覆盖或改写
2. 处理后文件必须写入 `processed/`
3. 报告必须写入 `reports/`
4. 每个处理结果必须有元数据文件
5. 每个工作流必须有 provenance 记录
6. 每个用户审核决定必须保存
7. 每个科学解释必须有审核状态
8. 假设不能被存储为已确认事实
9. 用户修改后的内容优先于 agent 原始输出
10. 所有长期记忆都必须可追溯

---

## 13. 子 Skill 返回结构

每个子 skill 应返回标准结构，便于 EA Orchestrator 统一处理。

示例：

```json
{
  "status": "success",
  "skill_name": "raman_analysis",
  "skill_version": "0.1.0",
  "inputs": {
    "raw_file": "raw/exp-001/sample-a-raman.csv"
  },
  "outputs": {
    "figure": "processed/exp-001/raman_plot.png",
    "peaks": "processed/exp-001/raman_peaks.csv",
    "processed_data": "processed/exp-001/raman_processed.csv",
    "summary": "processed/exp-001/raman_summary.md",
    "metadata": "processed/exp-001/raman_metadata.json"
  },
  "parameters": {
    "baseline_correction": "none",
    "normalization": "max_intensity",
    "smoothing": "none",
    "peak_detection": "scipy_find_peaks"
  },
  "warnings": [
    "峰位解释需要用户审核。",
    "当前结果不能单独用于确认材料相变。"
  ],
  "requires_user_review": true
}
```

---

## 14. v0.1 成功标准

EA v0.1 成功的标准是：

1. 能初始化一个本地 EA 项目目录
2. 能接收自由文本实验日志
3. 能生成结构化实验记录
4. 能请求用户审核和编辑实验字段
5. 能保存审核后的实验记录
6. 能接收 Raman 原始数据文件
7. 能读取数据并请求用户确认列和参数
8. 能生成 Raman 图谱、峰表和处理后数据
9. 能生成审慎的 Raman 分析报告
10. 能请求用户审核科学解释
11. 能把确认后的结果写入项目主线记忆
12. 能保存完整 provenance
13. 不修改任何原始数据

---

## 15. v0.1 不做

- Web、UI、移动端或其他前端产品设计
- 云部署
- 多用户权限系统
- 实验室设备控制
- 自动实验决策
- 大规模 RAG
- 自动在线论文搜索
- 大量表征模块并行开发
- 复杂数据库设计
- 模型微调

---

## 16. 后续版本方向

后续方向必须在 v0.1 闭环稳定后再启动。

### 16.1 技能扩展

- XRD 分析
- PL 光谱
- AFM 分析
- 电化学数据处理
- SEM/TEM 图像标注
- 批量实验对比

### 16.2 文献与知识增强

- 本地文献摘要
- 本地文献问答
- 领域知识 Markdown
- Raman 分析知识库
- 材料体系知识文件

### 16.3 置信度校准与评审

建议路径：

1. 先写领域知识文件
2. 再构建 reviewer skill
3. 让 reviewer skill 检查分析结论
4. 标注证据等级、置信度和过度推断风险
5. 用评审反馈迭代 EA 的 prompt、脚本和报告模板

不建议在早期直接做模型微调，除非已经有明确数据集、评估标准和训练资源。

### 16.4 Skill 工作流增强

后续优化仍应围绕 skill 能力、文件系统工作流和 agent 协作展开，不把 Web、UI、移动端或其他前端产品形态作为当前项目路线。

可考虑的增强方向：

- 文件夹监听自动导入
- 组会报告草稿
- 项目进展总结
- 更稳定的项目记忆维护
- 更完整的 provenance 索引和查询

---

## 17. 对后续 Agent 的工作准则

任何继续实现 EA 的 agent 都必须遵守：

1. 先理解 `docs/ea-new-direction-zh.md`
2. 以 Agent-native skill 为首版目标
3. 保留本地优先和原始数据只读
4. 保留所有强制审核节点
5. 把计算处理和 LLM 解释分开
6. 用确定性脚本处理数据
7. 用审慎语言生成科学解释
8. 把审核结果写入文件
9. 把项目记忆分层维护
10. 每个输出都要有溯源
11. 不要规划或实现 Web、UI、移动端等前端形态
12. 不要过度架构化
13. 不要把 EA 简化成聊天机器人
14. 不要把未经确认的假设写成事实

EA 的首要任务是成为一个可靠、准确、可追溯、符合科研工作流和科研审美的实验助手 skill。
