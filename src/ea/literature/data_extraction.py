from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from ea.figures import NATURE_LIKE_STYLE_PROFILE, register_figure
from ea.figures.style import apply_figure_style
from ea.provenance import write_provenance_entry
from ea.schema.models import EARecord
from ea.storage.files import atomic_write_bytes, atomic_write_text, read_yaml, write_yaml


DATASET_SCHEMA_VERSION = "1.0"
PROPERTY_KINDS = {
    "conductivity",
    "resistivity",
    "sheet_resistance",
    "sheet_conductance",
    "contact_resistance",
    "mobility",
}
REVIEW_DECISIONS = {"accept", "reject", "edit", "defer", "not_comparable"}
NOT_REPORTED = "not_reported"

PROPERTY_ALIASES = {
    "conductivity": ["electrical conductivity", "conductivity", "电导率"],
    "resistivity": ["electrical resistivity", "resistivity", "电阻率"],
    "sheet_resistance": ["sheet resistance", "sheet resistivity", "方块电阻"],
    "sheet_conductance": ["sheet conductance", "面电导"],
    "contact_resistance": ["contact resistance", "接触电阻"],
    "mobility": ["carrier mobility", "electron mobility", "hole mobility", "mobility", "迁移率"],
}

UNIT_RULES: dict[str, dict[str, tuple[str, float, str]]] = {
    "conductivity": {
        "s/m": ("S/m", 1.0, "reported_value * 1"),
        "s m-1": ("S/m", 1.0, "reported_value * 1"),
        "s m^-1": ("S/m", 1.0, "reported_value * 1"),
        "s/cm": ("S/m", 100.0, "reported_value * 100"),
        "s cm-1": ("S/m", 100.0, "reported_value * 100"),
        "s cm^-1": ("S/m", 100.0, "reported_value * 100"),
        "ms/cm": ("S/m", 0.1, "reported_value * 0.1"),
        "us/cm": ("S/m", 0.0001, "reported_value * 0.0001"),
        "µs/cm": ("S/m", 0.0001, "reported_value * 0.0001"),
        "μs/cm": ("S/m", 0.0001, "reported_value * 0.0001"),
    },
    "resistivity": {
        "ohm m": ("ohm m", 1.0, "reported_value * 1"),
        "ω m": ("ohm m", 1.0, "reported_value * 1"),
        "ohm cm": ("ohm m", 0.01, "reported_value * 0.01"),
        "ω cm": ("ohm m", 0.01, "reported_value * 0.01"),
    },
    "sheet_resistance": {
        "ohm/sq": ("ohm/sq", 1.0, "reported_value * 1"),
        "ohm/square": ("ohm/sq", 1.0, "reported_value * 1"),
        "ω/sq": ("ohm/sq", 1.0, "reported_value * 1"),
        "kohm/sq": ("ohm/sq", 1000.0, "reported_value * 1000"),
        "kω/sq": ("ohm/sq", 1000.0, "reported_value * 1000"),
    },
    "sheet_conductance": {
        "s/sq": ("S/sq", 1.0, "reported_value * 1"),
        "s/square": ("S/sq", 1.0, "reported_value * 1"),
    },
    "contact_resistance": {
        "ohm": ("ohm", 1.0, "reported_value * 1"),
        "ω": ("ohm", 1.0, "reported_value * 1"),
        "kohm": ("ohm", 1000.0, "reported_value * 1000"),
        "kω": ("ohm", 1000.0, "reported_value * 1000"),
        "ohm um": ("ohm um", 1.0, "reported_value * 1"),
        "ω um": ("ohm um", 1.0, "reported_value * 1"),
    },
    "mobility": {
        "cm2/vs": ("cm2/(V s)", 1.0, "reported_value * 1"),
        "cm^2/vs": ("cm2/(V s)", 1.0, "reported_value * 1"),
        "cm2 v-1 s-1": ("cm2/(V s)", 1.0, "reported_value * 1"),
        "m2/vs": ("cm2/(V s)", 10000.0, "reported_value * 10000"),
    },
}

VALUE_PATTERN = re.compile(
    r"(?P<value>[+-]?(?:\d+(?:,\d{3})*|\d*\.\d+)(?:\.\d+)?(?:\s*[x×]\s*10\s*\^?\s*[+-]?\d+|[eE][+-]?\d+)?)"
)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:64] or "dataset"


def _dataset_root(root: Path, dataset_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}", dataset_id):
        raise ValueError("dataset_id must use only letters, numbers, dot, underscore, or hyphen")
    return root / "literature" / "data-extractions" / dataset_id


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_file():
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    if path.is_dir():
        for name in ("metadata.json", "chunks.jsonl", "outline.json", "paper.md"):
            candidate = path / name
            if candidate.is_file():
                digest.update(name.encode("utf-8"))
                digest.update(_sha256(candidate).encode("ascii"))
        if digest.digest() == hashlib.sha256().digest():
            digest.update(str(path.resolve()).encode("utf-8"))
        return digest.hexdigest()
    return hashlib.sha256(str(path).encode("utf-8")).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _source_metadata(path: Path) -> dict[str, Any]:
    if path.is_dir():
        return _json(path / "metadata.json")
    sidecar = path.with_suffix(path.suffix + ".metadata.json")
    return _json(sidecar) if sidecar.exists() else {}


def _discover_acquisition_sources(root: Path) -> list[dict[str, Any]]:
    status_path = root / "literature" / "zotero_codex_batch_status.json"
    if not status_path.exists():
        return []
    payload = _json(status_path)
    discovered: list[dict[str, Any]] = []
    for item in payload.get("items") or payload.get("targets") or []:
        if not isinstance(item, dict):
            continue
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        candidate = (
            item.get("cache_dir")
            or item.get("cache_path")
            or item.get("pdf_path")
            or item.get("local_path")
            or result.get("cache_dir")
        )
        if not candidate:
            continue
        path = Path(str(candidate)).expanduser()
        if not path.is_absolute():
            path = root / path
        discovered.append(
            {
                "path": path,
                "title": item.get("title") or result.get("title"),
                "doi": item.get("doi") or result.get("doi"),
                "zotero_item_key": item.get("zotero_item_key") or result.get("item_key"),
            }
        )
    return discovered


def _source_records(root: Path, sources: Iterable[Path]) -> list[dict[str, Any]]:
    raw = [{"path": path} for path in sources]
    if not raw:
        raw = _discover_acquisition_sources(root)
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in raw:
        path = Path(entry["path"]).expanduser()
        if not path.is_absolute():
            path = root / path
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        metadata = _source_metadata(path)
        records.append(
            {
                "source_id": f"source-{len(records) + 1:03d}",
                "source_type": "cache" if path.is_dir() else "pdf" if path.suffix.lower() == ".pdf" else "searchable_text",
                "source_path": str(path.resolve()),
                "source_hash": _sha256(path),
                "availability": "available" if path.exists() else "missing",
                "title": entry.get("title") or metadata.get("title") or path.stem,
                "doi": entry.get("doi") or metadata.get("doi"),
                "reference_id": metadata.get("reference_id"),
                "zotero_item_key": entry.get("zotero_item_key") or metadata.get("item_key") or metadata.get("zotero_item_key"),
                "cache_identity": metadata.get("pdf_sha256") or metadata.get("source_hash") or _sha256(path),
            }
        )
    return records


def plan_literature_data_extraction(
    root: Path,
    *,
    property_name: str,
    property_kind: str,
    material_name: str,
    sources: Iterable[Path] = (),
    required_conditions: Iterable[str] = (),
    comparability_rules: Iterable[str] = (),
    dataset_id: str | None = None,
    confirmed: bool = False,
    created_at: str | None = None,
) -> dict[str, Any]:
    if property_kind not in PROPERTY_KINDS:
        raise ValueError(f"Unsupported property_kind: {property_kind}")
    created_at = created_at or EARecord.now_iso()
    dataset_id = dataset_id or f"{_slug(property_kind)}-{_slug(material_name)}"
    dataset_root = _dataset_root(root, dataset_id)
    source_records = _source_records(root, sources)
    preview = {
        "status": "ready_to_create" if source_records else "scope_defined_needs_sources",
        "maturity": "beta",
        "dataset_id": dataset_id,
        "property_kind": property_kind,
        "material_name": material_name,
        "source_count": len(source_records),
        "requires_confirmation": not confirmed,
        "next_action": "Confirm creation, then run data-extract." if source_records else "Add searchable PDF/cache sources.",
    }
    if not confirmed:
        return preview
    spec_path = dataset_root / "extraction_spec.yml"
    if spec_path.exists():
        existing = read_yaml(spec_path)
        if existing.get("property_kind") != property_kind or existing.get("material_name") != material_name:
            raise ValueError(f"Dataset already exists with a different scope: {dataset_id}")
        state = read_yaml(dataset_root / "extraction_state.compact.yml")
        return {**preview, "status": "existing_plan_reused", "state": state.get("status"), "dataset_ref": _relative(root, dataset_root)}
    dataset_root.mkdir(parents=True, exist_ok=True)
    (dataset_root / "evidence").mkdir(exist_ok=True)
    (dataset_root / "plots").mkdir(exist_ok=True)
    spec = {
        "schema_version": DATASET_SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "maturity": "beta",
        "created_at": created_at,
        "property_name": property_name,
        "property_kind": property_kind,
        "material_name": material_name,
        "required_conditions": list(dict.fromkeys(required_conditions)),
        "comparability_rules": list(dict.fromkeys(comparability_rules)),
        "accepted_reported_units": list(UNIT_RULES[property_kind]),
        "normalized_units": sorted({rule[0] for rule in UNIT_RULES[property_kind].values()}),
        "boundaries": [
            "Only lawful user-provided or verified cached full text may be processed.",
            "Automatic values are candidates until explicit record review.",
            "Conductivity, resistivity, sheet resistance, sheet conductance, contact resistance, and mobility are never silently interchanged.",
            "Complex figure digitization and bulk OCR are outside this beta workflow.",
        ],
    }
    source_manifest = {
        "schema_version": DATASET_SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "source_count": len(source_records),
        "sources": source_records,
    }
    state = {
        "schema_version": DATASET_SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "status": "sources_selected" if source_records else "scope_defined",
        "updated_at": created_at,
        "checkpoints": {},
        "metrics": {"papers_processed": 0, "pages_read": 0, "chunks_read": 0, "candidate_count": 0, "output_bytes": 0, "artifact_bytes": 0},
        "next_action": "Run `ea literature data-extract`.",
    }
    write_yaml(spec_path, spec)
    write_yaml(dataset_root / "source_manifest.yml", source_manifest)
    write_yaml(dataset_root / "extraction_state.compact.yml", state)
    return {**preview, "status": state["status"], "requires_confirmation": False, "dataset_ref": _relative(root, dataset_root)}


def _documents_from_jsonl(path: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for index, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue
        text = item.get("text") or item.get("content") or item.get("chunk")
        caption = item.get("caption")
        if text and caption and str(caption) not in str(text):
            text = f"{text}\nCaption: {caption}"
        elif not text and caption:
            text = f"Caption: {caption}"
        if not text:
            continue
        docs.append(
            {
                "text": str(text),
                "page": item.get("page") or item.get("page_number") or NOT_REPORTED,
                "section": item.get("section") or NOT_REPORTED,
                "table": item.get("table") or item.get("table_id") or NOT_REPORTED,
                "figure": item.get("figure") or item.get("figure_id") or NOT_REPORTED,
                "caption": caption or NOT_REPORTED,
                "chunk_id": item.get("chunk_id") or item.get("id") or f"chunk-{index:04d}",
            }
        )
    return docs


def _documents_from_pdf(path: Path) -> list[dict[str, Any]]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - package dependency provides pypdf
        raise RuntimeError("pypdf is required for direct PDF input; alternatively provide a verified searchable cache") from exc
    reader = PdfReader(str(path))
    return [
        {
            "text": page.extract_text() or "",
            "page": index,
            "section": NOT_REPORTED,
            "table": NOT_REPORTED,
            "figure": NOT_REPORTED,
            "caption": NOT_REPORTED,
            "chunk_id": f"page-{index:04d}",
        }
        for index, page in enumerate(reader.pages, start=1)
    ]


def _source_documents(source: dict[str, Any]) -> list[dict[str, Any]]:
    path = Path(source["source_path"])
    if not path.exists():
        raise FileNotFoundError(path)
    if path.is_dir():
        chunks = path / "chunks.jsonl"
        if chunks.exists():
            return _documents_from_jsonl(chunks)
        paper = path / "paper.md"
        if not paper.exists():
            raise FileNotFoundError(f"Searchable cache has no chunks.jsonl or paper.md: {path}")
        path = paper
    if path.suffix.lower() == ".pdf":
        return _documents_from_pdf(path)
    if path.suffix.lower() == ".jsonl":
        return _documents_from_jsonl(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    pages = text.split("\f")
    return [
        {
            "text": page,
            "page": index,
            "section": NOT_REPORTED,
            "table": NOT_REPORTED,
            "figure": NOT_REPORTED,
            "caption": NOT_REPORTED,
            "chunk_id": f"page-{index:04d}",
        }
        for index, page in enumerate(pages, start=1)
    ]


def _parse_number(value: str) -> float:
    normalized = value.replace(",", "").replace(" ", "").replace("×", "x")
    normalized = re.sub(r"x10\^?([+-]?\d+)", r"e\1", normalized, flags=re.I)
    return float(normalized)


def _unit_match(text: str, property_kind: str) -> tuple[float, str] | None:
    units = sorted(UNIT_RULES[property_kind], key=len, reverse=True)
    unit_pattern = "|".join(re.escape(unit) for unit in units)
    match = re.search(VALUE_PATTERN.pattern + rf"\s*(?P<unit>{unit_pattern})(?![A-Za-z0-9])", text, flags=re.I)
    if not match:
        return None
    return _parse_number(match.group("value")), match.group("unit")


def _normalize_unit(property_kind: str, value: float, reported_unit: str) -> tuple[float | None, str | None, str, str]:
    key = re.sub(r"\s+", " ", reported_unit.strip().lower().replace("Ω", "ω").replace("Ω", "ω"))
    rule = UNIT_RULES[property_kind].get(key)
    if not rule:
        return None, None, "unsupported", "not_available"
    normalized_unit, factor, formula = rule
    return value * factor, normalized_unit, "converted" if factor != 1.0 else "identity", formula


def _context_value(pattern: str, text: str, group: int | str = 1) -> Any:
    match = re.search(pattern, text, flags=re.I)
    return match.group(group) if match else NOT_REPORTED


def _conditions(text: str) -> dict[str, Any]:
    temperature = re.search(r"([+-]?\d+(?:\.\d+)?)\s*(K|°C|C)\b", text, flags=re.I)
    method = "four_probe" if re.search(r"four[- ]?probe|4[- ]?probe", text, re.I) else "two_probe" if re.search(r"two[- ]?probe|2[- ]?probe", text, re.I) else NOT_REPORTED
    direction = "in_plane" if re.search(r"in[- ]?plane", text, re.I) else "out_of_plane" if re.search(r"out[- ]?of[- ]?plane|cross[- ]?plane", text, re.I) else NOT_REPORTED
    return {
        "temperature": f"{temperature.group(1)} {temperature.group(2)}" if temperature else NOT_REPORTED,
        "pressure": _context_value(r"([+-]?\d+(?:\.\d+)?\s*(?:Pa|kPa|MPa|GPa|bar|atm))\b", text),
        "frequency": _context_value(r"([+-]?\d+(?:\.\d+)?\s*(?:Hz|kHz|MHz|GHz))\b", text),
        "direction": direction,
        "geometry": _context_value(r"\b(van der pauw|hall bar|transmission line|TLM)\b", text),
        "instrument_or_method": method,
        "sample_count": _context_value(r"\bn\s*=\s*(\d+)\b", text),
    }


def _identity_context(text: str) -> tuple[dict[str, Any], dict[str, Any]]:
    layer = _context_value(r"\b(monolayer|bilayer|trilayer|\d+[- ]?layer)\b", text)
    thickness = _context_value(r"([+-]?\d+(?:\.\d+)?\s*(?:nm|um|µm|μm))\b", text)
    identity = {
        "composition": NOT_REPORTED,
        "phase": NOT_REPORTED,
        "morphology": NOT_REPORTED,
        "layer_count": layer,
        "thickness": thickness,
    }
    context = {
        "preparation": NOT_REPORTED,
        "substrate": _context_value(r"(?:on|substrate[: ]+)\s*([A-Za-z0-9_-]+)", text),
        "contacts": _context_value(r"\b(Au|Ti/Au|Cr/Au|Pt|Ag|graphene)\s+contacts?\b", text),
        "doping": _context_value(r"\b([np])[- ]?doped\b", text),
        "defects": NOT_REPORTED,
        "strain": _context_value(r"([+-]?\d+(?:\.\d+)?\s*%\s*strain)\b", text),
        "environment": _context_value(r"\b(vacuum|air|nitrogen|argon|ambient)\b", text),
    }
    return identity, context


def _property_sentences(text: str, property_kind: str) -> list[str]:
    aliases = PROPERTY_ALIASES[property_kind]
    sentences = re.split(r"(?<=[.!?。！？])\s+|[\r\n]+", text)
    return [sentence.strip() for sentence in sentences if sentence.strip() and any(alias.lower() in sentence.lower() for alias in aliases)]


def _extract_source_records(source: dict[str, Any], spec: dict[str, Any], docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    property_kind = spec["property_kind"]
    for doc in docs:
        for sentence in _property_sentences(doc["text"], property_kind):
            unit_match = _unit_match(sentence, property_kind)
            warnings: list[str] = []
            if unit_match:
                reported_value, reported_unit = unit_match
                normalized_value, normalized_unit, conversion_status, formula = _normalize_unit(property_kind, reported_value, reported_unit)
            else:
                loose = re.search(r"(?:was|is|of|=|为)\s*" + VALUE_PATTERN.pattern, sentence, flags=re.I)
                if not loose:
                    continue
                reported_value = _parse_number(loose.group("value"))
                reported_unit = NOT_REPORTED
                normalized_value, normalized_unit, conversion_status, formula = None, None, "missing_unit", "not_available"
                warnings.append("missing_reported_unit")
            identity, context = _identity_context(sentence)
            conditions = _conditions(sentence)
            record_id = f"rec-{source['source_id']}-{len(records) + 1:03d}"
            records.append(
                {
                    "record_id": record_id,
                    "property_name": spec["property_name"],
                    "property_kind": property_kind,
                    "material_name": spec["material_name"],
                    **identity,
                    "reported_value": reported_value,
                    "reported_unit": reported_unit,
                    "range": NOT_REPORTED,
                    "uncertainty": NOT_REPORTED,
                    "qualifier": NOT_REPORTED,
                    "normalized_value": normalized_value,
                    "normalized_unit": normalized_unit or NOT_REPORTED,
                    "conversion_formula": formula,
                    "conversion_status": conversion_status,
                    "conditions": conditions,
                    "context": context,
                    "source": {
                        "doi": source.get("doi") or NOT_REPORTED,
                        "reference_id": source.get("reference_id") or NOT_REPORTED,
                        "zotero_item_key": source.get("zotero_item_key") or NOT_REPORTED,
                        "cache_identity": source.get("cache_identity") or source["source_hash"],
                        "source_hash": source["source_hash"],
                        "paper_title": source.get("title") or NOT_REPORTED,
                        "source_id": source["source_id"],
                    },
                    "evidence": {
                        "page": doc.get("page", NOT_REPORTED),
                        "section": doc.get("section", NOT_REPORTED),
                        "table": doc.get("table", NOT_REPORTED),
                        "figure": doc.get("figure", NOT_REPORTED),
                        "caption": doc.get("caption", NOT_REPORTED),
                        "chunk_anchor": doc.get("chunk_id", NOT_REPORTED),
                        "short_context": sentence[:400],
                    },
                    "audit": {
                        "extraction_origin": "deterministic_searchable_text_pattern_beta",
                        "confidence": "medium" if unit_match else "low",
                        "warnings": warnings,
                        "review_state": "candidate",
                        "reviewed_at": None,
                        "review_notes": [],
                        "duplicate_refs": [],
                        "conflict_refs": [],
                    },
                    "comparison_status": "needs_review",
                }
            )
    return records


def _mark_duplicates_and_conflicts(records: list[dict[str, Any]]) -> None:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        doi = str(record["source"].get("doi") or "").lower()
        if doi and doi != NOT_REPORTED:
            groups[(doi, record["property_kind"])].append(record)
    for grouped in groups.values():
        if len(grouped) < 2:
            continue
        for record in grouped:
            peers = [peer for peer in grouped if peer["record_id"] != record["record_id"]]
            same = [peer["record_id"] for peer in peers if peer.get("reported_value") == record.get("reported_value") and peer.get("reported_unit") == record.get("reported_unit")]
            conflicts = [peer["record_id"] for peer in peers if peer["record_id"] not in same]
            record["audit"]["duplicate_refs"] = same
            record["audit"]["conflict_refs"] = conflicts
            if conflicts and "duplicate_doi_conflicting_evidence" not in record["audit"]["warnings"]:
                record["audit"]["warnings"].append("duplicate_doi_conflicting_evidence")


CSV_FIELDS = [
    "record_id",
    "property_name",
    "property_kind",
    "material_name",
    "reported_value",
    "reported_unit",
    "normalized_value",
    "normalized_unit",
    "conversion_formula",
    "conversion_status",
    "temperature",
    "direction",
    "instrument_or_method",
    "doi",
    "paper_title",
    "page",
    "section",
    "table",
    "figure",
    "chunk_anchor",
    "review_state",
    "comparison_status",
    "warnings",
]


def _csv_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for record in records:
        rows.append(
            {
                "record_id": record["record_id"],
                "property_name": record["property_name"],
                "property_kind": record["property_kind"],
                "material_name": record["material_name"],
                "reported_value": record["reported_value"],
                "reported_unit": record["reported_unit"],
                "normalized_value": record["normalized_value"],
                "normalized_unit": record["normalized_unit"],
                "conversion_formula": record["conversion_formula"],
                "conversion_status": record["conversion_status"],
                "temperature": record["conditions"]["temperature"],
                "direction": record["conditions"]["direction"],
                "instrument_or_method": record["conditions"]["instrument_or_method"],
                "doi": record["source"]["doi"],
                "paper_title": record["source"]["paper_title"],
                "page": record["evidence"]["page"],
                "section": record["evidence"]["section"],
                "table": record["evidence"]["table"],
                "figure": record["evidence"]["figure"],
                "chunk_anchor": record["evidence"]["chunk_anchor"],
                "review_state": record["audit"]["review_state"],
                "comparison_status": record["comparison_status"],
                "warnings": ";".join(record["audit"]["warnings"]),
            }
        )
    return rows


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(_csv_rows(records))
    atomic_write_text(path, buffer.getvalue())


def _review_package(dataset_root: Path, records: list[dict[str, Any]], updated_at: str) -> None:
    pending = [record for record in records if record["audit"]["review_state"] in {"candidate", "deferred"}]
    package = {
        "schema_version": DATASET_SCHEMA_VERSION,
        "dataset_id": dataset_root.name,
        "updated_at": updated_at,
        "status": "needs_review" if pending else "review_complete",
        "candidate_count": len(records),
        "pending_count": len(pending),
        "records": [
            {
                "record_id": record["record_id"],
                "property_kind": record["property_kind"],
                "reported": f"{record['reported_value']} {record['reported_unit']}",
                "normalized": f"{record['normalized_value']} {record['normalized_unit']}",
                "source": record["source"],
                "evidence": record["evidence"],
                "warnings": record["audit"]["warnings"],
                "review_state": record["audit"]["review_state"],
            }
            for record in records
        ],
        "allowed_decisions": sorted(REVIEW_DECISIONS),
        "boundaries": ["Only accepted or edited records can enter the reviewed dataset; plot eligibility also requires comparability."],
    }
    write_yaml(dataset_root / "review_package.yml", package)
    lines = [
        f"# Literature Data Review: {dataset_root.name}",
        "",
        f"Candidates: {len(records)} | pending: {len(pending)}",
        "",
        "| Record | Property | Reported | DOI | Evidence | State | Warnings |",
        "|---|---|---|---|---|---|---|",
    ]
    for record in records:
        evidence = record["evidence"]
        anchor = f"p.{evidence['page']} / {evidence['chunk_anchor']}"
        values = [
            record["record_id"],
            record["property_kind"],
            f"{record['reported_value']} {record['reported_unit']}",
            record["source"]["doi"],
            anchor,
            record["audit"]["review_state"],
            ", ".join(record["audit"]["warnings"]) or "-",
        ]
        lines.append("| " + " | ".join(str(value).replace("|", "\\|").replace("\n", " ") for value in values) + " |")
    lines.extend(["", "Unreviewed candidates cannot enter plots, statistics, reports, or durable memory.", ""])
    atomic_write_text(dataset_root / "review_package.md", "\n".join(lines))


def _artifact_bytes(dataset_root: Path) -> int:
    return sum(path.stat().st_size for path in dataset_root.rglob("*") if path.is_file())


def extract_literature_data(
    root: Path,
    *,
    dataset_id: str,
    max_sources: int | None = None,
    confirmed: bool = False,
    extracted_at: str | None = None,
) -> dict[str, Any]:
    if not confirmed:
        return {"status": "needs_confirmation", "dataset_id": dataset_id, "next_action": "Rerun with explicit confirmation."}
    extracted_at = extracted_at or EARecord.now_iso()
    dataset_root = _dataset_root(root, dataset_id)
    spec = read_yaml(dataset_root / "extraction_spec.yml")
    manifest = read_yaml(dataset_root / "source_manifest.yml")
    state_path = dataset_root / "extraction_state.compact.yml"
    state = read_yaml(state_path)
    candidate_path = dataset_root / "candidate_records.yml"
    records = (read_yaml(candidate_path).get("records") or []) if candidate_path.exists() else []
    processed_now = 0
    attempted_now = 0
    skipped = 0
    failures = 0
    checkpoints = state.setdefault("checkpoints", {})
    sources = manifest.get("sources") or []
    for source in sources:
        if max_sources is not None and attempted_now >= max_sources:
            break
        source_hash = _sha256(Path(source["source_path"]))
        checkpoint = checkpoints.get(source["source_id"]) or {}
        if checkpoint.get("status") == "completed" and checkpoint.get("source_hash") == source_hash:
            skipped += 1
            continue
        records = [record for record in records if record["source"]["source_id"] != source["source_id"]]
        attempted_now += 1
        try:
            docs = _source_documents({**source, "source_hash": source_hash})
            if not any(str(doc.get("text") or "").strip() for doc in docs):
                raise RuntimeError("source_has_no_searchable_text_ocr_required")
            source_records = _extract_source_records({**source, "source_hash": source_hash}, spec, docs)
            records.extend(source_records)
            write_yaml(
                dataset_root / "evidence" / f"{source['source_id']}.yml",
                {
                    "schema_version": DATASET_SCHEMA_VERSION,
                    "source_id": source["source_id"],
                    "source_hash": source_hash,
                    "records": [
                        {
                            "record_id": record["record_id"],
                            "page": record["evidence"]["page"],
                            "section": record["evidence"]["section"],
                            "table": record["evidence"]["table"],
                            "figure": record["evidence"]["figure"],
                            "chunk_anchor": record["evidence"]["chunk_anchor"],
                            "short_context": record["evidence"]["short_context"],
                        }
                        for record in source_records
                    ],
                    "copyright_boundary": "Only short evidence contexts and exact anchors are stored; this is not a full-text export.",
                },
            )
            checkpoints[source["source_id"]] = {
                "status": "completed",
                "source_hash": source_hash,
                "processed_at": extracted_at,
                "pages_or_chunks_read": len(docs),
                "candidate_count": len(source_records),
            }
            processed_now += 1
            state["metrics"]["pages_read"] = int(state["metrics"].get("pages_read", 0)) + len({str(doc.get("page")) for doc in docs})
            state["metrics"]["chunks_read"] = int(state["metrics"].get("chunks_read", 0)) + len(docs)
        except Exception as exc:
            error_text = str(exc)
            checkpoints[source["source_id"]] = {
                "status": "failed",
                "source_hash": source_hash,
                "processed_at": extracted_at,
                "error_code": "ocr_required" if "ocr_required" in error_text else "source_unreadable_or_unsearchable",
                "error": error_text[:300],
                "safe_to_retry": True,
            }
            failures += 1
        _mark_duplicates_and_conflicts(records)
        write_yaml(candidate_path, {"schema_version": DATASET_SCHEMA_VERSION, "dataset_id": dataset_id, "records": records})
        _write_csv(dataset_root / "candidate_records.csv", records)
        _review_package(dataset_root, records, extracted_at)
        state["updated_at"] = extracted_at
        state["metrics"]["papers_processed"] = sum(item.get("status") == "completed" for item in checkpoints.values())
        state["metrics"]["candidate_count"] = len(records)
        state["status"] = "needs_review" if records else "fulltext_ready"
        state["next_action"] = "Review candidate records with `ea literature data-review`." if records else "Resolve source failures or add sources."
        state["metrics"]["artifact_bytes"] = _artifact_bytes(dataset_root)
        write_yaml(state_path, state)
    provenance = None
    if attempted_now:
        provenance = write_provenance_entry(
            root,
            workflow="literature_data_extraction_beta",
            inputs={"records": [], "files": [_relative(root, dataset_root / "source_manifest.yml")]},
            outputs={"records": [record["record_id"] for record in records], "files": [_relative(root, candidate_path)]},
            parameters={"dataset_id": dataset_id, "property_kind": spec["property_kind"], "max_sources": max_sources},
            warnings=[checkpoint for checkpoint in checkpoints.values() if checkpoint.get("status") == "failed"],
            created_at=extracted_at,
        )
    state["metrics"]["output_bytes"] = sum(
        path.stat().st_size for path in (candidate_path, dataset_root / "candidate_records.csv", dataset_root / "review_package.yml") if path.exists()
    )
    state["metrics"]["artifact_bytes"] = _artifact_bytes(dataset_root)
    write_yaml(state_path, state)
    return {
        "status": state["status"],
        "maturity": "beta",
        "dataset_id": dataset_id,
        "processed_now": processed_now,
        "reused_checkpoints": skipped,
        "failed_sources": failures,
        "candidate_count": len(records),
        "metrics": state["metrics"],
        "candidate_records_ref": _relative(root, candidate_path),
        "review_package_ref": _relative(root, dataset_root / "review_package.md"),
        "provenance_ref": _relative(root, provenance) if provenance else None,
        "next_action": state["next_action"],
    }


def _comparison_status(record: dict[str, Any], spec: dict[str, Any]) -> str:
    if record["audit"]["review_state"] == "not_comparable":
        return "not_comparable_by_review"
    if record.get("normalized_value") is None or record.get("normalized_unit") in {None, NOT_REPORTED}:
        return "not_comparable_missing_normalized_value"
    missing = [name for name in spec.get("required_conditions") or [] if record.get("conditions", {}).get(name, NOT_REPORTED) == NOT_REPORTED]
    if missing:
        return "not_comparable_missing_conditions:" + ",".join(missing)
    if record["audit"].get("conflict_refs"):
        return "not_comparable_conflicting_evidence"
    return "comparable"


def _reviewed_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in records if record["audit"]["review_state"] in {"accepted", "edited"}]


def review_literature_data(
    root: Path,
    *,
    dataset_id: str,
    record_id: str,
    decision: str,
    notes: Iterable[str] = (),
    reported_value: float | None = None,
    reported_unit: str | None = None,
    normalized_value: float | None = None,
    normalized_unit: str | None = None,
    conditions: dict[str, Any] | None = None,
    confirmed: bool = False,
    reviewed_at: str | None = None,
) -> dict[str, Any]:
    decision = decision.replace("-", "_")
    if decision not in REVIEW_DECISIONS:
        raise ValueError(f"Unsupported review decision: {decision}")
    if not confirmed:
        return {"status": "needs_confirmation", "dataset_id": dataset_id, "record_id": record_id, "decision": decision}
    reviewed_at = reviewed_at or EARecord.now_iso()
    dataset_root = _dataset_root(root, dataset_id)
    spec = read_yaml(dataset_root / "extraction_spec.yml")
    candidate_path = dataset_root / "candidate_records.yml"
    payload = read_yaml(candidate_path)
    records = payload.get("records") or []
    try:
        record = next(item for item in records if item["record_id"] == record_id)
    except StopIteration as exc:
        raise KeyError(f"Unknown literature data record: {record_id}") from exc
    if decision == "edit":
        edited_value_or_unit = any(value is not None for value in (reported_value, reported_unit, normalized_value, normalized_unit))
        if reported_value is not None:
            record["reported_value"] = reported_value
        if reported_unit is not None:
            record["reported_unit"] = reported_unit
        if normalized_value is not None:
            record["normalized_value"] = normalized_value
        if normalized_unit is not None:
            record["normalized_unit"] = normalized_unit
        if conditions:
            record["conditions"].update(conditions)
        if record.get("normalized_value") is None or record.get("normalized_unit") in {None, NOT_REPORTED}:
            raise ValueError("Edited records need a reviewed normalized value and unit before acceptance")
        record["conversion_status"] = "reviewer_edited"
        if edited_value_or_unit:
            record["conversion_formula"] = "reviewer_supplied_or_verified"
    if decision == "accept" and (record.get("normalized_value") is None or record.get("normalized_unit") in {None, NOT_REPORTED}):
        raise ValueError("A record with no reviewed normalized value/unit cannot be accepted; edit, defer, reject, or mark not-comparable")
    state_map = {
        "accept": "accepted",
        "reject": "rejected",
        "edit": "edited",
        "defer": "deferred",
        "not_comparable": "not_comparable",
    }
    record["audit"]["review_state"] = state_map[decision]
    record["audit"]["reviewed_at"] = reviewed_at
    record["audit"]["review_notes"] = list(notes)
    record["comparison_status"] = _comparison_status(record, spec)
    write_yaml(candidate_path, payload)
    _write_csv(dataset_root / "candidate_records.csv", records)
    reviewed = _reviewed_records(records)
    write_yaml(dataset_root / "reviewed_dataset.yml", {"schema_version": DATASET_SCHEMA_VERSION, "dataset_id": dataset_id, "records": reviewed})
    _write_csv(dataset_root / "reviewed_dataset.csv", reviewed)
    _review_package(dataset_root, records, reviewed_at)
    pending = sum(record["audit"]["review_state"] in {"candidate", "deferred"} for record in records)
    state_path = dataset_root / "extraction_state.compact.yml"
    state = read_yaml(state_path)
    state.update(
        {
            "status": "reviewed_dataset_ready" if reviewed and not pending else "needs_review",
            "updated_at": reviewed_at,
            "reviewed_count": len(reviewed),
            "pending_review_count": pending,
            "next_action": "Run data-validate; plot/export only comparable reviewed records." if reviewed else "Continue reviewing candidates.",
        }
    )
    write_yaml(state_path, state)
    return {
        "status": state["status"],
        "dataset_id": dataset_id,
        "record_id": record_id,
        "review_state": record["audit"]["review_state"],
        "comparison_status": record["comparison_status"],
        "reviewed_count": len(reviewed),
        "pending_review_count": pending,
        "reviewed_dataset_ref": _relative(root, dataset_root / "reviewed_dataset.yml"),
        "next_action": state["next_action"],
    }


def validate_literature_data(
    root: Path,
    *,
    dataset_id: str,
    write_report: bool = True,
    validated_at: str | None = None,
) -> dict[str, Any]:
    validated_at = validated_at or EARecord.now_iso()
    dataset_root = _dataset_root(root, dataset_id)
    spec = read_yaml(dataset_root / "extraction_spec.yml")
    candidates = read_yaml(dataset_root / "candidate_records.yml").get("records") or []
    reviewed_path = dataset_root / "reviewed_dataset.yml"
    reviewed = read_yaml(reviewed_path).get("records") or [] if reviewed_path.exists() else []
    findings: list[dict[str, Any]] = []
    record_ids = {record["record_id"] for record in candidates}
    for record in candidates:
        evidence = record.get("evidence") or {}
        if evidence.get("page") in {None, NOT_REPORTED} and evidence.get("chunk_anchor") in {None, NOT_REPORTED}:
            findings.append({"severity": "error", "code": "missing_evidence_anchor", "record_id": record["record_id"]})
        for ref in record.get("audit", {}).get("conflict_refs") or []:
            if ref not in record_ids:
                findings.append({"severity": "error", "code": "missing_conflict_reference", "record_id": record["record_id"], "ref": ref})
        if record["audit"]["review_state"] in {"accepted", "edited"}:
            if record.get("normalized_value") is None or record.get("normalized_unit") in {None, NOT_REPORTED}:
                findings.append({"severity": "error", "code": "reviewed_record_missing_normalized_value", "record_id": record["record_id"]})
            if record["property_kind"] != spec["property_kind"]:
                findings.append({"severity": "error", "code": "property_kind_mismatch", "record_id": record["record_id"]})
            if record["comparison_status"] != "comparable":
                findings.append({"severity": "warning", "code": record["comparison_status"], "record_id": record["record_id"]})
        elif record["audit"]["review_state"] in {"candidate", "deferred"}:
            findings.append({"severity": "info", "code": "record_not_yet_reviewed", "record_id": record["record_id"]})
    error_count = sum(item["severity"] == "error" for item in findings)
    warning_count = sum(item["severity"] == "warning" for item in findings)
    comparable_count = sum(record.get("comparison_status") == "comparable" for record in reviewed)
    status = "fail" if error_count else "warnings" if warning_count else "pass"
    validation = {
        "schema_version": DATASET_SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "validated_at": validated_at,
        "status": status,
        "candidate_count": len(candidates),
        "reviewed_count": len(reviewed),
        "comparable_reviewed_count": comparable_count,
        "plot_eligible_count": comparable_count,
        "error_count": error_count,
        "warning_count": warning_count,
        "findings": findings,
        "reviewed_only_rule": "Only accepted/edited and comparable records are plot eligible.",
    }
    if write_report:
        write_yaml(dataset_root / "validation.yml", validation)
    return validation


def plot_literature_data(
    root: Path,
    *,
    dataset_id: str,
    confirmed: bool = False,
    created_at: str | None = None,
) -> dict[str, Any]:
    if not confirmed:
        return {"status": "needs_confirmation", "dataset_id": dataset_id, "next_action": "Confirm reviewed-only plotting."}
    created_at = created_at or EARecord.now_iso()
    dataset_root = _dataset_root(root, dataset_id)
    spec = read_yaml(dataset_root / "extraction_spec.yml")
    reviewed = read_yaml(dataset_root / "reviewed_dataset.yml").get("records") or []
    eligible = [record for record in reviewed if record.get("comparison_status") == "comparable" and record.get("normalized_value") is not None]
    if not eligible:
        raise ValueError("No reviewed, comparable records are eligible for plotting")
    units = {record["normalized_unit"] for record in eligible}
    if len(units) != 1:
        raise ValueError("Plot-eligible records must share one normalized unit")
    plots = dataset_root / "plots"
    plots.mkdir(parents=True, exist_ok=True)
    source_data = plots / "source_data.csv"
    _write_csv(source_data, eligible)
    figure_id = f"fig-{_slug(dataset_id)}-property-001"
    png_path = plots / f"{figure_id}.png"
    svg_path = plots / f"{figure_id}.svg"
    apply_figure_style()
    import matplotlib.pyplot as plt

    labels = [str(record["source"]["paper_title"])[:28] or record["record_id"] for record in eligible]
    values = [float(record["normalized_value"]) for record in eligible]
    fig, ax = plt.subplots(figsize=(max(6.2, len(values) * 0.62), 4.4))
    ax.scatter(range(len(values)), values, color="#007C91", edgecolor="#222222", linewidth=0.5, s=42)
    ax.set_xticks(range(len(values)), labels, rotation=35, ha="right")
    ax.set_ylabel(f"{spec['property_name']} ({next(iter(units))})")
    ax.set_title(f"Reviewed {spec['property_name']} evidence")
    ax.grid(axis="y", color="#D9D9D9", linewidth=0.6)
    fig.tight_layout()
    fig.savefig(png_path, dpi=300, bbox_inches="tight")
    fig.savefig(svg_path, bbox_inches="tight")
    plt.close(fig)
    metadata = {
        "schema_version": DATASET_SCHEMA_VERSION,
        "figure_id": figure_id,
        "created_at": created_at,
        "dataset_id": dataset_id,
        "record_ids": [record["record_id"] for record in eligible],
        "source_data_ref": _relative(root, source_data),
        "normalized_unit": next(iter(units)),
        "reviewed_only": True,
        "limitations": ["Records marked not comparable, conflicting, deferred, rejected, or unreviewed are excluded."],
    }
    metadata_path = plots / f"{figure_id}.yml"
    write_yaml(metadata_path, metadata)
    register_figure(
        root,
        figure_id=figure_id,
        path=_relative(root, png_path),
        report_id=None,
        result_id=dataset_id,
        raw_data_ids=[],
        sample_ids=[],
        generation={"workflow": "literature_data_plot_beta", "created_at": created_at, "reviewed_only": True},
        caption=f"Reviewed {spec['property_name']} records from the literature evidence dataset.",
        purpose="cross-paper reviewed property comparison",
        style_profile=NATURE_LIKE_STYLE_PROFILE,
        source_data_refs=[_relative(root, source_data), _relative(root, dataset_root / "reviewed_dataset.yml")],
    )
    return {
        "status": "plot_ready",
        "maturity": "beta",
        "dataset_id": dataset_id,
        "figure_id": figure_id,
        "plotted_record_count": len(eligible),
        "excluded_record_count": len(reviewed) - len(eligible),
        "figure_ref": _relative(root, png_path),
        "source_data_ref": _relative(root, source_data),
        "metadata_ref": _relative(root, metadata_path),
    }


def _report_markdown(spec: dict[str, Any], validation: dict[str, Any], reviewed: list[dict[str, Any]]) -> str:
    lines = [
        f"# Reviewed Literature Dataset: {spec['dataset_id']}",
        "",
        f"Maturity: `beta` | property: `{spec['property_kind']}` | material: {spec['material_name']}",
        "",
        f"Reviewed records: {len(reviewed)} | comparable: {validation['comparable_reviewed_count']} | validation: `{validation['status']}`",
        "",
        "| Record | Material | Reported | Normalized | Conditions | DOI | Evidence | Comparable |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for record in reviewed:
        conditions = record["conditions"]
        values = [
            record["record_id"],
            record["material_name"],
            f"{record['reported_value']} {record['reported_unit']}",
            f"{record['normalized_value']} {record['normalized_unit']}",
            f"T={conditions['temperature']}; {conditions['direction']}; {conditions['instrument_or_method']}",
            record["source"]["doi"],
            f"p.{record['evidence']['page']} / {record['evidence']['chunk_anchor']}",
            record["comparison_status"],
        ]
        lines.append("| " + " | ".join(str(value).replace("|", "\\|").replace("\n", " ") for value in values) + " |")
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "- Values are included only after explicit review; this beta workflow does not establish scientific truth or exhaustive coverage.",
            "- Missing, ambiguous, conflicting, and not-comparable conditions remain explicit.",
            "- Evidence contexts are short anchors, not substitutes for reading the source paper.",
            "",
        ]
    )
    return "\n".join(lines)


def export_literature_data(
    root: Path,
    *,
    dataset_id: str,
    confirmed: bool = False,
    exported_at: str | None = None,
) -> dict[str, Any]:
    if not confirmed:
        return {"status": "needs_confirmation", "dataset_id": dataset_id, "next_action": "Confirm reviewed dataset export."}
    exported_at = exported_at or EARecord.now_iso()
    dataset_root = _dataset_root(root, dataset_id)
    spec = read_yaml(dataset_root / "extraction_spec.yml")
    reviewed = read_yaml(dataset_root / "reviewed_dataset.yml").get("records") or []
    validation = validate_literature_data(root, dataset_id=dataset_id, write_report=True, validated_at=exported_at)
    if validation["error_count"]:
        raise ValueError("Reviewed dataset has validation errors; repair them before export")
    report_path = dataset_root / "report.md"
    atomic_write_text(report_path, _report_markdown(spec, validation, reviewed))
    files = [
        dataset_root / "extraction_spec.yml",
        dataset_root / "reviewed_dataset.yml",
        dataset_root / "reviewed_dataset.csv",
        dataset_root / "validation.yml",
        report_path,
    ]
    files.extend(sorted((dataset_root / "plots").glob("*")))
    files = [path for path in files if path.is_file()]
    manifest = {
        "schema_version": DATASET_SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "exported_at": exported_at,
        "maturity": "beta",
        "reviewed_record_count": len(reviewed),
        "files": [{"path": path.relative_to(dataset_root).as_posix(), "sha256": _sha256(path)} for path in files],
        "excluded": ["raw PDFs", "private full text", "cookies", "credentials", "absolute source paths", "unreviewed candidate records"],
    }
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", manifest_bytes)
        for path in files:
            archive.write(path, arcname=path.relative_to(dataset_root).as_posix())
    export_dir = root / "exports" / "literature-data"
    archive_path = export_dir / f"{dataset_id}-reviewed.zip"
    atomic_write_bytes(archive_path, buffer.getvalue())
    checksum = hashlib.sha256(buffer.getvalue()).hexdigest()
    atomic_write_text(archive_path.with_suffix(".zip.sha256"), f"{checksum}  {archive_path.name}\n")
    return {
        "status": "export_ready",
        "maturity": "beta",
        "dataset_id": dataset_id,
        "reviewed_record_count": len(reviewed),
        "validation_status": validation["status"],
        "archive_ref": _relative(root, archive_path),
        "sha256": checksum,
        "report_ref": _relative(root, report_path),
        "next_action": "Share the reviewed bundle with its beta limitations and checksum.",
    }
