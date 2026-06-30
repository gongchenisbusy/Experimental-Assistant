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


def _uv_vis_tauc_text(metadata: dict) -> str:
    tauc = (metadata.get("peak_analysis") or {}).get("tauc_analysis")
    if not tauc:
        return "当前没有启用或记录 Tauc/Kubelka-Munk screening 分析。"
    status = tauc.get("status", "unknown")
    transform = tauc.get("transform", "unknown")
    transition = tauc.get("transition", "unknown")
    exponent = tauc.get("exponent", "unknown")
    confidence = tauc.get("confidence", "insufficient")
    source = tauc.get("assignment_source", "ea.uv_vis.tauc_screening:v0.2")
    fit_window = tauc.get("fit_window_eV") or []
    window_text = f"{float(fit_window[0]):.3g}-{float(fit_window[1]):.3g} eV" if len(fit_window) == 2 else "not recorded"
    if status != "screening_fit_recorded":
        return (
            f"Tauc/Kubelka-Munk screening 状态为 `{status}`；transform: `{transform}`；transition: `{transition}`；"
            f"exponent: `{exponent}`；fit window: `{window_text}`；confidence: `{confidence}`；assignment_source: `{source}`。"
        )
    intercept = tauc.get("intercept_energy_eV")
    intercept_text = f"{float(intercept):.3f} eV" if intercept is not None else "n/a"
    r2 = tauc.get("r2")
    r2_text = f"{float(r2):.3f}" if r2 is not None else "n/a"
    return (
        f"Reviewed-parameter Tauc/Kubelka-Munk screening 使用 `{transform}` transform、`{transition}` transition "
        f"(exponent `{exponent}`)，fit window 为 `{window_text}`，线性外推截距为 `{intercept_text}`，R2 为 `{r2_text}`；"
        f"confidence: `{confidence}`；assignment_source: `{source}`。该值只作为筛查记录，不等同于最终 optical band gap。"
    )


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
    tauc_text = _uv_vis_tauc_text(metadata)
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

## Tauc/Kubelka-Munk screening

{tauc_text}

## 可能结论与可信度

{interpretation_text}

## 谨慎解释

在当前数据范围内，自动 UV-Vis 特征和阈值 edge 只能支持“光学响应筛查”。不能仅凭本次处理结果直接确认带隙、跃迁类型、缺陷态、膜厚效应或吸收机制；正式 Tauc/derivative/Kubelka-Munk 等分析需要用户确认模型、样品形态和文献依据。{literature_note}任何科学解释进入项目记忆前都需要用户审核。

## 不确定性与限制

{warning_text}

## 输出文件

- processed CSV: `{outputs['processed_csv']}`
- feature table: `{outputs['peak_table']}`
{f"- Tauc/Kubelka-Munk table: `{outputs['tauc_table']}`" if outputs.get('tauc_table') else "- Tauc/Kubelka-Munk table: `未生成`"}
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


def _xps_peak_summary(root: Path, peak_table_ref: str) -> str:
    peaks = pd.read_csv(root / peak_table_ref)
    if peaks.empty:
        return "当前自动检测未得到稳定 XPS peak，需结合人工检查。"
    positions = []
    for _, peak in peaks.sort_values("prominence", ascending=False).head(8).iterrows():
        positions.append(f"{float(peak['binding_energy_eV']):.2f} eV")
    return "自动检测给出的主要 XPS peak binding energy 包括：" + "、".join(positions) + "。"


def _xps_peak_table(root: Path, peak_table_ref: str) -> str:
    peaks = pd.read_csv(root / peak_table_ref)
    if peaks.empty:
        return "当前没有可展示的自动 XPS peak 检测结果。"
    rows = [
        "| peak_id | binding energy (eV) | raw energy | prominence | component model | assignment | confidence |",
        "|---|---:|---:|---:|---|---|---|",
    ]
    for _, peak in peaks.sort_values("prominence", ascending=False).head(12).iterrows():
        assignment = peak.get("possible_assignment") if pd.notna(peak.get("possible_assignment")) and peak.get("possible_assignment") else "unassigned"
        confidence = peak.get("assignment_confidence") if pd.notna(peak.get("assignment_confidence")) and peak.get("assignment_confidence") else "insufficient"
        rows.append(
            "| {peak_id} | {energy:.2f} | {raw_energy:.2f} | {prominence:.3g} | {model} | {assignment} | {confidence} |".format(
                peak_id=peak["peak_id"],
                energy=float(peak["binding_energy_eV"]),
                raw_energy=float(peak["raw_binding_energy"]),
                prominence=float(peak.get("prominence", 0.0)),
                model=peak.get("component_model") if pd.notna(peak.get("component_model")) and peak.get("component_model") else "not_fitted",
                assignment=assignment,
                confidence=confidence,
            )
        )
    return "\n".join(rows)


def _xps_component_summary(metadata: dict) -> str:
    summary = (metadata.get("peak_analysis") or {}).get("component_quantification") or {}
    if not summary:
        return "当前没有记录 XPS component quantification screening。"
    if not summary.get("enabled"):
        return "当前未启用 XPS component quantification screening；如需组分面积/RSF 筛查，应先由用户确认 component windows、背景/模型和 sensitivity factors。"
    status = summary.get("status", "unknown")
    count = summary.get("quantified_component_count", 0)
    rsf_complete = summary.get("rsf_complete", False)
    source = summary.get("assignment_source", "ea.xps.component_quantification:v0.2")
    return (
        f"Reviewed component window integration 状态为 `{status}`；已积分 component 数量为 `{count}`；"
        f"RSF complete: `{rsf_complete}`；assignment_source: `{source}`。这些结果是筛查记录，不等同于最终化学态或定量组成。"
    )


def _xps_component_table(root: Path, component_table_ref: str | None) -> str:
    if not component_table_ref:
        return "当前没有 component table 输出。"
    components = pd.read_csv(root / component_table_ref)
    if components.empty:
        return "当前没有可展示的 XPS component quantification screening 结果。"
    rows = [
        "| component_id | label | element/core | window (eV) | centroid (eV) | area % | atomic % screening | confidence | status |",
        "|---|---|---|---:|---:|---:|---:|---|---|",
    ]
    for _, component in components.head(12).iterrows():
        element = component.get("element") if pd.notna(component.get("element")) and component.get("element") else ""
        core = component.get("core_level") if pd.notna(component.get("core_level")) and component.get("core_level") else ""
        element_core = "/".join(part for part in [str(element), str(core)] if part) or "n/a"
        low = component.get("binding_energy_min_eV")
        high = component.get("binding_energy_max_eV")
        centroid = component.get("centroid_eV")
        area_percent = component.get("relative_area_percent")
        atomic_percent = component.get("relative_atomic_percent_screening")
        rows.append(
            "| {component_id} | {label} | {element_core} | {window} | {centroid} | {area_percent} | {atomic_percent} | {confidence} | {status} |".format(
                component_id=component.get("component_id", ""),
                label=component.get("label", ""),
                element_core=element_core,
                window=f"{float(low):.2f}-{float(high):.2f}" if pd.notna(low) and pd.notna(high) else "n/a",
                centroid=f"{float(centroid):.2f}" if pd.notna(centroid) else "n/a",
                area_percent=f"{float(area_percent):.2f}" if pd.notna(area_percent) else "n/a",
                atomic_percent=f"{float(atomic_percent):.2f}" if pd.notna(atomic_percent) else "n/a",
                confidence=component.get("confidence") if pd.notna(component.get("confidence")) else "insufficient",
                status=component.get("status") if pd.notna(component.get("status")) else "unknown",
            )
        )
    return "\n".join(rows)


def _xps_calibration_text(metadata: dict) -> str:
    calibration = (metadata.get("peak_analysis") or {}).get("calibration") or {}
    shift = float(metadata.get("energy_shift_eV", calibration.get("energy_shift_eV", 0.0)))
    reference = metadata.get("calibration_reference") or calibration.get("calibration_reference") or "未记录"
    confidence = calibration.get("confidence", "insufficient")
    return f"本次处理记录的 binding-energy shift 为 `{shift:.3f} eV`；calibration reference 为 `{reference}`；confidence: `{confidence}`。"


def _xps_interpretation_text(metadata: dict, citation_text: str) -> str:
    peak_analysis = metadata.get("peak_analysis") or {}
    interpretations = peak_analysis.get("possible_interpretations") or []
    if not interpretations:
        return "- 当前 metadata 中没有可复用的 XPS 自动解释结果；建议先复核能量校准、背景模型、峰模型和样品背景。\n  - confidence: `insufficient`"
    lines: list[str] = []
    for item in interpretations:
        text = str(item.get("text", "No interpretation text recorded."))
        confidence = str(item.get("confidence", "insufficient"))
        evidence = ", ".join(str(value) for value in item.get("evidence", [])) or "未记录"
        cite = citation_text if citation_text else ""
        source = str(item.get("assignment_source", "") or "未记录")
        lines.append(f"- {text}{cite}\n  - confidence: `{confidence}`；evidence peaks: `{evidence}`；assignment_source: `{source}`")
    if not citation_text:
        lines.append("- 上述 XPS 自动解释尚未绑定外部文献、标准谱库或项目参考谱；若用于正式化学态判断，应补充 reference_ids 并让用户审核。\n  - confidence: `insufficient`")
    return "\n".join(lines)


def generate_xps_report(
    root: Path,
    *,
    project_id: str,
    xps_metadata_path: Path,
    related_experiments: list[str] | None = None,
    related_samples: list[str] | None = None,
    reference_ids: list[str] | None = None,
    created_at: str | None = None,
) -> Path:
    metadata = read_yaml(xps_metadata_path)
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
        report_type="xps_analysis",
        related_experiments=related_experiments,
        related_samples=related_samples,
        related_results=[metadata["xps_result_id"]],
        figure_ids=figure_ids,
        include_next_step_suggestions=False,
        status="draft",
        created_at=created_at or EARecord.now_iso(),
        updated_at=created_at or EARecord.now_iso(),
    )
    outputs = metadata["outputs"]
    peak_text = _xps_peak_summary(root, outputs["peak_table"])
    peak_table = _xps_peak_table(root, outputs["peak_table"])
    component_summary = _xps_component_summary(metadata)
    component_table = _xps_component_table(root, outputs.get("component_table"))
    calibration_text = _xps_calibration_text(metadata)
    warnings = metadata.get("warnings") or []
    warning_text = "；".join(
        warning.get("message", str(warning)) if isinstance(warning, dict) else str(warning)
        for warning in warnings
    ) or "未记录高风险 warning。"
    reference_block = build_report_reference_block(root, reference_ids)
    citation_text = reference_block["inline_citation"]
    literature_note = f"相关解释应与已登记文献、标准谱库或项目参考谱对应位置共同阅读{citation_text}。" if citation_text else "相关解释尚未绑定外部文献、标准谱库或项目参考谱引用。"
    interpretation_text = _xps_interpretation_text(metadata, citation_text)
    figure_rel = outputs["figure"]
    figure_embed = f"![XPS spectrum](../{figure_rel})"
    body = f"""# XPS 分析报告

## 报告 ID 信息

- report_id: `{report_id}`
- project_id: `{project_id}`
- result_ids: `{metadata['xps_result_id']}`
- figure_ids: `{', '.join(figure_ids) if figure_ids else '未生成 v0.2 figure_id'}`

## 数据来源

本报告基于 XPS processing result `{metadata['xps_result_id']}` 生成，关联样品为 `{', '.join(related_samples) if related_samples else '未明确映射样品'}`。原始数据、处理结果和图谱路径均通过 provenance 保留。

## 数据列、校准与处理参数

用户确认的 x 列为 `{metadata['x_column']}`，y 列为 `{metadata['y_column']}`，XPS x 轴单位记录为 `{metadata['x_unit']}`。{calibration_text}处理参数为 `{metadata['processing_parameters']}`。

## 图谱

{figure_embed}

原图文件：`{figure_rel}`

## 主要观察

{peak_text}这些 peak 来自自动处理结果，仍需要结合能量校准、背景扣除、拟合模型、元素窗口、样品制备、仪器设置和用户审核进行解释。

## XPS peak 参数

{peak_table}

## XPS component quantification screening

{component_summary}

{component_table}

## 可能结论与可信度

{interpretation_text}

## 谨慎解释

在当前数据范围内，自动 XPS peak 只能支持“谱图结构筛查”。不能仅凭本次自动检峰直接确认化学态、价态、元素组成、表面污染、充电校正正确性或拟合组分；正式 XPS 结论需要用户确认校准参考、背景模型、spin-orbit/峰形/约束、灵敏度因子和文献依据。{literature_note}任何科学解释进入项目记忆前都需要用户审核。

## 不确定性与限制

{warning_text}

## 输出文件

- processed CSV: `{outputs['processed_csv']}`
- peak table: `{outputs['peak_table']}`
- component table: `{outputs.get('component_table', '未生成')}`
- plot: `{outputs['figure']}`
- metadata: `{outputs['metadata']}`

## References

{reference_block['references_markdown']}

## 溯源

本报告草稿引用 XPS result `{metadata['xps_result_id']}`，对应 provenance 将在报告生成后写入。
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
            "records": [str(xps_metadata_path.relative_to(root))],
            "files": [value for value in [outputs["processed_csv"], outputs["peak_table"], outputs.get("component_table"), outputs["figure"]] if value],
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
        result_ids=[metadata["xps_result_id"]],
        figure_ids=figure_ids,
        sample_ids=related_samples,
        experiment_ids=related_experiments,
        reference_ids=reference_block["reference_ids"],
    )
    return report_path


def _electrochemistry_feature_summary(root: Path, feature_table_ref: str) -> str:
    features = pd.read_csv(root / feature_table_ref)
    if features.empty:
        return "当前自动检测未得到稳定 electrochemistry feature，需结合人工检查。"
    positions = []
    for _, feature in features.head(8).iterrows():
        unit = str(feature.get("axis_unit") or "unknown")
        positions.append(f"{feature['feature_id']}@{float(feature['axis_value']):.4g} {unit}")
    return "自动检测给出的主要 electrochemistry feature 包括：" + "、".join(positions) + "。"


def _electrochemistry_feature_table(root: Path, feature_table_ref: str) -> str:
    features = pd.read_csv(root / feature_table_ref)
    if features.empty:
        return "当前没有可展示的自动 electrochemistry feature 检测结果。"
    rows = [
        "| feature_id | type | axis | current (mA) | current density (mA cm^-2) | confidence | source |",
        "|---|---|---:|---:|---:|---|---|",
    ]
    for _, feature in features.head(12).iterrows():
        density = feature.get("current_density_mA_cm-2")
        density_text = f"{float(density):.4g}" if pd.notna(density) else "n/a"
        rows.append(
            "| {feature_id} | {feature_type} | {axis:.4g} {unit} | {current:.4g} | {density} | {confidence} | {source} |".format(
                feature_id=feature["feature_id"],
                feature_type=feature["feature_type"],
                axis=float(feature["axis_value"]),
                unit=feature.get("axis_unit") or "unknown",
                current=float(feature["current_mA"]),
                density=density_text,
                confidence=feature.get("assignment_confidence") or "low",
                source=feature.get("assignment_source") or "未记录",
            )
        )
    return "\n".join(rows)


def _electrochemistry_eis_feature_summary(root: Path, feature_table_ref: str) -> str:
    features = pd.read_csv(root / feature_table_ref)
    if features.empty:
        return "当前自动 EIS Nyquist screening 未得到可展示 feature，需结合人工检查。"
    positions = []
    for _, feature in features.head(6).iterrows():
        positions.append(f"{feature['feature_id']}@Zreal {float(feature['z_real_ohm']):.4g} ohm / -Zimag {float(feature['neg_z_imag_ohm']):.4g} ohm")
    return "自动 EIS Nyquist screening 记录的主要阻抗 feature 包括：" + "、".join(positions) + "。"


def _electrochemistry_eis_feature_table(root: Path, feature_table_ref: str) -> str:
    features = pd.read_csv(root / feature_table_ref)
    if features.empty:
        return "当前没有可展示的 EIS Nyquist screening feature。"
    rows = [
        "| feature_id | type | Z real (ohm) | -Z imag (ohm) | impedance magnitude (ohm) | screening span (ohm) | confidence | source |",
        "|---|---|---:|---:|---:|---:|---|---|",
    ]
    for _, feature in features.head(12).iterrows():
        span = feature.get("screening_resistance_ohm")
        span_text = f"{float(span):.4g}" if pd.notna(span) else "n/a"
        rows.append(
            "| {feature_id} | {feature_type} | {z_real:.4g} | {neg_imag:.4g} | {magnitude:.4g} | {span} | {confidence} | {source} |".format(
                feature_id=feature["feature_id"],
                feature_type=feature["feature_type"],
                z_real=float(feature["z_real_ohm"]),
                neg_imag=float(feature["neg_z_imag_ohm"]),
                magnitude=float(feature["impedance_magnitude_ohm"]),
                span=span_text,
                confidence=feature.get("assignment_confidence") or "low",
                source=feature.get("assignment_source") or "未记录",
            )
        )
    return "\n".join(rows)


def _electrochemistry_current_summary(metadata: dict) -> str:
    summary = ((metadata.get("peak_analysis") or {}).get("current_summary") or {})
    if not summary:
        return "当前 metadata 中没有可复用的 current summary。"
    retention = summary.get("retention_percent")
    retention_text = f"{float(retention):.2f}%" if retention is not None else "n/a"
    return (
        f"start current `{float(summary.get('start_current_mA', 0.0)):.4g} mA`；"
        f"end current `{float(summary.get('end_current_mA', 0.0)):.4g} mA`；"
        f"min/max current `{float(summary.get('min_current_mA', 0.0)):.4g}` / "
        f"`{float(summary.get('max_current_mA', 0.0)):.4g} mA`；"
        f"retention `{retention_text}`。"
    )


def _electrochemistry_eis_summary_text(metadata: dict) -> str:
    summary = ((metadata.get("peak_analysis") or {}).get("eis_summary") or {})
    if not summary:
        return "当前 metadata 中没有可复用的 EIS Nyquist summary。"
    return (
        f"high-frequency intercept screening `{float(summary.get('high_frequency_intercept_ohm', 0.0)):.4g} ohm`；"
        f"real-axis span screening `{float(summary.get('real_axis_span_ohm', 0.0)):.4g} ohm`；"
        f"maximum -Zimag `{float(summary.get('max_neg_z_imag_ohm', 0.0)):.4g} ohm` at Zreal "
        f"`{float(summary.get('apex_z_real_ohm', 0.0)):.4g} ohm`；confidence: `{summary.get('confidence', 'low')}`；"
        f"assignment_source: `{summary.get('assignment_source', 'ea.electrochemistry.eis_nyquist_screening:v0.2')}`。"
    )


def _electrochemistry_interpretation_text(metadata: dict, citation_text: str) -> str:
    peak_analysis = metadata.get("peak_analysis") or {}
    interpretations = peak_analysis.get("possible_interpretations") or []
    if not interpretations:
        return "- 当前 metadata 中没有可复用的 electrochemistry 自动解释结果；建议先复核电极、电解液、参比电极、扫描/计时协议和归一化方式。\n  - confidence: `insufficient`"
    lines: list[str] = []
    for item in interpretations:
        text = str(item.get("text", "No interpretation text recorded."))
        confidence = str(item.get("confidence", "insufficient"))
        evidence = ", ".join(str(value) for value in item.get("evidence", [])) or "未记录"
        cite = citation_text if citation_text else ""
        source = str(item.get("assignment_source", "") or "未记录")
        lines.append(f"- {text}{cite}\n  - confidence: `{confidence}`；evidence: `{evidence}`；assignment_source: `{source}`")
    if not citation_text:
        lines.append("- 上述 electrochemistry 自动解释尚未绑定外部文献、标准方法或项目参考实验；若用于正式性能/机制判断，应补充 reference_ids 并让用户审核。\n  - confidence: `insufficient`")
    return "\n".join(lines)


def generate_electrochemistry_report(
    root: Path,
    *,
    project_id: str,
    electrochemistry_metadata_path: Path,
    related_experiments: list[str] | None = None,
    related_samples: list[str] | None = None,
    reference_ids: list[str] | None = None,
    created_at: str | None = None,
) -> Path:
    metadata = read_yaml(electrochemistry_metadata_path)
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
        report_type="electrochemistry_analysis",
        related_experiments=related_experiments,
        related_samples=related_samples,
        related_results=[metadata["electrochemistry_result_id"]],
        figure_ids=figure_ids,
        include_next_step_suggestions=False,
        status="draft",
        created_at=created_at or EARecord.now_iso(),
        updated_at=created_at or EARecord.now_iso(),
    )
    outputs = metadata["outputs"]
    feature_table_ref = outputs.get("feature_table", outputs.get("peak_table"))
    is_eis = metadata.get("measurement_mode") == "eis"
    feature_text = _electrochemistry_eis_feature_summary(root, feature_table_ref) if is_eis else _electrochemistry_feature_summary(root, feature_table_ref)
    feature_table = _electrochemistry_eis_feature_table(root, feature_table_ref) if is_eis else _electrochemistry_feature_table(root, feature_table_ref)
    current_summary = _electrochemistry_eis_summary_text(metadata) if is_eis else _electrochemistry_current_summary(metadata)
    summary_heading = "EIS Nyquist screening 摘要" if is_eis else "电流摘要"
    caution_text = (
        "在当前数据范围内，自动 EIS Nyquist screening 只能支持“阻抗弧形状/截距筛查”。不能仅凭本次自动处理直接确认等效电路、Rct、Warburg 扩散、电容、电荷转移机制或器件性能；正式结论需要用户确认频率顺序、扰动幅值、等效电路模型、重复性和文献依据。"
        if is_eis
        else "在当前数据范围内，自动 electrochemistry feature 只能支持“电流响应摘要/筛查”。不能仅凭本次自动处理直接确认催化机制、过电位、Tafel slope、电容、稳定性、容量、倍率性能或器件性能；正式结论需要用户确认实验协议、归一化方式、参比校正、重复性和文献依据。"
    )
    warnings = metadata.get("warnings") or []
    warning_text = "；".join(
        warning.get("message", str(warning)) if isinstance(warning, dict) else str(warning)
        for warning in warnings
    ) or "未记录高风险 warning。"
    reference_block = build_report_reference_block(root, reference_ids)
    citation_text = reference_block["inline_citation"]
    literature_note = f"相关解释应与已登记文献、标准方法或项目参考实验对应位置共同阅读{citation_text}。" if citation_text else "相关解释尚未绑定外部文献、标准方法或项目参考实验引用。"
    interpretation_text = _electrochemistry_interpretation_text(metadata, citation_text)
    figure_rel = outputs["figure"]
    figure_embed = f"![Electrochemistry trace](../{figure_rel})"
    body = f"""# Electrochemistry 分析报告

## 报告 ID 信息

- report_id: `{report_id}`
- project_id: `{project_id}`
- result_ids: `{metadata['electrochemistry_result_id']}`
- figure_ids: `{', '.join(figure_ids) if figure_ids else '未生成 v0.2 figure_id'}`

## 数据来源

本报告基于 electrochemistry processing result `{metadata['electrochemistry_result_id']}` 生成，关联样品为 `{', '.join(related_samples) if related_samples else '未明确映射样品'}`。原始数据、处理结果和图谱路径均通过 provenance 保留。

## 数据列、实验上下文与处理参数

用户确认的 x 列为 `{metadata['x_column']}`，y 列为 `{metadata['y_column']}`，x 轴/阻抗单位记录为 `{metadata['x_unit']}`，current 单位记录为 `{metadata['current_unit']}`，measurement mode 为 `{metadata['measurement_mode']}`。电极面积记录为 `{metadata.get('electrode_area_cm2', '未记录')}` cm^2。用户确认的上下文摘要为：`{metadata.get('context_summary') or '未记录'}`。处理参数为 `{metadata['processing_parameters']}`。

## 图谱

{figure_embed}

原图文件：`{figure_rel}`

## 主要观察

{feature_text}这些 feature 来自自动处理结果，仍需要结合电极几何面积、电解液、参比电极、频率/扫描/计时协议、仪器设置和用户审核进行解释。

## {summary_heading}

{current_summary}

## Electrochemistry feature 参数

{feature_table}

## 可能结论与可信度

{interpretation_text}

## 谨慎解释

{caution_text}{literature_note}任何科学解释进入项目记忆前都需要用户审核。

## 不确定性与限制

{warning_text}

## 输出文件

- processed CSV: `{outputs['processed_csv']}`
- feature table: `{feature_table_ref}`
- plot: `{outputs['figure']}`
- metadata: `{outputs['metadata']}`

## References

{reference_block['references_markdown']}

## 溯源

本报告草稿引用 electrochemistry result `{metadata['electrochemistry_result_id']}`，对应 provenance 将在报告生成后写入。
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
            "records": [str(electrochemistry_metadata_path.relative_to(root))],
            "files": [outputs["processed_csv"], feature_table_ref, outputs["figure"]],
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
        result_ids=[metadata["electrochemistry_result_id"]],
        figure_ids=figure_ids,
        sample_ids=related_samples,
        experiment_ids=related_experiments,
        reference_ids=reference_block["reference_ids"],
    )
    return report_path


def _thermal_feature_summary(root: Path, feature_table_ref: str) -> str:
    features = pd.read_csv(root / feature_table_ref)
    if features.empty:
        return "当前自动检测未得到稳定 thermal event，需结合人工检查。"
    positions = []
    for _, event in features.head(8).iterrows():
        positions.append(f"{event['event_id']}@{float(event['temperature_C']):.1f} C")
    return "自动检测给出的主要 thermal event 包括：" + "、".join(positions) + "。"


def _thermal_feature_table(root: Path, feature_table_ref: str) -> str:
    features = pd.read_csv(root / feature_table_ref)
    if features.empty:
        return "当前没有可展示的自动 thermal event 检测结果。"
    rows = [
        "| event_id | type | temperature (C) | signal | mass (%) | derivative (%/C) | confidence | source |",
        "|---|---|---:|---:|---:|---:|---|---|",
    ]
    for _, event in features.head(12).iterrows():
        signal = event.get("signal_value")
        mass = event.get("mass_percent")
        derivative = event.get("mass_derivative_percent_per_C")
        rows.append(
            "| {event_id} | {event_type} | {temperature:.1f} | {signal} | {mass} | {derivative} | {confidence} | {source} |".format(
                event_id=event["event_id"],
                event_type=event["event_type"],
                temperature=float(event["temperature_C"]),
                signal=f"{float(signal):.4g}" if pd.notna(signal) else "n/a",
                mass=f"{float(mass):.4g}" if pd.notna(mass) else "n/a",
                derivative=f"{float(derivative):.4g}" if pd.notna(derivative) else "n/a",
                confidence=event.get("assignment_confidence") or "low",
                source=event.get("assignment_source") or "未记录",
            )
        )
    return "\n".join(rows)


def _thermal_summary_text(metadata: dict) -> str:
    analysis = metadata.get("peak_analysis") or {}
    temperature = analysis.get("temperature_summary") or {}
    signal = analysis.get("signal_summary") or {}
    mass = analysis.get("mass_summary") or {}
    parts = [
        "temperature range `{min_temp:.1f}` to `{max_temp:.1f} C`".format(
            min_temp=float(temperature.get("min_temperature_C", 0.0)),
            max_temp=float(temperature.get("max_temperature_C", 0.0)),
        ),
        "signal start/end `{start:.4g}` / `{end:.4g}` `{unit}`".format(
            start=float(signal.get("start_signal", 0.0)),
            end=float(signal.get("end_signal", 0.0)),
            unit=signal.get("signal_unit", "unknown"),
        ),
    ]
    if mass:
        parts.append(
            "mass loss `{loss:.3g}%` from `{start:.3g}%` to `{end:.3g}%`".format(
                loss=float(mass.get("total_mass_loss_percent", 0.0)),
                start=float(mass.get("start_mass_percent", 0.0)),
                end=float(mass.get("end_mass_percent", 0.0)),
            )
        )
    return "；".join(parts) + "。"


def _thermal_interpretation_text(metadata: dict, citation_text: str) -> str:
    peak_analysis = metadata.get("peak_analysis") or {}
    interpretations = peak_analysis.get("possible_interpretations") or []
    if not interpretations:
        return "- 当前 metadata 中没有可复用的 thermal 自动解释结果；建议先复核温度程序、气氛、基线、样品质量和重复性。\n  - confidence: `insufficient`"
    lines: list[str] = []
    for item in interpretations:
        text = str(item.get("text", "No interpretation text recorded."))
        confidence = str(item.get("confidence", "insufficient"))
        evidence = ", ".join(str(value) for value in item.get("evidence", [])) or "未记录"
        cite = citation_text if citation_text else ""
        source = str(item.get("assignment_source", "") or "未记录")
        lines.append(f"- {text}{cite}\n  - confidence: `{confidence}`；evidence: `{evidence}`；assignment_source: `{source}`")
    if not citation_text:
        lines.append("- 上述 thermal 自动解释尚未绑定外部文献、标准方法或项目参考实验；若用于正式热稳定性、相变或机理判断，应补充 reference_ids 并让用户审核。\n  - confidence: `insufficient`")
    return "\n".join(lines)


def generate_thermal_report(
    root: Path,
    *,
    project_id: str,
    thermal_metadata_path: Path,
    related_experiments: list[str] | None = None,
    related_samples: list[str] | None = None,
    reference_ids: list[str] | None = None,
    created_at: str | None = None,
) -> Path:
    metadata = read_yaml(thermal_metadata_path)
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
        report_type="thermal_analysis",
        related_experiments=related_experiments,
        related_samples=related_samples,
        related_results=[metadata["thermal_result_id"]],
        figure_ids=figure_ids,
        include_next_step_suggestions=False,
        status="draft",
        created_at=created_at or EARecord.now_iso(),
        updated_at=created_at or EARecord.now_iso(),
    )
    outputs = metadata["outputs"]
    feature_table_ref = outputs.get("feature_table", outputs.get("peak_table"))
    feature_text = _thermal_feature_summary(root, feature_table_ref)
    feature_table = _thermal_feature_table(root, feature_table_ref)
    summary_text = _thermal_summary_text(metadata)
    warnings = metadata.get("warnings") or []
    warning_text = "；".join(
        warning.get("message", str(warning)) if isinstance(warning, dict) else str(warning)
        for warning in warnings
    ) or "未记录高风险 warning。"
    reference_block = build_report_reference_block(root, reference_ids)
    citation_text = reference_block["inline_citation"]
    literature_note = f"相关解释应与已登记文献、标准方法或项目参考实验对应位置共同阅读{citation_text}。" if citation_text else "相关解释尚未绑定外部文献、标准方法或项目参考实验引用。"
    interpretation_text = _thermal_interpretation_text(metadata, citation_text)
    figure_rel = outputs["figure"]
    figure_embed = f"![Thermal analysis trace](../{figure_rel})"
    body = f"""# Thermal Analysis 分析报告

## 报告 ID 信息

- report_id: `{report_id}`
- project_id: `{project_id}`
- result_ids: `{metadata['thermal_result_id']}`
- figure_ids: `{', '.join(figure_ids) if figure_ids else '未生成 v0.2 figure_id'}`

## 数据来源

本报告基于 thermal analysis processing result `{metadata['thermal_result_id']}` 生成，关联样品为 `{', '.join(related_samples) if related_samples else '未明确映射样品'}`。原始数据、处理结果和图谱路径均通过 provenance 保留。

## 数据列、实验上下文与处理参数

用户确认的 temperature 列为 `{metadata['temperature_column']}`，signal 列为 `{metadata['signal_column']}`，temperature 单位记录为 `{metadata['temperature_unit']}`，signal 单位记录为 `{metadata['signal_unit']}`，measurement mode 为 `{metadata['measurement_mode']}`。用户确认的上下文摘要为：`{metadata.get('context_summary') or '未记录'}`。处理参数为 `{metadata['processing_parameters']}`。

## 图谱

{figure_embed}

原图文件：`{figure_rel}`

## 主要观察

{feature_text}这些 thermal event 来自自动处理结果，仍需要结合温度程序、气氛、样品质量、基线、坩埚/参比、重复性和用户审核进行解释。

## 数据摘要

{summary_text}

## Thermal event 参数

{feature_table}

## 可能结论与可信度

{interpretation_text}

## 谨慎解释

在当前数据范围内，自动 thermal event 只能支持“热响应摘要/筛查”。不能仅凭本次自动处理直接确认分解机理、玻璃化转变、熔融/结晶归属、动力学参数、组成比例或热稳定性排名；正式结论需要用户确认温度程序、气氛、基线模型、样品质量、重复性和文献依据。{literature_note}任何科学解释进入项目记忆前都需要用户审核。

## 不确定性与限制

{warning_text}

## 输出文件

- processed CSV: `{outputs['processed_csv']}`
- feature table: `{feature_table_ref}`
- plot: `{outputs['figure']}`
- metadata: `{outputs['metadata']}`

## References

{reference_block['references_markdown']}

## 溯源

本报告草稿引用 thermal analysis result `{metadata['thermal_result_id']}`，对应 provenance 将在报告生成后写入。
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
            "records": [str(thermal_metadata_path.relative_to(root))],
            "files": [outputs["processed_csv"], feature_table_ref, outputs["figure"]],
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
        result_ids=[metadata["thermal_result_id"]],
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
