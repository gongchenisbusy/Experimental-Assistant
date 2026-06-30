from __future__ import annotations

import argparse
import json
from pathlib import Path

from ea.config import doctor_project_config
from ea.figures import lookup_figure
from ea.healthcheck import run_healthcheck
from ea.image_data import create_image_analysis_record, generate_image_analysis_report
from ea.literature import (
    confirm_literature_selection,
    ensure_literature_status,
    plan_literature_deployment,
    prepare_literature_acquisition_handoff,
    sync_literature_acquisition_status,
)
from ea.projects.service import initialize_project
from ea.skills import register_skill_manifest, run_skill_dry_run, validate_skill_manifest
from ea.storage.files import read_markdown_record


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ea")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="initialize a local EA project workspace (v0.1-compatible alias)")
    init.add_argument("workspace", type=Path)
    init.add_argument("--name", required=True)
    init.add_argument("--direction", required=True)
    init.add_argument("--material", required=True)
    init.add_argument("--experiment-type", required=True)

    init_project = sub.add_parser("init-project", help="initialize a public-user EA v0.2 project workspace")
    init_project.add_argument("workspace", type=Path)
    init_project.add_argument("--name", required=True)
    init_project.add_argument("--slug", required=True)
    init_project.add_argument("--direction", required=True)
    init_project.add_argument("--material", required=True)
    init_project.add_argument("--experiment-type", required=True)
    init_project.add_argument("--report-language", choices=["zh", "en"], default="zh")
    init_project.add_argument("--enable-literature", action="store_true")
    init_project.add_argument("--enable-zotero", action="store_true")
    init_project.add_argument("--literature-cache-root")
    init_project.add_argument("--zotero-local-api-url")
    init_project.add_argument("--zotero-collection")
    init_project.add_argument("--browser-assist", action="store_true")
    init_project.add_argument("--browser-name")
    init_project.add_argument("--browser-profile")
    init_project.add_argument("--institution-access")

    status = sub.add_parser("status", help="summarize an EA project workspace")
    status.add_argument("workspace", type=Path)

    healthcheck = sub.add_parser("healthcheck", help="audit EA project config, provenance, raw files, reports, and figures")
    healthcheck.add_argument("workspace", type=Path)

    config = sub.add_parser("config", help="EA configuration helpers")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    doctor = config_sub.add_parser("doctor", help="check project config for public-release portability")
    doctor.add_argument("workspace", type=Path)

    literature = sub.add_parser("literature", help="local literature-library helpers")
    literature_sub = literature.add_subparsers(dest="literature_command", required=True)
    lit_status = literature_sub.add_parser("status", help="create or show literature deployment status")
    lit_status.add_argument("workspace", type=Path)
    lit_status.add_argument("--project-id")
    lit_plan = literature_sub.add_parser("plan", help="prepare literature search queries and user confirmation package")
    lit_plan.add_argument("workspace", type=Path)
    lit_plan.add_argument("--scope", choices=["narrow", "ordinary", "review"], default="ordinary")
    lit_plan.add_argument("--access-mode", choices=["index_only", "open_access_only", "user_authenticated"], default="open_access_only")
    lit_plan.add_argument("--keyword", action="append", default=[])
    lit_confirm = literature_sub.add_parser("confirm", help="record user confirmation for selected literature top N")
    lit_confirm.add_argument("workspace", type=Path)
    lit_confirm.add_argument("--selected-top-n", required=True, type=int)
    lit_confirm.add_argument("--user-response", required=True)
    lit_handoff = literature_sub.add_parser("handoff", help="prepare an acquisition handoff packet for a dedicated literature workflow")
    lit_handoff.add_argument("workspace", type=Path)
    lit_handoff.add_argument("--mode", choices=["dedicated_thread", "manual_agent", "same_thread"], default="dedicated_thread")
    lit_handoff.add_argument("--literature-thread-id")
    lit_sync = literature_sub.add_parser("sync-status", help="sync acquisition workflow status back into the origin project")
    lit_sync.add_argument("workspace", type=Path)
    lit_sync.add_argument("--update", type=Path)

    image_data = sub.add_parser("image-data", help="image characterization helpers for SEM, TEM, and microscopy data")
    image_sub = image_data.add_subparsers(dest="image_command", required=True)
    image_record = image_sub.add_parser("record", help="create a traceable image analysis result from a raw image metadata file")
    image_record.add_argument("workspace", type=Path)
    image_record.add_argument("--metadata", required=True, type=Path)
    image_record.add_argument("--project-id")
    image_record.add_argument("--method", required=True)
    image_record.add_argument("--description", required=True)
    image_record.add_argument("--description-review-ref", required=True)
    image_record.add_argument("--sample-ref", action="append", default=[])
    image_record.add_argument("--analysis-mode", choices=["user_described", "agent_visual_review", "mixed"], default="user_described")
    image_record.add_argument("--ea-observation", action="append", default=[])
    image_record.add_argument("--interpretation")
    image_record.add_argument("--confidence", choices=["high", "medium", "low", "insufficient"], default="insufficient")
    image_record.add_argument("--scale-bar")
    image_report = image_sub.add_parser("report", help="generate a Markdown image analysis report from an image result metadata file")
    image_report.add_argument("workspace", type=Path)
    image_report.add_argument("--metadata", required=True, type=Path)
    image_report.add_argument("--project-id")
    image_report.add_argument("--experiment-ref", action="append", default=[])
    image_report.add_argument("--sample-ref", action="append", default=[])

    add_skills = sub.add_parser("add-skills", help="validate EA child-skill manifests")
    add_skills_sub = add_skills.add_subparsers(dest="add_skills_command", required=True)
    check = add_skills_sub.add_parser("check", help="check a child skill manifest")
    check.add_argument("manifest", type=Path)
    dry_run = add_skills_sub.add_parser("dry-run", help="write a dry-run report for a child skill manifest")
    dry_run.add_argument("manifest", type=Path)
    dry_run.add_argument("--workspace", required=True, type=Path)
    dry_run.add_argument("--sample-output", type=Path)
    register = add_skills_sub.add_parser("register", help="register a compliant child skill manifest")
    register.add_argument("manifest", type=Path)
    register.add_argument("--workspace", required=True, type=Path)
    register.add_argument("--sample-output", type=Path)
    register.add_argument("--status", choices=["active", "sandbox"], default="active")

    figure = sub.add_parser("lookup-figure", help="look up a figure by figure_id")
    figure.add_argument("workspace", type=Path)
    figure.add_argument("figure_id")

    return parser


def _print_json(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _project_id_from_workspace(workspace: Path) -> str:
    project_path = workspace / "EA_PROJECT.md"
    if not project_path.exists():
        return "unknown-project"
    frontmatter, _ = read_markdown_record(project_path)
    return str(frontmatter.get("project_id", "unknown-project"))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "init":
        initialize_project(
            args.workspace,
            project_name=args.name,
            research_direction=args.direction,
            material_system=args.material,
            experiment_type=args.experiment_type,
        )
        return 0
    if args.command == "init-project":
        outputs = initialize_project(
            args.workspace,
            project_name=args.name,
            project_slug=args.slug,
            research_direction=args.direction,
            material_system=args.material,
            experiment_type=args.experiment_type,
            default_language=args.report_language,
            enable_literature=args.enable_literature,
            enable_zotero=args.enable_zotero,
            literature_cache_root=args.literature_cache_root,
            zotero_local_api_url=args.zotero_local_api_url,
            zotero_collection=args.zotero_collection,
            browser_assist_enabled=args.browser_assist,
            browser_name=args.browser_name,
            browser_profile=args.browser_profile,
            institution_access=args.institution_access,
        )
        _print_json({key: str(value) for key, value in outputs.items()})
        return 0
    if args.command == "status":
        _print_json(
            {
                "workspace": str(args.workspace),
                "project_id": _project_id_from_workspace(args.workspace),
                "has_project_config": (args.workspace / ".ea" / "project_config.yml").exists(),
                "has_literature_status": (args.workspace / "literature" / "deployment_status.yml").exists(),
            }
        )
        return 0
    if args.command == "healthcheck":
        result = run_healthcheck(args.workspace)
        _print_json(result)
        return 0 if result["status"] == "pass" else 2
    if args.command == "config":
        if args.config_command == "doctor":
            _print_json(doctor_project_config(args.workspace))
            return 0
    if args.command == "literature":
        if args.literature_command == "status":
            project_id = args.project_id or _project_id_from_workspace(args.workspace)
            path = ensure_literature_status(args.workspace, project_id=project_id)
            _print_json({"status_path": str(path)})
            return 0
        if args.literature_command == "plan":
            _print_json(
                plan_literature_deployment(
                    args.workspace,
                    scope=args.scope,
                    access_mode=args.access_mode,
                    extra_keywords=args.keyword,
                )
            )
            return 0
        if args.literature_command == "confirm":
            _print_json(
                confirm_literature_selection(
                    args.workspace,
                    selected_top_n=args.selected_top_n,
                    user_response=args.user_response,
                )
            )
            return 0
        if args.literature_command == "handoff":
            _print_json(
                prepare_literature_acquisition_handoff(
                    args.workspace,
                    handoff_mode=args.mode,
                    literature_thread_id=args.literature_thread_id,
                )
            )
            return 0
        if args.literature_command == "sync-status":
            _print_json(
                sync_literature_acquisition_status(
                    args.workspace,
                    update_path=args.update,
                )
            )
            return 0
    if args.command == "image-data":
        project_id = args.project_id or _project_id_from_workspace(args.workspace)
        if args.image_command == "record":
            path = create_image_analysis_record(
                args.workspace,
                characterization_metadata_path=args.metadata,
                project_id=project_id,
                method=args.method,
                user_description=args.description,
                description_review_ref=args.description_review_ref,
                sample_refs=args.sample_ref,
                analysis_mode=args.analysis_mode,
                ea_observations=args.ea_observation,
                interpretation=args.interpretation,
                confidence=args.confidence,
                scale_bar=args.scale_bar,
            )
            _print_json({"metadata": str(path)})
            return 0
        if args.image_command == "report":
            path = generate_image_analysis_report(
                args.workspace,
                project_id=project_id,
                image_metadata_path=args.metadata,
                related_experiments=args.experiment_ref,
                related_samples=args.sample_ref,
            )
            _print_json({"report": str(path)})
            return 0
    if args.command == "add-skills":
        if args.add_skills_command == "check":
            result = validate_skill_manifest(args.manifest)
            _print_json(
                {
                    "ok": result.ok,
                    "errors": result.errors,
                    "warnings": result.warnings,
                    "skill_id": result.manifest.get("id"),
                }
            )
            return 0 if result.ok else 2
        if args.add_skills_command == "dry-run":
            result = run_skill_dry_run(
                args.workspace,
                args.manifest,
                sample_output_path=args.sample_output,
            )
            _print_json(result.to_dict())
            return 0 if result.ok else 2
        if args.add_skills_command == "register":
            result = register_skill_manifest(
                args.workspace,
                args.manifest,
                sample_output_path=args.sample_output,
                status=args.status,
            )
            _print_json(result)
            return 0 if result["ok"] else 2
    if args.command == "lookup-figure":
        _print_json(lookup_figure(args.workspace, args.figure_id))
        return 0
    raise AssertionError(f"Unhandled command: {args.command}")
