from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from ea.cli import main
from ea.figures import register_figure, source_data_entry, update_figure_report_ref
from ea.literature import plan_literature_data_extraction
from ea.literature import (
    ELECTRICAL_PRESETS,
    export_literature_data,
    extract_literature_data,
    plot_literature_data,
    review_literature_data,
    validate_literature_data,
    validate_literature_data_schema_payload,
)
from ea.projects import initialize_project
from ea.reports.service import _interpretation_text, _prepare_localized_report
from ea.schema import ReportRecord
from ea.storage import read_yaml, write_yaml


def _project(root: Path) -> None:
    initialize_project(
        root,
        project_name="v0.9.9 contract",
        project_slug="v0-9-9-contract",
        research_direction="contract fixtures",
        material_system="mixed materials",
        experiment_type="literature and Raman",
    )


def test_user_schema_preview_accepts_unknown_field_without_writes(tmp_path: Path) -> None:
    _project(tmp_path)
    source = tmp_path / "paper-cache"
    source.mkdir()
    (source / "metadata.json").write_text(
        json.dumps({"title": "Optical paper", "doi": "10.1000/optical"}),
        encoding="utf-8",
    )
    (source / "chunks.jsonl").write_text(
        json.dumps(
            {
                "chunk_id": "optical-001",
                "page": 3,
                "text": "The optical band gap was 1.82 eV by a Tauc analysis.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    schema_path = tmp_path / "optical-band-gap.schema.yml"
    write_yaml(
        schema_path,
        {
            "schema_version": "2.0",
            "schema_id": "user-optical-band-gap",
            "source": {"kind": "user_file", "version": "1"},
            "material_scope": "semiconductors",
            "primary_field_id": "optical_band_gap",
            "fields": [
                {
                    "field_id": "optical_band_gap",
                    "name": {"en": "optical band gap", "zh": "光学带隙"},
                    "aliases": ["optical band gap", "band gap"],
                    "description": "Reported optical band gap.",
                    "type": "number",
                    "unit": {
                        "dimension": "energy",
                        "allowed": ["eV"],
                        "canonical": "eV",
                        "conversions": {"eV": {"factor": 1.0, "formula": "reported_value * 1"}},
                    },
                    "required_conditions": ["instrument_or_method"],
                    "optional_conditions": ["temperature"],
                    "missing_value_policy": "not_reported",
                    "comparability": {"require_same_unit": True},
                    "dedup_policy": "source_field_value",
                    "conflict_policy": "preserve",
                    "search_hints": ["Tauc"],
                    "evidence": {"minimum_anchors": ["page_or_chunk"]},
                    "output": {"include": True},
                    "plot": {"enabled": True, "kind": "point"},
                }
            ],
        },
    )

    preview = plan_literature_data_extraction(
        tmp_path,
        schema_path=schema_path,
        material_name="semiconductors",
        sources=[source],
        dataset_id="optical-custom",
    )

    assert preview["status"] == "ready_to_create"
    assert preview["schema_id"] == "user-optical-band-gap"
    assert preview["schema_hash"]
    assert not (tmp_path / "literature" / "data-extractions" / "optical-custom").exists()


def test_custom_optical_field_completes_reviewed_pipeline_without_source_change(
    tmp_path: Path,
) -> None:
    _project(tmp_path)
    source = tmp_path / "paper-cache"
    source.mkdir()
    (source / "metadata.json").write_text(
        json.dumps({"title": "Optical paper", "doi": "10.1000/optical"}),
        encoding="utf-8",
    )
    (source / "chunks.jsonl").write_text(
        json.dumps(
            {
                "chunk_id": "optical-001",
                "page": 3,
                "section": "Optical properties",
                "text": "The optical band gap was 1.82 eV by a Tauc analysis.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    schema = {
        "schema_version": "2.0",
        "schema_id": "user-optical-band-gap",
        "source": {"kind": "user_file", "version": "1"},
        "material_scope": "semiconductors",
        "primary_field_id": "optical_band_gap",
        "fields": [
            {
                "field_id": "optical_band_gap",
                "name": {"en": "optical band gap", "zh": "光学带隙"},
                "aliases": ["optical band gap", "band gap"],
                "description": "Reported optical band gap.",
                "type": "number",
                "unit": {
                    "dimension": "energy",
                    "allowed": ["eV"],
                    "canonical": "eV",
                    "unknown_allowed": False,
                    "conversions": {
                        "eV": {
                            "canonical": "eV",
                            "factor": 1.0,
                            "formula": "reported_value * 1",
                        }
                    },
                },
                "required_conditions": ["instrument_or_method"],
                "optional_conditions": ["temperature"],
                "missing_value_policy": "not_reported",
                "comparability": {"enabled": True, "require_same_unit": True},
                "dedup_policy": "source_field_value",
                "conflict_policy": "preserve",
                "search_hints": ["Tauc"],
                "evidence": {"minimum_anchors": ["page_or_chunk"]},
                "output": {"include": True},
                "plot": {"enabled": True, "kind": "point"},
            }
        ],
    }
    schema_path = tmp_path / "optical.schema.yml"
    write_yaml(schema_path, schema)

    created = plan_literature_data_extraction(
        tmp_path,
        schema_path=schema_path,
        material_name="semiconductors",
        sources=[source],
        dataset_id="optical-custom",
        confirmed=True,
    )
    extracted = extract_literature_data(
        tmp_path, dataset_id="optical-custom", confirmed=True
    )
    dataset = tmp_path / "literature" / "data-extractions" / "optical-custom"
    record = read_yaml(dataset / "candidate_records.yml")["records"][0]
    reviewed = review_literature_data(
        tmp_path,
        dataset_id="optical-custom",
        record_id=record["record_id"],
        decision="accept",
        notes=["Verified against page 3."],
        confirmed=True,
    )
    validation = validate_literature_data(tmp_path, dataset_id="optical-custom")
    plotted = plot_literature_data(
        tmp_path, dataset_id="optical-custom", confirmed=True
    )
    exported = export_literature_data(
        tmp_path, dataset_id="optical-custom", confirmed=True
    )

    assert created["schema_id"] == "user-optical-band-gap"
    assert extracted["candidate_count"] == 1
    assert record["property_kind"] == "optical_band_gap"
    assert record["reported_value"] == 1.82
    assert record["reported_unit"] == "eV"
    assert record["normalized_value"] == 1.82
    assert record["conditions"]["instrument_or_method"] == "tauc_analysis"
    assert reviewed["comparison_status"] == "comparable"
    assert validation["status"] == "pass"
    assert plotted["plotted_record_count"] == 1
    assert (tmp_path / exported["archive_ref"]).is_file()


def test_schema_driven_mixed_synthesis_record_exports_without_plotting(
    tmp_path: Path,
) -> None:
    _project(tmp_path)
    source = tmp_path / "synthesis-cache"
    source.mkdir()
    (source / "metadata.json").write_text(
        json.dumps({"title": "Synthesis paper", "doi": "10.1000/synthesis"}),
        encoding="utf-8",
    )
    (source / "chunks.jsonl").write_text(
        json.dumps(
            {
                "chunk_id": "synthesis-001",
                "page": 5,
                "text": "The synthesis method was chemical vapor deposition; temperature was 750 °C; time was 30 min; atmosphere was argon; precursors were MoO3 and sulfur.",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    def field(field_id: str, name: str, field_type: str, **extra):
        return {
            "field_id": field_id,
            "name": {"en": name, "zh": ""},
            "aliases": [name],
            "description": name,
            "type": field_type,
            "required_conditions": [],
            "optional_conditions": [],
            "missing_value_policy": "not_reported",
            "comparability": {"enabled": True},
            "dedup_policy": "source_field_value",
            "conflict_policy": "preserve",
            "search_hints": [],
            "evidence": {"minimum_anchors": ["page_or_chunk"]},
            "output": {"include": True},
            "plot": {"enabled": False, "kind": "none"},
            **extra,
        }

    schema = {
        "schema_version": "2.0",
        "schema_id": "user-synthesis-record",
        "source": {"kind": "user_file", "version": "1"},
        "material_scope": "CVD materials",
        "primary_field_id": "synthesis_method",
        "fields": [
            field("synthesis_method", "synthesis method", "text"),
            field(
                "temperature",
                "temperature",
                "number",
                unit={
                    "dimension": "temperature",
                    "allowed": ["°C"],
                    "canonical": "°C",
                    "unknown_allowed": False,
                    "conversions": {
                        "°C": {"canonical": "°C", "factor": 1.0, "formula": "reported_value * 1"}
                    },
                },
            ),
            field(
                "time",
                "time",
                "number",
                unit={
                    "dimension": "time",
                    "allowed": ["min"],
                    "canonical": "min",
                    "unknown_allowed": False,
                    "conversions": {
                        "min": {"canonical": "min", "factor": 1.0, "formula": "reported_value * 1"}
                    },
                },
            ),
            field(
                "atmosphere",
                "atmosphere",
                "enum",
                choices=["argon", "nitrogen", "vacuum", "air"],
            ),
            field("precursors", "precursors", "list"),
        ],
    }
    schema_path = tmp_path / "synthesis.schema.yml"
    write_yaml(schema_path, schema)
    plan_literature_data_extraction(
        tmp_path,
        schema_path=schema_path,
        sources=[source],
        dataset_id="synthesis-custom",
        confirmed=True,
    )
    extract_literature_data(
        tmp_path, dataset_id="synthesis-custom", confirmed=True
    )
    dataset = tmp_path / "literature" / "data-extractions" / "synthesis-custom"
    record = read_yaml(dataset / "candidate_records.yml")["records"][0]
    review_literature_data(
        tmp_path,
        dataset_id="synthesis-custom",
        record_id=record["record_id"],
        decision="accept",
        confirmed=True,
    )
    validation = validate_literature_data(tmp_path, dataset_id="synthesis-custom")
    exported = export_literature_data(
        tmp_path, dataset_id="synthesis-custom", confirmed=True
    )

    assert set(record["field_values"]) == {
        "synthesis_method",
        "temperature",
        "time",
        "atmosphere",
        "precursors",
    }
    assert record["field_values"]["temperature"]["reported_value"] == 750.0
    assert record["field_values"]["atmosphere"]["reported_value"] == "argon"
    assert record["field_values"]["precursors"]["reported_value"] == [
        "MoO3",
        "sulfur",
    ]
    assert validation["status"] == "pass"
    assert validation["plot_eligible_count"] == 0
    assert (tmp_path / exported["archive_ref"]).is_file()


def test_schema_validator_supports_all_contract_types_and_actionable_errors() -> None:
    def base_field(field_id: str, field_type: str, **extra):
        return {
            "field_id": field_id,
            "name": {"en": field_id, "zh": ""},
            "aliases": [field_id],
            "description": field_id,
            "type": field_type,
            "required_conditions": [],
            "optional_conditions": [],
            "missing_value_policy": "not_reported",
            "comparability": {"enabled": True},
            "dedup_policy": "source_field_value",
            "conflict_policy": "preserve",
            "search_hints": [],
            "evidence": {"minimum_anchors": ["page_or_chunk"]},
            "output": {"include": True},
            "plot": {"enabled": False},
            **extra,
        }

    numeric_unit = {
        "dimension": "custom",
        "allowed": ["u"],
        "canonical": "u",
        "unknown_allowed": False,
        "conversions": {
            "u": {"canonical": "u", "factor": 1.0, "formula": "reported_value * 1"}
        },
    }
    fields = [
        base_field("number_value", "number", unit=numeric_unit),
        base_field("range_value", "range", unit=numeric_unit),
        base_field("uncertain_value", "uncertain_number", unit=numeric_unit),
        base_field("text_value", "text"),
        base_field("enum_value", "enum", choices=["a", "b"]),
        base_field("boolean_value", "boolean"),
        base_field("date_value", "date"),
        base_field("datetime_value", "datetime"),
        base_field("list_value", "list"),
        base_field(
            "nested_value",
            "nested",
            children=[
                {
                    "field_id": "child",
                    "name": {"en": "child", "zh": ""},
                    "aliases": ["child"],
                    "type": "text",
                }
            ],
        ),
    ]
    schema = {
        "schema_version": "2.0",
        "schema_id": "all-field-types",
        "source": {"kind": "user_file", "version": "1"},
        "material_scope": "all",
        "primary_field_id": "number_value",
        "fields": fields,
    }
    passed = validate_literature_data_schema_payload(schema)
    assert passed["status"] == "pass"
    assert passed["field_count"] == 10

    invalid = json.loads(json.dumps(schema))
    del invalid["fields"][0]["unit"]
    del invalid["fields"][1]["conflict_policy"]
    failed = validate_literature_data_schema_payload(invalid)
    codes = {item["code"] for item in failed["errors"]}
    assert failed["status"] == "fail"
    assert {"unit_rule_required", "conflict_policy_required"} <= codes
    assert all(item["next_action"] for item in failed["errors"])


def test_cli_schema_template_validation_and_unknown_request_preview(
    tmp_path: Path, capsys
) -> None:
    _project(tmp_path)
    assert main(["literature", "data-template", "--preset", "conductivity"]) == 0
    template = json.loads(capsys.readouterr().out)
    assert template["status"] == "template_preview"
    assert template["schema"]["source"]["kind"] == "ea_builtin_preset"

    schema_path = tmp_path / "template.yml"
    write_yaml(schema_path, template["schema"])
    assert main(["literature", "data-schema", "validate", str(schema_path)]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated["status"] == "pass"

    assert (
        main(
            [
                "literature",
                "data-plan",
                str(tmp_path),
                "--property",
                "photocatalytic hydrogen evolution rate",
                "--kind",
                "hydrogen_evolution_rate",
                "--material",
                "photocatalysts",
                "--type",
                "number",
                "--unit",
                "umol/g/h",
                "--dataset-id",
                "unknown-request-preview",
            ]
        )
        == 0
    )
    preview = json.loads(capsys.readouterr().out)
    assert preview["property_kind"] == "hydrogen_evolution_rate"
    assert preview["schema_source"]["kind"] == "natural_language_preview"
    assert preview["requires_confirmation"] is True
    assert not (
        tmp_path / "literature" / "data-extractions" / "unknown-request-preview"
    ).exists()


@pytest.mark.parametrize(
    ("preset", "sentence", "expected_unit", "expected_value"),
    [
        ("conductivity", "The electrical conductivity was 2 S/cm.", "S/m", 200.0),
        ("resistivity", "The electrical resistivity was 2 ohm cm.", "ohm m", 0.02),
        ("sheet_resistance", "The sheet resistance was 2 kohm/sq.", "ohm/sq", 2000.0),
        ("sheet_conductance", "The sheet conductance was 2 S/sq.", "S/sq", 2.0),
        ("contact_resistance", "The contact resistance was 2 kohm.", "ohm", 2000.0),
        ("mobility", "The carrier mobility was 2 m2/vs.", "cm2/(V s)", 20000.0),
    ],
)
def test_all_six_electrical_presets_preserve_golden_conversion(
    tmp_path: Path,
    preset: str,
    sentence: str,
    expected_unit: str,
    expected_value: float,
) -> None:
    _project(tmp_path)
    source = tmp_path / f"{preset}-cache"
    source.mkdir()
    (source / "metadata.json").write_text(
        json.dumps({"title": f"{preset} paper", "doi": f"10.1000/{preset}"}),
        encoding="utf-8",
    )
    (source / "chunks.jsonl").write_text(
        json.dumps({"chunk_id": f"{preset}-001", "page": 2, "text": sentence})
        + "\n",
        encoding="utf-8",
    )
    planned = plan_literature_data_extraction(
        tmp_path,
        property_name=str(ELECTRICAL_PRESETS[preset]["name"]["en"]),
        property_kind=preset,
        material_name="preset fixture",
        sources=[source],
        dataset_id=f"preset-{preset}",
        confirmed=True,
    )
    extracted = extract_literature_data(
        tmp_path, dataset_id=f"preset-{preset}", confirmed=True
    )
    record = read_yaml(
        tmp_path
        / "literature"
        / "data-extractions"
        / f"preset-{preset}"
        / "candidate_records.yml"
    )["records"][0]

    assert "maturity" not in planned
    assert "maturity" not in extracted
    assert record["normalized_unit"] == expected_unit
    assert record["normalized_value"] == pytest.approx(expected_value)


def test_cli_schema_validation_failure_has_nonzero_exit(
    tmp_path: Path, capsys
) -> None:
    invalid = tmp_path / "invalid-schema.yml"
    write_yaml(invalid, {"schema_version": "2.0", "fields": []})

    assert main(["literature", "data-schema", "validate", str(invalid)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "fail"
    assert result["errors"][0]["next_action"]


def test_confirmed_schema_change_requires_migration_and_legacy_preset_remains_readable(
    tmp_path: Path,
) -> None:
    _project(tmp_path)
    source = tmp_path / "legacy-cache"
    source.mkdir()
    (source / "metadata.json").write_text(
        json.dumps({"title": "Legacy conductivity", "doi": "10.1000/legacy"}),
        encoding="utf-8",
    )
    (source / "chunks.jsonl").write_text(
        json.dumps(
            {
                "chunk_id": "legacy-001",
                "page": 1,
                "text": "The electrical conductivity was 2.0 S/cm at 300 K.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    plan_literature_data_extraction(
        tmp_path,
        property_name="electrical conductivity",
        property_kind="conductivity",
        material_name="films",
        sources=[source],
        dataset_id="legacy-reader",
        confirmed=True,
    )
    dataset = tmp_path / "literature" / "data-extractions" / "legacy-reader"
    spec_path = dataset / "extraction_spec.yml"
    spec = read_yaml(spec_path)
    (dataset / spec["schema_ref"]).unlink()
    for key in (
        "schema_ref",
        "schema_hash",
        "schema_source",
        "literature_data_schema_version",
        "literature_data_schema_id",
        "primary_field_id",
    ):
        spec.pop(key, None)
    spec["schema_version"] = "1.0"
    write_yaml(spec_path, spec)
    extracted = extract_literature_data(
        tmp_path, dataset_id="legacy-reader", confirmed=True
    )
    record = read_yaml(dataset / "candidate_records.yml")["records"][0]
    assert extracted["candidate_count"] == 1
    assert record["normalized_value"] == 200.0

    custom_schema = {
        "schema_version": "2.0",
        "schema_id": "schema-stale-test",
        "source": {"kind": "user_file", "version": "1"},
        "material_scope": "films",
        "primary_field_id": "custom_value",
        "fields": [
            {
                "field_id": "custom_value",
                "name": {"en": "custom value", "zh": "自定义值"},
                "aliases": ["custom value"],
                "description": "Custom value.",
                "type": "number",
                "unit": {
                    "dimension": "custom",
                    "allowed": ["u"],
                    "canonical": "u",
                    "unknown_allowed": False,
                    "conversions": {
                        "u": {"canonical": "u", "factor": 1.0, "formula": "reported_value * 1"}
                    },
                },
                "required_conditions": [],
                "optional_conditions": [],
                "missing_value_policy": "not_reported",
                "comparability": {"enabled": True},
                "dedup_policy": "source_field_value",
                "conflict_policy": "preserve",
                "search_hints": [],
                "evidence": {"minimum_anchors": ["page_or_chunk"]},
                "output": {"include": True},
                "plot": {"enabled": True, "kind": "point"},
            }
        ],
    }
    plan_literature_data_extraction(
        tmp_path,
        schema_payload=custom_schema,
        sources=[source],
        dataset_id="schema-stale",
        confirmed=True,
    )
    schema_file = (
        tmp_path
        / "literature"
        / "data-extractions"
        / "schema-stale"
        / "literature_data_schema.yml"
    )
    edited_schema = read_yaml(schema_file)
    edited_schema["fields"][0]["description"] = "Changed after confirmation."
    write_yaml(schema_file, edited_schema)
    stale = extract_literature_data(
        tmp_path, dataset_id="schema-stale", confirmed=True
    )
    assert stale["status"] == "migration_required"
    assert stale["error_code"] == "literature_data_schema_changed"


def test_raman_legacy_dynamic_english_uses_safe_chinese_fallback() -> None:
    text = _interpretation_text(
        {
            "peak_analysis": {
                "possible_interpretations": [
                    {
                        "text": "Detected E2g-like and A1g-like candidate peaks form a MoS2-like Raman pair; the mode separation is more consistent with a thin-layer MoS2 signal than with a large bulk-like separation.",
                        "confidence": "medium",
                        "evidence": ["peak-005", "peak-006"],
                        "mode_separation_cm-1": 19.76,
                    }
                ]
            }
        },
        "[1]",
    )

    assert "Detected" not in text
    assert "more consistent" not in text
    assert "候选" in text
    assert "19.76 cm^-1" in text


def test_markdown_uses_figure_local_source_data_without_bottom_section(tmp_path: Path) -> None:
    _project(tmp_path)
    image = tmp_path / "figures" / "base.png"
    image.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (800, 500), "white").save(image)
    data = tmp_path / "processed" / "trace.csv"
    data.parent.mkdir(exist_ok=True)
    data.write_text("x,y\n1,2\n", encoding="utf-8")
    register_figure(
        tmp_path,
        figure_id="fig-local-001",
        path="figures/base.png",
        report_id=None,
        result_id="res-local-001",
        raw_data_ids=[],
        sample_ids=[],
        caption="Processed trace.",
        source_data=[
            source_data_entry(
                tmp_path,
                "processed/trace.csv",
                role="primary_plotting_dataset",
                purpose="Processed trace plotted on the main axis.",
                primary=True,
            )
        ],
    )
    report = ReportRecord(
        report_id="rpt-local-001",
        project_id="prj-v0-9-9-contract",
        report_type="raman_analysis",
        related_results=["res-local-001"],
        figure_ids=["fig-local-001"],
        status="draft",
        created_at="2026-07-16T10:00:00",
        updated_at="2026-07-16T10:00:00",
    )

    _, body, _ = _prepare_localized_report(
        tmp_path,
        report=report,
        body="# Raman 报告\n\n## References\n\n无。\n",
        metadata={"warnings": []},
        outputs={"figure": "figures/base.png"},
        reference_block={"reference_ids": [], "references_markdown": "无。"},
    )

    assert "## 图下数据" not in body
    assert "## Figure Source Data" not in body
    assert "![" in body
    assert "processed/trace.csv" in body
    assert body.index("![") < body.index("processed/trace.csv")


def test_multi_figure_missing_and_protected_sources_stay_local_and_private(
    tmp_path: Path,
) -> None:
    _project(tmp_path)
    for index in (1, 2):
        image = tmp_path / "figures" / f"base-{index}.png"
        image.parent.mkdir(exist_ok=True)
        Image.new("RGB", (640, 360), "white").save(image)
    data = tmp_path / "processed" / "visible.csv"
    data.parent.mkdir(exist_ok=True)
    data.write_text("x,y\n1,2\n", encoding="utf-8")
    register_figure(
        tmp_path,
        figure_id="fig-local-001",
        path="figures/base-1.png",
        report_id=None,
        result_id="res-local-001",
        raw_data_ids=[],
        sample_ids=[],
        caption="First trace.",
        source_data=[
            source_data_entry(
                tmp_path,
                "processed/visible.csv",
                role="primary_plotting_dataset",
                purpose="Visible processed trace.",
                primary=True,
            ),
            {
                "ref": "raw/private-secret-name.csv",
                "role": "supporting_raw_data",
                "purpose": "Protected raw input.",
                "columns": [],
                "primary": False,
                "protected_raw": True,
            },
        ],
    )
    register_figure(
        tmp_path,
        figure_id="fig-local-002",
        path="figures/base-2.png",
        report_id=None,
        result_id="res-local-002",
        raw_data_ids=[],
        sample_ids=[],
        caption="Second trace.",
        source_data=[
            {
                "ref": "processed/missing.csv",
                "role": "primary_plotting_dataset",
                "purpose": "Missing processed trace.",
                "columns": [],
                "primary": True,
                "protected_raw": False,
            }
        ],
    )
    report = ReportRecord(
        report_id="rpt-local-multi-001",
        project_id="prj-v0-9-9-contract",
        report_type="raman_analysis",
        related_results=["res-local-001", "res-local-002"],
        figure_ids=["fig-local-001", "fig-local-002"],
        status="draft",
        created_at="2026-07-16T10:00:00",
        updated_at="2026-07-16T10:00:00",
    )

    _, body, _ = _prepare_localized_report(
        tmp_path,
        report=report,
        body="# 报告\n\n## References\n\n无。\n",
        metadata={"warnings": []},
        outputs={},
        reference_block={"reference_ids": [], "references_markdown": "无。"},
    )

    assert body.count("![") == 2
    assert body.count("visible.csv") == 2  # one link label plus one link target
    assert "private-secret-name.csv" not in body
    assert "protected_raw_source_omitted" in body
    assert "figure_source_data_file_missing" in body
    assert body.index("fig-local-001") < body.index("visible.csv") < body.index(
        "fig-local-002"
    )
    assert "## 图下数据" not in body


def test_no_figure_report_does_not_create_orphan_figure_section(tmp_path: Path) -> None:
    _project(tmp_path)
    report = ReportRecord(
        report_id="rpt-no-figure-001",
        project_id="prj-v0-9-9-contract",
        report_type="thermal_analysis",
        related_results=["res-no-figure-001"],
        figure_ids=[],
        status="draft",
        created_at="2026-07-16T10:00:00",
        updated_at="2026-07-16T10:00:00",
    )
    _, body, _ = _prepare_localized_report(
        tmp_path,
        report=report,
        body="# 报告\n\n## References\n\n无。\n",
        metadata={"warnings": []},
        outputs={},
        reference_block={"reference_ids": [], "references_markdown": "无。"},
    )

    assert "## 图件" not in body
    assert "## Figures" not in body


def test_report_bound_footer_records_readable_display_scale(tmp_path: Path) -> None:
    image = tmp_path / "figures" / "wide.png"
    image.parent.mkdir(parents=True)
    Image.new("RGB", (1796, 1194), "white").save(image)
    register_figure(
        tmp_path,
        figure_id="fig-ea-test1-mos2-mica-raman-20260716-001",
        path="figures/wide.png",
        report_id=None,
        result_id="res-test1",
        raw_data_ids=[],
        sample_ids=[],
    )

    record = update_figure_report_ref(
        tmp_path,
        "fig-ea-test1-mos2-mica-raman-20260716-001",
        "rpt-ea-test1-mos2-mica-20260716-001",
    )
    rendering = record["renderings"]["rpt-ea-test1-mos2-mica-20260716-001"]
    final_path = tmp_path / rendering["path"]
    with Image.open(final_path) as final:
        assert int(final.info["ea_footer_font_px"]) >= 24
        assert float(final.info["ea_footer_effective_css_px"]) >= 12.0
        assert final.height > 1194
