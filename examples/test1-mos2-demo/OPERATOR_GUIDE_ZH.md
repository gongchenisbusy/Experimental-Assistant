# Experimental Assistant test1 MoS₂ Demo 维护说明

本说明用于维护已经完成的 15 组截图演示。公开展示采用截图与文字说明，不录制视频。

## 1. 展示目标

Demo 用一个 mica 上 CVD 生长 MoS₂ 候选片层的案例展示：

1. 用户用不完整自然语言提出研究目标和实验条件。
2. EA 创建项目并把已知、近似和未知条件分开记录。
3. 用户逐炉输入实验观察，EA 累计日志并进行跨炉比较。
4. EA 将形貌观察和用户推测分开，设计控制变量优化路线。
5. 条件改善后，EA 保存阶段标准并推荐表征样品和测点。
6. 用户上传 Raman、PL 和 AFM 数据，EA 生成综合分析与完整报告。

Demo 不应把任何单项表征或单次实验描述为无条件科学证明。

## 2. 问答分类

| 分类 | 文件 | 默认主图 |
|---|---|---|
| 研究目标与项目创建 | `01`–`02` | `01-project-goal.png` |
| 基线实验方法确认 | `03`–`05` | `03-baseline-conditions.png` |
| 连续实验日志与跨炉比较 | `06`–`10` | `07-cvd-run-002.png` |
| 供硫优化与阶段标准 | `11`–`13` | `13-cvd-run-006-stage-standard.png` |
| Raman、PL 与 AFM 综合分析 | `14`–`15` | `15-characterization-report.png` |
| 完整报告 | 公开 HTML | 报告关键结果摘要 |

所有问答图片都放在 `site/assets/qa/`。页面默认只显示每类主图，展开后按编号显示完整过程。

## 3. 数据文件

正式 Demo 只使用：

- `source-inputs/data/MoS-2(1).txt`：Raman；
- `source-inputs/data/MoS-PL-2(1).txt`：PL；
- `source-inputs/data/afm-user-annotated-0p79nm.png`：带 `0.79 nm` 标注的 AFM 图。

修改或替换数据前必须重新计算 `source-inputs/data/checksums.sha256`，并重新核对报告中的结果和限制。

## 4. 页面维护规则

- Demo 公开地址：`https://gongchenisbusy.github.io/Experimental-Assistant/demo/`
- 完整报告地址：`https://gongchenisbusy.github.io/Experimental-Assistant/`
- 不要把完整报告地址改回旧的托管域名。
- 不要在截图、页面或文档中加入本机绝对路径、账号、邮箱、token、cookie 或私人研究数据。
- 主图与详细问答使用同一张原始 PNG，不另外修改问答文字。
- 新增问答时同时更新页面、示例 README、自然语言脚本和截图编号。
- 详细图片使用延迟加载；完整报告只在用户展开时加载。

## 5. 发布检查

发布前至少确认：

- [ ] 页面包含 Q01–Q15，且顺序正确。
- [ ] 五类问答的默认主图正确。
- [ ] 每类可以独立展开和收起。
- [ ] “展开全部／收起全部”可用。
- [ ] 完整报告可在页面内展开，也可单独打开。
- [ ] 页面和 README 中的报告链接均为正确 GitHub Pages 根地址。
- [ ] 375 px 宽度下没有页面级横向溢出。
- [ ] 所有图片和静态资源返回成功。
- [ ] 公共发布检查未发现凭据或本机绝对路径。
