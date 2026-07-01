from __future__ import annotations

import csv
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable, Literal

from ea.schema.models import EARecord
from ea.references.service import find_duplicate_reference, register_reference
from ea.storage.files import read_markdown_record, read_yaml, write_yaml
from ea.literature.source_packet_manifest import SourcePacketManifestError, confirmed_source_packet_library

ProjectScope = Literal["narrow", "ordinary", "review"]
AccessMode = Literal["index_only", "open_access_only", "user_authenticated"]
HandoffMode = Literal["dedicated_thread", "manual_agent", "same_thread"]
PublicMetadataSource = Literal["crossref", "openalex", "arxiv"]

SEARCH_SOURCES = [
    "project_zotero_library",
    "crossref",
    "openalex",
    "semantic_scholar",
    "pubmed_or_europe_pmc_when_relevant",
    "arxiv_and_chemrxiv",
    "publisher_or_doi_pages",
    "wos_scopus_google_scholar_cnki_wanfang_when_user_has_access",
]

PUBLIC_METADATA_SOURCES: list[PublicMetadataSource] = ["crossref", "openalex", "arxiv"]
SOURCE_CANDIDATE_METHODS = {"ftir", "uv_vis", "xps"}

RANKING_HEADERS = [
    "candidate_id",
    "title",
    "authors",
    "year",
    "venue",
    "doi",
    "url",
    "project_relevance",
    "venue_authority",
    "recency",
    "citation_or_influence",
    "fulltext_availability_and_usefulness",
    "score",
    "notes",
]

STATUS_UPDATE_FIELDS = [
    "status",
    "literature_thread_id",
    "candidate_count",
    "deduped_count",
    "downloaded_fulltext",
    "cached_fulltext",
    "needs_user_login",
    "blocked_items",
    "summary_for_origin_thread",
    "library_manifest_ref",
    "cache_index_ref",
    "reference_import",
    "zotero_codex_batch_status_ref",
    "zotero_codex_status_markdown_ref",
    "zotero_codex_sidecar_verification_ref",
    "zotero_codex_status_import_ref",
    "sidecar_verification",
]

FTIR_SOURCE_CANDIDATE_REQUIRED_FIELDS = [
    "candidate_id",
    "assignment_label",
    "wavenumber_window_cm1",
    "source_summary",
    "applicability_notes",
    "reference_ids",
    "confidence",
    "caveats",
]

XPS_SOURCE_CANDIDATE_REQUIRED_FIELDS = [
    "candidate_id",
    "suggestion_type",
    "source_summary",
    "applicability_notes",
    "reference_ids",
    "confidence",
    "caveats",
]

UV_VIS_SOURCE_CANDIDATE_REQUIRED_FIELDS = [
    "candidate_id",
    "candidate_type",
    "source_summary",
    "applicability_notes",
    "reference_ids",
    "confidence",
    "caveats",
]

UV_VIS_SOURCE_CANDIDATE_TYPES = {
    "optical_transition_model",
    "optical_gap_candidate",
    "optical_feature_assignment",
    "correction_context_candidate",
}


def recommended_top_n(scope: ProjectScope) -> int | tuple[int, int]:
    if scope == "narrow":
        return 30
    if scope == "ordinary":
        return 50
    if scope == "review":
        return (100, 200)
    raise ValueError(f"Unsupported literature scope: {scope}")


def _recommended_max(value: int | tuple[int, int]) -> int:
    return value[1] if isinstance(value, tuple) else value


def ensure_literature_status(
    root: Path,
    *,
    project_id: str,
    scope: ProjectScope = "ordinary",
    literature_thread_id: str | None = None,
) -> Path:
    path = root / "literature" / "deployment_status.yml"
    if path.exists():
        return path
    top_n = recommended_top_n(scope)
    status = {
        "schema_version": "0.2",
        "project_id": project_id,
        "status": "not_started",
        "literature_thread_id": literature_thread_id,
        "candidate_count": 0,
        "deduped_count": 0,
        "recommended_top_n": top_n,
        "selected_top_n": None,
        "downloaded_fulltext": 0,
        "cached_fulltext": 0,
        "needs_user_login": [],
        "blocked_items": [],
        "summary_for_origin_thread": (
            "Literature library has not been deployed. Ask the user before bulk search "
            "or full-text acquisition."
        ),
    }
    write_yaml(path, status)
    for sibling, data in {
        "library_manifest.yml": {"schema_version": "0.2", "project_id": project_id, "items": []},
        "search_queries.yml": {"schema_version": "0.2", "project_id": project_id, "queries": []},
        "selected_items.yml": {"schema_version": "0.2", "project_id": project_id, "items": []},
        "cache_index.yml": {"schema_version": "0.2", "project_id": project_id, "items": []},
    }.items():
        target = root / "literature" / sibling
        if not target.exists():
            write_yaml(target, data)
    return path


def _tokenize(text: str) -> list[str]:
    tokens = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9\-]{1,}|[A-Z][a-z]?[0-9A-Za-z]*", text):
        cleaned = token.strip("-").lower()
        if len(cleaned) >= 3:
            tokens.append(cleaned)
    return tokens


def _unique(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        key = value.lower()
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _project_context(root: Path) -> dict[str, Any]:
    project_path = root / "EA_PROJECT.md"
    if not project_path.exists():
        return {
            "project_id": "unknown-project",
            "project_name": "unknown project",
            "project_slug": "unknown-project",
            "research_direction": "",
            "material_system": "",
            "experiment_type": "",
        }
    frontmatter, _ = read_markdown_record(project_path)
    return frontmatter


def generate_literature_keywords(
    *,
    project_name: str,
    research_direction: str,
    material_system: str,
    experiment_type: str,
    extra_keywords: list[str] | None = None,
) -> dict[str, list[str]]:
    exact_terms = _unique(
        [
            material_system.strip(),
            project_name.strip(),
            research_direction.strip(),
            experiment_type.strip(),
        ]
        + (extra_keywords or [])
    )
    text = " ".join(exact_terms)
    method_terms = []
    for method in ["raman", "photoluminescence", "pl", "xrd", "ftir", "sem", "tem", "afm", "cvd"]:
        if method in text.lower():
            method_terms.append(method)
    material_tokens = _unique(_tokenize(material_system))
    topic_tokens = _unique(_tokenize(f"{project_name} {research_direction} {experiment_type}"))
    return {
        "exact_terms": exact_terms,
        "material_terms": material_tokens,
        "method_terms": _unique(method_terms),
        "topic_terms": topic_tokens[:20],
    }


def build_search_queries(keywords: dict[str, list[str]]) -> list[dict[str, Any]]:
    material = keywords.get("material_terms") or keywords.get("exact_terms") or ["material"]
    methods = keywords.get("method_terms") or ["characterization"]
    topics = keywords.get("topic_terms") or []
    core_material = material[0]
    queries = [
        {
            "query_id": "q-core-review",
            "query": f"{core_material} review synthesis characterization properties",
            "purpose": "broad project background and review coverage",
            "sources": SEARCH_SOURCES,
        }
    ]
    for method in methods[:6]:
        queries.append(
            {
                "query_id": f"q-method-{method.lower().replace(' ', '-')}",
                "query": f"{core_material} {method} analysis peak assignment mechanism",
                "purpose": f"method-specific literature for {method}",
                "sources": SEARCH_SOURCES,
            }
        )
    if topics:
        queries.append(
            {
                "query_id": "q-project-specific",
                "query": " ".join(_unique([core_material] + topics[:8])),
                "purpose": "project-specific synthesis, substrate, and performance context",
                "sources": SEARCH_SOURCES,
            }
        )
    return queries


def _write_csv_header(path: Path, headers: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _project_relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _compact_dict(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value not in (None, "", [], {})}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(item) for item in value if item not in (None, ""))
    return str(value)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "open", "oa"}


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _score_component(value: Any) -> float | None:
    parsed = _as_float(value)
    if parsed is None:
        return None
    if parsed > 5:
        parsed = parsed / 20 if parsed <= 100 else 5
    return max(0.0, min(5.0, parsed))


def _write_csv_rows(path: Path, headers: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _estimate_confirmation(scope: ProjectScope, top_n: int | tuple[int, int], access_mode: AccessMode) -> dict[str, Any]:
    recommended_max = _recommended_max(top_n)
    multiplier = 1.0 if access_mode == "index_only" else 1.5 if access_mode == "open_access_only" else 2.2
    return {
        "recommended_top_n": top_n,
        "estimated_time_minutes": {
            "search_and_rank": max(10, int(recommended_max * 0.8)),
            "fulltext_acquisition_after_confirmation": int(recommended_max * multiplier),
        },
        "estimated_token_budget": {
            "planning_and_ranking": f"{recommended_max * 200}-{recommended_max * 400}",
            "fulltext_reading_after_confirmation": f"{recommended_max * 1000}-{recommended_max * 2500}",
        },
        "estimated_storage_mb": {
            "metadata_only": max(1, int(recommended_max * 0.05)),
            "fulltext_cache_after_confirmation": f"{recommended_max * 2}-{recommended_max * 8}",
        },
        "access_mode": access_mode,
        "requires_user_confirmation_before_download": True,
        "notes": [
            "This plan does not guarantee exhaustive web coverage; it creates a systematic source/query log.",
            (
                "Journal impact factors or venue metrics may be used when supplied by the user, "
                "retrieved by a dedicated user-confirmed literature workflow, or otherwise recorded "
                "from verified sources; otherwise use source-labeled venue/citation proxies and do not invent IF values."
            ),
            "Credentials, SSO, VPN, browser profiles, and Zotero paths must be supplied by the user, not assumed.",
        ],
    }


def _timestamp_key(value: str | None = None) -> str:
    raw = value or EARecord.now_iso()
    return (
        raw.replace("-", "")
        .replace(":", "")
        .replace("+", "")
        .replace(".", "")
        .replace("T", "T")[:15]
    )


def _reference_year(value: int | None = None) -> int:
    if value:
        return value
    return int(EARecord.now_iso()[:4])


def plan_literature_deployment(
    root: Path,
    *,
    scope: ProjectScope = "ordinary",
    access_mode: AccessMode = "open_access_only",
    extra_keywords: list[str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    literature_root = root / "literature"
    literature_root.mkdir(parents=True, exist_ok=True)
    project = _project_context(root)
    project_id = str(project.get("project_id", "unknown-project"))
    status_path = ensure_literature_status(root, project_id=project_id, scope=scope)
    keywords = generate_literature_keywords(
        project_name=str(project.get("project_name", "")),
        research_direction=str(project.get("research_direction", "")),
        material_system=str(project.get("material_system", "")),
        experiment_type=str(project.get("experiment_type", "")),
        extra_keywords=extra_keywords,
    )
    queries = build_search_queries(keywords)
    top_n = recommended_top_n(scope)
    confirmation = _estimate_confirmation(scope, top_n, access_mode)
    confirmation.update(
        {
            "schema_version": "0.2",
            "project_id": project_id,
            "status": "awaiting_user_confirmation",
            "candidate_count": 0,
            "deduped_count": 0,
            "scope": scope,
            "keywords_summary": keywords,
            "recommended_action": "Confirm selected_top_n before any bulk search or full-text acquisition.",
        }
    )
    write_yaml(
        literature_root / "search_queries.yml",
        {
            "schema_version": "0.2",
            "project_id": project_id,
            "scope": scope,
            "access_mode": access_mode,
            "keywords": keywords,
            "queries": queries,
            "coverage_goal": "systematic_multi_source_search_with_logged_gaps",
            "sources": SEARCH_SOURCES,
        },
    )
    _write_csv_header(literature_root / "candidates.csv", RANKING_HEADERS[:7] + ["source", "abstract", "keywords"])
    _write_csv_header(literature_root / "ranking.csv", RANKING_HEADERS)
    write_yaml(literature_root / "confirmation_request.yml", confirmation)
    search_log = "\n".join(
        [
            "# Literature Search Log",
            "",
            f"- project_id: {project_id}",
            f"- scope: {scope}",
            f"- access_mode: {access_mode}",
            "- status: planned; no external search or download has been executed.",
            "",
            "## Coverage Plan",
            "",
            *[f"- {source}" for source in SEARCH_SOURCES],
            "",
            "## Queries",
            "",
            *[f"- `{query['query_id']}`: {query['query']}" for query in queries],
            "",
            "## Known Limits",
            "",
            "- No claim of exhaustive web coverage.",
            "- Full-text acquisition requires user confirmation and lawful access.",
            "- Institution login, Zotero, browser profile, and cache paths are user-supplied settings.",
        ]
    )
    (literature_root / "search_log.md").write_text(search_log + "\n", encoding="utf-8")
    status = read_yaml(status_path)
    status.update(
        {
            "status": "planned_awaiting_user_confirmation",
            "candidate_count": 0,
            "deduped_count": 0,
            "recommended_top_n": top_n,
            "selected_top_n": None,
            "search_queries_ref": "literature/search_queries.yml",
            "confirmation_request_ref": "literature/confirmation_request.yml",
            "access_mode": access_mode,
            "summary_for_origin_thread": (
                "Literature deployment plan prepared. Awaiting user confirmation for selected_top_n "
                "before search/download/acquisition."
            ),
        }
    )
    write_yaml(status_path, status)
    return {
        "project_id": project_id,
        "status_path": str(status_path),
        "search_queries_path": str(literature_root / "search_queries.yml"),
        "search_log_path": str(literature_root / "search_log.md"),
        "candidates_path": str(literature_root / "candidates.csv"),
        "ranking_path": str(literature_root / "ranking.csv"),
        "confirmation_request_path": str(literature_root / "confirmation_request.yml"),
        "confirmation": confirmation,
    }


def confirm_literature_selection(
    root: Path,
    *,
    selected_top_n: int,
    user_response: str,
    confirmed_at: str | None = None,
) -> dict[str, Any]:
    if selected_top_n <= 0:
        raise ValueError("selected_top_n must be positive")
    status_path = root / "literature" / "deployment_status.yml"
    status = read_yaml(status_path) if status_path.exists() else {}
    recommended = status.get("recommended_top_n", 50)
    recommended_max = _recommended_max(recommended)
    warnings = list(status.get("warnings") or [])
    if selected_top_n > recommended_max:
        warnings.append(
            {
                "code": "selected_top_n_above_recommendation",
                "message": "User selected more papers than the default recommendation; execute in batches.",
                "severity": "medium",
            }
        )
    status.update(
        {
            "status": "confirmed_awaiting_acquisition",
            "selected_top_n": selected_top_n,
            "confirmed_at": confirmed_at,
            "user_response": user_response,
            "warnings": warnings,
            "summary_for_origin_thread": (
                f"User confirmed literature deployment for top {selected_top_n}. "
                "Next step is search/ranking/acquisition in a dedicated literature workflow."
            ),
        }
    )
    write_yaml(status_path, status)
    selected_path = root / "literature" / "selected_items.yml"
    selected = read_yaml(selected_path) if selected_path.exists() else {"schema_version": "0.2", "items": []}
    selected.update(
        {
            "project_id": status.get("project_id"),
            "selection_status": "awaiting_search_results",
            "selected_top_n": selected_top_n,
            "user_response": user_response,
            "items": selected.get("items", []),
        }
    )
    write_yaml(selected_path, selected)
    return {
        "status_path": str(status_path),
        "selected_items_path": str(selected_path),
        "status": status,
    }


def prepare_literature_acquisition_handoff(
    root: Path,
    *,
    handoff_mode: HandoffMode = "dedicated_thread",
    literature_thread_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    literature_root = root / "literature"
    status_path = literature_root / "deployment_status.yml"
    if not status_path.exists():
        raise FileNotFoundError(status_path)
    status = read_yaml(status_path)
    if status.get("status") not in {
        "confirmed_awaiting_acquisition",
        "ranked_candidates_ready",
        "acquisition_handoff_ready",
    }:
        raise ValueError("Literature acquisition handoff requires confirmed_awaiting_acquisition status")
    selected_top_n = status.get("selected_top_n")
    if not selected_top_n:
        raise ValueError("Literature acquisition handoff requires selected_top_n")

    project = _project_context(root)
    project_id = str(status.get("project_id") or project.get("project_id", "unknown-project"))
    created_at = created_at or EARecord.now_iso()
    handoff_id = f"lit-handoff-{_timestamp_key(created_at)}"
    handoff_path = literature_root / "acquisition_handoff.yml"
    prompt_path = literature_root / "acquisition_handoff.md"
    sync_path = literature_root / "origin_thread_sync.yml"
    handoff = {
        "schema_version": "0.2",
        "handoff_id": handoff_id,
        "project_id": project_id,
        "created_at": created_at,
        "handoff_mode": handoff_mode,
        "literature_thread_id": literature_thread_id,
        "status": "ready_for_acquisition_workflow",
        "selected_top_n": selected_top_n,
        "access_mode": status.get("access_mode", "open_access_only"),
        "input_refs": {
            "deployment_status": "literature/deployment_status.yml",
            "search_queries": status.get("search_queries_ref", "literature/search_queries.yml"),
            "confirmation_request": status.get("confirmation_request_ref", "literature/confirmation_request.yml"),
            "candidate_table": "literature/candidates.csv",
            "ranking_table": "literature/ranking.csv",
            "selected_items": "literature/selected_items.yml",
        },
        "expected_output_refs": {
            "candidate_table": "literature/candidates.csv",
            "ranking_table": "literature/ranking.csv",
            "selected_items": "literature/selected_items.yml",
            "library_manifest": "literature/library_manifest.yml",
            "cache_index": "literature/cache_index.yml",
            "status_update": "literature/acquisition_status_update.yml",
        },
        "workflow_contract": [
            "Do not assume developer-machine Zotero, browser, institution login, cache, or school authentication paths.",
            "Use user-provided access settings only; record items that require login under needs_user_login.",
            "Log sources, queries, dates, and known gaps; do not claim exhaustive web coverage.",
            "Do not download full text until selected_top_n has been confirmed and lawful access is available.",
            "Write status updates to literature/acquisition_status_update.yml, then run ea literature sync-status in the origin project.",
        ],
        "forbidden_actions": [
            "do_not_store_passwords",
            "do_not_bypass_sso_mfa_captcha_or_paywalls",
            "do_not_modify_reference_manager_database_directly",
            "do_not_write_generated_outputs_under_raw",
        ],
    }
    write_yaml(handoff_path, handoff)
    prompt = "\n".join(
        [
            "# Literature Acquisition Handoff",
            "",
            f"- handoff_id: `{handoff_id}`",
            f"- project_id: `{project_id}`",
            f"- selected_top_n: `{selected_top_n}`",
            f"- access_mode: `{handoff['access_mode']}`",
            f"- handoff_mode: `{handoff_mode}`",
            "",
            "Use EA v0.2 literature workflow references. Work only from the files listed in the handoff YAML.",
            "Keep the acquisition workflow context separate from experimental analysis work.",
            "",
            "## Required Inputs",
            "",
            *[f"- {key}: `{value}`" for key, value in handoff["input_refs"].items()],
            "",
            "## Expected Outputs",
            "",
            *[f"- {key}: `{value}`" for key, value in handoff["expected_output_refs"].items()],
            "",
            "## Sync Back",
            "",
            "After search/ranking/acquisition progress, write `literature/acquisition_status_update.yml` with the fields needed by `ea literature sync-status`, then run that command in the origin project.",
            "",
            "## Boundaries",
            "",
            *[f"- {item}" for item in handoff["workflow_contract"]],
        ]
    )
    prompt_path.write_text(prompt + "\n", encoding="utf-8")
    sync_seed = {
        "schema_version": "0.2",
        "project_id": project_id,
        "handoff_id": handoff_id,
        "last_synced_at": None,
        "status": "handoff_ready",
        "summary_for_origin_thread": (
            f"Literature acquisition handoff is ready for top {selected_top_n}. "
            "No search or full-text download has been executed by this handoff step."
        ),
    }
    write_yaml(sync_path, sync_seed)
    status.update(
        {
            "status": "acquisition_handoff_ready",
            "literature_thread_id": literature_thread_id,
            "acquisition_handoff_ref": "literature/acquisition_handoff.yml",
            "acquisition_handoff_prompt_ref": "literature/acquisition_handoff.md",
            "origin_thread_sync_ref": "literature/origin_thread_sync.yml",
            "summary_for_origin_thread": sync_seed["summary_for_origin_thread"],
        }
    )
    write_yaml(status_path, status)
    return {
        "handoff_path": str(handoff_path),
        "prompt_path": str(prompt_path),
        "sync_path": str(sync_path),
        "status_path": str(status_path),
        "handoff": handoff,
        "status": status,
    }


def _load_acquisition_candidates(root: Path, selected_top_n: int) -> tuple[str, list[dict[str, Any]]]:
    selected_path = root / "literature" / "selected_items.yml"
    selected = read_yaml(selected_path) if selected_path.exists() else {}
    selected_items = list(selected.get("items") or [])
    if selected_items:
        return "selected_items", selected_items[:selected_top_n]

    ranking_rows = _read_csv_rows(root / "literature" / "ranking.csv")
    ranked = [row for row in ranking_rows if row.get("title") or row.get("doi") or row.get("url")]
    return "ranking_table", ranked[:selected_top_n]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(_compact_dict(row), ensure_ascii=False, sort_keys=True) + "\n")


def _target_from_candidate(candidate: dict[str, Any], *, index: int, project_id: str) -> dict[str, Any]:
    candidate_id = candidate.get("candidate_id") or candidate.get("id") or f"lit-target-{index:03d}"
    return {
        "target_id": f"target-{index:03d}",
        "project_id": project_id,
        "source_candidate_id": candidate_id,
        "rank": candidate.get("rank") or candidate.get("top30_rank") or index,
        "title": candidate.get("title"),
        "doi": candidate.get("doi"),
        "url": candidate.get("url"),
        "authors": candidate.get("authors"),
        "year": candidate.get("year"),
        "venue": candidate.get("venue"),
        "notes": candidate.get("notes"),
        "tags": candidate.get("tags") or [f"project:{project_id}", "ea-literature"],
    }


def prepare_literature_acquisition_request(
    root: Path,
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    literature_root = root / "literature"
    status_path = literature_root / "deployment_status.yml"
    if not status_path.exists():
        raise FileNotFoundError(status_path)
    status = read_yaml(status_path)
    if status.get("status") not in {
        "confirmed_awaiting_acquisition",
        "ranked_candidates_ready",
        "acquisition_handoff_ready",
        "acquisition_request_ready",
    }:
        raise ValueError("Literature acquisition request requires confirmed literature selection")
    selected_top_n = status.get("selected_top_n")
    if not selected_top_n:
        raise ValueError("Literature acquisition request requires selected_top_n")

    created_at = created_at or EARecord.now_iso()
    project = _project_context(root)
    project_id = str(status.get("project_id") or project.get("project_id", "unknown-project"))
    request_id = f"lit-acq-{_timestamp_key(created_at)}"
    query_rows = []
    query_data = read_yaml(literature_root / "search_queries.yml") if (literature_root / "search_queries.yml").exists() else {}
    for query in query_data.get("queries") or []:
        query_rows.append(
            {
                "query_id": query.get("query_id"),
                "query": query.get("query"),
                "purpose": query.get("purpose"),
                "project_id": project_id,
                "access_mode": status.get("access_mode", "open_access_only"),
            }
        )

    candidate_source, candidates = _load_acquisition_candidates(root, int(selected_top_n))
    targets = [
        _target_from_candidate(candidate, index=index, project_id=project_id)
        for index, candidate in enumerate(candidates, start=1)
    ]
    request_path = literature_root / "acquisition_request.yml"
    query_manifest_path = literature_root / "zotero_codex_queries.jsonl"
    target_manifest_path = literature_root / "zotero_codex_targets.jsonl"
    batch_status_path = literature_root / "zotero_codex_batch_status.json"
    _write_jsonl(query_manifest_path, query_rows)
    _write_jsonl(target_manifest_path, targets)

    target_status = "ready_for_batch_acquisition" if targets else "awaiting_search_results"
    request = {
        "schema_version": "0.2",
        "request_id": request_id,
        "project_id": project_id,
        "created_at": created_at,
        "status": target_status,
        "selected_top_n": selected_top_n,
        "access_mode": status.get("access_mode", "open_access_only"),
        "target_source": candidate_source,
        "query_count": len(query_rows),
        "target_count": len(targets),
        "query_manifest_ref": _project_relative(root, query_manifest_path),
        "target_manifest_ref": _project_relative(root, target_manifest_path),
        "batch_status_ref": _project_relative(root, batch_status_path),
        "zotero_codex_contract": {
            "run_inside_skill": "zotero-codex-literature",
            "doctor_command": "python3 scripts/literature_doctor.py --json",
            "batch_acquire_command": (
                "python3 scripts/batch_acquire.py --targets "
                f"{_project_relative(root, target_manifest_path)} --batch-status "
                f"{_project_relative(root, batch_status_path)} --resume --json"
            ),
            "render_status_command": (
                "python3 scripts/render_batch_status.py --batch-status "
                f"{_project_relative(root, batch_status_path)} --markdown "
                "literature/zotero_codex_batch_status.md --json"
            ),
            "sidecar_command": (
                "python3 scripts/write_project_sidecars.py --status "
                f"{_project_relative(root, batch_status_path)} --json"
            ),
            "import_back_command": (
                "ea literature import-acquisition /path/to/ea-project "
                "--manifest literature/acquisition_manifest.yml"
            ),
        },
        "boundaries": [
            "This request does not execute live search, Zotero calls, browser automation, DOI resolution, or PDF downloads.",
            "Use only user-supplied Zotero, browser, cache, proxy, VPN, or institution-access settings.",
            "Pause for SSO, MFA, CAPTCHA, institution selection, publisher access control, or non-autofilled login.",
            "Do not store passwords, bypass access controls, modify the reference-manager database directly, or claim exhaustive web coverage.",
        ],
        "next_action": (
            "Run the Zotero-Codex batch acquisition command in a dedicated literature workflow."
            if targets
            else "Run literature search/ranking in a dedicated workflow, then populate selected_items.yml or ranking.csv and regenerate this request."
        ),
    }
    write_yaml(request_path, request)
    status.update(
        {
            "status": "acquisition_request_ready",
            "acquisition_request_ref": _project_relative(root, request_path),
            "zotero_codex_queries_ref": _project_relative(root, query_manifest_path),
            "zotero_codex_targets_ref": _project_relative(root, target_manifest_path),
            "acquisition_request_status": target_status,
            "summary_for_origin_thread": (
                f"Literature acquisition request prepared with {len(targets)} target(s). "
                "No live search or full-text acquisition has been executed by EA."
            ),
        }
    )
    write_yaml(status_path, status)
    return {
        "request_path": str(request_path),
        "query_manifest_path": str(query_manifest_path),
        "target_manifest_path": str(target_manifest_path),
        "status_path": str(status_path),
        "request": request,
        "status": status,
    }


def _optional_path_ref(root: Path, path: Path | None) -> str | None:
    return _project_relative(root, path) if path else None


def _bridge_required_inputs(
    *,
    access_mode: str,
    zotero_config_ref: str | None,
    allow_default_config: bool,
    project_collection: str | None,
    browser_assist: bool,
    browser_name: str | None,
    browser_profile_ref: str | None,
    institution_access: str | None,
) -> list[dict[str, str]]:
    inputs: list[dict[str, str]] = []
    if not zotero_config_ref and not allow_default_config:
        inputs.append(
            {
                "field": "zotero_codex_config",
                "reason": "Confirm a Zotero-Codex config path or explicitly allow the user's default config.",
            }
        )
    if not project_collection:
        inputs.append(
            {
                "field": "project_collection",
                "reason": "Confirm the Zotero collection or project tag that should receive acquired items.",
            }
        )
    if access_mode == "user_authenticated" and not institution_access:
        inputs.append(
            {
                "field": "institution_access",
                "reason": "Describe the user-managed institution/proxy/VPN access route before gated acquisition.",
            }
        )
    if access_mode == "user_authenticated" and not browser_assist:
        inputs.append(
            {
                "field": "browser_assist",
                "reason": "Confirm whether a visible browser-assisted authorization workflow is allowed.",
            }
        )
    if browser_assist and not browser_name:
        inputs.append(
            {
                "field": "browser_name",
                "reason": "Confirm which user-managed browser should be used for visible authorization windows.",
            }
        )
    if browser_assist and not browser_profile_ref:
        inputs.append(
            {
                "field": "browser_profile",
                "reason": "Confirm the user-managed browser profile path or profile name; do not assume a developer-machine profile.",
            }
        )
    return inputs


def prepare_zotero_codex_acquisition_bridge(
    root: Path,
    *,
    zotero_config: Path | None = None,
    allow_default_config: bool = False,
    cache_root: Path | None = None,
    project_collection: str | None = None,
    browser_assist: bool = False,
    browser_name: str | None = None,
    browser_profile: Path | None = None,
    institution_access: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    literature_root = root / "literature"
    request_path = literature_root / "acquisition_request.yml"
    status_path = literature_root / "deployment_status.yml"
    if not request_path.exists():
        raise FileNotFoundError(request_path)
    if not status_path.exists():
        raise FileNotFoundError(status_path)

    request = read_yaml(request_path)
    status = read_yaml(status_path)
    created_at = created_at or EARecord.now_iso()
    project = _project_context(root)
    project_id = str(request.get("project_id") or status.get("project_id") or project.get("project_id", "unknown-project"))
    bridge_id = f"lit-zotero-bridge-{_timestamp_key(created_at)}"
    target_count = _safe_int(request.get("target_count"), 0)
    access_mode = str(request.get("access_mode") or status.get("access_mode") or "open_access_only")
    zotero_config_ref = _optional_path_ref(root, zotero_config)
    cache_root_ref = _optional_path_ref(root, cache_root)
    browser_profile_ref = _optional_path_ref(root, browser_profile)
    target_manifest_ref = str(request.get("target_manifest_ref") or "literature/zotero_codex_targets.jsonl")
    batch_status_ref = str(request.get("batch_status_ref") or "literature/zotero_codex_batch_status.json")
    batch_status_md_ref = "literature/zotero_codex_batch_status.md"
    acquisition_manifest_ref = "literature/acquisition_manifest.yml"
    status_update_ref = "literature/acquisition_status_update.yml"

    required_inputs = _bridge_required_inputs(
        access_mode=access_mode,
        zotero_config_ref=zotero_config_ref,
        allow_default_config=allow_default_config,
        project_collection=project_collection,
        browser_assist=browser_assist,
        browser_name=browser_name,
        browser_profile_ref=browser_profile_ref,
        institution_access=institution_access,
    )
    bridge_status = (
        "awaiting_targets"
        if target_count <= 0
        else "needs_user_settings"
        if required_inputs
        else "ready_for_zotero_codex_batch"
    )

    config_option = f" --config {zotero_config_ref}" if zotero_config_ref else ""
    commands = {
        "doctor": f"python3 scripts/literature_doctor.py{config_option} --json",
        "batch_acquire": (
            "python3 scripts/batch_acquire.py"
            f"{config_option} --targets {target_manifest_ref} --batch-status {batch_status_ref} --resume --json"
        ),
        "render_status": (
            "python3 scripts/render_batch_status.py"
            f" --batch-status {batch_status_ref} --markdown {batch_status_md_ref} --json"
        ),
        "write_project_sidecars": f"python3 scripts/write_project_sidecars.py --status {batch_status_ref} --json",
        "verify_project_sidecars": (
            "python3 scripts/verify_project_sidecars.py"
            f" --status {batch_status_ref} --expect-count {target_count} --compact-json"
        ),
        "sync_status_back_to_ea": f"ea literature sync-status /path/to/ea-project --update {status_update_ref}",
        "import_acquisition_manifest": (
            f"ea literature import-acquisition /path/to/ea-project --manifest {acquisition_manifest_ref}"
        ),
    }
    settings = {
        "zotero_codex_config_ref": zotero_config_ref,
        "allow_default_zotero_codex_config": allow_default_config,
        "cache_root_ref": cache_root_ref,
        "project_collection": project_collection,
        "browser_assist_enabled": browser_assist,
        "browser_name": browser_name,
        "browser_profile_ref": browser_profile_ref,
        "institution_access": institution_access,
    }
    bridge_path = literature_root / "zotero_codex_bridge.yml"
    runbook_path = literature_root / "zotero_codex_bridge.md"
    settings_path = literature_root / "zotero_codex_settings_request.yml"
    bridge = {
        "schema_version": "0.2",
        "bridge_id": bridge_id,
        "project_id": project_id,
        "created_at": created_at,
        "status": bridge_status,
        "acquisition_request_ref": "literature/acquisition_request.yml",
        "target_manifest_ref": target_manifest_ref,
        "target_count": target_count,
        "access_mode": access_mode,
        "settings_request_ref": "literature/zotero_codex_settings_request.yml",
        "runbook_ref": "literature/zotero_codex_bridge.md",
        "settings": settings,
        "required_user_inputs": required_inputs,
        "commands": commands,
        "expected_outputs": {
            "batch_status": batch_status_ref,
            "batch_status_markdown": batch_status_md_ref,
            "project_sidecars": "Zotero-Codex cache sidecars generated by write_project_sidecars.py",
            "acquisition_manifest": acquisition_manifest_ref,
            "status_update": status_update_ref,
        },
        "boundaries": [
            "This bridge only prepares a Zotero-Codex runbook; it does not run Zotero, browser automation, DOI resolution, PDF download, or cache extraction.",
            "Use only user-supplied or user-confirmed Zotero, browser, cache, proxy, VPN, and institution settings.",
            "Pause for SSO, MFA, CAPTCHA, institution selection, publisher access control, or non-autofilled login.",
            "Never store passwords, bypass access controls, modify the reference-manager database file directly, or assume developer-machine defaults.",
        ],
    }
    settings_request = {
        "schema_version": "0.2",
        "project_id": project_id,
        "created_at": created_at,
        "status": "needs_user_input" if required_inputs else "settings_confirmed",
        "required_user_inputs": required_inputs,
        "provided_settings": settings,
        "notes": [
            "The dedicated literature workflow may use Zotero-Codex defaults only if the user confirms they are valid for this project.",
            "Institution or publisher authorization must happen in a visible user-managed browser session.",
            "Do not ask the user to paste institution credentials into chat.",
        ],
    }
    runbook_lines = [
        "# Zotero-Codex Acquisition Bridge",
        "",
        f"- bridge_id: `{bridge_id}`",
        f"- project_id: `{project_id}`",
        f"- status: `{bridge_status}`",
        f"- target_count: `{target_count}`",
        f"- access_mode: `{access_mode}`",
        "",
        "## Required User Inputs",
        "",
    ]
    if required_inputs:
        runbook_lines.extend(f"- `{item['field']}`: {item['reason']}" for item in required_inputs)
    else:
        runbook_lines.append("- All bridge settings required before batch acquisition are confirmed.")
    runbook_lines.extend(
        [
            "",
            "## Commands",
            "",
            *[f"- `{name}`: `{command}`" for name, command in commands.items()],
            "",
            "## Boundaries",
            "",
            *[f"- {item}" for item in bridge["boundaries"]],
        ]
    )

    write_yaml(bridge_path, bridge)
    write_yaml(settings_path, settings_request)
    runbook_path.write_text("\n".join(runbook_lines) + "\n", encoding="utf-8")
    status.update(
        {
            "status": "zotero_codex_bridge_ready" if bridge_status == "ready_for_zotero_codex_batch" else bridge_status,
            "zotero_codex_bridge_ref": _project_relative(root, bridge_path),
            "zotero_codex_bridge_runbook_ref": _project_relative(root, runbook_path),
            "zotero_codex_settings_request_ref": _project_relative(root, settings_path),
            "zotero_codex_bridge_status": bridge_status,
            "summary_for_origin_thread": (
                f"Zotero-Codex bridge prepared for {target_count} target(s); status is {bridge_status}. "
                "EA did not run Zotero, browser automation, DOI resolution, PDF download, or cache extraction."
            ),
        }
    )
    write_yaml(status_path, status)
    return {
        "bridge_path": str(bridge_path),
        "runbook_path": str(runbook_path),
        "settings_request_path": str(settings_path),
        "status_path": str(status_path),
        "bridge": bridge,
        "settings_request": settings_request,
        "status": status,
    }


def _quote_cli_value(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


SENSITIVE_ACCESS_DETAIL_RE = re.compile(r"\b(pass(word)?|pwd|token|cookie|session|otp|samlresponse)\b\s*[:=]", re.IGNORECASE)


def _redact_sensitive_access_text(value: str | None) -> tuple[str | None, bool]:
    if not value:
        return value, False
    if SENSITIVE_ACCESS_DETAIL_RE.search(value):
        return "[redacted-sensitive-access-detail]", True
    return value, False


def _redact_sensitive_access_notes(notes: list[str] | None) -> tuple[list[str], bool]:
    redacted = []
    any_redacted = False
    for item in notes or []:
        value, was_redacted = _redact_sensitive_access_text(item)
        if value:
            redacted.append(value)
        any_redacted = any_redacted or was_redacted
    return redacted, any_redacted


def _institution_access_required_inputs(
    *,
    access_mode: str,
    institution_name: str | None,
    access_method: str | None,
    access_url: str | None,
    access_instructions: str | None,
    browser_name: str | None,
    browser_profile_ref: str | None,
    authorization_status: str | None,
) -> list[dict[str, str]]:
    if access_mode != "user_authenticated":
        return []
    inputs: list[dict[str, str]] = []
    if not institution_name:
        inputs.append({"field": "institution_name", "reason": "Name the institution or library access provider the user will use."})
    if not access_method:
        inputs.append(
            {
                "field": "access_method",
                "reason": "Confirm whether access uses VPN, library proxy, campus network, publisher SSO, or another user-managed route.",
            }
        )
    if not access_url and not access_instructions:
        inputs.append(
            {
                "field": "access_url_or_instructions",
                "reason": "Record the user-supplied login/start URL or manual access instructions without credentials.",
            }
        )
    if not browser_name:
        inputs.append({"field": "browser_name", "reason": "Confirm the user-managed browser for visible authorization."})
    if not browser_profile_ref:
        inputs.append(
            {
                "field": "browser_profile",
                "reason": "Confirm the user-managed browser profile path or profile name; do not assume a developer-machine profile.",
            }
        )
    if not authorization_status:
        inputs.append(
            {
                "field": "authorization_status",
                "reason": "Record whether manual authorization is not checked, needs user login, ready, or blocked.",
            }
        )
    return inputs


def prepare_institution_access_guidance(
    root: Path,
    *,
    institution_name: str | None = None,
    access_method: str | None = None,
    access_url: str | None = None,
    access_instructions: str | None = None,
    browser_name: str | None = None,
    browser_profile: Path | None = None,
    zotero_config: Path | None = None,
    cache_root: Path | None = None,
    project_collection: str | None = None,
    authorization_status: str | None = None,
    note: list[str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    literature_root = root / "literature"
    status_path = literature_root / "deployment_status.yml"
    if not status_path.exists():
        raise FileNotFoundError(status_path)
    created_at = created_at or EARecord.now_iso()
    project = _project_context(root)
    status = read_yaml(status_path)
    project_id = str(status.get("project_id") or project.get("project_id", "unknown-project"))
    access_mode = str(status.get("access_mode") or "open_access_only")
    access_url, access_url_redacted = _redact_sensitive_access_text(access_url)
    access_instructions, access_instructions_redacted = _redact_sensitive_access_text(access_instructions)
    notes, notes_redacted = _redact_sensitive_access_notes(note)
    browser_profile_ref = _optional_path_ref(root, browser_profile)
    zotero_config_ref = _optional_path_ref(root, zotero_config)
    cache_root_ref = _optional_path_ref(root, cache_root)
    required_inputs = _institution_access_required_inputs(
        access_mode=access_mode,
        institution_name=institution_name,
        access_method=access_method,
        access_url=access_url,
        access_instructions=access_instructions,
        browser_name=browser_name,
        browser_profile_ref=browser_profile_ref,
        authorization_status=authorization_status,
    )
    if access_mode != "user_authenticated":
        guidance_status = "not_required_for_current_access_mode"
    else:
        guidance_status = "needs_user_settings" if required_inputs else "ready_for_user_managed_authorization"
    guide_id = f"lit-institution-access-{_timestamp_key(created_at)}"
    settings = _compact_dict(
        {
            "institution_name": institution_name,
            "access_method": access_method,
            "access_url": access_url,
            "access_instructions": access_instructions,
            "browser_name": browser_name,
            "browser_profile_ref": browser_profile_ref,
            "zotero_codex_config_ref": zotero_config_ref,
            "cache_root_ref": cache_root_ref,
            "project_collection": project_collection,
            "authorization_status": authorization_status,
            "notes": notes,
            "redaction_notes": ["Sensitive access details were redacted before writing this project artifact."]
            if access_url_redacted or access_instructions_redacted or notes_redacted
            else [],
        }
    )
    institution_access_summary = "; ".join(
        item
        for item in [institution_name, access_method, access_url, access_instructions]
        if item
    )
    bridge_parts = ["ea literature zotero-bridge /path/to/ea-project"]
    if zotero_config_ref:
        bridge_parts.extend(["--zotero-config", zotero_config_ref])
    if cache_root_ref:
        bridge_parts.extend(["--cache-root", cache_root_ref])
    if project_collection:
        bridge_parts.extend(["--project-collection", _quote_cli_value(project_collection)])
    if browser_name or browser_profile_ref:
        bridge_parts.append("--enable-browser-assist")
    if browser_name:
        bridge_parts.extend(["--browser-name", _quote_cli_value(browser_name)])
    if browser_profile_ref:
        bridge_parts.extend(["--browser-profile", browser_profile_ref])
    if institution_access_summary:
        bridge_parts.extend(["--institution-access", _quote_cli_value(institution_access_summary)])

    safe_commands = {
        "prepare_zotero_bridge": " ".join(bridge_parts),
        "import_zotero_status": (
            "ea literature import-zotero-status /path/to/ea-project "
            "--batch-status literature/zotero_codex_batch_status.json "
            "--sidecar-verification literature/zotero_codex_sidecars_verify.json"
        ),
        "reconcile_acquisition": "ea literature reconcile-acquisition /path/to/ea-project",
    }
    user_actions = [
        "Confirm that the institution route is lawful for this project and belongs to the user or organization.",
        "Open the user-managed browser/profile outside EA and complete SSO, MFA, CAPTCHA, proxy, or publisher authorization manually.",
        "Do not paste passwords, one-time codes, cookies, or session tokens into chat or project files.",
        "After user-managed authorization, run the dedicated Zotero-Codex acquisition workflow and import status back into EA.",
    ]
    boundaries = [
        "This guidance records user-supplied institution-access settings only.",
        "EA does not store passwords, one-time codes, cookies, session tokens, or school credentials.",
        "EA does not open browsers, operate Zotero, run Zotero-Codex scripts, probe institution URLs, resolve DOI pages, download PDFs, or parse full text.",
        "EA must not bypass access controls or assume developer-machine Zotero, browser, profile, cache, or institution settings.",
    ]
    guidance_path = literature_root / "institution_access_guidance.yml"
    runbook_path = literature_root / "institution_access_guidance.md"
    guidance = {
        "schema_version": "0.2",
        "guide_id": guide_id,
        "project_id": project_id,
        "created_at": created_at,
        "status": guidance_status,
        "access_mode": access_mode,
        "settings": settings,
        "required_user_inputs": required_inputs,
        "questions_for_user": [{"field": item["field"], "question": item["reason"]} for item in required_inputs],
        "user_actions": user_actions,
        "safe_commands": safe_commands,
        "boundaries": boundaries,
        "next_action": (
            "Institution access is not required for the current access mode; keep this guide only if future gated acquisition is planned."
            if access_mode != "user_authenticated"
            else "Ask the user for missing settings before preparing the Zotero-Codex bridge."
            if required_inputs
            else "Use the user-managed browser authorization route, then prepare or rerun the Zotero-Codex bridge."
        ),
    }
    runbook_lines = [
        "# Institution Access Guidance",
        "",
        f"- guide_id: `{guide_id}`",
        f"- project_id: `{project_id}`",
        f"- status: `{guidance_status}`",
        f"- access_mode: `{access_mode}`",
        "",
        "## Required User Inputs",
        "",
    ]
    if required_inputs:
        runbook_lines.extend(f"- `{item['field']}`: {item['reason']}" for item in required_inputs)
    else:
        runbook_lines.append("- No missing institution-access settings for the current access mode.")
    runbook_lines.extend(
        [
            "",
            "## User Actions",
            "",
            *[f"- {item}" for item in user_actions],
            "",
            "## Safe Commands",
            "",
            *[f"- `{name}`: `{command}`" for name, command in safe_commands.items()],
            "",
            "## Boundaries",
            "",
            *[f"- {item}" for item in boundaries],
        ]
    )
    write_yaml(guidance_path, guidance)
    runbook_path.write_text("\n".join(runbook_lines) + "\n", encoding="utf-8")
    status.update(
        {
            "institution_access_guidance_ref": _project_relative(root, guidance_path),
            "institution_access_guidance_runbook_ref": _project_relative(root, runbook_path),
            "institution_access_guidance_status": guidance_status,
            "summary_for_origin_thread": (
                f"Institution access guidance prepared with status {guidance_status}. "
                "EA did not open browsers, operate Zotero, store credentials, or access publisher content."
            ),
        }
    )
    write_yaml(status_path, status)
    return {
        "guidance_path": str(guidance_path),
        "runbook_path": str(runbook_path),
        "status_path": str(status_path),
        "guidance": guidance,
        "status": status,
    }


ZOTERO_CODEX_SUCCESS_STATUSES = {
    "cached",
    "reused-cache",
    "reused_cache",
    "cache-ok",
    "cache_ok",
    "pdf-ok",
    "pdf_ok",
    "acquired",
    "downloaded",
    "completed",
    "complete",
    "success",
    "ok",
    "imported",
    "ingested",
}
ZOTERO_CODEX_CACHE_STATUSES = {"cached", "reused-cache", "reused_cache", "cache-ok", "cache_ok"}
ZOTERO_CODEX_LOGIN_STATUSES = {
    "needs-login",
    "needs_login",
    "needs-browser-authorization",
    "needs_browser_authorization",
    "login-required",
    "login_required",
    "auth-required",
    "auth_required",
    "authorization-required",
    "authorization_required",
}
ZOTERO_CODEX_BLOCKED_STATUSES = {
    "failed",
    "failure",
    "failed-nonpdf",
    "failed_nonpdf",
    "failed-ambiguous",
    "failed_ambiguous",
    "error",
    "blocked",
    "no-access",
    "no_access",
}


def _resolve_project_path(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _zotero_codex_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("items", "targets", "results", "records", "entries"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            return [item for item in value.values() if isinstance(item, dict)]
    return []


def _zotero_codex_item_status(item: dict[str, Any]) -> str:
    return _as_text(
        item.get("status")
        or item.get("acquisition_status")
        or item.get("result_status")
        or item.get("outcome")
        or item.get("state")
    ).strip().lower()


def _zotero_codex_item_ref(item: dict[str, Any]) -> dict[str, Any]:
    return _compact_dict(
        {
            "target_id": item.get("target_id") or item.get("id"),
            "rank": item.get("rank") or item.get("top30_rank"),
            "title": item.get("title"),
            "doi": item.get("doi"),
            "url": item.get("url"),
            "status": item.get("status") or item.get("acquisition_status") or item.get("outcome"),
            "reason": item.get("reason") or item.get("error") or item.get("message"),
            "zotero_item_key": item.get("zotero_item_key") or item.get("item_key"),
            "cache_path": item.get("cache_path") or item.get("cache_dir"),
        }
    )


def _sidecar_verification_summary(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {}
    missing = payload.get("missing") or payload.get("missing_sidecars") or []
    invalid = payload.get("invalid") or payload.get("invalid_sidecars") or []
    errors = payload.get("errors") or []
    return _compact_dict(
        {
            "status": payload.get("status"),
            "verified_count": payload.get("verified_count") or payload.get("checked_count") or payload.get("count"),
            "missing_count": len(missing) if isinstance(missing, list) else payload.get("missing_count"),
            "invalid_count": len(invalid) if isinstance(invalid, list) else payload.get("invalid_count"),
            "error_count": len(errors) if isinstance(errors, list) else payload.get("error_count"),
        }
    )


def _status_from_zotero_counts(total: int, success_count: int, login_count: int, blocked_count: int) -> str:
    if total == 0:
        return "acquisition_status_imported_no_targets"
    if blocked_count:
        return "acquisition_partial_with_blockers" if success_count or login_count else "acquisition_blocked"
    if login_count:
        return "acquisition_partial_needs_user_login" if success_count else "acquisition_needs_user_login"
    if success_count >= total:
        return "acquisition_complete"
    if success_count:
        return "acquisition_in_progress"
    return "acquisition_status_imported"


def import_zotero_codex_batch_status(
    root: Path,
    *,
    batch_status_path: Path | None = None,
    sidecar_verification_path: Path | None = None,
    status_markdown_path: Path | None = None,
    imported_at: str | None = None,
    sync: bool = True,
) -> dict[str, Any]:
    literature_root = root / "literature"
    status_path = literature_root / "deployment_status.yml"
    if not status_path.exists():
        raise FileNotFoundError(status_path)
    imported_at = imported_at or EARecord.now_iso()
    batch_status_path = batch_status_path or Path("literature/zotero_codex_batch_status.json")
    resolved_batch_status = _resolve_project_path(root, batch_status_path)
    batch_payload = _load_manifest(resolved_batch_status)
    if not isinstance(batch_payload, dict):
        raise ValueError("Zotero-Codex batch status must be a JSON/YAML object")
    items = _zotero_codex_items(batch_payload)
    project_status = read_yaml(status_path)
    project_id = str(project_status.get("project_id") or _project_context(root).get("project_id", "unknown-project"))

    success_items: list[dict[str, Any]] = []
    login_items: list[dict[str, Any]] = []
    blocked_items: list[dict[str, Any]] = []
    downloaded_fulltext = 0
    cached_fulltext = 0
    for item in items:
        status_key = _zotero_codex_item_status(item)
        compact = _zotero_codex_item_ref(item)
        has_pdf = any(item.get(key) for key in ("local_path", "pdf_path", "attachment_path", "pdf"))
        has_cache = any(item.get(key) for key in ("cache_path", "cache_dir", "cached_path"))
        if status_key in ZOTERO_CODEX_LOGIN_STATUSES:
            login_items.append(compact)
            continue
        if status_key in ZOTERO_CODEX_BLOCKED_STATUSES:
            blocked_items.append(compact)
            continue
        if status_key in ZOTERO_CODEX_SUCCESS_STATUSES or has_pdf or has_cache or item.get("zotero_item_key"):
            success_items.append(compact)
        if status_key in ZOTERO_CODEX_SUCCESS_STATUSES or has_pdf or has_cache:
            downloaded_fulltext += 1
        if status_key in ZOTERO_CODEX_CACHE_STATUSES or has_cache:
            cached_fulltext += 1

    sidecar_payload: dict[str, Any] = {}
    sidecar_ref = None
    if sidecar_verification_path:
        resolved_sidecar = _resolve_project_path(root, sidecar_verification_path)
        sidecar_payload = _load_manifest(resolved_sidecar)
        sidecar_ref = _project_relative(root, resolved_sidecar)
        sidecar_status = _as_text(sidecar_payload.get("status")).lower()
        if sidecar_status and sidecar_status not in {"pass", "ok", "success"}:
            blocked_items.append(
                _compact_dict(
                    {
                        "title": "Zotero-Codex sidecar verification",
                        "status": sidecar_payload.get("status"),
                        "reason": "sidecar_verification_failed",
                        "source_ref": sidecar_ref,
                    }
                )
            )

    status_markdown_ref = None
    if status_markdown_path:
        resolved_markdown = _resolve_project_path(root, status_markdown_path)
        status_markdown_ref = _project_relative(root, resolved_markdown)

    total = _safe_int(batch_payload.get("target_count") or batch_payload.get("item_count"), len(items))
    status_value = _status_from_zotero_counts(total, len(success_items), len(login_items), len(blocked_items))
    summary = (
        f"Zotero-Codex status import saw {total} target(s): "
        f"{downloaded_fulltext} downloaded/reused PDF item(s), {cached_fulltext} cached full-text item(s), "
        f"{len(login_items)} item(s) needing user login, and {len(blocked_items)} blocked item(s). "
        "EA imported status artifacts only; it did not run Zotero, browser automation, DOI resolution, PDF download, or cache extraction."
    )
    status_import_path = literature_root / "zotero_codex_status_import.yml"
    update_path = literature_root / "acquisition_status_update.yml"
    status_import = {
        "schema_version": "0.2",
        "project_id": project_id,
        "imported_at": imported_at,
        "status": status_value,
        "batch_status_ref": _project_relative(root, resolved_batch_status),
        "status_markdown_ref": status_markdown_ref,
        "sidecar_verification_ref": sidecar_ref,
        "target_count": total,
        "success_count": len(success_items),
        "downloaded_fulltext": downloaded_fulltext,
        "cached_fulltext": cached_fulltext,
        "needs_user_login_count": len(login_items),
        "blocked_count": len(blocked_items),
        "sidecar_verification": _sidecar_verification_summary(sidecar_payload),
        "items": {
            "successful": success_items,
            "needs_user_login": login_items,
            "blocked": blocked_items,
        },
        "boundaries": [
            "This import reads Zotero-Codex status artifacts only.",
            "No Zotero scripts, browser automation, DOI resolution, PDF download, credential handling, or full-text parsing is executed by EA.",
        ],
    }
    update = {
        "schema_version": "0.2",
        "status": status_value,
        "candidate_count": batch_payload.get("candidate_count") or project_status.get("candidate_count") or total,
        "deduped_count": batch_payload.get("deduped_count") or project_status.get("deduped_count") or total,
        "downloaded_fulltext": downloaded_fulltext,
        "cached_fulltext": cached_fulltext,
        "needs_user_login": login_items,
        "blocked_items": blocked_items,
        "summary_for_origin_thread": summary,
        "zotero_codex_batch_status_ref": _project_relative(root, resolved_batch_status),
        "zotero_codex_status_markdown_ref": status_markdown_ref,
        "zotero_codex_sidecar_verification_ref": sidecar_ref,
        "zotero_codex_status_import_ref": "literature/zotero_codex_status_import.yml",
        "sidecar_verification": status_import["sidecar_verification"],
    }
    write_yaml(status_import_path, status_import)
    write_yaml(update_path, update)
    sync_result = (
        sync_literature_acquisition_status(root, update_path=Path("literature/acquisition_status_update.yml"), synced_at=imported_at)
        if sync
        else None
    )
    return {
        "batch_status_path": str(resolved_batch_status),
        "status_import_path": str(status_import_path),
        "status_update_path": str(update_path),
        "status_import": status_import,
        "status_update": update,
        "sync": sync_result,
    }


def _literature_identifier_keys(item: dict[str, Any]) -> set[str]:
    keys = set()
    doi = _as_text(item.get("doi")).strip().lower()
    if doi:
        doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
        keys.add(f"doi:{doi.rstrip('.')}")
    title = _normalized_title(item.get("title"))
    if title:
        keys.add(f"title:{title}")
    reference_id = _as_text(item.get("reference_id")).strip()
    if reference_id:
        keys.add(f"reference:{reference_id}")
    zotero_key = _as_text(item.get("zotero_item_key") or item.get("item_key")).strip()
    if zotero_key:
        keys.add(f"zotero:{zotero_key}")
    cache_path = _as_text(item.get("cache_path") or item.get("cache_dir")).strip()
    if cache_path:
        keys.add(f"cache:{cache_path}")
    return keys


def _literature_items_by_key(items: list[dict[str, Any]]) -> set[str]:
    keys = set()
    for item in items:
        keys.update(_literature_identifier_keys(item))
    return keys


def _status_import_items(status_import: dict[str, Any]) -> list[dict[str, Any]]:
    grouped = status_import.get("items")
    if isinstance(grouped, dict):
        items = []
        for value in grouped.values():
            if isinstance(value, list):
                items.extend(item for item in value if isinstance(item, dict))
        return items
    return []


def _reconciliation_finding(
    findings: list[dict[str, Any]],
    *,
    severity: str,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    findings.append(_compact_dict({"severity": severity, "code": code, "message": message, "details": details or {}}))


def _reconciliation_repair_suggestion(finding: dict[str, Any]) -> dict[str, Any]:
    code = _as_text(finding.get("code"))
    details = finding.get("details") if isinstance(finding.get("details"), dict) else {}
    base_commands = ["ea literature reconcile-acquisition /path/to/ea-project"]
    suggestions: dict[str, dict[str, Any]] = {
        "missing_acquisition_manifest": {
            "title": "Decide whether acquisition has produced a manifest.",
            "recommended_next_step": (
                "If a dedicated literature workflow has produced an acquisition manifest, import it. "
                "If not, continue ranking and acquisition-request preparation first."
            ),
            "command_hints": [
                "ea literature acquisition-request /path/to/ea-project",
                "ea literature import-acquisition /path/to/ea-project --manifest literature/acquisition_manifest.yml",
                *base_commands,
            ],
            "requires_user_confirmation": True,
            "question_for_user": "Has the dedicated literature workflow already produced literature/acquisition_manifest.yml for this project?",
        },
        "missing_zotero_codex_status_import": {
            "title": "Import the latest dedicated-workflow status before reconciling acquisition progress.",
            "recommended_next_step": "Run the status import if Zotero-Codex batch status artifacts exist; otherwise keep this as a warning until acquisition starts.",
            "command_hints": [
                "ea literature import-zotero-status /path/to/ea-project --batch-status literature/zotero_codex_batch_status.json",
                *base_commands,
            ],
            "requires_user_confirmation": False,
        },
        "missing_library_manifest": {
            "title": "Create or refresh the EA literature library manifest.",
            "recommended_next_step": "Import an acquisition manifest that contains the project literature items, then rerun reconciliation.",
            "command_hints": [
                "ea literature import-acquisition /path/to/ea-project --manifest literature/acquisition_manifest.yml",
                *base_commands,
            ],
            "requires_user_confirmation": True,
            "question_for_user": "Which acquisition manifest should EA treat as authoritative for the project library?",
        },
        "missing_cache_index": {
            "title": "Refresh cache tracking from the latest acquisition import.",
            "recommended_next_step": "Import the latest acquisition manifest or status artifacts so EA can rebuild cache-related records, then rerun reconciliation.",
            "command_hints": [
                "ea literature import-acquisition /path/to/ea-project --manifest literature/acquisition_manifest.yml",
                "ea literature import-zotero-status /path/to/ea-project --batch-status literature/zotero_codex_batch_status.json",
                *base_commands,
            ],
            "requires_user_confirmation": False,
        },
        "missing_reference_index": {
            "title": "Register project references before relying on report citations.",
            "recommended_next_step": "Import references from the acquisition manifest or a user-exported BibTeX file, then rerun reconciliation.",
            "command_hints": [
                "ea literature import-acquisition /path/to/ea-project --manifest literature/acquisition_manifest.yml",
                "ea references import-bibtex /path/to/ea-project /path/to/user-exported-references.bib",
                *base_commands,
            ],
            "requires_user_confirmation": True,
            "question_for_user": "Can you provide an acquisition manifest or BibTeX export containing the missing reference metadata?",
        },
        "missing_reconciliation_sources": {
            "title": "Create at least one acquisition source artifact.",
            "recommended_next_step": "Run the literature planning/ranking/acquisition-request path or import existing dedicated-workflow results before reconciliation can prove anything useful.",
            "command_hints": [
                "ea literature plan /path/to/ea-project",
                "ea literature rank-candidates /path/to/ea-project --candidates literature/candidate_results.yml",
                "ea literature acquisition-request /path/to/ea-project",
                "ea literature import-acquisition /path/to/ea-project --manifest literature/acquisition_manifest.yml",
            ],
            "requires_user_confirmation": True,
            "question_for_user": "Do you want to start literature acquisition setup, or do you already have a manifest/status artifact to import?",
        },
        "library_item_count_mismatch": {
            "title": "Regenerate or manually inspect library_manifest.yml item_count.",
            "recommended_next_step": "Treat the item list as evidence and refresh the manifest from the authoritative acquisition import, or manually fix the declared count after review.",
            "command_hints": [
                "ea literature import-acquisition /path/to/ea-project --manifest literature/acquisition_manifest.yml",
                *base_commands,
            ],
            "file_refs": ["literature/library_manifest.yml"],
            "requires_user_confirmation": False,
        },
        "cache_count_mismatch": {
            "title": "Regenerate or inspect cache_index.yml cached_count.",
            "recommended_next_step": "Refresh cache records from the authoritative acquisition import/status artifacts or manually correct the count after review.",
            "command_hints": [
                "ea literature import-acquisition /path/to/ea-project --manifest literature/acquisition_manifest.yml",
                "ea literature import-zotero-status /path/to/ea-project --batch-status literature/zotero_codex_batch_status.json",
                *base_commands,
            ],
            "file_refs": ["literature/cache_index.yml"],
            "requires_user_confirmation": False,
        },
        "missing_reference_record": {
            "title": "Register the missing reference metadata.",
            "recommended_next_step": "Import a BibTeX export or an acquisition manifest containing the referenced item, then rerun reconciliation.",
            "command_hints": [
                "ea references import-bibtex /path/to/ea-project /path/to/user-exported-references.bib",
                "ea literature import-acquisition /path/to/ea-project --manifest literature/acquisition_manifest.yml",
                *base_commands,
            ],
            "file_refs": ["literature/references/index.yml"],
            "requires_user_confirmation": True,
            "question_for_user": f"Can you provide metadata for missing reference_id {details.get('reference_id', '<unknown>')}?",
        },
        "manifest_item_missing_from_outputs": {
            "title": "Import or match the acquisition manifest item.",
            "recommended_next_step": "Import the acquisition manifest into EA, or verify that DOI/title/Zotero/cache identifiers match the status and library records.",
            "command_hints": [
                "ea literature import-acquisition /path/to/ea-project --manifest literature/acquisition_manifest.yml",
                "ea literature import-zotero-status /path/to/ea-project --batch-status literature/zotero_codex_batch_status.json",
                *base_commands,
            ],
            "file_refs": ["literature/acquisition_manifest.yml", "literature/library_manifest.yml", "literature/zotero_codex_status_import.yml"],
            "requires_user_confirmation": False,
        },
        "cache_item_missing_from_library_or_status": {
            "title": "Decide whether the cache item belongs to this project.",
            "recommended_next_step": "If the cache item is valid for the project, import an acquisition manifest/status record that names it; if it is stale, remove or archive it only after user confirmation.",
            "command_hints": [
                "ea literature import-acquisition /path/to/ea-project --manifest literature/acquisition_manifest.yml",
                "ea literature import-zotero-status /path/to/ea-project --batch-status literature/zotero_codex_batch_status.json",
                *base_commands,
            ],
            "file_refs": ["literature/cache_index.yml"],
            "requires_user_confirmation": True,
            "question_for_user": f"Should cache item {details.get('cache_path', '<unknown cache path>')} remain part of this EA project?",
        },
        "deployment_downloaded_fulltext_mismatch": {
            "title": "Resync deployment_status.yml from the latest status import.",
            "recommended_next_step": "Import the latest Zotero-Codex batch status or sync the latest acquisition_status_update.yml, then rerun reconciliation.",
            "command_hints": [
                "ea literature import-zotero-status /path/to/ea-project --batch-status literature/zotero_codex_batch_status.json",
                "ea literature sync-status /path/to/ea-project --update literature/acquisition_status_update.yml",
                *base_commands,
            ],
            "file_refs": ["literature/deployment_status.yml", "literature/zotero_codex_status_import.yml"],
            "requires_user_confirmation": False,
        },
        "deployment_cached_fulltext_mismatch": {
            "title": "Resync deployment_status.yml cached count from the latest status import.",
            "recommended_next_step": "Import the latest Zotero-Codex batch status or sync the latest acquisition_status_update.yml, then rerun reconciliation.",
            "command_hints": [
                "ea literature import-zotero-status /path/to/ea-project --batch-status literature/zotero_codex_batch_status.json",
                "ea literature sync-status /path/to/ea-project --update literature/acquisition_status_update.yml",
                *base_commands,
            ],
            "file_refs": ["literature/deployment_status.yml", "literature/zotero_codex_status_import.yml"],
            "requires_user_confirmation": False,
        },
        "deployment_cache_count_differs_from_cache_index": {
            "title": "Choose the authoritative cached-fulltext count.",
            "recommended_next_step": "If cache_index.yml is current, sync deployment status from the latest status update; if deployment_status.yml is current, refresh cache_index.yml from acquisition import/status artifacts.",
            "command_hints": [
                "ea literature sync-status /path/to/ea-project --update literature/acquisition_status_update.yml",
                "ea literature import-acquisition /path/to/ea-project --manifest literature/acquisition_manifest.yml",
                *base_commands,
            ],
            "file_refs": ["literature/deployment_status.yml", "literature/cache_index.yml"],
            "requires_user_confirmation": True,
            "question_for_user": "Should EA treat deployment_status.yml or cache_index.yml as the authoritative cached-fulltext count?",
        },
    }
    if code.startswith("origin_sync_") and code.endswith("_mismatch"):
        suggestions[code] = {
            "title": "Refresh origin_thread_sync.yml from deployment_status.yml.",
            "recommended_next_step": "Run sync-status with the latest acquisition status update so origin-thread handoff counts mirror deployment_status.yml.",
            "command_hints": [
                "ea literature sync-status /path/to/ea-project --update literature/acquisition_status_update.yml",
                *base_commands,
            ],
            "file_refs": ["literature/origin_thread_sync.yml", "literature/deployment_status.yml"],
            "requires_user_confirmation": False,
        }
    suggestion = suggestions.get(
        code,
        {
            "title": "Review this reconciliation finding manually.",
            "recommended_next_step": "Inspect the source refs and rerun reconciliation after correcting the relevant local status artifacts.",
            "command_hints": base_commands,
            "requires_user_confirmation": True,
        },
    )
    if expected_ref := details.get("expected_ref"):
        suggestion = {**suggestion, "file_refs": _unique([*(suggestion.get("file_refs") or []), str(expected_ref)])}
    return _compact_dict({"finding_code": code, **suggestion, "auto_applied": False})


def _reconciliation_repair_actions(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: dict[str, dict[str, Any]] = {}
    for finding in findings:
        suggestion = finding.get("repair_suggestion")
        if not isinstance(suggestion, dict):
            continue
        key = _as_text(suggestion.get("title") or suggestion.get("finding_code"))
        action = actions.setdefault(
            key,
            {
                "title": suggestion.get("title"),
                "finding_codes": [],
                "recommended_next_step": suggestion.get("recommended_next_step"),
                "command_hints": [],
                "file_refs": [],
                "requires_user_confirmation": False,
            },
        )
        action["finding_codes"] = _unique([*action["finding_codes"], _as_text(finding.get("code"))])
        action["command_hints"] = _unique([*action["command_hints"], *(suggestion.get("command_hints") or [])])
        action["file_refs"] = _unique([*action["file_refs"], *(suggestion.get("file_refs") or [])])
        action["requires_user_confirmation"] = bool(action["requires_user_confirmation"] or suggestion.get("requires_user_confirmation"))
    return [_compact_dict(action) for action in actions.values()]


def _reconciliation_questions_for_user(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    questions: dict[str, dict[str, Any]] = {}
    for finding in findings:
        suggestion = finding.get("repair_suggestion")
        if not isinstance(suggestion, dict) or not suggestion.get("question_for_user"):
            continue
        question = _as_text(suggestion.get("question_for_user"))
        record = questions.setdefault(
            question,
            {"question": question, "finding_codes": [], "why_it_matters": "Answer only if this affects the next repair step."},
        )
        record["finding_codes"] = _unique([*record["finding_codes"], _as_text(finding.get("code"))])
    return list(questions.values())


def _markdown_value(value: Any) -> str:
    if value in (None, "", [], {}):
        return "not recorded"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list):
        return "; ".join(_markdown_value(item) for item in value if item not in (None, "", [], {})) or "not recorded"
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).replace("\n", " ").strip() or "not recorded"


def _markdown_bullets(values: list[Any], *, code: bool = False) -> list[str]:
    if not values:
        return ["- not recorded"]
    lines = []
    for value in values:
        text = _markdown_value(value)
        lines.append(f"- `{text}`" if code else f"- {text}")
    return lines


def _markdown_mapping(mapping: dict[str, Any]) -> list[str]:
    if not mapping:
        return ["- not recorded"]
    return [f"- {key}: {_markdown_value(value)}" for key, value in mapping.items()]


def _reconciliation_markdown(reconciliation: dict[str, Any]) -> str:
    summary = reconciliation.get("summary") if isinstance(reconciliation.get("summary"), dict) else {}
    source_refs = reconciliation.get("source_refs") if isinstance(reconciliation.get("source_refs"), dict) else {}
    findings = reconciliation.get("findings") if isinstance(reconciliation.get("findings"), list) else []
    repair_actions = reconciliation.get("repair_actions") if isinstance(reconciliation.get("repair_actions"), list) else []
    questions = reconciliation.get("questions_for_user") if isinstance(reconciliation.get("questions_for_user"), list) else []
    boundaries = reconciliation.get("boundaries") if isinstance(reconciliation.get("boundaries"), list) else []

    lines = [
        "# Literature Acquisition Reconciliation Audit",
        "",
        "Generated from `literature/acquisition_reconciliation.yml` as a human-readable audit view.",
        "",
        "## Report",
        "",
        f"- project_id: {_markdown_value(reconciliation.get('project_id'))}",
        f"- status: {_markdown_value(reconciliation.get('status'))}",
        f"- reconciled_at: {_markdown_value(reconciliation.get('reconciled_at'))}",
        f"- yaml_ref: {_markdown_value(reconciliation.get('yaml_ref', 'literature/acquisition_reconciliation.yml'))}",
        f"- markdown_ref: {_markdown_value(reconciliation.get('markdown_ref', 'literature/acquisition_reconciliation.md'))}",
        "",
        "## Source Refs",
        "",
        *_markdown_mapping(source_refs),
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | --- |",
    ]
    for key, value in summary.items():
        lines.append(f"| {key} | {_markdown_value(value)} |")

    lines.extend(["", "## Findings", ""])
    if findings:
        for index, finding in enumerate(findings, start=1):
            if not isinstance(finding, dict):
                continue
            suggestion = finding.get("repair_suggestion") if isinstance(finding.get("repair_suggestion"), dict) else {}
            details = finding.get("details") if isinstance(finding.get("details"), dict) else {}
            lines.extend(
                [
                    f"### F{index:03d} `{_markdown_value(finding.get('code'))}` [{_markdown_value(finding.get('severity'))}]",
                    "",
                    _markdown_value(finding.get("message")),
                    "",
                    "**Details**",
                    "",
                    *_markdown_mapping(details),
                    "",
                    "**Repair Suggestion**",
                    "",
                    f"- title: {_markdown_value(suggestion.get('title'))}",
                    f"- recommended_next_step: {_markdown_value(suggestion.get('recommended_next_step'))}",
                    f"- requires_user_confirmation: {_markdown_value(suggestion.get('requires_user_confirmation'))}",
                    f"- auto_applied: {_markdown_value(suggestion.get('auto_applied'))}",
                    "- command_hints:",
                    *_markdown_bullets(suggestion.get("command_hints") or [], code=True),
                    "- file_refs:",
                    *_markdown_bullets(suggestion.get("file_refs") or [], code=True),
                    "",
                ]
            )
    else:
        lines.append("No findings recorded.")

    lines.extend(["", "## Repair Actions", ""])
    if repair_actions:
        for index, action in enumerate(repair_actions, start=1):
            if not isinstance(action, dict):
                continue
            lines.extend(
                [
                    f"### A{index:03d} {_markdown_value(action.get('title'))}",
                    "",
                    f"- finding_codes: {_markdown_value(action.get('finding_codes'))}",
                    f"- recommended_next_step: {_markdown_value(action.get('recommended_next_step'))}",
                    f"- requires_user_confirmation: {_markdown_value(action.get('requires_user_confirmation'))}",
                    "- command_hints:",
                    *_markdown_bullets(action.get("command_hints") or [], code=True),
                    "- file_refs:",
                    *_markdown_bullets(action.get("file_refs") or [], code=True),
                    "",
                ]
            )
    else:
        lines.append("No repair actions recorded.")

    lines.extend(["", "## Questions For User", ""])
    if questions:
        for index, question in enumerate(questions, start=1):
            if not isinstance(question, dict):
                continue
            lines.extend(
                [
                    f"### Q{index:03d}",
                    "",
                    f"- question: {_markdown_value(question.get('question'))}",
                    f"- finding_codes: {_markdown_value(question.get('finding_codes'))}",
                    f"- why_it_matters: {_markdown_value(question.get('why_it_matters'))}",
                    "",
                ]
            )
    else:
        lines.append("No user questions recorded.")

    lines.extend(
        [
            "",
            "## Boundaries",
            "",
            *(_markdown_bullets(boundaries) if boundaries else ["- This Markdown rendering is local artifact rendering only."]),
            "- Rendering this Markdown view does not repair records, operate Zotero, open browsers, resolve DOI pages, download PDFs, parse full text, store credentials, or handle institution-login state.",
            "",
        ]
    )
    return "\n".join(lines)


def render_literature_acquisition_reconciliation(
    root: Path,
    *,
    reconciliation_path: Path | None = None,
) -> dict[str, Any]:
    literature_root = root / "literature"
    reconciliation_path = reconciliation_path or literature_root / "acquisition_reconciliation.yml"
    if not reconciliation_path.is_absolute():
        reconciliation_path = root / reconciliation_path
    if not reconciliation_path.exists():
        raise FileNotFoundError(reconciliation_path)

    reconciliation = read_yaml(reconciliation_path)
    if not isinstance(reconciliation, dict):
        raise ValueError(f"Reconciliation artifact must be a mapping: {reconciliation_path}")

    markdown_path = literature_root / "acquisition_reconciliation.md"
    yaml_ref = _project_relative(root, reconciliation_path)
    markdown_ref = _project_relative(root, markdown_path)
    updated_reconciliation = {**reconciliation, "yaml_ref": yaml_ref, "markdown_ref": markdown_ref}
    if updated_reconciliation != reconciliation:
        write_yaml(reconciliation_path, updated_reconciliation)

    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(_reconciliation_markdown(updated_reconciliation), encoding="utf-8")

    status_path = literature_root / "deployment_status.yml"
    status: dict[str, Any] | None = None
    if status_path.exists():
        status = read_yaml(status_path)
        status.update(
            _compact_dict(
                {
                    "acquisition_reconciliation_ref": yaml_ref,
                    "acquisition_reconciliation_markdown_ref": markdown_ref,
                    "acquisition_reconciliation_status": updated_reconciliation.get("status"),
                    "last_acquisition_reconciliation_at": updated_reconciliation.get("reconciled_at"),
                }
            )
        )
        write_yaml(status_path, status)

    return {
        "reconciliation_path": str(reconciliation_path),
        "markdown_path": str(markdown_path),
        "status_path": str(status_path) if status_path.exists() else None,
        "reconciliation": updated_reconciliation,
        "status": status,
    }


def reconcile_literature_acquisition(
    root: Path,
    *,
    reconciled_at: str | None = None,
) -> dict[str, Any]:
    literature_root = root / "literature"
    status_path = literature_root / "deployment_status.yml"
    if not status_path.exists():
        raise FileNotFoundError(status_path)
    reconciled_at = reconciled_at or EARecord.now_iso()
    status = read_yaml(status_path)
    project_id = str(status.get("project_id") or _project_context(root).get("project_id", "unknown-project"))
    artifact_paths = {
        "acquisition_manifest": literature_root / "acquisition_manifest.yml",
        "zotero_codex_status_import": literature_root / "zotero_codex_status_import.yml",
        "library_manifest": literature_root / "library_manifest.yml",
        "cache_index": literature_root / "cache_index.yml",
        "reference_index": literature_root / "references" / "index.yml",
        "deployment_status": status_path,
        "origin_thread_sync": literature_root / "origin_thread_sync.yml",
    }
    artifacts: dict[str, dict[str, Any]] = {}
    refs: dict[str, str] = {}
    findings: list[dict[str, Any]] = []
    for name, path in artifact_paths.items():
        if path.exists():
            artifacts[name] = _load_manifest(path)
            refs[name] = _project_relative(root, path)
        elif name in {"acquisition_manifest", "zotero_codex_status_import", "library_manifest", "cache_index", "reference_index"}:
            _reconciliation_finding(
                findings,
                severity="warning",
                code=f"missing_{name}",
                message=f"Optional literature acquisition artifact is missing: {name}.",
                details={"expected_ref": _project_relative(root, path)},
            )

    if not any(name in artifacts for name in ("acquisition_manifest", "zotero_codex_status_import", "library_manifest")):
        _reconciliation_finding(
            findings,
            severity="error",
            code="missing_reconciliation_sources",
            message="No acquisition manifest, Zotero-Codex status import, or library manifest is available to reconcile.",
        )

    manifest_items = _manifest_items(artifacts.get("acquisition_manifest", {})) if "acquisition_manifest" in artifacts else []
    library = artifacts.get("library_manifest", {})
    library_items = [item for item in library.get("items") or [] if isinstance(item, dict)]
    cache = artifacts.get("cache_index", {})
    cache_items = [item for item in cache.get("items") or [] if isinstance(item, dict)]
    references = (artifacts.get("reference_index", {}).get("references") or {}) if "reference_index" in artifacts else {}
    status_import = artifacts.get("zotero_codex_status_import", {})
    status_items = _status_import_items(status_import)
    origin_sync = artifacts.get("origin_thread_sync", {})

    declared_library_count = library.get("item_count")
    if declared_library_count is not None and _safe_int(declared_library_count, -1) != len(library_items):
        _reconciliation_finding(
            findings,
            severity="error",
            code="library_item_count_mismatch",
            message="library_manifest.yml item_count does not match the number of library items.",
            details={"declared": declared_library_count, "actual": len(library_items)},
        )
    declared_cache_count = cache.get("cached_count")
    actual_cache_count = sum(1 for item in cache_items if item.get("cache_path"))
    if declared_cache_count is not None and _safe_int(declared_cache_count, -1) != actual_cache_count:
        _reconciliation_finding(
            findings,
            severity="error",
            code="cache_count_mismatch",
            message="cache_index.yml cached_count does not match items with cache_path.",
            details={"declared": declared_cache_count, "actual": actual_cache_count},
        )

    reference_ids = set(references.keys()) if isinstance(references, dict) else set()
    for item in library_items:
        reference_id = _as_text(item.get("reference_id")).strip()
        if reference_id and reference_id not in reference_ids:
            _reconciliation_finding(
                findings,
                severity="error",
                code="missing_reference_record",
                message="A library item points to a reference_id missing from literature/references/index.yml.",
                details={"reference_id": reference_id, "title": item.get("title"), "doi": item.get("doi")},
            )

    library_keys = _literature_items_by_key(library_items)
    status_keys = _literature_items_by_key(status_items)
    combined_result_keys = library_keys | status_keys
    for item in manifest_items:
        keys = _literature_identifier_keys(item)
        if keys and not (keys & combined_result_keys):
            _reconciliation_finding(
                findings,
                severity="error",
                code="manifest_item_missing_from_outputs",
                message="An acquisition manifest item is not represented in the library manifest or Zotero-Codex status import.",
                details={"title": item.get("title"), "doi": item.get("doi")},
            )

    for item in cache_items:
        keys = _literature_identifier_keys(item)
        if keys and not (keys & (library_keys | status_keys)):
            _reconciliation_finding(
                findings,
                severity="error",
                code="cache_item_missing_from_library_or_status",
                message="A cache index item is not represented in the library manifest or Zotero-Codex status import.",
                details={"title": item.get("title"), "doi": item.get("doi"), "cache_path": item.get("cache_path")},
            )

    if status_import:
        for field, status_field in [
            ("downloaded_fulltext", "downloaded_fulltext"),
            ("cached_fulltext", "cached_fulltext"),
        ]:
            imported_value = status_import.get(field)
            deployed_value = status.get(status_field)
            if imported_value is not None and deployed_value is not None and _safe_int(imported_value, -1) != _safe_int(deployed_value, -1):
                _reconciliation_finding(
                    findings,
                    severity="error",
                    code=f"deployment_{status_field}_mismatch",
                    message=f"deployment_status.yml {status_field} does not match Zotero-Codex status import.",
                    details={"status_import": imported_value, "deployment_status": deployed_value},
                )
    if cache and status.get("cached_fulltext") is not None and _safe_int(status.get("cached_fulltext"), -1) != actual_cache_count:
        _reconciliation_finding(
            findings,
            severity="warning",
            code="deployment_cache_count_differs_from_cache_index",
            message="deployment_status.yml cached_fulltext differs from cache_index.yml cached_count.",
            details={"deployment_status": status.get("cached_fulltext"), "cache_index": actual_cache_count},
        )
    for field in ("downloaded_fulltext", "cached_fulltext", "candidate_count", "deduped_count"):
        if origin_sync and status.get(field) is not None and origin_sync.get(field) is not None:
            if _safe_int(status.get(field), -1) != _safe_int(origin_sync.get(field), -1):
                _reconciliation_finding(
                    findings,
                    severity="error",
                    code=f"origin_sync_{field}_mismatch",
                    message=f"origin_thread_sync.yml {field} does not mirror deployment_status.yml.",
                    details={"deployment_status": status.get(field), "origin_thread_sync": origin_sync.get(field)},
                )

    for finding in findings:
        finding["repair_suggestion"] = _reconciliation_repair_suggestion(finding)
    error_count = sum(1 for item in findings if item.get("severity") == "error")
    warning_count = sum(1 for item in findings if item.get("severity") == "warning")
    reconciliation_status = "fail" if error_count else "warnings" if warning_count else "pass"
    repair_actions = _reconciliation_repair_actions(findings)
    questions_for_user = _reconciliation_questions_for_user(findings)
    reconciliation = {
        "schema_version": "0.2",
        "project_id": project_id,
        "reconciled_at": reconciled_at,
        "status": reconciliation_status,
        "yaml_ref": "literature/acquisition_reconciliation.yml",
        "markdown_ref": "literature/acquisition_reconciliation.md",
        "summary": {
            "error_count": error_count,
            "warning_count": warning_count,
            "acquisition_manifest_items": len(manifest_items),
            "library_items": len(library_items),
            "cache_items": len(cache_items),
            "cached_count": actual_cache_count,
            "reference_count": len(reference_ids),
            "zotero_status_items": len(status_items),
        },
        "source_refs": refs,
        "findings": findings,
        "repair_actions": repair_actions,
        "questions_for_user": questions_for_user,
        "boundaries": [
            "This reconciliation reads local EA/Zotero-Codex status artifacts only.",
            "Repair suggestions are advisory; EA does not automatically modify acquisition, library, cache, reference, or Zotero-Codex artifacts.",
            "No Zotero scripts, browser automation, DOI resolution, PDF download, credential handling, or full-text parsing is executed by EA.",
        ],
    }
    reconciliation_path = literature_root / "acquisition_reconciliation.yml"
    markdown_path = literature_root / "acquisition_reconciliation.md"
    write_yaml(reconciliation_path, reconciliation)
    markdown_path.write_text(_reconciliation_markdown(reconciliation), encoding="utf-8")
    status.update(
        {
            "acquisition_reconciliation_ref": "literature/acquisition_reconciliation.yml",
            "acquisition_reconciliation_markdown_ref": "literature/acquisition_reconciliation.md",
            "acquisition_reconciliation_status": reconciliation_status,
            "last_acquisition_reconciliation_at": reconciled_at,
        }
    )
    write_yaml(status_path, status)
    return {
        "reconciliation_path": str(reconciliation_path),
        "markdown_path": str(markdown_path),
        "status_path": str(status_path),
        "reconciliation": reconciliation,
        "status": status,
    }


def _load_manifest(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    return read_yaml(path)


def _manifest_items(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("items", "papers", "references", "candidates"):
        value = manifest.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    results = manifest.get("results")
    if isinstance(results, list):
        return [item for item in results if isinstance(item, dict)]
    if isinstance(results, dict):
        return [item for item in results.values() if isinstance(item, dict)]
    targets = manifest.get("targets")
    if isinstance(targets, list):
        return [item for item in targets if isinstance(item, dict)]
    return []


def _load_candidate_items(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _read_csv_rows(path)
    if suffix == ".jsonl":
        items = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    if isinstance(data, dict):
                        items.append(data)
        return items
    data = _load_manifest(path)
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return _manifest_items(data)


def _coerce_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list | tuple | set):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _source_candidate_method(method: str) -> str:
    normalized = str(method or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "infrared": "ftir",
        "ir": "ftir",
        "optical_absorption": "uv_vis",
        "optical_spectroscopy": "uv_vis",
        "uvvis": "uv_vis",
        "uv_vis_absorption": "uv_vis",
        "uv_visible": "uv_vis",
        "uv_visible_absorption": "uv_vis",
        "surface_spectroscopy": "xps",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in SOURCE_CANDIDATE_METHODS:
        raise ValueError(f"Unsupported source-candidate method: {method}. Expected one of {sorted(SOURCE_CANDIDATE_METHODS)}")
    return normalized


def _source_candidate_default_path(root: Path, method: str, *, confirmed: bool) -> Path:
    stem = "confirmed" if confirmed else "draft"
    return root / "literature" / f"{stem}_{method}_source_candidates.yml"


def _source_candidate_source_items_path(root: Path, source_items_path: Path | None) -> Path:
    if source_items_path is not None:
        return source_items_path if source_items_path.is_absolute() else root / source_items_path
    library_manifest = root / "literature" / "library_manifest.yml"
    if library_manifest.exists() and _manifest_items(_load_manifest(library_manifest)):
        return library_manifest
    return root / "literature" / "selected_items.yml"


def _source_candidate_seed_id(method: str, item: dict[str, Any], index: int) -> str:
    reference_id = str(item.get("reference_id") or "").strip()
    if reference_id:
        return reference_id
    raw_id = str(item.get("candidate_id") or item.get("id") or item.get("doi") or item.get("title") or index).strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", raw_id).strip("-")[:48]
    return f"ref-lit-{method}-{slug}" if slug else f"ref-lit-{method}-{index:03d}"


def _source_candidate_reference_seed(item: dict[str, Any], *, seed_id: str, source_ref: str) -> dict[str, Any]:
    seed: dict[str, Any] = {
        "citation": _item_citation(item) or str(item.get("title") or seed_id),
        "title": item.get("title"),
        "authors": _item_authors(item),
        "year": item.get("year") or item.get("publication_year") or item.get("published_year"),
        "venue": item.get("venue") or item.get("journal") or item.get("container_title"),
        "doi": item.get("doi") or item.get("DOI"),
        "url": item.get("url") or item.get("article_url") or item.get("landing_page_url"),
        "local_path": item.get("local_path") or item.get("pdf_path"),
        "source_type": "literature_library",
        "source_item_ref": source_ref,
        "source_item_id": item.get("reference_id") or item.get("candidate_id") or item.get("id"),
    }
    return _compact_dict(seed)


def _source_candidate_base(method: str, item: dict[str, Any], *, index: int, seed_id: str) -> dict[str, Any]:
    title = str(item.get("title") or "untitled literature item").strip()
    summary = (
        f"Literature item `{title}` was selected from the project literature workflow. "
        "Replace this summary with the specific source statement that supports the candidate before enabling it."
    )
    common: dict[str, Any] = {
        "method": method,
        "include_in_source_packet": False,
        "candidate_id": f"{method}-lit-source-candidate-{index:03d}",
        "source_summary": summary,
        "applicability_notes": [
            "TODO: record the sample/material conditions and why this literature item applies to this project."
        ],
        "reference_ids": [seed_id],
        "confidence": "low",
        "caveats": [
            "Draft literature-derived source candidate; fill method-specific fields and confirm before source-packet use."
        ],
        "source_item": _compact_dict(
            {
                "title": item.get("title"),
                "year": item.get("year") or item.get("publication_year") or item.get("published_year"),
                "doi": item.get("doi") or item.get("DOI"),
                "url": item.get("url") or item.get("article_url") or item.get("landing_page_url"),
                "rank": item.get("rank"),
                "score": item.get("score"),
                "reference_id": item.get("reference_id"),
            }
        ),
    }
    if method == "ftir":
        common.update(
            {
                "assignment_type": "functional_group",
                "assignment_label": None,
                "band_label": None,
                "material_scope": None,
                "sample_scope": None,
                "wavenumber_window_cm1": [None, None],
                "expected_feature": "absorbance_maximum",
            }
        )
    elif method == "uv_vis":
        common.update(
            {
                "candidate_type": None,
                "optical_target": None,
                "reported_energy_eV": None,
                "energy_window_eV": [None, None],
                "wavelength_window_nm": [None, None],
                "transition_model": None,
                "transition_assumption": None,
                "tauc_transform": None,
                "signal_mode": None,
                "correction_context": {
                    "substrate": None,
                    "reference": None,
                    "background": None,
                    "sample_geometry": None,
                    "diffuse_reflectance_model": None,
                },
                "evidence_requirements": [
                    "Link the candidate to reviewed UV-Vis metadata, processing parameters, and project references before use."
                ],
            }
        )
    else:
        common.update(
            {
                "suggestion_type": None,
                "element": None,
                "core_level": None,
                "parameter_origin": "source_suggested",
                "center_delta_eV": None,
                "area_ratio": None,
                "fwhm_ratio": None,
                "tougaard_B": None,
                "tougaard_C_eV2": None,
                "integration_direction": None,
            }
        )
    return common


def _source_candidate_builder_next_step(method: str, output_ref: str) -> str:
    if method == "ftir":
        return f"After preflight passes, run `ea ftir build-assignment-packet /path/to/ea-project --literature-manifest {output_ref}`."
    if method == "xps":
        return f"After preflight passes, run `ea xps build-source-packet /path/to/ea-project --literature-manifest {output_ref}`."
    return (
        "After preflight passes, keep the confirmed UV-Vis manifest as source-backed staging for a future "
        "`ea uv-vis build-source-packet` workflow; EA v0.2 does not yet build UV-Vis source packets from this manifest."
    )


def _source_candidate_method_aliases(method: str) -> set[str]:
    if method == "ftir":
        return {"ftir", "infrared", "ftir_assignment", "ftir_assignment_source_packet"}
    if method == "uv_vis":
        return {
            "uv_vis",
            "uvvis",
            "uv_visible",
            "uv_visible_absorption",
            "uv_vis_absorption",
            "optical_absorption",
            "optical_spectroscopy",
        }
    return {"xps", "xps_parameter", "xps_parameter_source_packet", "surface_spectroscopy"}


def _source_candidate_preflight_fix_step(method: str) -> str:
    if method == "uv_vis":
        return "Fix errors and missing required metadata before using this UV-Vis manifest in a future source-packet workflow."
    return "Fix errors and missing required metadata before building FTIR/XPS source packets."


def _source_candidate_preflight_boundary(method: str) -> str:
    if method == "uv_vis":
        return (
            "Preflight status does not prove UV-Vis band gaps, transition types, optical feature assignments, "
            "substrate/reference/background corrections, mechanisms, thickness, or material state."
        )
    return "Preflight status does not prove FTIR composition/functional groups or XPS chemical states/composition."


def prepare_literature_source_candidate_manifest(
    root: Path,
    *,
    method: str,
    source_items_path: Path | None = None,
    output_path: Path | None = None,
    confirm_for_source_packet: bool = False,
    user_response: str | None = None,
    max_items: int | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    method = _source_candidate_method(method)
    literature_root = root / "literature"
    literature_root.mkdir(parents=True, exist_ok=True)
    source_path = _source_candidate_source_items_path(root, source_items_path)
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    items = _load_candidate_items(source_path)
    if max_items is not None:
        if max_items <= 0:
            raise ValueError("max_items must be positive")
        items = items[:max_items]
    if not items:
        raise ValueError("source item file contains no literature items")
    if confirm_for_source_packet and not str(user_response or "").strip():
        raise ValueError("--confirm-for-source-packet requires --user-response")

    created_at = created_at or EARecord.now_iso()
    project = _project_context(root)
    project_id = str(project.get("project_id", "unknown-project"))
    output_path = output_path or _source_candidate_default_path(root, method, confirmed=confirm_for_source_packet)
    if not output_path.is_absolute():
        output_path = root / output_path
    source_ref = _project_relative(root, source_path)
    output_ref = _project_relative(root, output_path)

    reference_seeds: dict[str, Any] = {}
    candidates: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        seed_id = _source_candidate_seed_id(method, item, index)
        reference_seeds[seed_id] = _source_candidate_reference_seed(item, seed_id=seed_id, source_ref=source_ref)
        candidates.append(_source_candidate_base(method, item, index=index, seed_id=seed_id))

    manifest: dict[str, Any] = {
        "schema_version": "0.2",
        "source": "ea.literature.source_candidates:v0.2",
        "project_id": project_id,
        "method_scope": [method],
        "status": "confirmed_for_source_packet" if confirm_for_source_packet else "draft_requires_candidate_edit",
        "prepared_at": created_at,
        "source_items_ref": source_ref,
        "source_item_count": len(items),
        "confirmed_for_source_packet": bool(confirm_for_source_packet),
        "reference_seeds": reference_seeds,
        "candidates": candidates,
        "next_steps": [
            "Fill method-specific candidate fields and set include_in_source_packet: true only for candidates the user wants staged.",
            f"Run `ea literature preflight-source-candidates /path/to/ea-project --method {method} --manifest {output_ref}` before building a source packet.",
            _source_candidate_builder_next_step(method, output_ref),
        ],
        "boundaries": [
            "This manifest preparation is local deterministic staging only.",
            "It does not search the web, download or parse articles/PDFs, register references, inject report citations, apply assignments/parameters, or prove material conclusions.",
            "Draft candidate stubs are disabled by include_in_source_packet: false until a user or agent fills method-specific fields and confirms applicability.",
        ],
    }
    if confirm_for_source_packet:
        manifest["confirmation"] = {
            "status": "user_confirmed",
            "confirmed_at": created_at,
            "user_response": str(user_response),
            "reviewed_content": "User confirmed this source-candidate manifest may be used for source-packet staging after candidate-level edits.",
        }
    write_yaml(output_path, manifest)

    status_path = ensure_literature_status(root, project_id=project_id)
    status = read_yaml(status_path)
    status.update(
        {
            f"{method}_source_candidate_manifest_ref": output_ref,
            f"{method}_source_candidate_manifest_status": manifest["status"],
            f"{method}_source_candidate_manifest_updated_at": created_at,
        }
    )
    write_yaml(status_path, status)

    return {
        "manifest_path": str(output_path),
        "manifest_ref": output_ref,
        "status": manifest["status"],
        "method": method,
        "source_items_ref": source_ref,
        "source_item_count": len(items),
        "candidate_count": len(candidates),
        "reference_seed_count": len(reference_seeds),
        "confirmed_for_source_packet": bool(confirm_for_source_packet),
    }


def _source_candidate_missing_fields(method: str, candidate: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if method == "ftir":
        required = FTIR_SOURCE_CANDIDATE_REQUIRED_FIELDS
    elif method == "uv_vis":
        required = UV_VIS_SOURCE_CANDIDATE_REQUIRED_FIELDS
    else:
        required = XPS_SOURCE_CANDIDATE_REQUIRED_FIELDS
    for field in required:
        value = candidate.get(field)
        if value in (None, "", [], {}):
            missing.append(field)
    if method == "ftir":
        window = candidate.get("wavenumber_window_cm1")
        if not (isinstance(window, list | tuple) and len(window) >= 2 and _as_float(window[0]) is not None and _as_float(window[1]) is not None):
            if "wavenumber_window_cm1" not in missing:
                missing.append("wavenumber_window_cm1")
    elif method == "uv_vis":
        candidate_type = str(candidate.get("candidate_type") or "").strip().lower().replace("-", "_")
        if candidate_type not in UV_VIS_SOURCE_CANDIDATE_TYPES and "candidate_type" not in missing:
            missing.append("supported_candidate_type")
        energy = _as_float(candidate.get("reported_energy_eV"))
        energy_window = candidate.get("energy_window_eV")
        has_energy_window = (
            isinstance(energy_window, list | tuple)
            and len(energy_window) >= 2
            and _as_float(energy_window[0]) is not None
            and _as_float(energy_window[1]) is not None
        )
        wavelength_window = candidate.get("wavelength_window_nm")
        has_wavelength_window = (
            isinstance(wavelength_window, list | tuple)
            and len(wavelength_window) >= 2
            and _as_float(wavelength_window[0]) is not None
            and _as_float(wavelength_window[1]) is not None
        )
        if candidate_type == "optical_transition_model":
            for field in ["transition_model", "transition_assumption", "tauc_transform"]:
                if candidate.get(field) in (None, "", [], {}):
                    missing.append(field)
        elif candidate_type == "optical_gap_candidate":
            if energy is None and not has_energy_window:
                missing.append("reported_energy_eV_or_energy_window_eV")
            if candidate.get("transition_assumption") in (None, "", [], {}):
                missing.append("transition_assumption")
        elif candidate_type == "optical_feature_assignment":
            if energy is None and not has_energy_window and not has_wavelength_window:
                missing.append("reported_energy_or_wavelength_window")
            if candidate.get("optical_target") in (None, "", [], {}):
                missing.append("optical_target")
        elif candidate_type == "correction_context_candidate":
            correction_context = candidate.get("correction_context")
            if not isinstance(correction_context, dict) or not any(
                correction_context.get(key)
                for key in ["substrate", "reference", "background", "sample_geometry", "diffuse_reflectance_model"]
            ):
                missing.append("correction_context")
    else:
        suggestion_type = str(candidate.get("suggestion_type") or "").strip().lower().replace("-", "_")
        if suggestion_type == "spin_orbit_constraint":
            for field in ["center_delta_eV", "area_ratio", "fwhm_ratio"]:
                if _as_float(candidate.get(field)) is None:
                    missing.append(field)
        elif suggestion_type == "tougaard_parameter":
            if _as_float(candidate.get("tougaard_B")) is None and _as_float(candidate.get("tougaard_C_eV2")) is None:
                missing.append("tougaard_B_or_tougaard_C_eV2")
        elif "suggestion_type" not in missing:
            missing.append("supported_suggestion_type")
    return _unique(missing)


def preflight_literature_source_candidate_manifest(
    root: Path,
    *,
    method: str,
    manifest_path: Path,
    output_path: Path | None = None,
    checked_at: str | None = None,
) -> dict[str, Any]:
    method = _source_candidate_method(method)
    resolved_manifest = manifest_path if manifest_path.is_absolute() else root / manifest_path
    literature_root = root / "literature"
    literature_root.mkdir(parents=True, exist_ok=True)
    checked_at = checked_at or EARecord.now_iso()
    output_path = output_path or literature_root / f"{method}_source_candidates_preflight.yml"
    if not output_path.is_absolute():
        output_path = root / output_path

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    reference_seeds: dict[str, Any] = {}
    confirmation_status = ""
    source_manifest_ref = _project_relative(root, resolved_manifest) if resolved_manifest.exists() else str(manifest_path)
    try:
        library, manifest_warnings = confirmed_source_packet_library(
            root,
            manifest_path=resolved_manifest,
            method=method,
            method_aliases=_source_candidate_method_aliases(method),
        )
        warnings.extend(manifest_warnings)
        candidates = [candidate for candidate in library.get("candidates") or [] if isinstance(candidate, dict)]
        reference_seeds = library.get("reference_seeds") if isinstance(library.get("reference_seeds"), dict) else {}
        confirmation_status = str(library.get("confirmation_status") or "")
        source_manifest_ref = str(library.get("source_manifest_ref") or source_manifest_ref)
    except (SourcePacketManifestError, FileNotFoundError) as exc:
        errors.append(
            {
                "code": "source_candidate_manifest_not_ready",
                "message": str(exc),
                "severity": "high",
            }
        )

    candidate_reports: list[dict[str, Any]] = []
    ready_count = 0
    invalid_count = 0
    referenced_ids: set[str] = set()
    for index, candidate in enumerate(candidates, start=1):
        reference_ids = _coerce_string_list(candidate.get("reference_ids"))
        referenced_ids.update(reference_ids)
        missing_fields = _source_candidate_missing_fields(method, candidate)
        candidate_id = str(candidate.get("candidate_id") or candidate.get("assignment_id") or candidate.get("suggestion_id") or f"candidate-{index:03d}")
        status = "ready_for_source_packet" if not missing_fields else "missing_required_metadata"
        if missing_fields:
            invalid_count += 1
            warnings.append(
                {
                    "code": "source_candidate_missing_required_metadata",
                    "message": "A source candidate is missing required metadata before packet staging.",
                    "severity": "high",
                    "candidate_id": candidate_id,
                    "missing_fields": missing_fields,
                }
            )
        else:
            ready_count += 1
        candidate_reports.append(
            {
                "candidate_id": candidate_id,
                "status": status,
                "missing_fields": missing_fields,
                "reference_ids": reference_ids,
            }
        )

    if not errors and not candidates:
        errors.append(
            {
                "code": "source_candidate_manifest_has_no_included_candidates",
                "message": "The manifest has no candidates selected for source-packet staging. Set include_in_source_packet: true on edited candidates.",
                "severity": "high",
            }
        )
    missing_seed_ids = sorted(reference_id for reference_id in referenced_ids if reference_id not in reference_seeds)
    if missing_seed_ids:
        warnings.append(
            {
                "code": "source_candidate_reference_seed_missing",
                "message": "Some reference_ids do not have matching reference_seeds; this is acceptable only if they are already registered project references.",
                "severity": "medium",
                "reference_ids": missing_seed_ids,
            }
        )

    status = "ready_for_source_packet" if not errors and invalid_count == 0 else "not_ready"
    preflight = {
        "schema_version": "0.2",
        "source": "ea.literature.source_candidate_manifest_preflight:v0.2",
        "status": status,
        "method": method,
        "checked_at": checked_at,
        "manifest_ref": source_manifest_ref,
        "confirmation_status": confirmation_status,
        "candidate_count": len(candidates),
        "ready_count": ready_count,
        "invalid_count": invalid_count,
        "reference_seed_count": len(reference_seeds),
        "candidate_reports": candidate_reports,
        "errors": errors,
        "warnings": warnings,
        "next_steps": [
            _source_candidate_preflight_fix_step(method),
            "Run `ea references register-seeds --source-packet ...` only after a source packet is built and the user wants those seeds registered.",
        ],
        "boundaries": [
            "Preflight reads local YAML only; it does not search, download, parse full text, register references, inject citations, or apply assignments/parameters.",
            _source_candidate_preflight_boundary(method),
        ],
    }
    write_yaml(output_path, preflight)
    return {
        "preflight_path": str(output_path),
        "preflight_ref": _project_relative(root, output_path),
        "status": status,
        "method": method,
        "manifest_ref": source_manifest_ref,
        "candidate_count": len(candidates),
        "ready_count": ready_count,
        "invalid_count": invalid_count,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
    }


def _normalized_title(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _as_text(value).lower()).strip()


def _candidate_dedup_key(candidate: dict[str, Any]) -> str:
    doi = _as_text(candidate.get("doi") or candidate.get("DOI")).lower().strip()
    if doi:
        return f"doi:{doi.removeprefix('https://doi.org/').removeprefix('http://doi.org/')}"
    url = _as_text(candidate.get("url") or candidate.get("article_url") or candidate.get("landing_page_url")).lower().strip()
    if url:
        return f"url:{url.rstrip('/')}"
    title = _normalized_title(candidate.get("title"))
    if title:
        return f"title:{title}"
    return f"row:{candidate.get('_row_index')}"


def _project_ranking_terms(root: Path, extra_keywords: list[str] | None = None) -> list[str]:
    project = _project_context(root)
    keywords = generate_literature_keywords(
        project_name=str(project.get("project_name", "")),
        research_direction=str(project.get("research_direction", "")),
        material_system=str(project.get("material_system", "")),
        experiment_type=str(project.get("experiment_type", "")),
        extra_keywords=extra_keywords,
    )
    terms: list[str] = []
    for key in ("material_terms", "method_terms", "topic_terms", "exact_terms"):
        terms.extend(_tokenize(" ".join(keywords.get(key) or [])))
    return _unique(terms)


def _candidate_body(candidate: dict[str, Any]) -> str:
    fields = [
        candidate.get("title"),
        candidate.get("abstract"),
        candidate.get("keywords"),
        candidate.get("notes"),
        candidate.get("venue") or candidate.get("journal") or candidate.get("container_title"),
    ]
    return " ".join(_as_text(field) for field in fields).lower()


def _score_relevance(candidate: dict[str, Any], project_terms: list[str]) -> float:
    supplied = _score_component(candidate.get("project_relevance") or candidate.get("relevance_score") or candidate.get("relevance"))
    if supplied is not None:
        return supplied
    body = _candidate_body(candidate)
    if not body or not project_terms:
        return 1.0
    body_tokens = set(_tokenize(body))
    matches = sum(1 for term in project_terms if term.lower() in body_tokens or term.lower() in body)
    title = _as_text(candidate.get("title")).lower()
    title_matches = sum(1 for term in project_terms if term.lower() in title)
    return max(1.0, min(5.0, 1.0 + matches * 0.45 + title_matches * 0.35))


def _score_venue(candidate: dict[str, Any]) -> float:
    supplied = _score_component(candidate.get("venue_authority") or candidate.get("journal_authority") or candidate.get("venue_score"))
    if supplied is not None:
        return supplied
    impact = _as_float(candidate.get("impact_factor") or candidate.get("journal_impact_factor"))
    if impact is not None:
        if impact >= 30:
            return 5.0
        if impact >= 15:
            return 4.5
        if impact >= 8:
            return 4.0
        if impact >= 4:
            return 3.0
        if impact >= 1:
            return 2.0
        return 1.0
    tier = _as_text(candidate.get("venue_tier") or candidate.get("journal_tier")).lower()
    if tier in {"flagship", "top", "high", "q1"}:
        return 4.5
    if tier in {"medium", "q2"}:
        return 3.0
    venue = _as_text(candidate.get("venue") or candidate.get("journal") or candidate.get("container_title")).lower()
    if any(marker in venue for marker in ("nature", "science", "cell")):
        return 5.0
    if any(marker in venue for marker in ("advanced", "acs nano", "nano letters", "angewandte")):
        return 4.0
    if any(marker in venue for marker in ("journal", "letters", "communications")):
        return 3.0
    return 2.0 if venue else 1.0


def _score_recency(candidate: dict[str, Any], reference_year: int) -> float:
    supplied = _score_component(candidate.get("recency") or candidate.get("recency_score"))
    if supplied is not None:
        return supplied
    year = _as_float(candidate.get("year") or candidate.get("publication_year") or candidate.get("published_year"))
    if year is None:
        return 1.0
    age = max(0, reference_year - int(year))
    if age <= 5:
        return 5.0
    if age <= 15:
        return 3.5
    return 2.0


def _score_influence(candidate: dict[str, Any]) -> float:
    supplied = _score_component(
        candidate.get("citation_or_influence") or candidate.get("influence_score") or candidate.get("citation_score")
    )
    if supplied is not None:
        return supplied
    citations = _as_float(candidate.get("citation_count") or candidate.get("cited_by_count") or candidate.get("citations"))
    if citations is None:
        return 1.0
    if citations >= 1000:
        return 5.0
    if citations >= 300:
        return 4.5
    if citations >= 100:
        return 4.0
    if citations >= 30:
        return 3.0
    if citations >= 1:
        return 2.0
    return 1.0


def _score_fulltext(candidate: dict[str, Any]) -> float:
    supplied = _score_component(
        candidate.get("fulltext_availability_and_usefulness")
        or candidate.get("fulltext_score")
        or candidate.get("availability_score")
    )
    if supplied is not None:
        return supplied
    if candidate.get("local_path") or candidate.get("cache_path") or candidate.get("pdf_path"):
        return 5.0
    status = _as_text(candidate.get("status") or candidate.get("acquisition_status") or candidate.get("fulltext_status")).lower()
    if any(marker in status for marker in ("cached", "downloaded", "fulltext", "full_text")):
        return 5.0
    if _as_bool(candidate.get("open_access")) or candidate.get("pdf_url") or candidate.get("oa_url"):
        return 4.0
    if candidate.get("abstract"):
        return 2.0
    return 1.0


def _score_candidate(candidate: dict[str, Any], *, project_terms: list[str], reference_year: int) -> dict[str, float]:
    project_relevance = _score_relevance(candidate, project_terms)
    venue_authority = _score_venue(candidate)
    recency = _score_recency(candidate, reference_year)
    influence = _score_influence(candidate)
    fulltext = _score_fulltext(candidate)
    score = (
        project_relevance * 0.40
        + venue_authority * 0.20
        + recency * 0.15
        + influence * 0.15
        + fulltext * 0.10
    ) / 5 * 100
    return {
        "project_relevance": round(project_relevance, 2),
        "venue_authority": round(venue_authority, 2),
        "recency": round(recency, 2),
        "citation_or_influence": round(influence, 2),
        "fulltext_availability_and_usefulness": round(fulltext, 2),
        "score": round(score, 2),
    }


def _candidate_record(candidate: dict[str, Any], *, candidate_id: str, scores: dict[str, float], notes: str) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "title": candidate.get("title"),
        "authors": _as_text(candidate.get("authors") or candidate.get("author")),
        "year": candidate.get("year") or candidate.get("publication_year") or candidate.get("published_year"),
        "venue": candidate.get("venue") or candidate.get("journal") or candidate.get("container_title"),
        "doi": candidate.get("doi") or candidate.get("DOI"),
        "url": candidate.get("url") or candidate.get("article_url") or candidate.get("landing_page_url"),
        "project_relevance": scores["project_relevance"],
        "venue_authority": scores["venue_authority"],
        "recency": scores["recency"],
        "citation_or_influence": scores["citation_or_influence"],
        "fulltext_availability_and_usefulness": scores["fulltext_availability_and_usefulness"],
        "score": scores["score"],
        "notes": notes,
    }


def rank_literature_candidates(
    root: Path,
    *,
    candidates_path: Path,
    top_n: int | None = None,
    reference_year: int | None = None,
    source_label: str | None = None,
    extra_keywords: list[str] | None = None,
    metadata_search_executed: bool = False,
    ranked_at: str | None = None,
) -> dict[str, Any]:
    literature_root = root / "literature"
    literature_root.mkdir(parents=True, exist_ok=True)
    resolved_path = candidates_path if candidates_path.is_absolute() else root / candidates_path
    if not resolved_path.exists():
        raise FileNotFoundError(resolved_path)

    project = _project_context(root)
    project_id = str(project.get("project_id", "unknown-project"))
    status_path = ensure_literature_status(root, project_id=project_id)
    status = read_yaml(status_path)
    raw_candidates = _load_candidate_items(resolved_path)
    if not raw_candidates:
        raise ValueError("candidate file contains no literature candidate records")

    reference_year = _reference_year(reference_year)
    project_terms = _project_ranking_terms(root, extra_keywords=extra_keywords)
    source_label = source_label or resolved_path.name
    ranked_at = ranked_at or EARecord.now_iso()
    candidate_rows: list[dict[str, Any]] = []
    best_by_key: dict[str, dict[str, Any]] = {}
    duplicate_count = 0

    for raw_index, raw in enumerate(raw_candidates, start=1):
        candidate = dict(raw)
        candidate["_row_index"] = raw_index
        title = candidate.get("title")
        doi = candidate.get("doi") or candidate.get("DOI")
        url = candidate.get("url") or candidate.get("article_url") or candidate.get("landing_page_url")
        if not (title or doi or url):
            continue
        scores = _score_candidate(candidate, project_terms=project_terms, reference_year=reference_year)
        notes = _as_text(candidate.get("notes"))
        source_id = candidate.get("candidate_id") or candidate.get("id")
        if source_id:
            notes = f"{notes}; source_id={source_id}".strip("; ")
        if not notes:
            notes = (
                "Ranked from supplied or public-search candidate metadata; venue authority uses supplied/verified "
                "fields or transparent proxy heuristics; impact factors are not invented."
            )
        record = _candidate_record(candidate, candidate_id=f"cand-raw-{raw_index:03d}", scores=scores, notes=notes)
        candidate_rows.append(
            {
                "candidate_id": record["candidate_id"],
                "title": record["title"],
                "authors": record["authors"],
                "year": record["year"],
                "venue": record["venue"],
                "doi": record["doi"],
                "url": record["url"],
                "source": candidate.get("source") or source_label,
                "abstract": candidate.get("abstract"),
                "keywords": _as_text(candidate.get("keywords")),
            }
        )
        key = _candidate_dedup_key(candidate)
        existing = best_by_key.get(key)
        if existing is None or float(record["score"]) > float(existing["score"]):
            if existing is not None:
                duplicate_count += 1
            best_by_key[key] = record
        else:
            duplicate_count += 1

    ranked_rows = sorted(
        best_by_key.values(),
        key=lambda row: (
            -float(row["score"]),
            -int(float(row["year"])) if _as_float(row.get("year")) is not None else 0,
            _as_text(row.get("title")).lower(),
        ),
    )
    for rank, row in enumerate(ranked_rows, start=1):
        row["candidate_id"] = f"cand-{rank:03d}"

    confirmed_top_n = status.get("selected_top_n")
    effective_top_n = int(confirmed_top_n or top_n or _recommended_max(status.get("recommended_top_n", recommended_top_n("ordinary"))))
    if effective_top_n <= 0:
        raise ValueError("top_n must be positive")
    selected_rows = ranked_rows[:effective_top_n]
    selection_status = "selected_from_ranked_candidates" if confirmed_top_n else "ranked_preview_awaiting_user_confirmation"
    selected_items = {
        "schema_version": "0.2",
        "project_id": project_id,
        "selection_status": selection_status,
        "selected_top_n": effective_top_n,
        "source_ranking_ref": "literature/ranking.csv",
        "items": [
            _compact_dict(
                {
                    "rank": rank,
                    "candidate_id": row.get("candidate_id"),
                    "title": row.get("title"),
                    "authors": row.get("authors"),
                    "year": row.get("year"),
                    "venue": row.get("venue"),
                    "doi": row.get("doi"),
                    "url": row.get("url"),
                    "score": row.get("score"),
                    "notes": row.get("notes"),
                }
            )
            for rank, row in enumerate(selected_rows, start=1)
        ],
    }
    ranking_path = literature_root / "ranking.csv"
    candidates_table_path = literature_root / "candidates.csv"
    selected_path = literature_root / "selected_items.yml"
    _write_csv_rows(candidates_table_path, RANKING_HEADERS[:7] + ["source", "abstract", "keywords"], candidate_rows)
    _write_csv_rows(ranking_path, RANKING_HEADERS, ranked_rows)
    write_yaml(selected_path, selected_items)

    status.update(
        {
            "status": "ranked_candidates_ready" if confirmed_top_n else "ranked_awaiting_user_confirmation",
            "candidate_count": len(candidate_rows),
            "deduped_count": len(ranked_rows),
            "duplicate_candidate_count": duplicate_count,
            "ranking_ref": "literature/ranking.csv",
            "candidate_table_ref": "literature/candidates.csv",
            "selected_items_ref": "literature/selected_items.yml",
            "candidate_source_ref": _project_relative(root, resolved_path),
            "candidate_ranking_updated_at": ranked_at,
            "candidate_ranking_method": {
                "schema_version": "0.2",
                "reference_year": reference_year,
                "component_scale": "0_to_5",
                "score_scale": "0_to_100",
                "weights": {
                    "project_relevance": 0.40,
                    "venue_authority": 0.20,
                    "recency": 0.15,
                    "citation_or_influence": 0.15,
                    "fulltext_availability_and_usefulness": 0.10,
                },
                "boundaries": [
                    (
                        "Public metadata search was executed, but no Zotero call, browser automation, "
                        "institution login, DOI full-text resolution, or PDF download was executed."
                        if metadata_search_executed
                        else "No live web search, Zotero call, browser automation, DOI resolution, or PDF download was executed."
                    ),
                    (
                        "Venue authority uses supplied/verified metadata, public-search fields, or transparent proxy "
                        "heuristics; impact factors are used only when source-recorded and are not invented."
                    ),
                    "Scores support triage only and require user review before bulk acquisition.",
                ],
            },
            "summary_for_origin_thread": (
                f"Ranked {len(ranked_rows)} literature candidate(s) from {len(candidate_rows)} supplied record(s). "
                + (
                    "Public metadata search was executed; no full-text acquisition was executed."
                    if metadata_search_executed
                    else "No live search or full-text acquisition was executed."
                )
            ),
        }
    )
    if confirmed_top_n:
        status["selected_top_n"] = confirmed_top_n
    write_yaml(status_path, status)
    return {
        "status_path": str(status_path),
        "candidates_path": str(candidates_table_path),
        "ranking_path": str(ranking_path),
        "selected_items_path": str(selected_path),
        "candidate_count": len(candidate_rows),
        "deduped_count": len(ranked_rows),
        "duplicate_candidate_count": duplicate_count,
        "selected_count": len(selected_rows),
        "selection_status": selection_status,
        "top_candidate": ranked_rows[0] if ranked_rows else None,
        "status": status,
    }


def _public_fetch_text(url: str, *, source: str, timeout: int = 20) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "EA-v0.2 public-metadata-search/0.2 (local-first research assistant)",
            "Accept": "application/json, application/xml, text/xml, */*",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - explicit user-invoked public metadata query
        return response.read().decode("utf-8", errors="replace")


def _public_search_url(
    source: PublicMetadataSource,
    query: str,
    max_results: int,
    *,
    cursor: str | None = None,
    offset: int = 0,
) -> str:
    if source == "crossref":
        return "https://api.crossref.org/works?" + urllib.parse.urlencode(
            {"query.bibliographic": query, "rows": max_results, "cursor": cursor or "*"}
        )
    if source == "openalex":
        return "https://api.openalex.org/works?" + urllib.parse.urlencode(
            {"search": query, "per-page": max_results, "cursor": cursor or "*"}
        )
    if source == "arxiv":
        return "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
            {"search_query": f'all:"{query}"', "start": offset, "max_results": max_results}
        )
    raise ValueError(f"Unsupported public metadata source: {source}")


def _public_search_state_path(root: Path) -> Path:
    return root / "literature" / "public_search_state.yml"


def _public_search_task_key(source: str, query: str) -> str:
    return f"{source}::{query}"


def _public_search_run_id(searched_at: str) -> str:
    token = re.sub(r"[^0-9A-Za-z]+", "", searched_at)
    return f"public-search-{token[:20] or 'run'}"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _arxiv_total_results(payload: str) -> int | None:
    root = ET.fromstring(payload)
    ns = {"opensearch": "http://a9.com/-/spec/opensearch/1.1/"}
    total = root.findtext("opensearch:totalResults", default="", namespaces=ns) or ""
    return int(total) if total.isdigit() else None


def _public_next_page(
    source: PublicMetadataSource,
    response_text: str,
    *,
    current_cursor: str | None,
    current_offset: int,
    normalized_count: int,
    max_results: int,
) -> dict[str, Any]:
    if source == "crossref":
        payload = json.loads(response_text)
        next_cursor = payload.get("message", {}).get("next-cursor")
        has_next = bool(next_cursor and next_cursor != current_cursor and normalized_count > 0)
        return {"has_next_page": has_next, "next_cursor": str(next_cursor) if has_next else None, "next_offset": None}
    if source == "openalex":
        payload = json.loads(response_text)
        next_cursor = payload.get("meta", {}).get("next_cursor")
        has_next = bool(next_cursor and next_cursor != current_cursor and normalized_count > 0)
        return {"has_next_page": has_next, "next_cursor": str(next_cursor) if has_next else None, "next_offset": None}
    if source == "arxiv":
        next_offset = current_offset + max_results
        total_results = _arxiv_total_results(response_text)
        has_next = normalized_count > 0 and total_results is not None and next_offset < total_results
        return {
            "has_next_page": has_next,
            "next_cursor": None,
            "next_offset": next_offset if has_next else None,
            "total_results": total_results,
        }
    raise ValueError(f"Unsupported public metadata source: {source}")


def _public_search_state_status(progress: dict[str, Any]) -> str:
    if not progress:
        return "complete"
    statuses = [str(item.get("status", "")) for item in progress.values() if isinstance(item, dict)]
    if any(status == "error" for status in statuses):
        return "partial_with_errors"
    if all(status == "complete" for status in statuses):
        return "complete"
    return "in_progress"


def _public_search_next_tasks(progress: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = []
    for item in progress.values():
        if not isinstance(item, dict) or item.get("status") == "complete":
            continue
        tasks.append(
            _compact_dict(
                {
                    "source": item.get("source"),
                    "query": item.get("query"),
                    "next_cursor": item.get("next_cursor"),
                    "next_offset": item.get("next_offset"),
                    "next_page_index": item.get("next_page_index"),
                    "status": item.get("status"),
                }
            )
        )
    return tasks


def _first(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _crossref_year(item: dict[str, Any]) -> int | None:
    for key in ("published-print", "published-online", "issued", "created"):
        parts = item.get(key, {}).get("date-parts") if isinstance(item.get(key), dict) else None
        if parts and parts[0]:
            try:
                return int(parts[0][0])
            except (TypeError, ValueError):
                return None
    return None


def _crossref_authors(item: dict[str, Any]) -> list[str]:
    authors = []
    for author in item.get("author") or []:
        if not isinstance(author, dict):
            continue
        name = " ".join(part for part in [author.get("given"), author.get("family")] if part)
        if name:
            authors.append(name)
    return authors


def _normalize_crossref_results(payload: dict[str, Any], *, query: str) -> list[dict[str, Any]]:
    items = payload.get("message", {}).get("items") or []
    candidates = []
    for item in items:
        if not isinstance(item, dict):
            continue
        candidates.append(
            _compact_dict(
                {
                    "title": _first(item.get("title")),
                    "authors": _crossref_authors(item),
                    "year": _crossref_year(item),
                    "venue": _first(item.get("container-title")),
                    "doi": item.get("DOI"),
                    "url": item.get("URL"),
                    "abstract": item.get("abstract"),
                    "citation_count": item.get("is-referenced-by-count"),
                    "source": "crossref",
                    "source_query": query,
                }
            )
        )
    return candidates


def _openalex_abstract(item: dict[str, Any]) -> str | None:
    inverted = item.get("abstract_inverted_index")
    if not isinstance(inverted, dict):
        return None
    positions: list[tuple[int, str]] = []
    for word, indices in inverted.items():
        if isinstance(indices, list):
            positions.extend((int(index), str(word)) for index in indices if isinstance(index, int))
    return " ".join(word for _, word in sorted(positions)) if positions else None


def _normalize_openalex_results(payload: dict[str, Any], *, query: str) -> list[dict[str, Any]]:
    items = payload.get("results") or []
    candidates = []
    for item in items:
        if not isinstance(item, dict):
            continue
        location = item.get("primary_location") if isinstance(item.get("primary_location"), dict) else {}
        source = location.get("source") if isinstance(location.get("source"), dict) else {}
        host_venue = item.get("host_venue") if isinstance(item.get("host_venue"), dict) else {}
        open_access = item.get("open_access") if isinstance(item.get("open_access"), dict) else {}
        candidates.append(
            _compact_dict(
                {
                    "title": item.get("display_name") or item.get("title"),
                    "authors": [
                        authorship.get("author", {}).get("display_name")
                        for authorship in item.get("authorships") or []
                        if isinstance(authorship, dict) and authorship.get("author")
                    ],
                    "year": item.get("publication_year"),
                    "venue": source.get("display_name") or host_venue.get("display_name"),
                    "doi": _as_text(item.get("doi")).replace("https://doi.org/", "") or None,
                    "url": location.get("landing_page_url") or item.get("doi"),
                    "abstract": _openalex_abstract(item),
                    "citation_count": item.get("cited_by_count"),
                    "open_access": open_access.get("is_oa"),
                    "pdf_url": location.get("pdf_url"),
                    "source": "openalex",
                    "source_query": query,
                }
            )
        )
    return candidates


def _normalize_arxiv_results(payload: str, *, query: str) -> list[dict[str, Any]]:
    root = ET.fromstring(payload)
    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    candidates = []
    for entry in root.findall("atom:entry", ns):
        title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
        url = (entry.findtext("atom:id", default="", namespaces=ns) or "").strip()
        published = entry.findtext("atom:published", default="", namespaces=ns) or ""
        doi = entry.findtext("arxiv:doi", default="", namespaces=ns) or None
        authors = [
            (author.findtext("atom:name", default="", namespaces=ns) or "").strip()
            for author in entry.findall("atom:author", ns)
        ]
        candidates.append(
            _compact_dict(
                {
                    "title": re.sub(r"\s+", " ", title),
                    "authors": [author for author in authors if author],
                    "year": int(published[:4]) if published[:4].isdigit() else None,
                    "venue": "arXiv",
                    "doi": doi,
                    "url": url,
                    "abstract": (entry.findtext("atom:summary", default="", namespaces=ns) or "").strip(),
                    "source": "arxiv",
                    "source_query": query,
                    "open_access": True,
                }
            )
        )
    return candidates


def _normalize_public_response(source: PublicMetadataSource, response_text: str, *, query: str) -> list[dict[str, Any]]:
    if source == "crossref":
        return _normalize_crossref_results(json.loads(response_text), query=query)
    if source == "openalex":
        return _normalize_openalex_results(json.loads(response_text), query=query)
    if source == "arxiv":
        return _normalize_arxiv_results(response_text, query=query)
    raise ValueError(f"Unsupported public metadata source: {source}")


def _search_query_strings(root: Path, extra_keywords: list[str] | None = None) -> list[str]:
    query_path = root / "literature" / "search_queries.yml"
    if query_path.exists():
        data = read_yaml(query_path)
        queries = [str(item.get("query")) for item in data.get("queries") or [] if item.get("query")]
        if extra_keywords:
            queries.extend(extra_keywords)
        return _unique(queries)
    project = _project_context(root)
    keywords = generate_literature_keywords(
        project_name=str(project.get("project_name", "")),
        research_direction=str(project.get("research_direction", "")),
        material_system=str(project.get("material_system", "")),
        experiment_type=str(project.get("experiment_type", "")),
        extra_keywords=extra_keywords,
    )
    return [item["query"] for item in build_search_queries(keywords)]


def search_public_literature_metadata(
    root: Path,
    *,
    sources: list[PublicMetadataSource] | None = None,
    max_results: int = 20,
    query_limit: int | None = 3,
    top_n: int | None = None,
    reference_year: int | None = None,
    extra_keywords: list[str] | None = None,
    searched_at: str | None = None,
    fetcher: Callable[[str, str], str] | None = None,
    page_limit: int = 1,
    delay_seconds: float = 0.0,
    resume: bool = False,
) -> dict[str, Any]:
    if max_results <= 0:
        raise ValueError("max_results must be positive")
    if query_limit is not None and query_limit <= 0:
        raise ValueError("query_limit must be positive when supplied")
    if page_limit <= 0:
        raise ValueError("page_limit must be positive")
    if delay_seconds < 0:
        raise ValueError("delay_seconds must be non-negative")
    selected_sources = sources or PUBLIC_METADATA_SOURCES
    unsupported = [source for source in selected_sources if source not in PUBLIC_METADATA_SOURCES]
    if unsupported:
        raise ValueError(f"Unsupported public metadata source(s): {', '.join(unsupported)}")

    literature_root = root / "literature"
    literature_root.mkdir(parents=True, exist_ok=True)
    project = _project_context(root)
    project_id = str(project.get("project_id", "unknown-project"))
    status_path = ensure_literature_status(root, project_id=project_id)
    searched_at = searched_at or EARecord.now_iso()
    queries = _search_query_strings(root, extra_keywords=extra_keywords)
    if query_limit is not None:
        queries = queries[:query_limit]
    fetch = fetcher or (lambda url, source: _public_fetch_text(url, source=source))

    candidate_manifest_path = literature_root / "public_search_candidates.yml"
    coverage_path = literature_root / "search_coverage.yml"
    state_path = _public_search_state_path(root)
    previous_state = read_yaml(state_path) if resume and state_path.exists() else {}
    progress: dict[str, Any] = dict(previous_state.get("progress") or {})
    state_entries: list[dict[str, Any]] = list(previous_state.get("state_entries") or [])
    request_count = _safe_int(previous_state.get("request_count"), len(state_entries))

    candidates: list[dict[str, Any]] = []
    coverage_entries: list[dict[str, Any]] = []
    if resume and candidate_manifest_path.exists():
        previous_manifest = read_yaml(candidate_manifest_path)
        candidates.extend(
            item for item in previous_manifest.get("candidates") or [] if isinstance(item, dict)
        )
    if resume and coverage_path.exists():
        previous_coverage = read_yaml(coverage_path)
        coverage_entries.extend(
            item for item in previous_coverage.get("coverage_entries") or [] if isinstance(item, dict)
        )
    if not state_entries and coverage_entries:
        state_entries.extend(coverage_entries)

    task_keys = []
    for source in selected_sources:
        for query in queries:
            task_key = _public_search_task_key(source, query)
            task_keys.append(task_key)
            progress.setdefault(
                task_key,
                {
                    "source": source,
                    "query": query,
                    "status": "not_started",
                    "next_cursor": None,
                    "next_offset": 0,
                    "next_page_index": 0,
                    "page_count": 0,
                    "candidate_count": 0,
                },
            )

    def active_progress() -> dict[str, Any]:
        return {key: progress[key] for key in task_keys if key in progress}

    def candidate_manifest() -> dict[str, Any]:
        return {
            "schema_version": "0.2",
            "project_id": project_id,
            "created_at": searched_at,
            "source_type": "public_metadata_search",
            "sources": selected_sources,
            "query_count": len(queries),
            "candidate_count": len(candidates),
            "search_state_ref": "literature/public_search_state.yml",
            "boundaries": [
                "Public metadata APIs only; no Zotero, browser profile, institution login, credentials, paywall access, DOI full-text resolution, or PDF download.",
                "Coverage is source-limited and query-limited; do not claim exhaustive web coverage.",
            ],
            "candidates": candidates,
        }

    def coverage_record() -> dict[str, Any]:
        return {
            "schema_version": "0.2",
            "project_id": project_id,
            "created_at": searched_at,
            "sources": selected_sources,
            "query_count": len(queries),
            "max_results_per_request": max_results,
            "page_limit_per_source_query": page_limit,
            "delay_seconds_between_requests": delay_seconds,
            "resume_enabled": resume,
            "request_count": request_count,
            "candidate_count": len(candidates),
            "search_state_ref": "literature/public_search_state.yml",
            "coverage_entries": coverage_entries,
            "known_limits": [
                "Source API availability, query syntax, indexing lag, and API rate limits can omit relevant literature.",
                "No source proves exhaustive web coverage.",
                "Full-text acquisition, Zotero use, browser assistance, and institution access remain separate user-confirmed workflows.",
            ],
        }

    def write_search_outputs() -> None:
        write_yaml(candidate_manifest_path, candidate_manifest())
        write_yaml(coverage_path, coverage_record())

    def write_state_snapshot() -> dict[str, Any]:
        current_progress = active_progress()
        snapshot = {
            "schema_version": "0.2",
            "project_id": project_id,
            "run_id": previous_state.get("run_id") or _public_search_run_id(searched_at),
            "created_at": previous_state.get("created_at") or searched_at,
            "updated_at": searched_at,
            "status": _public_search_state_status(current_progress),
            "sources": selected_sources,
            "query_count": len(queries),
            "max_results_per_request": max_results,
            "page_limit_per_source_query": page_limit,
            "delay_seconds_between_requests": delay_seconds,
            "resume_enabled": resume,
            "request_count": request_count,
            "candidate_count": len(candidates),
            "coverage_entry_count": len(coverage_entries),
            "output_artifacts": {
                "candidate_manifest": "literature/public_search_candidates.yml",
                "search_coverage": "literature/search_coverage.yml",
                "ranking": "literature/ranking.csv",
                "selected_items": "literature/selected_items.yml",
            },
            "progress": progress,
            "next_tasks": _public_search_next_tasks(current_progress),
            "state_entries": state_entries,
            "boundaries": [
                "Public metadata state tracks metadata search progress only.",
                "No Zotero, browser profile, institution login, credentials, paywall access, DOI full-text resolution, or PDF download is stored or executed here.",
            ],
        }
        write_yaml(state_path, snapshot)
        write_search_outputs()
        return snapshot

    request_count_this_run = 0
    for source in selected_sources:
        for query in queries:
            task_key = _public_search_task_key(source, query)
            task_state = progress[task_key]
            if resume and task_state.get("status") == "complete":
                continue
            cursor = str(task_state.get("next_cursor")) if resume and task_state.get("next_cursor") else None
            offset = _safe_int(task_state.get("next_offset"), 0) if resume else 0
            page_index = _safe_int(task_state.get("next_page_index"), 0) if resume else 0
            pages_requested = 0
            while pages_requested < page_limit:
                if delay_seconds and request_count_this_run:
                    time.sleep(delay_seconds)
                url = _public_search_url(source, query, max_results, cursor=cursor, offset=offset)
                entry: dict[str, Any] = _compact_dict(
                    {
                        "source": source,
                        "query": query,
                        "url": url,
                        "status": "not_started",
                        "page_index": page_index + 1,
                        "cursor": cursor if source in {"crossref", "openalex"} else None,
                        "offset": offset if source == "arxiv" else None,
                        "candidate_count": 0,
                    }
                )
                request_count_this_run += 1
                try:
                    response_text = fetch(url, source)
                    normalized = _normalize_public_response(source, response_text, query=query)
                    page_state = _public_next_page(
                        source,
                        response_text,
                        current_cursor=cursor,
                        current_offset=offset,
                        normalized_count=len(normalized),
                        max_results=max_results,
                    )
                except Exception as exc:  # noqa: BLE001 - coverage records should preserve source-level failures
                    request_count += 1
                    entry.update({"status": "error", "error": str(exc)})
                    coverage_entries.append(entry)
                    state_entries.append(entry.copy())
                    task_state.update(
                        {
                            "status": "error",
                            "last_error": str(exc),
                            "last_url": url,
                            "next_cursor": cursor,
                            "next_offset": offset,
                            "next_page_index": page_index,
                        }
                    )
                    write_state_snapshot()
                    break
                request_count += 1
                next_cursor = page_state.get("next_cursor")
                next_offset = page_state.get("next_offset")
                entry.update(
                    _compact_dict(
                        {
                            "status": "ok",
                            "candidate_count": len(normalized),
                            "next_cursor": next_cursor,
                            "next_offset": next_offset,
                            "has_next_page": page_state.get("has_next_page"),
                            "total_results": page_state.get("total_results"),
                        }
                    )
                )
                coverage_entries.append(entry)
                state_entries.append(entry.copy())
                candidates.extend(normalized)
                pages_requested += 1
                task_state["page_count"] = _safe_int(task_state.get("page_count"), 0) + 1
                task_state["candidate_count"] = _safe_int(task_state.get("candidate_count"), 0) + len(normalized)
                task_state["last_url"] = url
                task_state["last_candidate_count"] = len(normalized)
                if page_state.get("has_next_page"):
                    cursor = str(next_cursor) if next_cursor else None
                    offset = _safe_int(next_offset, offset)
                    page_index += 1
                    task_state.update(
                        {
                            "status": "in_progress",
                            "next_cursor": cursor,
                            "next_offset": offset,
                            "next_page_index": page_index,
                        }
                    )
                else:
                    task_state.update(
                        {
                            "status": "complete",
                            "next_cursor": None,
                            "next_offset": None,
                            "next_page_index": page_index + 1,
                        }
                    )
                write_state_snapshot()
                if not page_state.get("has_next_page"):
                    break

    search_state = write_state_snapshot()
    coverage = coverage_record()

    ranking = rank_literature_candidates(
        root,
        candidates_path=Path("literature/public_search_candidates.yml"),
        top_n=top_n,
        reference_year=reference_year,
        source_label="public_metadata_search",
        extra_keywords=extra_keywords,
        metadata_search_executed=True,
        ranked_at=searched_at,
    )
    status = read_yaml(status_path)
    search_status = str(search_state.get("status", "unknown"))
    status_update = {
        "status": "public_metadata_ranked_ready"
        if status.get("selected_top_n")
        else "public_metadata_ranked_awaiting_user_confirmation",
        "public_metadata_search_ref": "literature/public_search_candidates.yml",
        "search_coverage_ref": "literature/search_coverage.yml",
        "public_metadata_search_state_ref": "literature/public_search_state.yml",
        "public_metadata_search_status": search_status,
        "public_metadata_sources": selected_sources,
        "public_metadata_search_updated_at": searched_at,
        "public_metadata_search_request_count": request_count,
        "public_metadata_search_page_limit": page_limit,
        "public_metadata_search_resume_enabled": resume,
        "summary_for_origin_thread": (
            f"Public metadata search collected {len(candidates)} candidate record(s) from "
            f"{len(selected_sources)} source(s), {len(queries)} query/queries, and "
            f"{request_count} request(s); search state is {search_status}. "
            "No full-text acquisition, Zotero, browser, institution login, or PDF download was executed."
        ),
    }
    if search_status == "complete":
        status_update["public_metadata_search_completed_at"] = searched_at
    else:
        status.pop("public_metadata_search_completed_at", None)
    status.update(status_update)
    write_yaml(status_path, status)

    search_log = literature_root / "search_log.md"
    previous_log = search_log.read_text(encoding="utf-8") if search_log.exists() else "# Literature Search Log\n"
    log_lines = [
        previous_log.rstrip(),
        "",
        "## Public Metadata Search",
        "",
        f"- searched_at: {searched_at}",
        f"- sources: {', '.join(selected_sources)}",
        f"- query_count: {len(queries)}",
        f"- request_count: {request_count}",
        f"- page_limit_per_source_query: {page_limit}",
        f"- resume_enabled: {resume}",
        f"- candidate_count: {len(candidates)}",
        "- boundary: public metadata only; no full-text acquisition, Zotero, browser, institution login, or PDF download.",
        "- coverage: source-limited and query-limited; no exhaustive web coverage claim.",
    ]
    search_log.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    ranking["status"] = status
    return {
        "candidate_manifest_path": str(candidate_manifest_path),
        "coverage_path": str(coverage_path),
        "state_path": str(state_path),
        "ranking_path": ranking["ranking_path"],
        "selected_items_path": ranking["selected_items_path"],
        "candidate_count": len(candidates),
        "coverage": coverage,
        "search_state": search_state,
        "ranking": ranking,
        "status": status,
    }


def _item_citation(item: dict[str, Any]) -> str | None:
    citation = item.get("citation")
    if citation:
        return str(citation)
    title = item.get("title")
    if not title:
        return None
    authors = item.get("authors") or item.get("author") or []
    if isinstance(authors, str):
        author_text = authors
    elif isinstance(authors, list) and authors:
        author_text = f"{authors[0]} et al." if len(authors) > 1 else str(authors[0])
    else:
        author_text = "Unknown authors"
    venue = item.get("venue") or item.get("journal") or item.get("container_title")
    year = item.get("year") or item.get("publication_year")
    parts = [f"{author_text}.", f"{title}."]
    if venue and year:
        parts.append(f"{venue} ({year}).")
    elif venue:
        parts.append(f"{venue}.")
    elif year:
        parts.append(f"({year}).")
    return " ".join(parts)


def _item_authors(item: dict[str, Any]) -> list[str]:
    authors = item.get("authors") or item.get("author") or []
    if isinstance(authors, str):
        return [authors]
    if isinstance(authors, list):
        return [str(author) for author in authors]
    return []


def import_literature_acquisition_manifest(
    root: Path,
    *,
    manifest_path: Path,
    created_at: str | None = None,
) -> dict[str, Any]:
    literature_root = root / "literature"
    resolved_manifest = manifest_path if manifest_path.is_absolute() else root / manifest_path
    if not resolved_manifest.exists():
        raise FileNotFoundError(resolved_manifest)
    manifest = _load_manifest(resolved_manifest)
    status_path = literature_root / "deployment_status.yml"
    status = read_yaml(status_path) if status_path.exists() else {}
    project = _project_context(root)
    project_id = str(manifest.get("project_id") or status.get("project_id") or project.get("project_id", "unknown-project"))
    created_at = created_at or EARecord.now_iso()
    imported: list[dict[str, Any]] = []
    reused: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    manifest_items: list[dict[str, Any]] = []
    cache_items: list[dict[str, Any]] = []

    for index, item in enumerate(_manifest_items(manifest), start=1):
        citation = _item_citation(item)
        if not citation:
            skipped.append({"index": index, "reason": "missing_title_or_citation", "item": item})
            continue
        title = item.get("title")
        doi = item.get("doi")
        url = item.get("url") or item.get("article_url")
        local_path = item.get("local_path") or item.get("pdf_path")
        cache_path = item.get("cache_path") or item.get("fulltext_cache_path")
        duplicate = find_duplicate_reference(root, doi=doi, url=url, title=title, citation=citation)
        if duplicate:
            reference_id = duplicate["reference_id"]
            reused.append({"index": index, "reference_id": reference_id, "match": duplicate["match"]})
        else:
            reference_path = register_reference(
                root,
                project_id=project_id,
                citation=citation,
                title=str(title) if title else None,
                authors=_item_authors(item),
                year=item.get("year") or item.get("publication_year"),
                venue=item.get("venue") or item.get("journal") or item.get("container_title"),
                doi=str(doi) if doi else None,
                url=str(url) if url else None,
                local_path=str(local_path) if local_path else None,
                source_type="literature_library",
                notes=f"Imported from literature acquisition manifest `{resolved_manifest.name}`.",
                created_at=created_at,
            )
            reference_id = reference_path.stem
            imported.append({"index": index, "reference_id": reference_id, "path": str(reference_path)})
        manifest_record = {
            "reference_id": reference_id,
            "title": title,
            "doi": doi,
            "url": url,
            "year": item.get("year") or item.get("publication_year"),
            "venue": item.get("venue") or item.get("journal") or item.get("container_title"),
            "zotero_item_key": item.get("zotero_item_key") or item.get("item_key"),
            "zotero_attachment_key": item.get("zotero_attachment_key") or item.get("attachment_key"),
            "local_path": local_path,
            "cache_path": cache_path,
            "status": item.get("status") or item.get("acquisition_status"),
            "rank": item.get("rank") or item.get("top30_rank"),
        }
        manifest_items.append(_compact_dict(manifest_record))
        if local_path or cache_path or manifest_record.get("zotero_item_key"):
            cache_items.append(_compact_dict(manifest_record))

    library_manifest = {
        "schema_version": "0.2",
        "project_id": project_id,
        "source_manifest_ref": _project_relative(root, resolved_manifest),
        "imported_at": created_at,
        "item_count": len(manifest_items),
        "items": manifest_items,
    }
    cache_index = {
        "schema_version": "0.2",
        "project_id": project_id,
        "source_manifest_ref": _project_relative(root, resolved_manifest),
        "updated_at": created_at,
        "cached_count": sum(1 for item in cache_items if item.get("cache_path")),
        "items": cache_items,
    }
    write_yaml(literature_root / "library_manifest.yml", library_manifest)
    write_yaml(literature_root / "cache_index.yml", cache_index)

    downloaded_fulltext = manifest.get("downloaded_fulltext")
    if downloaded_fulltext is None:
        downloaded_fulltext = sum(1 for item in manifest_items if item.get("local_path"))
    cached_fulltext = manifest.get("cached_fulltext")
    if cached_fulltext is None:
        cached_fulltext = cache_index["cached_count"]
    update = {
        "schema_version": "0.2",
        "status": manifest.get("status") or "acquisition_manifest_imported",
        "candidate_count": manifest.get("candidate_count", len(manifest_items)),
        "deduped_count": manifest.get("deduped_count", len(manifest_items)),
        "downloaded_fulltext": downloaded_fulltext,
        "cached_fulltext": cached_fulltext,
        "needs_user_login": manifest.get("needs_user_login", []),
        "blocked_items": manifest.get("blocked_items", []),
        "summary_for_origin_thread": manifest.get(
            "summary_for_origin_thread",
            f"Imported {len(manifest_items)} literature item(s) from acquisition manifest.",
        ),
        "library_manifest_ref": "literature/library_manifest.yml",
        "cache_index_ref": "literature/cache_index.yml",
        "reference_import": {
            "imported_count": len(imported),
            "reused_count": len(reused),
            "skipped_count": len(skipped),
        },
    }
    update_path = literature_root / "acquisition_status_update.yml"
    write_yaml(update_path, update)
    sync = sync_literature_acquisition_status(root, update_path=Path("literature/acquisition_status_update.yml"), synced_at=created_at)
    return {
        "manifest_path": str(resolved_manifest),
        "library_manifest_path": str(literature_root / "library_manifest.yml"),
        "cache_index_path": str(literature_root / "cache_index.yml"),
        "status_update_path": str(update_path),
        "imported_count": len(imported),
        "reused_count": len(reused),
        "skipped_count": len(skipped),
        "imported": imported,
        "reused": reused,
        "skipped": skipped,
        "sync": sync,
    }


def sync_literature_acquisition_status(
    root: Path,
    *,
    update_path: Path | None = None,
    synced_at: str | None = None,
) -> dict[str, Any]:
    literature_root = root / "literature"
    status_path = literature_root / "deployment_status.yml"
    if not status_path.exists():
        raise FileNotFoundError(status_path)
    update_path = update_path or (literature_root / "acquisition_status_update.yml")
    update_path = update_path if update_path.is_absolute() else root / update_path
    update = read_yaml(update_path)
    status = read_yaml(status_path)
    for field in STATUS_UPDATE_FIELDS:
        if field in update:
            status[field] = update[field]
    status["last_acquisition_sync_at"] = synced_at or EARecord.now_iso()
    status["acquisition_status_update_ref"] = str(update_path.relative_to(root)) if update_path.is_relative_to(root) else str(update_path)
    if "status" not in update:
        status["status"] = "acquisition_in_progress"
    write_yaml(status_path, status)

    sync_path = literature_root / "origin_thread_sync.yml"
    sync_record = read_yaml(sync_path) if sync_path.exists() else {"schema_version": "0.2"}
    sync_record.update(
        {
            "project_id": status.get("project_id"),
            "handoff_id": sync_record.get("handoff_id") or status.get("acquisition_handoff_ref"),
            "last_synced_at": status["last_acquisition_sync_at"],
            "status": status.get("status"),
            "candidate_count": status.get("candidate_count", 0),
            "deduped_count": status.get("deduped_count", 0),
            "downloaded_fulltext": status.get("downloaded_fulltext", 0),
            "cached_fulltext": status.get("cached_fulltext", 0),
            "needs_user_login": status.get("needs_user_login", []),
            "blocked_items": status.get("blocked_items", []),
            "summary_for_origin_thread": status.get("summary_for_origin_thread"),
        }
    )
    write_yaml(sync_path, sync_record)
    return {
        "status_path": str(status_path),
        "sync_path": str(sync_path),
        "status": status,
        "sync": sync_record,
    }
