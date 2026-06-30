# EA 本地文献库部署 Skill 设计

> 状态：v0.2 设计草案  
> 日期：2026-06-30  
> 参考：开发阶段可参考本机已有 `zotero-codex-literature` skill 和 Zotero 集成设计；公开版 EA 不默认依赖任何开发者本机路径或账号。

## 1. 定位

`local-literature-library` 是 EA 项目初始化的一部分。它不只是一次搜索文献，而是为项目建立可复用、可追踪、可更新的本地知识基础。

EA 初始化新项目时应检查：

- 是否已有项目文献库。
- 是否已有 Zotero collection 或本地全文缓存。
- 是否已有 `literature/library_manifest.yml`。
- 项目问题是否依赖文献背景或标准图谱解释。

如果没有文献库，EA 应建议用户创建，并说明创建文献库能提高后续分析报告、项目解释和参考文献追踪质量。

## 2. 与 zotero-codex 的关系

开发阶段可参考 `zotero-codex-literature` skill 作为底层能力来源。公开版 EA 不应复制它的全部逻辑，也不应假设用户的 Zotero、浏览器或文献缓存已经按开发者本机方式配置。EA 应在项目初始化时检测用户环境，并在项目层面调用或包装可用能力：

- 用户启用 Zotero 时，Zotero 作为文献信息和 PDF 附件的权威来源。
- 用户未启用 Zotero 时，EA 应支持降级到 DOI/BibTeX/网页链接/手动 PDF 索引。
- EA 项目只保存 Zotero item key、PDF/cache 路径、阅读缓存和项目相关性评分。
- 全文获取优先走 Zotero、开放获取和用户合法访问渠道。
- 不保存学校或出版社密码。
- 不绕过 SSO、MFA、CAPTCHA、机构访问限制或出版商反爬规则。
- 不直接修改 `zotero.sqlite`。

## 3. 公开用户初始化

文献库部署 skill 不得默认采用开发者本机信息。以下内容必须由用户配置、选择或确认：

- Zotero 是否安装，以及是否允许 EA 使用 Zotero Local API。
- Zotero project collection 名称或是否创建新 collection。
- 文献缓存根目录使用 EA 用户级默认目录，还是用户指定目录。
- 项目文献索引保存在哪个 EA 项目目录中。
- 是否允许浏览器辅助访问网页、开放获取 PDF 或用户可访问全文。
- 用户希望使用的浏览器和 profile。
- 是否存在机构登录、SSO、VPN、代理或学校图书馆入口。
- 是否只下载开放获取全文，还是允许用户手动登录后下载其有权访问的全文。

EA 可以提示用户如何完成登录，但不保存密码，不假设某所学校的认证路径，不读取开发者本机 Chrome profile 或 cookie。

## 4. 项目目录

建议项目中新增：

```text
literature/
├── library_manifest.yml
├── deployment_status.yml
├── search_queries.yml
├── search_log.md
├── candidates.csv
├── ranking.csv
├── acquisition_request.yml
├── zotero_codex_queries.jsonl
├── zotero_codex_targets.jsonl
├── zotero_codex_bridge.yml
├── zotero_codex_bridge.md
├── zotero_codex_settings_request.yml
├── acquisition_manifest.yml
├── selected_items.yml
├── references.bib
├── notes/
└── cache_index.yml
```

全文缓存应使用用户级配置决定的位置，例如 `{ea_user_cache_root}/literature-cache/`，或用户在初始化时指定的目录。开发者本机的 `~/.codex/...` 路径只能作为 local-test-only 示例，不能作为公开版默认值。项目中只保留索引和链接，避免 PDF 散乱复制。

## 5. 检索策略

用户提供项目初始化信息后，EA 应提取关键词：

- 材料体系和化学式。
- 制备方法和处理条件。
- 表征方法。
- 性能指标和应用场景。
- 用户关心的问题和假设。
- 同义词、缩写、旧称、相关相结构和常见英文表达。

“全网无遗漏”在工程上无法保证。EA 应采用“系统化多源检索 + 覆盖日志”的目标：尽量覆盖主要数据库、出版商、预印本和本地库，同时记录检索式、来源、时间和遗漏风险。

候选来源：

- Zotero 本地库。
- Crossref、OpenAlex、Semantic Scholar。
- PubMed 或 Europe PMC，适用于生物材料、生医或毒理方向。
- arXiv、ChemRxiv 和相关预印本平台。
- 出版商和 DOI 页面。
- Web of Science、Scopus、Google Scholar、CNKI、万方等，在用户有访问权限且工具可用时作为补充。

## 6. 排名模型

每篇候选文献给出综合分数：

```text
score =
  0.45 * project_relevance
+ 0.20 * venue_authority
+ 0.15 * recency
+ 0.10 * citation_or_influence
+ 0.10 * fulltext_availability_and_usefulness
```

时间分层：

- 5 年内：优先作为当前进展和方法参考。
- 5 到 15 年：作为成熟机制、常用方法和稳定结论参考。
- 15 年以上：若为奠基性论文、标准方法或经典谱图，不应被简单降权。

期刊影响因子：

- 若用户提供 Clarivate Journal Citation Reports 或其他权威表格，EA 可使用具体影响因子。
- 若没有授权数据，EA 不应伪造影响因子；可使用期刊层级、出版社、引用数、领域声誉、SJR/CiteScore 等可得 proxy，并明确标注来源。

## 7. 用户确认点

部署前必须向用户确认：

- 检索到的候选文献数量。
- 去重后的候选数量。
- 推荐下载的 top N。
- top N 的主题覆盖是否符合项目目标。
- 预计耗时、token 消耗、存储空间和可能需要用户登录的环节。
- 是否只下载开放获取全文，还是允许在用户登录机构账号后获取可访问全文。

默认建议：

- 窄项目：top 30。
- 普通研究项目：top 50。
- 综述或大方向启动：top 100 到 200，分批执行。

## 8. 专用聊天窗口

文献库部署可能消耗大量上下文。EA 设计上应支持专用 literature thread：

1. 原始项目窗口完成项目初始化和用户确认。
2. 用户确认后，EA 创建或建议创建专用文献库部署窗口。
3. 专用窗口执行检索、去重、排序、下载、缓存和阅读索引。
4. 专用窗口持续写入 `literature/deployment_status.yml`。
5. 原始窗口读取 status 文件并同步摘要，知道当前文献库完成到哪一步。

在 Codex 环境中，实际创建新窗口或线程需要可用 thread 工具，并应在用户确认后执行。若没有可用 thread 工具，EA 应生成 handoff 文件，要求用户在新窗口中继续。

## 9. 部署状态文件

`literature/deployment_status.yml` 示例：

```yaml
project_id: prj-lm-mos2
status: searching
literature_thread_id: null
last_updated: 2026-06-30T15:30:00+08:00
candidate_count: 428
deduped_count: 312
recommended_top_n: 50
selected_top_n: null
downloaded_fulltext: 0
cached_fulltext: 0
needs_user_login: []
blocked_items: []
summary_for_origin_thread: >
  Search strategy prepared. Awaiting user confirmation for top N download.
```

## 10. v0.2 最小实现

v0.2 建议先完成：

- 项目初始化时检查文献库状态。
- 用户环境检测和配置向导，不默认使用开发者本机 Zotero、浏览器、缓存或学校认证设置。
- 关键词生成和检索计划输出。
- 候选文献 ranking 表结构。
- 用户确认 top N 的流程。
- 与已有 `zotero-codex-literature` skill 的调用边界。
- `deployment_status.yml` 同步机制。
- 用户确认后生成 acquisition request 和 Zotero-Codex target manifest，但不在 EA 主项目窗口直接执行下载。
- 导入专用文献流程输出的 acquisition manifest，并同步 `library_manifest.yml`、`cache_index.yml`、项目引用记录和 origin-thread 状态。

自动批量下载和全文缓存可以作为 v0.2 后段或 v0.3 能力，前提是先验证访问权限、检索质量和上下文隔离机制。

## 11. 风险与修正

- “全网无遗漏”不可保证，应改为可审计的系统化覆盖。
- 影响因子不是完全开放的实时数据源，不能在无来源时硬编码或臆造。
- 全文下载必须遵守版权、机构访问和用户授权。
- 新线程同步需要工具支持；无工具时使用 status 文件和 handoff 文档。
- 开发者本机配置只能用于 local integration tests，不能进入公开版默认初始化路径。

## 12. 外部依据

[1] Clarivate. Journal Citation Reports and Journal Impact Factor information. Web: https://clarivate.com/academia-government/scientific-and-academic-research/research-funding-analytics/journal-citation-reports/  
[2] Zotero. Official documentation. Web: https://www.zotero.org/support/  
[3] OpenAlex. Documentation. Web: https://docs.openalex.org/  
