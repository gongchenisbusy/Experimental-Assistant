from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
import shlex
from typing import Any, Callable

from ea.data_import import preview_import
from ea.migrations import project_format_status
from ea.project_state import aggregate_project_state
from ea.projects import initialize_project
from ea.storage.files import read_markdown_record
from ea.storage.files import read_yaml


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
    will_write = [
        "EA_PROJECT.md",
        "PROJECT_RULE_CARD.md",
        ".ea/project_config.yml",
        ".ea/project_format.yml",
        "memory/project-working-memory.md",
    ]
    if not confirmed:
        return {
            "schema_version": "1.0",
            "status": "needs_confirmation",
            "workspace": str(root),
            "values": values,
            "will_write": will_write,
            "literature": "not_used",
            "next_action": "Review the proposed values, edit any that matter now, then rerun with --yes.",
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
        "next_action": f"Run `ea journey {shlex.quote(str(root))}` to continue the guided first project.",
        "next_steps": [f"Run `ea journey {shlex.quote(str(root))}` to continue the guided first project."],
    }


def guided_first_journey(
    root: Path,
    *,
    source_path: Path | None = None,
    method: str | None = None,
) -> dict[str, Any]:
    """Inspect a first-project journey without mutating project or source files."""
    root = root.expanduser().resolve()
    source = source_path.expanduser().resolve() if source_path else None
    selected_method = (method or "").lower().replace("-", "_")
    progress = {
        "project": False,
        "import": False,
        "review": False,
        "analysis": False,
        "report": False,
        "html": False,
        "verified_bundle": False,
    }

    def result(
        stage: str,
        code: str,
        next_action: str | None,
        *,
        status: str = "ready",
        next_command: str | None = None,
        artifacts: dict[str, Any] | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": "1.0",
            "status": status,
            "read_only": True,
            "journey": "first_project_to_verified_report",
            "workspace": str(root),
            "stage": stage,
            "code": code,
            "progress": progress,
            "next_action": next_action,
        }
        if next_command:
            payload["next_command"] = next_command
        if artifacts:
            payload["artifacts"] = artifacts
        if details:
            payload["details"] = details
        return payload

    project_path = root / "EA_PROJECT.md"
    if not project_path.is_file():
        command = f"ea start {shlex.quote(str(root))}"
        return result(
            "project",
            "project_not_created",
            "Preview the project identity and safe defaults, then confirm creation.",
            status="needs_action",
            next_command=command,
        )
    progress["project"] = True

    raw_metadata = sorted(root.glob("raw/*/*/metadata.yml"))
    if not raw_metadata:
        if source is None:
            return result(
                "import",
                "source_required",
                "Choose the first local delimited-text source and rerun this journey with --source and --method.",
                status="needs_input",
            )
        if not source.is_file():
            return result(
                "import",
                "source_not_found",
                "Correct the source path; no project file was changed.",
                status="blocked",
                details={"source": str(source)},
            )
        if not selected_method:
            return result(
                "import",
                "method_required",
                "Specify the characterization method for this source with --method.",
                status="needs_input",
            )
        preview = preview_import(source)
        command = (
            f"ea import apply {shlex.quote(str(root))} {shlex.quote(str(source))} "
            f"--characterization-type {shlex.quote(selected_method)} "
            f"--preview-hash {preview['sha256']} --yes"
        )
        return result(
            "import",
            "import_ready_for_confirmation",
            "Review the detected encoding, columns, units, warnings, and source hash; apply only if they match the source.",
            status="needs_confirmation",
            next_command=command,
            details={
                "source_sha256": preview["sha256"],
                "encoding": preview["encoding"],
                "delimiter": preview["delimiter_name"],
                "columns": preview["columns"],
                "unit_proposals": preview["unit_proposals"],
                "warnings": preview["warnings"],
            },
        )
    progress["import"] = True
    if not selected_method:
        selected_method = raw_metadata[-1].parents[1].name.lower().replace("-", "_")

    reviews = sorted(root.glob("reviews/*.yml"))
    if not reviews:
        return result(
            "review",
            "review_required",
            "Use $ea to review the detected columns, units, context, and processing parameters before analysis.",
            status="needs_confirmation",
            artifacts={
                "raw_metadata": raw_metadata[-1].relative_to(root).as_posix()
            },
        )
    progress["review"] = True

    processed_metadata = sorted(root.glob(f"processed/**/{selected_method}_metadata.yml"))
    if not processed_metadata:
        return result(
            "analysis",
            "analysis_required",
            f"Use $ea to process the reviewed {selected_method} source; the selected parameters remain confirmation-gated.",
            status="needs_confirmation",
            artifacts={
                "raw_metadata": raw_metadata[-1].relative_to(root).as_posix(),
                "review_count": len(reviews),
            },
        )
    progress["analysis"] = True

    reports_path = root / "reports" / "index.yml"
    reports = (read_yaml(reports_path).get("reports") or {}) if reports_path.is_file() else {}
    if not reports:
        metadata_ref = processed_metadata[-1].relative_to(root).as_posix()
        command = (
            f"ea report {shlex.quote(str(root))} --method {shlex.quote(selected_method)} "
            f"--metadata {shlex.quote(metadata_ref)} --yes"
        )
        return result(
            "report",
            "report_required",
            "Generate a draft report from the reviewed processed metadata, then review its evidence and limitations.",
            status="needs_confirmation",
            next_command=command,
            artifacts={"processed_metadata": metadata_ref},
        )
    progress["report"] = True
    report_id = list(reports)[-1]
    report_ref = str(reports[report_id].get("path") or "")
    html_path = root / "exports" / "user-reports" / f"{report_id}.html"
    if not html_path.is_file():
        command = (
            f"ea export report-html {shlex.quote(str(root))} "
            f"--report-id {shlex.quote(report_id)}"
        )
        return result(
            "html",
            "html_export_required",
            "Render the reviewed draft as a user-readable HTML report.",
            status="needs_action",
            next_command=command,
            artifacts={"report": report_ref, "report_id": report_id},
        )
    progress["html"] = True

    bundle_dir = root / "exports" / "report-bundles" / report_id
    archive = root / "exports" / "report-bundles" / f"{report_id}.zip"
    if not (bundle_dir / "bundle_checksums.yml").is_file() or not archive.is_file():
        command = (
            f"ea export report-bundle {shlex.quote(str(root))} "
            f"--report-id {shlex.quote(report_id)} --zip"
        )
        return result(
            "verified_export",
            "verified_bundle_required",
            "Create the deterministic report bundle and checksum-protected archive.",
            status="needs_action",
            next_command=command,
            artifacts={
                "report": report_ref,
                "html": html_path.relative_to(root).as_posix(),
            },
        )

    from ea.exports import verify_archive_checksum, verify_bundle_checksums

    bundle_check = verify_bundle_checksums(bundle_dir)
    archive_check = verify_archive_checksum(archive)
    if bundle_check["status"] != "pass" or archive_check["status"] != "pass":
        return result(
            "verified_export",
            "bundle_verification_failed",
            "Inspect the reported checksum failures, restore the valid prior artifacts, then recreate the export.",
            status="blocked",
            artifacts={
                "bundle": bundle_dir.relative_to(root).as_posix(),
                "archive": archive.relative_to(root).as_posix(),
            },
            details={
                "bundle_failures": bundle_check["failures"],
                "archive_failures": archive_check["failures"],
            },
        )
    progress["verified_bundle"] = True
    return result(
        "complete",
        "journey_complete",
        None,
        status="completed",
        artifacts={
            "report": report_ref,
            "html": html_path.relative_to(root).as_posix(),
            "bundle": bundle_dir.relative_to(root).as_posix(),
            "archive": archive.relative_to(root).as_posix(),
            "archive_sha256": archive_check["actual_sha256"],
        },
        details={
            "bundle_files_checked": bundle_check["checked_count"],
            "archive_verification": "pass",
        },
    )


def build_project_dashboard(root: Path) -> dict[str, Any]:
    root = root.expanduser().resolve()
    state = aggregate_project_state(root)
    project = state["project"]
    config = state["config"]
    open_items = state["open_items"]
    incomplete = state["incomplete_operations"]
    reports = state["reports"]
    literature_config = config.get("literature", {})
    if state["literature_status"]:
        literature = state["literature_status"]
        literature_state = (
            literature.get("status")
            or literature.get("decision_status")
            or "configured"
        )
    elif literature_config.get("enabled"):
        literature_state = "required_missing"
    else:
        literature_state = "not_used"
    memory_path = root / "memory" / "project-working-memory.md"
    next_actions: list[str] = []
    if incomplete:
        next_actions.append(
            "Inspect failed or incomplete operation journals before starting another mutating workflow."
        )
    if open_items:
        next_actions.append("Review the highest-priority pending user decision.")
    if not reports:
        next_actions.append(
            "Preview and import the first data source, then inspect it with `ea analyze`."
        )
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
            {
                "path": record["path"],
                "type": record.get("item_type"),
                "priority": record.get("priority"),
                "description": record.get("description"),
            }
            for record in open_items[:5]
        ],
        "operations": {
            "incomplete_count": len(incomplete),
            "items": [
                {
                    "path": record["path"],
                    "operation": record.get("operation"),
                    "status": record.get("status"),
                }
                for record in incomplete[:5]
            ],
        },
        "latest_reports": [record["path"] for record in reports[:3]],
        "literature": {
            "status": literature_state,
            "enabled": bool(literature_config.get("enabled")),
        },
        "next_actions": next_actions[:3],
    }


def inspect_analysis_source(method: str, source_path: Path) -> dict[str, Any]:
    normalized = method.lower().replace("-", "_")
    inspectors: dict[str, Callable[[Path], Any]] = {}
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
            "raman": inspect_spectrum_file,
            "pl": inspect_pl_file,
            "xrd": inspect_xrd_file,
            "ftir": inspect_ftir_file,
            "uv_vis": inspect_uv_vis_file,
            "xps": inspect_xps_file,
            "electrochemistry": inspect_electrochemistry_file,
            "thermal": inspect_thermal_file,
        }
    )
    if normalized not in inspectors:
        raise ValueError(f"Unsupported analysis method: {method}")
    inspector = inspectors[normalized]
    result = inspector(source_path)
    payload = asdict(result) if is_dataclass(result) else result
    return {
        "schema_version": "1.0",
        "status": "ready_for_review",
        "read_only": True,
        "method": normalized,
        "review_boundary": "Review proposed columns, units, context, and parameters before processing; inspection is not a scientific conclusion.",
        "source": str(source_path),
        "inspection": payload,
        "next_steps": [
            "Review proposed columns, units, context, and parameters before running the method-specific process command."
        ],
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
            "will_write": [
                "reports/<report-id>.md",
                "reports/index.yml",
                "provenance/<provenance-id>.yml",
            ],
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
        "electrochemistry": (
            generate_electrochemistry_report,
            "electrochemistry_metadata_path",
        ),
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
        "review_boundary": "Review the draft report and its evidence, uncertainty, and provenance before export or durable memory use.",
        "report_path": str(report_path),
        "next_steps": ["Review the draft report before export or durable memory use."],
    }
