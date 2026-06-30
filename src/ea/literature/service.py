from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any, Literal

from ea.schema.models import EARecord
from ea.storage.files import read_markdown_record, read_yaml, write_yaml

ProjectScope = Literal["narrow", "ordinary", "review"]
AccessMode = Literal["index_only", "open_access_only", "user_authenticated"]
HandoffMode = Literal["dedicated_thread", "manual_agent", "same_thread"]

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
    if status.get("status") not in {"confirmed_awaiting_acquisition", "acquisition_handoff_ready"}:
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
