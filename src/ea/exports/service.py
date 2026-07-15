from __future__ import annotations

import base64
import hashlib
import html
import mimetypes
import os
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any, Iterable

import yaml

from ea.figures import figure_path_for_report
from ea.report_messages import localized_figure_caption, localized_source_data_purpose
from ea.schema.models import EARecord
from ea.storage.files import read_markdown_record, read_yaml, write_yaml
from ea.traceability import build_project_trace_view


class ReportBundleError(RuntimeError):
    """Raised when a report bundle cannot be produced from project indices."""


def _clean_ref(ref: str) -> str:
    return ref.split("#", 1)[0]


def _project_path(root: Path, ref: str) -> Path:
    path = Path(_clean_ref(ref))
    return path if path.is_absolute() else root / path


def _project_ref(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _provenance_path(root: Path, ref: str) -> Path:
    path = Path(_clean_ref(ref))
    if path.suffix or len(path.parts) > 1:
        return path if path.is_absolute() else root / path
    return root / "provenance" / f"{ref}.yml"


def _safe_name(value: str) -> str:
    value = _clean_ref(value).strip("/")
    return re.sub(r"[^A-Za-z0-9_.-]+", "__", value) or "artifact"


def _is_inside(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _copy_project_file(
    root: Path,
    bundle_dir: Path,
    *,
    ref: str,
    subdir: str,
    kind: str,
    label: str | None = None,
) -> dict[str, Any]:
    source = _project_path(root, ref)
    record: dict[str, Any] = {
        "kind": kind,
        "label": label,
        "source_ref": ref,
        "exists": source.exists(),
        "copied": False,
        "bundle_ref": None,
    }
    if not source.exists():
        record["skip_reason"] = "missing_source"
        return record
    if not _is_inside(root, source):
        record["skip_reason"] = "outside_project_root"
        return record
    target = bundle_dir / subdir / _safe_name(_project_ref(root, source))
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    record["copied"] = True
    record["bundle_ref"] = target.relative_to(bundle_dir).as_posix()
    record["source_ref"] = _project_ref(root, source)
    return record


def _reports_index(root: Path) -> dict[str, Any]:
    path = root / "reports" / "index.yml"
    if not path.exists():
        raise ReportBundleError(f"Report index is missing: {path}")
    return read_yaml(path).get("reports", {})


def _batch_index(root: Path) -> dict[str, Any]:
    path = root / "processed" / "batches" / "index.yml"
    if not path.exists():
        raise ReportBundleError(f"Batch index is missing: {path}")
    return read_yaml(path).get("batches", {})


def _figures_index(root: Path) -> dict[str, Any]:
    path = root / "figures" / "index.yml"
    return read_yaml(path).get("figures", {}) if path.exists() else {}


def _reference_index(root: Path) -> dict[str, Any]:
    path = root / "literature" / "references" / "index.yml"
    return read_yaml(path).get("references", {}) if path.exists() else {}


def _result_metadata_index(root: Path) -> dict[str, Path]:
    results: dict[str, Path] = {}
    for path in sorted((root / "processed").glob("**/*.yml")):
        if "batches" in path.parts:
            continue
        data = read_yaml(path)
        for key, value in data.items():
            if (key == "result_id" or key.endswith("_result_id")) and value:
                results[str(value)] = path
    return results


def _record_missing(
    manifest: dict[str, Any], *, kind: str, ref: str, reason: str
) -> None:
    manifest.setdefault("missing_refs", []).append(
        {"kind": kind, "ref": ref, "reason": reason}
    )


def _bundle_trace_view(
    root: Path,
    bundle_dir: Path,
    *,
    label: str,
    focus_ref: str,
    created_at: str,
) -> dict[str, Any]:
    trace_path = bundle_dir / "traceability" / f"{_safe_name(label)}_trace.yml"
    markdown_path = trace_path.with_suffix(".md")
    result = build_project_trace_view(
        root,
        focus_ref=focus_ref,
        output_path=trace_path,
        markdown_output_path=markdown_path,
        created_at=created_at,
    )
    return {
        "kind": "traceability_view",
        "label": label,
        "source": "ea.traceability.project_trace_view:v0.2",
        "generated": True,
        "status": result["status"],
        "focus_ref": focus_ref,
        "canonical_focus_ref": result.get("canonical_focus_ref"),
        "bundle_ref": trace_path.relative_to(bundle_dir).as_posix(),
        "markdown_bundle_ref": markdown_path.relative_to(bundle_dir).as_posix(),
        "trace_ref": result["trace_ref"],
        "markdown_ref": result["markdown_ref"],
        "node_count": result["node_count"],
        "edge_count": result["edge_count"],
        "missing_node_count": result["missing_node_count"],
        "boundaries": result["boundaries"],
    }


def _default_archive_path(bundle_dir: Path) -> Path:
    return bundle_dir.parent / f"{bundle_dir.name}.zip"


def _archive_checksum_path(archive_path: Path) -> Path:
    return archive_path.with_name(f"{archive_path.name}.sha256")


def _resolved_paths(paths: Iterable[Path | None]) -> set[Path]:
    return {path.resolve() for path in paths if path is not None}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


_MARKDOWN_IMAGE_RE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$")


def _dedupe_text(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value)
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _html_inline(text: str) -> str:
    escaped = html.escape(text, quote=False)
    escaped = re.sub(
        r"`([^`]+)`", lambda match: f"<code>{match.group(1)}</code>", escaped
    )
    escaped = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda match: (
            f'<a href="{html.escape(match.group(2), quote=True)}">{match.group(1)}</a>'
        ),
        escaped,
    )
    return escaped


def _data_uri_for_file(path: Path) -> str:
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{payload}"


def _resolve_report_image(root: Path, report_path: Path, image_ref: str) -> Path | None:
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", image_ref):
        return None
    clean_ref = image_ref.split(" ", 1)[0].strip()
    candidate = Path(clean_ref)
    if not candidate.is_absolute():
        candidate = report_path.parent / candidate
    candidate = candidate.resolve()
    return candidate if _is_inside(root, candidate) else None


def _render_markdown_image(
    root: Path,
    report_path: Path,
    image_ref: str,
    alt_text: str,
    *,
    embed_images: bool,
) -> str:
    image_path = _resolve_report_image(root, report_path, image_ref)
    original = html.escape(image_ref, quote=True)
    caption = _html_inline(alt_text or image_ref)
    if image_path and image_path.exists():
        src = (
            _data_uri_for_file(image_path)
            if embed_images
            else _project_ref(root, image_path)
        )
        return (
            '<figure class="report-figure inline-figure">'
            f'<img src="{html.escape(src, quote=True)}" alt="{html.escape(alt_text, quote=True)}">'
            f"<figcaption>{caption}<br><span>Original path: <code>{html.escape(_project_ref(root, image_path))}</code></span></figcaption>"
            "</figure>"
        )
    return (
        '<figure class="report-figure missing-figure">'
        f"<p>{caption}</p><p>Image link preserved but not embedded: <code>{original}</code></p>"
        "</figure>"
    )


def _split_table_row(line: str) -> list[str]:
    row = line.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    return [cell.strip() for cell in row.split("|")]


def _is_table_separator(line: str) -> bool:
    cells = _split_table_row(line)
    return bool(cells) and all(cell and set(cell) <= {"-", ":", " "} for cell in cells)


def _markdown_table_to_html(lines: list[str], start: int) -> tuple[str, int]:
    headers = _split_table_row(lines[start])
    rows: list[list[str]] = []
    index = start + 2
    while index < len(lines):
        line = lines[index]
        if "|" not in line or not line.strip():
            break
        rows.append(_split_table_row(line))
        index += 1
    header_html = "".join(f"<th>{_html_inline(header)}</th>" for header in headers)
    row_html = []
    for row in rows:
        row_html.append(
            "<tr>" + "".join(f"<td>{_html_inline(cell)}</td>" for cell in row) + "</tr>"
        )
    table = (
        "<table><thead><tr>"
        + header_html
        + "</tr></thead><tbody>"
        + "".join(row_html)
        + "</tbody></table>"
    )
    return table, index


def _markdown_body_to_html(
    root: Path, report_path: Path, body: str, *, embed_images: bool
) -> str:
    lines = body.splitlines()
    parts: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index].rstrip()
        stripped = line.strip()
        if not stripped:
            index += 1
            continue

        image = _MARKDOWN_IMAGE_RE.match(stripped)
        if image:
            parts.append(
                _render_markdown_image(
                    root,
                    report_path,
                    image.group(2),
                    image.group(1),
                    embed_images=embed_images,
                )
            )
            index += 1
            continue

        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            level = min(len(heading.group(1)) + 1, 6)
            parts.append(f"<h{level}>{_html_inline(heading.group(2))}</h{level}>")
            index += 1
            continue

        if (
            index + 1 < len(lines)
            and "|" in stripped
            and _is_table_separator(lines[index + 1])
        ):
            table, index = _markdown_table_to_html(lines, index)
            parts.append(table)
            continue

        if stripped.startswith("- "):
            items = []
            while index < len(lines) and lines[index].strip().startswith("- "):
                item_text = lines[index].strip()[2:]
                items.append(f"<li>{_html_inline(item_text)}</li>")
                index += 1
            parts.append("<ul>" + "".join(items) + "</ul>")
            continue

        paragraph = [stripped]
        index += 1
        while index < len(lines):
            next_line = lines[index].strip()
            if (
                not next_line
                or next_line.startswith("#")
                or next_line.startswith("- ")
                or _MARKDOWN_IMAGE_RE.match(next_line)
                or (
                    index + 1 < len(lines)
                    and "|" in next_line
                    and _is_table_separator(lines[index + 1])
                )
            ):
                break
            paragraph.append(next_line)
            index += 1
        parts.append(f"<p>{_html_inline(' '.join(paragraph))}</p>")
    return "\n".join(parts)


def _citation_check(
    body: str, numbered_references: list[dict[str, Any]]
) -> dict[str, Any]:
    body_without_code = re.sub(r"`[^`]*`", "", body)
    body_numbers = sorted(
        {
            int(number)
            for number in re.findall(r"(?<![A-Za-z0-9])\[(\d+)\]", body_without_code)
        }
    )
    reference_numbers = sorted(
        {
            int(record["number"])
            for record in numbered_references
            if isinstance(record, dict) and str(record.get("number") or "").isdigit()
        }
    )
    missing_numbers = [
        number for number in body_numbers if number not in reference_numbers
    ]
    status = "pass" if not missing_numbers else "warning"
    if body_numbers and not reference_numbers:
        status = "warning"
        missing_numbers = body_numbers
    return {
        "status": status,
        "body_numbers": body_numbers,
        "reference_numbers": reference_numbers,
        "missing_reference_numbers": missing_numbers,
    }


def _provenance_summary(
    provenance_id: str, record: dict[str, Any], provenance_ref: str
) -> dict[str, Any]:
    inputs = record.get("inputs") or {}
    outputs = record.get("outputs") or {}
    return {
        "provenance_id": provenance_id,
        "provenance_ref": provenance_ref,
        "workflow": record.get("workflow"),
        "created_at": record.get("created_at"),
        "input_record_count": len(inputs.get("records") or []),
        "input_file_count": len(inputs.get("files") or []),
        "output_record_count": len(outputs.get("records") or []),
        "output_file_count": len(outputs.get("files") or []),
        "review_refs": record.get("review_refs") or [],
        "source_refs": record.get("source_refs") or [],
        "warning_count": len(record.get("warnings") or []),
    }


def _yaml_pre(data: dict[str, Any]) -> str:
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    return html.escape(text, quote=False)


def _record_provenance_refs(root: Path, record_ref: str) -> list[str]:
    path = _project_path(root, record_ref)
    if not path.exists() or not _is_inside(root, path):
        return []
    try:
        if path.suffix.lower() in {".md", ".markdown"}:
            frontmatter, _ = read_markdown_record(path)
            return [str(ref) for ref in frontmatter.get("provenance_refs") or []]
        data = read_yaml(path)
        return [str(ref) for ref in data.get("provenance_refs") or []]
    except Exception:
        return []


def _expand_provenance_refs(root: Path, provenance_refs: Iterable[str]) -> list[str]:
    ordered = _dedupe_text(provenance_refs)
    seen = set(ordered)
    queue = list(ordered)
    while queue and len(ordered) < 100:
        provenance_ref = queue.pop(0)
        provenance_path = _provenance_path(root, provenance_ref)
        if not provenance_path.exists() or not _is_inside(root, provenance_path):
            continue
        provenance = read_yaml(provenance_path)
        inputs = provenance.get("inputs") or {}
        outputs = provenance.get("outputs") or {}
        for record_ref in [
            *(inputs.get("records") or []),
            *(outputs.get("records") or []),
        ]:
            for linked_ref in _record_provenance_refs(root, str(record_ref)):
                if linked_ref in seen:
                    continue
                seen.add(linked_ref)
                ordered.append(linked_ref)
                queue.append(linked_ref)
    return ordered


def _language_labels(language: str | None) -> dict[str, str]:
    if language == "zh":
        return {
            "title": "EA 报告导出",
            "canonical": "规范 Markdown 报告",
            "report_meta": "报告元数据",
            "figures": "图件",
            "source_data": "图源数据",
            "references": "参考文献记录",
            "provenance": "溯源摘要",
            "audit": "审计附录",
            "no_references": "本报告未登记外部参考文献。",
        }
    return {
        "title": "EA Friendly Report Export",
        "canonical": "Canonical Markdown report",
        "report_meta": "Report Metadata",
        "figures": "Figures",
        "source_data": "Figure source data",
        "references": "Reference Records",
        "provenance": "Provenance Summary",
        "audit": "Audit Appendix",
        "no_references": "No registered external references are linked to this report.",
    }


def _normalized_figure_source_data(figure: dict[str, Any]) -> list[dict[str, Any]]:
    source_data = [
        dict(item) for item in figure.get("source_data") or [] if isinstance(item, dict)
    ]
    if source_data:
        return source_data
    return [
        {
            "ref": str(ref),
            "role": "legacy_unspecified",
            "purpose": "Legacy source-data reference.",
            "columns": [],
            "primary": index == 0,
            "protected_raw": False,
        }
        for index, ref in enumerate(figure.get("source_data_refs") or [])
    ]


def _source_data_purpose_html(item: dict[str, Any], language: str) -> str:
    return localized_source_data_purpose(item, language)


def _render_figure_source_data_html(
    figure: dict[str, Any], label: str, language: str
) -> str:
    items = []
    for item in figure.get("source_data") or []:
        ref = str(item.get("ref") or "")
        purpose = _source_data_purpose_html(item, language)
        href = item.get("href")
        if item.get("protected_raw"):
            protected_label = (
                "受保护原始数据（未链接）"
                if language == "zh"
                else "Protected raw data (not linked)"
            )
            items.append(
                f"<li><span class=\"missing\">{html.escape(protected_label)}</span>"
                f" — {html.escape(purpose)}</li>"
            )
            continue
        display_name = Path(ref).name or ("缺失文件" if language == "zh" else "missing file")
        if href:
            ref_html = f'<a href="{html.escape(str(href), quote=True)}">{html.escape(display_name)}</a>'
        else:
            missing = "（链接不可用）" if language == "zh" else " (not linked)"
            ref_html = f'{html.escape(display_name)} <span class="missing">{missing}</span>'
        items.append(
            "<li>"
            + ref_html
            + f" — {html.escape(purpose)}"
            + "</li>"
        )
    if not items:
        missing = (
            "未登记可公开链接的处理数据。"
            if language == "zh"
            else "No public-safe processed source data is registered."
        )
        items.append(
            f'<li><span class="missing">{html.escape(missing)}</span></li>'
        )
    return f'<div class="figure-source-data"><strong>{html.escape(label)}</strong><ul>{"".join(items)}</ul></div>'


def _without_standard_figure_section(body: str) -> str:
    return re.sub(
        r"(?ms)^##\s+(?:图件|Figures)\s*$.*?(?=^##\s+|\Z)",
        "",
        body,
    ).strip()


def _render_report_html_document(
    *,
    root: Path,
    report_path: Path,
    frontmatter: dict[str, Any],
    body: str,
    manifest: dict[str, Any],
    figures: list[dict[str, Any]],
    references: list[dict[str, Any]],
    provenance_records: list[dict[str, Any]],
    embed_images: bool,
) -> str:
    labels = _language_labels(str(frontmatter.get("language") or ""))
    language = str(frontmatter.get("language") or "en")
    report_id = str(frontmatter.get("report_id") or manifest["report_id"])
    canonical_ref = manifest["canonical_report_ref"]
    body_html = _markdown_body_to_html(
        root,
        report_path,
        _without_standard_figure_section(body),
        embed_images=embed_images,
    )

    figure_parts = []
    for figure in figures:
        caption = localized_figure_caption(figure, language)
        image_src = figure.get("html_src")
        if image_src:
            image_html = f'<img src="{html.escape(image_src, quote=True)}" alt="{html.escape(str(caption), quote=True)}">'
        else:
            image_html = (
                '<p class="missing">'
                + (
                    "导出时未找到图件文件。"
                    if language == "zh"
                    else "Figure file was not found during export."
                )
                + "</p>"
            )
        report_id_label = "报告 ID" if language == "zh" else "Report ID"
        figure_parts.append(
            '<figure class="report-figure">'
            + image_html
            + "<figcaption>"
            + f"<strong>{html.escape(str(figure['figure_id']))}</strong>: {_html_inline(str(caption))}"
            + f"<br><span>{report_id_label}: <code>{html.escape(str(figure.get('report_id') or report_id))}</code></span>"
            + _render_figure_source_data_html(
                figure, labels["source_data"], language
            )
            + "</figcaption></figure>"
        )

    if references:
        reference_items = []
        for reference in references:
            label = (
                f"[{reference['number']}]"
                if reference.get("number")
                else reference["reference_id"]
            )
            detail = str(reference.get("citation") or reference.get("entry") or "")
            extras = []
            if reference.get("doi"):
                extras.append(f"DOI: {reference['doi']}")
            if reference.get("url"):
                extras.append(f"URL: {reference['url']}")
            reference_items.append(
                "<li>"
                + f"<strong>{html.escape(str(label))}</strong> "
                + _html_inline(detail)
                + (
                    f"<br><span>{_html_inline(' | '.join(extras))}</span>"
                    if extras
                    else ""
                )
                + f"<br><span>Reference ID: <code>{html.escape(str(reference['reference_id']))}</code></span>"
                + "</li>"
            )
        references_html = "<ol>" + "".join(reference_items) + "</ol>"
    else:
        references_html = f"<p>{html.escape(labels['no_references'])}</p>"

    provenance_rows = []
    provenance_details = []
    for record in provenance_records:
        summary = record["summary"]
        provenance_rows.append(
            "<tr>"
            + f"<td><code>{html.escape(str(summary['provenance_id']))}</code></td>"
            + f"<td>{html.escape(str(summary.get('workflow') or ''))}</td>"
            + f"<td>{html.escape(str(summary.get('created_at') or ''))}</td>"
            + f"<td>{summary['input_record_count']} records / {summary['input_file_count']} files</td>"
            + f"<td>{summary['output_record_count']} records / {summary['output_file_count']} files</td>"
            + f"<td>{len(summary['review_refs'])}</td>"
            + "</tr>"
        )
        provenance_details.append(
            "<details>"
            + f"<summary><code>{html.escape(str(summary['provenance_id']))}</code> {html.escape(str(summary.get('workflow') or ''))}</summary>"
            + f"<pre>{_yaml_pre(record['record'])}</pre>"
            + "</details>"
        )
    provenance_html = (
        "<table><thead><tr><th>Provenance</th><th>Workflow</th><th>Created</th><th>Inputs</th><th>Outputs</th><th>Review refs</th></tr></thead>"
        + "<tbody>"
        + "".join(provenance_rows)
        + "</tbody></table>"
        if provenance_rows
        else "<p>No provenance records were linked in the report frontmatter or result metadata.</p>"
    )

    audit_intro = (
        "Detailed provenance, raw hashes, processing parameters, review refs, source refs, warnings, and scripts are preserved here for audit. "
        "This section is copied from local EA records and does not add new scientific interpretation."
    )
    metadata_items = [
        ("Report ID", report_id),
        ("Project ID", frontmatter.get("project_id")),
        ("Report type", frontmatter.get("report_type")),
        ("Status", frontmatter.get("status")),
        ("Created", frontmatter.get("created_at")),
        ("HTML export sidecar", manifest["metadata_ref"]),
    ]
    metadata_html = (
        "<dl>"
        + "".join(
            f"<dt>{html.escape(label)}</dt><dd><code>{html.escape(str(value or ''))}</code></dd>"
            for label, value in metadata_items
        )
        + "</dl>"
    )

    css = """
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.55; margin: 0; color: #202124; background: #f7f7f4; }
header, main, section { max-width: 980px; margin: 0 auto; padding: 24px; background: #fff; }
header { margin-top: 24px; border-bottom: 1px solid #d8d8d2; }
main, section { border-top: 1px solid #ecece6; }
h1, h2, h3, h4 { line-height: 1.25; }
code, pre { font-family: "SFMono-Regular", Consolas, monospace; }
pre { overflow-x: auto; padding: 12px; background: #f3f3ee; border: 1px solid #deded6; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 0.94rem; }
th, td { border: 1px solid #d9d9d2; padding: 7px 8px; vertical-align: top; }
th { background: #f0f0ea; text-align: left; }
.report-figure { margin: 18px 0; }
.report-figure img { max-width: 100%; height: auto; border: 1px solid #d8d8d2; background: #fff; }
figcaption, span, .note { color: #5f6368; font-size: 0.92rem; }
.missing { color: #a33; }
dl { display: grid; grid-template-columns: minmax(140px, 220px) 1fr; gap: 6px 16px; }
dt { font-weight: 700; color: #3c4043; }
details { margin: 12px 0; }
"""
    document_language = "zh-CN" if language == "zh" else "en"
    citation_check_label = "引用校验" if language == "zh" else "Citation check"
    audit_html = (
        f"<section><h2>{html.escape(labels['audit'])}</h2>"
        f"<p>{html.escape(audit_intro)}</p>{''.join(provenance_details)}</section>\n"
        if any(record.get("record") for record in provenance_records)
        else ""
    )
    figures_html = (
        f"<section><h2>{html.escape(labels['figures'])}</h2>"
        f"{''.join(figure_parts)}</section>\n"
        if figure_parts
        else ""
    )
    return (
        f'<!doctype html>\n<html lang="{document_language}">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<meta name="ea-report-id" content="{html.escape(report_id, quote=True)}">\n'
        f'<meta name="ea-canonical-report" content="{html.escape(str(canonical_ref), quote=True)}">\n'
        f"<title>{html.escape(report_id)} - {html.escape(labels['title'])}</title>\n"
        f"<style>{css}</style>\n</head>\n<body>\n"
        f'<header><h1>{html.escape(report_id)}</h1><p class="note">{html.escape(labels["canonical"])}: <code>{html.escape(str(canonical_ref))}</code></p></header>\n'
        f"<section><h2>{html.escape(labels['report_meta'])}</h2>{metadata_html}</section>\n"
        f"<main>{body_html}</main>\n"
        f"{figures_html}"
        f'<section><h2>{html.escape(labels["references"])}</h2>{references_html}<p class="note">{citation_check_label}: <code>{html.escape(manifest["citation_check"]["status"])}</code></p></section>\n'
        f"<section><h2>{html.escape(labels['provenance'])}</h2>{provenance_html}</section>\n"
        f"{audit_html}"
        "</body>\n</html>\n"
    )


def export_report_html(
    root: Path,
    *,
    report_id: str,
    output_path: Path | None = None,
    created_at: str | None = None,
    embed_images: bool = True,
    include_audit: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    reports = _reports_index(root)
    report_record = reports.get(report_id)
    if not report_record:
        raise ReportBundleError(f"Unknown report_id: {report_id}")

    report_ref = str(report_record.get("path") or "")
    report_path = _project_path(root, report_ref)
    if not report_ref or not report_path.exists():
        raise ReportBundleError(
            f"Report file is missing for report_id {report_id}: {report_ref}"
        )
    if not _is_inside(root, report_path):
        raise ReportBundleError(f"Report file is outside project root: {report_ref}")

    output_path = output_path or root / "exports" / "user-reports" / f"{report_id}.html"
    if not output_path.is_absolute():
        output_path = root / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path = output_path.with_suffix(f"{output_path.suffix}.yml")

    frontmatter, body = read_markdown_record(report_path)
    created = created_at or EARecord.now_iso()
    missing_refs: list[dict[str, Any]] = []

    figures_index = _figures_index(root)
    figure_ids = _dedupe_text(
        [
            *(report_record.get("figure_ids") or []),
            *(frontmatter.get("figure_ids") or []),
        ]
    )
    figures: list[dict[str, Any]] = []
    for figure_id in figure_ids:
        figure = figures_index.get(figure_id)
        if not figure:
            missing_refs.append(
                {
                    "kind": "figure_record",
                    "ref": figure_id,
                    "reason": "unknown_figure_id",
                }
            )
            figures.append(
                {
                    "figure_id": figure_id,
                    "embedded": False,
                    "html_src": None,
                    "missing": True,
                }
            )
            continue
        figure_ref = figure_path_for_report(figure, report_id)
        figure_path = _project_path(root, figure_ref)
        html_src = None
        embedded = False
        if figure_ref and figure_path.exists() and _is_inside(root, figure_path):
            html_src = (
                _data_uri_for_file(figure_path)
                if embed_images
                else _project_ref(root, figure_path)
            )
            embedded = embed_images
        else:
            missing_refs.append(
                {
                    "kind": "figure_file",
                    "ref": figure_ref or figure_id,
                    "reason": "missing_or_outside_project_root",
                }
            )
        source_data = _normalized_figure_source_data(figure)
        for item in source_data:
            ref = str(item.get("ref") or "")
            source_path = _project_path(root, ref)
            if item.get("protected_raw"):
                item["href"] = None
                item["link_status"] = "protected_raw_omitted"
            elif ref and source_path.is_file() and _is_inside(root, source_path):
                item["href"] = Path(
                    os.path.relpath(source_path, output_path.parent)
                ).as_posix()
                item["link_status"] = "available"
            else:
                item["href"] = None
                item["link_status"] = "missing_or_outside_project_root"
                missing_refs.append(
                    {
                        "kind": "source_data",
                        "ref": ref or figure_id,
                        "reason": item["link_status"],
                    }
                )
        figures.append(
            {
                "figure_id": figure_id,
                "path": str(figure_path),
                "original_path": figure_ref,
                "report_id": report_id,
                "result_id": figure.get("result_id"),
                "caption": figure.get("caption"),
                "caption_key": figure.get("caption_key"),
                "purpose": figure.get("purpose"),
                "source_data_refs": figure.get("source_data_refs") or [],
                "source_data": source_data,
                "generation": figure.get("generation") or {},
                "embedded": embedded,
                "html_src": html_src,
                "missing": html_src is None,
            }
        )

    numbered_references = [
        item
        for item in frontmatter.get("numbered_references") or []
        if isinstance(item, dict)
    ]
    reference_numbers = {
        str(item.get("reference_id")): item.get("number")
        for item in numbered_references
    }
    reference_entries = {
        str(item.get("reference_id")): item.get("entry") for item in numbered_references
    }
    references_index = _reference_index(root)
    reference_ids = _dedupe_text(
        [
            *(report_record.get("reference_ids") or []),
            *(frontmatter.get("reference_ids") or []),
        ]
    )
    references: list[dict[str, Any]] = []
    for reference_id in reference_ids:
        reference_record = references_index.get(reference_id)
        if not reference_record:
            missing_refs.append(
                {
                    "kind": "reference_record",
                    "ref": reference_id,
                    "reason": "unknown_reference_id",
                }
            )
            references.append(
                {
                    "reference_id": reference_id,
                    "number": reference_numbers.get(reference_id),
                    "missing": True,
                }
            )
            continue
        record_ref = str(
            reference_record.get("path") or f"literature/references/{reference_id}.yml"
        )
        record_path = _project_path(root, record_ref)
        reference_data = (
            read_yaml(record_path)
            if record_path.exists() and _is_inside(root, record_path)
            else {}
        )
        if not reference_data:
            missing_refs.append(
                {
                    "kind": "reference_record",
                    "ref": record_ref,
                    "reason": "missing_or_outside_project_root",
                }
            )
        references.append(
            {
                "reference_id": reference_id,
                "number": reference_numbers.get(reference_id),
                "entry": reference_entries.get(reference_id),
                "path": record_ref,
                "citation": reference_data.get("citation")
                or reference_record.get("citation"),
                "doi": reference_data.get("doi") or reference_record.get("doi"),
                "url": reference_data.get("url") or reference_record.get("url"),
                "local_path": reference_data.get("local_path")
                or reference_record.get("local_path"),
                "missing": not bool(reference_data),
            }
        )

    result_index = _result_metadata_index(root)
    result_provenance_refs: list[str] = []
    for result_id in (
        report_record.get("result_ids") or frontmatter.get("related_results") or []
    ):
        result_path = result_index.get(str(result_id))
        if not result_path:
            missing_refs.append(
                {
                    "kind": "result_metadata",
                    "ref": str(result_id),
                    "reason": "unknown_result_id",
                }
            )
            continue
        result_data = read_yaml(result_path)
        result_provenance_refs.extend(
            str(ref) for ref in result_data.get("provenance_refs") or []
        )

    provenance_refs = _expand_provenance_refs(
        root, [*(frontmatter.get("provenance_refs") or []), *result_provenance_refs]
    )
    provenance_records: list[dict[str, Any]] = []
    for provenance_ref in provenance_refs:
        provenance_path = _provenance_path(root, provenance_ref)
        if not provenance_path.exists() or not _is_inside(root, provenance_path):
            missing_refs.append(
                {
                    "kind": "provenance_record",
                    "ref": provenance_ref,
                    "reason": "missing_or_outside_project_root",
                }
            )
            continue
        provenance = read_yaml(provenance_path)
        provenance_id = str(provenance.get("provenance_id") or provenance_ref)
        provenance_records.append(
            {
                "provenance_id": provenance_id,
                "provenance_ref": _project_ref(root, provenance_path),
                "summary": _provenance_summary(
                    provenance_id, provenance, _project_ref(root, provenance_path)
                ),
                "record": provenance if include_audit else {},
            }
        )

    manifest: dict[str, Any] = {
        "schema_version": "0.2",
        "export_type": "friendly_report_html",
        "export_id": f"html-{report_id}",
        "created_at": created,
        "status": "complete" if not missing_refs else "warning",
        "workspace": str(root),
        "report_id": report_id,
        "canonical_report_ref": _project_ref(root, report_path),
        "canonical_report_path": str(report_path),
        "html_path": str(output_path),
        "html_ref": _project_ref(root, output_path),
        "metadata_path": str(metadata_path),
        "metadata_ref": _project_ref(root, metadata_path),
        "embed_images": embed_images,
        "include_audit": include_audit,
        "figures": [
            {key: value for key, value in figure.items() if key != "html_src"}
            for figure in figures
        ],
        "references": references,
        "provenance": [record["summary"] for record in provenance_records],
        "citation_check": _citation_check(body, numbered_references),
        "missing_refs": missing_refs,
        "boundaries": [
            "HTML export is a user-readable rendering of an indexed canonical Markdown report.",
            "It does not mutate the canonical Markdown report, regenerate analysis, create ReviewRecords, commit memory, register references, download literature, or prove scientific conclusions.",
            "Detailed provenance, raw hashes, processing parameters, and review refs stay in the audit appendix and sidecar metadata.",
        ],
    }

    html_text = _render_report_html_document(
        root=root,
        report_path=report_path,
        frontmatter=frontmatter,
        body=body,
        manifest=manifest,
        figures=figures,
        references=references,
        provenance_records=provenance_records,
        embed_images=embed_images,
    )
    output_path.write_text(html_text, encoding="utf-8")
    write_yaml(metadata_path, manifest)
    return manifest


def _write_zip_archive(
    bundle_dir: Path, archive_path: Path, *, exclude_paths: Iterable[Path | None] = ()
) -> Path:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    excluded = _resolved_paths([archive_path, *exclude_paths])
    if archive_path.exists():
        archive_path.unlink()
    with zipfile.ZipFile(archive_path, "w") as archive:
        for path in sorted(item for item in bundle_dir.rglob("*") if item.is_file()):
            if path.resolve() in excluded:
                continue
            zip_info = zipfile.ZipInfo(path.relative_to(bundle_dir).as_posix())
            zip_info.date_time = (1980, 1, 1, 0, 0, 0)
            zip_info.compress_type = zipfile.ZIP_DEFLATED
            zip_info.external_attr = 0o644 << 16
            archive.writestr(zip_info, path.read_bytes())
    return archive_path


def _write_archive_checksum(archive_path: Path, checksum_path: Path) -> Path:
    checksum_path.parent.mkdir(parents=True, exist_ok=True)
    checksum_path.write_text(
        f"{_sha256_file(archive_path)}  {archive_path.name}\n", encoding="utf-8"
    )
    return checksum_path


def _write_bundle_checksums(
    root: Path,
    bundle_dir: Path,
    manifest: dict[str, Any],
    *,
    exclude_paths: Iterable[Path | None] = (),
) -> Path:
    checksum_path = bundle_dir / "bundle_checksums.yml"
    excluded = _resolved_paths([checksum_path, *exclude_paths])
    files = []
    for path in sorted(item for item in bundle_dir.rglob("*") if item.is_file()):
        if path.resolve() in excluded:
            continue
        files.append(
            {
                "path": path.relative_to(bundle_dir).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    checksum_manifest = {
        "schema_version": "0.2",
        "checksum_manifest_id": f"checksums-{manifest['bundle_id']}",
        "bundle_id": manifest["bundle_id"],
        "created_at": manifest["created_at"],
        "algorithm": "sha256",
        "bundle_path": str(bundle_dir),
        "checksum_manifest_path": str(checksum_path),
        "checksum_manifest_ref": _project_ref(root, checksum_path),
        "excluded_paths": sorted(
            path.relative_to(bundle_dir).as_posix()
            for path in (bundle_dir / rel for rel in ["bundle_checksums.yml"])
            if path.resolve() in excluded
        ),
        "files": files,
    }
    write_yaml(checksum_path, checksum_manifest)
    return checksum_path


def verify_bundle_checksums(bundle_dir: Path) -> dict[str, Any]:
    bundle_dir = bundle_dir.resolve()
    checksum_path = bundle_dir / "bundle_checksums.yml"
    result: dict[str, Any] = {
        "schema_version": "0.2",
        "check_type": "bundle",
        "status": "pass",
        "bundle_path": str(bundle_dir),
        "checksum_manifest_path": str(checksum_path),
        "algorithm": "sha256",
        "checked_count": 0,
        "failures": [],
    }
    if not bundle_dir.is_dir():
        result["status"] = "fail"
        result["failures"].append(
            {"path": str(bundle_dir), "reason": "missing_bundle_dir"}
        )
        return result
    if not checksum_path.exists():
        result["status"] = "fail"
        result["failures"].append(
            {"path": "bundle_checksums.yml", "reason": "missing_checksum_manifest"}
        )
        return result

    checksum_manifest = read_yaml(checksum_path)
    algorithm = str(checksum_manifest.get("algorithm") or "")
    result["algorithm"] = algorithm
    if algorithm != "sha256":
        result["status"] = "fail"
        result["failures"].append(
            {
                "path": "bundle_checksums.yml",
                "reason": "unsupported_algorithm",
                "algorithm": algorithm,
            }
        )
        return result

    bundle_manifest_path = bundle_dir / "bundle_manifest.yml"
    if bundle_manifest_path.is_file():
        bundle_manifest = read_yaml(bundle_manifest_path)
        for missing in bundle_manifest.get("missing_refs") or []:
            result["failures"].append(
                {
                    "path": str(missing.get("ref") or "bundle_manifest.yml"),
                    "reason": f"manifest_{missing.get('reason') or 'missing_ref'}",
                    "kind": missing.get("kind"),
                }
            )
        for artifact in (bundle_manifest.get("artifacts") or {}).get(
            "source_data"
        ) or []:
            bundle_ref = str(artifact.get("bundle_ref") or "")
            if artifact.get("copied") and (
                not bundle_ref or not _is_inside(bundle_dir, bundle_dir / bundle_ref)
            ):
                result["failures"].append(
                    {
                        "path": bundle_ref,
                        "reason": "source_data_outside_bundle",
                        "kind": "source_data",
                    }
                )

    for entry in checksum_manifest.get("files") or []:
        ref = str(entry.get("path") or "")
        file_path = bundle_dir / ref
        expected_size = entry.get("size_bytes")
        expected_sha = str(entry.get("sha256") or "")
        if not ref or not _is_inside(bundle_dir, file_path):
            result["failures"].append({"path": ref, "reason": "outside_bundle"})
            continue
        if not file_path.exists():
            result["failures"].append({"path": ref, "reason": "missing_file"})
            continue
        result["checked_count"] += 1
        actual_size = file_path.stat().st_size
        actual_sha = _sha256_file(file_path)
        if expected_size != actual_size:
            result["failures"].append(
                {
                    "path": ref,
                    "reason": "size_mismatch",
                    "expected_size_bytes": expected_size,
                    "actual_size_bytes": actual_size,
                }
            )
        if expected_sha != actual_sha:
            result["failures"].append(
                {
                    "path": ref,
                    "reason": "sha256_mismatch",
                    "expected_sha256": expected_sha,
                    "actual_sha256": actual_sha,
                }
            )
    result["status"] = "pass" if not result["failures"] else "fail"
    return result


def verify_archive_checksum(
    archive_path: Path, checksum_path: Path | None = None
) -> dict[str, Any]:
    archive_path = archive_path.resolve()
    checksum_path = (checksum_path or _archive_checksum_path(archive_path)).resolve()
    result: dict[str, Any] = {
        "schema_version": "0.2",
        "check_type": "archive",
        "status": "pass",
        "archive_path": str(archive_path),
        "checksum_path": str(checksum_path),
        "algorithm": "sha256",
        "failures": [],
    }
    if not archive_path.exists():
        result["status"] = "fail"
        result["failures"].append(
            {"path": str(archive_path), "reason": "missing_archive"}
        )
        return result
    if not checksum_path.exists():
        result["status"] = "fail"
        result["failures"].append(
            {"path": str(checksum_path), "reason": "missing_archive_checksum"}
        )
        return result
    sidecar = checksum_path.read_text(encoding="utf-8").strip().split()
    if not sidecar:
        result["status"] = "fail"
        result["failures"].append(
            {"path": str(checksum_path), "reason": "empty_archive_checksum"}
        )
        return result
    expected_sha = sidecar[0]
    actual_sha = _sha256_file(archive_path)
    result["expected_sha256"] = expected_sha
    result["actual_sha256"] = actual_sha
    if expected_sha != actual_sha:
        result["status"] = "fail"
        result["failures"].append(
            {
                "path": str(archive_path),
                "reason": "sha256_mismatch",
                "expected_sha256": expected_sha,
                "actual_sha256": actual_sha,
            }
        )
    return result


def _copy_provenance(
    root: Path,
    bundle_dir: Path,
    manifest: dict[str, Any],
    provenance_refs: list[str],
) -> list[dict[str, Any]]:
    copied = []
    seen = set()
    for provenance_ref in provenance_refs:
        if provenance_ref in seen:
            continue
        seen.add(provenance_ref)
        provenance_path = _provenance_path(root, provenance_ref)
        record = _copy_project_file(
            root,
            bundle_dir,
            ref=_project_ref(root, provenance_path),
            subdir="provenance",
            kind="provenance_record",
            label=provenance_ref,
        )
        copied.append(record)
        if not record["copied"]:
            _record_missing(
                manifest,
                kind="provenance_record",
                ref=provenance_ref,
                reason=str(record.get("skip_reason")),
            )
            continue
        provenance = read_yaml(provenance_path)
        inputs = provenance.get("inputs") or {}
        for input_ref in list(inputs.get("records") or []) + list(
            inputs.get("files") or []
        ):
            input_record = _copy_project_file(
                root,
                bundle_dir,
                ref=str(input_ref),
                subdir="provenance-inputs",
                kind="provenance_input",
                label=provenance_ref,
            )
            manifest.setdefault("provenance_inputs", []).append(input_record)
            if not input_record["copied"]:
                _record_missing(
                    manifest,
                    kind="provenance_input",
                    ref=str(input_ref),
                    reason=str(input_record.get("skip_reason")),
                )
    return copied


def _report_id_from_ref(root: Path, report_ref: str) -> str | None:
    report_path = _project_path(root, report_ref)
    if not report_path.exists():
        return None
    frontmatter, _ = read_markdown_record(report_path)
    report_id = frontmatter.get("report_id")
    return str(report_id) if report_id else None


def export_report_bundle(
    root: Path,
    *,
    report_id: str,
    output_dir: Path | None = None,
    created_at: str | None = None,
    create_archive: bool = False,
    archive_path: Path | None = None,
    include_trace: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    reports = _reports_index(root)
    report_record = reports.get(report_id)
    if not report_record:
        raise ReportBundleError(f"Unknown report_id: {report_id}")

    bundle_dir = output_dir or root / "exports" / "report-bundles" / report_id
    if not bundle_dir.is_absolute():
        bundle_dir = root / bundle_dir
    bundle_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "schema_version": "0.2",
        "bundle_id": f"bundle-{report_id}",
        "report_id": report_id,
        "created_at": created_at or EARecord.now_iso(),
        "workspace": str(root),
        "bundle_path": str(bundle_dir),
        "artifacts": {
            "reports": [],
            "figures": [],
            "source_data": [],
            "results": [],
            "references": [],
            "reference_files": [],
            "provenance": [],
            "traceability": [],
        },
        "trace_export": {
            "included": include_trace,
            "focus_ref": None,
            "strategy": "focused_report_trace_view"
            if include_trace
            else "not_requested",
            "boundaries": [
                "Trace export writes audit YAML/Markdown into the bundle only.",
                "It does not mutate reports, create ReviewRecords, commit memory, register references, inject citations, generate source packets/suggestions, or prove scientific conclusions.",
            ],
        },
        "provenance_inputs": [],
        "missing_refs": [],
        "archive_created": False,
        "archive_path": None,
        "archive_ref": None,
        "archive_checksum_path": None,
        "archive_checksum_ref": None,
        "checksum_manifest_path": None,
        "checksum_manifest_ref": None,
        "checksum_manifest_bundle_ref": None,
    }

    report_ref = str(report_record.get("path") or "")
    manifest["trace_export"]["focus_ref"] = report_ref or None
    report_copy = _copy_project_file(
        root,
        bundle_dir,
        ref=report_ref,
        subdir="reports",
        kind="report",
        label=report_id,
    )
    manifest["artifacts"]["reports"].append(report_copy)
    report_frontmatter: dict[str, Any] = {}
    if report_copy["copied"]:
        report_frontmatter, _ = read_markdown_record(_project_path(root, report_ref))
    else:
        _record_missing(
            manifest,
            kind="report",
            ref=report_ref,
            reason=str(report_copy.get("skip_reason")),
        )

    result_index = _result_metadata_index(root)
    for result_id in report_record.get("result_ids") or []:
        result_path = result_index.get(str(result_id))
        if not result_path:
            _record_missing(
                manifest,
                kind="result_metadata",
                ref=str(result_id),
                reason="unknown_result_id",
            )
            continue
        result_ref = _project_ref(root, result_path)
        result_copy = _copy_project_file(
            root,
            bundle_dir,
            ref=result_ref,
            subdir="results",
            kind="result_metadata",
            label=str(result_id),
        )
        manifest["artifacts"]["results"].append(result_copy)
        if result_copy["copied"]:
            result_data = read_yaml(result_path)
            for provenance_ref in result_data.get("provenance_refs") or []:
                manifest["artifacts"]["provenance"].extend(
                    _copy_provenance(root, bundle_dir, manifest, [str(provenance_ref)])
                )

    figures = _figures_index(root)
    seen_source_refs: set[str] = set()
    for figure_id in report_record.get("figure_ids") or []:
        figure = figures.get(str(figure_id))
        if not figure:
            _record_missing(
                manifest,
                kind="figure_record",
                ref=str(figure_id),
                reason="unknown_figure_id",
            )
            continue
        figure_ref = figure_path_for_report(figure, report_id)
        figure_copy = _copy_project_file(
            root,
            bundle_dir,
            ref=figure_ref,
            subdir="figures",
            kind="figure_file",
            label=str(figure_id),
        )
        figure_copy["figure_record"] = figure
        manifest["artifacts"]["figures"].append(figure_copy)
        if not figure_copy["copied"]:
            _record_missing(
                manifest,
                kind="figure_file",
                ref=str(figure_id),
                reason=str(figure_copy.get("skip_reason")),
            )
        for source_entry in _normalized_figure_source_data(figure):
            if source_entry.get("protected_raw"):
                continue
            source_ref = str(source_entry.get("ref") or "")
            if source_ref in seen_source_refs:
                continue
            seen_source_refs.add(source_ref)
            source_copy = _copy_project_file(
                root,
                bundle_dir,
                ref=source_ref,
                subdir="source-data",
                kind="source_data",
                label=str(figure_id),
            )
            source_copy["source_data"] = source_entry
            manifest["artifacts"]["source_data"].append(source_copy)
            if not source_copy["copied"]:
                _record_missing(
                    manifest,
                    kind="source_data",
                    ref=source_ref,
                    reason=str(source_copy.get("skip_reason")),
                )

    references = _reference_index(root)
    for reference_id in (
        report_record.get("reference_ids")
        or report_frontmatter.get("reference_ids")
        or []
    ):
        reference = references.get(str(reference_id))
        if not reference:
            _record_missing(
                manifest,
                kind="reference_record",
                ref=str(reference_id),
                reason="unknown_reference_id",
            )
            continue
        record_ref = str(
            reference.get("path") or f"literature/references/{reference_id}.yml"
        )
        reference_copy = _copy_project_file(
            root,
            bundle_dir,
            ref=record_ref,
            subdir="references",
            kind="reference_record",
            label=str(reference_id),
        )
        manifest["artifacts"]["references"].append(reference_copy)
        if not reference_copy["copied"]:
            _record_missing(
                manifest,
                kind="reference_record",
                ref=str(reference_id),
                reason=str(reference_copy.get("skip_reason")),
            )
            continue
        reference_data = read_yaml(_project_path(root, record_ref))
        local_path = reference_data.get("local_path")
        if local_path:
            file_copy = _copy_project_file(
                root,
                bundle_dir,
                ref=str(local_path),
                subdir="references/files",
                kind="reference_file",
                label=str(reference_id),
            )
            manifest["artifacts"]["reference_files"].append(file_copy)
            if not file_copy["copied"]:
                _record_missing(
                    manifest,
                    kind="reference_file",
                    ref=str(local_path),
                    reason=str(file_copy.get("skip_reason")),
                )

    report_provenance_refs = [
        str(item) for item in report_frontmatter.get("provenance_refs") or []
    ]
    manifest["artifacts"]["provenance"].extend(
        _copy_provenance(root, bundle_dir, manifest, report_provenance_refs)
    )

    if include_trace and report_ref:
        trace_record = _bundle_trace_view(
            root,
            bundle_dir,
            label=report_id,
            focus_ref=report_ref,
            created_at=str(manifest["created_at"]),
        )
        manifest["artifacts"]["traceability"].append(trace_record)
        manifest["trace_export"]["trace_bundle_ref"] = trace_record["bundle_ref"]
        manifest["trace_export"]["markdown_bundle_ref"] = trace_record[
            "markdown_bundle_ref"
        ]
        manifest["trace_export"]["canonical_focus_ref"] = trace_record.get(
            "canonical_focus_ref"
        )

    manifest["status"] = "complete" if not manifest["missing_refs"] else "warning"
    archive_target: Path | None = None
    archive_checksum: Path | None = None
    if create_archive:
        archive_target = archive_path or _default_archive_path(bundle_dir)
        if not archive_target.is_absolute():
            archive_target = root / archive_target
        archive_checksum = _archive_checksum_path(archive_target)
        manifest["archive_created"] = True
        manifest["archive_path"] = str(archive_target)
        manifest["archive_ref"] = _project_ref(root, archive_target)
        manifest["archive_checksum_path"] = str(archive_checksum)
        manifest["archive_checksum_ref"] = _project_ref(root, archive_checksum)

    manifest_path = bundle_dir / "bundle_manifest.yml"
    manifest["manifest_path"] = str(manifest_path)
    checksum_path = bundle_dir / "bundle_checksums.yml"
    manifest["checksum_manifest_path"] = str(checksum_path)
    manifest["checksum_manifest_ref"] = _project_ref(root, checksum_path)
    manifest["checksum_manifest_bundle_ref"] = checksum_path.relative_to(
        bundle_dir
    ).as_posix()
    write_yaml(manifest_path, manifest)
    _write_bundle_checksums(
        root, bundle_dir, manifest, exclude_paths=[archive_target, archive_checksum]
    )
    if create_archive:
        try:
            _write_zip_archive(
                bundle_dir, archive_target, exclude_paths=[archive_checksum]
            )
            _write_archive_checksum(archive_target, archive_checksum)
        except OSError as exc:
            raise ReportBundleError(
                f"Failed to create report bundle archive: {archive_target}: {exc}"
            ) from exc
    return manifest


def export_batch_bundle(
    root: Path,
    *,
    batch_id: str,
    output_dir: Path | None = None,
    created_at: str | None = None,
    create_archive: bool = False,
    archive_path: Path | None = None,
    include_trace: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    batches = _batch_index(root)
    batch_index_record = batches.get(batch_id)
    if not batch_index_record:
        raise ReportBundleError(f"Unknown batch_id: {batch_id}")

    bundle_dir = output_dir or root / "exports" / "batch-bundles" / batch_id
    if not bundle_dir.is_absolute():
        bundle_dir = root / bundle_dir
    bundle_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "schema_version": "0.2",
        "bundle_id": f"bundle-{batch_id}",
        "batch_id": batch_id,
        "created_at": created_at or EARecord.now_iso(),
        "workspace": str(root),
        "bundle_path": str(bundle_dir),
        "artifacts": {
            "batch_records": [],
            "report_bundles": [],
            "provenance": [],
        },
        "trace_export": {
            "included": include_trace,
            "strategy": "nested_report_focused_trace_views"
            if include_trace
            else "not_requested",
            "batch_level_trace_included": False,
            "batch_level_trace_reason": "project_trace_view_does_not_model_batch_nodes_yet"
            if include_trace
            else None,
            "boundaries": [
                "Batch trace export currently delegates to nested report bundle focused trace views.",
                "It does not mutate source reports, create ReviewRecords, commit memory, register references, inject citations, generate source packets/suggestions, or prove scientific conclusions.",
            ],
        },
        "provenance_inputs": [],
        "missing_refs": [],
        "archive_created": False,
        "archive_path": None,
        "archive_ref": None,
        "archive_checksum_path": None,
        "archive_checksum_ref": None,
        "checksum_manifest_path": None,
        "checksum_manifest_ref": None,
        "checksum_manifest_bundle_ref": None,
    }

    batch_refs = [
        ("batch_index", "processed/batches/index.yml"),
        ("batch_run", str(batch_index_record.get("record_ref") or "")),
        ("batch_summary", str(batch_index_record.get("summary_ref") or "")),
        ("batch_manifest", str(batch_index_record.get("manifest_ref") or "")),
    ]
    for kind, ref in batch_refs:
        if not ref:
            _record_missing(manifest, kind=kind, ref=ref, reason="empty_ref")
            continue
        copied = _copy_project_file(
            root, bundle_dir, ref=ref, subdir="batch", kind=kind, label=batch_id
        )
        manifest["artifacts"]["batch_records"].append(copied)
        if not copied["copied"]:
            _record_missing(
                manifest, kind=kind, ref=ref, reason=str(copied.get("skip_reason"))
            )

    batch_record_path = _project_path(
        root, str(batch_index_record.get("record_ref") or "")
    )
    batch_record = read_yaml(batch_record_path) if batch_record_path.exists() else {}
    manifest["batch_status"] = batch_record.get("status") or batch_index_record.get(
        "status"
    )
    manifest["item_count"] = batch_record.get("item_count") or batch_index_record.get(
        "item_count"
    )
    manifest["items"] = []

    for item in batch_record.get("items") or []:
        item_summary = {
            "item_id": item.get("item_id"),
            "method": item.get("method"),
            "status": item.get("status"),
            "report_ref": item.get("report_ref"),
            "report_id": None,
            "report_bundle_ref": None,
            "report_manifest_ref": None,
        }
        manifest["items"].append(item_summary)
        report_ref = str(item.get("report_ref") or "")
        if not report_ref:
            if item.get("status") == "success":
                _record_missing(
                    manifest,
                    kind="item_report",
                    ref=str(item.get("item_id") or ""),
                    reason="missing_report_ref",
                )
            continue
        report_id = _report_id_from_ref(root, report_ref)
        if not report_id:
            _record_missing(
                manifest,
                kind="item_report",
                ref=report_ref,
                reason="missing_or_unreadable_report",
            )
            continue
        report_bundle = export_report_bundle(
            root,
            report_id=report_id,
            output_dir=bundle_dir / "report-bundles" / report_id,
            created_at=str(manifest["created_at"]),
            create_archive=False,
            include_trace=include_trace,
        )
        report_bundle_ref = _project_ref(root, Path(report_bundle["bundle_path"]))
        report_manifest_ref = _project_ref(root, Path(report_bundle["manifest_path"]))
        item_summary["report_id"] = report_id
        item_summary["report_bundle_ref"] = report_bundle_ref
        item_summary["report_manifest_ref"] = report_manifest_ref
        nested = {
            "kind": "report_bundle",
            "label": report_id,
            "item_id": item.get("item_id"),
            "status": report_bundle["status"],
            "bundle_ref": Path(report_bundle["bundle_path"])
            .relative_to(bundle_dir)
            .as_posix(),
            "manifest_ref": Path(report_bundle["manifest_path"])
            .relative_to(bundle_dir)
            .as_posix(),
            "missing_ref_count": len(report_bundle.get("missing_refs") or []),
            "traceability": report_bundle.get("artifacts", {}).get("traceability", []),
        }
        manifest["artifacts"]["report_bundles"].append(nested)
        for missing in report_bundle.get("missing_refs") or []:
            manifest["missing_refs"].append(
                {
                    "kind": f"report_bundle.{missing.get('kind')}",
                    "ref": str(missing.get("ref")),
                    "reason": str(missing.get("reason")),
                    "report_id": report_id,
                    "item_id": item.get("item_id"),
                }
            )

    manifest["artifacts"]["provenance"].extend(
        _copy_provenance(
            root,
            bundle_dir,
            manifest,
            [str(ref) for ref in batch_record.get("provenance_refs") or []],
        )
    )

    manifest["status"] = "complete" if not manifest["missing_refs"] else "warning"
    archive_target: Path | None = None
    archive_checksum: Path | None = None
    if create_archive:
        archive_target = archive_path or _default_archive_path(bundle_dir)
        if not archive_target.is_absolute():
            archive_target = root / archive_target
        archive_checksum = _archive_checksum_path(archive_target)
        manifest["archive_created"] = True
        manifest["archive_path"] = str(archive_target)
        manifest["archive_ref"] = _project_ref(root, archive_target)
        manifest["archive_checksum_path"] = str(archive_checksum)
        manifest["archive_checksum_ref"] = _project_ref(root, archive_checksum)

    manifest_path = bundle_dir / "batch_bundle_manifest.yml"
    manifest["manifest_path"] = str(manifest_path)
    checksum_path = bundle_dir / "bundle_checksums.yml"
    manifest["checksum_manifest_path"] = str(checksum_path)
    manifest["checksum_manifest_ref"] = _project_ref(root, checksum_path)
    manifest["checksum_manifest_bundle_ref"] = checksum_path.relative_to(
        bundle_dir
    ).as_posix()
    write_yaml(manifest_path, manifest)
    _write_bundle_checksums(
        root, bundle_dir, manifest, exclude_paths=[archive_target, archive_checksum]
    )
    if create_archive:
        try:
            _write_zip_archive(
                bundle_dir, archive_target, exclude_paths=[archive_checksum]
            )
            _write_archive_checksum(archive_target, archive_checksum)
        except OSError as exc:
            raise ReportBundleError(
                f"Failed to create batch bundle archive: {archive_target}: {exc}"
            ) from exc
    return manifest
