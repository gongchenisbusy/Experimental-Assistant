from __future__ import annotations

import csv
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable, Literal

from ea.schema.models import EARecord
from ea.references.service import find_duplicate_reference, register_reference
from ea.storage.files import read_markdown_record, read_yaml, write_yaml

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
]


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
            "Journal impact factors must come from user-provided or otherwise verified sources.",
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
            notes = "Ranked from supplied candidate metadata; venue authority uses supplied fields or conservative text heuristics."
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
                    "Venue authority uses supplied metadata or conservative text heuristics; it is not automatic impact-factor lookup.",
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


def _public_search_url(source: PublicMetadataSource, query: str, max_results: int) -> str:
    if source == "crossref":
        return "https://api.crossref.org/works?" + urllib.parse.urlencode(
            {"query.bibliographic": query, "rows": max_results}
        )
    if source == "openalex":
        return "https://api.openalex.org/works?" + urllib.parse.urlencode({"search": query, "per-page": max_results})
    if source == "arxiv":
        return "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
            {"search_query": f'all:"{query}"', "start": 0, "max_results": max_results}
        )
    raise ValueError(f"Unsupported public metadata source: {source}")


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
) -> dict[str, Any]:
    if max_results <= 0:
        raise ValueError("max_results must be positive")
    if query_limit is not None and query_limit <= 0:
        raise ValueError("query_limit must be positive when supplied")
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

    candidates: list[dict[str, Any]] = []
    coverage_entries: list[dict[str, Any]] = []
    for source in selected_sources:
        for query in queries:
            url = _public_search_url(source, query, max_results)
            entry: dict[str, Any] = {
                "source": source,
                "query": query,
                "url": url,
                "status": "not_started",
                "candidate_count": 0,
            }
            try:
                response_text = fetch(url, source)
                normalized = _normalize_public_response(source, response_text, query=query)
            except Exception as exc:  # noqa: BLE001 - coverage records should preserve source-level failures
                entry.update({"status": "error", "error": str(exc)})
                coverage_entries.append(entry)
                continue
            entry.update({"status": "ok", "candidate_count": len(normalized)})
            coverage_entries.append(entry)
            candidates.extend(normalized)

    candidate_manifest_path = literature_root / "public_search_candidates.yml"
    coverage_path = literature_root / "search_coverage.yml"
    candidate_manifest = {
        "schema_version": "0.2",
        "project_id": project_id,
        "created_at": searched_at,
        "source_type": "public_metadata_search",
        "sources": selected_sources,
        "query_count": len(queries),
        "candidate_count": len(candidates),
        "boundaries": [
            "Public metadata APIs only; no Zotero, browser profile, institution login, credentials, paywall access, DOI full-text resolution, or PDF download.",
            "Coverage is source-limited and query-limited; do not claim exhaustive web coverage.",
        ],
        "candidates": candidates,
    }
    coverage = {
        "schema_version": "0.2",
        "project_id": project_id,
        "created_at": searched_at,
        "sources": selected_sources,
        "query_count": len(queries),
        "max_results_per_query": max_results,
        "candidate_count": len(candidates),
        "coverage_entries": coverage_entries,
        "known_limits": [
            "Source API availability, query syntax, indexing lag, and API rate limits can omit relevant literature.",
            "No source proves exhaustive web coverage.",
            "Full-text acquisition, Zotero use, browser assistance, and institution access remain separate user-confirmed workflows.",
        ],
    }
    write_yaml(candidate_manifest_path, candidate_manifest)
    write_yaml(coverage_path, coverage)

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
    status.update(
        {
            "status": "public_metadata_ranked_ready"
            if status.get("selected_top_n")
            else "public_metadata_ranked_awaiting_user_confirmation",
            "public_metadata_search_ref": "literature/public_search_candidates.yml",
            "search_coverage_ref": "literature/search_coverage.yml",
            "public_metadata_sources": selected_sources,
            "public_metadata_search_completed_at": searched_at,
            "summary_for_origin_thread": (
                f"Public metadata search collected {len(candidates)} candidate record(s) from "
                f"{len(selected_sources)} source(s) and {len(queries)} query/queries. "
                "No full-text acquisition, Zotero, browser, institution login, or PDF download was executed."
            ),
        }
    )
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
        f"- candidate_count: {len(candidates)}",
        "- boundary: public metadata only; no full-text acquisition, Zotero, browser, institution login, or PDF download.",
        "- coverage: source-limited and query-limited; no exhaustive web coverage claim.",
    ]
    search_log.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    ranking["status"] = status
    return {
        "candidate_manifest_path": str(candidate_manifest_path),
        "coverage_path": str(coverage_path),
        "ranking_path": ranking["ranking_path"],
        "selected_items_path": ranking["selected_items_path"],
        "candidate_count": len(candidates),
        "coverage": coverage,
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
