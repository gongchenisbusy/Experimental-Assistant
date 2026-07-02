from __future__ import annotations

from pathlib import Path

import pandas as pd

from ea.figures import update_figure_report_ref
from ea.provenance import write_provenance_entry
from ea.references import build_report_reference_block, format_inline_citation
from ea.review import require_confirmed_review
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
    assignment_suggestion_paths: list[Path] | None = None,
    assignment_review_refs: list[str] | None = None,
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
    assignment_suggestion_records = _load_xrd_assignment_suggestion_records(
        root,
        assignment_suggestion_paths,
        assignment_review_refs,
        xrd_metadata_path=xrd_metadata_path,
        project_id=project_id,
    )
    registered_references = _registered_reference_ids(root)
    suggestion_reference_ids = [
        str(reference_id)
        for record in assignment_suggestion_records
        for reference_id in record.get("reference_ids", [])
        if str(reference_id) in registered_references
    ]
    reference_block = build_report_reference_block(root, _ordered_unique([*(reference_ids or []), *suggestion_reference_ids]))
    citation_text = reference_block["inline_citation"]
    literature_note = f"相关解释应与已登记文献或相数据库条目对应位置共同阅读{citation_text}。" if citation_text else "相关解释尚未绑定外部文献或相数据库引用。"
    interpretation_text = _xrd_interpretation_text(metadata, citation_text)
    assignment_suggestion_text = _xrd_assignment_suggestion_text(assignment_suggestion_records, reference_block)
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

## Reviewed source-backed XRD assignment suggestions

{assignment_suggestion_text}

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
            "records": [
                str(xrd_metadata_path.relative_to(root)),
                *[_relative_to_root(root, path) for path in assignment_suggestion_paths or []],
                *[f"reviews/{review_ref}.yml" for review_ref in assignment_review_refs or []],
            ],
            "files": [outputs["processed_csv"], outputs["peak_table"], outputs["figure"]],
        },
        outputs={"records": [str(report_path.relative_to(root))], "files": []},
        parameters={
            "include_next_step_suggestions": False,
            "language": "zh",
            "assignment_suggestion_refs": [_relative_to_root(root, path) for path in assignment_suggestion_paths or []],
            "assignment_review_refs": assignment_review_refs or [],
        },
        review_refs=assignment_review_refs or [],
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


def _has_ftir_context_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_has_ftir_context_value(item) for item in value.values())
    if isinstance(value, list | tuple):
        return any(_has_ftir_context_value(item) for item in value)
    return True


def _format_ftir_context_value(value: object) -> str:
    if isinstance(value, dict):
        parts = [f"{key}={_format_ftir_context_value(item)}" for key, item in value.items() if _has_ftir_context_value(item)]
        return "; ".join(parts) if parts else "未记录"
    if isinstance(value, list | tuple):
        parts = [_format_ftir_context_value(item) for item in value if _has_ftir_context_value(item)]
        return "; ".join(parts) if parts else "未记录"
    return str(value)


def _ftir_context_record_text(metadata: dict) -> str:
    context = (metadata.get("peak_analysis") or {}).get("context_record")
    if not context:
        return "当前没有启用或记录 FTIR context record。"
    status = context.get("status", "unknown")
    confidence = context.get("confidence", "insufficient")
    source = context.get("assignment_source", "ea.ftir.context_record:v0.2")
    record_ref = context.get("record_ref", "未生成")
    fields = context.get("reviewed_context_fields") or []
    field_text = "、".join(str(field) for field in fields) if fields else "未记录 reviewed context 字段"
    labels = {
        "instrument_accessory": "instrument/accessory",
        "atmosphere": "atmosphere",
        "sample_preparation": "sample preparation",
        "background": "background",
        "reference": "reference",
        "correction_notes": "correction notes",
    }
    rows = []
    for key, label in labels.items():
        value = context.get(key)
        if _has_ftir_context_value(value):
            rows.append(f"- {label}: `{_format_ftir_context_value(value)}`")
    detail_text = "\n".join(rows) if rows else "- FTIR context details: `未记录`"
    return (
        f"FTIR context record 状态为 `{status}`；reviewed fields: `{field_text}`；record: `{record_ref}`；"
        f"confidence: `{confidence}`；assignment_source: `{source}`。\n\n"
        f"{detail_text}\n\n"
        "该记录只保存已审核的仪器/附件、气氛、样品制备、背景或参比语境；本阶段不执行自动背景/参比数值校正，也不把这些 metadata 单独作为化学组成或功能团定论。"
    )


def _ordered_unique(values: list[str] | None) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values or []:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            ordered.append(text)
    return ordered


def _registered_reference_ids(root: Path) -> set[str]:
    index_path = root / "literature" / "references" / "index.yml"
    if not index_path.exists():
        return set()
    index = read_yaml(index_path)
    references = index.get("references")
    if not isinstance(references, dict):
        return set()
    return {str(reference_id) for reference_id in references}


def _relative_to_root(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _load_ftir_assignment_suggestion_records(root: Path, refs: list[Path] | None) -> list[dict]:
    records = []
    for ref in refs or []:
        path = ref if ref.is_absolute() else root / ref
        record = read_yaml(path)
        record["record_ref"] = _relative_to_root(root, path)
        records.append(record)
    return records


def _load_xps_parameter_suggestion_records(root: Path, refs: list[Path] | None) -> list[dict]:
    records = []
    for ref in refs or []:
        path = ref if ref.is_absolute() else root / ref
        record = read_yaml(path)
        record["record_ref"] = _relative_to_root(root, path)
        records.append(record)
    return records


def _normalize_report_target_ref(root: Path, value: object) -> str:
    target = str(value or "").strip()
    if not target:
        return ""
    target_path = Path(target)
    if target_path.is_absolute():
        return _relative_to_root(root, target_path)
    return _relative_to_root(root, root / target_path)


def _load_uv_vis_interpretation_suggestion_records(
    root: Path,
    refs: list[Path] | None,
    review_refs: list[str] | None,
    *,
    uv_vis_metadata_path: Path,
    project_id: str,
) -> list[dict]:
    refs = refs or []
    review_refs = review_refs or []
    if not refs:
        return []
    if len(refs) != len(review_refs):
        raise ValueError("Each --interpretation-suggestion requires one matching --interpretation-review-ref.")

    metadata_ref = _relative_to_root(root, uv_vis_metadata_path)
    records: list[dict] = []
    for ref, review_ref in zip(refs, review_refs, strict=True):
        path = ref if ref.is_absolute() else root / ref
        record = read_yaml(path)
        if record.get("source") != "ea.uv_vis.interpretation_suggestions:v0.2":
            raise ValueError(f"Not a UV-Vis interpretation suggestion record: {ref}")
        record_ref = _relative_to_root(root, path)
        record_project_id = str(record.get("project_id") or "")
        if record_project_id and project_id and record_project_id != project_id:
            raise ValueError(f"UV-Vis suggestion project_id {record_project_id} does not match report project_id {project_id}.")
        suggestion_metadata_ref = str(record.get("uv_vis_metadata_ref") or "")
        if suggestion_metadata_ref and suggestion_metadata_ref != metadata_ref:
            raise ValueError(f"UV-Vis suggestion {record_ref} targets {suggestion_metadata_ref}, not report metadata {metadata_ref}.")

        review = require_confirmed_review(root, review_ref)
        review_target_type = str(review.get("target_type") or "")
        review_target_ref = _normalize_report_target_ref(root, review.get("target_ref"))
        if review_target_type != "uv_vis_interpretation_suggestions" or review_target_ref != record_ref:
            raise ValueError(
                f"ReviewRecord {review_ref} targets {review_target_type}:{review.get('target_ref')}, "
                f"not UV-Vis interpretation suggestion {record_ref}."
            )
        record["record_ref"] = record_ref
        record["review_ref"] = review_ref
        record["reviewed_content"] = review.get("reviewed_content") or review.get("user_original_text")
        records.append(record)
    return records


def _load_xrd_assignment_suggestion_records(
    root: Path,
    refs: list[Path] | None,
    review_refs: list[str] | None,
    *,
    xrd_metadata_path: Path,
    project_id: str,
) -> list[dict]:
    refs = refs or []
    review_refs = review_refs or []
    if not refs:
        return []
    if len(refs) != len(review_refs):
        raise ValueError("Each --assignment-suggestion requires one matching --assignment-review-ref.")

    metadata_ref = _relative_to_root(root, xrd_metadata_path)
    records: list[dict] = []
    for ref, review_ref in zip(refs, review_refs, strict=True):
        path = ref if ref.is_absolute() else root / ref
        record = read_yaml(path)
        if record.get("source") != "ea.xrd.assignment_suggestions:v0.2":
            raise ValueError(f"Not an XRD assignment suggestion record: {ref}")
        record_ref = _relative_to_root(root, path)
        record_project_id = str(record.get("project_id") or "")
        if record_project_id and project_id and record_project_id != project_id:
            raise ValueError(f"XRD suggestion project_id {record_project_id} does not match report project_id {project_id}.")
        suggestion_metadata_ref = str(record.get("xrd_metadata_ref") or "")
        if suggestion_metadata_ref and suggestion_metadata_ref != metadata_ref:
            raise ValueError(f"XRD suggestion {record_ref} targets {suggestion_metadata_ref}, not report metadata {metadata_ref}.")

        review = require_confirmed_review(root, review_ref)
        review_target_type = str(review.get("target_type") or "")
        review_target_ref = _normalize_report_target_ref(root, review.get("target_ref"))
        if review_target_type != "xrd_assignment_suggestions" or review_target_ref != record_ref:
            raise ValueError(
                f"ReviewRecord {review_ref} targets {review_target_type}:{review.get('target_ref')}, "
                f"not XRD assignment suggestion {record_ref}."
            )
        record["record_ref"] = record_ref
        record["review_ref"] = review_ref
        record["reviewed_content"] = review.get("reviewed_content") or review.get("user_original_text")
        records.append(record)
    return records


def _reference_citation(reference_ids: list[str], reference_block: dict) -> str:
    number_by_id = {
        str(item["reference_id"]): int(item["number"])
        for item in reference_block.get("numbered_references", [])
    }
    numbers = [number_by_id[reference_id] for reference_id in reference_ids if reference_id in number_by_id]
    return format_inline_citation(numbers) if numbers else ""


def _format_report_list(values: object, *, limit: int = 3) -> str:
    if values is None:
        return "未记录"
    if isinstance(values, str):
        return values if values.strip() else "未记录"
    if isinstance(values, list | tuple):
        items = [str(item) for item in values if str(item).strip()]
        if not items:
            return "未记录"
        shown = items[:limit]
        suffix = f"；另有 {len(items) - limit} 项" if len(items) > limit else ""
        return "；".join(shown) + suffix
    return str(values)


def _xrd_assignment_values_text(candidate: dict) -> str:
    fields = [
        ("material_id", candidate.get("material_id")),
        ("feature", candidate.get("feature")),
        ("assignment_type", candidate.get("assignment_type")),
        ("two_theta_window_deg", candidate.get("two_theta_window_deg")),
        ("d_spacing_window_angstrom", candidate.get("d_spacing_window_angstrom")),
    ]
    parts = [f"{key}={_format_report_list(value)}" for key, value in fields if value not in (None, "", [], {})]
    return "；".join(parts) if parts else "未记录可展示的 XRD assignment values"


def _xrd_assignment_report_use_status(candidate: dict, unresolved_reference_ids: list[str]) -> str:
    status = str(candidate.get("status") or "unknown")
    if status == "ready_for_user_review" and not unresolved_reference_ids and not candidate.get("missing_fields"):
        return "reviewed_assignment_context"
    if unresolved_reference_ids:
        return "warning_unresolved_references"
    if status == "no_feature_match":
        return "context_no_feature_match"
    if status.startswith("invalid") or candidate.get("missing_fields"):
        return "excluded_invalid_or_incomplete"
    return "context_not_used_as_evidence"


def _xrd_assignment_suggestion_text(records: list[dict], reference_block: dict) -> str:
    if not records:
        return (
            "当前报告未附加 reviewed XRD assignment suggestion record。若需要讨论 source-backed XRD 物相/晶面/"
            "衍射特征候选，请先运行 `ea xrd suggest-assignments`、`ea xrd prepare-review` 和 `ea review add`，"
            "再在报告生成时传入对应 suggestion 与 ReviewRecord。"
        )
    lines: list[str] = []
    status_rank = {
        "ready_for_user_review": 0,
        "needs_reference_registration": 1,
        "no_feature_match": 2,
        "invalid_missing_required_metadata": 3,
    }
    reference_ids_in_report = {
        str(item["reference_id"])
        for item in reference_block.get("numbered_references", [])
    }
    for record in records:
        record_ref = str(record.get("record_ref") or record.get("table_ref") or "未记录")
        record_status = str(record.get("status") or "unknown")
        suggestion_id = str(record.get("suggestion_id") or "unknown")
        review_ref = str(record.get("review_ref") or "未记录")
        reviewed_content = str(record.get("reviewed_content") or "未记录 reviewed_content")
        lines.append(
            f"- suggestion_record: `{record_ref}`；suggestion_id: `{suggestion_id}`；review_ref: `{review_ref}`；"
            f"status: `{record_status}`；candidate_count: `{record.get('candidate_count', 0)}`；auto_applied: `false`。"
        )
        lines.append(f"  - review summary: {reviewed_content}")
        candidates = record.get("candidates") or []
        if not candidates:
            lines.append("  - 该 suggestion record 未包含 candidate。")
            continue
        sorted_candidates = sorted(
            candidates,
            key=lambda item: (
                status_rank.get(str(item.get("status") or ""), 9),
                str(item.get("candidate_id") or ""),
            ),
        )
        for candidate in sorted_candidates[:8]:
            reference_ids = [str(item) for item in candidate.get("reference_ids", []) if str(item).strip()]
            unresolved_ids = [
                str(item)
                for item in [
                    *(candidate.get("unresolved_reference_ids") or []),
                    *[ref for ref in reference_ids if ref not in reference_ids_in_report],
                ]
                if str(item).strip()
            ]
            unresolved_ids = _ordered_unique(unresolved_ids)
            citation = _reference_citation(reference_ids, reference_block)
            status = str(candidate.get("status") or "unknown")
            report_use = _xrd_assignment_report_use_status(candidate, unresolved_ids)
            matched_peaks = _format_report_list(candidate.get("matched_peak_ids"))
            matched_two_theta = _format_report_list(candidate.get("matched_two_theta_deg"))
            matched_d_spacing = _format_report_list(candidate.get("matched_d_spacing_angstrom"))
            applicability = _format_report_list(candidate.get("applicability_notes"))
            caveats = _format_report_list(candidate.get("caveats"))
            missing_fields = _format_report_list(candidate.get("missing_fields"))
            source_summary = str(candidate.get("source_summary") or "未记录")
            label = str(candidate.get("label") or "未记录 label")
            lines.append(
                "  - `{candidate_id}`: {label}{citation}\n"
                "    - report_use: `{report_use}`；review_state: `{status}`；confidence: `{confidence}`\n"
                "    - values: {values}\n"
                "    - matched_peak_ids: `{matched_peaks}`；matched_two_theta_deg: `{matched_two_theta}`；matched_d_spacing_angstrom: `{matched_d_spacing}`\n"
                "    - source_summary: {source_summary}\n"
                "    - applicability: {applicability}\n"
                "    - caveats: {caveats}\n"
                "    - missing_fields: `{missing_fields}`；unresolved_reference_ids: `{unresolved}`".format(
                    candidate_id=str(candidate.get("candidate_id") or "unknown"),
                    label=label,
                    citation=citation,
                    report_use=report_use,
                    status=status,
                    confidence=str(candidate.get("confidence") or "insufficient"),
                    values=_xrd_assignment_values_text(candidate),
                    matched_peaks=matched_peaks,
                    matched_two_theta=matched_two_theta,
                    matched_d_spacing=matched_d_spacing,
                    source_summary=source_summary,
                    applicability=applicability,
                    caveats=caveats,
                    missing_fields=missing_fields,
                    unresolved=", ".join(unresolved_ids) if unresolved_ids else "无",
                )
            )
        if len(sorted_candidates) > 8:
            lines.append(f"  - 另有 `{len(sorted_candidates) - 8}` 个候选未在报告中展开，请查看原 suggestion record。")
    lines.append(
        "- 上述 XRD assignment suggestions 是 reviewed source-backed advisory records；它们可以帮助组织物相、晶面或衍射特征讨论，"
        "但不会自动应用 assignment，不能单独证明相组成、材料身份、结晶度、择优取向、应变、晶格参数、仪器校准或样品质量，也不会写入 confirmed memory。"
    )
    return "\n".join(lines)


def _uv_vis_candidate_values_text(candidate: dict) -> str:
    fields = [
        ("reported_energy_eV", candidate.get("reported_energy_eV")),
        ("energy_window_eV", candidate.get("energy_window_eV")),
        ("wavelength_window_nm", candidate.get("wavelength_window_nm")),
        ("transition_model", candidate.get("transition_model")),
        ("transition_assumption", candidate.get("transition_assumption")),
        ("tauc_transform", candidate.get("tauc_transform")),
        ("expected_feature", candidate.get("expected_feature")),
        ("correction_context_type", candidate.get("correction_context_type")),
        ("correction_method", candidate.get("correction_method")),
    ]
    parts = [f"{key}={_format_report_list(value)}" for key, value in fields if value not in (None, "", [], {})]
    return "；".join(parts) if parts else "未记录可展示的 UV-Vis interpretation values"


def _uv_vis_report_use_status(candidate: dict, unresolved_reference_ids: list[str]) -> str:
    status = str(candidate.get("status") or "unknown")
    if status == "ready_for_user_review" and not unresolved_reference_ids and not candidate.get("missing_fields"):
        return "reviewed_interpretation_context"
    if unresolved_reference_ids:
        return "warning_unresolved_references"
    if status == "no_evidence_match":
        return "context_no_evidence_match"
    if status.startswith("invalid") or candidate.get("missing_fields"):
        return "excluded_invalid_or_incomplete"
    return "context_not_used_as_evidence"


def _uv_vis_interpretation_suggestion_text(records: list[dict], reference_block: dict) -> str:
    if not records:
        return (
            "当前报告未附加 reviewed UV-Vis interpretation suggestion record。若需要讨论 source-backed band gap、"
            "transition model、feature assignment 或 correction context 候选，请先运行 `ea uv-vis suggest-interpretations`、"
            "`ea uv-vis prepare-review` 和 `ea review add`，再在报告生成时传入对应 suggestion 与 ReviewRecord。"
        )
    lines: list[str] = []
    status_rank = {
        "ready_for_user_review": 0,
        "needs_reference_registration": 1,
        "no_evidence_match": 2,
        "invalid_missing_required_metadata": 3,
    }
    reference_ids_in_report = {
        str(item["reference_id"])
        for item in reference_block.get("numbered_references", [])
    }
    for record in records:
        record_ref = str(record.get("record_ref") or record.get("table_ref") or "未记录")
        record_status = str(record.get("status") or "unknown")
        suggestion_id = str(record.get("suggestion_id") or "unknown")
        review_ref = str(record.get("review_ref") or "未记录")
        reviewed_content = str(record.get("reviewed_content") or "未记录 reviewed_content")
        lines.append(
            f"- suggestion_record: `{record_ref}`；suggestion_id: `{suggestion_id}`；review_ref: `{review_ref}`；"
            f"status: `{record_status}`；candidate_count: `{record.get('candidate_count', 0)}`；auto_applied: `false`。"
        )
        lines.append(f"  - review summary: {reviewed_content}")
        candidates = record.get("candidates") or []
        if not candidates:
            lines.append("  - 该 suggestion record 未包含 candidate。")
            continue
        sorted_candidates = sorted(
            candidates,
            key=lambda item: (
                status_rank.get(str(item.get("status") or ""), 9),
                str(item.get("candidate_id") or ""),
            ),
        )
        for candidate in sorted_candidates[:8]:
            reference_ids = [str(item) for item in candidate.get("reference_ids", []) if str(item).strip()]
            unresolved_ids = [
                str(item)
                for item in [
                    *(candidate.get("unresolved_reference_ids") or []),
                    *[ref for ref in reference_ids if ref not in reference_ids_in_report],
                ]
                if str(item).strip()
            ]
            unresolved_ids = _ordered_unique(unresolved_ids)
            citation = _reference_citation(reference_ids, reference_block)
            status = str(candidate.get("status") or "unknown")
            report_use = _uv_vis_report_use_status(candidate, unresolved_ids)
            matched_features = _format_report_list(candidate.get("matched_feature_ids"))
            matched_energies = _format_report_list(candidate.get("matched_energies_eV"))
            matched_wavelengths = _format_report_list(candidate.get("matched_wavelengths_nm"))
            evidence_refs = _format_report_list(candidate.get("evidence_refs"))
            applicability = _format_report_list(candidate.get("applicability_notes"))
            caveats = _format_report_list(candidate.get("caveats"))
            source_summary = str(candidate.get("source_summary") or "未记录")
            lines.append(
                "  - `{candidate_id}`: {candidate_type} / {optical_target}{citation}\n"
                "    - report_use: `{report_use}`；review_state: `{status}`；confidence: `{confidence}`；evidence_status: `{evidence_status}`\n"
                "    - values: {values}\n"
                "    - matched_features: `{matched_features}`；matched_energies_eV: `{matched_energies}`；matched_wavelengths_nm: `{matched_wavelengths}`\n"
                "    - evidence_refs: `{evidence_refs}`\n"
                "    - source_summary: {source_summary}\n"
                "    - applicability: {applicability}\n"
                "    - caveats: {caveats}\n"
                "    - unresolved_reference_ids: `{unresolved}`".format(
                    candidate_id=str(candidate.get("candidate_id") or "unknown"),
                    candidate_type=str(candidate.get("candidate_type") or "unknown"),
                    optical_target=str(candidate.get("optical_target") or "未记录 optical_target"),
                    citation=citation,
                    report_use=report_use,
                    status=status,
                    confidence=str(candidate.get("confidence") or "insufficient"),
                    evidence_status=str(candidate.get("evidence_status") or "unknown"),
                    values=_uv_vis_candidate_values_text(candidate),
                    matched_features=matched_features,
                    matched_energies=matched_energies,
                    matched_wavelengths=matched_wavelengths,
                    evidence_refs=evidence_refs,
                    source_summary=source_summary,
                    applicability=applicability,
                    caveats=caveats,
                    unresolved=", ".join(unresolved_ids) if unresolved_ids else "无",
                )
            )
        if len(sorted_candidates) > 8:
            lines.append(f"  - 另有 `{len(sorted_candidates) - 8}` 个候选未在报告中展开，请查看原 suggestion record。")
    lines.append(
        "- 上述 UV-Vis interpretation suggestions 是 reviewed source-backed advisory records；它们可以帮助组织 band gap、transition model、feature assignment 或 correction context 讨论，但不会自动应用 Tauc/Kubelka-Munk/derivative/correction 模型，不能单独证明带隙、跃迁机制、缺陷态、样品厚度效应或光学机制，也不会写入 confirmed memory。"
    )
    return "\n".join(lines)


def _ftir_assignment_suggestion_text(records: list[dict], reference_block: dict) -> str:
    if not records:
        return (
            "当前报告未附加 FTIR assignment suggestion record。若需要讨论 source-backed 功能团候选，"
            "请先运行 `ea ftir suggest-assignments`，再在报告生成时传入对应记录。"
        )
    lines: list[str] = []
    status_rank = {
        "ready_for_user_review": 0,
        "needs_reference_registration": 1,
        "no_feature_match": 2,
        "invalid_missing_required_metadata": 3,
    }
    for record in records:
        record_ref = str(record.get("record_ref") or record.get("table_ref") or "未记录")
        record_status = str(record.get("status") or "unknown")
        lines.append(
            f"- suggestion_record: `{record_ref}`；status: `{record_status}`；"
            f"candidate_count: `{record.get('candidate_count', 0)}`；auto_applied: `false`。"
        )
        candidates = record.get("candidates") or []
        if not candidates:
            lines.append("  - 该 suggestion record 未包含 candidate。")
            continue
        sorted_candidates = sorted(
            candidates,
            key=lambda item: (
                status_rank.get(str(item.get("status") or ""), 9),
                str(item.get("candidate_id") or ""),
            ),
        )
        for candidate in sorted_candidates[:8]:
            reference_ids = [str(item) for item in candidate.get("reference_ids", [])]
            unresolved_ids = [str(item) for item in candidate.get("unresolved_reference_ids", [])]
            citation = _reference_citation(reference_ids, reference_block)
            matched_bands = _format_report_list(candidate.get("matched_band_ids"))
            matched_wavenumbers = _format_report_list(candidate.get("matched_wavenumbers_cm-1"))
            caveats = _format_report_list(candidate.get("caveats"))
            applicability = _format_report_list(candidate.get("applicability_notes"))
            source_summary = str(candidate.get("source_summary") or "未记录")
            lines.append(
                "  - `{candidate_id}`: {assignment}{citation}\n"
                "    - status: `{status}`；confidence: `{confidence}`；matched bands: `{matched_bands}`；"
                "matched wavenumbers cm^-1: `{matched_wavenumbers}`\n"
                "    - source_summary: {source_summary}\n"
                "    - applicability: {applicability}\n"
                "    - caveats: {caveats}\n"
                "    - unresolved_reference_ids: `{unresolved}`".format(
                    candidate_id=str(candidate.get("candidate_id") or "unknown"),
                    assignment=str(candidate.get("assignment_label") or "未记录 assignment_label"),
                    citation=citation,
                    status=str(candidate.get("status") or "unknown"),
                    confidence=str(candidate.get("confidence") or "insufficient"),
                    matched_bands=matched_bands,
                    matched_wavenumbers=matched_wavenumbers,
                    source_summary=source_summary,
                    applicability=applicability,
                    caveats=caveats,
                    unresolved=", ".join(unresolved_ids) if unresolved_ids else "无",
                )
            )
        if len(sorted_candidates) > 8:
            lines.append(f"  - 另有 `{len(sorted_candidates) - 8}` 个候选未在报告中展开，请查看原 suggestion record。")
    lines.append(
        "- 上述 FTIR assignment suggestions 是 source-backed advisory records；它们可以帮助组织讨论，但不能单独证明化学组成、功能团归属、反应路径或写入 confirmed memory。"
    )
    return "\n".join(lines)


def _xps_parameter_values_text(candidate: dict) -> str:
    suggestion_type = str(candidate.get("suggestion_type") or "unknown")
    if suggestion_type == "spin_orbit_constraint":
        values = {
            "constraint_id": candidate.get("constraint_id"),
            "center_delta_eV": candidate.get("center_delta_eV"),
            "area_ratio": candidate.get("area_ratio"),
            "fwhm_ratio": candidate.get("fwhm_ratio"),
        }
    elif suggestion_type == "tougaard_parameter":
        values = {
            "tougaard_B": candidate.get("tougaard_B"),
            "tougaard_C_eV2": candidate.get("tougaard_C_eV2"),
            "integration_direction": candidate.get("integration_direction"),
        }
    elif suggestion_type == "binding_energy_candidate":
        values = {
            "chemical_state_label": candidate.get("chemical_state_label"),
            "expected_binding_energy_eV": candidate.get("expected_binding_energy_eV"),
            "binding_energy_window_eV": candidate.get("binding_energy_window_eV"),
            "calibration_reference": candidate.get("calibration_reference"),
            "charge_reference_assumption": candidate.get("charge_reference_assumption"),
            "calibration_group_id": candidate.get("calibration_group_id"),
            "overlap_notes": _format_report_list(candidate.get("overlap_notes")),
        }
    else:
        values = {"suggestion_type": suggestion_type}
    return "；".join(f"{key}={value}" for key, value in values.items() if value not in [None, "", []]) or "未记录"


def _xps_parameter_suggestion_text(records: list[dict], reference_block: dict) -> str:
    if not records:
        return (
            "当前报告未附加 XPS parameter suggestion record。若需要讨论 source-backed spin-orbit、"
            "Tougaard/background、component/bounds/peak-shape 或 binding-energy/chemical-state 候选，请先运行 `ea xps suggest-parameters`，"
            "再在报告生成时传入对应记录。"
        )
    lines: list[str] = []
    status_rank = {
        "ready_for_user_review": 0,
        "needs_reference_registration": 1,
        "needs_source_metadata": 2,
        "invalid_missing_required_metadata": 3,
    }
    for record in records:
        record_ref = str(record.get("record_ref") or record.get("table_ref") or "未记录")
        record_status = str(record.get("status") or "unknown")
        suggestion_id = str(record.get("suggestion_id") or "unknown")
        lines.append(
            f"- suggestion_record: `{record_ref}`；suggestion_id: `{suggestion_id}`；"
            f"status: `{record_status}`；candidate_count: `{record.get('candidate_count', 0)}`；auto_applied: `false`。"
        )
        candidates = record.get("candidates") or []
        if not candidates:
            lines.append("  - 该 suggestion record 未包含 candidate。")
            continue
        sorted_candidates = sorted(
            candidates,
            key=lambda item: (
                status_rank.get(str(item.get("status") or ""), 9),
                str(item.get("candidate_id") or ""),
            ),
        )
        for candidate in sorted_candidates[:8]:
            reference_ids = [str(item) for item in candidate.get("reference_ids", [])]
            unresolved_ids = [str(item) for item in candidate.get("unresolved_reference_ids", [])]
            citation = _reference_citation(reference_ids, reference_block)
            applicability = _format_report_list(candidate.get("applicability_notes"))
            caveats = _format_report_list(candidate.get("caveats"))
            source_summary = str(candidate.get("source_summary") or "未记录")
            lines.append(
                "  - `{candidate_id}`: {suggestion_type}{citation}\n"
                "    - target_parameter_path: `{target}`；review_state: `{status}`；confidence: `{confidence}`；"
                "parameter_origin: `{origin}`\n"
                "    - values: {values}\n"
                "    - source_summary: {source_summary}\n"
                "    - applicability: {applicability}\n"
                "    - caveats: {caveats}\n"
                "    - unresolved_reference_ids: `{unresolved}`".format(
                    candidate_id=str(candidate.get("candidate_id") or "unknown"),
                    suggestion_type=str(candidate.get("suggestion_type") or "unknown"),
                    citation=citation,
                    target=str(candidate.get("target_parameter_path") or "未记录"),
                    status=str(candidate.get("status") or "unknown"),
                    confidence=str(candidate.get("confidence") or "insufficient"),
                    origin=str(candidate.get("parameter_origin") or "unknown"),
                    values=_xps_parameter_values_text(candidate),
                    source_summary=source_summary,
                    applicability=applicability,
                    caveats=caveats,
                    unresolved=", ".join(unresolved_ids) if unresolved_ids else "无",
                )
            )
        if len(sorted_candidates) > 8:
            lines.append(f"  - 另有 `{len(sorted_candidates) - 8}` 个候选未在报告中展开，请查看原 suggestion record。")
    lines.append(
        "- 上述 XPS parameter suggestions 是 source-backed advisory records；它们可以帮助组织 spin-orbit、Tougaard/background、component/bounds/peak-shape 或 binding-energy/chemical-state 候选讨论，但不会自动写入 processing parameters、不会静默校准谱图或应用荷电校正，不能单独证明化学态、组成或正式定量。"
    )
    return "\n".join(lines)


def generate_ftir_report(
    root: Path,
    *,
    project_id: str,
    ftir_metadata_path: Path,
    related_experiments: list[str] | None = None,
    related_samples: list[str] | None = None,
    reference_ids: list[str] | None = None,
    assignment_suggestion_paths: list[Path] | None = None,
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
    context_text = _ftir_context_record_text(metadata)
    warnings = metadata.get("warnings") or []
    warning_text = "；".join(
        warning.get("message", str(warning)) if isinstance(warning, dict) else str(warning)
        for warning in warnings
    ) or "未记录高风险 warning。"
    assignment_suggestion_records = _load_ftir_assignment_suggestion_records(root, assignment_suggestion_paths)
    registered_references = _registered_reference_ids(root)
    suggestion_reference_ids = [
        str(reference_id)
        for record in assignment_suggestion_records
        for reference_id in record.get("reference_ids", [])
        if str(reference_id) in registered_references
    ]
    reference_block = build_report_reference_block(root, _ordered_unique([*(reference_ids or []), *suggestion_reference_ids]))
    citation_text = reference_block["inline_citation"]
    literature_note = f"相关解释应与已登记文献或参考谱库对应位置共同阅读{citation_text}。" if citation_text else "相关解释尚未绑定外部文献或参考谱库引用。"
    interpretation_text = _ftir_interpretation_text(metadata, citation_text)
    assignment_suggestion_text = _ftir_assignment_suggestion_text(assignment_suggestion_records, reference_block)
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

## FTIR context record

{context_text}

## 图谱

{figure_embed}

原图文件：`{figure_rel}`

## 主要观察

{band_text}这些 band 来自自动处理结果，仍需要结合样品制备、背景/空气扣除、ATR 或透射模式、其他表征结果和用户审核进行解释。

## FTIR band 参数

{band_table}

## 可能结论与可信度

{interpretation_text}

## Source-backed FTIR assignment suggestions

{assignment_suggestion_text}

## 谨慎解释

在当前数据范围内，自动 FTIR band family 只能支持“可能功能团或谱区提示”，不能仅凭本次 FTIR 数据直接确认化学组成、键合机制、表面吸附来源或反应路径。{literature_note}任何科学解释进入项目记忆前都需要用户审核。

## 不确定性与限制

{warning_text}

## 输出文件

- processed CSV: `{outputs['processed_csv']}`
- band table: `{outputs['peak_table']}`
{f"- context record: `{outputs['context_record']}`" if outputs.get('context_record') else "- context record: `未生成`"}
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
            "records": [str(ftir_metadata_path.relative_to(root)), *[_relative_to_root(root, path) for path in assignment_suggestion_paths or []]],
            "files": [value for value in [outputs["processed_csv"], outputs["peak_table"], outputs.get("context_record"), outputs["figure"]] if value],
        },
        outputs={"records": [str(report_path.relative_to(root))], "files": []},
        parameters={
            "include_next_step_suggestions": False,
            "language": "zh",
            "assignment_suggestion_refs": [_relative_to_root(root, path) for path in assignment_suggestion_paths or []],
        },
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


def _uv_vis_derivative_text(metadata: dict) -> str:
    derivative = (metadata.get("peak_analysis") or {}).get("derivative_analysis")
    if not derivative:
        return "当前没有启用或记录 UV-Vis derivative screening。"
    status = derivative.get("status", "unknown")
    axis = derivative.get("axis", "unknown")
    axis_unit = derivative.get("axis_unit", "unknown")
    confidence = derivative.get("confidence", "insufficient")
    source = derivative.get("assignment_source", "ea.uv_vis.derivative_screening:v0.2")
    strongest = derivative.get("max_abs_slope") or {}
    axis_value = strongest.get("axis_value")
    wavelength = strongest.get("wavelength_nm")
    energy = strongest.get("energy_eV")
    first_derivative = strongest.get("first_derivative")
    axis_text = f"{float(axis_value):.4g} {axis_unit}" if axis_value is not None else "n/a"
    wavelength_text = f"{float(wavelength):.1f} nm" if wavelength is not None else "n/a"
    energy_text = f"{float(energy):.3f} eV" if energy is not None else "n/a"
    derivative_text = f"{float(first_derivative):.4g}" if first_derivative is not None else "n/a"
    return (
        f"Derivative screening 状态为 `{status}`；axis: `{axis}` (`{axis_unit}`)；"
        f"最大一阶导数绝对值附近坐标为 `{axis_text}`，对应 `{wavelength_text}` / `{energy_text}`，"
        f"first_derivative: `{derivative_text}`；confidence: `{confidence}`；assignment_source: `{source}`。"
        "该记录只用于提示谱肩、边缘或拐点候选区域，不等同于最终 optical transition 或 band gap 结论。"
    )


def _has_uv_vis_context_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_has_uv_vis_context_value(item) for item in value.values())
    if isinstance(value, list | tuple):
        return any(_has_uv_vis_context_value(item) for item in value)
    return True


def _format_uv_vis_context_value(value: object) -> str:
    if isinstance(value, dict):
        parts = [f"{key}={_format_uv_vis_context_value(item)}" for key, item in value.items() if _has_uv_vis_context_value(item)]
        return "; ".join(parts) if parts else "未记录"
    if isinstance(value, list | tuple):
        parts = [_format_uv_vis_context_value(item) for item in value if _has_uv_vis_context_value(item)]
        return "; ".join(parts) if parts else "未记录"
    return str(value)


def _uv_vis_correction_context_text(metadata: dict) -> str:
    context = (metadata.get("peak_analysis") or {}).get("correction_context")
    if not context:
        return "当前没有启用或记录 UV-Vis correction context。"
    status = context.get("status", "unknown")
    confidence = context.get("confidence", "insufficient")
    source = context.get("assignment_source", "ea.uv_vis.correction_context:v0.2")
    record_ref = context.get("record_ref", "未生成")
    fields = context.get("reviewed_context_fields") or []
    field_text = "、".join(str(field) for field in fields) if fields else "未记录 reviewed context 字段"
    labels = {
        "sample_geometry": "sample geometry",
        "substrate": "substrate",
        "reference": "reference",
        "background": "background",
        "diffuse_reflectance": "diffuse reflectance",
        "correction_notes": "correction notes",
    }
    rows = []
    for key, label in labels.items():
        value = context.get(key)
        if _has_uv_vis_context_value(value):
            rows.append(f"- {label}: `{_format_uv_vis_context_value(value)}`")
    detail_text = "\n".join(rows) if rows else "- correction context details: `未记录`"
    return (
        f"Correction context 状态为 `{status}`；reviewed fields: `{field_text}`；record: `{record_ref}`；"
        f"confidence: `{confidence}`；assignment_source: `{source}`。\n\n"
        f"{detail_text}\n\n"
        "该 context 记录只保存已审核的基底、参比、背景、样品几何或漫反射语境；该记录本身不执行自动数值校正，也不把这些 metadata 单独作为 optical mechanism 或 band gap 结论。"
    )


def _uv_vis_numeric_correction_text(metadata: dict) -> str:
    correction = (metadata.get("peak_analysis") or {}).get("numeric_correction")
    if not correction:
        return "当前没有启用或记录 reviewed UV-Vis numeric correction。"
    status = correction.get("status", "unknown")
    method = correction.get("method", "unknown")
    confidence = correction.get("confidence", "insufficient")
    source = correction.get("assignment_source", "ea.uv_vis.numeric_correction:v0.2")
    record_ref = correction.get("record_ref", "未生成")
    input_column = correction.get("input_signal_column", "raw_signal")
    output_column = correction.get("output_signal_column", "numeric_corrected_signal")
    reference_column = correction.get("reviewed_reference_column") or correction.get("reference_signal_column") or "未使用"
    reference_scale = correction.get("reference_scale")
    reference_scale_text = f"{float(reference_scale):.4g}" if reference_scale is not None else "未使用"
    constant_offset = correction.get("constant_offset")
    constant_offset_text = f"{float(constant_offset):.4g}" if constant_offset is not None else "0"
    operation = correction.get("operation", "未记录")
    notes = correction.get("correction_notes") or []
    note_text = "；".join(str(note) for note in notes) if notes else "未记录"
    return (
        f"Reviewed numeric correction 状态为 `{status}`；method: `{method}`；record: `{record_ref}`；"
        f"input/output columns: `{input_column}` -> `{output_column}`；reference column: `{reference_column}`；"
        f"reference_scale: `{reference_scale_text}`；constant_offset: `{constant_offset_text}`；operation: `{operation}`；"
        f"confidence: `{confidence}`；assignment_source: `{source}`。\n\n"
        f"- correction notes: `{note_text}`\n\n"
        "该记录表示用户审核过的透明数值预处理；它不会自动选择参比/背景，不证明基底或参比修正有效，不证明 band gap、transition mechanism、feature assignment 或样品排名。"
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
    interpretation_suggestion_paths: list[Path] | None = None,
    interpretation_review_refs: list[str] | None = None,
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
    derivative_text = _uv_vis_derivative_text(metadata)
    correction_context_text = _uv_vis_correction_context_text(metadata)
    numeric_correction_text = _uv_vis_numeric_correction_text(metadata)
    warnings = metadata.get("warnings") or []
    warning_text = "；".join(
        warning.get("message", str(warning)) if isinstance(warning, dict) else str(warning)
        for warning in warnings
    ) or "未记录高风险 warning。"
    interpretation_suggestion_records = _load_uv_vis_interpretation_suggestion_records(
        root,
        interpretation_suggestion_paths,
        interpretation_review_refs,
        uv_vis_metadata_path=uv_vis_metadata_path,
        project_id=project_id,
    )
    registered_references = _registered_reference_ids(root)
    suggestion_reference_ids = [
        str(reference_id)
        for record in interpretation_suggestion_records
        for reference_id in record.get("reference_ids", [])
        if str(reference_id) in registered_references
    ]
    reference_block = build_report_reference_block(root, _ordered_unique([*(reference_ids or []), *suggestion_reference_ids]))
    citation_text = reference_block["inline_citation"]
    literature_note = f"相关解释应与已登记文献或项目参考谱对应位置共同阅读{citation_text}。" if citation_text else "相关解释尚未绑定外部文献或项目参考谱引用。"
    interpretation_text = _uv_vis_interpretation_text(metadata, citation_text)
    interpretation_suggestion_text = _uv_vis_interpretation_suggestion_text(interpretation_suggestion_records, reference_block)
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

## Correction context 记录

{correction_context_text}

## Reviewed numeric correction

{numeric_correction_text}

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

## Derivative screening

{derivative_text}

## 可能结论与可信度

{interpretation_text}

## Reviewed source-backed UV-Vis interpretation suggestions

{interpretation_suggestion_text}

## 谨慎解释

在当前数据范围内，自动 UV-Vis 特征和阈值 edge 只能支持“光学响应筛查”。不能仅凭本次处理结果直接确认带隙、跃迁类型、缺陷态、膜厚效应或吸收机制；正式 Tauc/derivative/Kubelka-Munk 等分析需要用户确认模型、样品形态和文献依据。{literature_note}任何科学解释进入项目记忆前都需要用户审核。

## 不确定性与限制

{warning_text}

## 输出文件

- processed CSV: `{outputs['processed_csv']}`
- feature table: `{outputs['peak_table']}`
{f"- Tauc/Kubelka-Munk table: `{outputs['tauc_table']}`" if outputs.get('tauc_table') else "- Tauc/Kubelka-Munk table: `未生成`"}
{f"- derivative table: `{outputs['derivative_table']}`" if outputs.get('derivative_table') else "- derivative table: `未生成`"}
{f"- correction context: `{outputs['correction_context']}`" if outputs.get('correction_context') else "- correction context: `未生成`"}
{f"- numeric correction: `{outputs['numeric_correction']}`" if outputs.get('numeric_correction') else "- numeric correction: `未生成`"}
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
            "records": [
                str(uv_vis_metadata_path.relative_to(root)),
                *[_relative_to_root(root, path) for path in interpretation_suggestion_paths or []],
                *[f"reviews/{review_ref}.yml" for review_ref in interpretation_review_refs or []],
            ],
            "files": [
                value
                for value in [
                    outputs["processed_csv"],
                    outputs["peak_table"],
                    outputs.get("tauc_table"),
                    outputs.get("derivative_table"),
                    outputs.get("correction_context"),
                    outputs.get("numeric_correction"),
                    outputs["figure"],
                ]
                if value
            ],
        },
        outputs={"records": [str(report_path.relative_to(root))], "files": []},
        parameters={
            "include_next_step_suggestions": False,
            "language": "zh",
            "interpretation_suggestion_refs": [_relative_to_root(root, path) for path in interpretation_suggestion_paths or []],
            "interpretation_review_refs": interpretation_review_refs or [],
        },
        review_refs=interpretation_review_refs or [],
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


def _xps_background_model_text(metadata: dict) -> str:
    background = (metadata.get("peak_analysis") or {}).get("background_model") or {}
    if not background:
        return "当前没有启用或记录 XPS background model record。"
    status = background.get("status", "unknown")
    count = background.get("region_count", 0)
    confidence = background.get("confidence", "insufficient")
    source = background.get("assignment_source", "ea.xps.background_model:v0.2")
    record_ref = background.get("record_ref", "未生成")
    references = background.get("reference_ids") or []
    reference_text = "、".join(str(item) for item in references) if references else "未绑定 reference_id"
    return (
        f"Reviewed XPS background model record 状态为 `{status}`；region count: `{count}`；record: `{record_ref}`；"
        f"confidence: `{confidence}`；assignment_source: `{source}`；references: `{reference_text}`。\n\n"
        "该记录保存用户审核的 Shirley/Tougaard/linear/local-minimum/rolling-quantile 等背景模型选择、区域和来源；"
        "该 background model record 本身不执行扣背景、不进行 spin-orbit constrained fitting，也不证明化学态或组成。"
    )


def _xps_background_model_table(metadata: dict) -> str:
    background = (metadata.get("peak_analysis") or {}).get("background_model") or {}
    regions = background.get("regions") or []
    if not regions:
        return "当前没有可展示的 XPS background model region。"
    rows = [
        "| region_id | type | window (eV) | applied to processed data | confidence | references |",
        "|---|---|---:|---|---|---|",
    ]
    for region in regions[:12]:
        if not isinstance(region, dict):
            continue
        low = region.get("binding_energy_min_eV")
        high = region.get("binding_energy_max_eV")
        references = region.get("reference_ids") or []
        reference_text = ", ".join(str(ref) for ref in references) if references else "n/a"
        rows.append(
            "| {region_id} | {background_type} | {window} | {applied} | {confidence} | {references} |".format(
                region_id=region.get("region_id", "n/a"),
                background_type=region.get("background_type", "n/a"),
                window=f"{float(low):.2f}-{float(high):.2f}" if low is not None and high is not None else "n/a",
                applied=region.get("applied_to_processed_data", False),
                confidence=region.get("confidence", "insufficient"),
                references=reference_text,
            )
        )
    return "\n".join(rows)


def _xps_background_subtraction_text(metadata: dict) -> str:
    subtraction = (metadata.get("peak_analysis") or {}).get("background_subtraction") or {}
    if not subtraction:
        return "当前没有启用或记录 XPS background subtraction。"
    method = subtraction.get("method", "reviewed_linear_background_subtraction")
    if method == "reviewed_shirley_background_subtraction":
        method_label = "Shirley"
    elif method == "reviewed_tougaard_u2_background_subtraction":
        method_label = "Tougaard U2"
    else:
        method_label = "linear"
    status = subtraction.get("status", "unknown")
    corrected_count = subtraction.get("corrected_region_count", 0)
    region_count = subtraction.get("region_count", 0)
    confidence = subtraction.get("confidence", "insufficient")
    source = subtraction.get("assignment_source", "ea.xps.background_subtraction:v0.2")
    record_ref = subtraction.get("record_ref", "未生成")
    background_column = subtraction.get("background_column", "xps_background")
    corrected_column = subtraction.get("corrected_intensity_column", "xps_background_subtracted_intensity")
    references = subtraction.get("reference_ids") or []
    reference_text = "、".join(str(item) for item in references) if references else "未绑定 reference_id"
    return (
        f"Reviewed XPS {method_label} background subtraction 状态为 `{status}`；corrected regions: `{corrected_count}/{region_count}`；"
        f"record: `{record_ref}`；background column: `{background_column}`；corrected column: `{corrected_column}`；"
        f"confidence: `{confidence}`；assignment_source: `{source}`；references: `{reference_text}`。\n\n"
        "该记录只表示用户审核过的数值扣背景预处理；EA 可以建议有来源的端点/窗口或 Tougaard 参数，"
        "但不能在缺少来源、适用性和审核记录时静默套用；本记录不执行 QUASES/depth-profile modeling 或峰拟合模型，"
        "也不据此证明化学态、组成或 spin-orbit constrained fitting。"
    )


def _xps_background_subtraction_table(metadata: dict) -> str:
    subtraction = (metadata.get("peak_analysis") or {}).get("background_subtraction") or {}
    regions = subtraction.get("regions") or []
    if not regions:
        return "当前没有可展示的 XPS background subtraction region。"
    rows = [
        "| region_id | method | algorithm | window (eV) | left anchor (eV) | right anchor (eV) | B | C_eV2 | direction | points | iterations | converged | status | confidence |",
        "|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---|---|---|",
    ]
    method = subtraction.get("method", "reviewed_linear_background_subtraction")
    for region in regions[:12]:
        if not isinstance(region, dict):
            continue
        low = region.get("binding_energy_min_eV")
        high = region.get("binding_energy_max_eV")
        left = region.get("left_anchor") or {}
        right = region.get("right_anchor") or {}
        left_x = left.get("binding_energy_eV") if isinstance(left, dict) else None
        right_x = right.get("binding_energy_eV") if isinstance(right, dict) else None
        rows.append(
            "| {region_id} | {method} | {algorithm} | {window} | {left} | {right} | {b_value} | {c_value} | {direction} | {points} | {iterations} | {converged} | {status} | {confidence} |".format(
                region_id=region.get("region_id", "n/a"),
                method=method,
                algorithm=region.get("algorithm", "n/a"),
                window=f"{float(low):.2f}-{float(high):.2f}" if low is not None and high is not None else "n/a",
                left=f"{float(left_x):.2f}" if left_x is not None else "n/a",
                right=f"{float(right_x):.2f}" if right_x is not None else "n/a",
                b_value=f"{float(region['tougaard_B']):.6g}" if region.get("tougaard_B") is not None else "n/a",
                c_value=f"{float(region['tougaard_C_eV2']):.6g}" if region.get("tougaard_C_eV2") is not None else "n/a",
                direction=region.get("integration_direction", "n/a"),
                points=region.get("point_count", 0),
                iterations=region.get("iterations", "n/a"),
                converged=region.get("converged", "n/a"),
                status=region.get("status", "unknown"),
                confidence=region.get("confidence", "insufficient"),
            )
        )
    return "\n".join(rows)


def _xps_component_fit_summary(metadata: dict) -> str:
    fit = (metadata.get("peak_analysis") or {}).get("component_fit") or {}
    if not fit:
        return "当前没有启用或记录 XPS component_fit。"
    status = fit.get("status", "unknown")
    fitted_regions = fit.get("fitted_region_count", 0)
    region_count = fit.get("region_count", 0)
    fitted_components = fit.get("fitted_component_count", 0)
    component_count = fit.get("component_count", 0)
    spin_constraints = fit.get("spin_orbit_constraint_count", 0)
    constrained_components = fit.get("constrained_component_count", 0)
    confidence = fit.get("confidence", "insufficient")
    source = fit.get("assignment_source", "ea.xps.component_fit:v0.2")
    record_ref = fit.get("record_ref", "未生成")
    table_ref = fit.get("component_table_ref", "未生成")
    fit_column = fit.get("fit_intensity_column", "xps_component_fit_intensity")
    residual_column = fit.get("residual_column", "xps_component_fit_residual")
    references = fit.get("reference_ids") or []
    reference_text = "、".join(str(item) for item in references) if references else "未绑定 reference_id"
    return (
        f"Reviewed XPS component_fit 状态为 `{status}`；fitted regions: `{fitted_regions}/{region_count}`；"
        f"fitted components: `{fitted_components}/{component_count}`；spin-orbit constraints: `{spin_constraints}`；"
        f"constrained components: `{constrained_components}`；record: `{record_ref}`；table: `{table_ref}`；"
        f"fit column: `{fit_column}`；residual column: `{residual_column}`；confidence: `{confidence}`；"
        f"assignment_source: `{source}`；references: `{reference_text}`。\n\n"
        "该记录只表示用户审核过的 component-fit screening；若存在 spin-orbit constraints，signed delta/ratio/bounds "
        "可以来自用户报告值或有 reference_id 的 source-backed 建议值，但参数来源、适用性和确认状态必须保存在记录中。"
        "EA 可以讨论或建议有来源的候选参数，但不在缺少来源或适用性记录时把它们当作拟合约束；"
        "本记录不静默选择组分、背景、bounds 或峰形，也不据此证明化学态、组成或正式定量。"
    )


def _xps_component_fit_table(metadata: dict) -> str:
    fit = (metadata.get("peak_analysis") or {}).get("component_fit") or {}
    regions = fit.get("regions") or []
    rows = [
        "| component_id | region_id | spin-orbit | shape | center (eV) | FWHM (eV) | area % | RMSE | R^2 | status | confidence |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for region in regions:
        if not isinstance(region, dict):
            continue
        for component in (region.get("components") or [])[:12]:
            if not isinstance(component, dict):
                continue
            center = component.get("fitted_center_eV")
            fwhm = component.get("fitted_fwhm_eV")
            area_percent = component.get("relative_fit_area_percent")
            rmse = component.get("fit_rmse")
            r2 = component.get("fit_r_squared")
            spin = component.get("spin_orbit_constraint_id")
            role = component.get("spin_orbit_role")
            spin_text = f"{spin}:{role}" if spin and role else (str(spin) if spin else "n/a")
            rows.append(
                "| {component_id} | {region_id} | {spin} | {shape} | {center} | {fwhm} | {area_percent} | {rmse} | {r2} | {status} | {confidence} |".format(
                    component_id=component.get("component_id", "n/a"),
                    region_id=component.get("region_id", region.get("region_id", "n/a")),
                    spin=spin_text,
                    shape=component.get("peak_shape", "n/a"),
                    center=f"{float(center):.3f}" if center is not None else "n/a",
                    fwhm=f"{float(fwhm):.3f}" if fwhm is not None else "n/a",
                    area_percent=f"{float(area_percent):.2f}" if area_percent is not None else "n/a",
                    rmse=f"{float(rmse):.4g}" if rmse is not None else "n/a",
                    r2=f"{float(r2):.4f}" if r2 is not None else "n/a",
                    status=component.get("status", "unknown"),
                    confidence=component.get("confidence", "insufficient"),
                )
            )
    if len(rows) == 2:
        return "当前没有可展示的 XPS component_fit component。"
    return "\n".join(rows)


def _xps_region_records_summary(metadata: dict) -> str:
    records = (metadata.get("peak_analysis") or {}).get("region_records") or {}
    if not records:
        return "当前没有启用或记录 XPS region_records。"
    status = records.get("status", "unknown")
    reviewed_regions = records.get("reviewed_region_count", 0)
    region_count = records.get("region_count", 0)
    confidence = records.get("confidence", "insufficient")
    source = records.get("assignment_source", "ea.xps.region_records:v0.2")
    record_ref = records.get("record_ref", "未生成")
    table_ref = records.get("region_table_ref", "未生成")
    refs = records.get("linked_output_refs") or []
    linked = "、".join(str(item) for item in refs[:8]) if refs else "未记录 linked output"
    return (
        f"Reviewed XPS region_records 状态为 `{status}`；reviewed regions: `{reviewed_regions}/{region_count}`；"
        f"record: `{record_ref}`；table: `{table_ref}`；confidence: `{confidence}`；assignment_source: `{source}`；"
        f"linked outputs: `{linked}`。\n\n"
        "该记录只表示用户审核过的 XPS survey/core-level/project region 组织和 provenance；EA 不在缺少审核记录时共享 charge correction，"
        "不静默对齐 survey/core-level 谱图，也不据此证明化学态、正式组成或样品排名。"
    )


def _xps_region_records_table(metadata: dict) -> str:
    records = (metadata.get("peak_analysis") or {}).get("region_records") or {}
    regions = records.get("regions") or []
    rows = [
        "| region_id | role | element | core level | window (eV) | points | calibration group | linked refs | status | confidence |",
        "|---|---|---|---|---:|---:|---|---|---|---|",
    ]
    for region in regions[:12]:
        if not isinstance(region, dict):
            continue
        low = region.get("binding_energy_min_eV")
        high = region.get("binding_energy_max_eV")
        linked_refs = region.get("linked_output_refs") or []
        linked_text = "<br>".join(str(item) for item in linked_refs[:4]) if linked_refs else "n/a"
        rows.append(
            "| {region_id} | {role} | {element} | {core_level} | {window} | {points} | {calibration_group} | {linked_refs} | {status} | {confidence} |".format(
                region_id=region.get("region_id", "n/a"),
                role=region.get("region_role", "n/a"),
                element=region.get("element") or "n/a",
                core_level=region.get("core_level") or "n/a",
                window=f"{float(low):.2f}-{float(high):.2f}" if low is not None and high is not None else "n/a",
                points=region.get("point_count", 0),
                calibration_group=region.get("calibration_group_id") or "n/a",
                linked_refs=linked_text,
                status=region.get("status", "unknown"),
                confidence=region.get("confidence", "insufficient"),
            )
        )
    if len(rows) == 2:
        return "当前没有可展示的 XPS region_records region。"
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
    parameter_suggestion_paths: list[Path] | None = None,
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
    component_fit_summary = _xps_component_fit_summary(metadata)
    component_fit_table = _xps_component_fit_table(metadata)
    region_records_summary = _xps_region_records_summary(metadata)
    region_records_table = _xps_region_records_table(metadata)
    background_summary = _xps_background_model_text(metadata)
    background_table = _xps_background_model_table(metadata)
    background_subtraction_summary = _xps_background_subtraction_text(metadata)
    background_subtraction_table = _xps_background_subtraction_table(metadata)
    calibration_text = _xps_calibration_text(metadata)
    warnings = metadata.get("warnings") or []
    warning_text = "；".join(
        warning.get("message", str(warning)) if isinstance(warning, dict) else str(warning)
        for warning in warnings
    ) or "未记录高风险 warning。"
    parameter_suggestion_records = _load_xps_parameter_suggestion_records(root, parameter_suggestion_paths)
    registered_references = _registered_reference_ids(root)
    suggestion_reference_ids = [
        str(reference_id)
        for record in parameter_suggestion_records
        for reference_id in record.get("reference_ids", [])
        if str(reference_id) in registered_references
    ]
    reference_block = build_report_reference_block(root, _ordered_unique([*(reference_ids or []), *suggestion_reference_ids]))
    citation_text = reference_block["inline_citation"]
    literature_note = f"相关解释应与已登记文献、标准谱库或项目参考谱对应位置共同阅读{citation_text}。" if citation_text else "相关解释尚未绑定外部文献、标准谱库或项目参考谱引用。"
    interpretation_text = _xps_interpretation_text(metadata, citation_text)
    parameter_suggestion_text = _xps_parameter_suggestion_text(parameter_suggestion_records, reference_block)
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

## XPS background model record

{background_summary}

{background_table}

## XPS reviewed background subtraction

{background_subtraction_summary}

{background_subtraction_table}

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

## XPS reviewed component fit screening

{component_fit_summary}

{component_fit_table}

## XPS reviewed multi-region records

{region_records_summary}

{region_records_table}

## 可能结论与可信度

{interpretation_text}

## Source-backed XPS parameter suggestions

{parameter_suggestion_text}

## 谨慎解释

在当前数据范围内，自动 XPS peak 只能支持“谱图结构筛查”。不能仅凭本次自动检峰直接确认化学态、价态、元素组成、表面污染、充电校正正确性或拟合组分；正式 XPS 结论需要用户确认校准参考、背景模型、spin-orbit/峰形/约束、灵敏度因子和文献依据。{literature_note}任何科学解释进入项目记忆前都需要用户审核。

## 不确定性与限制

{warning_text}

## 输出文件

- processed CSV: `{outputs['processed_csv']}`
- peak table: `{outputs['peak_table']}`
- component table: `{outputs.get('component_table', '未生成')}`
{f"- component fit: `{outputs['component_fit']}`" if outputs.get('component_fit') else "- component fit: `未生成`"}
{f"- component fit table: `{outputs['component_fit_table']}`" if outputs.get('component_fit_table') else "- component fit table: `未生成`"}
{f"- region records: `{outputs['region_records']}`" if outputs.get('region_records') else "- region records: `未生成`"}
{f"- region records table: `{outputs['region_records_table']}`" if outputs.get('region_records_table') else "- region records table: `未生成`"}
{f"- background model: `{outputs['background_model']}`" if outputs.get('background_model') else "- background model: `未生成`"}
{f"- background subtraction: `{outputs['background_subtraction']}`" if outputs.get('background_subtraction') else "- background subtraction: `未生成`"}
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
            "records": [str(xps_metadata_path.relative_to(root)), *[_relative_to_root(root, path) for path in parameter_suggestion_paths or []]],
            "files": [
                value
                for value in [
                    outputs["processed_csv"],
                    outputs["peak_table"],
                    outputs.get("component_table"),
                    outputs.get("component_fit_table"),
                    outputs.get("component_fit"),
                    outputs.get("region_records_table"),
                    outputs.get("region_records"),
                    outputs.get("background_model"),
                    outputs.get("background_subtraction"),
                    outputs["figure"],
                ]
                if value
            ],
        },
        outputs={"records": [str(report_path.relative_to(root))], "files": []},
        parameters={
            "include_next_step_suggestions": False,
            "language": "zh",
            "parameter_suggestion_refs": [_relative_to_root(root, path) for path in parameter_suggestion_paths or []],
        },
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


def _electrochemistry_eis_circuit_fit_text(metadata: dict) -> str:
    fit = (metadata.get("peak_analysis") or {}).get("eis_circuit_fit")
    if not fit:
        return "当前没有启用或记录 electrochemistry EIS circuit-fit screening。"
    status = fit.get("status", "unknown")
    confidence = fit.get("confidence", "insufficient")
    source = fit.get("assignment_source", "ea.electrochemistry.eis_circuit_fit:v0.2")
    record_ref = fit.get("record_ref", "未生成")
    applied = fit.get("applied_to_processed_data", False)
    fitted_parameters = fit.get("fitted_parameters") or {}
    quality = fit.get("fit_quality") or {}
    labels = {
        "circuit_model": "circuit model",
        "frequency_input_column": "frequency input column",
        "frequency_unit": "frequency unit",
        "frequency_order_reviewed": "frequency order reviewed",
        "perturbation_amplitude_mV": "perturbation amplitude mV",
        "z_real_input_column": "Z real input column",
        "z_imag_input_column": "Z imag input column",
        "imaginary_input_convention": "imaginary input convention",
        "initial_values": "initial values",
        "bounds": "parameter bounds",
        "fit_quality_thresholds": "fit-quality thresholds",
        "fit_quality_checks": "fit-quality checks",
        "reference_ids": "reference ids",
        "reviewer_notes": "reviewer notes",
        "caveats": "caveats",
    }
    rows = []
    for key, label in labels.items():
        value = fit.get(key)
        if _has_electrochemistry_correction_value(value):
            rows.append(f"- {label}: `{_format_electrochemistry_correction_value(value)}`")
    for key in ["rs_ohm", "rct_ohm", "c_dl_F"]:
        value = fitted_parameters.get(key)
        if _has_electrochemistry_correction_value(value):
            rows.append(f"- fitted {key}: `{_format_electrochemistry_correction_value(value)}`")
    for key in ["point_count", "rmse_ohm", "reduced_chi_square_ohm2", "r_squared_complex", "r_squared_real", "r_squared_imag"]:
        value = quality.get(key)
        if _has_electrochemistry_correction_value(value):
            rows.append(f"- {key}: `{_format_electrochemistry_correction_value(value)}`")
    detail_text = "\n".join(rows) if rows else "- electrochemistry EIS circuit-fit details: `未记录`"
    return (
        f"EIS circuit-fit screening 状态为 `{status}`；applied_to_processed_data: `{applied}`；"
        f"record: `{record_ref}`；confidence: `{confidence}`；assignment_source: `{source}`。\n\n"
        f"{detail_text}\n\n"
        "该步骤只对用户明确选择并审核的等效电路模型做 screening fit；它不是自动模型选择、机理证明、器件性能证明、重复性统计、Tafel/GCD 分析、催化剂排名，也不能单独作为稳定的 Rct/Warburg 结论。"
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


def _has_electrochemistry_correction_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_has_electrochemistry_correction_value(item) for item in value.values())
    if isinstance(value, list | tuple):
        return any(_has_electrochemistry_correction_value(item) for item in value)
    return True


def _format_electrochemistry_correction_value(value: object) -> str:
    if isinstance(value, dict):
        parts = [
            f"{key}={_format_electrochemistry_correction_value(item)}"
            for key, item in value.items()
            if _has_electrochemistry_correction_value(item)
        ]
        return "; ".join(parts) if parts else "未记录"
    if isinstance(value, list | tuple):
        parts = [_format_electrochemistry_correction_value(item) for item in value if _has_electrochemistry_correction_value(item)]
        return "; ".join(parts) if parts else "未记录"
    return str(value)


def _electrochemistry_correction_record_text(metadata: dict) -> str:
    correction = (metadata.get("peak_analysis") or {}).get("correction_record")
    if not correction:
        return "当前没有启用或记录 electrochemistry correction record。"
    status = correction.get("status", "unknown")
    confidence = correction.get("confidence", "insufficient")
    source = correction.get("assignment_source", "ea.electrochemistry.correction_record:v0.2")
    record_ref = correction.get("record_ref", "未生成")
    fields = correction.get("reviewed_correction_fields") or []
    field_text = "、".join(str(field) for field in fields) if fields else "未记录 reviewed correction 字段"
    labels = {
        "reference_electrode": "reference electrode",
        "converted_potential_scale": "converted potential scale",
        "uncompensated_resistance": "uncompensated resistance",
        "ir_compensation": "iR compensation",
        "correction_notes": "correction notes",
    }
    rows = []
    for key, label in labels.items():
        value = correction.get(key)
        if _has_electrochemistry_correction_value(value):
            rows.append(f"- {label}: `{_format_electrochemistry_correction_value(value)}`")
    detail_text = "\n".join(rows) if rows else "- electrochemistry correction details: `未记录`"
    return (
        f"Correction record 状态为 `{status}`；reviewed fields: `{field_text}`；record: `{record_ref}`；"
        f"confidence: `{confidence}`；assignment_source: `{source}`。\n\n"
        f"{detail_text}\n\n"
        "该 correction record 本身只保存已审核的参比电极、电位换算和 iR compensation/Ru 语境；不会由 correction_record 自动平移电位、不执行 iR 数值校正、不拟合等效电路，也不生成 Tafel/GCD 或性能结论。"
    )


def _electrochemistry_potential_conversion_text(metadata: dict) -> str:
    conversion = (metadata.get("peak_analysis") or {}).get("potential_conversion")
    if not conversion:
        return "当前没有启用或记录 electrochemistry potential conversion。"
    status = conversion.get("status", "unknown")
    confidence = conversion.get("confidence", "insufficient")
    source = conversion.get("assignment_source", "ea.electrochemistry.potential_conversion:v0.2")
    record_ref = conversion.get("record_ref", "未生成")
    applied = conversion.get("applied_to_processed_data", False)
    plot_axis = conversion.get("applied_to_plot_axis", False)
    labels = {
        "input_scale": "input scale",
        "target_scale": "target scale",
        "offset_V": "offset V",
        "equation": "equation",
        "input_column": "input column",
        "output_column": "output column",
        "reference_electrode": "reference electrode",
        "reference_ids": "reference ids",
        "reviewer_notes": "reviewer notes",
        "caveats": "caveats",
    }
    rows = []
    for key, label in labels.items():
        value = conversion.get(key)
        if _has_electrochemistry_correction_value(value):
            rows.append(f"- {label}: `{_format_electrochemistry_correction_value(value)}`")
    detail_text = "\n".join(rows) if rows else "- electrochemistry potential conversion details: `未记录`"
    return (
        f"Potential conversion 状态为 `{status}`；applied_to_processed_data: `{applied}`；"
        f"applied_to_plot_axis: `{plot_axis}`；record: `{record_ref}`；confidence: `{confidence}`；assignment_source: `{source}`。\n\n"
        f"{detail_text}\n\n"
        "该步骤是基于用户已审核数值 offset 的 coordinate transform，只对 processed voltammetry 坐标进行换算，并保留原始 `potential_V` 列；它不是 iR compensation、Tafel 分析、等效电路拟合、GCD 性能计算、催化剂排名或机理证明。"
    )


def _electrochemistry_ir_drop_correction_text(metadata: dict) -> str:
    correction = (metadata.get("peak_analysis") or {}).get("ir_drop_correction")
    if not correction:
        return "当前没有启用或记录 electrochemistry iR drop correction。"
    status = correction.get("status", "unknown")
    confidence = correction.get("confidence", "insufficient")
    source = correction.get("assignment_source", "ea.electrochemistry.ir_drop_correction:v0.2")
    record_ref = correction.get("record_ref", "未生成")
    applied = correction.get("applied_to_processed_data", False)
    plot_axis = correction.get("applied_to_plot_axis", False)
    labels = {
        "ru_ohm": "Ru ohm",
        "compensation_fraction": "compensation fraction",
        "sign_convention": "sign convention",
        "formula": "formula",
        "potential_input_column": "potential input column",
        "current_input_column": "current input column",
        "current_unit": "current unit",
        "drop_column": "iR drop column",
        "output_column": "corrected potential column",
        "reference_ids": "reference ids",
        "reviewer_notes": "reviewer notes",
        "caveats": "caveats",
    }
    rows = []
    for key, label in labels.items():
        value = correction.get(key)
        if _has_electrochemistry_correction_value(value):
            rows.append(f"- {label}: `{_format_electrochemistry_correction_value(value)}`")
    detail_text = "\n".join(rows) if rows else "- electrochemistry iR drop correction details: `未记录`"
    return (
        f"iR drop correction 状态为 `{status}`；applied_to_processed_data: `{applied}`；"
        f"applied_to_plot_axis: `{plot_axis}`；record: `{record_ref}`；confidence: `{confidence}`；assignment_source: `{source}`。\n\n"
        f"{detail_text}\n\n"
        "该步骤是基于用户已审核 Ru、补偿比例和符号约定的 coordinate correction，只对 processed voltammetry 坐标写入校正列，并保留原始/换算电位列；它不是 Tafel 分析、等效电路拟合、GCD 性能计算、过电位证明、催化剂排名或机理证明。"
    )


def _electrochemistry_tafel_analysis_text(metadata: dict) -> str:
    tafel = (metadata.get("peak_analysis") or {}).get("tafel_analysis")
    if not tafel:
        return "当前没有启用或记录 electrochemistry Tafel/overpotential analysis。"
    status = tafel.get("status", "unknown")
    confidence = tafel.get("confidence", "insufficient")
    source = tafel.get("assignment_source", "ea.electrochemistry.tafel_analysis:v0.2")
    record_ref = tafel.get("record_ref", "未生成")
    applied = tafel.get("applied_to_processed_data", False)
    stats = tafel.get("fit_statistics") or {}
    labels = {
        "potential_input_column": "potential input column",
        "current_input_column": "current/current-density input column",
        "current_unit": "current unit",
        "fit_window_V": "reviewed fit window V",
        "log_current_column": "log current column",
        "fit_potential_column": "fit potential column",
        "overpotential_reference_V": "overpotential reference V",
        "overpotential_column": "overpotential column",
        "reference_scale": "reference scale",
        "reference_ids": "reference ids",
        "reviewer_notes": "reviewer notes",
        "caveats": "caveats",
    }
    rows = []
    for key, label in labels.items():
        value = tafel.get(key)
        if _has_electrochemistry_correction_value(value):
            rows.append(f"- {label}: `{_format_electrochemistry_correction_value(value)}`")
    for key in ["fit_point_count", "tafel_slope_mV_decade", "absolute_tafel_slope_mV_decade", "intercept_V", "r_squared"]:
        value = stats.get(key)
        if _has_electrochemistry_correction_value(value):
            rows.append(f"- {key}: `{_format_electrochemistry_correction_value(value)}`")
    detail_text = "\n".join(rows) if rows else "- electrochemistry Tafel/overpotential analysis details: `未记录`"
    return (
        f"Tafel/overpotential analysis 状态为 `{status}`；applied_to_processed_data: `{applied}`；"
        f"record: `{record_ref}`；confidence: `{confidence}`；assignment_source: `{source}`。\n\n"
        f"{detail_text}\n\n"
        "该步骤只在用户已审核 kinetic window 内做 log-current 线性 screening fit，并可记录 reviewed overpotential reference；它不是自动选区、交换电流证明、催化剂排名、等效电路拟合、GCD 容量/电容计算、稳定性评估或机理证明。"
    )


def _electrochemistry_gcd_analysis_text(metadata: dict) -> str:
    gcd = (metadata.get("peak_analysis") or {}).get("gcd_analysis")
    if not gcd:
        return "当前没有启用或记录 electrochemistry GCD analysis。"
    status = gcd.get("status", "unknown")
    confidence = gcd.get("confidence", "insufficient")
    source = gcd.get("assignment_source", "ea.electrochemistry.gcd_analysis:v0.2")
    record_ref = gcd.get("record_ref", "未生成")
    applied = gcd.get("applied_to_processed_data", False)
    metrics = gcd.get("metrics") or {}
    labels = {
        "time_input_column": "time input column",
        "voltage_input_column": "voltage input column",
        "voltage_unit": "voltage unit",
        "discharge_time_window_s": "reviewed discharge time window s",
        "voltage_window_V": "reviewed voltage window V",
        "discharge_current_mA": "reviewed discharge current mA",
        "current_sign_convention": "current sign convention",
        "reference_ids": "reference ids",
        "reviewer_notes": "reviewer notes",
        "caveats": "caveats",
    }
    rows = []
    for key, label in labels.items():
        value = gcd.get(key)
        if _has_electrochemistry_correction_value(value):
            rows.append(f"- {label}: `{_format_electrochemistry_correction_value(value)}`")
    for key in [
        "duration_s",
        "voltage_span_V",
        "charge_C",
        "capacity_mAh",
        "capacitance_F",
        "specific_capacity_mAh_g-1",
        "specific_capacitance_F_g-1",
        "areal_capacity_mAh_cm-2",
        "areal_capacitance_F_cm-2",
    ]:
        value = metrics.get(key)
        if _has_electrochemistry_correction_value(value):
            rows.append(f"- {key}: `{_format_electrochemistry_correction_value(value)}`")
    detail_text = "\n".join(rows) if rows else "- electrochemistry GCD analysis details: `未记录`"
    return (
        f"GCD analysis 状态为 `{status}`；applied_to_processed_data: `{applied}`；"
        f"record: `{record_ref}`；confidence: `{confidence}`；assignment_source: `{source}`。\n\n"
        f"{detail_text}\n\n"
        "该步骤只在用户已审核 discharge time/voltage window 内计算容量/电容筛查指标；它不是自动放电段选择、电流符号推断、器件性能证明、倍率/循环稳定性评估、催化剂排名、等效电路拟合、Tafel 分析或机理证明。"
    )


def _electrochemistry_gcd_summary_text(metadata: dict) -> str:
    gcd = (metadata.get("peak_analysis") or {}).get("gcd_analysis") or {}
    metrics = gcd.get("metrics") or {}
    if not metrics:
        return "当前没有可复用的 reviewed GCD discharge metrics；请先确认放电时间窗口、电压窗口、电流、质量/面积/负载量和协议。"
    parts = [
        f"reviewed discharge duration = `{metrics.get('duration_s')}` s",
        f"voltage span = `{metrics.get('voltage_span_V')}` V",
        f"capacity = `{metrics.get('capacity_mAh')}` mAh",
        f"capacitance = `{metrics.get('capacitance_F')}` F",
    ]
    if metrics.get("specific_capacity_mAh_g-1") is not None:
        parts.append(f"specific capacity = `{metrics.get('specific_capacity_mAh_g-1')}` mAh g^-1")
    if metrics.get("specific_capacitance_F_g-1") is not None:
        parts.append(f"specific capacitance = `{metrics.get('specific_capacitance_F_g-1')}` F g^-1")
    return "GCD reviewed discharge metrics: " + "；".join(parts) + "。"


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
    is_gcd = metadata.get("measurement_mode") == "gcd"
    feature_text = _electrochemistry_eis_feature_summary(root, feature_table_ref) if is_eis else _electrochemistry_feature_summary(root, feature_table_ref)
    feature_table = _electrochemistry_eis_feature_table(root, feature_table_ref) if is_eis else _electrochemistry_feature_table(root, feature_table_ref)
    if is_eis:
        current_summary = _electrochemistry_eis_summary_text(metadata)
        summary_heading = "EIS Nyquist screening 摘要"
    elif is_gcd and (metadata.get("peak_analysis") or {}).get("gcd_analysis"):
        current_summary = _electrochemistry_gcd_summary_text(metadata)
        summary_heading = "GCD discharge metrics 摘要"
    else:
        current_summary = _electrochemistry_current_summary(metadata)
        summary_heading = "电流摘要"
    correction_text = _electrochemistry_correction_record_text(metadata)
    potential_conversion_text = _electrochemistry_potential_conversion_text(metadata)
    ir_drop_correction_text = _electrochemistry_ir_drop_correction_text(metadata)
    eis_circuit_fit_text = _electrochemistry_eis_circuit_fit_text(metadata)
    tafel_analysis_text = _electrochemistry_tafel_analysis_text(metadata)
    gcd_analysis_text = _electrochemistry_gcd_analysis_text(metadata)
    caution_text = (
        "在当前数据范围内，自动 EIS Nyquist screening 和可选 reviewed circuit-fit 只能支持“阻抗弧形状/用户指定模型筛查”。不能仅凭本次自动处理直接确认等效电路、Rct/Warburg 机理、电容、电荷转移机制或器件性能；正式结论需要用户确认频率顺序、扰动幅值、等效电路模型、重复性和文献依据。"
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

## Correction/reference record

{correction_text}

## Potential conversion

{potential_conversion_text}

## iR drop correction

{ir_drop_correction_text}

## EIS circuit-fit screening

{eis_circuit_fit_text}

## Tafel/overpotential analysis

{tafel_analysis_text}

## GCD discharge metrics

{gcd_analysis_text}

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
{f"- correction record: `{outputs['correction_record']}`" if outputs.get('correction_record') else "- correction record: `未生成`"}
{f"- potential conversion: `{outputs['potential_conversion']}`" if outputs.get('potential_conversion') else "- potential conversion: `未生成`"}
{f"- iR drop correction: `{outputs['ir_drop_correction']}`" if outputs.get('ir_drop_correction') else "- iR drop correction: `未生成`"}
{f"- EIS circuit-fit screening: `{outputs['eis_circuit_fit']}`" if outputs.get('eis_circuit_fit') else "- EIS circuit-fit screening: `未生成`"}
{f"- Tafel/overpotential analysis: `{outputs['tafel_analysis']}`" if outputs.get('tafel_analysis') else "- Tafel/overpotential analysis: `未生成`"}
{f"- GCD discharge metrics: `{outputs['gcd_analysis']}`" if outputs.get('gcd_analysis') else "- GCD discharge metrics: `未生成`"}
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
            "files": [
                value
                for value in [
                    outputs["processed_csv"],
                    feature_table_ref,
                    outputs.get("correction_record"),
                    outputs.get("potential_conversion"),
                    outputs.get("ir_drop_correction"),
                    outputs.get("eis_circuit_fit"),
                    outputs.get("tafel_analysis"),
                    outputs.get("gcd_analysis"),
                    outputs["figure"],
                ]
                if value
            ],
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


def _has_thermal_context_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_has_thermal_context_value(item) for item in value.values())
    if isinstance(value, list | tuple):
        return any(_has_thermal_context_value(item) for item in value)
    return True


def _format_thermal_context_value(value: object) -> str:
    if isinstance(value, dict):
        parts = [f"{key}={_format_thermal_context_value(item)}" for key, item in value.items() if _has_thermal_context_value(item)]
        return "; ".join(parts) if parts else "未记录"
    if isinstance(value, list | tuple):
        parts = [_format_thermal_context_value(item) for item in value if _has_thermal_context_value(item)]
        return "; ".join(parts) if parts else "未记录"
    return str(value)


def _thermal_context_record_text(metadata: dict) -> str:
    context = (metadata.get("peak_analysis") or {}).get("context_record")
    if not context:
        return "当前没有启用或记录 thermal context record。"
    status = context.get("status", "unknown")
    confidence = context.get("confidence", "insufficient")
    source = context.get("assignment_source", "ea.thermal.context_record:v0.2")
    record_ref = context.get("record_ref", "未生成")
    fields = context.get("reviewed_context_fields") or []
    field_text = "、".join(str(field) for field in fields) if fields else "未记录 reviewed context 字段"
    labels = {
        "dsc_sign_convention": "DSC sign convention",
        "baseline_reference": "baseline/reference",
        "sample_context": "sample context",
        "atmosphere_program": "atmosphere/program",
        "correction_notes": "correction notes",
    }
    rows = []
    for key, label in labels.items():
        value = context.get(key)
        if _has_thermal_context_value(value):
            rows.append(f"- {label}: `{_format_thermal_context_value(value)}`")
    detail_text = "\n".join(rows) if rows else "- thermal context details: `未记录`"
    return (
        f"Thermal context record 状态为 `{status}`；reviewed fields: `{field_text}`；record: `{record_ref}`；"
        f"confidence: `{confidence}`；assignment_source: `{source}`。\n\n"
        f"{detail_text}\n\n"
        "该记录只保存已审核的 DSC 符号约定、baseline/reference、样品和气氛/温度程序语境；本阶段不自动翻转 DSC 符号、不执行 baseline/reference 数值校正，"
        "也不把这些 metadata 单独作为 Tg/Tm/Tc、动力学或分解/熔融/结晶机制结论。"
    )


def _thermal_baseline_correction_text(metadata: dict) -> str:
    correction = (metadata.get("peak_analysis") or {}).get("baseline_correction")
    if not correction:
        return "当前没有启用或记录 thermal baseline correction。"
    status = correction.get("status", "unknown")
    applied = correction.get("applied", False)
    confidence = correction.get("confidence", "insufficient")
    source = correction.get("assignment_source", "ea.thermal.baseline_correction:v0.2")
    record_ref = correction.get("record_ref", "未生成")
    method = correction.get("method", "未记录")
    anchors = correction.get("anchor_points") or []
    anchor_parts = []
    for anchor in anchors:
        if isinstance(anchor, dict):
            temp = anchor.get("actual_temperature_C", "n/a")
            signal = anchor.get("signal_value", "n/a")
            anchor_parts.append(f"T={temp} C, signal={signal}")
    anchor_text = "；".join(anchor_parts) if anchor_parts else "未记录"
    baseline_column = correction.get("baseline_column", "未生成")
    corrected_column = correction.get("corrected_column", "未生成")
    return (
        f"Thermal baseline correction 状态为 `{status}`；applied: `{applied}`；method: `{method}`；record: `{record_ref}`；"
        f"confidence: `{confidence}`；assignment_source: `{source}`。\n\n"
        f"- anchor points: `{anchor_text}`\n"
        f"- baseline column: `{baseline_column}`\n"
        f"- corrected signal column: `{corrected_column}`\n\n"
        "该 baseline correction 是已审核参数触发的数值处理步骤，用于改善 DSC/DTG-style trace 的筛查；它本身不自动给出 Tg/Tm/Tc、动力学、热稳定性排名或分解/熔融/结晶机制结论。"
    )


def _thermal_transition_screening_text(metadata: dict) -> str:
    transition = (metadata.get("peak_analysis") or {}).get("transition_analysis")
    if not transition:
        return "当前没有启用或记录 thermal transition screening。"
    status = transition.get("status", "unknown")
    count = transition.get("transition_count", 0)
    confidence = transition.get("confidence", "insufficient")
    source = transition.get("assignment_source", "ea.thermal.transition_analysis:v0.2")
    table_ref = transition.get("table_ref", "未生成")
    record_ref = transition.get("record_ref", "未生成")
    method = transition.get("method", "未记录")
    return (
        f"Thermal transition screening 状态为 `{status}`；candidate count: `{count}`；method: `{method}`；"
        f"table: `{table_ref}`；record: `{record_ref}`；confidence: `{confidence}`；assignment_source: `{source}`。\n\n"
        "该 screening 只在用户已审核的温度窗口内提取 Tg/Tm/Tc-style 候选指标；它不是正式相变赋值、动力学拟合、热稳定性排名或分解/熔融/结晶机制证明。"
    )


def _thermal_transition_table(root: Path, transition_table_ref: str | None) -> str:
    if not transition_table_ref:
        return "当前没有可展示的 reviewed transition screening 表。"
    transitions = pd.read_csv(root / transition_table_ref)
    if transitions.empty:
        return "当前 transition screening 未生成候选行。"
    rows = [
        "| transition_id | type | window (C) | candidate T (C) | metric | signal | confidence | source |",
        "|---|---|---:|---:|---|---:|---|---|",
    ]
    for _, item in transitions.head(12).iterrows():
        candidate = item.get("estimated_temperature_C")
        signal = item.get("signal_value")
        rows.append(
            "| {transition_id} | {transition_type} | {window_start:.1f}-{window_end:.1f} | {candidate} | {metric} | {signal} | {confidence} | {source} |".format(
                transition_id=item.get("transition_id", "n/a"),
                transition_type=item.get("transition_type", "n/a"),
                window_start=float(item.get("window_start_C", 0.0)) if pd.notna(item.get("window_start_C")) else 0.0,
                window_end=float(item.get("window_end_C", 0.0)) if pd.notna(item.get("window_end_C")) else 0.0,
                candidate=f"{float(candidate):.2f}" if pd.notna(candidate) else "n/a",
                metric=item.get("metric", "n/a"),
                signal=f"{float(signal):.4g}" if pd.notna(signal) else "n/a",
                confidence=item.get("assignment_confidence", "insufficient"),
                source=item.get("assignment_source", "未记录"),
            )
        )
    return "\n".join(rows)


def _thermal_transition_assignment_text(metadata: dict) -> str:
    assignment = (metadata.get("peak_analysis") or {}).get("transition_assignment")
    if not assignment:
        return "当前没有启用或记录 user-confirmed thermal transition assignments。"
    status = assignment.get("status", "unknown")
    count = assignment.get("assignment_count", 0)
    confidence = assignment.get("confidence", "insufficient")
    source = assignment.get("assignment_source", "ea.thermal.transition_assignment:v0.2")
    record_ref = assignment.get("record_ref", "未生成")
    method = assignment.get("method", "未记录")
    reference_ids = assignment.get("reference_ids") or []
    reference_text = "、".join(str(item) for item in reference_ids) if reference_ids else "未绑定 reference_id"
    return (
        f"Thermal transition assignment 状态为 `{status}`；assignment count: `{count}`；method: `{method}`；"
        f"record: `{record_ref}`；confidence: `{confidence}`；assignment_source: `{source}`；references: `{reference_text}`。\n\n"
        "该记录保存用户确认的 transition interpretation 及其证据/引用链接；它不是 EA 自动从候选峰生成的正式相变赋值，也不是动力学拟合、热稳定性排名或机理证明。"
    )


def _thermal_transition_assignment_table(metadata: dict) -> str:
    assignment = (metadata.get("peak_analysis") or {}).get("transition_assignment")
    if not assignment:
        return "当前没有可展示的 user-confirmed transition assignment 表。"
    assignments = assignment.get("assignments") or []
    if not assignments:
        return "当前 transition assignment record 未生成 assignment 行。"
    rows = [
        "| assignment_id | transition_id | assigned type | assigned T (C) | candidate link | confidence | references |",
        "|---|---|---|---:|---|---|---|",
    ]
    for item in assignments[:12]:
        if not isinstance(item, dict):
            continue
        temperature = item.get("assigned_temperature_C")
        references = item.get("reference_ids") or []
        reference_text = ", ".join(str(ref) for ref in references) if references else "n/a"
        rows.append(
            "| {assignment_id} | {transition_id} | {assigned_type} | {temperature} | {link_status} | {confidence} | {references} |".format(
                assignment_id=item.get("assignment_id", "n/a"),
                transition_id=item.get("transition_id", "n/a") or "n/a",
                assigned_type=item.get("assigned_transition_type", "n/a"),
                temperature=f"{float(temperature):.2f}" if temperature is not None else "n/a",
                link_status=item.get("candidate_link_status", "n/a"),
                confidence=item.get("confidence", "insufficient"),
                references=reference_text,
            )
        )
    return "\n".join(rows)


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
    context_text = _thermal_context_record_text(metadata)
    baseline_text = _thermal_baseline_correction_text(metadata)
    transition_text = _thermal_transition_screening_text(metadata)
    transition_table = _thermal_transition_table(root, outputs.get("transition_table"))
    transition_assignment_text = _thermal_transition_assignment_text(metadata)
    transition_assignment_table = _thermal_transition_assignment_table(metadata)
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

## Thermal context record

{context_text}

## Thermal baseline correction

{baseline_text}

## Thermal transition screening

{transition_text}

{transition_table}

## Thermal transition assignments

{transition_assignment_text}

{transition_assignment_table}

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
{f"- baseline correction: `{outputs['baseline_correction']}`" if outputs.get('baseline_correction') else "- baseline correction: `未生成`"}
{f"- transition table: `{outputs['transition_table']}`" if outputs.get('transition_table') else "- transition table: `未生成`"}
{f"- transition record: `{outputs['transition_record']}`" if outputs.get('transition_record') else "- transition record: `未生成`"}
{f"- transition assignment: `{outputs['transition_assignment']}`" if outputs.get('transition_assignment') else "- transition assignment: `未生成`"}
{f"- context record: `{outputs['context_record']}`" if outputs.get('context_record') else "- context record: `未生成`"}
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
            "files": [
                value
                for value in [
                    outputs["processed_csv"],
                    feature_table_ref,
                    outputs.get("baseline_correction"),
                    outputs.get("transition_table"),
                    outputs.get("transition_record"),
                    outputs.get("transition_assignment"),
                    outputs.get("context_record"),
                    outputs["figure"],
                ]
                if value
            ],
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
