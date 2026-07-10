from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from ea.figures import figure_footer, register_figure, update_figure_report_ref
from ea.provenance import write_provenance_entry
from ea.raw_import import assert_not_raw_output_path
from ea.references import build_report_reference_block
from ea.reports.service import register_report
from ea.review import require_confirmed_review
from ea.schema import ImageAnalysisResult, ReportRecord
from ea.schema.models import EARecord
from ea.standards import infer_project_slug, slugify
from ea.storage.files import read_markdown_record, read_yaml, write_markdown_record, write_yaml
from ea.storage.ids import next_id, next_standard_id


class ImageDataError(RuntimeError):
    """Raised when image characterization records cannot be created safely."""


Confidence = Literal["high", "medium", "low", "insufficient"]
AnalysisMode = Literal["user_described", "agent_visual_review", "mixed"]


SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
CONFIDENCE_LABEL_ZH = {
    "high": "高",
    "medium": "中",
    "low": "低",
    "insufficient": "不足",
}


def _created_day(created_at: str | None) -> str | None:
    return created_at[:10] if created_at else None


def _uses_v0_2_project_ids(project_id: str) -> bool:
    return project_id.startswith("prj-")


def _project_path(root: Path, value: Path) -> Path:
    return value if value.is_absolute() else root / value


def _warning(code: str, message: str, severity: str = "low", **details: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message, "severity": severity}
    payload.update(details)
    return payload


def _write_display_copy(raw_path: Path, output: Path, footer: str | None) -> None:
    if raw_path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
        raise ImageDataError(f"Unsupported image format: {raw_path.suffix}")
    image = plt.imread(raw_path)
    fig, ax = plt.subplots(figsize=(6.0, 4.5))
    ax.imshow(image, cmap="gray" if getattr(image, "ndim", 0) == 2 else None)
    ax.axis("off")
    if footer:
        fig.text(0.99, 0.01, footer, ha="right", va="bottom", fontsize=5.5, color="#666666")
        fig.tight_layout(rect=(0, 0.04, 1, 1))
    else:
        fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=300, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)


def _reference_text(references: list[dict[str, Any]]) -> str:
    if not references:
        return "本报告当前未引用外部文献。若后续加入文献解释，正文对应位置必须使用 `[1]` 形式标注，并在本节列出 DOI、本地 PDF 或网页链接。"
    lines = []
    for index, reference in enumerate(references, start=1):
        citation = reference.get("citation") or reference.get("title") or "Untitled reference"
        doi = reference.get("doi")
        local = reference.get("local")
        web = reference.get("web")
        suffix = " | ".join(part for part in [f"DOI: {doi}" if doi else "", f"Local: {local}" if local else "", f"Web: {web}" if web else ""] if part)
        lines.append(f"[{index}] {citation}" + (f" | {suffix}" if suffix else ""))
    return "\n".join(lines)


def _report_link(report_path: Path, root_relative_ref: str) -> str:
    return Path("..", root_relative_ref).as_posix()


def create_image_analysis_record(
    root: Path,
    *,
    characterization_metadata_path: Path,
    project_id: str,
    method: str,
    user_description: str,
    description_review_ref: str,
    sample_refs: list[str] | None = None,
    analysis_mode: AnalysisMode = "user_described",
    ea_observations: list[str] | None = None,
    interpretation: str | None = None,
    confidence: Confidence = "insufficient",
    scale_bar: str | None = None,
    imaging_conditions: dict[str, Any] | None = None,
    references: list[dict[str, Any]] | None = None,
    reference_ids: list[str] | None = None,
    created_at: str | None = None,
) -> Path:
    if not user_description.strip():
        raise ImageDataError("Image analysis requires a user description or confirmed image notes.")
    require_confirmed_review(root, description_review_ref)

    metadata_path = _project_path(root, characterization_metadata_path)
    raw_metadata = read_yaml(metadata_path)
    raw_path = root / raw_metadata["project_raw_path"]
    if not raw_path.exists():
        raise ImageDataError(f"Raw image file is missing: {raw_path}")

    day = _created_day(created_at)
    project_slug = infer_project_slug(project_id)
    method_slug = slugify(method)
    if _uses_v0_2_project_ids(project_id):
        result_id = next_standard_id(root, "result", project_slug, method=method_slug, day=day)
        figure_id = next_standard_id(root, "figure", project_slug, method=method_slug, day=day)
    else:
        result_id = next_id(root, "image_result", day)
        figure_id = None

    sample_refs = sample_refs or raw_metadata.get("sample_refs", [])
    sample_dir = sample_refs[0] if sample_refs else "unmapped-sample"
    output_dir = root / "processed" / sample_dir / method_slug / result_id
    display_name = f"{figure_id}.png" if figure_id else "image_display.png"
    display_image = output_dir / display_name
    result_metadata = output_dir / "image_metadata.yml"
    for output in [display_image, result_metadata]:
        assert_not_raw_output_path(root, output)

    _write_display_copy(raw_path, display_image, figure_footer(figure_id, None) if figure_id else None)

    warnings: list[dict[str, Any]] = [
        _warning(
            "image_analysis_user_described",
            "Image interpretation is grounded in user-provided description unless explicit visual review is documented.",
        )
    ]
    if not scale_bar:
        warnings.append(_warning("scale_bar_missing", "No scale bar was recorded for this image.", severity="medium"))
    if confidence in {"low", "insufficient"}:
        warnings.append(
            _warning(
                "image_interpretation_low_confidence",
                "Image interpretation confidence is low or insufficient; ask for more image context before using it as strong evidence.",
                severity="medium",
                confidence=confidence,
            )
        )

    result = ImageAnalysisResult(
        image_result_id=result_id,
        result_id=result_id,
        project_id=project_id,
        characterization_file_ref=raw_metadata["characterization_id"],
        sample_refs=sample_refs,
        method=method_slug,
        analysis_mode=analysis_mode,
        user_description=user_description.strip(),
        ea_observations=ea_observations or [],
        interpretation=interpretation,
        confidence=confidence,
        scale_bar=scale_bar,
        imaging_conditions=imaging_conditions or {},
        outputs={
            "figure": display_image.relative_to(root).as_posix(),
            "raw_image": raw_metadata["project_raw_path"],
            "metadata": result_metadata.relative_to(root).as_posix(),
        },
        figure_id=figure_id,
        warnings=warnings,
        references=references or [],
        reference_ids=reference_ids or [],
        review_refs=[description_review_ref],
        created_at=created_at or EARecord.now_iso(),
        updated_at=created_at or EARecord.now_iso(),
    )
    write_yaml(result_metadata, result.model_dump(exclude_none=True))
    provenance_path = write_provenance_entry(
        root,
        workflow="image_characterization_analysis",
        inputs={
            "records": [metadata_path.relative_to(root).as_posix()],
            "files": [raw_metadata["project_raw_path"]],
        },
        outputs={
            "records": [result_metadata.relative_to(root).as_posix()],
            "files": [display_image.relative_to(root).as_posix()],
        },
        parameters={
            "method": method_slug,
            "analysis_mode": analysis_mode,
            "confidence": confidence,
            "scale_bar": scale_bar,
            "imaging_conditions": imaging_conditions or {},
        },
        review_refs=[description_review_ref],
        warnings=warnings,
        scripts=[{"path": "src/ea/image_data/service.py", "version": "0.2.0"}],
        created_at=created_at,
    )
    result_data = read_yaml(result_metadata)
    result_data["provenance_refs"] = [provenance_path.stem]
    write_yaml(result_metadata, result_data)

    if figure_id:
        register_figure(
            root,
            figure_id=figure_id,
            path=display_image.relative_to(root).as_posix(),
            report_id=None,
            result_id=result_id,
            raw_data_ids=[raw_metadata["characterization_id"]],
            sample_ids=sample_refs,
            experiment_ids=raw_metadata.get("experiment_refs", []),
            generation={
                "script": "src/ea/image_data/service.py",
                "parameters": {"method": method_slug, "analysis_mode": analysis_mode, "confidence": confidence},
            },
            caption=f"{method_slug} image display copy linked to raw characterization data.",
            purpose="image_analysis_report",
        )
    return result_metadata


def generate_image_analysis_report(
    root: Path,
    *,
    project_id: str,
    image_metadata_path: Path,
    related_experiments: list[str] | None = None,
    related_samples: list[str] | None = None,
    reference_ids: list[str] | None = None,
    created_at: str | None = None,
) -> Path:
    metadata_path = _project_path(root, image_metadata_path)
    metadata = read_yaml(metadata_path)
    day = _created_day(created_at)
    if _uses_v0_2_project_ids(project_id):
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
        report_type="image_analysis",
        related_experiments=related_experiments,
        related_samples=related_samples,
        related_results=[metadata["result_id"]],
        figure_ids=figure_ids,
        include_next_step_suggestions=False,
        status="draft",
        created_at=created_at or EARecord.now_iso(),
        updated_at=created_at or EARecord.now_iso(),
    )

    outputs = metadata["outputs"]
    warning_text = "；".join(
        warning.get("message", str(warning)) if isinstance(warning, dict) else str(warning)
        for warning in metadata.get("warnings", [])
    ) or "未记录高风险 warning。"
    reference_ids = reference_ids if reference_ids is not None else metadata.get("reference_ids", [])
    reference_block = build_report_reference_block(root, reference_ids)
    if reference_block["reference_ids"]:
        references_markdown = reference_block["references_markdown"]
        citation_text = reference_block["inline_citation"]
    else:
        references_markdown = _reference_text(metadata.get("references") or [])
        citation_text = ""
    observations = metadata.get("ea_observations") or ["未记录独立视觉观察；当前分析主要依据用户描述。"]
    interpretation = metadata.get("interpretation") or "当前报告未写入强解释；建议结合样品背景、仪器参数和必要的人工复核后再进入项目记忆。"
    if citation_text and not interpretation.rstrip().endswith(citation_text):
        interpretation = f"{interpretation}{citation_text}"
    confidence = CONFIDENCE_LABEL_ZH.get(metadata.get("confidence", "insufficient"), "不足")
    body = f"""# 图片类表征数据分析报告

## 报告 ID 信息

- report_id: `{report_id}`
- project_id: `{project_id}`
- result_ids: `{metadata['result_id']}`
- figure_ids: `{', '.join(figure_ids) if figure_ids else '未生成 v0.2 figure_id'}`
- characterization_file_ref: `{metadata['characterization_file_ref']}`
- method: `{metadata['method']}`

## 数据来源

本报告基于图片类表征结果 `{metadata['result_id']}` 生成，关联样品为 `{', '.join(related_samples) if related_samples else '未明确映射样品'}`。原始图片、展示副本、报告图 ID 和 provenance 均已保存。

![{figure_ids[0] if figure_ids else 'image-display'}]({_report_link(report_path, outputs['figure'])})

- 展示图片: `{outputs['figure']}`
- 原始图片: `{outputs['raw_image']}`
- 原图链接: [{outputs['raw_image']}]({_report_link(report_path, outputs['raw_image'])})
- 结果 metadata: `{outputs['metadata']}`

## 用户确认描述

{metadata['user_description']}

## EA 观察记录

{chr(10).join(f'- {item}' for item in observations)}

## 分析与可能结论

{interpretation}

- confidence: `{metadata.get('confidence', 'insufficient')}` / `{confidence}`
- scale_bar: `{metadata.get('scale_bar') or '未记录'}`
- analysis_mode: `{metadata.get('analysis_mode')}`

## 不确定性与限制

{warning_text}

## References

{references_markdown}

## 溯源

本报告草稿引用 image result `{metadata['result_id']}`，对应 provenance 将在报告生成后写入。
"""
    report_frontmatter = report.model_dump(exclude_none=True)
    report_frontmatter["reference_ids"] = reference_block["reference_ids"]
    report_frontmatter["numbered_references"] = reference_block["numbered_references"]
    write_markdown_record(report_path, report_frontmatter, body)
    provenance_path = write_provenance_entry(
        root,
        workflow="image_report_generation",
        inputs={
            "records": [metadata_path.relative_to(root).as_posix()],
            "files": [outputs["figure"], outputs["raw_image"]],
        },
        outputs={"records": [report_path.relative_to(root).as_posix()], "files": []},
        parameters={"language": "zh", "report_type": "image_analysis"},
        review_refs=metadata.get("review_refs", []),
        warnings=metadata.get("warnings", []),
        source_refs=[],
        scripts=[{"path": "src/ea/image_data/service.py", "version": "0.2.0"}],
        created_at=created_at,
    )
    frontmatter, _ = read_markdown_record(report_path)
    frontmatter["provenance_refs"] = [provenance_path.stem]
    write_markdown_record(report_path, frontmatter, body)
    for figure_id in figure_ids:
        update_figure_report_ref(root, figure_id, report_id)
    register_report(
        root,
        report_id=report_id,
        path=report_path.relative_to(root).as_posix(),
        project_id=project_id,
        result_ids=[metadata["result_id"]],
        figure_ids=figure_ids,
        sample_ids=related_samples,
        experiment_ids=related_experiments,
        reference_ids=reference_block["reference_ids"],
    )
    return report_path
