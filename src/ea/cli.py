from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from ea.config import doctor_project_config
from ea.evaluation import run_project_evaluation
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
from ea.memory import commit_memory_candidate, propose_memory_candidate, review_memory_candidate
from ea.pl import PLProcessingRequest, default_pl_processing_parameters, inspect_pl_file, process_pl_result
from ea.projects.service import initialize_project
from ea.raman import RamanProcessingRequest, default_processing_parameters, inspect_spectrum_file, process_raman_result
from ea.raw_import import import_raw_file
from ea.references import import_bibtex_references, register_reference, validate_report_citations
from ea.reports import generate_pl_report, generate_raman_report, generate_xrd_report
from ea.review import write_review_record
from ea.skills import register_skill_manifest, run_skill_dry_run, validate_skill_manifest
from ea.storage.files import read_markdown_record, read_yaml
from ea.xrd import XRDProcessingRequest, default_xrd_processing_parameters, inspect_xrd_file, process_xrd_result


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

    eval_parser = sub.add_parser("eval", help="run EA evaluation suites")
    eval_sub = eval_parser.add_subparsers(dest="eval_command", required=True)
    eval_project = eval_sub.add_parser("project", help="evaluate local project readiness for handoff or public release")
    eval_project.add_argument("workspace", type=Path)
    eval_project.add_argument("--suite", choices=["public-release", "public_release"], default="public-release")
    eval_project.add_argument("--no-write", action="store_true")
    eval_project.add_argument("--output", type=Path)

    healthcheck = sub.add_parser("healthcheck", help="audit EA project config, provenance, raw files, reports, and figures")
    healthcheck.add_argument("workspace", type=Path)

    config = sub.add_parser("config", help="EA configuration helpers")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    doctor = config_sub.add_parser("doctor", help="check project config for public-release portability")
    doctor.add_argument("workspace", type=Path)

    raw = sub.add_parser("raw", help="controlled raw-data import helpers")
    raw_sub = raw.add_subparsers(dest="raw_command", required=True)
    raw_import = raw_sub.add_parser("import", help="import a raw characterization file as a protected project copy")
    raw_import.add_argument("workspace", type=Path)
    raw_import.add_argument("source", type=Path)
    raw_import.add_argument("--project-id")
    raw_import.add_argument("--characterization-type", default="raman")
    raw_import.add_argument("--sample-ref", action="append", default=[])
    raw_import.add_argument("--experiment-ref", action="append", default=[])

    review = sub.add_parser("review", help="write user review records for review-gated workflows")
    review_sub = review.add_subparsers(dest="review_command", required=True)
    review_add = review_sub.add_parser("add", help="write a ReviewRecord")
    review_add.add_argument("workspace", type=Path)
    review_add.add_argument("--target-type", required=True)
    review_add.add_argument("--target-ref", required=True)
    review_add.add_argument("--user-response", required=True)
    review_add.add_argument("--reviewed-content")

    raman = sub.add_parser("raman", help="Raman inspection, processing, and report helpers")
    raman_sub = raman.add_subparsers(dest="raman_command", required=True)
    raman_inspect = raman_sub.add_parser("inspect", help="inspect a spectrum file and suggest Raman columns/unit")
    raman_inspect.add_argument("workspace", type=Path)
    raman_inspect.add_argument("spectrum", type=Path)
    raman_process = raman_sub.add_parser("process", help="run review-gated Raman processing")
    raman_process.add_argument("workspace", type=Path)
    raman_process.add_argument("--metadata", required=True, type=Path)
    raman_process.add_argument("--project-id")
    raman_process.add_argument("--sample-ref", action="append", default=[])
    raman_process.add_argument("--x-column", required=True)
    raman_process.add_argument("--y-column", required=True)
    raman_process.add_argument("--x-unit", choices=["cm^-1", "unknown"], required=True)
    raman_process.add_argument("--column-review-ref", required=True)
    raman_process.add_argument("--parameter-review-ref", required=True)
    raman_process.add_argument("--parameters-file", type=Path)
    raman_process.add_argument("--parameters-json")
    raman_report = raman_sub.add_parser("report", help="generate a Raman analysis report from Raman metadata")
    raman_report.add_argument("workspace", type=Path)
    raman_report.add_argument("--metadata", required=True, type=Path)
    raman_report.add_argument("--project-id")
    raman_report.add_argument("--experiment-ref", action="append", default=[])
    raman_report.add_argument("--sample-ref", action="append", default=[])
    raman_report.add_argument("--reference-id", action="append", default=[])

    pl = sub.add_parser("pl", help="PL inspection, processing, and report helpers")
    pl_sub = pl.add_subparsers(dest="pl_command", required=True)
    pl_inspect = pl_sub.add_parser("inspect", help="inspect a spectrum file and suggest PL columns/unit")
    pl_inspect.add_argument("workspace", type=Path)
    pl_inspect.add_argument("spectrum", type=Path)
    pl_process = pl_sub.add_parser("process", help="run review-gated PL processing")
    pl_process.add_argument("workspace", type=Path)
    pl_process.add_argument("--metadata", required=True, type=Path)
    pl_process.add_argument("--project-id")
    pl_process.add_argument("--sample-ref", action="append", default=[])
    pl_process.add_argument("--x-column", required=True)
    pl_process.add_argument("--y-column", required=True)
    pl_process.add_argument("--x-unit", choices=["eV", "nm", "unknown"], required=True)
    pl_process.add_argument("--column-review-ref", required=True)
    pl_process.add_argument("--parameter-review-ref", required=True)
    pl_process.add_argument("--parameters-file", type=Path)
    pl_process.add_argument("--parameters-json")
    pl_report = pl_sub.add_parser("report", help="generate a PL analysis report from PL metadata")
    pl_report.add_argument("workspace", type=Path)
    pl_report.add_argument("--metadata", required=True, type=Path)
    pl_report.add_argument("--project-id")
    pl_report.add_argument("--experiment-ref", action="append", default=[])
    pl_report.add_argument("--sample-ref", action="append", default=[])
    pl_report.add_argument("--reference-id", action="append", default=[])

    xrd = sub.add_parser("xrd", help="XRD inspection, processing, and report helpers")
    xrd_sub = xrd.add_subparsers(dest="xrd_command", required=True)
    xrd_inspect = xrd_sub.add_parser("inspect", help="inspect a diffraction file and suggest XRD columns/unit")
    xrd_inspect.add_argument("workspace", type=Path)
    xrd_inspect.add_argument("pattern", type=Path)
    xrd_process = xrd_sub.add_parser("process", help="run review-gated XRD processing")
    xrd_process.add_argument("workspace", type=Path)
    xrd_process.add_argument("--metadata", required=True, type=Path)
    xrd_process.add_argument("--project-id")
    xrd_process.add_argument("--sample-ref", action="append", default=[])
    xrd_process.add_argument("--x-column", required=True)
    xrd_process.add_argument("--y-column", required=True)
    xrd_process.add_argument("--x-unit", choices=["2theta_deg", "unknown"], required=True)
    xrd_process.add_argument("--column-review-ref", required=True)
    xrd_process.add_argument("--parameter-review-ref", required=True)
    xrd_process.add_argument("--parameters-file", type=Path)
    xrd_process.add_argument("--parameters-json")
    xrd_report = xrd_sub.add_parser("report", help="generate an XRD analysis report from XRD metadata")
    xrd_report.add_argument("workspace", type=Path)
    xrd_report.add_argument("--metadata", required=True, type=Path)
    xrd_report.add_argument("--project-id")
    xrd_report.add_argument("--experiment-ref", action="append", default=[])
    xrd_report.add_argument("--sample-ref", action="append", default=[])
    xrd_report.add_argument("--reference-id", action="append", default=[])

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
    image_report.add_argument("--reference-id", action="append", default=[])

    references = sub.add_parser("references", help="register and validate report references")
    references_sub = references.add_subparsers(dest="references_command", required=True)
    ref_add = references_sub.add_parser("add", help="register a literature or web reference in the EA project")
    ref_add.add_argument("workspace", type=Path)
    ref_add.add_argument("--project-id")
    ref_add.add_argument("--citation", required=True)
    ref_add.add_argument("--title")
    ref_add.add_argument("--author", action="append", default=[])
    ref_add.add_argument("--year", type=int)
    ref_add.add_argument("--venue")
    ref_add.add_argument("--doi")
    ref_add.add_argument("--url")
    ref_add.add_argument("--local-path")
    ref_add.add_argument("--source-type", choices=["manual", "literature_library", "web", "local_pdf", "report"], default="manual")
    ref_add.add_argument("--notes")
    ref_import = references_sub.add_parser("import-bibtex", help="import references from a user-provided BibTeX export")
    ref_import.add_argument("workspace", type=Path)
    ref_import.add_argument("bibtex", type=Path)
    ref_import.add_argument("--project-id")
    ref_import.add_argument("--source-type", choices=["literature_library", "manual", "web", "local_pdf", "report"], default="literature_library")
    ref_validate = references_sub.add_parser("validate-report", help="check report inline citations against its References section")
    ref_validate.add_argument("workspace", type=Path)
    ref_validate.add_argument("report", type=Path)

    memory = sub.add_parser("memory", help="review-gated project memory helpers")
    memory_sub = memory.add_subparsers(dest="memory_command", required=True)
    memory_propose = memory_sub.add_parser("propose", help="propose a memory candidate without committing it")
    memory_propose.add_argument("workspace", type=Path)
    memory_propose.add_argument("--project-id")
    memory_propose.add_argument("--text", required=True)
    memory_propose.add_argument("--source-ref", action="append", default=[])
    memory_propose.add_argument("--provenance-ref", action="append", default=[])
    memory_propose.add_argument("--category", choices=["finding", "interpretation", "hypothesis", "method_note", "project_rule"], default="interpretation")
    memory_propose.add_argument("--confidence", choices=["high", "medium", "low", "insufficient"], default="medium")
    memory_propose.add_argument("--rationale")
    memory_review = memory_sub.add_parser("review", help="record user review for a memory candidate")
    memory_review.add_argument("workspace", type=Path)
    memory_review.add_argument("--candidate", required=True, type=Path)
    memory_review.add_argument("--user-response", required=True)
    memory_review.add_argument("--reviewed-content")
    memory_commit = memory_sub.add_parser("commit", help="commit a user-confirmed memory candidate to project memory")
    memory_commit.add_argument("workspace", type=Path)
    memory_commit.add_argument("--candidate", required=True, type=Path)
    memory_commit.add_argument("--review-ref")

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


def _project_path(workspace: Path, path: Path) -> Path:
    return path if path.is_absolute() else workspace / path


def _processing_parameters(args: argparse.Namespace, workspace: Path) -> dict:
    parameters = default_processing_parameters()
    if args.parameters_file:
        parameters.update(read_yaml(_project_path(workspace, args.parameters_file)))
    if args.parameters_json:
        parameters.update(json.loads(args.parameters_json))
    return parameters


def _pl_processing_parameters(args: argparse.Namespace, workspace: Path) -> dict:
    parameters = default_pl_processing_parameters()
    if args.parameters_file:
        parameters.update(read_yaml(_project_path(workspace, args.parameters_file)))
    if args.parameters_json:
        parameters.update(json.loads(args.parameters_json))
    return parameters


def _xrd_processing_parameters(args: argparse.Namespace, workspace: Path) -> dict:
    parameters = default_xrd_processing_parameters()
    if args.parameters_file:
        parameters.update(read_yaml(_project_path(workspace, args.parameters_file)))
    if args.parameters_json:
        parameters.update(json.loads(args.parameters_json))
    return parameters


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
    if args.command == "eval":
        if args.eval_command == "project":
            result = run_project_evaluation(
                args.workspace,
                suite=args.suite,
                write_report=not args.no_write,
                output_path=args.output,
            )
            _print_json(result)
            return 0 if result["status"] != "fail" else 2
    if args.command == "healthcheck":
        result = run_healthcheck(args.workspace)
        _print_json(result)
        return 0 if result["status"] == "pass" else 2
    if args.command == "config":
        if args.config_command == "doctor":
            _print_json(doctor_project_config(args.workspace))
            return 0
    if args.command == "raw":
        if args.raw_command == "import":
            project_id = args.project_id or _project_id_from_workspace(args.workspace)
            result = import_raw_file(
                args.workspace,
                args.source,
                project_id=project_id,
                characterization_type=args.characterization_type,
                sample_refs=args.sample_ref,
                experiment_refs=args.experiment_ref,
            )
            _print_json(
                {
                    "characterization_id": result.characterization_id,
                    "import_status": result.import_status,
                    "metadata": str(result.metadata_path),
                    "project_raw_path": str(result.project_raw_path) if result.project_raw_path else None,
                    "canonical_metadata": str(result.canonical_metadata_path) if result.canonical_metadata_path else None,
                    "sha256": result.sha256,
                }
            )
            return 0
    if args.command == "review":
        if args.review_command == "add":
            path = write_review_record(
                args.workspace,
                target_type=args.target_type,
                target_ref=args.target_ref,
                user_response=args.user_response,
                reviewed_content=args.reviewed_content or args.user_response,
            )
            data = read_yaml(path)
            _print_json({"review": str(path), "review_id": path.stem, "review_status": data.get("review_status")})
            return 0
    if args.command == "raman":
        project_id = getattr(args, "project_id", None)
        if args.raman_command in {"process", "report"} and not project_id:
            project_id = _project_id_from_workspace(args.workspace)
        if args.raman_command == "inspect":
            inspection = asdict(inspect_spectrum_file(_project_path(args.workspace, args.spectrum)))
            inspection["path"] = str(inspection["path"])
            _print_json(inspection)
            return 0
        if args.raman_command == "process":
            parameters = _processing_parameters(args, args.workspace)
            path = process_raman_result(
                args.workspace,
                characterization_metadata_path=_project_path(args.workspace, args.metadata),
                project_id=project_id,
                sample_refs=args.sample_ref,
                request=RamanProcessingRequest(
                    x_column=args.x_column,
                    y_column=args.y_column,
                    x_unit=args.x_unit,
                    processing_parameters=parameters,
                    column_review_ref=args.column_review_ref,
                    parameter_review_ref=args.parameter_review_ref,
                ),
            )
            _print_json({"metadata": str(path)})
            return 0
        if args.raman_command == "report":
            path = generate_raman_report(
                args.workspace,
                project_id=project_id,
                raman_metadata_path=_project_path(args.workspace, args.metadata),
                related_experiments=args.experiment_ref,
                related_samples=args.sample_ref,
                reference_ids=args.reference_id,
            )
            _print_json({"report": str(path)})
            return 0
    if args.command == "pl":
        project_id = getattr(args, "project_id", None)
        if args.pl_command in {"process", "report"} and not project_id:
            project_id = _project_id_from_workspace(args.workspace)
        if args.pl_command == "inspect":
            inspection = asdict(inspect_pl_file(_project_path(args.workspace, args.spectrum)))
            inspection["path"] = str(inspection["path"])
            _print_json(inspection)
            return 0
        if args.pl_command == "process":
            parameters = _pl_processing_parameters(args, args.workspace)
            path = process_pl_result(
                args.workspace,
                characterization_metadata_path=_project_path(args.workspace, args.metadata),
                project_id=project_id,
                sample_refs=args.sample_ref,
                request=PLProcessingRequest(
                    x_column=args.x_column,
                    y_column=args.y_column,
                    x_unit=args.x_unit,
                    processing_parameters=parameters,
                    column_review_ref=args.column_review_ref,
                    parameter_review_ref=args.parameter_review_ref,
                ),
            )
            _print_json({"metadata": str(path)})
            return 0
        if args.pl_command == "report":
            path = generate_pl_report(
                args.workspace,
                project_id=project_id,
                pl_metadata_path=_project_path(args.workspace, args.metadata),
                related_experiments=args.experiment_ref,
                related_samples=args.sample_ref,
                reference_ids=args.reference_id,
            )
            _print_json({"report": str(path)})
            return 0
    if args.command == "xrd":
        project_id = getattr(args, "project_id", None)
        if args.xrd_command in {"process", "report"} and not project_id:
            project_id = _project_id_from_workspace(args.workspace)
        if args.xrd_command == "inspect":
            inspection = asdict(inspect_xrd_file(_project_path(args.workspace, args.pattern)))
            inspection["path"] = str(inspection["path"])
            _print_json(inspection)
            return 0
        if args.xrd_command == "process":
            parameters = _xrd_processing_parameters(args, args.workspace)
            path = process_xrd_result(
                args.workspace,
                characterization_metadata_path=_project_path(args.workspace, args.metadata),
                project_id=project_id,
                sample_refs=args.sample_ref,
                request=XRDProcessingRequest(
                    x_column=args.x_column,
                    y_column=args.y_column,
                    x_unit=args.x_unit,
                    processing_parameters=parameters,
                    column_review_ref=args.column_review_ref,
                    parameter_review_ref=args.parameter_review_ref,
                ),
            )
            _print_json({"metadata": str(path)})
            return 0
        if args.xrd_command == "report":
            path = generate_xrd_report(
                args.workspace,
                project_id=project_id,
                xrd_metadata_path=_project_path(args.workspace, args.metadata),
                related_experiments=args.experiment_ref,
                related_samples=args.sample_ref,
                reference_ids=args.reference_id,
            )
            _print_json({"report": str(path)})
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
                reference_ids=args.reference_id,
            )
            _print_json({"report": str(path)})
            return 0
    if args.command == "references":
        if args.references_command == "add":
            project_id = args.project_id or _project_id_from_workspace(args.workspace)
            path = register_reference(
                args.workspace,
                project_id=project_id,
                citation=args.citation,
                title=args.title,
                authors=args.author,
                year=args.year,
                venue=args.venue,
                doi=args.doi,
                url=args.url,
                local_path=args.local_path,
                source_type=args.source_type,
                notes=args.notes,
            )
            _print_json({"reference": str(path)})
            return 0
        if args.references_command == "import-bibtex":
            project_id = args.project_id or _project_id_from_workspace(args.workspace)
            _print_json(
                import_bibtex_references(
                    args.workspace,
                    args.bibtex,
                    project_id=project_id,
                    source_type=args.source_type,
                )
            )
            return 0
        if args.references_command == "validate-report":
            report_path = args.report if args.report.is_absolute() else args.workspace / args.report
            result = validate_report_citations(report_path)
            _print_json(result)
            return 0 if result["ok"] else 2
    if args.command == "memory":
        if args.memory_command == "propose":
            project_id = args.project_id or _project_id_from_workspace(args.workspace)
            path = propose_memory_candidate(
                args.workspace,
                project_id=project_id,
                candidate_text=args.text,
                source_refs=args.source_ref,
                provenance_refs=args.provenance_ref,
                category=args.category,
                confidence=args.confidence,
                rationale=args.rationale,
            )
            _print_json({"candidate": str(path)})
            return 0
        if args.memory_command == "review":
            path = review_memory_candidate(
                args.workspace,
                candidate_path=args.candidate,
                user_response=args.user_response,
                reviewed_content=args.reviewed_content,
            )
            _print_json({"candidate": str(path)})
            return 0
        if args.memory_command == "commit":
            path = commit_memory_candidate(
                args.workspace,
                candidate_path=args.candidate,
                review_ref=args.review_ref,
            )
            _print_json({"memory": str(path)})
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
