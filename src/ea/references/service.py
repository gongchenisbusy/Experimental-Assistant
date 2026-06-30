from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

from ea.schema import ReferenceRecord
from ea.schema.models import EARecord
from ea.storage.files import read_markdown_record, read_yaml, write_yaml
from ea.storage.ids import next_id


SourceType = Literal["manual", "literature_library", "web", "local_pdf", "report"]


class ReferenceError(ValueError):
    """Raised when reference records or report citations are invalid."""


def _reference_dir(root: Path) -> Path:
    return root / "literature" / "references"


def _index_path(root: Path) -> Path:
    return _reference_dir(root) / "index.yml"


def _relative_ref(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def register_reference(
    root: Path,
    *,
    project_id: str,
    citation: str,
    title: str | None = None,
    authors: list[str] | None = None,
    year: int | None = None,
    venue: str | None = None,
    doi: str | None = None,
    url: str | None = None,
    local_path: str | None = None,
    source_type: SourceType = "manual",
    notes: str | None = None,
    created_at: str | None = None,
) -> Path:
    if not citation.strip():
        raise ReferenceError("Reference citation cannot be empty")
    reference_id = next_id(root, "reference", created_at[:10] if created_at else None)
    record = ReferenceRecord(
        reference_id=reference_id,
        project_id=project_id,
        citation=citation.strip(),
        title=title,
        authors=authors or [],
        year=year,
        venue=venue,
        doi=doi,
        url=url,
        local_path=local_path,
        source_type=source_type,
        notes=notes,
        created_at=created_at or EARecord.now_iso(),
        updated_at=created_at or EARecord.now_iso(),
    )
    path = _reference_dir(root) / f"{reference_id}.yml"
    write_yaml(path, record.model_dump(exclude_none=True))
    index_path = _index_path(root)
    index = read_yaml(index_path) if index_path.exists() else {"schema_version": "0.2", "references": {}}
    index.setdefault("references", {})[reference_id] = {
        "reference_id": reference_id,
        "path": _relative_ref(root, path),
        "project_id": project_id,
        "citation": citation.strip(),
        "doi": doi,
        "url": url,
        "local_path": local_path,
        "source_type": source_type,
    }
    write_yaml(index_path, index)
    return path


def read_reference(root: Path, reference_id: str) -> dict[str, Any]:
    path = _reference_dir(root) / f"{reference_id}.yml"
    if not path.exists():
        raise ReferenceError(f"Unknown reference_id: {reference_id}")
    return read_yaml(path)


def format_inline_citation(numbers: list[int]) -> str:
    return "".join(f"[{number}]" for number in numbers)


def format_reference_entry(reference: dict[str, Any], number: int) -> str:
    parts = [str(reference.get("citation") or reference.get("title") or "Untitled reference")]
    doi = reference.get("doi")
    local_path = reference.get("local_path")
    url = reference.get("url")
    if doi:
        parts.append(f"DOI: {doi}")
    if local_path:
        parts.append(f"Local: {local_path}")
    if url:
        parts.append(f"Web: {url}")
    return f"[{number}] " + " | ".join(parts)


def build_report_reference_block(root: Path, reference_ids: list[str] | None) -> dict[str, Any]:
    reference_ids = reference_ids or []
    seen: set[str] = set()
    ordered_ids = []
    for reference_id in reference_ids:
        if reference_id not in seen:
            seen.add(reference_id)
            ordered_ids.append(reference_id)
    records = [read_reference(root, reference_id) for reference_id in ordered_ids]
    numbered = [
        {
            "number": index,
            "reference_id": record["reference_id"],
            "entry": format_reference_entry(record, index),
        }
        for index, record in enumerate(records, start=1)
    ]
    if not numbered:
        return {
            "reference_ids": [],
            "inline_citation": "",
            "numbered_references": [],
            "references_markdown": "本报告当前未引用外部文献。若后续加入文献解释，正文对应位置必须使用 `[1]` 形式标注，并在本节列出 DOI、本地 PDF 或网页链接。",
        }
    return {
        "reference_ids": ordered_ids,
        "inline_citation": format_inline_citation([item["number"] for item in numbered]),
        "numbered_references": numbered,
        "references_markdown": "\n".join(item["entry"] for item in numbered),
    }


def validate_report_citations(report_path: Path) -> dict[str, Any]:
    frontmatter, body = read_markdown_record(report_path)
    if "## References" in body:
        main_text, references_text = body.split("## References", 1)
    else:
        main_text, references_text = body, ""
    inline_numbers = sorted({int(match) for match in re.findall(r"\[(\d+)\]", main_text)})
    reference_numbers = sorted({int(match) for match in re.findall(r"^\[(\d+)\]", references_text, flags=re.MULTILINE)})
    missing_entries = [number for number in inline_numbers if number not in reference_numbers]
    uncited_entries = [number for number in reference_numbers if number not in inline_numbers]
    frontmatter_ids = frontmatter.get("reference_ids") or []
    numbering_mismatch = bool(frontmatter_ids and len(frontmatter_ids) != len(reference_numbers))
    return {
        "ok": not missing_entries and not uncited_entries and not numbering_mismatch,
        "report_path": str(report_path),
        "inline_numbers": inline_numbers,
        "reference_numbers": reference_numbers,
        "missing_entries": missing_entries,
        "uncited_entries": uncited_entries,
        "frontmatter_reference_ids": frontmatter_ids,
        "numbering_mismatch": numbering_mismatch,
    }
