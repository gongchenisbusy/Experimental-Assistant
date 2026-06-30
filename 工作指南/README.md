# EA v0.1 工作指南

> 用途：正式构建 agent 的开工指南。  
> 项目根目录：`EAv0.1-build/`。  
> 规则：先读指南，再写代码。

---

## 1. 必读顺序

请按顺序阅读：

1. `工作指南/docs/EA_V0_1_BUILD_PACKAGE_MANIFEST.md`
2. `工作指南/docs/EA_V0_1_GIT_WORKFLOW.md`
3. `工作指南/docs/panorama/EA_AGENT_TEAM_BRIEF.md`
4. `工作指南/docs/panorama/EA_PRODUCT_CHARTER.md`
5. `工作指南/docs/panorama/EA_ARCHITECTURE_MAP.md`
6. `工作指南/docs/panorama/EA_AGENT_TEAM_PROTOCOL.md`
7. `工作指南/docs/panorama/EA_TEST_PROTOCOL.md`
8. `工作指南/docs/specs/EA_SCHEMA_SPEC.md`
9. `工作指南/docs/specs/EA_REVIEW_STATE_MACHINE.md`
10. `工作指南/docs/specs/EA_RAW_IMPORT_SPEC.md`
11. `工作指南/docs/specs/EA_RAMAN_V0_1_SPEC.md`
12. `工作指南/docs/specs/EA_MEMORY_BOUNDARY_SPEC.md`
13. `工作指南/docs/specs/EA_PROVENANCE_MINIMUM_SPEC.md`
14. `工作指南/docs/EA_V0_1_PRE_BUILD_TODO.md`
15. `工作指南/docs/EA_V0_1_AGENT_TEAM_SETUP.md`
16. `工作指南/docs/EA_V0_1_SKILL_SETUP.md`

说明：部分指南文件内部仍使用 `docs/...` 作为通用路径示例。在本项目打包结构中，对应路径是 `工作指南/docs/...`。

---

## 2. Git 使用要求

正式构建 agent 必须先检查：

```bash
git status -sb
git remote -v
git log --oneline --decorate -3
git tag --list
```

工作规则：

- 阶段开始前确认工作区干净。
- 每个稳定阶段完成后 commit。
- 每个阶段完成后 push 到 `origin`。
- 重要阶段打 tag。
- 出错时优先从 tag 创建 rollback 分支或使用 `git revert`。
- 不要随意使用 `git reset --hard`、`git clean -fd`、`git push --force`。

当前仓库已经连接 GitHub remote。构建 agent 每阶段完成后应运行：

```bash
git push origin main
git push origin --tags
```

---

## 3. 文件边界

构建 agent 可读：

- `工作指南/docs/`
- `工作指南/test_cases/test-case-001/public/`
- `.agents/skills/`
- `skills-lock.json`

构建 agent 不可读：

- hidden truth。
- evaluator-only answer key。
- 准备目录中的 `findings.md`、`progress.md`、`task_plan.md`。

注意：本正式构建仓库没有放入 hidden truth 或 evaluator-only 文件。

---

## 4. v0.1 范围

必须做：

- 本地优先的 EA skill 系统。
- 一个工作目录对应一个科研项目。
- 项目初始化、规则卡、样品编号和实验日志确认。
- raw 只读导入。
- Raman v0.1 分析闭环。
- 中文报告、review record、provenance、project memory。
- test-case-001 public workflow。

不要做：

- Web/UI。
- 多项目管理。
- 自动实验决策。
- XRD/PL/AFM 完整分析模块。
- 大规模 RAG。
- 把 test1 答案硬编码为通用规则。

---

## 5. 开工动作

Main Orchestrator 的第一步不是写代码，而是：

1. 确认 Git 状态和 remote。
2. 建立 `task_plan.md`、`findings.md`、`progress.md`。
3. 检查 sub-agent 工具。
4. 建立 agent registry。
5. 输出 Stage 0-1 实施计划。

