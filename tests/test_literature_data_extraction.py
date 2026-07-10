from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path

import pytest

from ea.cli import main
from ea.literature import (
    export_literature_data,
    extract_literature_data,
    plan_literature_data_extraction,
    plot_literature_data,
    review_literature_data,
    validate_literature_data,
)
from ea.projects import initialize_project
from ea.storage import read_yaml


def _project(root: Path) -> None:
    initialize_project(
        root,
        project_name="2D Conductivity Evidence",
        project_slug="2d-conductivity-evidence",
        research_direction="cross-paper conductivity evidence",
        material_system="two-dimensional materials",
        experiment_type="literature data extraction",
    )


def _cache_source(root: Path, index: int, *, doi: str | None = None, text: str | None = None) -> Path:
    cache = root / "test-caches" / f"paper-{index:02d}"
    cache.mkdir(parents=True)
    (cache / "metadata.json").write_text(
        json.dumps(
            {
                "title": f"Conductivity paper {index}",
                "doi": doi or f"10.1000/conductivity-{index}",
                "item_key": f"ITEM{index:04d}",
                "pdf_sha256": f"{index:064x}",
            }
        ),
        encoding="utf-8",
    )
    sentence = text or (
        f"The electrical conductivity was {index}.0 S/cm at 300 K using a four-probe "
        "in-plane measurement on SiO2 substrate."
    )
    (cache / "chunks.jsonl").write_text(
        json.dumps(
            {
                "chunk_id": f"chunk-{index:03d}",
                "page": index,
                "section": "Electrical transport",
                "table": "Table 1",
                "text": sentence,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return cache


def test_ten_paper_conductivity_pilot_is_resumable_and_evidence_anchored(tmp_path: Path) -> None:
    _project(tmp_path)
    sources = [_cache_source(tmp_path, index) for index in range(1, 11)]

    preview = plan_literature_data_extraction(
        tmp_path,
        property_name="electrical conductivity",
        property_kind="conductivity",
        material_name="two-dimensional materials",
        sources=sources,
        required_conditions=["temperature", "direction", "instrument_or_method"],
        dataset_id="conductivity-pilot",
    )
    assert preview["status"] == "ready_to_create"
    assert not (tmp_path / "literature" / "data-extractions" / "conductivity-pilot").exists()

    plan = plan_literature_data_extraction(
        tmp_path,
        property_name="electrical conductivity",
        property_kind="conductivity",
        material_name="two-dimensional materials",
        sources=sources,
        required_conditions=["temperature", "direction", "instrument_or_method"],
        comparability_rules=["same normalized unit", "retain temperature and direction"],
        dataset_id="conductivity-pilot",
        confirmed=True,
        created_at="2026-07-10T16:00:00",
    )
    first = extract_literature_data(
        tmp_path,
        dataset_id="conductivity-pilot",
        max_sources=3,
        confirmed=True,
        extracted_at="2026-07-10T16:01:00",
    )
    resumed = extract_literature_data(
        tmp_path,
        dataset_id="conductivity-pilot",
        confirmed=True,
        extracted_at="2026-07-10T16:02:00",
    )
    reused = extract_literature_data(
        tmp_path,
        dataset_id="conductivity-pilot",
        confirmed=True,
        extracted_at="2026-07-10T16:03:00",
    )

    dataset = tmp_path / "literature" / "data-extractions" / "conductivity-pilot"
    records = read_yaml(dataset / "candidate_records.yml")["records"]
    state = read_yaml(dataset / "extraction_state.compact.yml")

    assert plan["source_count"] == 10
    assert first["processed_now"] == 3
    assert first["candidate_count"] == 3
    assert resumed["processed_now"] == 7
    assert resumed["candidate_count"] == 10
    assert reused["processed_now"] == 0
    assert reused["reused_checkpoints"] == 10
    assert len(records) == 10
    assert len(state["checkpoints"]) == 10
    assert state["metrics"]["papers_processed"] == 10
    assert state["metrics"]["chunks_read"] == 10
    assert all(record["property_kind"] == "conductivity" for record in records)
    assert all(record["reported_unit"].lower() == "s/cm" for record in records)
    assert all(record["normalized_unit"] == "S/m" for record in records)
    assert all(record["conversion_formula"] == "reported_value * 100" for record in records)
    assert all(record["evidence"]["page"] != "not_reported" for record in records)
    assert all(record["evidence"]["chunk_anchor"].startswith("chunk-") for record in records)
    assert all(record["conditions"]["temperature"] == "300 K" for record in records)
    assert all(record["conditions"]["direction"] == "in_plane" for record in records)
    assert all(record["conditions"]["instrument_or_method"] == "four_probe" for record in records)


def test_only_reviewed_comparable_records_enter_plot_and_export(tmp_path: Path) -> None:
    _project(tmp_path)
    sources = [_cache_source(tmp_path, index) for index in range(1, 7)]
    plan_literature_data_extraction(
        tmp_path,
        property_name="electrical conductivity",
        property_kind="conductivity",
        material_name="2D films",
        sources=sources,
        required_conditions=["temperature", "direction"],
        dataset_id="reviewed-only",
        confirmed=True,
    )
    extract_literature_data(tmp_path, dataset_id="reviewed-only", confirmed=True)
    dataset = tmp_path / "literature" / "data-extractions" / "reviewed-only"
    records = read_yaml(dataset / "candidate_records.yml")["records"]

    for record in records[:4]:
        review_literature_data(
            tmp_path,
            dataset_id="reviewed-only",
            record_id=record["record_id"],
            decision="accept",
            notes=["Verified against the cited page and table."],
            confirmed=True,
        )
    review_literature_data(
        tmp_path,
        dataset_id="reviewed-only",
        record_id=records[4]["record_id"],
        decision="not-comparable",
        notes=["Different device geometry."],
        confirmed=True,
    )

    validation = validate_literature_data(tmp_path, dataset_id="reviewed-only")
    plot = plot_literature_data(tmp_path, dataset_id="reviewed-only", confirmed=True, created_at="2026-07-10T16:20:00")
    export = export_literature_data(tmp_path, dataset_id="reviewed-only", confirmed=True, exported_at="2026-07-10T16:21:00")

    with (dataset / "plots" / "source_data.csv").open(encoding="utf-8") as handle:
        plotted = list(csv.DictReader(handle))
    archive = tmp_path / export["archive_ref"]
    with zipfile.ZipFile(archive) as bundle:
        names = set(bundle.namelist())

    assert validation["reviewed_count"] == 4
    assert validation["comparable_reviewed_count"] == 4
    assert plot["plotted_record_count"] == 4
    assert len(plotted) == 4
    assert {row["review_state"] for row in plotted} == {"accepted"}
    assert plot["figure_id"].startswith("fig-reviewed-only")
    assert Path(tmp_path / plot["figure_ref"]).exists()
    assert export["reviewed_record_count"] == 4
    assert "candidate_records.yml" not in names
    assert "reviewed_dataset.yml" in names
    assert "report.md" in names
    assert "manifest.json" in names


def test_missing_unit_requires_edit_and_duplicate_doi_conflicts_are_preserved(tmp_path: Path) -> None:
    _project(tmp_path)
    missing = _cache_source(
        tmp_path,
        1,
        doi="10.1000/duplicate",
        text="The electrical conductivity was 4.2 at 300 K using a four-probe in-plane method.",
    )
    conflicting = _cache_source(
        tmp_path,
        2,
        doi="10.1000/duplicate",
        text="The electrical conductivity was 8.0 S/cm at 300 K using a four-probe in-plane method.",
    )
    plan_literature_data_extraction(
        tmp_path,
        property_name="electrical conductivity",
        property_kind="conductivity",
        material_name="2D duplicate fixture",
        sources=[missing, conflicting],
        required_conditions=["temperature", "direction"],
        dataset_id="conflict-fixture",
        confirmed=True,
    )
    extract_literature_data(tmp_path, dataset_id="conflict-fixture", confirmed=True)
    dataset = tmp_path / "literature" / "data-extractions" / "conflict-fixture"
    records = read_yaml(dataset / "candidate_records.yml")["records"]
    first, second = records

    assert len(records) == 2
    assert first["reported_unit"] == "not_reported"
    assert "missing_reported_unit" in first["audit"]["warnings"]
    assert second["record_id"] in first["audit"]["conflict_refs"]
    assert first["record_id"] in second["audit"]["conflict_refs"]
    with pytest.raises(ValueError, match="cannot be accepted"):
        review_literature_data(
            tmp_path,
            dataset_id="conflict-fixture",
            record_id=first["record_id"],
            decision="accept",
            confirmed=True,
        )

    edited = review_literature_data(
        tmp_path,
        dataset_id="conflict-fixture",
        record_id=first["record_id"],
        decision="edit",
        reported_unit="S/cm",
        normalized_value=420.0,
        normalized_unit="S/m",
        notes=["Unit verified manually in Table 1."],
        confirmed=True,
    )
    assert edited["review_state"] == "edited"
    assert edited["comparison_status"] == "not_comparable_conflicting_evidence"
    with pytest.raises(ValueError, match="No reviewed, comparable"):
        plot_literature_data(tmp_path, dataset_id="conflict-fixture", confirmed=True)


def test_electrical_property_kinds_are_not_silently_mixed_and_cli_is_confirmation_gated(tmp_path: Path, capsys) -> None:
    _project(tmp_path)
    source = _cache_source(
        tmp_path,
        1,
        text=(
            "The electrical conductivity was 3.0 S/cm at 300 K. "
            "The sheet resistance was 12 kohm/sq at 300 K using a four-probe in-plane method."
        ),
    )
    assert (
        main(
            [
                "literature",
                "data-plan",
                str(tmp_path),
                "--property",
                "sheet resistance",
                "--kind",
                "sheet_resistance",
                "--material",
                "2D film",
                "--dataset-id",
                "sheet-only",
                "--source",
                str(source),
            ]
        )
        == 0
    )
    preview = json.loads(capsys.readouterr().out)
    assert preview["requires_confirmation"] is True
    assert not (tmp_path / "literature" / "data-extractions" / "sheet-only").exists()

    assert (
        main(
            [
                "literature",
                "data-plan",
                str(tmp_path),
                "--property",
                "sheet resistance",
                "--kind",
                "sheet_resistance",
                "--material",
                "2D film",
                "--dataset-id",
                "sheet-only",
                "--source",
                str(source),
                "--yes",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert main(["literature", "data-extract", str(tmp_path), "--dataset", "sheet-only", "--yes"]) == 0
    output = json.loads(capsys.readouterr().out)
    records = read_yaml(tmp_path / "literature" / "data-extractions" / "sheet-only" / "candidate_records.yml")["records"]

    assert output["candidate_count"] == 1
    assert records[0]["property_kind"] == "sheet_resistance"
    assert records[0]["normalized_unit"] == "ohm/sq"
    assert records[0]["normalized_value"] == 12000.0


def test_caption_extraction_and_ocr_required_failure_remain_explicit(tmp_path: Path) -> None:
    _project(tmp_path)
    caption_cache = tmp_path / "test-caches" / "caption-paper"
    caption_cache.mkdir(parents=True)
    (caption_cache / "metadata.json").write_text(
        json.dumps({"title": "Caption paper", "doi": "10.1000/caption"}),
        encoding="utf-8",
    )
    (caption_cache / "chunks.jsonl").write_text(
        json.dumps(
            {
                "chunk_id": "caption-001",
                "page": 4,
                "figure": "Figure 2",
                "caption": "Electrical conductivity was 6.0 S/cm at 300 K using a four-probe in-plane method.",
                "text": "Figure discussion.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    ocr_cache = tmp_path / "test-caches" / "ocr-paper"
    ocr_cache.mkdir(parents=True)
    (ocr_cache / "metadata.json").write_text(json.dumps({"title": "Scanned paper"}), encoding="utf-8")
    (ocr_cache / "chunks.jsonl").write_text(json.dumps({"chunk_id": "blank", "page": 1, "text": ""}) + "\n", encoding="utf-8")

    plan_literature_data_extraction(
        tmp_path,
        property_name="electrical conductivity",
        property_kind="conductivity",
        material_name="2D caption fixture",
        sources=[caption_cache, ocr_cache],
        dataset_id="caption-ocr",
        confirmed=True,
    )
    result = extract_literature_data(tmp_path, dataset_id="caption-ocr", confirmed=True)
    dataset = tmp_path / "literature" / "data-extractions" / "caption-ocr"
    records = read_yaml(dataset / "candidate_records.yml")["records"]
    state = read_yaml(dataset / "extraction_state.compact.yml")
    evidence = read_yaml(dataset / "evidence" / "source-001.yml")

    assert result["candidate_count"] == 1
    assert result["failed_sources"] == 1
    assert records[0]["evidence"]["figure"] == "Figure 2"
    assert records[0]["evidence"]["caption"].startswith("Electrical conductivity")
    assert evidence["records"][0]["chunk_anchor"] == "caption-001"
    assert len(evidence["records"][0]["short_context"]) < 400
    assert state["checkpoints"]["source-002"]["error_code"] == "ocr_required"
    assert state["checkpoints"]["source-002"]["safe_to_retry"] is True
