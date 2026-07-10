from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Callable

from ea.identity import CAPABILITY_MATURITY
from ea.migrations import project_format_status
from ea.projects import initialize_project
from ea.storage.files import read_markdown_record, read_yaml


def start_project(
    root: Path,
    *,
    project_name: str | None = None,
    research_direction: str | None = None,
    material_system: str | None = None,
    experiment_type: str | None = None,
    report_language: str = "zh",
    confirmed: bool = False,
) -> dict[str, Any]:
    root = root.expanduser()
    name = project_name or root.name or "EA project"
    values = {
        "project_name": name,
        "research_direction": research_direction or "general materials research",
        "material_system": material_system or "not specified",
        "experiment_type": experiment_type or "materials characterization",
        "report_language": report_language,
    }
    will_write = ["EA_PROJECT.md", "PROJECT_RULE_CARD.md", ".ea/project_config.yml", ".ea/project_format.yml", "memory/project-working-memory.md"]
    if not confirmed:
        return {
            "schema_version": "1.0",
            "status": "needs_confirmation",
            "workspace": str(root),
            "values": values,
            "will_write": will_write,
            "literature": "not_used",
            "next_steps": ["Review the proposed values, edit any that matter now, then rerun with --yes."],
        }
    if (root / "EA_PROJECT.md").exists():
        raise FileExistsError(f"EA project already exists: {root}")
    outputs = initialize_project(
        root,
        project_name=values["project_name"],
        research_direction=values["research_direction"],
        material_system=values["material_system"],
        experiment_type=values["experiment_type"],
        default_language=values["report_language"],
    )
    return {
        "schema_version": "1.0",
        "status": "completed",
        "workspace": str(root),
        "values": values,
        "artifacts_written": {key: str(path) for key, path in outputs.items()},
        "next_steps": ["Run `ea status <workspace>`.", "Preview the first source with `ea import preview <file>`."],
    }


def _records(root: Path, pattern: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path in sorted(root.glob(pattern)):
        if not path.is_file():
            continue
        try:
            data = read_yaml(path)
        except (OSError, ValueError):
            continue
        results.append({"path": str(path.relative_to(root)), **data})
    return results


def build_project_dashboard(root: Path) -> dict[str, Any]:
    root = root.expanduser().resolve()
    project_path = root / "EA_PROJECT.md"
    if not project_path.is_file():
        raise FileNotFoundError(f"EA_PROJECT.md was not found: {project_path}")
    project, _ = read_markdown_record(project_path)
    config = read_yaml(root / ".ea" / "project_config.yml") if (root / ".ea" / "project_config.yml").is_file() else {}
    open_items = [record for record in _records(root, "open-items/*.yml") if record.get("status") not in {"closed", "resolved", "archived"}]
    operations = _records(root, ".ea/operations/*.yml")
    incomplete = [record for record in operations if record.get("status") in {"planned", "in_progress", "failed"}]
    reports = sorted((path for path in (root / "reports").glob("*.md") if path.is_file()), key=lambda path: path.stat().st_mtime, reverse=True)
    literature_config = config.get("literature", {})
    literature_status_path = root / "literature" / "deployment_status.yml"
    if literature_status_path.is_file():
        literature = read_yaml(literature_status_path)
        literature_state = literature.get("status") or literature.get("decision_status") or "configured"
    elif literature_config.get("enabled"):
        literature_state = "required_missing"
    else:
        literature_state = "not_used"
    memory_path = root / "memory" / "project-working-memory.md"
    next_actions: list[str] = []
    if incomplete:
        next_actions.append("Inspect failed or incomplete operation journals before starting another mutating workflow.")
    if open_items:
        next_actions.append("Review the highest-priority pending user decision.")
    if not reports:
        next_actions.append("Preview and import the first data source, then inspect it with `ea analyze`.")
    if not next_actions:
        next_actions.append("Continue from the latest reviewed result or report.")
    return {
        "schema_version": "1.0",
        "status": "attention" if incomplete else "ready",
        "read_only": True,
        "workspace": str(root),
        "project": {
            "project_id": project.get("project_id"),
            "project_name": project.get("project_name"),
            "stage": project.get("status"),
            "research_direction": project.get("research_direction"),
            "material_system": project.get("material_system"),
        },
        "project_format": project_format_status(root),
        "working_memory": {"exists": memory_path.is_file(), "path": str(memory_path)},
        "pending_user_decisions": [
            {"path": record["path"], "type": record.get("item_type"), "priority": record.get("priority"), "description": record.get("description")}
            for record in open_items[:5]
        ],
        "operations": {
            "incomplete_count": len(incomplete),
            "items": [{"path": record["path"], "operation": record.get("operation"), "status": record.get("status")} for record in incomplete[:5]],
        },
        "latest_reports": [str(path.relative_to(root)) for path in reports[:3]],
        "literature": {"status": literature_state, "enabled": bool(literature_config.get("enabled"))},
        "next_actions": next_actions[:3],
    }


def inspect_analysis_source(method: str, source_path: Path) -> dict[str, Any]:
    normalized = method.lower().replace("-", "_")
    inspectors: dict[str, tuple[Callable[[Path], Any], str]] = {}
    from ea.electrochemistry import inspect_electrochemistry_file
    from ea.ftir import inspect_ftir_file
    from ea.pl import inspect_pl_file
    from ea.raman import inspect_spectrum_file
    from ea.thermal import inspect_thermal_file
    from ea.uv_vis import inspect_uv_vis_file
    from ea.xps import inspect_xps_file
    from ea.xrd import inspect_xrd_file

    inspectors.update(
        {
            "raman": (inspect_spectrum_file, "beta"),
            "pl": (inspect_pl_file, "beta"),
            "xrd": (inspect_xrd_file, "beta"),
            "ftir": (inspect_ftir_file, "beta"),
            "uv_vis": (inspect_uv_vis_file, "beta"),
            "xps": (inspect_xps_file, "beta"),
            "electrochemistry": (inspect_electrochemistry_file, "beta"),
            "thermal": (inspect_thermal_file, "beta"),
        }
    )
    if normalized not in inspectors:
        raise ValueError(f"Unsupported analysis method: {method}")
    inspector, maturity = inspectors[normalized]
    result = inspector(source_path)
    payload = asdict(result) if is_dataclass(result) else result
    return {
        "schema_version": "1.0",
        "status": "ready_for_review",
        "read_only": True,
        "method": normalized,
        "maturity": maturity,
        "source": str(source_path),
        "inspection": payload,
        "next_steps": ["Review proposed columns, units, context, and parameters before running the method-specific process command."],
    }


def generate_user_report(
    root: Path,
    *,
    method: str,
    metadata_path: Path,
    sample_refs: list[str] | None = None,
    experiment_refs: list[str] | None = None,
    reference_ids: list[str] | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    normalized = method.lower().replace("-", "_")
    path = metadata_path if metadata_path.is_absolute() else root / metadata_path
    if not path.is_file():
        raise FileNotFoundError(path)
    project, _ = read_markdown_record(root / "EA_PROJECT.md")
    project_id = str(project.get("project_id") or "")
    if not project_id:
        raise KeyError("project_id")
    if not confirmed:
        return {
            "schema_version": "1.0",
            "status": "needs_confirmation",
            "method": normalized,
            "metadata_path": str(path),
            "will_write": ["reports/<report-id>.md", "reports/index.yml", "provenance/<provenance-id>.yml"],
        }
    from ea.reports import (
        generate_electrochemistry_report,
        generate_ftir_report,
        generate_pl_report,
        generate_raman_report,
        generate_thermal_report,
        generate_uv_vis_report,
        generate_xps_report,
        generate_xrd_report,
    )

    generators: dict[str, tuple[Callable[..., Path], str]] = {
        "raman": (generate_raman_report, "raman_metadata_path"),
        "pl": (generate_pl_report, "pl_metadata_path"),
        "xrd": (generate_xrd_report, "xrd_metadata_path"),
        "ftir": (generate_ftir_report, "ftir_metadata_path"),
        "uv_vis": (generate_uv_vis_report, "uv_vis_metadata_path"),
        "xps": (generate_xps_report, "xps_metadata_path"),
        "electrochemistry": (generate_electrochemistry_report, "electrochemistry_metadata_path"),
        "thermal": (generate_thermal_report, "thermal_metadata_path"),
    }
    if normalized not in generators:
        raise ValueError(f"Unsupported report method: {method}")
    generator, metadata_keyword = generators[normalized]
    report_path = generator(
        root,
        project_id=project_id,
        related_experiments=experiment_refs or [],
        related_samples=sample_refs or [],
        reference_ids=reference_ids or [],
        **{metadata_keyword: path},
    )
    return {
        "schema_version": "1.0",
        "status": "completed",
        "method": normalized,
        "maturity": "beta",
        "report_path": str(report_path),
        "next_steps": ["Review the draft report before export or durable memory use."],
    }
