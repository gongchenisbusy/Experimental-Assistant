from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from ea.evaluation import run_project_evaluation
from ea.memory import project_working_memory_status
from ea.project_state import aggregate_project_state
from ea.storage.files import read_yaml, write_yaml
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


EVIDENCE_GATE_STATUSES = {"supported", "partial", "blocked", "unknown"}


def _safe_project_ref(
    root: Path, value: Any, *, require_exists: bool = False
) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    parsed = urlsplit(text)
    if (
        parsed.scheme in {"http", "https"}
        and parsed.netloc
        and not parsed.username
        and not parsed.password
    ):
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    path = Path(text)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(
            "Project refs must be project-relative paths or explicit public HTTP(S) URLs."
        )
    resolved = (root / path).resolve()
    if root.resolve() not in resolved.parents and resolved != root.resolve():
        raise ValueError("Project ref escapes the project root.")
    if require_exists and not resolved.exists():
        raise FileNotFoundError(resolved)
    return path.as_posix()


def validate_decision_summary(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    current_question = str(payload.get("current_question") or "").strip()
    if not current_question:
        raise ValueError("decision summary requires current_question")
    project_home = _safe_project_ref(
        root, payload.get("project_home"), require_exists=True
    )
    gates: list[dict[str, Any]] = []
    for index, source in enumerate(payload.get("evidence_gates") or [], start=1):
        if not isinstance(source, dict):
            raise ValueError("evidence_gates entries must be objects")
        status = str(source.get("status") or "unknown").lower()
        if status not in EVIDENCE_GATE_STATUSES:
            raise ValueError(f"unsupported evidence gate status: {status}")
        evidence_ref = _safe_project_ref(
            root, source.get("evidence_ref"), require_exists=status == "supported"
        )
        gates.append(
            {
                "gate_id": str(source.get("gate_id") or f"gate-{index:02d}"),
                "label": str(
                    source.get("label")
                    or source.get("gate_id")
                    or f"Evidence gate {index}"
                ),
                "status": status,
                "evidence_ref": evidence_ref,
                "blocking_reason": str(source.get("blocking_reason") or "").strip()
                or None,
                "next_step": str(source.get("next_step") or "").strip() or None,
            }
        )
    actions: list[dict[str, Any]] = []
    for index, source in enumerate(payload.get("actions") or [], start=1):
        if not isinstance(source, dict):
            raise ValueError("actions entries must be objects")
        priority = str(source.get("priority") or "P1").upper()
        if priority not in {"P0", "P1"}:
            raise ValueError("decision actions must use P0 or P1")
        action = str(source.get("action") or source.get("description") or "").strip()
        if not action:
            raise ValueError("decision action text is required")
        actions.append(
            {
                "action_id": str(source.get("action_id") or f"action-{index:02d}"),
                "priority": priority,
                "action": action,
                "evidence_gate_ref": source.get("evidence_gate_ref"),
            }
        )
    actions.sort(key=lambda item: (item["priority"] != "P0", item["action_id"]))
    return {
        "schema_version": "1.0",
        "current_question": current_question,
        "project_home": project_home,
        "evidence_gates": gates,
        "actions": actions,
        "review_refs": [
            ref
            for value in payload.get("review_refs") or []
            if (ref := _safe_project_ref(root, value))
        ],
        "updated_at": str(payload.get("updated_at") or _now_iso()),
    }


def set_decision_summary(
    root: Path,
    *,
    input_path: Path,
    confirmed: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    source = input_path if input_path.is_absolute() else root / input_path
    payload = read_yaml(source)
    summary = validate_decision_summary(root, payload)
    target = root / ".ea" / "decision_summary.yml"
    if not confirmed:
        try:
            source_ref = source.resolve().relative_to(root).as_posix()
        except ValueError:
            source_ref = source.name
        return {
            "schema_version": "1.0",
            "status": "needs_confirmation",
            "source_ref": source_ref,
            "will_write": ".ea/decision_summary.yml",
            "summary": summary,
        }
    write_yaml(target, summary)
    return {
        "schema_version": "1.0",
        "status": "completed",
        "decision_summary_ref": ".ea/decision_summary.yml",
        "summary": summary,
    }


def _decision_state(root: Path, project: dict[str, Any]) -> dict[str, Any]:
    path = root / ".ea" / "decision_summary.yml"
    if not path.is_file():
        return {
            "status": "not_configured",
            "current_question": project.get("research_direction") or "unknown",
            "project_home": None,
            "evidence_gates": [],
            "actions": [],
            "blocked_gate": None,
            "top_action": None,
            "decision_summary_ref": None,
        }
    try:
        summary = validate_decision_summary(root, read_yaml(path))
    except (OSError, ValueError) as exc:
        return {
            "status": "invalid",
            "current_question": project.get("research_direction") or "unknown",
            "project_home": None,
            "evidence_gates": [],
            "actions": [],
            "blocked_gate": {
                "label": "decision summary",
                "status": "blocked",
                "blocking_reason": str(exc),
            },
            "top_action": "Repair `.ea/decision_summary.yml` with `ea brief decision-set`.",
            "decision_summary_ref": ".ea/decision_summary.yml",
        }
    blocked = next(
        (gate for gate in summary["evidence_gates"] if gate["status"] == "blocked"),
        None,
    )
    return {
        **summary,
        "status": "configured",
        "blocked_gate": blocked,
        "top_action": summary["actions"][0]["action"] if summary["actions"] else None,
        "decision_summary_ref": ".ea/decision_summary.yml",
    }


def _project_summary(state: dict[str, Any]) -> dict[str, Any]:
    frontmatter = state["project"]
    return {
        "project_id": frontmatter.get("project_id"),
        "project_name": frontmatter.get("project_name"),
        "project_slug": frontmatter.get("project_slug"),
        "material_system": frontmatter.get("material_system"),
        "research_direction": frontmatter.get("research_direction"),
        "experiment_type": frontmatter.get("experiment_type"),
    }


def _recent_reports(state: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    return list(state["reports"][:limit])


def _figure_summary(root: Path) -> dict[str, Any]:
    figures = _safe_yaml(root / "figures" / "index.yml").get("figures") or {}
    linked = [
        record
        for record in figures.values()
        if isinstance(record, dict) and record.get("report_id")
    ]
    return {"figure_count": len(figures), "report_linked_count": len(linked)}


def _open_items(state: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for record in state["open_items"]:
        status = str(record.get("status") or "open")
        items.append(
            {
                "type": record.get("item_type") or "open_item",
                "status": status,
                "priority": record.get("priority"),
                "description": record.get("description")
                or Path(str(record.get("path") or "open-item")).name,
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


def _literature_summary(state: dict[str, Any]) -> dict[str, Any]:
    status = state["literature_status"]
    external_state = state["external_acquisition"]
    external_summary = external_state.get("summary") or {}
    external_ready = int(external_summary.get("ready_count") or 0)
    external_blocked = int(external_summary.get("blocked_count") or 0)
    if status:
        return {
            "enabled": True,
            "status": status.get("status")
            or status.get("deployment_status")
            or "present",
            "path": "literature/deployment_status.yml",
            "external_cache_used": bool(external_ready),
            "external_ready_count": external_ready,
            "external_blocked_count": external_blocked,
        }
    if external_ready:
        return {
            "enabled": False,
            "status": "external_cache_used_with_attention"
            if external_blocked
            else "external_cache_used",
            "path": "literature/external_acquisition_state.yml",
            "external_cache_used": True,
            "external_ready_count": external_ready,
            "external_blocked_count": external_blocked,
        }
    has_decision = False
    for record in state["open_items"]:
        if "literature" in str(record.get("item_type") or "").lower():
            has_decision = True
            break
    return {
        "enabled": False,
        "status": "decision_needed" if has_decision else "not_configured",
        "path": None,
        "external_cache_used": False,
        "external_ready_count": 0,
        "external_blocked_count": 0,
    }


def _next_actions(brief: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    actions.extend(item["action"] for item in brief["decision"]["actions"][:3])
    if brief["decision"]["blocked_gate"] and brief["decision"]["blocked_gate"].get(
        "next_step"
    ):
        actions.append(str(brief["decision"]["blocked_gate"]["next_step"]))
    if brief["evaluation"]["status"] == "fail":
        actions.append(
            "Run `ea healthcheck` and fix blocking errors before new analysis or handoff."
        )
    if brief["needs_user_confirmation"]:
        actions.append(
            "Ask the user to resolve the listed confirmations before committing memory or making stronger claims."
        )
    if not brief["key_outputs"]["reports"]:
        actions.append(
            "Import raw data, confirm columns/parameters, process one method, then generate the first report."
        )
    else:
        actions.append(
            "Share the latest report path and key result summary; keep audit details in project files unless requested."
        )
    if brief["literature"]["status"] in {"decision_needed", "not_configured"}:
        actions.append(
            "Ask whether to deploy a local literature library before source-backed literature acquisition."
        )
    if brief["project_working_memory"]["stale"]:
        actions.append(
            "Refresh compact project working memory before long handoff or project-management continuation."
        )
    actions.append(
        "Before handoff, run `ea eval project` and `ea trace view --focus <report-or-record>`."
    )
    return actions


def render_project_brief_markdown(brief: dict[str, Any]) -> str:
    project = brief["project"]
    decision = brief["decision"]
    blocked = decision.get("blocked_gate") or {}
    latest_report = (brief["key_outputs"]["reports"] or [{}])[0].get(
        "path"
    ) or "not_available"
    lines = [
        f"# EA Project Brief: {project.get('project_name') or project.get('project_id') or 'Unnamed project'}",
        "",
        "## Decision Snapshot",
        f"- Current question: {decision.get('current_question') or 'unknown'}",
        f"- Blocked evidence gate: {blocked.get('label') or 'none'} (`{blocked.get('status') or 'not_blocked'}`)",
        f"- Top action: {decision.get('top_action') or 'Review the project evaluation and choose the next evidence-producing step.'}",
        f"- Project home: `{decision.get('project_home') or 'not_configured'}`",
        f"- Latest report: `{latest_report}`",
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
            description = (
                item.get("description")
                or item.get("confidence")
                or "Needs user decision."
            )
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
    state = aggregate_project_state(root)
    evaluation = run_project_evaluation(root, write_report=False, created_at=created_at)
    project = _project_summary(state)
    brief: dict[str, Any] = {
        "schema_version": "0.2",
        "brief_type": "ea_agent_user_brief",
        "created_at": created_at,
        "workspace": ".",
        "brief_id": None,
        "yaml_path": None,
        "markdown_path": None,
        "project": project,
        "decision": _decision_state(root, project),
        "evaluation": {
            "status": evaluation["status"],
            "error_count": evaluation["error_count"],
            "warning_count": evaluation["warning_count"],
        },
        "key_outputs": {
            "reports": _recent_reports(state),
            "figures": _figure_summary(root),
        },
        "literature": _literature_summary(state),
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
    brief["needs_user_confirmation"] = _open_items(state) + _memory_review_items(root)
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
        write_yaml(
            target, {key: value for key, value in brief.items() if key != "markdown"}
        )
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(markdown, encoding="utf-8")
    return brief
