# EA v0.2 工作计划草案

> 状态：主干决策已确认，等待进入 v0.2 实现前的仓库基线整理  
> 日期：2026-06-30  
> 基础：EA v0.1 已完成最小纵向闭环，v0.2 目标是从“可运行原型内核”推进到“可持续使用、可扩展、可审计的研究工作台”。

## 1. v0.2 总目标

EA v0.2 不急于一次性支持所有材料表征方法。它应先建立能长期扩展的底座：

- 主线代码和交接状态可复现。
- v0.2 开始前重新整理或初始化干净 git 仓库，并建立阶段性提交和回滚点。
- 用户有稳定命令入口，而不是只靠 Python service 或 demo 脚本。
- 项目级设计文档不再被 v0.1、Raman 或单一 test-case 口径绑住。
- 建立模块化 skill 架构，让 Raman、PL、XRD、IR、文献库、绘图、报告等能力能作为子 skill 接入。
- 建立 `add-skills` 治理机制，规范用户自定义 skill 的输入、输出、报告、图片、记忆和 provenance。
- 建立统一的数据报告、图片 ID、报告 ID、引用和可信度表达标准。
- 建立本地文献库部署流程，为项目解释和报告引用提供可追踪知识来源。
- 评估集从单一 test-case 扩展到更能暴露真实问题的场景。
- 项目记忆和 provenance 从“能写”升级到“可审计、可查询、可维护”。

## 2. v0.2 设计文档入口

- `docs/EA_PROJECT_DESIGN.md`: 项目级长期设计。
- `docs/EA_SKILL_MODULE_ARCHITECTURE.md`: 模块化 skill、子 skill 清单和 `add-skills` 设计。
- `docs/EA_REPORT_AND_FIGURE_STANDARD.md`: 报告、图片、ID、引用和可信度标准。
- `docs/EA_LOCAL_LITERATURE_LIBRARY_SKILL.md`: 本地文献库部署 skill 设计。
- `docs/EA_PUBLIC_RELEASE_INITIALIZATION.md`: 公开用户初始化、路径、账号和测试隔离要求。
- `docs/EA_V0_2_CONFIRMATION_CHECKLIST.md`: 已确认决策和仍待细化项。
- `docs/EA_V0_2_WORK_PLAN.md`: 当前 v0.2 工作计划。

## 3. 阶段划分

### Phase 0: 计划收敛与文档清理

目标：

- 建立 v0.2 planning-with-files 跟踪。
- 明确当前项目权威设计文档。
- 把版本目标从项目目标中拆出来。
- 清理低价值边界语言和历史 UI/Web 噪声。

验收：

- `task_plan.md`、`findings.md`、`progress.md` 可持续跟踪 v0.2。
- `docs/EA_PROJECT_DESIGN.md` 成为项目级设计入口。
- 旧文档被标记为历史参考或简化入口。

状态：已完成。

### Phase 1: v0.2 架构标准确认

目标：

- 确认模块化 skill 架构。
- 确认 `add-skills` 的治理范围。
- 确认报告、图片、引用、ID 和可信度标准。
- 确认本地文献库部署流程和新聊天窗口协作方式。

验收：

- 用户确认或修改 `docs/EA_SKILL_MODULE_ARCHITECTURE.md`。
- 用户确认或修改 `docs/EA_REPORT_AND_FIGURE_STANDARD.md`。
- 用户确认或修改 `docs/EA_LOCAL_LITERATURE_LIBRARY_SKILL.md`。
- 需要追问的问题被整理在 planning files 中。

状态：已确认主干决策；少量细节随实现继续确认。

### Phase 2: Git 仓库重整与 v0.2 基线

目标：

- 在正式写 v0.2 代码前，整理或重新初始化 EA 实现仓库。
- 冻结 v0.1.1 基线，避免散落文件成为后续回滚障碍。
- 建立阶段性 commit、tag 和远程同步策略。

建议做法：

1. 新建干净 `EAv0.2-build`，保留 v0.1 实现仓库作为历史参考。
2. 从 v0.1 导入必要源码、测试和设计文档，不导入临时输出、demo artifact、本机私有配置或测试缓存。
3. 清理 `.gitignore`，排除 generated workspace、缓存、临时报告、大文件和 local-test-only 配置。
4. 创建 `v0.1.1-freeze-import` commit。
5. 创建 `v0.1.1-freeze` tag。
6. 创建 `codex/eav0.2` 分支。
7. 每个阶段至少一个可回滚 commit。
8. 若用户提供 GitHub remote，则按阶段 push；若没有 remote，则保持本地 tag 和 bundle。

验收：

- Git status clean。
- 有明确 baseline commit/tag。
- 回滚点覆盖每个实现阶段。
- 文档说明哪些文件属于源码、哪些属于项目数据或生成 artifact。
- 仓库中不包含开发者本机 Zotero、学校认证、Chrome profile、文献库路径或测试数据绝对路径。

### Phase 3: v0.1.1 Hardening

目标：

- 整理当前实现中的 wrapper、test、progress、task_plan 更新。
- 明确 demo artifact 与源码边界。
- 增加 `RELEASE_NOTES.md` 和 `KNOWN_LIMITATIONS.md`。

验收：

- 当前测试全通过。
- release notes 说明当前能力、限制和迁移方式。
- 后续 agent 能从 Git commit 而不是散落工作树恢复状态。

### Phase 4: 最小可用 CLI

目标：

- 把现有 service API 暴露成稳定命令。
- 降低真实用户使用门槛。
- 为公开用户提供初始化向导，避免依赖开发者本机默认配置。

候选命令：

```text
ea status
ea init-project
ea import-raw
ea inspect-spectrum
ea process-raman
ea report
ea healthcheck
ea literature status
ea config init
ea config doctor
```

验收：

- 用户能通过 CLI 完成初始化、raw 导入、光谱检查、Raman 处理、报告生成和项目健康检查。
- CLI 输出适合 agent 继续接手，也适合用户直接阅读。
- 所有命令保留 review/provenance 机制。
- 初始化命令会询问项目根目录、project slug、报告语言、Zotero/浏览器/文献缓存等必要配置。

### Phase 5: 项目健康检查与审计

目标：

- 增加 workspace-level audit。
- 检查引用断链、raw hash、review_refs、provenance_refs、processed 输出位置、报告引用状态。

验收：

- `ea healthcheck` 可发现至少以下问题：
  - raw metadata 缺失或 hash 不一致。
  - review ref 不存在或不是 confirmed。
  - provenance ref 断链。
  - processed 输出误写 raw。
  - report 引用的 result metadata 不存在。
  - rule card 仍有未确认关键项。
  - figure/report/raw/sample 索引断链。

### Phase 6: 模块化 Skill 与 add-skills

目标：

- 建立 `skill-registry/index.yml`。
- 定义子 skill manifest。
- 实现 `add-skills` 的静态检查和 dry-run 流程草案。
- 让新 skill 必须符合 EA 的数据、报告、图片、引用、记忆和 provenance 结构。

验收：

- 至少一个内置 skill 通过契约检查。
- 一个故意不合规的 skill 能被拒绝并给出修改建议。
- 子 skill 可在项目内调用，也能作为 standalone skill 输出可导入结果。

### Phase 7: 报告、图片和引用标准实现

目标：

- 落地 report ID、figure ID、raw data ID 和 result ID。
- 建立 `reports/index.yml`、`figures/index.yml`。
- 统一 Markdown 报告模板和 Matplotlib 绘图样式。
- 建立对话和报告中的 `[1][2]` 引用格式。

验收：

- 报告中图片可直接展示，并提供原图文件链接。
- 图片右下角 footer 有 figure ID 和 report ID。
- 给 EA 一个 figure ID，可定位图片、报告、原始数据、样品和实验条件。
- 报告中每个引用都有文末 reference 条目和本地/网页链接。
- 推论使用高/中/低/不足四级可信度。

### Phase 8: 本地文献库部署

目标：

- 项目初始化时检查是否已有文献库。
- 建议用户创建本地文献库。
- 生成关键词和系统化检索计划。
- 对候选文献去重、评分、排名。
- 在用户确认 top N 后调用或包装 `zotero-codex-literature` 完成下载和缓存。
- 支持专用 literature thread，并通过状态文件同步回原项目窗口。
- 面向公开用户运行时，通过初始化配置获得 Zotero、浏览器、缓存目录和机构访问方式，不使用开发者本机默认值。
- 用户确认 top N 后生成 acquisition request、Zotero-Codex query/target manifests，并能导入专用文献流程返回的 acquisition manifest。

验收：

- `literature/deployment_status.yml` 能表达检索、确认、下载和缓存状态。
- 用户确认前不会批量下载全文。
- 对 “全网无遗漏” 的限制、影响因子来源和版权/访问限制有明确说明。
- 原窗口能读取文献库部署摘要。
- public setup、developer setup、local integration test setup 明确分离。
- EA 主项目窗口不直接执行 live 下载；专用文献流程完成后可通过 `ea literature import-acquisition` 同步文献清单、缓存索引和引用记录。

### Phase 9: Raman v0.2 能力回流

目标：

- 将真实 `lm-mos2` 批处理中的成熟能力逐步产品化。
- 让 Raman 不只停留在简单归一化 + find_peaks。
- 作为第一个完整接入模块化架构、报告标准和 provenance 的分析 skill。

候选能力：

- AsLS baseline correction。
- Savitzky-Golay 平滑与参数记录。
- spike / artifact 诊断。
- pseudo-Voigt 或可替代峰拟合。
- 重复谱识别和唯一谱统计。
- 分组统计、样品内对照和报告模板。

验收：

- 每项处理能力都有参数、review gate、metadata 和测试。
- 新能力不破坏 v0.1 public workflow。
- 真实 `lm-mos2` 至少一个代表批次能用核心库流程复现主要表格和报告结构。

### Phase 10: 图像类数据分析流程

目标：

- 为 TEM、SEM、光学显微镜等图片式数据建立 human-in-the-loop 流程。
- 区分模型视觉判断、用户描述、仪器元数据和可量化图像分析。

验收：

- 用户上传图片和描述后，EA 能生成图片类数据报告。
- 当视觉分析不可靠时，EA 明确采用用户描述作为主证据并追问关键缺失信息。
- 原图、处理图、用户描述、分析结论和 provenance 均可追溯。
- scale bar、拍摄条件和样品位置进入报告元数据。

### Phase 11: 评估集扩展

目标：

- 减少对 `test-case-001` 的过拟合。
- 增加能暴露真实问题的回归样本。
- 增加 `ea eval project` 本地评估入口，把 healthcheck/config、报告引用、图片风格/源数据追踪和交接就绪度汇总为可持久化评估记录。

候选 test cases：

- 不同材料体系或不同实验日志风格。
- 坏数据、缺列、单位未知、重复文件、文件映射不确定。
- 用户拒绝、编辑、延后确认和反复修改的交互。
- 多批次数据与项目记忆冲突。
- 图片类数据和文献引用类报告。

验收：

- 至少 3 个 public test case。
- hidden/evaluator 材料继续隔离。
- CI 或本地测试可以区分 public workflow test 和 evaluator-only review。
- `evaluation/eval-{yyyymmdd}-{nnn}.yml` 能保存本地确定性评估结果，且明确不执行 live 文献检索、DOI 解析、PDF 下载、浏览器/Zotero 访问或科学真值打分。

### Phase 12: 项目记忆升级

目标：

- 把 memory 从 Markdown 追加升级为更稳定的结构化 record。
- 支持查询、去重、状态变更和证据等级。

候选字段：

- record_id
- record_type
- status
- evidence_level
- source_refs
- provenance_refs
- review_refs
- supersedes / superseded_by
- created_at / updated_at

验收：

- confirmed finding、decision、progress、open item 都能机器读取。
- 用户可以查询“当前确认发现”“开放问题”“失败尝试”“待复核建议”。
- 记忆写入仍需符合项目级 review 规则。

### Phase 13: 文档与用户体验打磨

目标：

- 让新 agent 和真实用户都能顺畅理解 EA。
- 减少冗余、重复、过度边界化表述。
- 把追问放在回答末尾，且只追问会影响后续工作的关键不确定项。

验收：

- 文档入口清晰：项目设计、版本计划、使用手册、API/CLI 文档、限制说明。
- 旧文档有历史定位，不再和当前权威文档竞争。
- 用户看到的文档更像研究工具说明，而不是内部约束清单。

## 4. 暂不纳入 v0.2 必做项

以下内容可以讨论，但默认不作为 v0.2 必做项：

- 完整 Web 产品。
- 多用户权限和云同步。
- 自动实验决策。
- 一次性完整实现所有表征方法。
- 自动化实验设备控制。
- 无用户授权的付费全文下载。

## 5. 已确认决策

1. v0.2 的首个完整表征 skill 采用 Raman。
2. 报告 ID、figure ID 和 reference 格式采用当前草案。
3. `[1][2]` 数字标注必须出现在正文实际引用文献的位置，并与文末 References 序号对应。
4. 本地文献库默认推荐 top N 分档采用：窄项目 30、普通项目 50、综述或大方向 100 到 200 分批。
5. v0.2 新建干净 `EAv0.2-build`。
6. EA 面向公开用户设计，初始化不得默认采用开发者本机 Zotero、学校认证、Chrome profile、本地文献库路径或测试集路径；这些信息只能作为测试 fixture 或由用户在初始化时提供。

## 6. 仍待实现时确认的细节

1. 文献库部署的专用聊天窗口是否每次都先询问用户。
2. `add-skills` 是否允许 sandbox 模式运行未完全合规的实验性 skill。
3. 报告默认语言是否固定中文，还是跟随项目初始化配置。
4. 是否在 v0.2 同时导出 BibTeX/CSL JSON，还是先只做 Markdown References。
