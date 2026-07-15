from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path

from pypdf import PdfWriter

from ea.literature.pipeline import (
    ContentAddressedPdfStore,
    HttpPdfRetriever,
    LiteratureFtsIndex,
    OACandidate,
    PublicMetadataDiscoveryAdapter,
    UnpaywallResolver,
    acquire_open_access_pdf,
    validate_pdf_payload,
)
from ea.literature import rank_literature_candidates
from ea.projects.service import initialize_project
from ea.storage.files import write_yaml
from ea.cli import main


def _pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_public_metadata_adapter_wraps_existing_source_contract() -> None:
    calls: list[tuple[str, str]] = []

    def fetcher(url: str, source: str) -> str:
        calls.append((url, source))
        return '{"items": [{"title": "candidate"}]}'

    adapter = PublicMetadataDiscoveryAdapter(
        name="crossref",
        fetcher=fetcher,
        url_builder=lambda source, query, limit, **kwargs: (
            f"https://example.test/{source}?q={query}&limit={limit}"
        ),
        normalizer=lambda source, payload, query: [
            {
                "source": source,
                "title": json.loads(payload)["items"][0]["title"],
                "source_query": query,
            }
        ],
    )

    results = adapter.search("MoS2 Raman", limit=5)

    assert results == [
        {"source": "crossref", "title": "candidate", "source_query": "MoS2 Raman"}
    ]
    assert calls == [("https://example.test/crossref?q=MoS2 Raman&limit=5", "crossref")]


def test_unpaywall_resolver_deduplicates_and_redacts_query_strings() -> None:
    payload = {
        "best_oa_location": {
            "url_for_pdf": "https://repository.example/paper.pdf?token=secret",
            "version": "publishedVersion",
            "host_type": "repository",
        },
        "oa_locations": [
            {"url_for_pdf": "https://repository.example/paper.pdf?other=secret"},
            {"url_for_pdf": "https://publisher.example/paper.pdf"},
        ],
    }
    resolver = UnpaywallResolver(
        email="maintainer@example.org", fetcher=lambda url: json.dumps(payload)
    )

    candidates = resolver.resolve("https://doi.org/10.1000/Example")

    assert [candidate.url for candidate in candidates] == [
        "https://repository.example/paper.pdf",
        "https://publisher.example/paper.pdf",
    ]
    assert all("secret" not in candidate.url for candidate in candidates)


def test_bounded_retriever_isolates_failure_and_validates_pdf() -> None:
    pdf = _pdf_bytes()

    def fetch(url: str):
        if "first" in url:
            raise TimeoutError("injected")
        return pdf, "application/pdf", 200, url

    result = HttpPdfRetriever(fetcher=fetch).acquire(
        [
            OACandidate("https://example.org/first", "test"),
            OACandidate("https://example.org/second", "test"),
        ]
    )

    assert result["status"] == "acquired"
    assert len(result["attempts"]) == 2
    assert result["validation"]["page_count"] == 1


def test_pdf_validation_rejects_html_even_when_mime_claims_pdf() -> None:
    result = validate_pdf_payload(b"<html>login</html>", content_type="application/pdf")

    assert result["status"] == "fail"
    assert "pdf_signature_missing" in result["findings"]


def test_content_addressed_store_and_acquisition_are_idempotent(tmp_path: Path) -> None:
    pdf = _pdf_bytes()

    class Resolver:
        name = "fixture"

        def resolve(self, doi: str):
            return [OACandidate("https://repository.example/paper.pdf", "fixture")]

    retriever = HttpPdfRetriever(fetcher=lambda url: (pdf, "application/pdf", 200, url))
    first = acquire_open_access_pdf(
        tmp_path,
        doi="10.1000/idempotent",
        resolver=Resolver(),
        retriever=retriever,
        confirmed=True,
    )
    second = acquire_open_access_pdf(
        tmp_path,
        doi="10.1000/idempotent",
        resolver=Resolver(),
        retriever=retriever,
        confirmed=True,
    )

    assert first["cache"]["status"] == "created"
    assert second["cache"]["status"] == "reused"
    assert first["cache"]["object_ref"] == second["cache"]["object_ref"]
    assert (
        len(list((tmp_path / "literature" / "cache" / "objects").rglob("*.pdf"))) == 1
    )


def test_fts_index_tracks_freshness_quality_and_never_overclaims_absence(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(_pdf_bytes())
    index = LiteratureFtsIndex(tmp_path)
    indexed = index.index_pdf(pdf_path)

    assert indexed["quality_state"] == "needs_ocr_or_original_page"
    assert index.is_fresh(indexed["object_hash"]) is True
    result = index.targeted_search("missing evidence", initial_chunks=3)
    assert result["status"] == "not_found_in_searchable_text"
    assert "may still require OCR" in result["interpretation_boundary"]


def test_content_store_detects_existing_hash_mismatch(tmp_path: Path) -> None:
    pdf = _pdf_bytes()
    store = ContentAddressedPdfStore(tmp_path)
    first = store.put(pdf, page_count=1)
    object_path = tmp_path / first["object_ref"]
    object_path.write_bytes(b"corrupt")

    try:
        store.put(pdf, page_count=1)
    except RuntimeError as exc:
        assert "failed its hash check" in str(exc)
    else:
        raise AssertionError("hash mismatch was not detected")


def test_ranking_preserves_but_downranks_supplements_and_fuses_sources(
    tmp_path: Path,
) -> None:
    initialize_project(
        tmp_path,
        project_name="MoS2 Raman",
        project_slug="mos2-ranking",
        research_direction="MoS2 Raman strain",
        material_system="MoS2",
        experiment_type="Raman strain",
        enable_literature=True,
    )
    candidates = tmp_path / "literature" / "candidates.yml"
    write_yaml(
        candidates,
        {
            "candidates": [
                {
                    "title": "MoS2 Raman strain article",
                    "doi": "10.1000/main",
                    "source": "crossref",
                    "document_type": "journal-article",
                    "year": 2026,
                },
                {
                    "title": "MoS2 Raman strain article",
                    "doi": "10.1000/main",
                    "source": "openalex",
                    "document_type": "article",
                    "year": 2026,
                },
                {
                    "title": "MoS2 Raman strain supplementary data",
                    "doi": "10.1000/supp",
                    "source": "crossref",
                    "document_type": "supplement",
                    "year": 2026,
                },
            ]
        },
    )

    result = rank_literature_candidates(
        tmp_path,
        candidates_path=candidates,
        extra_keywords=["strain"],
        reference_year=2026,
    )

    rows = list(
        __import__("csv").DictReader(
            (tmp_path / "literature" / "ranking.csv").open(encoding="utf-8")
        )
    )
    assert result["deduped_count"] == 2
    assert rows[0]["document_type"] == "article"
    assert rows[0]["source_count"] == "2"
    assert rows[1]["document_type"] == "supplement"
    assert float(rows[1]["score"]) < float(rows[0]["score"])


def test_cli_oa_plan_is_confirmation_gated_and_compact(tmp_path: Path, capsys) -> None:
    assert (
        main(
            [
                "literature",
                "acquire-oa",
                str(tmp_path),
                "--doi",
                "10.1000/example",
                "--email",
                "test@example.org",
            ]
        )
        == 0
    )

    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "needs_confirmation"
    assert result["doi"] == "10.1000/example"
    assert len(json.dumps(result)) <= 2048


def test_cli_cache_search_is_compact_by_default(tmp_path: Path, capsys) -> None:
    index = LiteratureFtsIndex(tmp_path)
    with index._connect() as connection:
        connection.execute(
            "INSERT INTO chunks(object_hash, page, chunk_index, text) VALUES (?, ?, ?, ?)",
            ("a" * 64, 7, 0, "MoS2 Raman strain evidence"),
        )
        connection.execute(
            "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("a" * 64, "a" * 64, "pypdf-targeted-v1", "2.0", 10, 1, "searchable_text"),
        )

    assert (
        main(["literature", "search-cache", str(tmp_path), "--query", "Raman strain"])
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["evidence_count"] == 1
    assert result["page_anchors"] == [7]
    assert "results" not in result
