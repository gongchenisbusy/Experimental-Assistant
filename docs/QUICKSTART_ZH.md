# Experimental Assistant v0.9.8 中文快速入门

EA 是一个本地优先的材料研究助手。公开名称是 Experimental Assistant，命令行是 `ea`，Codex 中唯一的 skill 入口是 `$ea`。

## 1. 安装

支持 Python 3.11、3.12 和 3.13，推荐 3.12。

```bash
uv tool install --python 3.12 git+https://github.com/gongchenisbusy/Experimental-Assistant.git@v0.9.8
ea setup
ea doctor
```

安装后重启 Codex，新建任务并调用 `$ea`。

## 2. 建立第一个项目

第一次命令只显示计划，不写入；确认路径和材料信息后再加 `--yes`。

```bash
ea start /path/to/project \
  --name "二维材料研究" \
  --material "MoS2" \
  --direction "电学和光谱表征"

ea start /path/to/project \
  --name "二维材料研究" \
  --material "MoS2" \
  --direction "电学和光谱表征" \
  --yes

ea status /path/to/project
```

## 3. 导入数据

先预览编码、分隔符、列、单位和 SHA-256，再导入同一个已确认文件。EA 不覆盖原始文件。

```bash
ea import preview /path/to/data.csv
ea import apply /path/to/project /path/to/data.csv --characterization-type raman --preview-hash SHA256 --yes
ea analyze /path/to/project raw/raman/RECORD/data.csv --method raman
```

标准流程是：检查数据、确认列和参数、处理、生成报告。EA 不应在没有审核记录时静默应用参数或把候选解释写成确定结论。

## 4. 交互模式

- `consult`：咨询和预览，项目零写入。
- `record`：确认后记录草稿、问题或审核信息，不执行正式分析。
- `execute`：确认后导入、处理、检索、作图、报告或导出。
- `audit`：只读检查健康状态、证据链、诊断和发布材料。

运行 `ea mode` 查看完整规则。

## 5. 文献数据 beta

v0.9.8 可以从用户合法获得的可搜索全文中提取窄范围的物性数据，保留页码/表格/图注/短上下文证据，并让用户逐条接受、拒绝、编辑、推迟或标记为不可比较。只有接受或编辑后的记录可以进入数据集和作图。

电导率、电阻率、方阻、方电导、接触电阻和迁移率不会被混为同一个量。扫描版 PDF 会明确提示需要 OCR，不会编造数值。

```bash
ea literature data-plan /path/to/project --help
ea literature data-extract /path/to/project --help
ea literature data-review /path/to/project --help
ea literature data-validate /path/to/project --help
ea literature data-plot /path/to/project --help
ea literature data-export /path/to/project --help
```

## 6. 检查和导出

```bash
ea healthcheck /path/to/project
ea brief project /path/to/project
ea trace index /path/to/project
ea export report-bundle /path/to/project --report-id REPORT_ID --include-trace --zip
ea export verify-archive /path/to/report-bundle.zip
```

## 7. 更新和排错

`ea update`、`ea rollback` 和 `ea uninstall` 默认只显示计划，执行替换或移除时需要 `--yes`。遇到错误先查看 `code`、`safe_to_retry`、`artifacts_written` 和 `next_steps`；错误目录见 `docs/ERROR_CATALOG.md`。

完整英文安装说明见 `docs/PUBLIC_INSTALL_AND_CODEX_SKILL_SETUP.md`，能力成熟度见 `docs/CAPABILITY_MATRIX.md`，已知限制见 `docs/V0_9_KNOWN_LIMITATIONS.md`。
