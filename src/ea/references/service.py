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


def _normalize_doi(doi: str | None) -> str:
    if not doi:
        return ""
    value = doi.strip().lower()
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value)
    value = re.sub(r"^doi:\s*", "", value)
    return value.strip().rstrip(".")


def _normalize_url(url: str | None) -> str:
    if not url:
        return ""
    return url.strip().lower().rstrip("/")


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _clean_bibtex_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", value.replace("\n", " ")).strip()
    while cleaned.startswith("{") and cleaned.endswith("}") and len(cleaned) >= 2:
        cleaned = cleaned[1:-1].strip()
    cleaned = cleaned.replace("{", "").replace("}", "")
    return cleaned or None


def _parse_bibtex_value(text: str, start: int) -> tuple[str, int]:
    if start >= len(text):
        return "", start
    opener = text[start]
    if opener == "{":
        depth = 1
        index = start + 1
        while index < len(text) and depth:
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
            index += 1
        if depth:
            raise ReferenceError("Unclosed BibTeX field value")
        return text[start + 1 : index - 1], index
    if opener == '"':
        index = start + 1
        escaped = False
        while index < len(text):
            char = text[index]
            if char == '"' and not escaped:
                return text[start + 1 : index], index + 1
            escaped = char == "\\" and not escaped
            if char != "\\":
                escaped = False
            index += 1
        raise ReferenceError("Unclosed BibTeX quoted value")
    index = start
    while index < len(text) and text[index] != ",":
        index += 1
    return text[start:index], index


def _split_bibtex_key_and_fields(body: str) -> tuple[str, str]:
    depth = 0
    in_quote = False
    for index, char in enumerate(body):
        if char == '"' and (index == 0 or body[index - 1] != "\\"):
            in_quote = not in_quote
        elif not in_quote and char == "{":
            depth += 1
        elif not in_quote and char == "}":
            depth -= 1
        elif not in_quote and depth == 0 and char == ",":
            return body[:index].strip(), body[index + 1 :]
    return body.strip(), ""


def _parse_bibtex_fields(fields_text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    index = 0
    while index < len(fields_text):
        while index < len(fields_text) and fields_text[index] in " \t\r\n,":
            index += 1
        name_start = index
        while index < len(fields_text) and re.match(r"[A-Za-z0-9_-]", fields_text[index]):
            index += 1
        name = fields_text[name_start:index].strip().lower()
        if not name:
            break
        while index < len(fields_text) and fields_text[index].isspace():
            index += 1
        if index >= len(fields_text) or fields_text[index] != "=":
            break
        index += 1
        while index < len(fields_text) and fields_text[index].isspace():
            index += 1
        value, index = _parse_bibtex_value(fields_text, index)
        cleaned = _clean_bibtex_value(value)
        if cleaned:
            fields[name] = cleaned
        while index < len(fields_text) and fields_text[index] != ",":
            index += 1
    return fields


def parse_bibtex_references(text: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    index = 0
    while True:
        at_index = text.find("@", index)
        if at_index == -1:
            break
        type_start = at_index + 1
        bracket_index = type_start
        while bracket_index < len(text) and text[bracket_index] not in "{(":
            bracket_index += 1
        if bracket_index >= len(text):
            break
        entry_type = text[type_start:bracket_index].strip().lower()
        opener = text[bracket_index]
        closer = "}" if opener == "{" else ")"
        depth = 1
        end_index = bracket_index + 1
        while end_index < len(text) and depth:
            if text[end_index] == opener:
                depth += 1
            elif text[end_index] == closer:
                depth -= 1
            end_index += 1
        if depth:
            raise ReferenceError(f"Unclosed BibTeX entry starting at offset {at_index}")
        body = text[bracket_index + 1 : end_index - 1]
        index = end_index
        if entry_type in {"comment", "preamble", "string"}:
            continue
        key, fields_text = _split_bibtex_key_and_fields(body)
        entries.append(
            {
                "entry_type": entry_type,
                "entry_key": key,
                "fields": _parse_bibtex_fields(fields_text),
            }
        )
    return entries


def _parse_bibtex_authors(author_text: str | None) -> list[str]:
    if not author_text:
        return []
    authors = []
    for raw_author in re.split(r"\s+and\s+", author_text):
        author = _clean_bibtex_value(raw_author)
        if not author:
            continue
        if "," in author:
            last, first = [part.strip() for part in author.split(",", 1)]
            author = f"{last} {first}".strip()
        authors.append(author)
    return authors


def _bibtex_year(year_text: str | None) -> int | None:
    if not year_text:
        return None
    match = re.search(r"\d{4}", year_text)
    return int(match.group(0)) if match else None


def _first_present(fields: dict[str, str], names: list[str]) -> str | None:
    for name in names:
        value = _clean_bibtex_value(fields.get(name))
        if value:
            return value
    return None


def _citation_from_bibtex(fields: dict[str, str]) -> str | None:
    title = _clean_bibtex_value(fields.get("title"))
    if not title:
        return None
    authors = _parse_bibtex_authors(fields.get("author"))
    author_text = "Unknown authors"
    if len(authors) == 1:
        author_text = authors[0]
    elif len(authors) > 1:
        author_text = f"{authors[0]} et al."
    venue = _first_present(fields, ["journal", "journaltitle", "booktitle", "publisher", "institution"])
    year = _bibtex_year(fields.get("year") or fields.get("date"))
    parts = [f"{author_text}.", f"{title}."]
    if venue and year:
        parts.append(f"{venue} ({year}).")
    elif venue:
        parts.append(f"{venue}.")
    elif year:
        parts.append(f"({year}).")
    return " ".join(parts)


def _reference_kwargs_from_bibtex(entry: dict[str, Any]) -> dict[str, Any]:
    fields = entry.get("fields", {})
    title = _clean_bibtex_value(fields.get("title"))
    doi = _normalize_doi(fields.get("doi")) or None
    url = _clean_bibtex_value(fields.get("url"))
    return {
        "citation": _citation_from_bibtex(fields),
        "title": title,
        "authors": _parse_bibtex_authors(fields.get("author")),
        "year": _bibtex_year(fields.get("year") or fields.get("date")),
        "venue": _first_present(fields, ["journal", "journaltitle", "booktitle", "publisher", "institution"]),
        "doi": doi,
        "url": url,
        "local_path": _clean_bibtex_value(fields.get("file")),
    }


def find_duplicate_reference(
    root: Path,
    *,
    doi: str | None = None,
    url: str | None = None,
    title: str | None = None,
    citation: str | None = None,
) -> dict[str, Any] | None:
    index_path = _index_path(root)
    if not index_path.exists():
        return None
    index = read_yaml(index_path)
    target_doi = _normalize_doi(doi)
    target_url = _normalize_url(url)
    target_title = _normalize_text(title)
    target_citation = _normalize_text(citation)
    for reference_id, item in (index.get("references") or {}).items():
        record_path = root / item.get("path", "")
        record = read_yaml(record_path) if record_path.exists() else item
        if target_doi and _normalize_doi(record.get("doi")) == target_doi:
            return {"reference_id": reference_id, "path": str(record_path), "match": "doi"}
        if target_url and _normalize_url(record.get("url")) == target_url:
            return {"reference_id": reference_id, "path": str(record_path), "match": "url"}
        if target_title and _normalize_text(record.get("title")) == target_title:
            return {"reference_id": reference_id, "path": str(record_path), "match": "title"}
        if target_citation and _normalize_text(record.get("citation")) == target_citation:
            return {"reference_id": reference_id, "path": str(record_path), "match": "citation"}
    return None


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


def import_bibtex_references(
    root: Path,
    bibtex_path: Path,
    *,
    project_id: str,
    source_type: SourceType = "literature_library",
    created_at: str | None = None,
) -> dict[str, Any]:
    source_path = bibtex_path if bibtex_path.exists() else root / bibtex_path
    if not source_path.exists():
        raise ReferenceError(f"BibTeX file not found: {bibtex_path}")
    entries = parse_bibtex_references(source_path.read_text(encoding="utf-8"))
    imported: list[dict[str, Any]] = []
    reused: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for entry in entries:
        kwargs = _reference_kwargs_from_bibtex(entry)
        citation = kwargs.pop("citation")
        if not citation:
            skipped.append(
                {
                    "entry_key": entry.get("entry_key"),
                    "entry_type": entry.get("entry_type"),
                    "reason": "missing_title_or_citation",
                }
            )
            continue
        duplicate = find_duplicate_reference(
            root,
            doi=kwargs.get("doi"),
            url=kwargs.get("url"),
            title=kwargs.get("title"),
            citation=citation,
        )
        if duplicate:
            reused.append(
                {
                    "entry_key": entry.get("entry_key"),
                    "entry_type": entry.get("entry_type"),
                    "reference_id": duplicate["reference_id"],
                    "match": duplicate["match"],
                    "path": duplicate["path"],
                }
            )
            continue
        path = register_reference(
            root,
            project_id=project_id,
            citation=citation,
            source_type=source_type,
            notes=f"Imported from BibTeX entry `{entry.get('entry_key')}` in `{source_path.name}`.",
            created_at=created_at,
            **kwargs,
        )
        imported.append(
            {
                "entry_key": entry.get("entry_key"),
                "entry_type": entry.get("entry_type"),
                "reference_id": path.stem,
                "path": str(path),
            }
        )
    return {
        "bibtex_path": str(source_path),
        "entry_count": len(entries),
        "imported_count": len(imported),
        "reused_count": len(reused),
        "skipped_count": len(skipped),
        "imported": imported,
        "reused": reused,
        "skipped": skipped,
    }


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
