from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import sqlite3
import time
from typing import Any, Callable, Protocol, Sequence
from urllib.parse import quote
from urllib.request import Request, urlopen

from pypdf import PdfReader

from ea.literature.handoff import privacy_safe_url
from ea.storage.files import read_yaml, write_yaml


PIPELINE_SCHEMA_VERSION = "2.0"
EXTRACTOR_VERSION = "pypdf-targeted-v1"


class DiscoveryAdapter(Protocol):
    name: str

    def search(self, query: str, *, limit: int) -> list[dict[str, Any]]: ...


@dataclass
class PublicMetadataDiscoveryAdapter:
    """Versioned adapter around an existing public-metadata source implementation."""

    name: str
    fetcher: Callable[[str, str], str]
    url_builder: Callable[..., str]
    normalizer: Callable[..., list[dict[str, Any]]]
    version: str = "1.0"

    def search(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        _, candidates = self.search_page(query, limit=limit)
        return candidates

    def search_page(
        self,
        query: str,
        *,
        limit: int,
        cursor: str | None = None,
        offset: int = 0,
    ) -> tuple[str, list[dict[str, Any]]]:
        url = self.url_builder(self.name, query, limit, cursor=cursor, offset=offset)
        response = self.fetcher(url, self.name)
        return response, self.normalizer(self.name, response, query=query)


class AccessResolver(Protocol):
    name: str

    def resolve(self, doi: str) -> list["OACandidate"]: ...


class Retriever(Protocol):
    name: str

    def acquire(self, candidates: Sequence["OACandidate"]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class OACandidate:
    url: str
    source: str
    version: str | None = None
    host_type: str | None = None
    request_url: str | None = field(default=None, repr=False, compare=False)


def canonical_doi(value: str) -> str:
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value.strip().lower()).rstrip(
        "./"
    )
    if not doi or "/" not in doi:
        raise ValueError("A canonical DOI is required.")
    return doi


class UnpaywallResolver:
    name = "unpaywall"

    def __init__(
        self, *, email: str, fetcher: Callable[[str], str] | None = None
    ) -> None:
        if "@" not in email:
            raise ValueError("Unpaywall requires a contact email.")
        self.email = email
        self.fetcher = fetcher or self._fetch

    @staticmethod
    def _fetch(url: str) -> str:
        request = Request(
            url, headers={"User-Agent": "Experimental-Assistant OA resolver"}
        )
        with urlopen(request, timeout=20) as response:  # noqa: S310 - explicit public OA API call
            return response.read().decode("utf-8", errors="replace")

    def resolve(self, doi: str) -> list[OACandidate]:
        normalized = canonical_doi(doi)
        url = f"https://api.unpaywall.org/v2/{quote(normalized, safe='')}?email={quote(self.email)}"
        payload = json.loads(self.fetcher(url))
        locations: list[dict[str, Any]] = []
        best = payload.get("best_oa_location")
        if isinstance(best, dict):
            locations.append(best)
        locations.extend(
            item for item in payload.get("oa_locations") or [] if isinstance(item, dict)
        )
        candidates: list[OACandidate] = []
        seen: set[str] = set()
        for location in locations:
            candidate_url = location.get("url_for_pdf") or location.get("url")
            safe = privacy_safe_url(candidate_url)
            if not safe or safe in seen:
                continue
            seen.add(safe)
            candidates.append(
                OACandidate(
                    url=safe,
                    source=self.name,
                    version=location.get("version"),
                    host_type=location.get("host_type"),
                    request_url=str(candidate_url),
                )
            )
        return candidates


def validate_pdf_payload(
    payload: bytes, *, content_type: str | None, status_code: int = 200
) -> dict[str, Any]:
    findings: list[str] = []
    if status_code < 200 or status_code >= 300:
        findings.append("http_status_not_success")
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    if mime not in {"application/pdf", "application/octet-stream"}:
        findings.append("mime_not_pdf")
    if not payload.startswith(b"%PDF-"):
        findings.append("pdf_signature_missing")
    page_count = 0
    if not findings:
        try:
            page_count = len(PdfReader(BytesIO(payload)).pages)
        except Exception:  # noqa: BLE001 - validator returns a stable finding code
            findings.append("pdf_parse_failed")
    if page_count <= 0 and "pdf_parse_failed" not in findings:
        findings.append("pdf_has_no_pages")
    return {
        "status": "pass" if not findings else "fail",
        "http_status": status_code,
        "content_type": mime or None,
        "pdf_signature": payload[:5].decode("ascii", errors="replace"),
        "size_bytes": len(payload),
        "page_count": page_count,
        "sha256": sha256(payload).hexdigest(),
        "findings": findings,
    }


class HttpPdfRetriever:
    name = "bounded_http_pdf"

    def __init__(
        self,
        *,
        fetcher: Callable[[str], tuple[bytes, str | None, int, str]] | None = None,
        max_attempts: int = 2,
    ) -> None:
        self.fetcher = fetcher or self._fetch
        self.max_attempts = max(1, min(max_attempts, 2))

    @staticmethod
    def _fetch(url: str) -> tuple[bytes, str | None, int, str]:
        request = Request(
            url, headers={"User-Agent": "Experimental-Assistant bounded OA retriever"}
        )
        with urlopen(request, timeout=30) as response:  # noqa: S310 - URL came from a confirmed OA resolver
            return (
                response.read(),
                response.headers.get("Content-Type"),
                response.status,
                response.geturl(),
            )

    def acquire(self, candidates: Sequence[OACandidate]) -> dict[str, Any]:
        attempts: list[dict[str, Any]] = []
        for index, candidate in enumerate(candidates[: self.max_attempts], start=1):
            try:
                payload, content_type, status_code, final_url = self.fetcher(
                    candidate.request_url or candidate.url
                )
                validation = validate_pdf_payload(
                    payload, content_type=content_type, status_code=status_code
                )
            except Exception as exc:  # noqa: BLE001 - optional resolver failures remain isolated
                attempts.append(
                    {
                        "attempt": index,
                        "stage": "retrieve",
                        "status": "retryable_error",
                        "source": candidate.source,
                        "url": privacy_safe_url(candidate.url),
                        "error_code": type(exc).__name__,
                    }
                )
                continue
            attempts.append(
                {
                    "attempt": index,
                    "stage": "retrieve",
                    "status": "completed"
                    if validation["status"] == "pass"
                    else "invalid_pdf",
                    "source": candidate.source,
                    "url": privacy_safe_url(final_url),
                    "validation": validation,
                }
            )
            if validation["status"] == "pass":
                return {
                    "status": "acquired",
                    "payload": payload,
                    "validation": validation,
                    "attempts": attempts,
                }
        return {
            "status": "blocked",
            "payload": None,
            "validation": None,
            "attempts": attempts,
        }


class ContentAddressedPdfStore:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.cache_root = self.project_root / "literature" / "cache"
        self.manifest_path = self.cache_root / "object_store.yml"

    def put(
        self,
        payload: bytes,
        *,
        source_url: str | None = None,
        page_count: int | None = None,
    ) -> dict[str, Any]:
        digest = sha256(payload).hexdigest()
        relative = (
            Path("literature")
            / "cache"
            / "objects"
            / "sha256"
            / digest[:2]
            / f"{digest}.pdf"
        )
        target = self.project_root / relative
        reused = target.is_file()
        if reused and sha256(target.read_bytes()).hexdigest() != digest:
            raise RuntimeError(
                "Existing content-addressed cache object failed its hash check."
            )
        if not reused:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(".tmp")
            temporary.write_bytes(payload)
            temporary.replace(target)
        manifest = (
            read_yaml(self.manifest_path)
            if self.manifest_path.is_file()
            else {
                "schema_version": PIPELINE_SCHEMA_VERSION,
                "objects": {},
            }
        )
        manifest.setdefault("objects", {})[digest] = {
            "ref": relative.as_posix(),
            "sha256": digest,
            "size_bytes": len(payload),
            "page_count": page_count,
            "source_url": privacy_safe_url(source_url),
        }
        write_yaml(self.manifest_path, manifest)
        return {
            "status": "reused" if reused else "created",
            "object_ref": relative.as_posix(),
            "sha256": digest,
            "size_bytes": len(payload),
            "page_count": page_count,
            "manifest_ref": "literature/cache/object_store.yml",
        }


def acquire_open_access_pdf(
    project_root: Path,
    *,
    doi: str,
    resolver: AccessResolver,
    retriever: Retriever | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    normalized = canonical_doi(doi)
    if not confirmed:
        return {
            "schema_version": PIPELINE_SCHEMA_VERSION,
            "status": "needs_confirmation",
            "doi": normalized,
            "will_use": [resolver.name, (retriever or HttpPdfRetriever()).name],
            "will_write": [
                "literature/cache/objects/sha256",
                "literature/cache/object_store.yml",
            ],
            "boundaries": [
                "Lawful OA candidates only; no login, paywall bypass, or credential access."
            ],
            "metrics": {
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                "stdout_chars": 0,
                "exact_model_tokens_available": False,
            },
        }
    candidates = resolver.resolve(normalized)
    retrieval = (retriever or HttpPdfRetriever()).acquire(candidates)
    if retrieval["status"] != "acquired":
        return {
            "schema_version": PIPELINE_SCHEMA_VERSION,
            "status": retrieval["status"],
            "doi": normalized,
            "candidate_count": len(candidates),
            "attempts": retrieval["attempts"],
            "next_action": "Use another lawful OA source or provide a user-authorized local PDF.",
            "metrics": {
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                "candidate_count": len(candidates),
                "retry_count": max(0, len(retrieval["attempts"]) - 1),
                "bytes_received": 0,
                "stdout_chars": 0,
                "exact_model_tokens_available": False,
            },
        }
    validation = retrieval["validation"]
    stored = ContentAddressedPdfStore(project_root).put(
        retrieval["payload"],
        source_url=next(
            (
                attempt.get("url")
                for attempt in reversed(retrieval["attempts"])
                if attempt.get("url")
            ),
            None,
        ),
        page_count=validation["page_count"],
    )
    return {
        "schema_version": PIPELINE_SCHEMA_VERSION,
        "status": "acquired",
        "doi": normalized,
        "candidate_count": len(candidates),
        "attempts": retrieval["attempts"],
        "pdf": validation,
        "cache": stored,
        "transaction_counts": {
            "created": int(stored["status"] == "created"),
            "reused": int(stored["status"] == "reused"),
            "rolled_back": 0,
            "partial": 0,
        },
        "metrics": {
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "candidate_count": len(candidates),
            "retry_count": max(0, len(retrieval["attempts"]) - 1),
            "bytes_received": validation["size_bytes"],
            "pages_validated": validation["page_count"],
            "cache_hit": stored["status"] == "reused",
            "stdout_chars": 0,
            "estimated_token_proxy": 0,
            "exact_model_tokens_available": False,
        },
    }


class LiteratureFtsIndex:
    def __init__(
        self, project_root: Path, *, database_path: Path | None = None
    ) -> None:
        self.project_root = project_root.resolve()
        self.database_path = (
            database_path
            or self.project_root / "literature" / "cache" / "fulltext-index.sqlite3"
        )
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(object_hash UNINDEXED, page UNINDEXED, chunk_index UNINDEXED, text, tokenize='unicode61')"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS documents (object_hash TEXT PRIMARY KEY, pdf_hash TEXT NOT NULL, extractor_version TEXT NOT NULL, schema_version TEXT NOT NULL, page_count INTEGER NOT NULL, chunk_count INTEGER NOT NULL, quality_state TEXT NOT NULL)"
        )
        return connection

    def is_fresh(self, object_hash: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM documents WHERE object_hash = ?", (object_hash,)
            ).fetchone()
        return bool(
            row
            and row["pdf_hash"] == object_hash
            and row["extractor_version"] == EXTRACTOR_VERSION
            and row["schema_version"] == PIPELINE_SCHEMA_VERSION
        )

    def index_pdf(self, pdf_path: Path, *, chunk_chars: int = 1200) -> dict[str, Any]:
        started = time.perf_counter()
        path = pdf_path if pdf_path.is_absolute() else self.project_root / pdf_path
        payload = path.read_bytes()
        validation = validate_pdf_payload(payload, content_type="application/pdf")
        if validation["status"] != "pass":
            raise ValueError(f"PDF validation failed: {validation['findings']}")
        object_hash = validation["sha256"]
        if self.is_fresh(object_hash):
            return {
                "status": "reused",
                "object_hash": object_hash,
                "database_ref": self._database_ref(),
                "metrics": {
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                    "pdf_bytes": len(payload),
                    "cache_hit": True,
                    "exact_model_tokens_available": False,
                },
            }
        reader = PdfReader(BytesIO(payload))
        rows: list[tuple[str, int, int, str]] = []
        empty_pages = 0
        for page_number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if not text:
                empty_pages += 1
                continue
            for chunk_index, start in enumerate(range(0, len(text), chunk_chars)):
                rows.append(
                    (
                        object_hash,
                        page_number,
                        chunk_index,
                        text[start : start + chunk_chars],
                    )
                )
        quality_state = (
            "needs_ocr_or_original_page" if empty_pages else "searchable_text"
        )
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM chunks WHERE object_hash = ?", (object_hash,)
            )
            connection.executemany(
                "INSERT INTO chunks(object_hash, page, chunk_index, text) VALUES (?, ?, ?, ?)",
                rows,
            )
            connection.execute(
                "INSERT OR REPLACE INTO documents VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    object_hash,
                    object_hash,
                    EXTRACTOR_VERSION,
                    PIPELINE_SCHEMA_VERSION,
                    validation["page_count"],
                    len(rows),
                    quality_state,
                ),
            )
        return {
            "status": "indexed",
            "object_hash": object_hash,
            "page_count": validation["page_count"],
            "chunk_count": len(rows),
            "empty_page_count": empty_pages,
            "quality_state": quality_state,
            "database_ref": self._database_ref(),
            "metrics": {
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                "pdf_bytes": len(payload),
                "pages_read": validation["page_count"],
                "chunks_written": len(rows),
                "cache_hit": False,
                "exact_model_tokens_available": False,
            },
        }

    def _database_ref(self) -> str:
        try:
            return (
                self.database_path.resolve().relative_to(self.project_root).as_posix()
            )
        except ValueError:
            return self.database_path.name

    @staticmethod
    def _fts_query(query: str) -> str:
        terms = re.findall(r"[\w\-]+", query, flags=re.UNICODE)
        if not terms:
            raise ValueError("Search query contains no indexable terms.")
        return " AND ".join(f'"{term}"' for term in terms[:12])

    def targeted_search(
        self,
        query: str,
        *,
        initial_chunks: int = 3,
        minimum_evidence: int = 1,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        fts_query = self._fts_query(query)
        with self._connect() as connection:
            total_chunks = connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[
                0
            ]
            document_rows = connection.execute("SELECT * FROM documents").fetchall()
            limit = min(max(initial_chunks, 1), max(total_chunks, 1))
            widened = False
            results: list[sqlite3.Row] = []
            while True:
                results = connection.execute(
                    "SELECT object_hash, page, chunk_index, text, bm25(chunks) AS score FROM chunks WHERE chunks MATCH ? ORDER BY score LIMIT ?",
                    (fts_query, limit),
                ).fetchall()
                if len(results) >= minimum_evidence or limit >= total_chunks:
                    break
                widened = True
                limit = min(total_chunks, max(limit * 2, minimum_evidence))
        quality_states = sorted({row["quality_state"] for row in document_rows})
        searched_complete_index = limit >= total_chunks
        return {
            "schema_version": PIPELINE_SCHEMA_VERSION,
            "status": "evidence_found" if results else "not_found_in_searchable_text",
            "query": query,
            "initial_chunk_limit": initial_chunks,
            "final_chunk_limit": limit,
            "total_indexed_chunks": total_chunks,
            "auto_widened": widened,
            "searched_complete_index": searched_complete_index,
            "quality_states": quality_states,
            "results": [
                {
                    "object_hash": row["object_hash"],
                    "page": row["page"],
                    "chunk_index": row["chunk_index"],
                    "bm25": row["score"],
                    "text": row["text"],
                }
                for row in results
            ],
            "interpretation_boundary": (
                "No match was found in the complete searchable index; scanned or low-quality pages may still require OCR/original-page review."
                if not results and searched_complete_index
                else "The result is a targeted evidence candidate, not a scientific conclusion."
            ),
            "database_ref": self._database_ref(),
            "metrics": {
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                "chunks_considered": limit,
                "chunks_returned": len(results),
                "context_chars": sum(len(row["text"]) for row in results),
                "estimated_token_proxy": sum(len(row["text"]) for row in results) // 4,
                "exact_model_tokens_available": False,
            },
        }
