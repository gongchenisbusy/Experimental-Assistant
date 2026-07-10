from __future__ import annotations

from pathlib import Path

from ea.config import build_project_config, write_project_config
from ea.literature import ensure_literature_status
from ea.memory import write_open_item, write_project_working_memory_skeleton
from ea.migrations import initialize_project_format
from ea.schema import Project, ProjectRuleCard
from ea.schema.models import EARecord
from ea.standards import slugify, standard_project_id
from ea.storage.files import ensure_project_dirs, read_yaml, write_markdown_record, write_yaml
from ea.provenance import write_provenance_entry
from ea.review import write_review_record


def _slug(text: str) -> str:
    return slugify(text)


def _literature_decision_description(project_id: str) -> str:
    return (
        f"Literature library is recommended for project `{project_id}` but was not enabled during initialization. "
        "Ask the user whether to deploy a local literature library before broad literature search or full-text acquisition. "
        "If yes, confirm scope (`narrow`, `ordinary`, or `review`), access mode (`index_only`, `open_access_only`, "
        "or `user_authenticated`), selected top N, and any user-supplied Zotero, browser, cache, proxy/VPN, or "
        "institution-access settings. Do not infer developer-machine paths or credentials. Suggested next command: "
        "`ea literature plan /path/to/ea-project --scope ordinary --access-mode open_access_only`."
    )


def _mark_literature_enabled_at_initialization(root: Path, *, project_id: str, created_at: str) -> Path:
    status_path = ensure_literature_status(root, project_id=project_id)
    status = read_yaml(status_path)
    status.update(
        {
            "decision_status": "enabled_at_initialization",
            "decision_recorded_at": created_at,
            "recommended_next_command": (
                "ea literature plan /path/to/ea-project --scope ordinary --access-mode open_access_only"
            ),
            "environment_settings_required": [
                "zotero_local_api_url_if_zotero_is_used",
                "zotero_collection_if_zotero_is_used",
                "literature_cache_root_if_user_wants_custom_cache",
                "browser_name_and_profile_if_browser_assist_is_used",
                "institution_access_note_if_user_authenticated_access_is_needed",
            ],
            "summary_for_origin_thread": (
                "Literature library was enabled during project initialization. Next ask the user to confirm "
                "search scope, access mode, selected_top_n, and any user-supplied Zotero/browser/cache/institution settings."
            ),
        }
    )
    write_yaml(status_path, status)
    return status_path


def initialize_project(
    root: Path,
    *,
    project_name: str,
    research_direction: str,
    material_system: str,
    experiment_type: str,
    project_slug: str | None = None,
    default_language: str = "zh",
    enable_literature: bool = False,
    enable_zotero: bool = False,
    literature_cache_root: str | None = None,
    zotero_local_api_url: str | None = None,
    zotero_collection: str | None = None,
    browser_assist_enabled: bool = False,
    browser_name: str | None = None,
    browser_profile: str | None = None,
    institution_access: str | None = None,
    created_at: str | None = None,
) -> dict[str, Path]:
    created_at = created_at or EARecord.now_iso()
    ensure_project_dirs(root)
    day = created_at[:10].replace("-", "")
    normalized_slug = _slug(project_slug or project_name)
    project_id = standard_project_id(normalized_slug) if project_slug else f"project-{day}-{normalized_slug}"
    project = Project(
        project_id=project_id,
        project_name=project_name,
        project_slug=normalized_slug,
        research_direction=research_direction,
        material_system=material_system,
        experiment_type=experiment_type,
        default_language=default_language,  # type: ignore[arg-type]
        created_at=created_at,
        updated_at=created_at,
        status="draft",
    )
    rule_card = ProjectRuleCard(
        rule_card_id=f"rule-card-{day}-001",
        project_id=project_id,
        research_direction=research_direction,
        material_system=material_system,
        experiment_type=experiment_type,
        default_report_language=default_language,  # type: ignore[arg-type]
        created_at=created_at,
        updated_at=created_at,
    )
    config = build_project_config(
        project_slug=normalized_slug,
        report_language=default_language,
        enable_literature=enable_literature,
        enable_zotero=enable_zotero,
        literature_cache_root=literature_cache_root,
        zotero_local_api_url=zotero_local_api_url,
        zotero_collection=zotero_collection,
        browser_assist_enabled=browser_assist_enabled,
        browser_name=browser_name,
        browser_profile=browser_profile,
        institution_access=institution_access,
    )
    config_path = write_project_config(root, config)
    project_format_path = initialize_project_format(root, created_at=created_at)
    literature_status_path: Path | None = None
    literature_decision_path: Path | None = None
    if enable_literature:
        literature_status_path = _mark_literature_enabled_at_initialization(
            root,
            project_id=project_id,
            created_at=created_at,
        )
    else:
        literature_decision_path = write_open_item(
            root,
            item_type="literature_library_decision",
            description=_literature_decision_description(project_id),
            related_records=["EA_PROJECT.md", ".ea/project_config.yml"],
            priority="medium",
            source_refs=["EA_PROJECT.md"],
            created_at=created_at,
        )
    project_path = write_markdown_record(
        root / "EA_PROJECT.md",
        project.model_dump(exclude_none=True),
        "# EA Project\n\nThis project record is review-gated.",
    )
    rule_card_path = write_markdown_record(
        root / "PROJECT_RULE_CARD.md",
        rule_card.model_dump(exclude_none=True),
        "# Project Rule Card\n\nKey rules require item-by-item user confirmation.",
    )
    output_records = [
        "EA_PROJECT.md",
        "PROJECT_RULE_CARD.md",
        config_path.relative_to(root).as_posix(),
        project_format_path.relative_to(root).as_posix(),
    ]
    if literature_status_path:
        output_records.append(literature_status_path.relative_to(root).as_posix())
    if literature_decision_path:
        output_records.append(literature_decision_path.relative_to(root).as_posix())
    working_memory_path = write_project_working_memory_skeleton(
        root,
        project_id=project_id,
        project_name=project_name,
        material_system=material_system,
        current_stage="initialized",
        created_at=created_at,
    )
    output_records.append(working_memory_path.relative_to(root).as_posix())
    provenance_path = write_provenance_entry(
        root,
        workflow="project_initialization",
        inputs={"records": [], "files": []},
        outputs={"records": output_records, "files": []},
        parameters={
            "project_name": project_name,
            "material_system": material_system,
            "status": "draft_until_user_review",
            "project_slug": normalized_slug,
            "public_initialization": "developer_machine_defaults_disabled",
        },
        created_at=created_at,
    )
    project_frontmatter = project.model_dump(exclude_none=True)
    project_frontmatter["provenance_refs"] = [provenance_path.stem]
    write_markdown_record(
        project_path,
        project_frontmatter,
        "# EA Project\n\nThis project record is review-gated.",
    )
    outputs = {
        "project": project_path,
        "rule_card": rule_card_path,
        "config": config_path,
        "project_format": project_format_path,
        "project_working_memory": working_memory_path,
    }
    if literature_status_path:
        outputs["literature_status"] = literature_status_path
    if literature_decision_path:
        outputs["literature_decision_open_item"] = literature_decision_path
    return outputs


def confirm_rule_card_item(
    root: Path,
    *,
    rule_key: str,
    reviewed_content: str,
    user_response: str,
    reviewed_at: str | None = None,
) -> Path:
    review_path = write_review_record(
        root,
        target_type="project_rule_card_item",
        target_ref=f"PROJECT_RULE_CARD.md#{rule_key}",
        user_response=user_response,
        reviewed_content=reviewed_content,
        reviewed_at=reviewed_at,
    )
    write_provenance_entry(
        root,
        workflow="project_rule_card_update",
        inputs={"records": ["PROJECT_RULE_CARD.md"], "files": []},
        outputs={"records": [f"PROJECT_RULE_CARD.md#{rule_key}"], "files": []},
        parameters={"rule_key": rule_key, "review_status": "recorded"},
        review_refs=[review_path.stem],
        created_at=reviewed_at,
    )
    return review_path
