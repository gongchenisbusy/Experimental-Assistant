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


def _pl_peak_summary(root: Path, peak_table_ref: str) -> str:
    peak_table = root / peak_table_ref
    peaks = pd.read_csv(peak_table)
    if peaks.empty:
        return "当前自动检峰未得到稳定 PL 发光峰，需结合人工检查。"
    positions = []
    for _, peak in peaks.sort_values("prominence", ascending=False).head(5).iterrows():
        position = f"{float(peak['position']):.3f} {peak['position_unit']}"
        wavelength = peak.get("wavelength_nm")
        if pd.notna(wavelength):
            position += f" / {float(wavelength):.1f} nm"
        positions.append(position)
    return "自动检峰给出的主要 PL 峰位包括：" + "、".join(positions) + "。"


def _pl_peak_table(root: Path, peak_table_ref: str) -> str:
    peaks = pd.read_csv(root / peak_table_ref)
    if peaks.empty:
        return "当前没有可展示的自动 PL 检峰结果。"
    rows = [
        "| peak_id | position | wavelength (nm) | prominence | assignment |",
        "|---|---:|---:|---:|---|",
    ]
    for _, peak in peaks.sort_values("prominence", ascending=False).head(8).iterrows():
        wavelength = peak.get("wavelength_nm")
        rows.append(
            "| {peak_id} | {position:.4g} {unit} | {wavelength} | {prominence:.3g} | {assignment} |".format(
                peak_id=peak["peak_id"],
                position=float(peak["position"]),
                unit=peak["position_unit"],
                wavelength=f"{float(wavelength):.1f}" if pd.notna(wavelength) else "n/a",
                prominence=float(peak.get("prominence", 0.0)),
                assignment=peak.get("assignment") if pd.notna(peak.get("assignment")) and peak.get("assignment") else "unassigned",
            )
        )
    return "\n".join(rows)


def _pl_interpretation_text(metadata: dict, citation_text: str) -> str:
    peak_analysis = metadata.get("peak_analysis") or {}
    interpretations = peak_analysis.get("possible_interpretations") or []
    if not interpretations:
        return "- 当前 metadata 中没有可复用的 PL 自动解释结果；建议先复核检峰参数和样品背景。\n  - confidence: `insufficient`"
    lines: list[str] = []
    for item in interpretations:
        text = str(item.get("text", "No interpretation text recorded."))
        confidence = str(item.get("confidence", "insufficient"))
        evidence = ", ".join(str(value) for value in item.get("evidence", [])) or "未记录"
        cite = citation_text if citation_text else ""
        lines.append(f"- {text}{cite}\n  - confidence: `{confidence}`；evidence peaks: `{evidence}`")
    if not citation_text:
        lines.append("- 上述 PL 自动解释尚未绑定外部文献；若用于正式结论，应补充 reference_ids 并让用户审核。\n  - confidence: `insufficient`")
    return "\n".join(lines)


def generate_pl_report(
    root: Path,
    *,
    project_id: str,
    pl_metadata_path: Path,
    related_experiments: list[str] | None = None,
    related_samples: list[str] | None = None,
    reference_ids: list[str] | None = None,
    created_at: str | None = None,
) -> Path:
    metadata = read_yaml(pl_metadata_path)
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
        report_type="pl_analysis",
        related_experiments=related_experiments,
        related_samples=related_samples,
        related_results=[metadata["pl_result_id"]],
        figure_ids=figure_ids,
        include_next_step_suggestions=False,
        status="draft",
        created_at=created_at or EARecord.now_iso(),
        updated_at=created_at or EARecord.now_iso(),
    )
    outputs = metadata["outputs"]
    peak_text = _pl_peak_summary(root, outputs["peak_table"])
    peak_table = _pl_peak_table(root, outputs["peak_table"])
    warnings = metadata.get("warnings") or []
    warning_text = "；".join(
        warning.get("message", str(warning)) if isinstance(warning, dict) else str(warning)
        for warning in warnings
    ) or "未记录高风险 warning。"
    reference_block = build_report_reference_block(root, reference_ids)
    citation_text = reference_block["inline_citation"]
    literature_note = f"相关解释应与已登记文献对应位置共同阅读{citation_text}。" if citation_text else "相关解释尚未绑定外部文献引用。"
    interpretation_text = _pl_interpretation_text(metadata, citation_text)
    body = f"""# PL 分析报告

## 报告 ID 信息

- report_id: `{report_id}`
- project_id: `{project_id}`
- result_ids: `{metadata['pl_result_id']}`
- figure_ids: `{', '.join(figure_ids) if figure_ids else '未生成 v0.2 figure_id'}`

## 数据来源

本报告基于 PL processing result `{metadata['pl_result_id']}` 生成，关联样品为 `{', '.join(related_samples) if related_samples else '未明确映射样品'}`。原始数据、处理结果和图谱路径均通过 provenance 保留。

## 数据列与处理参数

用户确认的 x 列为 `{metadata['x_column']}`，y 列为 `{metadata['y_column']}`，PL x 轴单位记录为 `{metadata['x_unit']}`。处理参数为 `{metadata['processing_parameters']}`。

## 主要观察

{peak_text}这些峰位来自自动处理结果，仍需要结合样品背景、激发条件、Raman/XRD/显微结果和用户审核进行解释。

## PL 峰参数

{peak_table}

## 可能结论与可信度

{interpretation_text}

## 谨慎解释

在当前数据范围内，自动 PL 峰位只能支持“可能解释”，不能仅凭本次 PL 数据直接确认缺陷类型、能带结构变化或发光机制。{literature_note}任何科学解释进入项目记忆前都需要用户审核。

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

本报告草稿引用 PL result `{metadata['pl_result_id']}`，对应 provenance 将在报告生成后写入。
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
            "records": [str(pl_metadata_path.relative_to(root))],
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
        result_ids=[metadata["pl_result_id"]],
        figure_ids=figure_ids,
        sample_ids=related_samples,
        experiment_ids=related_experiments,
        reference_ids=reference_block["reference_ids"],
    )
    return report_path


def _xrd_peak_summary(root: Path, peak_table_ref: str) -> str:
    peak_table = root / peak_table_ref
    peaks = pd.read_csv(peak_table)
    if peaks.empty:
        return "当前自动检峰未得到稳定 XRD 衍射峰，需结合人工检查。"
    positions = []
    for _, peak in peaks.sort_values("prominence", ascending=False).head(6).iterrows():
        position = f"{float(peak['two_theta_deg']):.2f} deg"
        d_spacing = peak.get("d_spacing_angstrom")
        if pd.notna(d_spacing):
            position += f" / d={float(d_spacing):.3f} A"
        positions.append(position)
    return "自动检峰给出的主要 XRD 峰位包括：" + "、".join(positions) + "。"


def _xrd_peak_table(root: Path, peak_table_ref: str) -> str:
    peaks = pd.read_csv(root / peak_table_ref)
    if peaks.empty:
        return "当前没有可展示的自动 XRD 检峰结果。"
    rows = [
        "| peak_id | 2theta (deg) | d-spacing (A) | prominence | possible phase |",
        "|---|---:|---:|---:|---|",
    ]
    for _, peak in peaks.sort_values("prominence", ascending=False).head(10).iterrows():
        d_spacing = peak.get("d_spacing_angstrom")
        possible_phase = peak.get("possible_phase") if pd.notna(peak.get("possible_phase")) and peak.get("possible_phase") else "unassigned"
        rows.append(
            "| {peak_id} | {two_theta:.2f} | {d_spacing} | {prominence:.3g} | {possible_phase} |".format(
                peak_id=peak["peak_id"],
                two_theta=float(peak["two_theta_deg"]),
                d_spacing=f"{float(d_spacing):.3f}" if pd.notna(d_spacing) else "n/a",
                prominence=float(peak.get("prominence", 0.0)),
                possible_phase=possible_phase,
            )
        )
    return "\n".join(rows)


def _xrd_interpretation_text(metadata: dict, citation_text: str) -> str:
    peak_analysis = metadata.get("peak_analysis") or {}
    interpretations = peak_analysis.get("possible_interpretations") or []
    if not interpretations:
        return "- 当前 metadata 中没有可复用的 XRD 自动解释结果；建议先复核检峰参数、仪器条件和样品背景。\n  - confidence: `insufficient`"
    lines: list[str] = []
    for item in interpretations:
        text = str(item.get("text", "No interpretation text recorded."))
        confidence = str(item.get("confidence", "insufficient"))
        evidence = ", ".join(str(value) for value in item.get("evidence", [])) or "未记录"
        cite = citation_text if citation_text else ""
        lines.append(f"- {text}{cite}\n  - confidence: `{confidence}`；evidence peaks: `{evidence}`")
    if not citation_text:
        lines.append("- 上述 XRD 自动解释尚未绑定外部文献或相数据库；若用于正式结论，应补充 reference_ids 并让用户审核。\n  - confidence: `insufficient`")
    return "\n".join(lines)


def generate_xrd_report(
    root: Path,
    *,
    project_id: str,
    xrd_metadata_path: Path,
    related_experiments: list[str] | None = None,
    related_samples: list[str] | None = None,
    reference_ids: list[str] | None = None,
    created_at: str | None = None,
) -> Path:
    metadata = read_yaml(xrd_metadata_path)
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
        report_type="xrd_analysis",
        related_experiments=related_experiments,
        related_samples=related_samples,
        related_results=[metadata["xrd_result_id"]],
        figure_ids=figure_ids,
        include_next_step_suggestions=False,
        status="draft",
        created_at=created_at or EARecord.now_iso(),
        updated_at=created_at or EARecord.now_iso(),
    )
    outputs = metadata["outputs"]
    peak_text = _xrd_peak_summary(root, outputs["peak_table"])
    peak_table = _xrd_peak_table(root, outputs["peak_table"])
    warnings = metadata.get("warnings") or []
    warning_text = "；".join(
        warning.get("message", str(warning)) if isinstance(warning, dict) else str(warning)
        for warning in warnings
    ) or "未记录高风险 warning。"
    reference_block = build_report_reference_block(root, reference_ids)
    citation_text = reference_block["inline_citation"]
    literature_note = f"相关解释应与已登记文献或相数据库条目对应位置共同阅读{citation_text}。" if citation_text else "相关解释尚未绑定外部文献或相数据库引用。"
    interpretation_text = _xrd_interpretation_text(metadata, citation_text)
    wavelength = metadata.get("wavelength_angstrom")
    wavelength_text = f"{float(wavelength):.4f} A" if wavelength is not None else "未记录/不可计算"
    body = f"""# XRD 分析报告

## 报告 ID 信息

- report_id: `{report_id}`
- project_id: `{project_id}`
- result_ids: `{metadata['xrd_result_id']}`
- figure_ids: `{', '.join(figure_ids) if figure_ids else '未生成 v0.2 figure_id'}`

## 数据来源

本报告基于 XRD processing result `{metadata['xrd_result_id']}` 生成，关联样品为 `{', '.join(related_samples) if related_samples else '未明确映射样品'}`。原始数据、处理结果和图谱路径均通过 provenance 保留。

## 数据列与处理参数

用户确认的 x 列为 `{metadata['x_column']}`，y 列为 `{metadata['y_column']}`，XRD x 轴单位记录为 `{metadata['x_unit']}`。X-ray wavelength 为 `{wavelength_text}`。处理参数为 `{metadata['processing_parameters']}`。

## 主要观察

{peak_text}这些峰位来自自动处理结果，仍需要结合样品制备条件、仪器配置、相数据库、Raman/PL/显微结果和用户审核进行解释。

## XRD 峰参数

{peak_table}

## 可能结论与可信度

{interpretation_text}

## 谨慎解释

在当前数据范围内，自动 XRD 峰位只能支持“可能结构特征”，不能仅凭本次 XRD 数据直接确认相纯度、晶粒尺寸、应变、择优取向或精确晶格常数。{literature_note}任何科学解释进入项目记忆前都需要用户审核。

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

本报告草稿引用 XRD result `{metadata['xrd_result_id']}`，对应 provenance 将在报告生成后写入。
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
            "records": [str(xrd_metadata_path.relative_to(root))],
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
        result_ids=[metadata["xrd_result_id"]],
        figure_ids=figure_ids,
        sample_ids=related_samples,
        experiment_ids=related_experiments,
        reference_ids=reference_block["reference_ids"],
    )
    return report_path


def _ftir_band_summary(root: Path, peak_table_ref: str) -> str:
    bands = pd.read_csv(root / peak_table_ref)
    if bands.empty:
        return "当前自动检峰未得到稳定 FTIR band，需结合人工检查。"
    positions = []
    for _, band in bands.sort_values("prominence", ascending=False).head(6).iterrows():
        positions.append(f"{float(band['wavenumber_cm-1']):.0f} cm^-1")
    return "自动检峰给出的主要 FTIR band 位于：" + "、".join(positions) + "。"


def _ftir_band_table(root: Path, peak_table_ref: str) -> str:
    bands = pd.read_csv(root / peak_table_ref)
    if bands.empty:
        return "当前没有可展示的自动 FTIR band 检测结果。"
    rows = [
        "| band_id | wavenumber (cm^-1) | prominence | possible band family | confidence |",
        "|---|---:|---:|---|---|",
    ]
    for _, band in bands.sort_values("prominence", ascending=False).head(12).iterrows():
        family = band.get("possible_band_family") if pd.notna(band.get("possible_band_family")) and band.get("possible_band_family") else "unassigned"
        confidence = band.get("assignment_confidence") if pd.notna(band.get("assignment_confidence")) and band.get("assignment_confidence") else "insufficient"
        rows.append(
            "| {band_id} | {wavenumber:.0f} | {prominence:.3g} | {family} | {confidence} |".format(
                band_id=band["band_id"],
                wavenumber=float(band["wavenumber_cm-1"]),
                prominence=float(band.get("prominence", 0.0)),
                family=family,
                confidence=confidence,
            )
        )
    return "\n".join(rows)


def _ftir_interpretation_text(metadata: dict, citation_text: str) -> str:
    peak_analysis = metadata.get("peak_analysis") or {}
    interpretations = peak_analysis.get("possible_interpretations") or []
    if not interpretations:
        return "- 当前 metadata 中没有可复用的 FTIR 自动解释结果；建议先复核检峰参数、背景扣除和样品信息。\n  - confidence: `insufficient`"
    lines: list[str] = []
    for item in interpretations:
        text = str(item.get("text", "No interpretation text recorded."))
        confidence = str(item.get("confidence", "insufficient"))
        evidence = ", ".join(str(value) for value in item.get("evidence", [])) or "未记录"
        cite = citation_text if citation_text else ""
        source = str(item.get("assignment_source", "") or "未记录")
        lines.append(f"- {text}{cite}\n  - confidence: `{confidence}`；evidence bands: `{evidence}`；assignment_source: `{source}`")
    if not citation_text:
        lines.append("- 上述 FTIR 自动解释尚未绑定外部文献或参考谱库；若用于正式结论，应补充 reference_ids 并让用户审核。\n  - confidence: `insufficient`")
    return "\n".join(lines)


def generate_ftir_report(
    root: Path,
    *,
    project_id: str,
    ftir_metadata_path: Path,
    related_experiments: list[str] | None = None,
    related_samples: list[str] | None = None,
    reference_ids: list[str] | None = None,
    created_at: str | None = None,
) -> Path:
    metadata = read_yaml(ftir_metadata_path)
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
        report_type="ftir_analysis",
        related_experiments=related_experiments,
        related_samples=related_samples,
        related_results=[metadata["ftir_result_id"]],
        figure_ids=figure_ids,
        include_next_step_suggestions=False,
        status="draft",
        created_at=created_at or EARecord.now_iso(),
        updated_at=created_at or EARecord.now_iso(),
    )
    outputs = metadata["outputs"]
    band_text = _ftir_band_summary(root, outputs["peak_table"])
    band_table = _ftir_band_table(root, outputs["peak_table"])
    warnings = metadata.get("warnings") or []
    warning_text = "；".join(
        warning.get("message", str(warning)) if isinstance(warning, dict) else str(warning)
        for warning in warnings
    ) or "未记录高风险 warning。"
    reference_block = build_report_reference_block(root, reference_ids)
    citation_text = reference_block["inline_citation"]
    literature_note = f"相关解释应与已登记文献或参考谱库对应位置共同阅读{citation_text}。" if citation_text else "相关解释尚未绑定外部文献或参考谱库引用。"
    interpretation_text = _ftir_interpretation_text(metadata, citation_text)
    figure_rel = outputs["figure"]
    figure_embed = f"![FTIR spectrum](../{figure_rel})"
    body = f"""# FTIR 分析报告

## 报告 ID 信息

- report_id: `{report_id}`
- project_id: `{project_id}`
- result_ids: `{metadata['ftir_result_id']}`
- figure_ids: `{', '.join(figure_ids) if figure_ids else '未生成 v0.2 figure_id'}`

## 数据来源

本报告基于 FTIR processing result `{metadata['ftir_result_id']}` 生成，关联样品为 `{', '.join(related_samples) if related_samples else '未明确映射样品'}`。原始数据、处理结果和图谱路径均通过 provenance 保留。

## 数据列与处理参数

用户确认的 x 列为 `{metadata['x_column']}`，y 列为 `{metadata['y_column']}`，FTIR x 轴单位记录为 `{metadata['x_unit']}`，信号模式为 `{metadata.get('signal_mode', 'absorbance')}`。处理参数为 `{metadata['processing_parameters']}`。

## 图谱

{figure_embed}

原图文件：`{figure_rel}`

## 主要观察

{band_text}这些 band 来自自动处理结果，仍需要结合样品制备、背景/空气扣除、ATR 或透射模式、其他表征结果和用户审核进行解释。

## FTIR band 参数

{band_table}

## 可能结论与可信度

{interpretation_text}

## 谨慎解释

在当前数据范围内，自动 FTIR band family 只能支持“可能功能团或谱区提示”，不能仅凭本次 FTIR 数据直接确认化学组成、键合机制、表面吸附来源或反应路径。{literature_note}任何科学解释进入项目记忆前都需要用户审核。

## 不确定性与限制

{warning_text}

## 输出文件

- processed CSV: `{outputs['processed_csv']}`
- band table: `{outputs['peak_table']}`
- plot: `{outputs['figure']}`
- metadata: `{outputs['metadata']}`

## References

{reference_block['references_markdown']}

## 溯源

本报告草稿引用 FTIR result `{metadata['ftir_result_id']}`，对应 provenance 将在报告生成后写入。
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
            "records": [str(ftir_metadata_path.relative_to(root))],
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
        result_ids=[metadata["ftir_result_id"]],
        figure_ids=figure_ids,
        sample_ids=related_samples,
        experiment_ids=related_experiments,
        reference_ids=reference_block["reference_ids"],
    )
    return report_path


def _uv_vis_feature_summary(root: Path, peak_table_ref: str) -> str:
    features = pd.read_csv(root / peak_table_ref)
    if features.empty:
        return "当前自动检测未得到稳定 UV-Vis 光学特征，需结合人工检查。"
    positions = []
    for _, feature in features.sort_values("prominence", ascending=False).head(6).iterrows():
        wavelength = feature.get("wavelength_nm")
        energy = feature.get("energy_eV")
        if pd.notna(wavelength):
            text = f"{float(wavelength):.0f} nm"
            if pd.notna(energy):
                text += f" / {float(energy):.2f} eV"
        else:
            text = f"{float(feature['position']):.4g} {feature['position_unit']}"
        positions.append(text)
    return "自动检测给出的主要 UV-Vis 光学特征位于：" + "、".join(positions) + "。"


def _uv_vis_feature_table(root: Path, peak_table_ref: str) -> str:
    features = pd.read_csv(root / peak_table_ref)
    if features.empty:
        return "当前没有可展示的自动 UV-Vis 光学特征检测结果。"
    rows = [
        "| feature_id | position | wavelength (nm) | energy (eV) | prominence | feature type | confidence |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for _, feature in features.sort_values("prominence", ascending=False).head(10).iterrows():
        wavelength = feature.get("wavelength_nm")
        energy = feature.get("energy_eV")
        confidence = feature.get("assignment_confidence") if pd.notna(feature.get("assignment_confidence")) and feature.get("assignment_confidence") else "insufficient"
        rows.append(
            "| {feature_id} | {position:.4g} {unit} | {wavelength} | {energy} | {prominence:.3g} | {feature_type} | {confidence} |".format(
                feature_id=feature["feature_id"],
                position=float(feature["position"]),
                unit=feature["position_unit"],
                wavelength=f"{float(wavelength):.1f}" if pd.notna(wavelength) else "n/a",
                energy=f"{float(energy):.3f}" if pd.notna(energy) else "n/a",
                prominence=float(feature.get("prominence", 0.0)),
                feature_type=feature.get("feature_type") if pd.notna(feature.get("feature_type")) and feature.get("feature_type") else "optical_feature",
                confidence=confidence,
            )
        )
    return "\n".join(rows)


def _uv_vis_edge_text(metadata: dict) -> str:
    edge = (metadata.get("peak_analysis") or {}).get("edge_estimate")
    if not edge:
        return "当前没有记录自动 optical edge 估计。"
    wavelength = edge.get("wavelength_nm")
    energy = edge.get("energy_eV")
    wavelength_text = f"{float(wavelength):.1f} nm" if wavelength is not None else "n/a"
    energy_text = f"{float(energy):.3f} eV" if energy is not None else "n/a"
    confidence = edge.get("confidence", "low")
    source = edge.get("assignment_source", "ea.uv_vis.edge_threshold:v0.2")
    return f"自动阈值法记录的 optical edge 估计为 `{wavelength_text}` / `{energy_text}`；confidence: `{confidence}`；assignment_source: `{source}`。"


def _uv_vis_interpretation_text(metadata: dict, citation_text: str) -> str:
    peak_analysis = metadata.get("peak_analysis") or {}
    interpretations = peak_analysis.get("possible_interpretations") or []
    if not interpretations:
        return "- 当前 metadata 中没有可复用的 UV-Vis 自动解释结果；建议先复核列选择、信号模式、样品背景和处理参数。\n  - confidence: `insufficient`"
    lines: list[str] = []
    for item in interpretations:
        text = str(item.get("text", "No interpretation text recorded."))
        confidence = str(item.get("confidence", "insufficient"))
        evidence = ", ".join(str(value) for value in item.get("evidence", [])) or "未记录"
        cite = citation_text if citation_text else ""
        source = str(item.get("assignment_source", "") or "未记录")
        lines.append(f"- {text}{cite}\n  - confidence: `{confidence}`；evidence features: `{evidence}`；assignment_source: `{source}`")
    if not citation_text:
        lines.append("- 上述 UV-Vis 自动解释尚未绑定外部文献或项目参考谱；若用于正式结论，应补充 reference_ids 并让用户审核。\n  - confidence: `insufficient`")
    return "\n".join(lines)


def generate_uv_vis_report(
    root: Path,
    *,
    project_id: str,
    uv_vis_metadata_path: Path,
    related_experiments: list[str] | None = None,
    related_samples: list[str] | None = None,
    reference_ids: list[str] | None = None,
    created_at: str | None = None,
) -> Path:
    metadata = read_yaml(uv_vis_metadata_path)
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
        report_type="uv_vis_analysis",
        related_experiments=related_experiments,
        related_samples=related_samples,
        related_results=[metadata["uv_vis_result_id"]],
        figure_ids=figure_ids,
        include_next_step_suggestions=False,
        status="draft",
        created_at=created_at or EARecord.now_iso(),
        updated_at=created_at or EARecord.now_iso(),
    )
    outputs = metadata["outputs"]
    feature_text = _uv_vis_feature_summary(root, outputs["peak_table"])
    feature_table = _uv_vis_feature_table(root, outputs["peak_table"])
    edge_text = _uv_vis_edge_text(metadata)
    warnings = metadata.get("warnings") or []
    warning_text = "；".join(
        warning.get("message", str(warning)) if isinstance(warning, dict) else str(warning)
        for warning in warnings
    ) or "未记录高风险 warning。"
    reference_block = build_report_reference_block(root, reference_ids)
    citation_text = reference_block["inline_citation"]
    literature_note = f"相关解释应与已登记文献或项目参考谱对应位置共同阅读{citation_text}。" if citation_text else "相关解释尚未绑定外部文献或项目参考谱引用。"
    interpretation_text = _uv_vis_interpretation_text(metadata, citation_text)
    figure_rel = outputs["figure"]
    figure_embed = f"![UV-Vis spectrum](../{figure_rel})"
    body = f"""# UV-Vis 分析报告

## 报告 ID 信息

- report_id: `{report_id}`
- project_id: `{project_id}`
- result_ids: `{metadata['uv_vis_result_id']}`
- figure_ids: `{', '.join(figure_ids) if figure_ids else '未生成 v0.2 figure_id'}`

## 数据来源

本报告基于 UV-Vis processing result `{metadata['uv_vis_result_id']}` 生成，关联样品为 `{', '.join(related_samples) if related_samples else '未明确映射样品'}`。原始数据、处理结果和图谱路径均通过 provenance 保留。

## 数据列与处理参数

用户确认的 x 列为 `{metadata['x_column']}`，y 列为 `{metadata['y_column']}`，UV-Vis x 轴单位记录为 `{metadata['x_unit']}`，信号模式为 `{metadata.get('signal_mode', 'absorbance')}`。处理参数为 `{metadata['processing_parameters']}`。

## 图谱

{figure_embed}

原图文件：`{figure_rel}`

## 主要观察

{feature_text}这些光学特征来自自动处理结果，仍需要结合样品厚度、透射/反射/吸收模式、基底背景、积分球或薄膜几何、其他表征结果和用户审核进行解释。

## UV-Vis feature 参数

{feature_table}

## Optical edge 估计

{edge_text}

## 可能结论与可信度

{interpretation_text}

## 谨慎解释

在当前数据范围内，自动 UV-Vis 特征和阈值 edge 只能支持“光学响应筛查”。不能仅凭本次处理结果直接确认带隙、跃迁类型、缺陷态、膜厚效应或吸收机制；正式 Tauc/derivative/Kubelka-Munk 等分析需要用户确认模型、样品形态和文献依据。{literature_note}任何科学解释进入项目记忆前都需要用户审核。

## 不确定性与限制

{warning_text}

## 输出文件

- processed CSV: `{outputs['processed_csv']}`
- feature table: `{outputs['peak_table']}`
- plot: `{outputs['figure']}`
- metadata: `{outputs['metadata']}`

## References

{reference_block['references_markdown']}

## 溯源

本报告草稿引用 UV-Vis result `{metadata['uv_vis_result_id']}`，对应 provenance 将在报告生成后写入。
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
            "records": [str(uv_vis_metadata_path.relative_to(root))],
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
        result_ids=[metadata["uv_vis_result_id"]],
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
