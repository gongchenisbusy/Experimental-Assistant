from __future__ import annotations

from pathlib import Path

import pandas as pd

from ea.figures import update_figure_report_ref
from ea.provenance import write_provenance_entry
from ea.references import build_report_reference_block
from ea.schema import ReportRecord
from ea.schema.models import EARecord
from ea.standards import infer_project_slug
from ea.storage.files import read_yaml, write_markdown_record, write_yaml
from ea.storage.ids import next_id, next_standard_id


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


def _peak_fit_table(root: Path, peak_table_ref: str) -> str:
    peak_table = root / peak_table_ref
    peaks = pd.read_csv(peak_table)
    if peaks.empty:
        return "当前没有可展示的自动检峰/拟合结果。"
    rows = [
        "| peak_id | position (cm^-1) | fit center (cm^-1) | FWHM (cm^-1) | prominence | assignment |",
        "|---|---:|---:|---:|---:|---|",
    ]
    sort_column = "prominence" if "prominence" in peaks.columns else "height"
    for _, peak in peaks.sort_values(sort_column, ascending=False).head(8).iterrows():
        fit_center = peak.get("fit_center_cm-1")
        fwhm = peak.get("fit_fwhm_cm-1")
        assignment = peak.get("assignment") if pd.notna(peak.get("assignment")) else ""
        rows.append(
            "| {peak_id} | {position:.1f} | {fit_center} | {fwhm} | {prominence:.3g} | {assignment} |".format(
                peak_id=peak["peak_id"],
                position=float(peak["position_cm-1"]),
                fit_center=f"{float(fit_center):.2f}" if pd.notna(fit_center) else "n/a",
                fwhm=f"{float(fwhm):.2f}" if pd.notna(fwhm) else "n/a",
                prominence=float(peak.get("prominence", 0.0)),
                assignment=assignment or "unassigned",
            )
        )
    return "\n".join(rows)


def _interpretation_text(metadata: dict, citation_text: str) -> str:
    peak_analysis = metadata.get("peak_analysis") or {}
    interpretations = peak_analysis.get("possible_interpretations") or []
    if not interpretations:
        return "- 当前 metadata 中没有可复用的自动解释结果；建议先复核检峰参数和样品背景。\n  - confidence: `insufficient`"
    lines: list[str] = []
    for item in interpretations:
        text = str(item.get("text", "No interpretation text recorded."))
        confidence = str(item.get("confidence", "insufficient"))
        evidence = ", ".join(str(value) for value in item.get("evidence", [])) or "未记录"
        separation = item.get("mode_separation_cm-1")
        suffix = f"；mode separation: `{float(separation):.2f} cm^-1`" if separation is not None else ""
        cite = citation_text if citation_text else ""
        lines.append(f"- {text}{cite}\n  - confidence: `{confidence}`；evidence peaks: `{evidence}`{suffix}")
    if not citation_text:
        lines.append("- 上述自动解释尚未绑定外部文献；若用于正式结论，应补充 reference_ids 并让用户审核。\n  - confidence: `insufficient`")
    return "\n".join(lines)


def generate_raman_report(
    root: Path,
    *,
    project_id: str,
    raman_metadata_path: Path,
    related_experiments: list[str] | None = None,
    related_samples: list[str] | None = None,
    reference_ids: list[str] | None = None,
    created_at: str | None = None,
) -> Path:
    metadata = read_yaml(raman_metadata_path)
    day = created_at[:10] if created_at else None
    if project_id.startswith("prj-"):
        report_id = next_standard_id(root, "report", infer_project_slug(project_id), day=day)
    else:
        report_id = next_id(root, "report", day)
    report_path = root / "reports" / f"{report_id}.md"
    related_experiments = related_experiments or []
    related_samples = related_samples or metadata.get("sample_refs", [])
    figure_ids = [metadata["figure_id"]] if metadata.get("figure_id") else []
    report = ReportRecord(
        report_id=report_id,
        project_id=project_id,
        report_type="raman_analysis",
        related_experiments=related_experiments,
        related_samples=related_samples,
        related_results=[metadata["raman_result_id"]],
        figure_ids=figure_ids,
        include_next_step_suggestions=False,
        status="draft",
        created_at=created_at or EARecord.now_iso(),
        updated_at=created_at or EARecord.now_iso(),
    )
    outputs = metadata["outputs"]
    peak_text = _peak_summary(root, outputs["peak_table"])
    peak_fit_table = _peak_fit_table(root, outputs["peak_table"])
    warnings = metadata.get("warnings") or []
    warning_text = "；".join(
        warning.get("message", str(warning)) if isinstance(warning, dict) else str(warning)
        for warning in warnings
    ) or "未记录高风险 warning。"
    reference_block = build_report_reference_block(root, reference_ids)
    citation_text = reference_block["inline_citation"]
    literature_note = f"相关解释应与已登记文献对应位置共同阅读{citation_text}。" if citation_text else "相关解释尚未绑定外部文献引用。"
    interpretation_text = _interpretation_text(metadata, citation_text)
    body = f"""# Raman 分析报告

## 报告 ID 信息

- report_id: `{report_id}`
- project_id: `{project_id}`
- result_ids: `{metadata['raman_result_id']}`
- figure_ids: `{', '.join(figure_ids) if figure_ids else '未生成 v0.2 figure_id'}`

## 数据来源

本报告基于 Raman processing result `{metadata['raman_result_id']}` 生成，关联样品为 `{', '.join(related_samples) if related_samples else '未明确映射样品'}`。原始数据、处理结果和图谱路径均通过 provenance 保留。

## 数据列与处理参数

用户确认的 x 列为 `{metadata['x_column']}`，y 列为 `{metadata['y_column']}`，Raman shift 单位记录为 `{metadata['x_unit']}`。处理参数为 `{metadata['processing_parameters']}`。

## 主要观察

{peak_text}这些峰位是脚本处理得到的 processed result，仍需要结合样品形貌、实验记录和用户审核进行解释。

## 拟合峰参数

{peak_fit_table}

## 可能结论与可信度

{interpretation_text}

## 谨慎解释

在当前数据范围内，自动峰位与拟合结果只能支持“可能解释”，不能仅凭本次 Raman 数据直接确认层数、缺陷机制或生长机理。{literature_note}任何科学解释进入项目记忆前都需要用户审核。

## 不确定性与限制

{warning_text}

## 输出文件

- processed CSV: `{outputs['processed_csv']}`
- peak table: `{outputs['peak_table']}`
- plot: `{outputs['figure']}`
- metadata: `{outputs['metadata']}`

## References

{reference_block['references_markdown']}

## 溯源

本报告草稿引用 Raman result `{metadata['raman_result_id']}`，对应 provenance 将在报告生成后写入。
"""
    for forbidden in FORBIDDEN_STRONG_CLAIMS:
        body = body.replace(forbidden, "")

    report_frontmatter = report.model_dump(exclude_none=True)
    report_frontmatter["reference_ids"] = reference_block["reference_ids"]
    report_frontmatter["numbered_references"] = reference_block["numbered_references"]
    write_markdown_record(report_path, report_frontmatter, body)
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
    if figure_ids:
        for figure_id in figure_ids:
            update_figure_report_ref(root, figure_id, report_id)
    register_report(
        root,
        report_id=report_id,
        path=str(report_path.relative_to(root)),
        project_id=project_id,
        result_ids=[metadata["raman_result_id"]],
        figure_ids=figure_ids,
        sample_ids=related_samples,
        experiment_ids=related_experiments,
        reference_ids=reference_block["reference_ids"],
    )
    return report_path


def read_yaml_from_markdown_frontmatter(path: Path) -> dict:
    from ea.storage.files import read_markdown_record

    frontmatter, _ = read_markdown_record(path)
    return frontmatter


def register_report(
    root: Path,
    *,
    report_id: str,
    path: str,
    project_id: str,
    result_ids: list[str],
    figure_ids: list[str],
    sample_ids: list[str],
    experiment_ids: list[str],
    reference_ids: list[str] | None = None,
) -> dict:
    index_path = root / "reports" / "index.yml"
    index = read_yaml(index_path) if index_path.exists() else {"schema_version": "0.2", "reports": {}}
    record = {
        "report_id": report_id,
        "path": path,
        "project_id": project_id,
        "result_ids": result_ids,
        "figure_ids": figure_ids,
        "sample_ids": sample_ids,
        "experiment_ids": experiment_ids,
        "reference_ids": reference_ids or [],
    }
    index.setdefault("reports", {})[report_id] = record
    write_yaml(index_path, index)
    return record
