from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from ea.evaluation import run_project_evaluation
from ea.memory import project_working_memory_status
from ea.storage.files import read_markdown_record, read_yaml, write_yaml
from ea.storage.ids import next_id


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _safe_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return read_yaml(path)
    except Exception:
        return {}


def _safe_markdown_frontmatter(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        frontmatter, _ = read_markdown_record(path)
        return frontmatter
    except Exception:
        return {}


def _project_summary(root: Path) -> dict[str, Any]:
    frontmatter = _safe_markdown_frontmatter(root / "EA_PROJECT.md")
    return {
        "project_id": frontmatter.get("project_id"),
        "project_name": frontmatter.get("project_name"),
        "project_slug": frontmatter.get("project_slug"),
        "material_system": frontmatter.get("material_system"),
        "research_direction": frontmatter.get("research_direction"),
        "experiment_type": frontmatter.get("experiment_type"),
    }


def _recent_reports(root: Path, limit: int = 3) -> list[dict[str, Any]]:
    reports = (_safe_yaml(root / "reports" / "index.yml").get("reports") or {})
    items: list[dict[str, Any]] = []
    for report_id, record in reports.items():
        if not isinstance(record, dict):
            continue
        path = str(record.get("path") or f"reports/{report_id}.md")
        frontmatter = _safe_markdown_frontmatter(root / path)
        items.append(
            {
                "report_id": report_id,
                "path": path,
                "report_type": frontmatter.get("report_type") or record.get("report_type"),
                "status": frontmatter.get("status"),
                "created_at": frontmatter.get("created_at"),
            }
        )
    return sorted(items, key=lambda item: str(item.get("created_at") or item["path"]), reverse=True)[:limit]


def _figure_summary(root: Path) -> dict[str, Any]:
    figures = (_safe_yaml(root / "figures" / "index.yml").get("figures") or {})
    linked = [record for record in figures.values() if isinstance(record, dict) and record.get("report_id")]
    return {"figure_count": len(figures), "report_linked_count": len(linked)}


def _open_items(root: Path, limit: int = 5) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in sorted((root / "open-items").glob("*.yml")):
        record = _safe_yaml(path)
        status = str(record.get("status") or "open")
        if status in {"closed", "resolved", "done"}:
            continue
        items.append(
            {
                "type": record.get("item_type") or "open_item",
                "status": status,
                "priority": record.get("priority"),
                "description": record.get("description") or path.name,
            }
        )
    return items[:limit]


def _memory_review_items(root: Path) -> list[dict[str, Any]]:
    index = _safe_yaml(root / "memory" / "candidates" / "index.yml")
    candidates = index.get("candidates") or {}
    items: list[dict[str, Any]] = []
    for record in candidates.values():
        if not isinstance(record, dict):
            continue
        status = str(record.get("status") or "")
        if status in {"committed", "user_confirmed", "rejected"}:
            continue
        items.append(
            {
                "category": record.get("category") or "memory_candidate",
                "status": status or "needs_review",
                "confidence": record.get("confidence"),
            }
        )
    return items[:5]


def _literature_summary(root: Path) -> dict[str, Any]:
    status = _safe_yaml(root / "literature" / "deployment_status.yml")
    if status:
        return {
            "enabled": True,
            "status": status.get("status") or status.get("deployment_status") or "present",
            "path": "literature/deployment_status.yml",
        }
    has_decision = False
    for path in sorted((root / "open-items").glob("*.yml")):
        record = _safe_yaml(path)
        if "literature" in str(record.get("item_type") or "").lower():
            has_decision = True
            break
    return {
        "enabled": False,
        "status": "decision_needed" if has_decision else "not_configured",
        "path": None,
    }


def _next_actions(brief: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    if brief["evaluation"]["status"] == "fail":
        actions.append("Run `ea healthcheck` and fix blocking errors before new analysis or handoff.")
    if brief["needs_user_confirmation"]:
        actions.append("Ask the user to resolve the listed confirmations before committing memory or making stronger claims.")
    if not brief["key_outputs"]["reports"]:
        actions.append("Import raw data, confirm columns/parameters, process one method, then generate the first report.")
    else:
        actions.append("Share the latest report path and key result summary; keep audit details in project files unless requested.")
    if brief["literature"]["status"] in {"decision_needed", "not_configured"}:
        actions.append("Ask whether to deploy a local literature library before source-backed literature acquisition.")
    if brief["project_working_memory"]["stale"]:
        actions.append("Refresh compact project working memory before long handoff or project-management continuation.")
    actions.append("Before handoff, run `ea eval project` and `ea trace view --focus <report-or-record>`.")
    return actions


def render_project_brief_markdown(brief: dict[str, Any]) -> str:
    project = brief["project"]
    lines = [
        f"# EA Project Brief: {project.get('project_name') or project.get('project_id') or 'Unnamed project'}",
        "",
        "## Current Status",
        f"- Project: `{project.get('project_id') or 'unknown'}`",
        f"- Evaluation: `{brief['evaluation']['status']}` ({brief['evaluation']['error_count']} errors, {brief['evaluation']['warning_count']} warnings)",
        f"- Reports: {len(brief['key_outputs']['reports'])}",
        f"- Figures: {brief['key_outputs']['figures']['figure_count']} total, {brief['key_outputs']['figures']['report_linked_count']} linked to reports",
        f"- Literature: `{brief['literature']['status']}`",
        f"- Project working memory: `{'stale' if brief['project_working_memory']['stale'] else 'current'}`",
        "",
        "## Key Outputs",
    ]
    reports = brief["key_outputs"]["reports"]
    if reports:
        for report in reports:
            label = report.get("report_type") or "report"
            lines.append(f"- {label}: `{report['path']}`")
    else:
        lines.append("- No reports have been generated yet.")
    lines.extend(["", "## Needs User Confirmation"])
    if brief["needs_user_confirmation"]:
        for item in brief["needs_user_confirmation"]:
            label = item.get("type") or item.get("category") or "item"
            status = item.get("status") or "open"
            description = item.get("description") or item.get("confidence") or "Needs user decision."
            lines.append(f"- {label} (`{status}`): {description}")
    else:
        lines.append("- No open confirmation items were found in the brief scan.")
    lines.extend(["", "## Recommended Next Actions"])
    for action in brief["next_actions"]:
        lines.append(f"- {action}")
    lines.extend(
        [
            "",
            "## Audit Trail",
            f"- Detailed brief YAML: `{brief.get('yaml_path') or 'not written'}`",
            "- Full readiness gate: `ea eval project /path/to/ea-project`",
            "- Focused trace: `ea trace view /path/to/ea-project --focus <report-or-record>`",
            "",
            "This brief is user-facing by design. Detailed refs, hashes, provenance, review records, and trace graphs stay in local EA files unless the user asks for audit detail.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_project_brief(
    root: Path,
    *,
    write_report: bool = True,
    output_path: Path | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    created_at = created_at or _now_iso()
    evaluation = run_project_evaluation(root, write_report=False, created_at=created_at)
    brief: dict[str, Any] = {
        "schema_version": "0.2",
        "brief_type": "ea_agent_user_brief",
        "created_at": created_at,
        "workspace": str(root),
        "brief_id": None,
        "yaml_path": None,
        "markdown_path": None,
        "project": _project_summary(root),
        "evaluation": {
            "status": evaluation["status"],
            "error_count": evaluation["error_count"],
            "warning_count": evaluation["warning_count"],
        },
        "key_outputs": {
            "reports": _recent_reports(root),
            "figures": _figure_summary(root),
        },
        "literature": _literature_summary(root),
        "project_working_memory": project_working_memory_status(root),
        "needs_user_confirmation": [],
        "next_actions": [],
        "audit_commands": [
            "ea healthcheck /path/to/ea-project",
            "ea eval project /path/to/ea-project",
            "ea trace view /path/to/ea-project --focus <report-or-record>",
        ],
        "scope": {
            "user_visible_summary": True,
            "writes_raw_data": False,
            "runs_analysis": False,
            "commits_memory": False,
            "hides_low_level_refs_by_default": True,
        },
    }
    brief["needs_user_confirmation"] = _open_items(root) + _memory_review_items(root)
    brief["next_actions"] = _next_actions(brief)
    markdown = render_project_brief_markdown(brief)
    brief["markdown"] = markdown

    if write_report:
        brief_id = next_id(root, "brief", day=created_at[:10])
        target = output_path or root / "briefs" / f"{brief_id}.yml"
        if not target.is_absolute():
            target = root / target
        markdown_path = target.with_suffix(".md")
        brief["brief_id"] = brief_id
        brief["yaml_path"] = str(target)
        brief["markdown_path"] = str(markdown_path)
        markdown = render_project_brief_markdown(brief)
        brief["markdown"] = markdown
        write_yaml(target, {key: value for key, value in brief.items() if key != "markdown"})
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(markdown, encoding="utf-8")
    return brief
