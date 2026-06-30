from __future__ import annotations

import argparse
import json
from pathlib import Path

from ea.config import doctor_project_config
from ea.figures import lookup_figure
from ea.literature import ensure_literature_status
from ea.projects.service import initialize_project
from ea.skills import validate_skill_manifest
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

    config = sub.add_parser("config", help="EA configuration helpers")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    doctor = config_sub.add_parser("doctor", help="check project config for public-release portability")
    doctor.add_argument("workspace", type=Path)

    literature = sub.add_parser("literature", help="local literature-library helpers")
    literature_sub = literature.add_subparsers(dest="literature_command", required=True)
    lit_status = literature_sub.add_parser("status", help="create or show literature deployment status")
    lit_status.add_argument("workspace", type=Path)
    lit_status.add_argument("--project-id")

    add_skills = sub.add_parser("add-skills", help="validate EA child-skill manifests")
    add_skills_sub = add_skills.add_subparsers(dest="add_skills_command", required=True)
    check = add_skills_sub.add_parser("check", help="check a child skill manifest")
    check.add_argument("manifest", type=Path)

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
    if args.command == "lookup-figure":
        _print_json(lookup_figure(args.workspace, args.figure_id))
        return 0
    raise AssertionError(f"Unhandled command: {args.command}")
