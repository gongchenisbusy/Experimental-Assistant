from __future__ import annotations

from pathlib import Path

from ea.config import build_project_config, write_project_config
from ea.literature import ensure_literature_status
from ea.schema import Project, ProjectRuleCard
from ea.standards import slugify, standard_project_id
from ea.storage.files import ensure_project_dirs, write_markdown_record
from ea.provenance import write_provenance_entry
from ea.review import write_review_record


def _slug(text: str) -> str:
    return slugify(text)


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
    created_at: str = "2026-06-02T00:00:00",
) -> dict[str, Path]:
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
    if enable_literature:
        ensure_literature_status(root, project_id=project_id)
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
    provenance_path = write_provenance_entry(
        root,
        workflow="project_initialization",
        inputs={"records": [], "files": []},
        outputs={
            "records": ["EA_PROJECT.md", "PROJECT_RULE_CARD.md", str(config_path.relative_to(root))],
            "files": [],
        },
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
    outputs = {"project": project_path, "rule_card": rule_card_path, "config": config_path}
    if enable_literature:
        outputs["literature_status"] = root / "literature" / "deployment_status.yml"
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
