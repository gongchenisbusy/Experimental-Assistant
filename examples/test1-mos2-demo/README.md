# test1：mica 上 CVD MoS₂ 全流程公开 Demo

这个示例使用 15 组真实自然语言问答，展示 Experimental Assistant（EA）如何把一个材料研究目标逐步整理为项目基线、连续实验日志、工艺优化记录、表征分析和完整 HTML 报告。

- [打开在线 Demo](https://gongchenisbusy.github.io/Experimental-Assistant/demo/)
- [打开完整数据分析报告](https://gongchenisbusy.github.io/Experimental-Assistant/)
- [查看自然语言输入脚本](source-inputs/CONVERSATION_ZH.md)
- [查看演示维护说明](OPERATOR_GUIDE_ZH.md)

## 演示流程

| 阶段 | 问答 | 主要展示内容 |
|---|---:|---|
| 研究目标与项目创建 | Q01–Q02 | 从普通研究目标建立 EA 项目 |
| 基线实验方法确认 | Q03–Q05 | 提取不完整条件，保留未知项并确认基线 |
| 连续实验日志与跨炉比较 | Q06–Q10 | 逐炉记录、比较条件、区分事实与推测 |
| 供硫优化与阶段标准 | Q11–Q13 | 设计控制变量路线并形成阶段标准 S1 |
| Raman、PL 与 AFM 综合分析 | Q14–Q15 | 样品选择、三种表征交叉分析和报告输出 |
| 完整报告 | 独立页面 | 方法、图表、结果、限制和溯源摘要 |

在线页面每个阶段默认显示一张代表性问答。点击阶段下方的展开栏，可以按照原始顺序查看该阶段全部问答。完整报告既可以在 Demo 页面内展开，也可以通过独立链接打开。

## 公开输入数据

正式演示只使用一组 Raman、一组 PL 和一张用户标注 AFM 图：

| 文件 | 用途 | SHA-256 |
|---|---|---|
| `MoS-2(1).txt` | Raman | `3f8b57b8f993936c4a84efce82f658e8e2b31d8d637378a893aef9a69517cf51` |
| `MoS-PL-2(1).txt` | PL | `078cbe0e9659cd750efec9b6e0a5a494b615c32791225efbf3054d4822dd003b` |
| `afm-user-annotated-0p79nm.png` | AFM | `c4896c68b6337d3ba22a44dbdbf4631539e3e36860f6d99aa930667c696468e9` |

校验文件位于 [`source-inputs/data/checksums.sha256`](source-inputs/data/checksums.sha256)。

## 目录结构

```text
examples/test1-mos2-demo/
├── README.md
├── DATA-NOTICE.md
├── OPERATOR_GUIDE_ZH.md
├── source-inputs/
│   ├── CONVERSATION_ZH.md
│   └── data/
└── site/
    ├── index.html
    ├── styles.css
    ├── script.js
    └── assets/qa/              # 15 张整理后的问答图片
```

## 本地预览

这是一个不需要构建步骤的静态页面。在仓库根目录运行：

```bash
python3 -m http.server 8000 --directory examples/test1-mos2-demo/site
```

然后打开 `http://localhost:8000/`。本地预览中的完整报告 iframe 会继续加载公开报告链接。

## 科学边界

这个 Demo 展示的是研究记录和分析工作流，不构成对材料身份、层数、机理或整批样品均匀性的独立证明。最终结论只适用于本次被测片层和测量区域；Raman 仪器元数据与 AFM 原始高度矩阵等限制仍保留在完整报告中。
