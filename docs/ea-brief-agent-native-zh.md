# EA Agent 入口简报

> 状态：当前简版入口  
> 日期：2026-06-30  
> 说明：本文是给后续 agent 的快速入口。项目级设计以 `EA_PROJECT_DESIGN.md` 为准；版本计划以 `EA_V0_2_WORK_PLAN.md` 为准。

## 先读哪些文件

1. `docs/EA_PROJECT_DESIGN.md`
2. `docs/EA_V0_2_WORK_PLAN.md`
3. `docs/EA_SKILL_MODULE_ARCHITECTURE.md`
4. `docs/EA_REPORT_AND_FIGURE_STANDARD.md`
5. `docs/EA_LOCAL_LITERATURE_LIBRARY_SKILL.md`
6. `docs/EA_PUBLIC_RELEASE_INITIALIZATION.md`
7. `docs/EA_V0_2_CONFIRMATION_CHECKLIST.md`
8. `task_plan.md`
9. `findings.md`
10. `progress.md`
11. `ea-current-context-bundle/README.md`
12. `ea-current-context-bundle/LATEST_PROGRESS_FILE_LIST.md`

## 当前项目判断

EA 是本地优先、面向实验科学研究者的科研工作系统。它的稳定内核是：

- 实验记录结构化
- 原始数据保护
- 可复现数据处理
- 证据化科学解释
- 用户确认
- 报告生成
- 项目记忆
- provenance 审计
- 模块化子 skill
- 统一报告、图片和引用
- 本地文献库

Raman / MoS2 / v0.1 test-case 是早期验证入口，不是 EA 的整体边界。

## 当前实现状态

EA v0.1 已经完成一个可运行纵向切片：

- 项目初始化
- review gate
- 实验日志结构化
- 样品记录
- raw import
- Raman v0.1 处理
- 中文报告
- memory/provenance 边界
- Codex skill wrapper

当前 v0.2 的重点不是盲目扩功能，而是先确认模块化、报告/图片、文献库和 git 基线标准，再让这个纵向切片变得更稳、更易用、更可扩展。

## 后续 agent 工作准则

- 不要把版本目标写成项目整体目标。
- 不要把普通工程正确性检查写成项目原则。
- 不要让旧 Web/UI 文档覆盖当前 agent-native 主线，但也不要否定未来多入口形态的可能性。
- 先更新 planning files，再做较大设计或实现改动。
- 新增能力必须说明它服务哪一类真实研究工作流。
- 项目记忆、用户确认和 provenance 是 EA 的长期核心，不是 v0.1 临时机制。
- 新增子 skill 必须通过 `add-skills` 契约检查后再进入 EA 架构。
- 报告、图片、引用和可信度表达应遵守当前标准草案，直到用户另行确认修改。
- EA 面向公开用户设计，不能默认采用开发者本机 Zotero、学校认证、Chrome profile、文献库路径或测试数据路径；这些只能作为 local-test-only fixture。
