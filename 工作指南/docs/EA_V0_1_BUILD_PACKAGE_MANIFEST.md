# EA v0.1 Build Package Manifest

> 用途：把当前 EA v0.1 准备文件打包到一个新实现项目时使用。  
> 读者：新窗口 Main Orchestrator、Context Librarian、QA Reviewer，以及负责复制/整理启动包的人。  
> 关键边界：构建 agent 可以知道存在 hidden truth，但不能读取 hidden truth 内容。

---

## 1. 当前状态结论

当前文件已经足以支持 EA v0.1 正式开工：

- 全景地图完整。
- P0 实现规格完整。
- agent-team 配置和 Codex 子 agent 独立上下文协议已准备。
- skill 推荐、安装来源、白名单和锁定信息已准备。
- test-case-001 已拆成 public input 与 hidden evaluation truth。

EA v0.1 只使用 `test-case-001` 作为正式用户模拟测试样本。更多测试样本放到后续版本扩展。

本项目采用 `工作指南/` 打包结构。所有原先写作 `docs/...` 的指南路径，在本正式项目中对应为 `工作指南/docs/...`。

---

## 2. 建议新项目结构

建议新建目录：

```text
EAv0.1-build/
├── 工作指南/
│   ├── README.md
│   ├── docs/
│   │   ├── panorama/
│   │   ├── specs/
│   │   ├── templates/
│   │   ├── notes/
│   │   ├── EA_V0_1_BUILD_PACKAGE_MANIFEST.md
│   │   ├── EA_V0_1_PRE_BUILD_TODO.md
│   │   ├── EA_V0_1_AGENT_TEAM_SETUP.md
│   │   ├── EA_V0_1_GIT_WORKFLOW.md
│   │   └── EA_V0_1_SKILL_SETUP.md
│   └── test_cases/
│       └── test-case-001/
├── .agents/
│   └── skills/
├── skills-lock.json
├── README.md
├── pyproject.toml
└── tests/
```

---

## 3. 文件放置清单

### 3.1 全景地图

已放入 `工作指南/docs/panorama/`：

- `EA_AGENT_TEAM_BRIEF.md`
- `EA_PRODUCT_CHARTER.md`
- `EA_ARCHITECTURE_MAP.md`
- `EA_AGENT_TEAM_PROTOCOL.md`
- `EA_TEST_PROTOCOL.md`

### 3.2 P0 实现规格

已放入 `工作指南/docs/specs/`：

- `EA_SCHEMA_SPEC.md`
- `EA_REVIEW_STATE_MACHINE.md`
- `EA_RAW_IMPORT_SPEC.md`
- `EA_RAMAN_V0_1_SPEC.md`
- `EA_MEMORY_BOUNDARY_SPEC.md`
- `EA_PROVENANCE_MINIMUM_SPEC.md`

### 3.3 启动与组织文件

已放入 `工作指南/docs/`：

- `EA_V0_1_BUILD_PACKAGE_MANIFEST.md`
- `EA_V0_1_PRE_BUILD_TODO.md`
- `EA_V0_1_AGENT_TEAM_SETUP.md`
- `EA_V0_1_GIT_WORKFLOW.md`
- `EA_V0_1_SKILL_SETUP.md`

### 3.4 模板与背景笔记

已放入 `工作指南/docs/templates/`：

- `ea-project-rule-card-template.md`
- `ea-test-experiment-template.md`

已放入 `工作指南/docs/notes/`：

- `EA_IMPLEMENTATION_SPEC_TODO.md`
- `ea-panorama-working-notes.md`
- `ea-brief-agent-native-zh.md`

这些 notes 可帮助理解设计过程，但正式构建应优先以 `工作指南/docs/panorama/`、`工作指南/docs/specs/`、`工作指南/docs/EA_V0_1_AGENT_TEAM_SETUP.md` 和 `工作指南/docs/EA_V0_1_GIT_WORKFLOW.md` 为准。

### 3.5 测试样本

复制整个目录：

- `test_cases/test-case-001/`

`test-case-001` 的构建安全输入：

- `工作指南/test_cases/test-case-001/public/conversation.md`
- `工作指南/test_cases/test-case-001/public/raw_data/`

`test-case-001` 的 evaluator-only 文件保留在准备目录，不复制到正式构建 repo：

- 准备目录中的 `test_cases/test-case-001/hidden_truth/evaluation_truth.md`
- 准备目录中的 `test_cases/test-case-001/evaluation.md`

构建 agent 只读 `public/`。Evaluation agent 才能在单独上下文中读取 `hidden_truth/` 与 `evaluation.md`。

### 3.6 Skills

如果希望直接复用当前已安装 skill，复制：

- `.agents/skills/`
- `skills-lock.json`

如果不复制 `.agents/skills/`，在新项目中运行：

```bash
npx skills add K-Dense-AI/scientific-agent-skills
```

然后按 `工作指南/docs/EA_V0_1_SKILL_SETUP.md` 的白名单按需启用，不默认加载全部科学 skill。

---

## 4. 不应给构建 Agent 的文件

以下文件不得放入构建 agent 的可读上下文：

- `test_cases/test-case-001/hidden_truth/`
- `test_cases/test-case-001/evaluation.md`
- `ea-test-experiment-test1.md`
- `findings.md`
- `progress.md`
- `task_plan.md`

原因：

- `ea-test-experiment-test1.md` 是旧合并稿，包含 public input 和 hidden truth。
- `findings.md`、`progress.md`、`task_plan.md` 是准备过程记录，含有测试真值、评估信息和历史工作细节，不属于构建启动上下文。

如果需要让新窗口理解准备过程，只给它本 manifest、全景地图、P0 specs、agent-team setup 和 skill setup。

---

## 5. 新窗口推荐阅读顺序

Main Orchestrator 先读：

1. `工作指南/README.md`
2. `工作指南/docs/EA_V0_1_BUILD_PACKAGE_MANIFEST.md`
3. `工作指南/docs/EA_V0_1_GIT_WORKFLOW.md`
4. `工作指南/docs/panorama/EA_AGENT_TEAM_BRIEF.md`
5. `工作指南/docs/panorama/EA_PRODUCT_CHARTER.md`
6. `工作指南/docs/panorama/EA_ARCHITECTURE_MAP.md`
7. `工作指南/docs/panorama/EA_AGENT_TEAM_PROTOCOL.md`
8. `工作指南/docs/panorama/EA_TEST_PROTOCOL.md`
9. `工作指南/docs/specs/EA_SCHEMA_SPEC.md`
10. `工作指南/docs/specs/EA_REVIEW_STATE_MACHINE.md`
11. `工作指南/docs/specs/EA_RAW_IMPORT_SPEC.md`
12. `工作指南/docs/specs/EA_RAMAN_V0_1_SPEC.md`
13. `工作指南/docs/specs/EA_MEMORY_BOUNDARY_SPEC.md`
14. `工作指南/docs/specs/EA_PROVENANCE_MINIMUM_SPEC.md`
15. `工作指南/docs/EA_V0_1_PRE_BUILD_TODO.md`
16. `工作指南/docs/EA_V0_1_SKILL_SETUP.md`
17. `工作指南/docs/EA_V0_1_AGENT_TEAM_SETUP.md`

读取后，先建立 agent registry 和文件访问边界，再开始写代码。

---

## 6. 开工前检查

- [ ] `工作指南/docs/panorama/` 已包含 5 份全景地图。
- [ ] `工作指南/docs/specs/` 已包含 6 份 P0 实现规格。
- [ ] `工作指南/docs/` 已包含本 manifest、pre-build TODO、Git workflow、agent-team setup、skill setup。
- [ ] Git repo 已初始化并完成 Stage 0 commit。
- [ ] 如果 remote 可用，Stage 0 commit 已 push。
- [ ] `工作指南/test_cases/test-case-001/public/` 已提供给构建/被测 EA。
- [ ] `test-case-001/hidden_truth/` 和 `evaluation.md` 未复制到正式构建 repo。
- [ ] `.agents/skills/` 已复制，或已按 skill setup 重新安装。
- [ ] `.gitignore` 已覆盖 hidden truth、私密资料、token、缓存和大型临时输出。

---

## 7. 已知缺口

| 缺口 | 影响 | 处理方式 |
|---|---|---|
| hidden truth 需要 evaluator-only 管理 | 若误给构建 agent，会造成过拟合 | 用目录权限、上下文分派和 agent registry 控制 |
| 当前 skill 库较大 | 子 agent 可能滥用无关科学 skill | 严格使用 `EA_V0_1_SKILL_SETUP.md` 白名单 |

---

## 8. 新项目 `.gitignore` 建议

不要直接忽略 `test_cases/**/public/raw_data/`，因为 public test fixture 需要随测试包提供。建议新实现项目至少包含：

```gitignore
# evaluator-only material
test_cases/**/hidden_truth/
test_cases/**/evaluation.md

# user/private research material
private/
secrets/
credentials/
*.token
*.key
.env
.env.*

# runtime caches
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.DS_Store

# generated outputs
outputs/
reports/generated/
processed/
figures/generated/

# live project raw data, not public test fixtures
raw/
```

如果 evaluator 需要版本管理 hidden truth，建议放在单独 private evaluator repo，或由用户手动管理，不进入构建 agent 的代码仓库上下文。
