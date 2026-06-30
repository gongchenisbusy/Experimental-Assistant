# EA v0.2 标准确认清单

> 状态：主干决策已由用户确认，少量实现细节待后续确认  
> 日期：2026-06-30  
> 用途：把 v0.2 开始实现前需要拍板的架构标准整理成可直接确认或修改的清单。

## 0. 已确认决策

用户已确认：

- Raman 作为 v0.2 第一个完整模块化表征分析 skill。
- 当前 ID、报告、图片、reference 和可信度格式可以作为默认标准。
- `[1][2]` 数字引用必须出现在正文中实际引用文献的位置，并与文末 `References` 序号对应。
- 本地文献库默认 top N 分档采用：窄项目 30、普通研究项目 50、综述或大方向 100 到 200 分批。
- v0.2 新建干净 `EAv0.2-build`，保留 v0.1 作为历史参考。
- EA 最终面向公开用户，初始化不得默认采用开发者本机 Zotero、学校认证、Chrome profile、本地文献库文件夹或测试集路径；这些只能用于测试或由用户初始化时提供。

## 1. 模块化 Skill 架构

推荐默认方案：确认。

EA 采用父级 orchestrator 加模块化子 skill。父级 EA 管项目上下文、项目记忆、raw/processed/report/figure/provenance 索引和跨 skill 调度；子 skill 负责专业任务，可项目内调用，也可独立调用。

v0.2 首批优先级：

1. `project-init`
2. `raw-data-import`
3. `scientific-plotting`
4. `analysis-report`
5. `add-skills`
6. `local-literature-library`
7. `raman-analysis`
8. `provenance-audit`
9. `memory-query`

PL、XRD、IR、SEM/TEM、AFM、电学、电化学等进入长期 skill 目录和接口测试，不作为 v0.2 首批完整实现目标。

已确认：

- Raman 作为第一个完整表征分析 skill。
- PL、XRD、IR、SEM/TEM、AFM、电学、电化学等保留为长期候选或接口测试，不提前作为 v0.2 首批完整实现。

## 2. add-skills 治理

推荐默认方案：确认。

用户新增 skill 必须通过 `add-skills`：

- manifest 检查
- 输入/输出契约检查
- review gate 检查
- raw 数据保护检查
- report/figure/reference 格式检查
- provenance 检查
- 最小 fixture dry run
- 注册到 `skill-registry/index.yml`

待确认：

- 是否允许“实验性未完全合规 skill”以 sandbox 模式临时运行，但不得写入正式项目记忆？

## 3. ID 与索引

推荐默认方案：确认。

```text
project_id: prj-{project_slug}
raw_data_id: raw-{project_slug}-{yyyymmdd}-{nnn}-{hash8}
result_id: res-{project_slug}-{method}-{yyyymmdd}-{nnn}
report_id: rpt-{project_slug}-{yyyymmdd}-{nnn}
figure_id: fig-{project_slug}-{method}-{yyyymmdd}-{nnn}
```

索引文件：

- `raw/index.yml`
- `processed/index.yml`
- `reports/index.yml`
- `figures/index.yml`
- `provenance/index.yml`
- `literature/cache_index.yml`
- `skill-registry/index.yml`

待确认：

- `project_slug` 是否使用用户项目名拼音/英文短名，还是由 EA 自动生成？

## 4. 图片规范

推荐默认方案：确认。

- 默认使用 Nature-like clean academic style。
- 线图优先导出 PDF/SVG，并提供 PNG。
- 显微图、照片、热图导出高分辨率 PNG/TIFF。
- 坐标轴必须写物理量和单位。
- 图片右下角 footer 写 `FigID` 和 `Report`。
- footer 在画布边缘或页边距，不覆盖数据区域。
- 显微图优先使用 scale bar。

待确认：

- footer 是否用英文 `FigID | Report`，还是中文 `图片ID | 报告ID`？

## 5. 报告结构

推荐默认方案：确认。

报告统一使用 Markdown + YAML frontmatter，正文结构为：

1. 摘要
2. 报告 ID 信息
3. 样品与原始数据
4. 原始数据处理过程
5. 图片与原图链接
6. 数据分析
7. 可能结论与可信度
8. 限制、替代解释和待确认问题
9. References
10. Provenance

可信度使用：

- 高
- 中
- 低
- 不足

待确认：

- 报告默认语言是否为中文，除非用户特别要求英文？

## 6. 引用格式

推荐默认方案：确认。

正文使用 `[1]`、`[1][2]`。文末 reference：

```text
[1] Author A, Author B. Title. Journal volume, pages (year). DOI: https://doi.org/xxxxx | Local: /absolute/path/to/paper.pdf | Web: https://...
```

普通对话中如引用本地或网络文献，也使用同一格式。

已确认：

- `[1][2]` 必须出现在正文中实际引用文献的位置。
- 文中编号必须与文末 `References` 的序号一一对应。
- 不能只在文末列 reference 而正文不标注来源。

待确认：

- 是否需要同时支持 BibTeX/CSL JSON 导出，还是 v0.2 只做 Markdown references？

## 7. 本地文献库部署

推荐默认方案：确认。

项目初始化时 EA 检查文献库；没有则建议创建。用户确认后：

1. 生成关键词和检索式。
2. 多源检索并记录覆盖日志。
3. 去重、评分、排名。
4. 向用户报告候选数量、推荐 top N、预计耗时/token/存储。
5. 用户确认 top N。
6. 调用或包装 `zotero-codex-literature` 获取全文和缓存。
7. 用 `literature/deployment_status.yml` 同步状态。

默认 top N：

- 窄项目：30
- 普通研究项目：50
- 综述或大方向启动：100 到 200，分批执行

已确认：

- 上述 top N 分档合适。
- 公开版 EA 不默认采用开发者本机 Zotero、浏览器、学校认证路径或本地文献库目录。
- 这些初始化信息应由用户配置、选择或确认。

待确认：

- 默认是否创建专用 literature thread，还是每次先询问？
- 是否允许优先下载开放获取全文，机构访问全文等用户登录后再处理？

## 8. 图像类数据

推荐默认方案：确认。

TEM、SEM、光学显微镜等采用 human-in-the-loop：

- 用户上传原图和描述。
- EA 读取图像、scale bar、仪器信息和用户描述。
- 能可靠判断时补充分析。
- 不可靠时，以用户描述为主证据，并追问关键缺失信息。
- 原图、处理图、用户描述、分析结论和 provenance 全部保存。

待确认：

- 是否要求图片类报告必须包含用户原始描述原文？

## 9. Git 基线

推荐默认方案：新建干净 `EAv0.2-build`，同时保留 v0.1 实现仓库为历史基线。

原因：

- 现有 v0.1 构建工作树较乱。
- 新建 v0.2 repo 更容易设定 `.gitignore`、tag、分支和阶段性回滚。
- v0.1 可以作为只读参考，降低误删风险。

建议流程：

1. 创建干净的 `EAv0.2-build` 实现仓库。
2. 导入 v0.1 必要源码，不导入临时输出和 demo artifact。
3. 初始化 git。
4. commit `v0.1.1-freeze-import`。
5. tag `v0.1.1-freeze`。
6. 创建分支 `codex/eav0.2`。
7. 每个阶段至少一个 commit。

已确认：

- 采用新建干净 `EAv0.2-build` 方案。
- 不把开发者本机私有配置、测试路径、浏览器 profile 或文献库路径导入公开版默认配置。

待确认：

- 是否已有 GitHub remote 需要绑定？

## 10. 后续实现时仍需确认

主干决策已经确认。进入实现时仍需在具体场景中确认：

- 是否已有 GitHub remote 需要绑定。
- 文献库专用 thread 是默认创建，还是每次先询问。
- 是否允许实验性未完全合规 skill 以 sandbox 模式运行。
- 报告默认语言是否跟随项目初始化配置。
- v0.2 是否同时导出 BibTeX/CSL JSON，还是先只做 Markdown references。
