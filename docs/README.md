# EA 文档入口

## 当前权威文档

1. `V1_0_RELEASE_DOSSIER.md` / `V1_0_RELEASE_DOSSIER.yml` / `V1_0_PUBLICATION_VERIFICATION.*`
   - v1.0.0 候选、发布和下载重放门禁的当前权威记录。
   - 与历史 `V1_0_READINESS_DOSSIER.*` 分离，后者只记录 v0.9.9 晋升快照。

2. `V1_0_RELEASE_NOTES.md` / `V1_0_KNOWN_LIMITATIONS.md` / `V1_0_SUPPORT_PROMISE.md`
   - 描述 v1.0.0 稳定包合同、有限 Raman 稳定范围和仍需 review 的方法/集成边界。

3. `PUBLIC_ONBOARDING.md`
   - 面向陌生公开用户和新 agent 的入门路径。
   - 覆盖安装、第一个项目、review gates、文献库选择、导出、release 检查和需要追问用户的事项。

4. `RELEASE_VERIFICATION.md`
   - 面向 release 接收者、维护者和后续 agent 的本地验证路径。
   - 说明 manifest、release zip、`.sha256`、可选签名和 distribution checklist 的验证顺序与边界。

5. `PROJECT_BUNDLE_VERIFICATION.md`
   - 面向报告/批处理项目导出包接收者和后续 agent 的交接验证路径。
   - 说明 `bundle_manifest.yml`、`batch_bundle_manifest.yml`、`bundle_checksums.yml`、archive checksum、provenance 审计和项目导出包签名边界。

6. `../examples/public-raman-project/`
   - 随 release 打包的公开安全 Raman 示例项目。
   - 用于新用户和后续 agent 检查 EA 项目结构、review gates、Raman 处理结果、报告、图件和 provenance，不作为真实用户项目默认值。

7. `EA_PROJECT_DESIGN.md`
   - EA 的项目级设计文档。
   - 描述长期目标、核心价值、架构原则、数据/记忆/证据模型。
   - 不把任何单一版本、单一测试样本或单一表征方法写成项目整体目标。

8. `EA_V0_2_WORK_PLAN.md`
   - EA v0.2 工作计划草案。
   - 用于承接 v0.1 已完成纵向切片，并收集后续用户提出的新版本改进建议。

9. `EA_SKILL_MODULE_ARCHITECTURE.md`
   - EA 父级 skill、子 skill 清单、`add-skills` 接入治理和模块契约。

10. `EA_REPORT_AND_FIGURE_STANDARD.md`
   - 数据分析报告、图片 ID、报告 ID、图片 footer、引用格式和可信度表达。

11. `EA_LOCAL_LITERATURE_LIBRARY_SKILL.md`
   - 本地文献库部署流程、Zotero 集成、候选文献评分和专用文献线程同步。

12. `EA_PUBLIC_RELEASE_INITIALIZATION.md`
   - 公开发布场景下的初始化、配置、路径、账号和测试隔离要求。

13. `EA_V0_2_CONFIRMATION_CHECKLIST.md`
   - v0.2 开始实现前需要用户确认或修改的标准清单。

14. `ea-brief-agent-native-zh.md`
   - 当前简版 agent 入口。
   - 给后续 agent 快速理解 EA 当前方向和应该先读哪些文件。

## 历史参考文档

以下文件保留作为设计演化记录，不再作为当前建设的唯一依据：

- `ea-new-direction-zh.md`
- `ea-brief-zh.md`
- `ea-brief-agent.md`
- `V0_9_9_*`
- `V1_0_READINESS_DOSSIER.md` / `V1_0_READINESS_DOSSIER.yml`

历史文档中出现的 Web/UI-first、v0.1/MVP、Raman-only、或过细的反面边界表述，应按历史语境理解。新的项目目标和版本规划以当前权威文档为准。
