from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from ea.storage.files import read_yaml, write_yaml


LITERATURE_DATA_SCHEMA_VERSION = "2.0"
FIELD_TYPES = {
    "number",
    "range",
    "uncertain_number",
    "text",
    "enum",
    "boolean",
    "date",
    "datetime",
    "list",
    "nested",
}
NUMERIC_FIELD_TYPES = {"number", "range", "uncertain_number"}
MISSING_VALUE_POLICIES = {"not_reported", "null", "omit", "defer"}
CONFLICT_POLICIES = {"preserve", "prefer_reviewed", "reject_conflict"}
DEDUP_POLICIES = {"source_field_value", "source_field", "none"}


class LiteratureDataSchemaError(ValueError):
    """Raised when a literature-data schema cannot safely drive a dataset."""


def _conversion(
    canonical: str, factor: float, formula: str
) -> dict[str, Any]:
    return {"canonical": canonical, "factor": factor, "formula": formula}


ELECTRICAL_PRESETS: dict[str, dict[str, Any]] = {
    "conductivity": {
        "name": {"en": "electrical conductivity", "zh": "电导率"},
        "aliases": ["electrical conductivity", "conductivity", "电导率"],
        "dimension": "electrical_conductivity",
        "canonical": "S/m",
        "units": {
            "s/m": _conversion("S/m", 1.0, "reported_value * 1"),
            "s m-1": _conversion("S/m", 1.0, "reported_value * 1"),
            "s m^-1": _conversion("S/m", 1.0, "reported_value * 1"),
            "s/cm": _conversion("S/m", 100.0, "reported_value * 100"),
            "s cm-1": _conversion("S/m", 100.0, "reported_value * 100"),
            "s cm^-1": _conversion("S/m", 100.0, "reported_value * 100"),
            "ms/cm": _conversion("S/m", 0.1, "reported_value * 0.1"),
            "us/cm": _conversion("S/m", 0.0001, "reported_value * 0.0001"),
            "µs/cm": _conversion("S/m", 0.0001, "reported_value * 0.0001"),
            "μs/cm": _conversion("S/m", 0.0001, "reported_value * 0.0001"),
        },
    },
    "resistivity": {
        "name": {"en": "electrical resistivity", "zh": "电阻率"},
        "aliases": ["electrical resistivity", "resistivity", "电阻率"],
        "dimension": "electrical_resistivity",
        "canonical": "ohm m",
        "units": {
            "ohm m": _conversion("ohm m", 1.0, "reported_value * 1"),
            "ω m": _conversion("ohm m", 1.0, "reported_value * 1"),
            "ohm cm": _conversion("ohm m", 0.01, "reported_value * 0.01"),
            "ω cm": _conversion("ohm m", 0.01, "reported_value * 0.01"),
        },
    },
    "sheet_resistance": {
        "name": {"en": "sheet resistance", "zh": "方块电阻"},
        "aliases": ["sheet resistance", "sheet resistivity", "方块电阻"],
        "dimension": "sheet_resistance",
        "canonical": "ohm/sq",
        "units": {
            "ohm/sq": _conversion("ohm/sq", 1.0, "reported_value * 1"),
            "ohm/square": _conversion("ohm/sq", 1.0, "reported_value * 1"),
            "ω/sq": _conversion("ohm/sq", 1.0, "reported_value * 1"),
            "kohm/sq": _conversion("ohm/sq", 1000.0, "reported_value * 1000"),
            "kω/sq": _conversion("ohm/sq", 1000.0, "reported_value * 1000"),
        },
    },
    "sheet_conductance": {
        "name": {"en": "sheet conductance", "zh": "面电导"},
        "aliases": ["sheet conductance", "面电导"],
        "dimension": "sheet_conductance",
        "canonical": "S/sq",
        "units": {
            "s/sq": _conversion("S/sq", 1.0, "reported_value * 1"),
            "s/square": _conversion("S/sq", 1.0, "reported_value * 1"),
        },
    },
    "contact_resistance": {
        "name": {"en": "contact resistance", "zh": "接触电阻"},
        "aliases": ["contact resistance", "接触电阻"],
        "dimension": "contact_resistance",
        "canonical": "ohm",
        "units": {
            "ohm": _conversion("ohm", 1.0, "reported_value * 1"),
            "ω": _conversion("ohm", 1.0, "reported_value * 1"),
            "kohm": _conversion("ohm", 1000.0, "reported_value * 1000"),
            "kω": _conversion("ohm", 1000.0, "reported_value * 1000"),
            "ohm um": _conversion("ohm um", 1.0, "reported_value * 1"),
            "ω um": _conversion("ohm um", 1.0, "reported_value * 1"),
        },
    },
    "mobility": {
        "name": {"en": "carrier mobility", "zh": "载流子迁移率"},
        "aliases": [
            "carrier mobility",
            "electron mobility",
            "hole mobility",
            "mobility",
            "迁移率",
        ],
        "dimension": "carrier_mobility",
        "canonical": "cm2/(V s)",
        "units": {
            "cm2/vs": _conversion("cm2/(V s)", 1.0, "reported_value * 1"),
            "cm^2/vs": _conversion("cm2/(V s)", 1.0, "reported_value * 1"),
            "cm2 v-1 s-1": _conversion("cm2/(V s)", 1.0, "reported_value * 1"),
            "m2/vs": _conversion("cm2/(V s)", 10000.0, "reported_value * 10000"),
        },
    },
}

PROPERTY_KINDS = frozenset(ELECTRICAL_PRESETS)
PROPERTY_ALIASES = {
    key: list(value["aliases"]) for key, value in ELECTRICAL_PRESETS.items()
}
UNIT_RULES: dict[str, dict[str, tuple[str, float, str]]] = {
    key: {
        unit: (
            str(rule["canonical"]),
            float(rule["factor"]),
            str(rule["formula"]),
        )
        for unit, rule in value["units"].items()
    }
    for key, value in ELECTRICAL_PRESETS.items()
}


def _field_id(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return normalized[:64] or "custom_field"


def _base_field(
    *,
    field_id: str,
    name: Mapping[str, str],
    aliases: Iterable[str],
    field_type: str,
    material_scope: str,
) -> dict[str, Any]:
    return {
        "field_id": field_id,
        "name": {"en": str(name.get("en") or field_id), "zh": str(name.get("zh") or "")},
        "aliases": list(dict.fromkeys(str(value) for value in aliases if str(value))),
        "description": f"Source-reported {name.get('en') or field_id}.",
        "material_scope": material_scope,
        "type": field_type,
        "required_conditions": [],
        "optional_conditions": [],
        "missing_value_policy": "not_reported",
        "comparability": {"enabled": True, "rules": []},
        "dedup_policy": "source_field_value",
        "conflict_policy": "preserve",
        "search_hints": [],
        "evidence": {"minimum_anchors": ["page_or_chunk"]},
        "output": {"include": True, "group_by": [], "sort_by": []},
        "plot": {"enabled": field_type in NUMERIC_FIELD_TYPES, "kind": "point"},
    }


def builtin_schema(
    property_kind: str,
    *,
    property_name: str | None = None,
    material_scope: str = "materials",
    required_conditions: Iterable[str] = (),
    comparability_rules: Iterable[str] = (),
) -> dict[str, Any]:
    try:
        preset = ELECTRICAL_PRESETS[property_kind]
    except KeyError as exc:
        raise LiteratureDataSchemaError(
            f"Unknown built-in literature-data preset: {property_kind}"
        ) from exc
    name = dict(preset["name"])
    if property_name:
        name["en"] = property_name
    field = _base_field(
        field_id=property_kind,
        name=name,
        aliases=preset["aliases"],
        field_type="number",
        material_scope=material_scope,
    )
    field["required_conditions"] = list(dict.fromkeys(required_conditions))
    field["comparability"] = {
        "enabled": True,
        "require_same_unit": True,
        "rules": list(dict.fromkeys(comparability_rules)),
    }
    field["unit"] = {
        "dimension": preset["dimension"],
        "allowed": list(preset["units"]),
        "canonical": preset["canonical"],
        "unknown_allowed": False,
        "conversions": copy.deepcopy(preset["units"]),
    }
    return {
        "schema_version": LITERATURE_DATA_SCHEMA_VERSION,
        "schema_id": f"ea-preset-{property_kind}",
        "source": {
            "kind": "ea_builtin_preset",
            "version": "1.0",
            "preset_id": property_kind,
        },
        "material_scope": material_scope,
        "primary_field_id": property_kind,
        "fields": [field],
    }


def request_schema(
    *,
    property_name: str,
    property_kind: str | None,
    material_scope: str,
    field_type: str = "number",
    allowed_units: Iterable[str] = (),
    required_conditions: Iterable[str] = (),
    comparability_rules: Iterable[str] = (),
    aliases: Iterable[str] = (),
) -> dict[str, Any]:
    if property_kind in PROPERTY_KINDS:
        return builtin_schema(
            str(property_kind),
            property_name=property_name,
            material_scope=material_scope,
            required_conditions=required_conditions,
            comparability_rules=comparability_rules,
        )
    field_id = _field_id(property_kind or property_name)
    contains_cjk = bool(re.search(r"[\u3400-\u9fff]", property_name))
    field = _base_field(
        field_id=field_id,
        name={
            "en": field_id.replace("_", " ") if contains_cjk else property_name,
            "zh": property_name if contains_cjk else "",
        },
        aliases=[property_name, *aliases],
        field_type=field_type,
        material_scope=material_scope,
    )
    field["required_conditions"] = list(dict.fromkeys(required_conditions))
    field["comparability"] = {
        "enabled": True,
        "require_same_unit": field_type in NUMERIC_FIELD_TYPES,
        "rules": list(dict.fromkeys(comparability_rules)),
    }
    units = list(dict.fromkeys(str(value) for value in allowed_units if str(value)))
    if field_type in NUMERIC_FIELD_TYPES:
        canonical = units[0] if units else "unknown"
        field["unit"] = {
            "dimension": "user_defined" if units else "unknown",
            "allowed": units,
            "canonical": canonical,
            "unknown_allowed": not bool(units),
            "conversions": {
                unit: {
                    "canonical": canonical,
                    "factor": 1.0,
                    "formula": "reported_value * 1",
                }
                for unit in units
            },
        }
    return {
        "schema_version": LITERATURE_DATA_SCHEMA_VERSION,
        "schema_id": f"project-{field_id}",
        "source": {"kind": "natural_language_preview", "version": "1.0"},
        "material_scope": material_scope,
        "primary_field_id": field_id,
        "fields": [field],
    }


def _canonical_schema(payload: Mapping[str, Any]) -> dict[str, Any]:
    schema = copy.deepcopy(dict(payload))
    schema.setdefault("schema_version", LITERATURE_DATA_SCHEMA_VERSION)
    schema.setdefault("source", {"kind": "user_file", "version": "1"})
    schema.setdefault("material_scope", "materials")
    for field in schema.get("fields") or []:
        if not isinstance(field, dict):
            continue
        field["aliases"] = list(
            dict.fromkeys(str(value) for value in field.get("aliases") or [])
        )
        field["required_conditions"] = list(
            dict.fromkeys(str(value) for value in field.get("required_conditions") or [])
        )
        field["optional_conditions"] = list(
            dict.fromkeys(str(value) for value in field.get("optional_conditions") or [])
        )
        field["search_hints"] = list(
            dict.fromkeys(str(value) for value in field.get("search_hints") or [])
        )
    return schema


def literature_data_schema_hash(schema: Mapping[str, Any]) -> str:
    canonical = _canonical_schema(schema)
    return hashlib.sha256(
        json.dumps(
            canonical,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def validate_literature_data_schema_payload(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    schema = _canonical_schema(payload)
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    def error(code: str, path: str, message: str, next_action: str) -> None:
        errors.append(
            {
                "code": code,
                "path": path,
                "message": message,
                "next_action": next_action,
            }
        )

    if schema.get("schema_version") != LITERATURE_DATA_SCHEMA_VERSION:
        error(
            "unsupported_schema_version",
            "schema_version",
            f"Expected schema version {LITERATURE_DATA_SCHEMA_VERSION}.",
            "Migrate or regenerate the schema preview with the current EA version.",
        )
    schema_id = str(schema.get("schema_id") or "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}", schema_id):
        error(
            "invalid_schema_id",
            "schema_id",
            "schema_id must be a portable identifier.",
            "Use 1-96 letters, numbers, dots, underscores, or hyphens.",
        )
    source = schema.get("source")
    if not isinstance(source, dict) or not source.get("kind") or not source.get("version"):
        error(
            "schema_source_required",
            "source",
            "Schema source kind and version are required for provenance.",
            "Add source.kind and source.version.",
        )
    fields = schema.get("fields")
    if not isinstance(fields, list) or not fields:
        error(
            "fields_required",
            "fields",
            "At least one field is required.",
            "Add a complete field definition.",
        )
        fields = []
    seen: set[str] = set()

    def validate_field(field: Any, path: str, *, nested_child: bool = False) -> str:
        if not isinstance(field, dict):
            error("invalid_field", path, "Field must be an object.", "Replace it with a field mapping.")
            return ""
        field_id = str(field.get("field_id") or "")
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", field_id):
            error(
                "invalid_field_id",
                f"{path}.field_id",
                "field_id must be lower snake_case.",
                "Use a stable lower-case identifier beginning with a letter.",
            )
        if not nested_child and field_id in seen:
            error(
                "duplicate_field_id",
                f"{path}.field_id",
                f"Duplicate field_id: {field_id}",
                "Rename or merge the duplicate field.",
            )
        if not nested_child:
            seen.add(field_id)
        name = field.get("name")
        if not isinstance(name, dict) or not str(name.get("en") or "").strip():
            error(
                "field_name_required",
                f"{path}.name",
                "At least an English field name is required.",
                "Add name.en and optionally name.zh.",
            )
        if not field.get("aliases"):
            error(
                "field_alias_required",
                f"{path}.aliases",
                "Extraction requires at least one explicit alias.",
                "Add source-visible names without mapping to a different property.",
            )
        field_type = str(field.get("type") or "")
        if field_type not in FIELD_TYPES:
            error(
                "unsupported_field_type",
                f"{path}.type",
                f"Unsupported field type: {field_type or 'missing'}",
                f"Choose one of: {', '.join(sorted(FIELD_TYPES))}.",
            )
        if field.get("missing_value_policy") not in MISSING_VALUE_POLICIES:
            error(
                "missing_value_policy_required",
                f"{path}.missing_value_policy",
                "A supported missing-value policy is required.",
                f"Choose one of: {', '.join(sorted(MISSING_VALUE_POLICIES))}.",
            )
        if field.get("dedup_policy") not in DEDUP_POLICIES:
            error(
                "dedup_policy_required",
                f"{path}.dedup_policy",
                "A supported deduplication policy is required.",
                f"Choose one of: {', '.join(sorted(DEDUP_POLICIES))}.",
            )
        if field.get("conflict_policy") not in CONFLICT_POLICIES:
            error(
                "conflict_policy_required",
                f"{path}.conflict_policy",
                "A supported conflict policy is required.",
                f"Choose one of: {', '.join(sorted(CONFLICT_POLICIES))}.",
            )
        if not isinstance(field.get("comparability"), dict) or not isinstance(
            field.get("comparability", {}).get("enabled"), bool
        ):
            error(
                "comparability_policy_required",
                f"{path}.comparability",
                "An explicit comparability policy is required.",
                "Add boolean comparability.enabled and any required rules.",
            )
        evidence = field.get("evidence")
        if not isinstance(evidence, dict) or not evidence.get("minimum_anchors"):
            error(
                "minimum_evidence_required",
                f"{path}.evidence",
                "Minimum evidence anchors are required.",
                "Add at least page_or_chunk to evidence.minimum_anchors.",
            )
        output = field.get("output")
        if not isinstance(output, dict) or not isinstance(output.get("include"), bool):
            error(
                "output_policy_required",
                f"{path}.output",
                "An explicit output policy is required.",
                "Add boolean output.include and optional grouping or sorting rules.",
            )
        plot = field.get("plot")
        if not isinstance(plot, dict) or not isinstance(plot.get("enabled"), bool):
            error(
                "plot_policy_required",
                f"{path}.plot",
                "An explicit plot policy is required.",
                "Add boolean plot.enabled and an optional plot kind.",
            )
        if field_type in NUMERIC_FIELD_TYPES:
            unit = field.get("unit")
            if not isinstance(unit, dict):
                error(
                    "unit_rule_required",
                    f"{path}.unit",
                    "Numeric fields need an explicit unit rule.",
                    "Add dimension, canonical, allowed, conversions, and unknown_allowed.",
                )
            else:
                allowed = [str(value) for value in unit.get("allowed") or []]
                unknown_allowed = bool(unit.get("unknown_allowed"))
                if not unit.get("dimension") or not unit.get("canonical"):
                    error(
                        "unit_dimension_or_canonical_missing",
                        f"{path}.unit",
                        "Numeric unit dimension and canonical unit are required.",
                        "Declare both values, using unknown only when explicitly permitted.",
                    )
                if not allowed and not unknown_allowed:
                    error(
                        "allowed_units_required",
                        f"{path}.unit.allowed",
                        "No allowed unit or explicit unknown-unit policy was provided.",
                        "Add allowed units or set unknown_allowed: true.",
                    )
                conversions = unit.get("conversions") or {}
                for allowed_unit in allowed:
                    rule = conversions.get(allowed_unit) or conversions.get(allowed_unit.lower())
                    if (
                        not isinstance(rule, dict)
                        or "factor" not in rule
                        or not (rule.get("canonical") or unit.get("canonical"))
                    ):
                        error(
                            "unit_conversion_missing",
                            f"{path}.unit.conversions.{allowed_unit}",
                            f"Explicit conversion rule missing for {allowed_unit}.",
                            "Add canonical, numeric factor, and formula.",
                        )
        if field_type == "enum" and not field.get("choices"):
            error(
                "enum_choices_required",
                f"{path}.choices",
                "Enum fields need controlled choices.",
                "Add at least one allowed choice.",
            )
        if field_type == "nested":
            children = field.get("children")
            if not isinstance(children, list) or not children:
                error(
                    "nested_children_required",
                    f"{path}.children",
                    "Nested fields need child definitions.",
                    "Add one or more complete child field contracts.",
                )
            else:
                child_ids: set[str] = set()
                for child_index, child in enumerate(children):
                    child_path = f"{path}.children[{child_index}]"
                    child_id = validate_field(child, child_path, nested_child=True)
                    if child_id and child_id in child_ids:
                        error(
                            "duplicate_nested_field_id",
                            f"{child_path}.field_id",
                            f"Duplicate nested field_id: {child_id}",
                            "Rename or merge the duplicate nested child.",
                        )
                    if child_id:
                        child_ids.add(child_id)
        return field_id

    for index, field in enumerate(fields):
        validate_field(field, f"fields[{index}]")

    primary = str(schema.get("primary_field_id") or "")
    if primary not in seen:
        error(
            "primary_field_missing",
            "primary_field_id",
            "primary_field_id must reference exactly one declared field.",
            "Choose a field_id from fields.",
        )
    semantic_hash = literature_data_schema_hash(schema)
    return {
        "schema_version": LITERATURE_DATA_SCHEMA_VERSION,
        "status": "pass" if not errors else "fail",
        "schema_id": schema_id or None,
        "schema_hash": semantic_hash,
        "field_count": len(fields),
        "errors": errors,
        "warnings": warnings,
        "schema": schema,
        "next_action": (
            "Use this schema hash in a zero-write dataset preview."
            if not errors
            else errors[0]["next_action"]
        ),
    }


def validate_literature_data_schema(path: Path) -> dict[str, Any]:
    payload = read_yaml(path)
    result = validate_literature_data_schema_payload(payload)
    return {**result, "schema_path": str(path)}


def load_literature_data_schema(path: Path) -> tuple[dict[str, Any], str]:
    result = validate_literature_data_schema(path)
    if result["status"] != "pass":
        first = result["errors"][0]
        raise LiteratureDataSchemaError(
            f"{first['code']} at {first['path']}: {first['message']} Next action: {first['next_action']}"
        )
    return result["schema"], str(result["schema_hash"])


def schema_field(schema: Mapping[str, Any], field_id: str) -> dict[str, Any]:
    for field in schema.get("fields") or []:
        if isinstance(field, dict) and field.get("field_id") == field_id:
            return field
    raise LiteratureDataSchemaError(f"Unknown schema field: {field_id}")


def schema_template() -> dict[str, Any]:
    field = _base_field(
        field_id="requested_field",
        name={"en": "requested field", "zh": "待收集字段"},
        aliases=["requested field"],
        field_type="number",
        material_scope="describe applicable materials or samples",
    )
    field["unit"] = {
        "dimension": "declare_dimension",
        "allowed": ["declare_unit"],
        "canonical": "declare_unit",
        "unknown_allowed": False,
        "conversions": {
            "declare_unit": {
                "canonical": "declare_unit",
                "factor": 1.0,
                "formula": "reported_value * 1",
            }
        },
    }
    return {
        "schema_version": LITERATURE_DATA_SCHEMA_VERSION,
        "schema_id": "project-requested-field",
        "source": {"kind": "project_template", "version": "1.0"},
        "material_scope": "describe applicable materials or samples",
        "primary_field_id": "requested_field",
        "fields": [field],
    }


def prepare_literature_data_schema_template(
    *,
    preset: str | None = None,
    output: Path | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    schema = builtin_schema(preset) if preset else schema_template()
    validation = validate_literature_data_schema_payload(schema)
    result = {
        "status": "template_preview" if output is None else "needs_confirmation",
        "read_only": output is None or not confirmed,
        "preset": preset,
        "schema_hash": validation["schema_hash"],
        "schema": validation["schema"],
        "output": str(output) if output else None,
        "next_action": (
            "Copy the template into a project file and edit every declared placeholder."
            if output is None
            else "Confirm the template write after reviewing the output path."
        ),
    }
    if output is None or not confirmed:
        return result
    write_yaml(output, validation["schema"])
    return {
        **result,
        "status": "template_written",
        "read_only": False,
        "next_action": "Edit the schema, then run `ea literature data-schema validate`.",
    }
