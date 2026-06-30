from __future__ import annotations

import re
from pathlib import Path

from ea.schema import Project, ProjectRuleCard
from ea.storage.files import ensure_project_dirs, write_markdown_record
from ea.provenance import write_provenance_entry
from ea.review import write_review_record


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or "project"


def initialize_project(
    root: Path,
    *,
    project_name: str,
    research_direction: str,
    material_system: str,
    experiment_type: str,
    created_at: str = "2026-06-02T00:00:00",
) -> dict[str, Path]:
    ensure_project_dirs(root)
    day = created_at[:10].replace("-", "")
    project_id = f"project-{day}-{_slug(project_name)}"
    project = Project(
        project_id=project_id,
        project_name=project_name,
        research_direction=research_direction,
        material_system=material_system,
        experiment_type=experiment_type,
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
        created_at=created_at,
        updated_at=created_at,
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
    provenance_path = write_provenance_entry(
        root,
        workflow="project_initialization",
        inputs={"records": [], "files": []},
        outputs={"records": ["EA_PROJECT.md", "PROJECT_RULE_CARD.md"], "files": []},
        parameters={
            "project_name": project_name,
            "material_system": material_system,
            "status": "draft_until_user_review",
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
    return {"project": project_path, "rule_card": rule_card_path}


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
