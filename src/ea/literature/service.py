from __future__ import annotations

from pathlib import Path
from typing import Literal

from ea.storage.files import read_yaml, write_yaml

ProjectScope = Literal["narrow", "ordinary", "review"]


def recommended_top_n(scope: ProjectScope) -> int | tuple[int, int]:
    if scope == "narrow":
        return 30
    if scope == "ordinary":
        return 50
    if scope == "review":
        return (100, 200)
    raise ValueError(f"Unsupported literature scope: {scope}")


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
