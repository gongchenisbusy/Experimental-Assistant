from __future__ import annotations

from pathlib import Path

import pandas as pd

from ea.provenance import write_provenance_entry
from ea.schema import ReportRecord
from ea.schema.models import EARecord
from ea.storage.files import read_yaml, write_markdown_record
from ea.storage.ids import next_id


FORBIDDEN_STRONG_CLAIMS = ["证明了", "毫无疑问", "机制已经确定", "完全说明"]


def _peak_summary(root: Path, peak_table_ref: str) -> str:
    peak_table = root / peak_table_ref
    peaks = pd.read_csv(peak_table)
    if peaks.empty:
        return "当前自动检峰未得到稳定峰位，需结合人工检查。"
    positions = []
    for value in peaks["position_cm-1"].head(6):
        positions.append(f"{float(value):.1f} cm^-1")
    return "自动检峰给出的主要峰位包括：" + "、".join(positions) + "。"


def generate_raman_report(
    root: Path,
    *,
    project_id: str,
    raman_metadata_path: Path,
    related_experiments: list[str] | None = None,
    related_samples: list[str] | None = None,
    created_at: str | None = None,
) -> Path:
    metadata = read_yaml(raman_metadata_path)
    report_id = next_id(root, "report")
    report_path = root / "reports" / f"{report_id}.md"
    related_experiments = related_experiments or []
    related_samples = related_samples or metadata.get("sample_refs", [])
    report = ReportRecord(
        report_id=report_id,
        project_id=project_id,
        report_type="raman_analysis",
        related_experiments=related_experiments,
        related_samples=related_samples,
        related_results=[metadata["raman_result_id"]],
        include_next_step_suggestions=False,
        status="draft",
        created_at=created_at or EARecord.now_iso(),
        updated_at=created_at or EARecord.now_iso(),
    )
    outputs = metadata["outputs"]
    peak_text = _peak_summary(root, outputs["peak_table"])
    warnings = metadata.get("warnings") or []
    warning_text = "；".join(
        warning.get("message", str(warning)) if isinstance(warning, dict) else str(warning)
        for warning in warnings
    ) or "未记录高风险 warning。"
    body = f"""# Raman 分析报告

## 数据来源

本报告基于 Raman processing result `{metadata['raman_result_id']}` 生成，关联样品为 `{', '.join(related_samples) if related_samples else '未明确映射样品'}`。原始数据、处理结果和图谱路径均通过 provenance 保留。

## 数据列与处理参数

用户确认的 x 列为 `{metadata['x_column']}`，y 列为 `{metadata['y_column']}`，Raman shift 单位记录为 `{metadata['x_unit']}`。处理参数为 `{metadata['processing_parameters']}`。

## 主要观察

{peak_text}这些峰位是脚本处理得到的 processed result，仍需要结合样品形貌、实验记录和用户审核进行解释。

## 谨慎解释

在当前数据范围内，图谱特征可能与 MoS2 Raman 响应相一致，但不能仅凭本次 Raman 数据直接确认层数、缺陷机制或生长机理。任何科学解释进入项目记忆前都需要用户审核。

## 不确定性与限制

{warning_text}

## 输出文件

- processed CSV: `{outputs['processed_csv']}`
- peak table: `{outputs['peak_table']}`
- plot: `{outputs['figure']}`
- metadata: `{outputs['metadata']}`

## 溯源

本报告草稿引用 Raman result `{metadata['raman_result_id']}`，对应 provenance 将在报告生成后写入。
"""
    for forbidden in FORBIDDEN_STRONG_CLAIMS:
        body = body.replace(forbidden, "")

    write_markdown_record(report_path, report.model_dump(exclude_none=True), body)
    provenance_path = write_provenance_entry(
        root,
        workflow="report_generation",
        inputs={
            "records": [str(raman_metadata_path.relative_to(root))],
            "files": [outputs["processed_csv"], outputs["peak_table"], outputs["figure"]],
        },
        outputs={"records": [str(report_path.relative_to(root))], "files": []},
        parameters={"include_next_step_suggestions": False, "language": "zh"},
        review_refs=[],
        warnings=warnings,
        created_at=created_at,
    )
    frontmatter = read_yaml_from_markdown_frontmatter(report_path)
    frontmatter["provenance_refs"] = [provenance_path.stem]
    write_markdown_record(report_path, frontmatter, body)
    return report_path


def read_yaml_from_markdown_frontmatter(path: Path) -> dict:
    from ea.storage.files import read_markdown_record

    frontmatter, _ = read_markdown_record(path)
    return frontmatter
