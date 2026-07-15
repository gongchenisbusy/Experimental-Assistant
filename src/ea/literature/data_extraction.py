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

from ea.figures import NATURE_LIKE_STYLE_PROFILE, register_figure, source_data_entry
from ea.literature.data_schema import (
    LITERATURE_DATA_SCHEMA_VERSION,
    NUMERIC_FIELD_TYPES,
    LiteratureDataSchemaError,
    builtin_schema,
    literature_data_schema_hash,
    load_literature_data_schema,
    request_schema,
    schema_field,
    validate_literature_data_schema_payload,
)
from ea.figures.style import apply_figure_style
from ea.errors import ReviewRequiredError
from ea.provenance import write_provenance_entry
from ea.schema.models import EARecord
from ea.storage.files import (
    atomic_write_bytes,
    atomic_write_text,
    read_yaml,
    write_yaml,
)


DATASET_SCHEMA_VERSION = LITERATURE_DATA_SCHEMA_VERSION
REVIEW_DECISIONS = {"accept", "reject", "edit", "defer", "not_comparable"}
NOT_REPORTED = "not_reported"

NUMBER_PATTERN = r"[+-]?(?:\d+(?:,\d{3})*|\d*\.\d+)(?:\.\d+)?(?:\s*[x×]\s*10\s*\^?\s*[+-]?\d+|[eE][+-]?\d+)?"
VALUE_PATTERN = re.compile(rf"(?P<value>{NUMBER_PATTERN})")


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:64] or "dataset"


def _dataset_root(root: Path, dataset_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}", dataset_id):
        raise ValueError(
            "dataset_id must use only letters, numbers, dot, underscore, or hyphen"
        )
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
                "zotero_item_key": item.get("zotero_item_key")
                or result.get("item_key"),
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
                "source_type": "cache"
                if path.is_dir()
                else "pdf"
                if path.suffix.lower() == ".pdf"
                else "searchable_text",
                "source_path": str(path.resolve()),
                "source_hash": _sha256(path),
                "availability": "available" if path.exists() else "missing",
                "title": entry.get("title") or metadata.get("title") or path.stem,
                "doi": entry.get("doi") or metadata.get("doi"),
                "reference_id": metadata.get("reference_id"),
                "zotero_item_key": entry.get("zotero_item_key")
                or metadata.get("item_key")
                or metadata.get("zotero_item_key"),
                "cache_identity": metadata.get("pdf_sha256")
                or metadata.get("source_hash")
                or _sha256(path),
            }
        )
    return records


def plan_literature_data_extraction(
    root: Path,
    *,
    property_name: str | None = None,
    property_kind: str | None = None,
    material_name: str | None = None,
    schema_path: Path | None = None,
    schema_payload: dict[str, Any] | None = None,
    field_type: str = "number",
    allowed_units: Iterable[str] = (),
    aliases: Iterable[str] = (),
    sources: Iterable[Path] = (),
    required_conditions: Iterable[str] = (),
    comparability_rules: Iterable[str] = (),
    dataset_id: str | None = None,
    confirmed: bool = False,
    created_at: str | None = None,
) -> dict[str, Any]:
    if schema_path is not None and schema_payload is not None:
        raise LiteratureDataSchemaError(
            "Provide either schema_path or schema_payload, not both."
        )
    if schema_path is not None:
        resolved_schema_path = schema_path if schema_path.is_absolute() else root / schema_path
        schema, schema_hash = load_literature_data_schema(resolved_schema_path)
    elif schema_payload is not None:
        validated = validate_literature_data_schema_payload(schema_payload)
        if validated["status"] != "pass":
            first = validated["errors"][0]
            raise LiteratureDataSchemaError(
                f"{first['code']} at {first['path']}: {first['message']} Next action: {first['next_action']}"
            )
        schema = validated["schema"]
        schema_hash = str(validated["schema_hash"])
    else:
        if not property_name:
            raise LiteratureDataSchemaError(
                "property_name is required when no literature-data schema is supplied"
            )
        schema = request_schema(
            property_name=property_name,
            property_kind=property_kind,
            material_scope=material_name or "materials",
            field_type=field_type,
            allowed_units=allowed_units,
            required_conditions=required_conditions,
            comparability_rules=comparability_rules,
            aliases=aliases,
        )
        validated = validate_literature_data_schema_payload(schema)
        if validated["status"] != "pass":
            first = validated["errors"][0]
            raise LiteratureDataSchemaError(
                f"{first['code']} at {first['path']}: {first['message']} Next action: {first['next_action']}"
            )
        schema = validated["schema"]
        schema_hash = str(validated["schema_hash"])

    primary_field_id = str(schema["primary_field_id"])
    primary_field = schema_field(schema, primary_field_id)
    property_kind = primary_field_id
    property_name = str(
        (primary_field.get("name") or {}).get("en") or primary_field_id
    )
    material_name = material_name or str(schema.get("material_scope") or "materials")
    created_at = created_at or EARecord.now_iso()
    dataset_id = dataset_id or f"{_slug(str(schema['schema_id']))}-{_slug(material_name)}"
    dataset_root = _dataset_root(root, dataset_id)
    source_records = _source_records(root, sources)
    preview = {
        "status": "ready_to_create"
        if source_records
        else "scope_defined_needs_sources",
        "dataset_id": dataset_id,
        "property_kind": property_kind,
        "primary_field_id": primary_field_id,
        "schema_id": schema["schema_id"],
        "schema_hash": schema_hash,
        "schema_source": schema["source"],
        "field_count": len(schema["fields"]),
        "fields": [
            {
                "field_id": field["field_id"],
                "name": field["name"],
                "type": field["type"],
                "unit": field.get("unit"),
                "required_conditions": field.get("required_conditions") or [],
                "comparability": field.get("comparability") or {},
                "minimum_evidence": (field.get("evidence") or {}).get(
                    "minimum_anchors"
                )
                or [],
            }
            for field in schema["fields"]
        ],
        "material_name": material_name,
        "source_count": len(source_records),
        "requires_confirmation": not confirmed,
        "next_action": "Confirm creation, then run data-extract."
        if source_records
        else "Add searchable PDF/cache sources.",
    }
    if not confirmed:
        return preview
    spec_path = dataset_root / "extraction_spec.yml"
    if spec_path.exists():
        existing = read_yaml(spec_path)
        if existing.get("schema_hash") != schema_hash:
            state_path = dataset_root / "extraction_state.compact.yml"
            if confirmed and state_path.exists():
                state = read_yaml(state_path)
                state.update(
                    {
                        "status": "migration_required",
                        "updated_at": created_at,
                        "pending_schema_hash": schema_hash,
                        "next_action": "Create a migration plan or choose a new dataset_id; the existing dataset was not reinterpreted.",
                    }
                )
                write_yaml(state_path, state)
            return {
                **preview,
                "status": "migration_required"
                if confirmed
                else "schema_change_requires_confirmation",
                "requires_confirmation": not confirmed,
                "existing_schema_hash": existing.get("schema_hash"),
                "next_action": "Create a migration plan or choose a new dataset_id; do not reinterpret existing records in place.",
            }
        if existing.get("material_name") != material_name:
            raise ValueError(f"Dataset already exists with a different scope: {dataset_id}")
        state = read_yaml(dataset_root / "extraction_state.compact.yml")
        return {
            **preview,
            "status": "existing_plan_reused",
            "state": state.get("status"),
            "dataset_ref": _relative(root, dataset_root),
        }
    dataset_root.mkdir(parents=True, exist_ok=True)
    (dataset_root / "evidence").mkdir(exist_ok=True)
    (dataset_root / "plots").mkdir(exist_ok=True)
    schema_ref = "literature_data_schema.yml"
    write_yaml(dataset_root / schema_ref, schema)
    primary_unit = primary_field.get("unit") or {}
    spec = {
        "schema_version": DATASET_SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "maturity": "beta",
        "created_at": created_at,
        "property_name": property_name,
        "property_kind": property_kind,
        "primary_field_id": primary_field_id,
        "literature_data_schema_version": schema["schema_version"],
        "literature_data_schema_id": schema["schema_id"],
        "schema_ref": schema_ref,
        "schema_hash": schema_hash,
        "schema_source": schema["source"],
        "material_name": material_name,
        "required_conditions": primary_field.get("required_conditions") or [],
        "comparability_rules": (primary_field.get("comparability") or {}).get(
            "rules"
        )
        or [],
        "accepted_reported_units": primary_unit.get("allowed") or [],
        "normalized_units": [primary_unit["canonical"]]
        if primary_unit.get("canonical")
        else [],
        "boundaries": [
            "Only lawful user-provided or verified cached full text may be processed.",
            "Automatic values are candidates until explicit record review.",
            "Schema fields are never silently mapped to a different built-in or user-defined field.",
            "Complex figure digitization and bulk OCR are outside this beta workflow.",
        ],
    }
    source_manifest = {
        "schema_version": DATASET_SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "schema_hash": schema_hash,
        "source_count": len(source_records),
        "sources": source_records,
    }
    state = {
        "schema_version": DATASET_SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "schema_hash": schema_hash,
        "status": "sources_selected" if source_records else "scope_defined",
        "updated_at": created_at,
        "checkpoints": {},
        "metrics": {
            "papers_processed": 0,
            "pages_read": 0,
            "chunks_read": 0,
            "candidate_count": 0,
            "output_bytes": 0,
            "artifact_bytes": 0,
        },
        "next_action": "Run `ea literature data-extract`.",
    }
    write_yaml(spec_path, spec)
    write_yaml(dataset_root / "source_manifest.yml", source_manifest)
    write_yaml(dataset_root / "extraction_state.compact.yml", state)
    return {
        **preview,
        "status": state["status"],
        "requires_confirmation": False,
        "dataset_ref": _relative(root, dataset_root),
        "schema_ref": _relative(root, dataset_root / schema_ref),
    }


def _documents_from_jsonl(path: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for index, line in enumerate(
        path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
    ):
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
                "chunk_id": item.get("chunk_id")
                or item.get("id")
                or f"chunk-{index:04d}",
            }
        )
    return docs


def _documents_from_pdf(path: Path) -> list[dict[str, Any]]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - package dependency provides pypdf
        raise RuntimeError(
            "pypdf is required for direct PDF input; alternatively provide a verified searchable cache"
        ) from exc
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
            raise FileNotFoundError(
                f"Searchable cache has no chunks.jsonl or paper.md: {path}"
            )
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


def _context_value(pattern: str, text: str, group: int | str = 1) -> Any:
    match = re.search(pattern, text, flags=re.I)
    return match.group(group) if match else NOT_REPORTED


def _conditions(text: str) -> dict[str, Any]:
    temperature = re.search(r"([+-]?\d+(?:\.\d+)?)\s*(K|°C|C)\b", text, flags=re.I)
    method = (
        "four_probe"
        if re.search(r"four[- ]?probe|4[- ]?probe", text, re.I)
        else "two_probe"
        if re.search(r"two[- ]?probe|2[- ]?probe", text, re.I)
        else "tauc_analysis"
        if re.search(r"\btauc\b", text, re.I)
        else "x_ray_diffraction"
        if re.search(r"\bx[- ]?ray|\bxrd\b", text, re.I)
        else "raman_spectroscopy"
        if re.search(r"\braman\b", text, re.I)
        else NOT_REPORTED
    )
    direction = (
        "in_plane"
        if re.search(r"in[- ]?plane", text, re.I)
        else "out_of_plane"
        if re.search(r"out[- ]?of[- ]?plane|cross[- ]?plane", text, re.I)
        else NOT_REPORTED
    )
    return {
        "temperature": f"{temperature.group(1)} {temperature.group(2)}"
        if temperature
        else NOT_REPORTED,
        "pressure": _context_value(
            r"([+-]?\d+(?:\.\d+)?\s*(?:Pa|kPa|MPa|GPa|bar|atm))\b", text
        ),
        "frequency": _context_value(
            r"([+-]?\d+(?:\.\d+)?\s*(?:Hz|kHz|MHz|GHz))\b", text
        ),
        "direction": direction,
        "geometry": _context_value(
            r"\b(van der pauw|hall bar|transmission line|TLM)\b", text
        ),
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
        "contacts": _context_value(
            r"\b(Au|Ti/Au|Cr/Au|Pt|Ag|graphene)\s+contacts?\b", text
        ),
        "doping": _context_value(r"\b([np])[- ]?doped\b", text),
        "defects": NOT_REPORTED,
        "strain": _context_value(r"([+-]?\d+(?:\.\d+)?\s*%\s*strain)\b", text),
        "environment": _context_value(r"\b(vacuum|air|nitrogen|argon|ambient)\b", text),
    }
    return identity, context


def _property_sentences(text: str, aliases: Iterable[str]) -> list[str]:
    normalized_aliases = [str(alias).lower() for alias in aliases if str(alias)]
    sentences = re.split(r"(?<=[.!?。！？])\s+|[\r\n]+", text)
    return [
        sentence.strip()
        for sentence in sentences
        if sentence.strip()
        and any(alias in sentence.lower() for alias in normalized_aliases)
    ]


def _schema_for_dataset(
    dataset_root: Path, spec: dict[str, Any]
) -> tuple[dict[str, Any], str]:
    schema_ref = spec.get("schema_ref")
    if schema_ref:
        schema_path = dataset_root / str(schema_ref)
        schema, current_hash = load_literature_data_schema(schema_path)
        expected_hash = str(spec.get("schema_hash") or "")
        if expected_hash and current_hash != expected_hash:
            raise LiteratureDataSchemaError(
                "literature_data_schema_changed: the dataset schema hash no longer matches the confirmed extraction spec; restore it or create a new dataset ID with the revised schema"
            )
        return schema, current_hash
    property_kind = str(spec.get("property_kind") or "")
    schema = builtin_schema(
        property_kind,
        property_name=str(spec.get("property_name") or property_kind),
        material_scope=str(spec.get("material_name") or "materials"),
        required_conditions=spec.get("required_conditions") or [],
        comparability_rules=spec.get("comparability_rules") or [],
    )
    return schema, literature_data_schema_hash(schema)


def _field_aliases(field: dict[str, Any]) -> list[str]:
    name = field.get("name") or {}
    return list(
        dict.fromkeys(
            [
                *(str(value) for value in field.get("aliases") or []),
                str(name.get("en") or ""),
                str(name.get("zh") or ""),
            ]
        )
    )


def _field_tail(sentence: str, field: dict[str, Any]) -> str:
    lowered = sentence.lower()
    positions: list[tuple[int, int]] = []
    for alias in _field_aliases(field):
        if not alias:
            continue
        index = lowered.find(alias.lower())
        if index >= 0:
            positions.append((index, index + len(alias)))
    if not positions:
        return sentence
    _, end = min(positions)
    return sentence[end:]


def _schema_unit_rule(
    field: dict[str, Any], reported_unit: str
) -> tuple[str, float, str] | None:
    unit = field.get("unit") or {}
    rules = unit.get("conversions") or {}
    normalized_key = re.sub(
        r"\s+",
        " ",
        reported_unit.strip().lower().replace("Ω", "ω").replace("Ω", "ω"),
    )
    for key, rule in rules.items():
        candidate = re.sub(
            r"\s+",
            " ",
            str(key).strip().lower().replace("Ω", "ω").replace("Ω", "ω"),
        )
        if candidate != normalized_key or not isinstance(rule, dict):
            continue
        return (
            str(rule.get("canonical") or unit.get("canonical") or reported_unit),
            float(rule.get("factor", 1.0)),
            str(rule.get("formula") or f"reported_value * {rule.get('factor', 1.0)}"),
        )
    return None


def _schema_numeric_match(
    sentence: str, field: dict[str, Any]
) -> dict[str, Any] | None:
    tail = _field_tail(sentence, field)
    field_type = str(field.get("type"))
    unit = field.get("unit") or {}
    allowed = sorted((str(value) for value in unit.get("allowed") or []), key=len, reverse=True)
    unit_pattern = "|".join(re.escape(value) for value in allowed)
    optional_unit = (
        rf"(?:\s*(?P<unit>{unit_pattern})(?![A-Za-z0-9]))?"
        if unit_pattern
        else r"(?:\s*(?P<unit>[A-Za-zµμΩω°/%][A-Za-z0-9µμΩω°/().^ -]{0,24}))?"
    )
    if field_type == "range":
        match = re.search(
            rf"(?P<low>{NUMBER_PATTERN})\s*(?:-|–|—|to)\s*(?P<high>{NUMBER_PATTERN}){optional_unit}",
            tail,
            flags=re.I,
        )
        if not match:
            return None
        low = _parse_number(match.group("low"))
        high = _parse_number(match.group("high"))
        reported_unit = (match.groupdict().get("unit") or NOT_REPORTED).strip()
        rule = _schema_unit_rule(field, reported_unit) if reported_unit != NOT_REPORTED else None
        if rule:
            normalized_unit, factor, formula = rule
            normalized = [low * factor, high * factor]
            status = "converted" if factor != 1.0 else "identity"
        else:
            normalized_unit = NOT_REPORTED
            normalized = None
            formula = "not_available"
            status = "missing_unit" if reported_unit == NOT_REPORTED else "unsupported"
        return {
            "type": field_type,
            "reported_value": [low, high],
            "reported_unit": reported_unit,
            "range": {"low": low, "high": high},
            "uncertainty": NOT_REPORTED,
            "normalized_value": normalized,
            "normalized_unit": normalized_unit,
            "conversion_formula": formula,
            "conversion_status": status,
        }
    if field_type == "uncertain_number":
        match = re.search(
            rf"(?P<value>{NUMBER_PATTERN})\s*(?:±|\+/-)\s*(?P<uncertainty>{NUMBER_PATTERN}){optional_unit}",
            tail,
            flags=re.I,
        )
        if not match:
            return None
        value = _parse_number(match.group("value"))
        uncertainty = _parse_number(match.group("uncertainty"))
        reported_unit = (match.groupdict().get("unit") or NOT_REPORTED).strip()
        rule = _schema_unit_rule(field, reported_unit) if reported_unit != NOT_REPORTED else None
        if rule:
            normalized_unit, factor, formula = rule
            normalized: Any = value * factor
            normalized_uncertainty: Any = uncertainty * abs(factor)
            status = "converted" if factor != 1.0 else "identity"
        else:
            normalized_unit = NOT_REPORTED
            normalized = None
            normalized_uncertainty = None
            formula = "not_available"
            status = "missing_unit" if reported_unit == NOT_REPORTED else "unsupported"
        return {
            "type": field_type,
            "reported_value": value,
            "reported_unit": reported_unit,
            "range": NOT_REPORTED,
            "uncertainty": uncertainty,
            "normalized_value": normalized,
            "normalized_uncertainty": normalized_uncertainty,
            "normalized_unit": normalized_unit,
            "conversion_formula": formula,
            "conversion_status": status,
        }
    match = re.search(
        VALUE_PATTERN.pattern + optional_unit,
        tail,
        flags=re.I,
    )
    if not match:
        return None
    value = _parse_number(match.group("value"))
    reported_unit = (match.groupdict().get("unit") or NOT_REPORTED).strip()
    rule = _schema_unit_rule(field, reported_unit) if reported_unit != NOT_REPORTED else None
    if rule:
        normalized_unit, factor, formula = rule
        normalized = value * factor
        status = "converted" if factor != 1.0 else "identity"
    elif not allowed and bool(unit.get("unknown_allowed")):
        normalized_unit = reported_unit
        normalized = value
        formula = "identity_unknown_unit"
        status = "unknown_unit_preserved"
    else:
        normalized_unit = NOT_REPORTED
        normalized = None
        formula = "not_available"
        status = "missing_unit" if reported_unit == NOT_REPORTED else "unsupported"
    return {
        "type": field_type,
        "reported_value": value,
        "reported_unit": reported_unit,
        "range": NOT_REPORTED,
        "uncertainty": NOT_REPORTED,
        "normalized_value": normalized,
        "normalized_unit": normalized_unit,
        "conversion_formula": formula,
        "conversion_status": status,
    }


def _schema_non_numeric_match(
    sentence: str, field: dict[str, Any]
) -> dict[str, Any] | None:
    field_type = str(field.get("type"))
    tail = re.sub(
        r"^\s*(?:was|were|is|are|of|=|:|为|是|包括|包含)\s*",
        "",
        _field_tail(sentence, field),
        flags=re.I,
    ).strip(" ;,:。")
    value: Any = None
    if field_type == "enum":
        for choice in field.get("choices") or []:
            if str(choice).lower() in sentence.lower():
                value = choice
                break
    elif field_type == "boolean":
        value = not bool(re.search(r"\b(?:not|no|absent|false)\b|未|无", tail, re.I))
    elif field_type == "date":
        match = re.search(r"\b\d{4}-\d{2}-\d{2}\b", tail)
        value = match.group(0) if match else None
    elif field_type == "datetime":
        match = re.search(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?\b", tail)
        value = match.group(0) if match else None
    elif field_type == "list":
        values = [
            part.strip(" ;,:。.\t")
            for part in re.split(r",|;|\band\b|、|，", tail, flags=re.I)
            if part.strip(" ;,:。.\t")
        ]
        value = values or None
    elif field_type == "nested":
        nested: dict[str, Any] = {}
        for child in field.get("children") or []:
            if not isinstance(child, dict):
                continue
            child_value = (
                _schema_numeric_match(sentence, child)
                if child.get("type") in NUMERIC_FIELD_TYPES
                else _schema_non_numeric_match(sentence, child)
            )
            if child_value is not None:
                nested[str(child.get("field_id"))] = child_value["reported_value"]
        value = nested or None
    else:
        value = tail or None
    if value is None:
        return None
    return {
        "type": field_type,
        "reported_value": value,
        "reported_unit": NOT_REPORTED,
        "range": NOT_REPORTED,
        "uncertainty": NOT_REPORTED,
        "normalized_value": value,
        "normalized_unit": NOT_REPORTED,
        "conversion_formula": "not_applicable",
        "conversion_status": "not_applicable",
    }


def _extract_field_value(
    sentence: str, field: dict[str, Any]
) -> dict[str, Any] | None:
    if not any(alias.lower() in sentence.lower() for alias in _field_aliases(field) if alias):
        return None
    if field.get("type") in NUMERIC_FIELD_TYPES:
        return _schema_numeric_match(sentence, field)
    return _schema_non_numeric_match(sentence, field)


def _extract_source_records(
    source: dict[str, Any],
    spec: dict[str, Any],
    schema: dict[str, Any],
    docs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    primary_field_id = str(schema["primary_field_id"])
    primary_field = schema_field(schema, primary_field_id)
    all_aliases = [alias for field in schema["fields"] for alias in _field_aliases(field)]
    for doc in docs:
        for sentence in _property_sentences(doc["text"], all_aliases):
            field_values = {
                str(field["field_id"]): value
                for field in schema["fields"]
                if (value := _extract_field_value(sentence, field)) is not None
            }
            if not field_values:
                continue
            primary_value = field_values.get(primary_field_id)
            if primary_value is None:
                primary_value = next(iter(field_values.values()))
            warnings: list[str] = []
            if (
                primary_field.get("type") in NUMERIC_FIELD_TYPES
                and primary_value["reported_unit"] == NOT_REPORTED
            ):
                warnings.append("missing_reported_unit")
            identity, context = _identity_context(sentence)
            conditions = _conditions(sentence)
            record_id = f"rec-{source['source_id']}-{len(records) + 1:03d}"
            records.append(
                {
                    "record_id": record_id,
                    "property_name": spec["property_name"],
                    "property_kind": primary_field_id,
                    "primary_field_id": primary_field_id,
                    "schema_id": schema["schema_id"],
                    "schema_hash": spec.get("schema_hash"),
                    "value_type": primary_value["type"],
                    "field_values": field_values,
                    "material_name": spec["material_name"],
                    **identity,
                    "reported_value": primary_value["reported_value"],
                    "reported_unit": primary_value["reported_unit"],
                    "range": primary_value.get("range", NOT_REPORTED),
                    "uncertainty": primary_value.get("uncertainty", NOT_REPORTED),
                    "qualifier": NOT_REPORTED,
                    "normalized_value": primary_value["normalized_value"],
                    "normalized_unit": primary_value["normalized_unit"],
                    "conversion_formula": primary_value["conversion_formula"],
                    "conversion_status": primary_value["conversion_status"],
                    "conditions": conditions,
                    "context": context,
                    "source": {
                        "doi": source.get("doi") or NOT_REPORTED,
                        "reference_id": source.get("reference_id") or NOT_REPORTED,
                        "zotero_item_key": source.get("zotero_item_key")
                        or NOT_REPORTED,
                        "cache_identity": source.get("cache_identity")
                        or source["source_hash"],
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
                        "extraction_origin": "schema_driven_searchable_text_pattern_v2",
                        "confidence": "medium"
                        if not warnings
                        else "low",
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


def _canonical_value_key(record: dict[str, Any]) -> tuple[str, str]:
    value = record.get("normalized_value")
    unit = record.get("normalized_unit")
    if value is None or unit in {None, NOT_REPORTED}:
        value = record.get("reported_value")
        unit = record.get("reported_unit")
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        str(unit or NOT_REPORTED).strip().lower(),
    )


def _mark_duplicates_and_conflicts(
    records: list[dict[str, Any]], primary_field: dict[str, Any]
) -> None:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    if str(primary_field.get("dedup_policy") or "source_field_value") == "none":
        return
    for record in records:
        doi = str(record["source"].get("doi") or "").lower()
        source_identity = (
            doi
            if doi and doi != NOT_REPORTED
            else str(
                record["source"].get("source_hash")
                or record["source"].get("source_id")
                or ""
            )
        )
        if source_identity:
            groups[(source_identity, record["property_kind"])].append(record)
    for grouped in groups.values():
        if len(grouped) < 2:
            continue
        for record in grouped:
            peers = [
                peer for peer in grouped if peer["record_id"] != record["record_id"]
            ]
            same = [
                peer["record_id"]
                for peer in peers
                if _canonical_value_key(peer) == _canonical_value_key(record)
            ]
            conflicts = [
                peer["record_id"] for peer in peers if peer["record_id"] not in same
            ]
            record["audit"]["duplicate_refs"] = same
            record["audit"]["conflict_refs"] = conflicts
            if (
                conflicts
                and "duplicate_doi_conflicting_evidence"
                not in record["audit"]["warnings"]
            ):
                record["audit"]["warnings"].append("duplicate_doi_conflicting_evidence")


CSV_FIELDS = [
    "record_id",
    "property_name",
    "property_kind",
    "schema_id",
    "schema_hash",
    "value_type",
    "field_values_json",
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
    "conditions_json",
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
                "schema_id": record.get("schema_id"),
                "schema_hash": record.get("schema_hash"),
                "value_type": record.get("value_type", "number"),
                "field_values_json": json.dumps(
                    record.get("field_values") or {},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "material_name": record["material_name"],
                "reported_value": record["reported_value"],
                "reported_unit": record["reported_unit"],
                "normalized_value": record["normalized_value"],
                "normalized_unit": record["normalized_unit"],
                "conversion_formula": record["conversion_formula"],
                "conversion_status": record["conversion_status"],
                "temperature": record.get("conditions", {}).get(
                    "temperature", NOT_REPORTED
                ),
                "direction": record.get("conditions", {}).get(
                    "direction", NOT_REPORTED
                ),
                "instrument_or_method": record.get("conditions", {}).get(
                    "instrument_or_method", NOT_REPORTED
                ),
                "conditions_json": json.dumps(
                    record.get("conditions") or {},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
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


def _review_package(
    dataset_root: Path, records: list[dict[str, Any]], updated_at: str
) -> None:
    pending = [
        record
        for record in records
        if record["audit"]["review_state"] in {"candidate", "deferred"}
    ]
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
        "boundaries": [
            "Only accepted or edited records can enter the reviewed dataset; plot eligibility also requires comparability."
        ],
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
        lines.append(
            "| "
            + " | ".join(
                str(value).replace("|", "\\|").replace("\n", " ") for value in values
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "Unreviewed candidates cannot enter plots, statistics, reports, or durable memory.",
            "",
        ]
    )
    atomic_write_text(dataset_root / "review_package.md", "\n".join(lines))


def _artifact_bytes(dataset_root: Path) -> int:
    return sum(
        path.stat().st_size for path in dataset_root.rglob("*") if path.is_file()
    )


def extract_literature_data(
    root: Path,
    *,
    dataset_id: str,
    max_sources: int | None = None,
    confirmed: bool = False,
    extracted_at: str | None = None,
) -> dict[str, Any]:
    if not confirmed:
        return {
            "status": "needs_confirmation",
            "dataset_id": dataset_id,
            "next_action": "Rerun with explicit confirmation.",
        }
    extracted_at = extracted_at or EARecord.now_iso()
    dataset_root = _dataset_root(root, dataset_id)
    spec = read_yaml(dataset_root / "extraction_spec.yml")
    manifest = read_yaml(dataset_root / "source_manifest.yml")
    state_path = dataset_root / "extraction_state.compact.yml"
    state = read_yaml(state_path)
    try:
        schema, schema_hash = _schema_for_dataset(dataset_root, spec)
    except LiteratureDataSchemaError as exc:
        state.update(
            {
                "status": "migration_required",
                "updated_at": extracted_at,
                "error_code": "literature_data_schema_changed",
                "error": str(exc),
                "next_action": "Restore the confirmed schema, or run data-plan with a new dataset ID and the revised schema.",
            }
        )
        write_yaml(state_path, state)
        return {
            "status": state["status"],
            "dataset_id": dataset_id,
            "error_code": state["error_code"],
            "next_action": state["next_action"],
        }
    primary_field = schema_field(schema, str(schema["primary_field_id"]))
    candidate_path = dataset_root / "candidate_records.yml"
    records = (
        (read_yaml(candidate_path).get("records") or [])
        if candidate_path.exists()
        else []
    )
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
        if (
            checkpoint.get("status") == "completed"
            and checkpoint.get("source_hash") == source_hash
            and checkpoint.get("schema_hash", schema_hash) == schema_hash
        ):
            skipped += 1
            continue
        records = [
            record
            for record in records
            if record["source"]["source_id"] != source["source_id"]
        ]
        attempted_now += 1
        try:
            docs = _source_documents({**source, "source_hash": source_hash})
            if not any(str(doc.get("text") or "").strip() for doc in docs):
                raise RuntimeError("source_has_no_searchable_text_ocr_required")
            source_records = _extract_source_records(
                {**source, "source_hash": source_hash}, spec, schema, docs
            )
            records.extend(source_records)
            write_yaml(
                dataset_root / "evidence" / f"{source['source_id']}.yml",
                {
                    "schema_version": DATASET_SCHEMA_VERSION,
                    "literature_data_schema_id": schema["schema_id"],
                    "schema_hash": schema_hash,
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
                "schema_hash": schema_hash,
                "processed_at": extracted_at,
                "pages_or_chunks_read": len(docs),
                "candidate_count": len(source_records),
            }
            processed_now += 1
            state["metrics"]["pages_read"] = int(
                state["metrics"].get("pages_read", 0)
            ) + len({str(doc.get("page")) for doc in docs})
            state["metrics"]["chunks_read"] = int(
                state["metrics"].get("chunks_read", 0)
            ) + len(docs)
        except Exception as exc:
            error_text = str(exc)
            checkpoints[source["source_id"]] = {
                "status": "failed",
                "source_hash": source_hash,
                "schema_hash": schema_hash,
                "processed_at": extracted_at,
                "error_code": "ocr_required"
                if "ocr_required" in error_text
                else "source_unreadable_or_unsearchable",
                "error": error_text[:300],
                "safe_to_retry": True,
            }
            failures += 1
        _mark_duplicates_and_conflicts(records, primary_field)
        write_yaml(
            candidate_path,
            {
                "schema_version": DATASET_SCHEMA_VERSION,
                "dataset_id": dataset_id,
                "literature_data_schema_id": schema["schema_id"],
                "schema_hash": schema_hash,
                "records": records,
            },
        )
        _write_csv(dataset_root / "candidate_records.csv", records)
        _review_package(dataset_root, records, extracted_at)
        state["updated_at"] = extracted_at
        state["metrics"]["papers_processed"] = sum(
            item.get("status") == "completed" for item in checkpoints.values()
        )
        state["metrics"]["candidate_count"] = len(records)
        state["status"] = "needs_review" if records else "fulltext_ready"
        state["next_action"] = (
            "Review candidate records with `ea literature data-review`."
            if records
            else "Resolve source failures or add sources."
        )
        state["metrics"]["artifact_bytes"] = _artifact_bytes(dataset_root)
        write_yaml(state_path, state)
    provenance = None
    if attempted_now:
        provenance = write_provenance_entry(
            root,
            workflow="literature_data_extraction_beta",
            inputs={
                "records": [],
                "files": [_relative(root, dataset_root / "source_manifest.yml")],
            },
            outputs={
                "records": [record["record_id"] for record in records],
                "files": [_relative(root, candidate_path)],
            },
            parameters={
                "dataset_id": dataset_id,
                "property_kind": spec["property_kind"],
                "schema_id": schema["schema_id"],
                "schema_hash": schema_hash,
                "max_sources": max_sources,
            },
            warnings=[
                checkpoint
                for checkpoint in checkpoints.values()
                if checkpoint.get("status") == "failed"
            ],
            created_at=extracted_at,
        )
    state["metrics"]["output_bytes"] = sum(
        path.stat().st_size
        for path in (
            candidate_path,
            dataset_root / "candidate_records.csv",
            dataset_root / "review_package.yml",
        )
        if path.exists()
    )
    state["metrics"]["artifact_bytes"] = _artifact_bytes(dataset_root)
    write_yaml(state_path, state)
    return {
        "status": state["status"],
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


def _comparison_status(
    record: dict[str, Any],
    spec: dict[str, Any],
    primary_field: dict[str, Any] | None = None,
) -> str:
    if record["audit"]["review_state"] == "not_comparable":
        return "not_comparable_by_review"
    value_type = str(
        record.get("value_type")
        or (primary_field or {}).get("type")
        or "number"
    )
    if value_type in NUMERIC_FIELD_TYPES:
        if record.get("normalized_value") is None or record.get(
            "normalized_unit"
        ) in {None, NOT_REPORTED}:
            return "not_comparable_missing_normalized_value"
    comparability = (primary_field or {}).get("comparability") or {}
    if comparability.get("enabled") is False:
        return "not_comparable_by_schema"
    missing = [
        name
        for name in spec.get("required_conditions") or []
        if record.get("conditions", {}).get(name, NOT_REPORTED) == NOT_REPORTED
    ]
    if missing:
        return "not_comparable_missing_conditions:" + ",".join(missing)
    if record["audit"].get("conflict_refs"):
        conflict_policy = str(
            (primary_field or {}).get("conflict_policy") or "preserve"
        )
        if conflict_policy == "prefer_reviewed" and record["audit"].get(
            "review_state"
        ) in {"accepted", "edited"}:
            return "comparable"
        if conflict_policy == "reject_conflict":
            return "not_comparable_conflict_rejected"
        return "not_comparable_conflicting_evidence"
    return "comparable"


def _reviewed_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if record["audit"]["review_state"] in {"accepted", "edited"}
    ]


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
        return {
            "status": "needs_confirmation",
            "dataset_id": dataset_id,
            "record_id": record_id,
            "decision": decision,
        }
    reviewed_at = reviewed_at or EARecord.now_iso()
    dataset_root = _dataset_root(root, dataset_id)
    spec = read_yaml(dataset_root / "extraction_spec.yml")
    schema, schema_hash = _schema_for_dataset(dataset_root, spec)
    primary_field = schema_field(schema, str(schema["primary_field_id"]))
    candidate_path = dataset_root / "candidate_records.yml"
    payload = read_yaml(candidate_path)
    records = payload.get("records") or []
    try:
        record = next(item for item in records if item["record_id"] == record_id)
    except StopIteration as exc:
        raise KeyError(f"Unknown literature data record: {record_id}") from exc
    allowed_conditions = {
        str(name)
        for field in schema.get("fields") or []
        if isinstance(field, dict)
        for name in [
            *(field.get("required_conditions") or []),
            *(field.get("optional_conditions") or []),
        ]
    }
    unsupported_conditions = sorted(set(conditions or {}) - allowed_conditions)
    if unsupported_conditions:
        raise ValueError(
            "Unsupported reviewed condition(s): "
            + ", ".join(unsupported_conditions)
            + "; declare them in required_conditions or optional_conditions first"
        )
    if conditions:
        record.setdefault("conditions", {}).update(conditions)

    conflict_policy = str(primary_field.get("conflict_policy") or "preserve")
    if decision in {"accept", "edit"} and record["audit"].get("conflict_refs"):
        if conflict_policy == "reject_conflict":
            raise ValueError(
                "Conflicting evidence cannot be accepted under reject_conflict; reject, defer, or create a new reviewed resolution"
            )
        if conflict_policy == "prefer_reviewed":
            reviewed_conflicts = [
                peer["record_id"]
                for peer in records
                if peer["record_id"] in record["audit"]["conflict_refs"]
                and peer["audit"].get("review_state") in {"accepted", "edited"}
            ]
            if reviewed_conflicts:
                raise ValueError(
                    "A conflicting record is already preferred by review: "
                    + ", ".join(reviewed_conflicts)
                )
    if decision == "edit":
        edited_value_or_unit = any(
            value is not None
            for value in (
                reported_value,
                reported_unit,
                normalized_value,
                normalized_unit,
            )
        )
        if reported_value is not None:
            record["reported_value"] = reported_value
        if reported_unit is not None:
            record["reported_unit"] = reported_unit
        if normalized_value is not None:
            record["normalized_value"] = normalized_value
        if normalized_unit is not None:
            record["normalized_unit"] = normalized_unit
        if record.get("value_type", primary_field.get("type")) in NUMERIC_FIELD_TYPES and (
            record.get("normalized_value") is None
            or record.get("normalized_unit") in {None, NOT_REPORTED}
        ):
            raise ValueError(
                "Edited records need a reviewed normalized value and unit before acceptance"
            )
        record["conversion_status"] = "reviewer_edited"
        if edited_value_or_unit:
            record["conversion_formula"] = "reviewer_supplied_or_verified"
        primary_value = (record.get("field_values") or {}).get(
            str(schema["primary_field_id"])
        )
        if isinstance(primary_value, dict):
            primary_value.update(
                {
                    "reported_value": record.get("reported_value"),
                    "reported_unit": record.get("reported_unit"),
                    "normalized_value": record.get("normalized_value"),
                    "normalized_unit": record.get("normalized_unit"),
                    "conversion_formula": record.get("conversion_formula"),
                    "conversion_status": record.get("conversion_status"),
                }
            )
    if decision == "accept" and record.get(
        "value_type", primary_field.get("type")
    ) in NUMERIC_FIELD_TYPES and (
        record.get("normalized_value") is None
        or record.get("normalized_unit") in {None, NOT_REPORTED}
    ):
        raise ValueError(
            "A record with no reviewed normalized value/unit cannot be accepted; edit, defer, reject, or mark not-comparable"
        )
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
    record["comparison_status"] = _comparison_status(record, spec, primary_field)
    write_yaml(candidate_path, payload)
    _write_csv(dataset_root / "candidate_records.csv", records)
    reviewed = _reviewed_records(records)
    write_yaml(
        dataset_root / "reviewed_dataset.yml",
        {
            "schema_version": DATASET_SCHEMA_VERSION,
            "dataset_id": dataset_id,
            "literature_data_schema_id": schema["schema_id"],
            "schema_hash": schema_hash,
            "records": reviewed,
        },
    )
    _write_csv(dataset_root / "reviewed_dataset.csv", reviewed)
    _review_package(dataset_root, records, reviewed_at)
    pending = sum(
        record["audit"]["review_state"] in {"candidate", "deferred"}
        for record in records
    )
    state_path = dataset_root / "extraction_state.compact.yml"
    state = read_yaml(state_path)
    state.update(
        {
            "status": "reviewed_dataset_ready"
            if reviewed and not pending
            else "needs_review",
            "updated_at": reviewed_at,
            "reviewed_count": len(reviewed),
            "pending_review_count": pending,
            "next_action": "Run data-validate; plot/export only comparable reviewed records."
            if reviewed
            else "Continue reviewing candidates.",
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
    try:
        schema, schema_hash = _schema_for_dataset(dataset_root, spec)
    except LiteratureDataSchemaError as exc:
        validation = {
            "schema_version": DATASET_SCHEMA_VERSION,
            "dataset_id": dataset_id,
            "validated_at": validated_at,
            "status": "fail",
            "candidate_count": 0,
            "reviewed_count": 0,
            "comparable_reviewed_count": 0,
            "plot_eligible_count": 0,
            "error_count": 1,
            "warning_count": 0,
            "findings": [
                {
                    "severity": "error",
                    "code": "literature_data_schema_changed",
                    "message": str(exc),
                }
            ],
            "next_action": "Restore the confirmed schema, or run data-plan with a new dataset ID and the revised schema.",
        }
        if write_report:
            write_yaml(dataset_root / "validation.yml", validation)
        return validation
    primary_field = schema_field(schema, str(schema["primary_field_id"]))
    primary_type = str(primary_field["type"])
    candidates = read_yaml(dataset_root / "candidate_records.yml").get("records") or []
    reviewed_path = dataset_root / "reviewed_dataset.yml"
    reviewed = (
        read_yaml(reviewed_path).get("records") or [] if reviewed_path.exists() else []
    )
    findings: list[dict[str, Any]] = []
    record_ids = {record["record_id"] for record in candidates}
    for record in candidates:
        evidence = record.get("evidence") or {}
        if evidence.get("page") in {None, NOT_REPORTED} and evidence.get(
            "chunk_anchor"
        ) in {None, NOT_REPORTED}:
            findings.append(
                {
                    "severity": "error",
                    "code": "missing_evidence_anchor",
                    "record_id": record["record_id"],
                }
            )
        for ref in record.get("audit", {}).get("conflict_refs") or []:
            if ref not in record_ids:
                findings.append(
                    {
                        "severity": "error",
                        "code": "missing_conflict_reference",
                        "record_id": record["record_id"],
                        "ref": ref,
                    }
                )
        if record["audit"]["review_state"] in {"accepted", "edited"}:
            if primary_type in NUMERIC_FIELD_TYPES and (
                record.get("normalized_value") is None
                or record.get("normalized_unit") in {None, NOT_REPORTED}
            ):
                findings.append(
                    {
                        "severity": "error",
                        "code": "reviewed_record_missing_normalized_value",
                        "record_id": record["record_id"],
                    }
                )
            if record["property_kind"] != schema["primary_field_id"]:
                findings.append(
                    {
                        "severity": "error",
                        "code": "property_kind_mismatch",
                        "record_id": record["record_id"],
                    }
                )
            if record["comparison_status"] != "comparable":
                findings.append(
                    {
                        "severity": "warning",
                        "code": record["comparison_status"],
                        "record_id": record["record_id"],
                    }
                )
        elif record["audit"]["review_state"] in {"candidate", "deferred"}:
            findings.append(
                {
                    "severity": "info",
                    "code": "record_not_yet_reviewed",
                    "record_id": record["record_id"],
                }
            )
    error_count = sum(item["severity"] == "error" for item in findings)
    warning_count = sum(item["severity"] == "warning" for item in findings)
    comparable_count = sum(
        record.get("comparison_status") == "comparable" for record in reviewed
    )
    plot_config = primary_field.get("plot") or {}
    plot_supported = primary_type in NUMERIC_FIELD_TYPES | {
        "text",
        "enum",
        "boolean",
        "date",
        "datetime",
    }
    plot_eligible_count = (
        comparable_count
        if plot_config.get("enabled") and plot_supported
        else 0
    )
    status = "fail" if error_count else "warnings" if warning_count else "pass"
    validation = {
        "schema_version": DATASET_SCHEMA_VERSION,
        "literature_data_schema_id": schema["schema_id"],
        "schema_hash": schema_hash,
        "dataset_id": dataset_id,
        "validated_at": validated_at,
        "status": status,
        "candidate_count": len(candidates),
        "reviewed_count": len(reviewed),
        "comparable_reviewed_count": comparable_count,
        "plot_eligible_count": plot_eligible_count,
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
        return {
            "status": "needs_confirmation",
            "dataset_id": dataset_id,
            "next_action": "Confirm reviewed-only plotting.",
        }
    created_at = created_at or EARecord.now_iso()
    dataset_root = _dataset_root(root, dataset_id)
    spec = read_yaml(dataset_root / "extraction_spec.yml")
    schema, schema_hash = _schema_for_dataset(dataset_root, spec)
    primary_field = schema_field(schema, str(schema["primary_field_id"]))
    primary_type = str(primary_field["type"])
    plot_config = primary_field.get("plot") or {}
    if not plot_config.get("enabled"):
        raise ValueError(
            f"Plotting is disabled by schema for {schema['primary_field_id']}; reviewed export remains available"
        )
    supported_types = NUMERIC_FIELD_TYPES | {
        "text",
        "enum",
        "boolean",
        "date",
        "datetime",
    }
    if primary_type not in supported_types:
        raise ValueError(
            f"Plot configuration does not support field type {primary_type}; reviewed export remains available"
        )
    reviewed_path = dataset_root / "reviewed_dataset.yml"
    if not reviewed_path.is_file():
        raise ReviewRequiredError(
            f"Dataset {dataset_id} has no reviewed_dataset.yml; review candidate records with `ea literature data-review` first"
        )
    reviewed = read_yaml(reviewed_path).get("records") or []
    eligible = [
        record
        for record in reviewed
        if record.get("comparison_status") == "comparable"
        and record.get("normalized_value") is not None
    ]
    if not eligible:
        raise ValueError("No reviewed, comparable records are eligible for plotting")
    plots = dataset_root / "plots"
    plots.mkdir(parents=True, exist_ok=True)
    source_data = plots / "source_data.csv"
    figure_id = f"fig-{_slug(dataset_id)}-property-001"
    png_path = plots / f"{figure_id}.png"
    svg_path = plots / f"{figure_id}.svg"
    apply_figure_style()
    import matplotlib.pyplot as plt

    normalized_unit: str | None = None
    if primary_type in NUMERIC_FIELD_TYPES:
        units = {str(record["normalized_unit"]) for record in eligible}
        if len(units) != 1:
            raise ValueError("Plot-eligible records must share one normalized unit")
        normalized_unit = next(iter(units))
        _write_csv(source_data, eligible)
        labels = [
            str(record["source"]["paper_title"])[:28] or record["record_id"]
            for record in eligible
        ]
        values: list[float] = []
        lower_errors: list[float] = []
        upper_errors: list[float] = []
        for record in eligible:
            value = record["normalized_value"]
            primary_value = (record.get("field_values") or {}).get(
                str(schema["primary_field_id"]), {}
            )
            if primary_type == "range" and isinstance(value, list) and len(value) == 2:
                low, high = float(value[0]), float(value[1])
                midpoint = (low + high) / 2
                values.append(midpoint)
                lower_errors.append(midpoint - low)
                upper_errors.append(high - midpoint)
            else:
                values.append(float(value))
                uncertainty = float(
                    primary_value.get("normalized_uncertainty") or 0.0
                )
                lower_errors.append(uncertainty)
                upper_errors.append(uncertainty)
        fig, ax = plt.subplots(figsize=(max(6.2, len(values) * 0.62), 4.4))
        if any(lower_errors) or any(upper_errors):
            ax.errorbar(
                range(len(values)),
                values,
                yerr=[lower_errors, upper_errors],
                fmt="o",
                color="#007C91",
                ecolor="#555555",
                capsize=3,
            )
        else:
            ax.scatter(
                range(len(values)),
                values,
                color="#007C91",
                edgecolor="#222222",
                linewidth=0.5,
                s=42,
            )
        ax.set_xticks(range(len(values)), labels, rotation=35, ha="right")
        ax.set_ylabel(f"{spec['property_name']} ({normalized_unit})")
    else:
        categories = [
            json.dumps(record["normalized_value"], ensure_ascii=False, sort_keys=True)
            if isinstance(record["normalized_value"], (list, dict))
            else str(record["normalized_value"])
            for record in eligible
        ]
        counts: dict[str, int] = defaultdict(int)
        for value in categories:
            counts[value] += 1
        buffer = io.StringIO()
        writer = csv.DictWriter(
            buffer, fieldnames=["category", "count"], lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(
            {"category": category, "count": count}
            for category, count in sorted(counts.items())
        )
        atomic_write_text(source_data, buffer.getvalue())
        labels = list(sorted(counts))
        values = [counts[label] for label in labels]
        fig, ax = plt.subplots(figsize=(max(6.2, len(values) * 0.75), 4.4))
        ax.bar(range(len(values)), values, color="#007C91", edgecolor="#222222")
        ax.set_xticks(range(len(values)), labels, rotation=35, ha="right")
        ax.set_ylabel("Reviewed record count")
    ax.set_title(f"Reviewed {spec['property_name']} evidence")
    ax.grid(axis="y", color="#D9D9D9", linewidth=0.6)
    fig.tight_layout()
    fig.savefig(png_path, dpi=300, bbox_inches="tight")
    fig.savefig(svg_path, bbox_inches="tight")
    plt.close(fig)
    metadata = {
        "schema_version": DATASET_SCHEMA_VERSION,
        "literature_data_schema_id": schema["schema_id"],
        "schema_hash": schema_hash,
        "figure_id": figure_id,
        "created_at": created_at,
        "dataset_id": dataset_id,
        "record_ids": [record["record_id"] for record in eligible],
        "source_data_ref": _relative(root, source_data),
        "normalized_unit": normalized_unit,
        "value_type": primary_type,
        "reviewed_only": True,
        "limitations": [
            "Records marked not comparable, conflicting, deferred, rejected, or unreviewed are excluded."
        ],
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
        generation={
            "workflow": "literature_data_plot_beta",
            "created_at": created_at,
            "reviewed_only": True,
        },
        caption=f"Reviewed {spec['property_name']} records from the literature evidence dataset.",
        purpose="cross-paper reviewed property comparison",
        style_profile=NATURE_LIKE_STYLE_PROFILE,
        source_data_refs=[
            _relative(root, source_data),
            _relative(root, dataset_root / "reviewed_dataset.yml"),
        ],
        source_data=[
            source_data_entry(
                root,
                _relative(root, source_data),
                role="primary_plotting_dataset",
                purpose="Reviewed, normalized cross-paper values plotted in the comparison figure.",
                primary=True,
            ),
            source_data_entry(
                root,
                _relative(root, dataset_root / "reviewed_dataset.yml"),
                role="reviewed_dataset_manifest",
                purpose="Review decisions and record provenance for the plotted values.",
            ),
        ],
    )
    return {
        "status": "plot_ready",
        "dataset_id": dataset_id,
        "figure_id": figure_id,
        "plotted_record_count": len(eligible),
        "excluded_record_count": len(reviewed) - len(eligible),
        "figure_ref": _relative(root, png_path),
        "source_data_ref": _relative(root, source_data),
        "metadata_ref": _relative(root, metadata_path),
    }


def _report_markdown(
    spec: dict[str, Any], validation: dict[str, Any], reviewed: list[dict[str, Any]]
) -> str:
    lines = [
        f"# Reviewed Literature Dataset: {spec['dataset_id']}",
        "",
        f"Schema: `{spec.get('literature_data_schema_id') or spec['property_kind']}` | field: `{spec['property_kind']}` | material: {spec['material_name']}",
        "",
        f"Reviewed records: {len(reviewed)} | comparable: {validation['comparable_reviewed_count']} | validation: `{validation['status']}`",
        "",
        "| Record | Material | Reported | Normalized | Conditions | DOI | Evidence | Comparable |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for record in reviewed:
        conditions = record.get("conditions") or {}
        values = [
            record["record_id"],
            record["material_name"],
            f"{record['reported_value']} {record['reported_unit']}",
            f"{record['normalized_value']} {record['normalized_unit']}",
            f"T={conditions.get('temperature', NOT_REPORTED)}; {conditions.get('direction', NOT_REPORTED)}; {conditions.get('instrument_or_method', NOT_REPORTED)}",
            record.get("source", {}).get("doi", NOT_REPORTED),
            f"p.{record.get('evidence', {}).get('page', NOT_REPORTED)} / {record.get('evidence', {}).get('chunk_anchor', NOT_REPORTED)}",
            record["comparison_status"],
        ]
        lines.append(
            "| "
            + " | ".join(
                str(value).replace("|", "\\|").replace("\n", " ") for value in values
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "- Values are included only after explicit review; this workflow does not establish scientific truth or exhaustive coverage.",
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
        return {
            "status": "needs_confirmation",
            "dataset_id": dataset_id,
            "next_action": "Confirm reviewed dataset export.",
        }
    exported_at = exported_at or EARecord.now_iso()
    dataset_root = _dataset_root(root, dataset_id)
    spec = read_yaml(dataset_root / "extraction_spec.yml")
    reviewed_path = dataset_root / "reviewed_dataset.yml"
    if not reviewed_path.is_file():
        raise ReviewRequiredError(
            f"Dataset {dataset_id} has no reviewed_dataset.yml; review candidate records with `ea literature data-review` first"
        )
    reviewed = read_yaml(reviewed_path).get("records") or []
    validation = validate_literature_data(
        root, dataset_id=dataset_id, write_report=True, validated_at=exported_at
    )
    if validation["error_count"]:
        raise ValueError(
            "Reviewed dataset has validation errors; repair them before export"
        )
    report_path = dataset_root / "report.md"
    atomic_write_text(report_path, _report_markdown(spec, validation, reviewed))
    files = [
        dataset_root / "extraction_spec.yml",
        dataset_root / str(spec.get("schema_ref") or "literature_data_schema.yml"),
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
        "files": [
            {"path": path.relative_to(dataset_root).as_posix(), "sha256": _sha256(path)}
            for path in files
        ],
        "excluded": [
            "raw PDFs",
            "private full text",
            "cookies",
            "credentials",
            "absolute source paths",
            "unreviewed candidate records",
        ],
    }
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", manifest_bytes)
        for path in files:
            archive.write(path, arcname=path.relative_to(dataset_root).as_posix())
    export_dir = root / "exports" / "literature-data"
    archive_path = export_dir / f"{dataset_id}-reviewed.zip"
    atomic_write_bytes(archive_path, buffer.getvalue())
    checksum = hashlib.sha256(buffer.getvalue()).hexdigest()
    atomic_write_text(
        archive_path.with_suffix(".zip.sha256"), f"{checksum}  {archive_path.name}\n"
    )
    return {
        "status": "export_ready",
        "dataset_id": dataset_id,
        "reviewed_record_count": len(reviewed),
        "validation_status": validation["status"],
        "archive_ref": _relative(root, archive_path),
        "sha256": checksum,
        "report_ref": _relative(root, report_path),
        "next_action": "Share the reviewed bundle with its declared limitations and checksum.",
    }
