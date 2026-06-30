# EA 文档入口

## 当前权威文档

1. `PUBLIC_ONBOARDING.md`
   - 面向陌生公开用户和新 agent 的入门路径。
   - 覆盖安装、第一个项目、review gates、文献库选择、导出、release 检查和需要追问用户的事项。

2. `RELEASE_VERIFICATION.md`
   - 面向 release 接收者、维护者和后续 agent 的本地验证路径。
   - 说明 manifest、release zip、`.sha256`、可选签名和 distribution checklist 的验证顺序与边界。

3. `PROJECT_BUNDLE_VERIFICATION.md`
   - 面向报告/批处理项目导出包接收者和后续 agent 的交接验证路径。
   - 说明 `bundle_manifest.yml`、`batch_bundle_manifest.yml`、`bundle_checksums.yml`、archive checksum、provenance 审计和项目导出包签名边界。

4. `EA_PROJECT_DESIGN.md`
   - EA 的项目级设计文档。
   - 描述长期目标、核心价值、架构原则、数据/记忆/证据模型。
   - 不把任何单一版本、单一测试样本或单一表征方法写成项目整体目标。

5. `EA_V0_2_WORK_PLAN.md`
   - EA v0.2 工作计划草案。
   - 用于承接 v0.1 已完成纵向切片，并收集后续用户提出的新版本改进建议。

6. `EA_SKILL_MODULE_ARCHITECTURE.md`
   - EA 父级 skill、子 skill 清单、`add-skills` 接入治理和模块契约。

7. `EA_REPORT_AND_FIGURE_STANDARD.md`
   - 数据分析报告、图片 ID、报告 ID、图片 footer、引用格式和可信度表达。

8. `EA_LOCAL_LITERATURE_LIBRARY_SKILL.md`
   - 本地文献库部署流程、Zotero 集成、候选文献评分和专用文献线程同步。

9. `EA_PUBLIC_RELEASE_INITIALIZATION.md`
   - 公开发布场景下的初始化、配置、路径、账号和测试隔离要求。

10. `EA_V0_2_CONFIRMATION_CHECKLIST.md`
   - v0.2 开始实现前需要用户确认或修改的标准清单。

11. `ea-brief-agent-native-zh.md`
   - 当前简版 agent 入口。
   - 给后续 agent 快速理解 EA 当前方向和应该先读哪些文件。

## 历史参考文档

以下文件保留作为设计演化记录，不再作为当前建设的唯一依据：

- `ea-new-direction-zh.md`
- `ea-brief-zh.md`
- `ea-brief-agent.md`

历史文档中出现的 Web/UI-first、v0.1/MVP、Raman-only、或过细的反面边界表述，应按历史语境理解。新的项目目标和版本规划以当前权威文档为准。
