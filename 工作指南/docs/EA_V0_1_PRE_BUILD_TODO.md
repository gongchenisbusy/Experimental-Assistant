# EA v0.1 正式搭建前 TODO

> 用途：正式开启 EA v0.1 agent team 搭建前的准备清单。  
> 状态：开工前 checklist。  
> 说明：本文件不替代全景地图，只用于开工准备。

---

## 1. Git 仓库准备

- [ ] 新建 EA v0.1 实现目录，例如 `EAv0.1-build/`。
- [ ] 初始化 Git 仓库。
- [ ] 创建 `.gitignore`。
- [ ] 确认 raw 数据、hidden truth、私密文献、账号/token 不进入 Git。
- [ ] 按 `EA_V0_1_GIT_WORKFLOW.md` 创建 Stage 0 初始 commit 和 tag。
- [ ] 每个阶段完成后 commit；remote 可用时 push。
- [ ] 如需远程备份，创建 GitHub private repo。
- [ ] 规划分支策略，例如：

```text
main
codex/schema
codex/experiment-log
codex/raw-import
codex/raman-analysis
codex/memory-provenance
codex/tests
```

---

## 2. 正式 Map 文件准备

按 `EA_V0_1_BUILD_PACKAGE_MANIFEST.md` 将以下文件放入新实现目录。全景地图目录例如：

```text
docs/panorama/
```

必须准备：

- [ ] `EA_AGENT_TEAM_BRIEF.md`
- [ ] `EA_PRODUCT_CHARTER.md`
- [ ] `EA_ARCHITECTURE_MAP.md`
- [ ] `EA_AGENT_TEAM_PROTOCOL.md`
- [ ] `EA_TEST_PROTOCOL.md`

P0 实现规格：

- [ ] `EA_SCHEMA_SPEC.md`
- [ ] `EA_REVIEW_STATE_MACHINE.md`
- [ ] `EA_RAW_IMPORT_SPEC.md`
- [ ] `EA_RAMAN_V0_1_SPEC.md`
- [ ] `EA_MEMORY_BOUNDARY_SPEC.md`
- [ ] `EA_PROVENANCE_MINIMUM_SPEC.md`

辅助模板：

- [ ] `EA_V0_1_BUILD_PACKAGE_MANIFEST.md`
- [ ] `ea-project-rule-card-template.md`
- [ ] `ea-test-experiment-template.md`
- [ ] `EA_IMPLEMENTATION_SPEC_TODO.md`
- [ ] `EA_V0_1_AGENT_TEAM_SETUP.md`
- [ ] `EA_V0_1_GIT_WORKFLOW.md`
- [ ] `EA_V0_1_SKILL_SETUP.md`

---

## 3. Agent Team 设置

建议至少设置以下角色：

- [ ] Main orchestrator：主线程，总控全景地图、任务拆分、范围控制和 review。
- [ ] Architecture agent：目录结构、schema、项目规则卡、review/provenance/progress。
- [ ] Raman/script agent：Raman 文件读取、列确认、参数确认、处理、绘图、metadata。
- [ ] Memory/provenance agent：project memory、suggestion/decision/progress 隔离、provenance。
- [ ] Documentation/test agent：测试样本、验收标准、模拟用户流程、文档一致性。
- [ ] Evaluation agent：可选，持有 hidden truth，只负责评估，不参与构建。

隔离规则：

- [ ] 构建 agent 不看 hidden truth。
- [ ] evaluation agent 可看 hidden truth。
- [ ] test 样本答案不能反馈成可硬编码规则。

---

## 4. Skill / 工作方式准备

建议启用或遵守：

- [ ] `planning-with-files`：维护 `task_plan.md`、`findings.md`、`progress.md`。
- [ ] `diagnose`：调试失败、解析错误、Raman 处理问题时使用。
- [ ] `tdd`：schema、raw import、review state machine、Raman parser 建议测试先行。
- [ ] `improve-codebase-architecture`：阶段性架构复核时使用。
- [ ] `handoff`：跨窗口/跨 agent 交接时使用。
- [ ] GitHub 相关能力：需要提交 PR 或远程协作时再启用。
- [ ] 文献/PDF 相关能力：后续知识库增强时再启用，不作为 v0.1 第一阶段重点。
- [ ] K-Dense scientific skills：如正式构建目录中没有 `.agents/skills/`，可运行 `npx skills add K-Dense-AI/scientific-agent-skills`；仅按 `EA_V0_1_SKILL_SETUP.md` 白名单启用，不默认加载全部科学 skill。

---

## 5. 测试样本准备

v0.1 准备 1 组正式 test case：`test-case-001`。更多 test case 放到后续版本扩展。

当前准备状态：

- [x] `test_cases/test-case-001/public/conversation.md` 已准备，可给构建 agent / 被测 EA。
- [x] `test_cases/test-case-001/public/raw_data/` 已准备，包含 test1 Raman/PL 原始 txt。
- [x] `test_cases/test-case-001/hidden_truth/evaluation_truth.md` 已准备，仅 Evaluation Agent 可读。
- [x] `test_cases/test-case-001/evaluation.md` 已准备，仅 Evaluation Agent 可读。

推荐结构：

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

说明：`test-case-001` 当前将多个 hidden truth 子文件合并为 `hidden_truth/evaluation_truth.md`，这是 v0.1 准备阶段可接受的简化结构；构建 agent 仍只能读取 `public/`。

每组 test case 需要准备：

- [ ] 项目初始化自然语言描述。
- [ ] 3-6 条自然语言实验记录。
- [ ] 至少一个历史查询，例如“哪些样品比较适合 Raman？”。
- [ ] 对应 Raman 原始数据文件。
- [ ] 文件与样品真实映射。
- [ ] 期望 EA 抽取出的字段。
- [ ] 期望样品编号。
- [ ] 样品质量判断真值。
- [ ] Raman x/y 列真值。
- [ ] 报告必须包含和不能包含的内容。
- [ ] 哪些内容可进入 confirmed findings。
- [ ] 哪些内容只能进入 open questions。

注意：

- [ ] public 输入尽量接近真实用户表达，不要整理得太完美。
- [ ] hidden truth 不给构建 agent。
- [ ] 如含真实数据，先考虑脱敏。

---

## 6. 实现环境准备

建议准备：

- [ ] `README.md`
- [ ] `pyproject.toml` 或 `requirements.txt`
- [ ] `tests/`
- [ ] `docs/panorama/`
- [ ] `docs/specs/`
- [ ] `examples/`

Python 依赖建议：

- [ ] `pandas`
- [ ] `numpy`
- [ ] `scipy`
- [ ] `matplotlib`
- [ ] `openpyxl`
- [ ] `pyyaml`
- [ ] `pytest`

可选：

- [ ] `pydantic`
- [ ] `jsonschema`

---

## 7. 新窗口启动提示准备

可以在新窗口用类似提示启动：

```text
你是 EA v0.1 agent team 的主线程 orchestrator。
请先按顺序阅读 docs/EA_V0_1_BUILD_PACKAGE_MANIFEST.md，docs/EA_V0_1_GIT_WORKFLOW.md，docs/panorama/ 下的 EA_AGENT_TEAM_BRIEF.md、EA_PRODUCT_CHARTER.md、EA_ARCHITECTURE_MAP.md、EA_AGENT_TEAM_PROTOCOL.md、EA_TEST_PROTOCOL.md，docs/specs/ 下的 6 份 P0 实现规格，以及 docs/EA_V0_1_AGENT_TEAM_SETUP.md 和 docs/EA_V0_1_SKILL_SETUP.md。

你的任务是搭建 EA v0.1。
不要实现 Web/UI。
不要做多项目管理。
不要跳过用户审核。
不要让 EA 建议直接进入项目决策。
不要修改 raw 数据。

请先阅读文档，检查 sub-agent 工具和 skill 可用性，建立 agent registry，并输出实现计划，不要立刻写代码。
在写任何产品代码前，先确认 Git repo、`.gitignore`、Stage 0 commit、remote/push 状态；如果没有 remote，告诉用户当前只有本地 Git 保护。
```

---

## 8. 第一阶段实现目标

第一阶段建议只做：

- [ ] 初始化 repo 和目录结构。
- [ ] 建立核心 schema。
- [ ] 实现项目初始化。
- [ ] 实现项目规则卡。
- [ ] 实现实验日志结构化、用户确认和保存。
- [ ] 实现 review record。
- [ ] 实现最小 provenance。
- [ ] 写第一批测试。

不要第一阶段就做：

- [ ] Web/UI。
- [ ] 多项目管理。
- [ ] XRD/PL/AFM 等多表征。
- [ ] 完整知识库自动同步。
- [ ] 完整阶段冻结恢复。
- [ ] reviewer 证据等级。

---

## 9. 第二阶段实现目标

第二阶段建议做 Raman 闭环：

- [ ] raw import。
- [ ] raw hash 和去重。
- [ ] CSV/TXT/XLSX 读取。
- [ ] Raman x/y 列候选识别。
- [ ] 用户确认列和单位。
- [ ] 用户确认处理参数。
- [ ] 生成 processed CSV。
- [ ] 生成峰表。
- [ ] 生成图谱。
- [ ] 生成 metadata。
- [ ] 生成中文分析报告。
- [ ] 写 Raman workflow provenance。

---

## 10. 开工前最终检查

- [ ] Git 仓库已初始化。
- [ ] Stage 0 commit 和 tag 已创建。
- [ ] remote 可用时已 push；remote 不可用时已告知用户。
- [ ] `EA_V0_1_BUILD_PACKAGE_MANIFEST.md` 已放入 `docs/`。
- [ ] map 文件已放入 `docs/panorama/`。
- [ ] P0 spec 已放入 `docs/specs/` 或 `docs/panorama/`。
- [ ] test case public 和 hidden truth 已分离。
- [ ] raw 数据、hidden truth、私密文献已加入 `.gitignore` 或另行管理。
- [ ] 新窗口主线程启动提示已准备。
- [ ] 第一阶段任务边界已明确。
- [ ] 确认 agent 不会先写代码，而是先读文档并输出计划。
