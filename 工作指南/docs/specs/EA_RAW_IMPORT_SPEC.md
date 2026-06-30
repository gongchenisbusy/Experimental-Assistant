# EA Raw Import Spec

> 版本：v0.1-p0-draft  
> 日期：2026-06-01  
> 优先级：P0  
> 用途：定义 EA v0.1 raw 文件导入、hash、去重、更名、只读和 raw/processed 边界。  

---

## 1. 核心原则

raw 文件是科研原始数据资产。

EA 可以：

- 读取 raw。
- 复制 raw 到项目目录。
- 计算 hash。
- 建立 metadata。
- 建立样品和实验关联。

EA 不可以：

- 修改 raw。
- 覆盖 raw。
- 清洗后写回 raw。
- 将 processed 输出放入 raw。

---

## 2. 导入策略

v0.1 默认采用：

```text
受控只读副本 + 原始路径记录 + SHA-256 hash
```

导入流程：

```text
用户提供文件路径或拖入文件
→ EA 检查文件存在性和可读性
→ EA 计算 SHA-256
→ EA 检查项目内是否已有相同 hash
→ 如无重复，复制到 raw/
→ 如重复，新增 alias/import record
→ 写 CharacterizationFile metadata
→ 写 provenance
```

---

## 3. 项目内路径规则

推荐路径：

```text
raw/{characterization_type}/{characterization_id}/{original_filename}
raw/{characterization_type}/{characterization_id}/metadata.yml
```

示例：

```text
raw/raman/char-20260601-001/sample001.txt
raw/raman/char-20260601-001/metadata.yml
```

文件名保留原始文件名，但路径中的 `characterization_id` 保证唯一。

---

## 4. Metadata 字段

```yaml
characterization_id:
characterization_type: raman
project_id:
sample_refs: []
experiment_refs: []
original_filename:
original_source_path:
project_raw_path:
sha256:
file_size_bytes:
original_mtime:
imported_at:
import_status: imported | duplicate_alias | needs_review | failed
aliases: []
notes:
provenance_refs: []
review_refs: []
```

---

## 5. 去重规则

如果新文件 SHA-256 与已有 raw 文件相同：

- 不重复复制文件内容。
- 新增 `aliases` 或 import record。
- 记录新的原始路径、文件名、导入时间和用户提供的样品关联。
- 如果用户声称它对应不同样品，EA 必须提示用户确认。

示例：

```yaml
import_status: duplicate_alias
canonical_raw_ref: char-20260601-001
alias_reason: same_sha256
```

---

## 6. 文件更名处理

文件名不是数据身份。

数据身份优先由以下组合确定：

- SHA-256。
- 文件大小。
- 内容。
- 导入时间。
- 原始路径。
- 用户提供的样品关联。

同一内容更名后再次导入，应识别为同一 raw 数据的 alias。

---

## 7. Hash 冲突策略

SHA-256 冲突极罕见，但 v0.1 应有保守处理：

如果 hash 相同但文件大小、部分内容或用户描述明显冲突：

- 标记 `needs_review`。
- 不自动合并。
- 请求用户确认。
- 在 provenance 中记录冲突。

辅助检查：

- file size。
- first bytes hash。
- last bytes hash。
- original filename。
- original path。

---

## 8. 只读保护

v0.1 应至少做到：

- 代码逻辑不写入 raw 文件。
- processed 输出路径不能位于 `raw/`。
- metadata 写在 raw 文件旁边可以，但不得覆盖原始数据文件。
- 文件导入后可尝试设置只读权限。

如因系统权限无法设置只读，必须在 metadata 中记录 warning。

---

## 9. Raw 与 processed 边界

| 类型 | 路径 | 是否可修改 |
|---|---|---|
| 原始仪器文件 | `raw/` | 不可修改 |
| raw metadata | `raw/.../metadata.yml` | 可追加/更新 |
| 处理后 CSV | `processed/` | 可生成新版本 |
| 图谱 | `processed/` | 可生成新版本 |
| 峰表 | `processed/` | 可生成新版本 |
| 报告 | `reports/` | 可生成新版本 |

---

## 10. 失败处理

导入失败情况：

- 文件不存在。
- 无读取权限。
- 文件为空。
- hash 计算失败。
- 复制失败。
- 项目路径不可写。

失败时：

- 不创建正式 CharacterizationFile。
- 创建 open item 或 error provenance。
- 告知用户。

---

## 11. v0.1 验收

必须验证：

- 同一文件重复导入不会复制两份内容。
- 文件更名后可识别为相同 raw。
- raw 不被处理脚本覆盖。
- processed 输出不进入 raw。
- metadata 记录原始路径、项目路径、hash、size、导入时间。
- provenance 记录导入过程。

