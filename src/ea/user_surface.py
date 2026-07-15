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
from ea.standards import slugify


def _project_slug(
    *,
    explicit: str | None,
    project_name: str,
    material_system: str,
    experiment_type: str,
    research_direction: str,
) -> str:
    """Choose a portable public ID even when the display name is non-Latin."""
    if explicit:
        return slugify(explicit)
    for candidate in (
        project_name,
        material_system,
        experiment_type,
        research_direction,
    ):
        slug = slugify(candidate)
        if slug != "project" and slug not in {
            "not-specified",
            "materials-characterization",
            "general-materials-research",
        }:
            return slug
    return "project"


def _journey_language(root: Path) -> str:
    config_path = root / ".ea" / "project_config.yml"
    config = read_yaml(config_path) if config_path.is_file() else {}
    language = str(config.get("report_language") or "zh").lower()
    return language if language in {"zh", "en"} else "zh"


def _journey_text(language: str, en: str, zh: str) -> str:
    return zh if language == "zh" else en


def _report_figure_contract(root: Path, report_ref: str) -> list[str]:
    """Return semantic artifact failures that checksums alone cannot detect."""
    failures: list[str] = []
    report_path = root / report_ref
    if not report_ref or not report_path.is_file():
        return ["report_file_missing"]
    frontmatter, _ = read_markdown_record(report_path)
    figure_ids = [str(value) for value in frontmatter.get("figure_ids") or []]
    if not figure_ids:
        return ["report_figure_ids_missing"]
    index_path = root / "figures" / "index.yml"
    if not index_path.is_file():
        return ["figure_index_missing"]
    figures = read_yaml(index_path).get("figures") or {}
    for figure_id in figure_ids:
        figure = figures.get(figure_id)
        if not isinstance(figure, dict):
            failures.append(f"figure_record_missing:{figure_id}")
            continue
        path = str(figure.get("path") or figure.get("base_path") or "")
        if not path or not (root / path).is_file():
            failures.append(f"figure_file_missing:{figure_id}")
        source_data = list(figure.get("source_data") or [])
        source_refs = [str(value) for value in figure.get("source_data_refs") or []]
        if not source_data and not source_refs:
            failures.append(f"figure_source_data_missing:{figure_id}")
            continue
        refs = [str(item.get("ref") or "") for item in source_data if isinstance(item, dict)]
        refs.extend(source_refs)
        for ref in refs:
            if not ref or not (root / ref).is_file():
                failures.append(f"figure_source_data_file_missing:{figure_id}:{ref}")
    return failures


def start_project(
    root: Path,
    *,
    project_name: str | None = None,
    research_direction: str | None = None,
    material_system: str | None = None,
    experiment_type: str | None = None,
    project_slug: str | None = None,
    report_language: str = "zh",
    confirmed: bool = False,
) -> dict[str, Any]:
    root = root.expanduser()
    name = project_name or root.name or "EA project"
    direction = research_direction or "general materials research"
    material = material_system or "not specified"
    experiment = experiment_type or "materials characterization"
    normalized_slug = _project_slug(
        explicit=project_slug,
        project_name=name,
        material_system=material,
        experiment_type=experiment,
        research_direction=direction,
    )
    values = {
        "project_name": name,
        "project_slug": normalized_slug,
        "research_direction": direction,
        "material_system": material,
        "experiment_type": experiment,
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
        next_action = _journey_text(
            report_language,
            "Review the proposed values, edit any that matter now, then rerun with --yes.",
            "核对建议值，修改需要调整的内容，然后使用 --yes 重新运行。",
        )
        return {
            "schema_version": "1.0",
            "status": "needs_confirmation",
            "workspace": str(root),
            "values": values,
            "will_write": will_write,
            "literature": "not_used",
            "next_action": next_action,
            "next_steps": [next_action],
        }
    if (root / "EA_PROJECT.md").exists():
        raise FileExistsError(f"EA project already exists: {root}")
    outputs = initialize_project(
        root,
        project_name=values["project_name"],
        research_direction=values["research_direction"],
        material_system=values["material_system"],
        experiment_type=values["experiment_type"],
        project_slug=values["project_slug"],
        default_language=values["report_language"],
    )
    next_action = _journey_text(
        report_language,
        f"Run `ea journey {shlex.quote(str(root))}` to continue the guided first project.",
        f"运行 `ea journey {shlex.quote(str(root))}` 继续第一个项目向导。",
    )
    return {
        "schema_version": "1.0",
        "status": "completed",
        "workspace": str(root),
        "values": values,
        "artifacts_written": {key: str(path) for key, path in outputs.items()},
        "next_action": next_action,
        "next_steps": [next_action],
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
    language = _journey_language(root)
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
            _journey_text(language, "Preview the project identity and safe defaults, then confirm creation.", "预览项目身份和安全默认值，然后确认创建。"),
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
                _journey_text(language, "Choose the first local delimited-text source and rerun this journey with --source and --method.", "选择第一个本地分隔文本数据源，并使用 --source 和 --method 重新运行本向导。"),
                status="needs_input",
            )
        if not source.is_file():
            return result(
                "import",
                "source_not_found",
                _journey_text(language, "Correct the source path; no project file was changed.", "请修正数据源路径；项目文件尚未发生更改。"),
                status="blocked",
                details={"source": str(source)},
            )
        if not selected_method:
            return result(
                "import",
                "method_required",
                _journey_text(language, "Specify the characterization method for this source with --method.", "请使用 --method 指定该数据源的表征方法。"),
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
            _journey_text(language, "Review the detected encoding, columns, units, warnings, and source hash; apply only if they match the source.", "核对检测到的编码、列、单位、警告和源文件哈希；确认与源文件一致后再导入。"),
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
            _journey_text(language, "Use $ea to review the detected columns, units, context, and processing parameters before analysis.", "分析前请使用 $ea 复核检测到的列、单位、实验背景和处理参数。"),
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
            _journey_text(language, f"Use $ea to process the reviewed {selected_method} source; the selected parameters remain confirmation-gated.", f"请使用 $ea 处理已经复核的 {selected_method} 数据源；所选参数仍需明确确认。"),
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
            _journey_text(language, "Generate a draft report from the reviewed processed metadata, then review its evidence and limitations.", "根据已复核的处理结果生成报告草稿，然后核对证据与限制。"),
            status="needs_confirmation",
            next_command=command,
            artifacts={"processed_metadata": metadata_ref},
        )
    progress["report"] = True
    report_id = list(reports)[-1]
    report_ref = str(reports[report_id].get("path") or "")
    figure_failures = _report_figure_contract(root, report_ref)
    if figure_failures:
        return result(
            "report",
            "report_figure_contract_failed",
            _journey_text(
                language,
                "Regenerate the analysis and report after restoring registered figures and figure-local source data.",
                "请恢复已登记图件及图件下方的源数据后，重新生成分析结果与报告。",
            ),
            status="blocked",
            artifacts={"report": report_ref, "report_id": report_id},
            details={"failures": figure_failures},
        )
    html_path = root / "exports" / "user-reports" / f"{report_id}.html"
    if not html_path.is_file():
        command = (
            f"ea export report-html {shlex.quote(str(root))} "
            f"--report-id {shlex.quote(report_id)}"
        )
        return result(
            "html",
            "html_export_required",
            _journey_text(language, "Render the reviewed draft as a user-readable HTML report.", "将已复核的报告草稿导出为便于阅读的 HTML 报告。"),
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
            _journey_text(language, "Create the deterministic report bundle and checksum-protected archive.", "创建确定性的报告包和受校验和保护的归档文件。"),
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
            _journey_text(language, "Inspect the reported checksum failures, restore the valid prior artifacts, then recreate the export.", "检查校验和失败项，恢复有效产物后重新导出。"),
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
