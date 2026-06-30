# EA 公开发布与初始化设计约束

> 状态：v0.2 设计要求  
> 日期：2026-06-30  
> 用途：确保 EA 面向陌生用户可用，而不是绑定到开发者本机环境。

## 1. 总原则

EA 最终需要公开给其他用户使用。因此，设计和实现默认面向陌生用户环境，不能默认采用开发者本机已有路径、账号、浏览器、Zotero 配置、学校认证路径或本地文献库位置。

开发者本机信息只能作为测试 fixture、迁移参考或调试输入，不能写成产品默认值。

## 2. 禁止作为默认值的信息

以下信息不得硬编码为 EA 默认配置：

- 开发者本机 Zotero 数据目录、collection 名称或 item key。
- 开发者本机文献缓存路径。
- 学校/机构认证入口、SSO 路径、VPN 或代理设置。
- Google Chrome、Chrome profile、浏览器扩展或 cookie 状态。
- 任何个人账号、学校账号、出版社登录状态。
- 当前项目中的测试数据路径。
- `/Users/geecoe/...` 等开发者本机绝对路径。

这些信息可以出现在测试文档或本机开发说明中，但必须标记为 `local-test-only`。

## 3. 初始化时应向用户索取的信息

EA 初始化项目时，如需要相关能力，应通过配置向导或明确追问获得：

- 项目根目录。
- 项目名称和 `project_slug`。
- 默认报告语言。
- 原始数据导入来源目录。
- 是否启用 Zotero。
- Zotero 是否已安装、是否可访问 Local API、是否需要创建 project collection。
- 文献缓存目录使用 EA 默认用户目录还是用户指定目录。
- 是否允许使用浏览器辅助获取开放网页或用户可访问全文。
- 用户希望使用的浏览器和 profile。
- 是否存在机构访问、SSO 或代理；如存在，EA 只提示用户手动登录，不保存凭据。
- 是否启用本地文献库部署，以及初始 top N 规模。

## 4. 配置文件

公开版 EA 应使用用户级配置和项目级配置分层。

用户级配置示例：

```text
~/.ea/config.yml
```

项目级配置示例：

```text
ea-project/EA_PROJECT.md
ea-project/PROJECT_RULE_CARD.md
ea-project/.ea/project_config.yml
```

用户级配置可保存工具路径、默认缓存根目录和偏好设置；项目级配置保存项目 slug、数据目录、文献库选择、报告语言和项目规则。

敏感信息不写入配置文件。需要登录时，EA 应暂停并提示用户在浏览器中手动完成。

## 5. 测试策略

测试可以读取本机已有资源，但必须隔离：

- 测试配置放在 `tests/fixtures/local/` 或等价位置。
- 测试数据路径和本机资源标记为 `local-test-only`。
- CI/public tests 不依赖开发者本机 Zotero、浏览器登录状态或学校网络。
- public tests 使用小型公开数据和 mock 文献记录。
- integration/local tests 可以验证真实 Zotero、浏览器和本地缓存。

## 6. v0.2 实施要求

v0.2 构建时必须：

- 新建干净 `EAv0.2-build`。
- 不把当前机器的私有路径写入产品默认配置。
- 为 project init、literature init 和 browser-assisted acquisition 提供配置向导或明确追问。
- 把本机已有 `zotero-codex-literature` 作为参考和可选底层能力，而不是公开版 EA 的唯一默认环境。
- 在 README 或安装文档中区分 public setup、developer setup、local integration test setup。

