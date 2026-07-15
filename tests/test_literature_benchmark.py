from __future__ import annotations

import csv
from io import BytesIO
from pathlib import Path

from pypdf import PdfWriter

from ea.literature import (
    ContentAddressedPdfStore,
    LiteratureFtsIndex,
    rank_literature_candidates,
)
from ea.projects import initialize_project
from ea.storage.files import read_yaml, write_yaml


def _pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_literature_pipeline_non_regression_benchmark(tmp_path: Path) -> None:
    fixture = read_yaml(Path("benchmarks/literature-v0.9.9.yml"))
    initialize_project(
        tmp_path,
        project_name="MoS2 Raman strain",
        project_slug="literature-benchmark",
        research_direction="Raman strain coefficient",
        material_system="MoS2",
        experiment_type="Raman",
        enable_literature=True,
    )
    candidates = tmp_path / "literature" / "benchmark-candidates.yml"
    write_yaml(
        candidates,
        {
            "candidates": [
                {
                    "title": "MoS2 Raman strain coefficient main article",
                    "doi": "10.1000/main",
                    "source": "crossref",
                    "document_type": "article",
                    "citation_count": 50,
                },
                {
                    "title": "MoS2 Raman strain coefficient main article",
                    "doi": "10.1000/main",
                    "source": "openalex",
                    "document_type": "journal-article",
                    "citation_count": 51,
                },
                {
                    "title": "MoS2 Raman strain coefficient independent validation",
                    "doi": "10.1000/second",
                    "source": "arxiv",
                    "document_type": "preprint",
                    "citation_count": 5,
                },
                {
                    "title": "MoS2 Raman strain coefficient supplementary tables",
                    "doi": "10.1000/supplement",
                    "source": "crossref",
                    "document_type": "supplement",
                    "citation_count": 1,
                },
                {
                    "title": "Unrelated highly cited catalyst survey",
                    "doi": "10.1000/irrelevant",
                    "source": "crossref",
                    "document_type": "article",
                    "citation_count": 50000,
                },
            ]
        },
    )

    result = rank_literature_candidates(
        tmp_path,
        candidates_path=candidates,
        extra_keywords=["strain coefficient"],
        top_n=3,
        reference_year=2026,
    )
    rows = list(
        csv.DictReader((tmp_path / "literature" / "ranking.csv").open(encoding="utf-8"))
    )
    top_three = rows[:3]
    expected = set(fixture["ranking"]["expected_relevant_dois"])
    returned = {row["doi"] for row in top_three}
    recall_at_3 = len(expected & returned) / len(expected)
    precision_at_3 = len(expected & returned) / len(top_three)
    parent_rank = next(
        index for index, row in enumerate(rows) if row["doi"] == "10.1000/main"
    )
    supplement_rank = next(
        index for index, row in enumerate(rows) if row["doi"] == "10.1000/supplement"
    )

    assert result["duplicate_candidate_count"] == 1
    assert result["relevance_rejected_count"] >= 1
    assert recall_at_3 >= fixture["ranking"]["recall_at_3_min"]
    assert precision_at_3 >= fixture["ranking"]["precision_at_3_min"]
    assert (
        int(supplement_rank < parent_rank)
        <= fixture["ranking"]["supplement_above_parent_max"]
    )

    store = ContentAddressedPdfStore(tmp_path)
    cold = store.put(_pdf_bytes(), page_count=1)
    warm = store.put(_pdf_bytes(), page_count=1)
    assert cold["status"] == "created"
    assert warm["status"] == "reused"
    assert cold["object_ref"] == warm["object_ref"]

    index = LiteratureFtsIndex(tmp_path)
    with index._connect() as connection:
        connection.execute(
            "INSERT INTO chunks(object_hash, page, chunk_index, text) VALUES (?, ?, ?, ?)",
            (
                "a" * 64,
                7,
                0,
                "The measured MoS2 Raman strain coefficient is evidence for this benchmark.",
            ),
        )
        connection.execute(
            "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("a" * 64, "a" * 64, "pypdf-targeted-v1", "2.0", 8, 1, "searchable_text"),
        )
    evidence = index.targeted_search(
        fixture["retrieval"]["known_evidence_query"],
        initial_chunks=fixture["resource_gates"]["initial_chunk_limit"],
    )
    assert evidence["status"] == "evidence_found"
    assert evidence["results"][0]["page"] == fixture["retrieval"]["expected_page"]
    assert (
        evidence["metrics"]["chunks_considered"]
        <= fixture["resource_gates"]["initial_chunk_limit"]
    )
    assert evidence["metrics"]["exact_model_tokens_available"] is False
