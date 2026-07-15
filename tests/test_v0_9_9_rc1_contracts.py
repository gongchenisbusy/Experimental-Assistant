from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from ea.data_import import preview_import
from ea.errors import ReviewRequiredError
from ea.literature import (
    extract_literature_data,
    export_literature_data,
    plan_literature_data_extraction,
    plot_literature_data,
    review_literature_data,
    validate_literature_data,
    validate_literature_data_schema,
)
from ea.projects import initialize_project
from ea.storage import read_markdown_record, read_yaml, write_markdown_record, write_yaml
from ea.user_surface import guided_first_journey, start_project


def _project(root: Path) -> None:
    initialize_project(
        root,
        project_name="RC1 contract",
        project_slug="rc1-contract",
        research_direction="universal evidence",
        material_system="mixed materials",
        experiment_type="literature extraction",
    )


def _field(
    field_id: str,
    field_type: str,
    *,
    aliases: list[str] | None = None,
    units: dict[str, tuple[str, float]] | None = None,
    required_conditions: list[str] | None = None,
    optional_conditions: list[str] | None = None,
    conflict_policy: str = "preserve",
) -> dict:
    field = {
        "field_id": field_id,
        "name": {"en": field_id.replace("_", " "), "zh": ""},
        "aliases": aliases or [field_id.replace("_", " ")],
        "description": field_id,
        "material_scope": "mixed materials",
        "type": field_type,
        "required_conditions": required_conditions or [],
        "optional_conditions": optional_conditions or [],
        "missing_value_policy": "not_reported",
        "comparability": {"enabled": True, "require_same_unit": bool(units)},
        "dedup_policy": "source_field_value",
        "conflict_policy": conflict_policy,
        "search_hints": [],
        "evidence": {"minimum_anchors": ["page_or_chunk"]},
        "output": {"include": True, "group_by": [], "sort_by": []},
        "plot": {"enabled": field_type in {"number", "range", "uncertain_number"}, "kind": "point"},
    }
    if units is not None:
        canonical = next(iter(units.values()))[0]
        field["unit"] = {
            "dimension": "user_defined",
            "allowed": list(units),
            "canonical": canonical,
            "unknown_allowed": False,
            "conversions": {
                unit: {
                    "canonical": normalized_unit,
                    "factor": factor,
                    "formula": f"reported_value * {factor:g}",
                }
                for unit, (normalized_unit, factor) in units.items()
            },
        }
    return field


def _schema(field: dict, schema_id: str) -> dict:
    return {
        "schema_version": "2.0",
        "schema_id": schema_id,
        "source": {"kind": "public_fixture", "version": "1"},
        "material_scope": "mixed materials",
        "primary_field_id": field["field_id"],
        "fields": [field],
    }


def _source(root: Path, text: str, *, doi: str = "10.1000/rc1") -> Path:
    source = root / "cache"
    source.mkdir(exist_ok=True)
    (source / "metadata.json").write_text(
        json.dumps({"title": "RC1 public fixture", "doi": doi}),
        encoding="utf-8",
    )
    (source / "chunks.jsonl").write_text(
        json.dumps({"chunk_id": "rc1-001", "page": 1, "text": text}) + "\n",
        encoding="utf-8",
    )
    return source


def test_start_uses_standard_ids_for_non_latin_project_names(tmp_path: Path) -> None:
    workspace = tmp_path / "中文项目"
    result = start_project(
        workspace,
        project_name="二维材料拉曼入门",
        material_system="MoS2",
        experiment_type="拉曼光谱",
        confirmed=True,
    )

    project, _ = read_markdown_record(workspace / "EA_PROJECT.md")
    assert result["values"]["project_slug"] == "mos2"
    assert project["project_id"] == "prj-mos2"


def test_journey_blocks_semantically_incomplete_verified_report(tmp_path: Path) -> None:
    start_project(tmp_path, material_system="MoS2", confirmed=True)
    write_yaml(tmp_path / "raw" / "record" / "raman" / "metadata.yml", {"ok": True})
    write_yaml(tmp_path / "reviews" / "review.yml", {"status": "confirmed"})
    write_yaml(
        tmp_path / "processed" / "sample" / "raman" / "raman_metadata.yml",
        {"ok": True},
    )
    report_id = "rpt-mos2-20260716-001"
    report_ref = f"reports/{report_id}.md"
    write_markdown_record(
        tmp_path / report_ref,
        {"report_id": report_id, "figure_ids": []},
        "# Raman 报告\n",
    )
    write_yaml(
        tmp_path / "reports" / "index.yml",
        {"reports": {report_id: {"path": report_ref}}},
    )

    result = guided_first_journey(tmp_path, method="raman")

    assert result["status"] == "blocked"
    assert result["code"] == "report_figure_contract_failed"
    assert result["details"]["failures"] == ["report_figure_ids_missing"]


def test_headerless_numeric_preview_uses_stable_column_names(tmp_path: Path) -> None:
    source = tmp_path / "headerless.txt"
    source.write_text("300.028,158\n301.0,160\n", encoding="utf-8")

    preview = preview_import(source)

    assert preview["columns"] == ["col_0", "col_1"]
    assert preview["preview_rows"][0] == ["300.028", "158"]
    assert "header_row_not_detected" in preview["warnings"]


@pytest.mark.parametrize(
    ("field_type", "text", "expected"),
    [
        ("range", "The activity window was 10-20 u.", [10.0, 20.0]),
        ("uncertain_number", "The activity window was 15 +/- 2 u.", 15.0),
    ],
)
def test_range_and_uncertainty_extract_without_regex_failure(
    tmp_path: Path, field_type: str, text: str, expected: object
) -> None:
    _project(tmp_path)
    field = _field(
        "activity_window",
        field_type,
        aliases=["activity window"],
        units={"u": ("u", 1.0)},
    )
    schema_path = tmp_path / "schema.yml"
    write_yaml(schema_path, _schema(field, f"rc1-{field_type}"))
    source = _source(tmp_path, text)
    plan_literature_data_extraction(
        tmp_path,
        schema_path=schema_path,
        sources=[source],
        dataset_id="typed",
        confirmed=True,
    )

    result = extract_literature_data(tmp_path, dataset_id="typed", confirmed=True)
    record = read_yaml(
        tmp_path / "literature" / "data-extractions" / "typed" / "candidate_records.yml"
    )["records"][0]

    assert result["failed_sources"] == 0
    assert record["reported_value"] == expected
    assert record["evidence"]["chunk_anchor"] == "rc1-001"


def test_custom_review_conditions_and_canonical_dedup_are_persisted(tmp_path: Path) -> None:
    _project(tmp_path)
    field = _field(
        "hydrogen_evolution_rate",
        "number",
        aliases=["hydrogen evolution rate"],
        units={
            "umol/g/h": ("umol/g/h", 1.0),
            "mmol/g/h": ("umol/g/h", 1000.0),
        },
        required_conditions=["light_source", "cocatalyst"],
        optional_conditions=["reactor_volume"],
    )
    schema_path = tmp_path / "schema.yml"
    write_yaml(schema_path, _schema(field, "rc1-hydrogen-rate"))
    source = _source(
        tmp_path,
        "The hydrogen evolution rate was 1.25 mmol/g/h. The hydrogen evolution rate was 1250 umol/g/h.",
    )
    plan_literature_data_extraction(
        tmp_path,
        schema_path=schema_path,
        sources=[source],
        dataset_id="rates",
        confirmed=True,
    )
    extract_literature_data(tmp_path, dataset_id="rates", confirmed=True)
    dataset = tmp_path / "literature" / "data-extractions" / "rates"
    records = read_yaml(dataset / "candidate_records.yml")["records"]

    assert records[1]["record_id"] in records[0]["audit"]["duplicate_refs"]
    assert records[0]["audit"]["conflict_refs"] == []
    reviewed = review_literature_data(
        tmp_path,
        dataset_id="rates",
        record_id=records[0]["record_id"],
        decision="accept",
        conditions={"light_source": "420 nm LED", "cocatalyst": "1 wt% Pt"},
        confirmed=True,
    )
    validation = validate_literature_data(tmp_path, dataset_id="rates")

    assert reviewed["comparison_status"] == "comparable"
    assert validation["comparable_reviewed_count"] == 1
    persisted = read_yaml(dataset / "reviewed_dataset.yml")["records"][0]
    assert persisted["conditions"]["light_source"] == "420 nm LED"
    with (dataset / "reviewed_dataset.csv").open(encoding="utf-8") as handle:
        csv_record = next(csv.DictReader(handle))
    assert json.loads(csv_record["conditions_json"])["cocatalyst"] == "1 wt% Pt"

    with pytest.raises(ValueError, match="Unsupported reviewed condition"):
        review_literature_data(
            tmp_path,
            dataset_id="rates",
            record_id=records[1]["record_id"],
            decision="accept",
            conditions={"undeclared_condition": "value"},
            confirmed=True,
        )


def test_public_universal_fixture_extracts_all_ten_types(tmp_path: Path) -> None:
    _project(tmp_path)
    fixture = Path("benchmarks/literature-universal-v1").resolve()
    schema_path = fixture / "schema.yml"
    expected = read_yaml(fixture / "expected.yml")
    assert hashlib.sha256(schema_path.read_bytes()).hexdigest() == expected[
        "schema_file_sha256"
    ]
    assert hashlib.sha256((fixture / "source" / "chunks.jsonl").read_bytes()).hexdigest() == expected[
        "source_chunks_sha256"
    ]
    assert hashlib.sha256((fixture / "source" / "metadata.json").read_bytes()).hexdigest() == expected[
        "source_metadata_sha256"
    ]
    schema_result = validate_literature_data_schema(schema_path)
    assert schema_result["status"] == "pass"
    assert schema_result["field_count"] == 10
    plan_literature_data_extraction(
        tmp_path,
        schema_path=schema_path,
        sources=[fixture / "source"],
        dataset_id="universal-ten-types",
        confirmed=True,
    )

    result = extract_literature_data(
        tmp_path, dataset_id="universal-ten-types", confirmed=True
    )
    record = read_yaml(
        tmp_path
        / "literature"
        / "data-extractions"
        / "universal-ten-types"
        / "candidate_records.yml"
    )["records"][0]

    assert result["failed_sources"] == expected["expected_source_failures"]
    assert result["candidate_count"] == expected["expected_record_count"]
    assert record["evidence"]["chunk_anchor"] == expected["expected_anchor"]
    assert {
        field_id: value["type"] for field_id, value in record["field_values"].items()
    } == expected["expected_field_types"]


@pytest.mark.parametrize("conflict_policy", ["reject_conflict", "prefer_reviewed"])
def test_conflict_policies_are_deterministic(
    tmp_path: Path, conflict_policy: str
) -> None:
    _project(tmp_path)
    field = _field(
        "catalytic_rate",
        "number",
        aliases=["catalytic rate"],
        units={"u": ("u", 1.0)},
        conflict_policy=conflict_policy,
    )
    schema_path = tmp_path / "schema.yml"
    write_yaml(schema_path, _schema(field, f"rc1-{conflict_policy}"))
    source = _source(
        tmp_path,
        "The catalytic rate was 10 u. The catalytic rate was 20 u.",
    )
    plan_literature_data_extraction(
        tmp_path,
        schema_path=schema_path,
        sources=[source],
        dataset_id="conflicts",
        confirmed=True,
    )
    extract_literature_data(tmp_path, dataset_id="conflicts", confirmed=True)
    records = read_yaml(
        tmp_path
        / "literature"
        / "data-extractions"
        / "conflicts"
        / "candidate_records.yml"
    )["records"]
    assert records[1]["record_id"] in records[0]["audit"]["conflict_refs"]

    if conflict_policy == "reject_conflict":
        with pytest.raises(ValueError, match="cannot be accepted"):
            review_literature_data(
                tmp_path,
                dataset_id="conflicts",
                record_id=records[0]["record_id"],
                decision="accept",
                confirmed=True,
            )
    else:
        first = review_literature_data(
            tmp_path,
            dataset_id="conflicts",
            record_id=records[0]["record_id"],
            decision="accept",
            confirmed=True,
        )
        assert first["comparison_status"] == "comparable"
        with pytest.raises(ValueError, match="already preferred by review"):
            review_literature_data(
                tmp_path,
                dataset_id="conflicts",
                record_id=records[1]["record_id"],
                decision="accept",
                confirmed=True,
            )


def test_pre_review_downstream_actions_have_stable_review_error(tmp_path: Path) -> None:
    _project(tmp_path)
    field = _field(
        "catalytic_rate",
        "number",
        aliases=["catalytic rate"],
        units={"u": ("u", 1.0)},
    )
    schema_path = tmp_path / "schema.yml"
    write_yaml(schema_path, _schema(field, "rc1-review-gate"))
    source = _source(tmp_path, "The catalytic rate was 10 u.")
    plan_literature_data_extraction(
        tmp_path,
        schema_path=schema_path,
        sources=[source],
        dataset_id="review-gate",
        confirmed=True,
    )
    extract_literature_data(tmp_path, dataset_id="review-gate", confirmed=True)

    with pytest.raises(ReviewRequiredError, match="data-review"):
        plot_literature_data(tmp_path, dataset_id="review-gate", confirmed=True)
    with pytest.raises(ReviewRequiredError, match="data-review"):
        export_literature_data(tmp_path, dataset_id="review-gate", confirmed=True)
