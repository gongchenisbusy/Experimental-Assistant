from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path

from ea import __version__
from ea.identity import CAPABILITY_MATURITY
from ea.batch import BatchManifestError, run_batch_manifest, validate_batch_manifest
from ea.brief import build_project_brief
from ea.config import doctor_project_config
from ea.data_import import apply_import, preview_import
from ea.diagnostics import collect_diagnostics
from ea.drafts import draft_artifact_status, promote_draft_artifact, stage_draft_artifact
from ea.electrochemistry import (
    ElectrochemistryProcessingRequest,
    default_electrochemistry_processing_parameters,
    inspect_electrochemistry_file,
    process_electrochemistry_result,
)
from ea.evaluation import run_project_evaluation
from ea.errors import error_record
from ea.exports import (
    ReportBundleError,
    export_batch_bundle,
    export_report_html,
    export_report_bundle,
    verify_archive_checksum,
    verify_bundle_checksums,
)
from ea.figures import lookup_figure
from ea.ftir import (
    FTIRProcessingRequest,
    build_ftir_assignment_source_packet,
    builtin_ftir_assignment_libraries,
    default_ftir_processing_parameters,
    inspect_ftir_file,
    prepare_ftir_assignment_review_package,
    process_ftir_result,
    propose_ftir_assignment_memory_candidates,
    suggest_ftir_assignments,
    summarize_ftir_assignment_libraries,
)
from ea.healthcheck import run_healthcheck
from ea.image_data import create_image_analysis_record, generate_image_analysis_report
from ea.install_experience import (
    PACKAGE_NAME,
    PUBLIC_VERSION,
    RELEASE_LABEL,
    SKILL_INVOCATION,
    identity_record,
    install_check,
    install_codex_skill,
    lifecycle_update_plan,
    onboarding_post_install_record,
    rollback_codex_skills,
    rollback_installation,
    render_onboarding_post_install,
    render_install_skill_summary,
    render_install_summary,
    setup_installation,
    uninstall_codex_skills,
    uninstall_installation,
    update_installation,
)
from ea.estimates import estimate_workflow, large_work_gate, large_work_reminders_disabled, set_large_work_reminders
from ea.literature import (
    PROPERTY_KINDS,
    REVIEW_DECISIONS,
    confirm_literature_selection,
    ensure_literature_status,
    export_literature_data,
    extract_literature_data,
    import_literature_acquisition_manifest,
    import_zotero_codex_batch_status,
    plan_literature_deployment,
    plan_literature_data_extraction,
    plot_literature_data,
    preflight_literature_source_candidate_manifest,
    prepare_institution_access_guidance,
    prepare_literature_acceptance_checklist,
    prepare_literature_acquisition_request,
    prepare_literature_acquisition_handoff,
    prepare_literature_source_candidate_manifest,
    prepare_zotero_codex_acquisition_bridge,
    rank_literature_candidates,
    reconcile_literature_acquisition,
    render_literature_acquisition_reconciliation,
    review_literature_data,
    search_public_literature_metadata,
    setup_literature_preflight,
    summarize_zotero_codex_readiness,
    sync_literature_acquisition_status,
    validate_literature_data,
)
from ea.materials import (
    audit_assignment_library,
    assignment_candidates,
    available_materials,
    get_material_profile,
    summarize_pl_assignment_libraries,
    summarize_raman_assignment_libraries,
    summarize_xrd_assignment_libraries,
)
from ea.memory import (
    commit_memory_candidate,
    propose_memory_candidate,
    refresh_project_working_memory,
    review_memory_candidate,
    show_project_working_memory,
)
from ea.migrations import (
    apply_project_migration,
    plan_project_migration,
    project_format_status,
    rollback_project_migration,
)
from ea.pl import PLProcessingRequest, default_pl_processing_parameters, inspect_pl_file, process_pl_result
from ea.projects.service import initialize_project
from ea.raman import RamanProcessingRequest, default_processing_parameters, inspect_spectrum_file, process_raman_result
from ea.raw_import import import_raw_file
from ea.references import import_bibtex_references, register_reference, register_reference_seeds, validate_report_citations
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
from ea.review import promote_review_record, write_review_record
from ea.skills import register_skill_manifest, run_skill_dry_run, validate_skill_manifest
from ea.storage.files import read_markdown_record, read_yaml
from ea.templates import (
    SUPPORTED_TEMPLATE_METHODS,
    batch_manifest_template,
    processing_parameters_template,
    write_batch_manifest_template,
    write_processing_parameters_template,
)
from ea.thermal import ThermalAnalysisProcessingRequest, default_thermal_processing_parameters, inspect_thermal_file, process_thermal_result
from ea.traceability import build_project_trace_view, build_trace_focus, build_trace_index, export_full_trace, lookup_trace_record
from ea.user_surface import build_project_dashboard, generate_user_report, inspect_analysis_source, start_project
from ea.uv_vis import (
    UVVisProcessingRequest,
    build_uv_vis_source_packet,
    builtin_uv_vis_source_libraries,
    compare_uv_vis_replicates,
    default_uv_vis_processing_parameters,
    inspect_uv_vis_file,
    prepare_uv_vis_interpretation_review_package,
    process_uv_vis_result,
    propose_uv_vis_interpretation_memory_candidates,
    suggest_uv_vis_interpretations,
    summarize_uv_vis_source_libraries,
)
from ea.xps import (
    XPSProcessingRequest,
    build_xps_parameter_source_packet,
    builtin_xps_parameter_libraries,
    default_xps_processing_parameters,
    inspect_xps_file,
    prepare_xps_parameter_review_package,
    process_xps_result,
    propose_xps_parameter_memory_candidates,
    suggest_xps_parameters,
    summarize_xps_parameter_libraries,
)
from ea.xrd import (
    XRDProcessingRequest,
    build_xrd_assignment_source_packet,
    builtin_xrd_assignment_libraries,
    default_xrd_processing_parameters,
    inspect_xrd_file,
    prepare_xrd_assignment_review_package,
    process_xrd_result,
    suggest_xrd_assignments,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ea")
    parser.add_argument(
        "--mode",
        dest="interaction_mode",
        choices=["consult", "record", "execute", "audit"],
        default=os.environ.get("EA_MODE", "execute"),
        help="set read/write interaction semantics for this command",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=(
            f"{PUBLIC_VERSION} package {PACKAGE_NAME} {__version__} "
            f"({RELEASE_LABEL}); skill invocation {SKILL_INVOCATION}"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    version = sub.add_parser("version", help="show Experimental Assistant product, package, release, and skill identity")
    version.add_argument("--json", action="store_true")
    capabilities = sub.add_parser("capabilities", help="show the stable, beta, and experimental capability contract")
    capabilities.add_argument("--maturity", choices=["stable", "beta", "experimental"])
    capabilities.add_argument("--json", action="store_true")
    mode = sub.add_parser("mode", help="show consult, record, execute, and audit semantics")
    mode.add_argument("--json", action="store_true")
    diagnostics = sub.add_parser("diagnostics", help="collect privacy-safe local diagnostics without submission")
    diagnostics_sub = diagnostics.add_subparsers(dest="diagnostics_command", required=True)
    diagnostics_collect = diagnostics_sub.add_parser("collect", help="summarize version, errors, operations, and selected logs")
    diagnostics_collect.add_argument("workspace", type=Path)
    diagnostics_collect.add_argument("--output", type=Path)
    diagnostics_collect.add_argument("--log", action="append", type=Path, default=[])
    diagnostics_collect.add_argument("--debug-json", action="store_true")
    drafts = sub.add_parser("draft", help="stage, inspect, and review-promote a formal project artifact")
    drafts_sub = drafts.add_subparsers(dest="draft_command", required=True)
    draft_stage = drafts_sub.add_parser("stage", help="copy one non-raw file into the project draft layer")
    draft_stage.add_argument("workspace", type=Path)
    draft_stage.add_argument("--source", required=True, type=Path)
    draft_stage.add_argument("--target", required=True)
    draft_stage.add_argument("--draft-id")
    draft_stage.add_argument("--yes", action="store_true")
    draft_status = drafts_sub.add_parser("status", help="inspect one draft without writing")
    draft_status.add_argument("workspace", type=Path)
    draft_status.add_argument("--draft-id", required=True)
    draft_promote = drafts_sub.add_parser("promote", help="atomically promote a reviewed draft without overwriting")
    draft_promote.add_argument("workspace", type=Path)
    draft_promote.add_argument("--draft-id", required=True)
    draft_promote.add_argument("--review-ref", required=True)
    draft_promote.add_argument("--yes", action="store_true")

    setup = sub.add_parser("setup", help="install the $ea and compatibility skills and show first-run onboarding")
    setup.add_argument("--source", type=Path, help="repository root or primary skills/ea folder")
    setup.add_argument("--codex-home", type=Path)
    setup.add_argument("--quick-validate", type=Path)
    setup.add_argument("--release-ref", default=RELEASE_LABEL)
    setup.add_argument("--lang", choices=["zh", "en"], default="zh")
    setup.add_argument("--json", action="store_true")

    public_doctor = sub.add_parser("doctor", help="verify exact CLI, distribution, and Codex skill identity")
    public_doctor.add_argument("--codex-home", type=Path)
    public_doctor.add_argument("--skill-path", type=Path)
    public_doctor.add_argument("--quick-validate", type=Path)
    public_doctor.add_argument("--run-example-check", action="store_true")
    public_doctor.add_argument("--example-workspace", type=Path)
    public_doctor.add_argument("--skip-codex-skill", action="store_true")
    public_doctor.add_argument("--json", action="store_true")

    public_import = sub.add_parser("import", help="preview and confirm a protected delimited-text import")
    public_import_sub = public_import.add_subparsers(dest="import_command", required=True)
    public_import_preview = public_import_sub.add_parser("preview", help="inspect encoding, delimiter, columns, units, and hash without writing")
    public_import_preview.add_argument("source", type=Path)
    public_import_preview.add_argument("--encoding", default="auto")
    public_import_preview.add_argument("--delimiter", default="auto")
    public_import_preview.add_argument("--allow-symlink", action="store_true")
    public_import_preview.add_argument("--max-rows", type=int, default=5)
    public_import_apply = public_import_sub.add_parser("apply", help="import the exact reviewed source hash as a protected copy")
    public_import_apply.add_argument("workspace", type=Path)
    public_import_apply.add_argument("source", type=Path)
    public_import_apply.add_argument("--characterization-type", required=True)
    public_import_apply.add_argument("--sample-ref", action="append", default=[])
    public_import_apply.add_argument("--experiment-ref", action="append", default=[])
    public_import_apply.add_argument("--encoding", default="auto")
    public_import_apply.add_argument("--delimiter", default="auto")
    public_import_apply.add_argument("--allow-symlink", action="store_true")
    public_import_apply.add_argument("--preview-hash")
    public_import_apply.add_argument("--yes", action="store_true")

    start = sub.add_parser("start", help="plan or create a first EA project with safe defaults")
    start.add_argument("workspace", type=Path)
    start.add_argument("--name")
    start.add_argument("--direction")
    start.add_argument("--material")
    start.add_argument("--experiment-type")
    start.add_argument("--report-language", choices=["zh", "en"], default="zh")
    start.add_argument("--yes", action="store_true")

    analyze = sub.add_parser("analyze", help="inspect a method input without writing or applying parameters")
    analyze.add_argument("workspace", type=Path)
    analyze.add_argument("source", type=Path)
    analyze.add_argument("--method", required=True)

    public_report = sub.add_parser("report", help="plan or generate a method report from reviewed processed metadata")
    public_report.add_argument("workspace", type=Path)
    public_report.add_argument("--method", required=True)
    public_report.add_argument("--metadata", type=Path, required=True)
    public_report.add_argument("--sample-ref", action="append", default=[])
    public_report.add_argument("--experiment-ref", action="append", default=[])
    public_report.add_argument("--reference-id", action="append", default=[])
    public_report.add_argument("--yes", action="store_true")

    update = sub.add_parser("update", help="plan or perform a transactional CLI and skill update")
    update.add_argument("--release-ref", default=RELEASE_LABEL)
    update.add_argument("--yes", action="store_true", help="confirm package and skill replacement")
    update.add_argument("--json", action="store_true")

    rollback = sub.add_parser("rollback", help="plan or perform rollback to a verified EA release")
    rollback.add_argument("--release-ref", default="v0.9.6")
    rollback.add_argument("--yes", action="store_true", help="confirm package and skill replacement")
    rollback.add_argument("--json", action="store_true")

    uninstall = sub.add_parser("uninstall", help="plan or remove the EA CLI and Codex skills with recoverable skill backups")
    uninstall.add_argument("--codex-home", type=Path)
    uninstall.add_argument("--yes", action="store_true", help="confirm CLI and skill removal")
    uninstall.add_argument("--json", action="store_true")

    install_check_parser = sub.add_parser("install-check", help="verify EA CLI and Codex skill installation readiness")
    install_check_parser.add_argument("--codex-home", type=Path)
    install_check_parser.add_argument("--skill-path", type=Path)
    install_check_parser.add_argument("--quick-validate", type=Path)
    install_check_parser.add_argument("--run-example-check", action="store_true")
    install_check_parser.add_argument("--example-workspace", type=Path)
    install_check_parser.add_argument("--skip-codex-skill", action="store_true")
    install_check_parser.add_argument("--json", action="store_true")

    codex = sub.add_parser("codex", help="Codex integration helpers for Experimental Assistant")
    codex_sub = codex.add_subparsers(dest="codex_command", required=True)
    codex_install = codex_sub.add_parser("install-skill", help="transactionally install the $ea skill and compatibility wrapper into Codex")
    codex_install.add_argument("--source", type=Path, help="repository root or primary skills/ea folder; defaults to local checkout or GitHub release fetch")
    codex_install.add_argument("--codex-home", type=Path)
    codex_install.add_argument("--quick-validate", type=Path)
    codex_install.add_argument("--no-backup", action="store_true", help="replace existing EA skills without making timestamped backups")
    codex_install.add_argument("--no-github-fetch", action="store_true", help="do not fetch the public release from GitHub if no local skill source is found")
    codex_install.add_argument("--release-ref", default=RELEASE_LABEL)
    codex_install.add_argument("--json", action="store_true")
    codex_rollback = codex_sub.add_parser("rollback-skill", help="restore the latest validated $ea and compatibility backups")
    codex_rollback.add_argument("--codex-home", type=Path)
    codex_rollback.add_argument("--quick-validate", type=Path)
    codex_rollback.add_argument("--yes", action="store_true")
    codex_rollback.add_argument("--json", action="store_true")
    codex_uninstall = codex_sub.add_parser("uninstall-skills", help="remove EA skills into recoverable backups")
    codex_uninstall.add_argument("--codex-home", type=Path)
    codex_uninstall.add_argument("--yes", action="store_true")
    codex_uninstall.add_argument("--json", action="store_true")

    onboarding = sub.add_parser("onboarding", help="version-bound onboarding messages")
    onboarding_sub = onboarding.add_subparsers(dest="onboarding_command", required=True)
    onboarding_post = onboarding_sub.add_parser("post-install", help="show stable post-install/update onboarding")
    onboarding_post.add_argument("--event", choices=["install", "update"], default="install")
    onboarding_post.add_argument("--lang", choices=["zh", "en"], default="zh")
    onboarding_post.add_argument("--json", action="store_true")

    init = sub.add_parser("init", help="initialize a local EA project workspace (v0.1-compatible alias)")
    init.add_argument("workspace", type=Path)
    init.add_argument("--name", required=True)
    init.add_argument("--direction", required=True)
    init.add_argument("--material", required=True)
    init.add_argument("--experiment-type", required=True)

    init_project = sub.add_parser("init-project", help="initialize a public-user Experimental Assistant v0.9.7 project workspace")
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

    migrate = sub.add_parser("migrate", help="plan, apply, inspect, or roll back EA project-format migrations")
    migrate_sub = migrate.add_subparsers(dest="migrate_command", required=True)
    migrate_status = migrate_sub.add_parser("status", help="inspect project format without writing")
    migrate_status.add_argument("workspace", type=Path)
    migrate_plan = migrate_sub.add_parser("plan", help="show migration writes and backups without writing")
    migrate_plan.add_argument("workspace", type=Path)
    migrate_plan.add_argument("--target-version", default="1.0")
    migrate_apply = migrate_sub.add_parser("apply", help="apply a confirmed, backed-up project-format migration")
    migrate_apply.add_argument("workspace", type=Path)
    migrate_apply.add_argument("--target-version", default="1.0")
    migrate_apply.add_argument("--yes", action="store_true", help="confirm the migration plan")
    migrate_rollback = migrate_sub.add_parser("rollback", help="restore a confirmed migration backup")
    migrate_rollback.add_argument("workspace", type=Path)
    migrate_rollback.add_argument("--migration-id", required=True)
    migrate_rollback.add_argument("--yes", action="store_true", help="confirm rollback")

    status = sub.add_parser("status", help="summarize an EA project workspace")
    status.add_argument("workspace", type=Path)

    brief_parser = sub.add_parser("brief", help="write agent-friendly project briefs")
    brief_sub = brief_parser.add_subparsers(dest="brief_command", required=True)
    brief_project = brief_sub.add_parser("project", help="summarize project state, confirmations, outputs, and next actions")
    brief_project.add_argument("workspace", type=Path)
    brief_project.add_argument("--no-write", action="store_true")
    brief_project.add_argument("--output", type=Path)
    brief_project.add_argument("--json", action="store_true", help="print compact structured JSON instead of the default human summary")
    brief_project.add_argument("--json-full", action="store_true", help="print the full brief result JSON")
    brief_project.add_argument("--print-markdown", action="store_true")

    eval_parser = sub.add_parser("eval", help="run EA evaluation suites")
    eval_sub = eval_parser.add_subparsers(dest="eval_command", required=True)
    eval_project = eval_sub.add_parser("project", help="evaluate local project readiness for handoff or public release")
    eval_project.add_argument("workspace", type=Path)
    eval_project.add_argument("--suite", choices=["public-release", "public_release"], default="public-release")
    eval_project.add_argument("--no-write", action="store_true")
    eval_project.add_argument("--output", type=Path)

    export_parser = sub.add_parser("export", help="export local EA handoff bundles")
    export_sub = export_parser.add_subparsers(dest="export_command", required=True)
    report_bundle = export_sub.add_parser("report-bundle", help="bundle one report with figures, source data, and traceability records")
    report_bundle.add_argument("workspace", type=Path)
    report_bundle.add_argument("--report-id", required=True)
    report_bundle.add_argument("--output", type=Path)
    report_bundle.add_argument("--include-trace", action="store_true", help="include a focused traceability YAML/Markdown view in the bundle")
    report_bundle.add_argument("--zip", action="store_true", help="also create a deterministic zip archive next to the bundle")
    report_bundle.add_argument("--zip-output", type=Path, help="write the optional zip archive to this path")
    report_html = export_sub.add_parser("report-html", help="render one indexed report as user-readable HTML with embedded figures")
    report_html.add_argument("workspace", type=Path)
    report_html.add_argument("--report-id", required=True)
    report_html.add_argument("--output", type=Path)
    report_html.add_argument("--no-embed-images", action="store_true", help="preserve project-local image refs instead of embedding figure data")
    report_html.add_argument("--no-audit", action="store_true", help="omit detailed provenance YAML from the HTML audit appendix")
    batch_bundle = export_sub.add_parser("batch-bundle", help="bundle one batch run with nested report bundles")
    batch_bundle.add_argument("workspace", type=Path)
    batch_bundle.add_argument("--batch-id", required=True)
    batch_bundle.add_argument("--output", type=Path)
    batch_bundle.add_argument("--include-trace", action="store_true", help="include focused traceability views in nested report bundles")
    batch_bundle.add_argument("--zip", action="store_true", help="also create a deterministic zip archive next to the bundle")
    batch_bundle.add_argument("--zip-output", type=Path, help="write the optional zip archive to this path")
    verify_bundle = export_sub.add_parser("verify-bundle", help="verify a report or batch bundle from bundle_checksums.yml")
    verify_bundle.add_argument("bundle", type=Path)
    verify_archive = export_sub.add_parser("verify-archive", help="verify a zip archive against a .sha256 sidecar")
    verify_archive.add_argument("archive", type=Path)
    verify_archive.add_argument("--checksum", type=Path)

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
    review_add.add_argument("--confirm", action="store_true", help="explicitly mark parameter/field review as user-confirmed")
    review_promote = review_sub.add_parser("promote", help="promote a parameter/field ReviewRecord after explicit user confirmation")
    review_promote.add_argument("workspace", type=Path)
    review_promote.add_argument("--review-ref", required=True)
    review_promote.add_argument("--user-response", required=True)

    raman = sub.add_parser("raman", help="Raman inspection, processing, and report helpers")
    raman_sub = raman.add_subparsers(dest="raman_command", required=True)
    raman_list_libraries = raman_sub.add_parser("list-assignment-libraries", help="list built-in Raman assignment libraries and candidates")
    raman_list_libraries.add_argument("--material", action="append", default=[])
    raman_list_libraries.add_argument("--feature", action="append", default=[])
    raman_list_libraries.add_argument("--shift-min-cm1", type=float)
    raman_list_libraries.add_argument("--shift-max-cm1", type=float)
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
    pl_list_libraries = pl_sub.add_parser("list-assignment-libraries", help="list built-in PL assignment libraries and candidates")
    pl_list_libraries.add_argument("--material", action="append", default=[])
    pl_list_libraries.add_argument("--feature", action="append", default=[])
    pl_list_libraries.add_argument("--energy-min-ev", type=float)
    pl_list_libraries.add_argument("--energy-max-ev", type=float)
    pl_list_libraries.add_argument("--wavelength-min-nm", type=float)
    pl_list_libraries.add_argument("--wavelength-max-nm", type=float)
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
    xrd_list_libraries = xrd_sub.add_parser("list-assignment-libraries", help="list built-in XRD assignment libraries and candidates")
    xrd_list_libraries.add_argument("--material", action="append", default=[])
    xrd_list_libraries.add_argument("--feature", action="append", default=[])
    xrd_list_libraries.add_argument("--two-theta-min-deg", type=float)
    xrd_list_libraries.add_argument("--two-theta-max-deg", type=float)
    xrd_list_libraries.add_argument("--d-spacing-min-angstrom", type=float)
    xrd_list_libraries.add_argument("--d-spacing-max-angstrom", type=float)
    xrd_source_packet = xrd_sub.add_parser("build-assignment-packet", help="build a standard XRD assignment source packet")
    xrd_source_packet.add_argument("workspace", type=Path)
    xrd_source_packet.add_argument("--library-file", type=Path)
    xrd_source_packet.add_argument(
        "--builtin-library",
        choices=builtin_xrd_assignment_libraries(),
        help="use a bundled XRD assignment library; defaults to builtin_material_assignments when no library file or template is supplied",
    )
    xrd_source_packet.add_argument("--literature-manifest", type=Path, help="build from a user-confirmed literature/source-candidate manifest")
    xrd_source_packet.add_argument("--output", type=Path)
    xrd_source_packet.add_argument("--project-id")
    xrd_source_packet.add_argument("--include-candidate", action="append", default=[])
    xrd_source_packet.add_argument("--material", action="append", default=[])
    xrd_source_packet.add_argument("--feature", action="append", default=[])
    xrd_source_packet.add_argument("--two-theta-min-deg", type=float)
    xrd_source_packet.add_argument("--two-theta-max-deg", type=float)
    xrd_source_packet.add_argument("--d-spacing-min-angstrom", type=float)
    xrd_source_packet.add_argument("--d-spacing-max-angstrom", type=float)
    xrd_source_packet.add_argument("--write-template", action="store_true")
    xrd_suggest = xrd_sub.add_parser("suggest-assignments", help="record source-backed XRD assignment suggestions without applying them")
    xrd_suggest.add_argument("workspace", type=Path)
    xrd_suggest.add_argument("--metadata", required=True, type=Path)
    xrd_suggest.add_argument("--source-file", required=True, type=Path)
    xrd_suggest.add_argument("--project-id")
    xrd_suggest.add_argument("--related-record", action="append", default=[])
    xrd_prepare_review = xrd_sub.add_parser("prepare-review", help="prepare a grouped review package from XRD assignment suggestions")
    xrd_prepare_review.add_argument("workspace", type=Path)
    xrd_prepare_review.add_argument("--suggestion", required=True, type=Path)
    xrd_prepare_review.add_argument("--project-id")
    xrd_prepare_review.add_argument("--candidate-id", action="append", default=[])
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
    xrd_report.add_argument("--assignment-suggestion", action="append", default=[], type=Path)
    xrd_report.add_argument("--assignment-review-ref", action="append", default=[])

    ftir = sub.add_parser("ftir", help="FTIR inspection, processing, and report helpers")
    ftir_sub = ftir.add_subparsers(dest="ftir_command", required=True)
    ftir_list_libraries = ftir_sub.add_parser("list-assignment-libraries", help="list built-in FTIR assignment libraries and candidates")
    ftir_list_libraries.add_argument("--builtin-library", action="append", choices=builtin_ftir_assignment_libraries(), default=[])
    ftir_list_libraries.add_argument("--include-candidate", action="append", default=[])
    ftir_list_libraries.add_argument("--assignment-type", action="append", default=[])
    ftir_list_libraries.add_argument("--material-scope", action="append", default=[])
    ftir_list_libraries.add_argument("--wavenumber-min-cm1", type=float)
    ftir_list_libraries.add_argument("--wavenumber-max-cm1", type=float)
    ftir_inspect = ftir_sub.add_parser("inspect", help="inspect an infrared spectrum file and suggest FTIR columns/unit")
    ftir_inspect.add_argument("workspace", type=Path)
    ftir_inspect.add_argument("spectrum", type=Path)
    ftir_process = ftir_sub.add_parser("process", help="run review-gated FTIR processing")
    ftir_process.add_argument("workspace", type=Path)
    ftir_process.add_argument("--metadata", required=True, type=Path)
    ftir_process.add_argument("--project-id")
    ftir_process.add_argument("--sample-ref", action="append", default=[])
    ftir_process.add_argument("--x-column", required=True)
    ftir_process.add_argument("--y-column", required=True)
    ftir_process.add_argument("--x-unit", choices=["cm^-1", "unknown"], required=True)
    ftir_process.add_argument("--signal-mode", choices=["absorbance", "transmittance"], required=True)
    ftir_process.add_argument("--column-review-ref", required=True)
    ftir_process.add_argument("--parameter-review-ref", required=True)
    ftir_process.add_argument("--parameters-file", type=Path)
    ftir_process.add_argument("--parameters-json")
    ftir_report = ftir_sub.add_parser("report", help="generate an FTIR analysis report from FTIR metadata")
    ftir_report.add_argument("workspace", type=Path)
    ftir_report.add_argument("--metadata", required=True, type=Path)
    ftir_report.add_argument("--project-id")
    ftir_report.add_argument("--experiment-ref", action="append", default=[])
    ftir_report.add_argument("--sample-ref", action="append", default=[])
    ftir_report.add_argument("--reference-id", action="append", default=[])
    ftir_report.add_argument("--assignment-suggestion", action="append", type=Path, default=[])
    ftir_suggest = ftir_sub.add_parser("suggest-assignments", help="record source-backed FTIR band-assignment suggestions without applying them")
    ftir_suggest.add_argument("workspace", type=Path)
    ftir_suggest.add_argument("--metadata", required=True, type=Path)
    ftir_suggest.add_argument("--source-file", required=True, type=Path)
    ftir_suggest.add_argument("--project-id")
    ftir_suggest.add_argument("--related-record", action="append", default=[])
    ftir_prepare_review = ftir_sub.add_parser("prepare-review", help="prepare a grouped review package from FTIR assignment suggestions")
    ftir_prepare_review.add_argument("workspace", type=Path)
    ftir_prepare_review.add_argument("--suggestion", required=True, type=Path)
    ftir_prepare_review.add_argument("--project-id")
    ftir_prepare_review.add_argument("--candidate-id", action="append", default=[])
    ftir_memory = ftir_sub.add_parser("propose-memory", help="propose draft memory candidates from reviewed FTIR assignment suggestions")
    ftir_memory.add_argument("workspace", type=Path)
    ftir_memory.add_argument("--suggestion", required=True, type=Path)
    ftir_memory.add_argument("--review-ref", required=True)
    ftir_memory.add_argument("--project-id")
    ftir_memory.add_argument("--candidate-id", action="append", default=[])
    ftir_memory.add_argument("--allow-non-ready", action="store_true")
    ftir_source_packet = ftir_sub.add_parser("build-assignment-packet", help="build a standard FTIR assignment source packet")
    ftir_source_packet.add_argument("workspace", type=Path)
    ftir_source_packet.add_argument("--library-file", type=Path)
    ftir_source_packet.add_argument("--builtin-library", choices=builtin_ftir_assignment_libraries(), help="use a bundled FTIR assignment library; defaults to generic_materials when no library file or template is supplied")
    ftir_source_packet.add_argument("--literature-manifest", type=Path, help="build from a user-confirmed literature/source-candidate manifest")
    ftir_source_packet.add_argument("--output", type=Path)
    ftir_source_packet.add_argument("--project-id")
    ftir_source_packet.add_argument("--include-candidate", action="append", default=[])
    ftir_source_packet.add_argument("--assignment-type", action="append", default=[])
    ftir_source_packet.add_argument("--material-scope", action="append", default=[])
    ftir_source_packet.add_argument("--write-template", action="store_true")

    uv_vis = sub.add_parser("uv-vis", help="UV-Vis inspection, processing, and report helpers")
    uv_vis_sub = uv_vis.add_subparsers(dest="uv_vis_command", required=True)
    uv_vis_list_libraries = uv_vis_sub.add_parser("list-source-libraries", help="list built-in UV-Vis source libraries and candidates")
    uv_vis_list_libraries.add_argument("--builtin-library", action="append", choices=builtin_uv_vis_source_libraries(), default=[])
    uv_vis_list_libraries.add_argument("--include-candidate", action="append", default=[])
    uv_vis_list_libraries.add_argument(
        "--candidate-type",
        action="append",
        choices=[
            "optical_transition_model",
            "optical_gap_candidate",
            "optical_feature_assignment",
            "correction_context_candidate",
        ],
        default=[],
    )
    uv_vis_list_libraries.add_argument("--optical-target", action="append", default=[])
    uv_vis_list_libraries.add_argument("--energy-min-ev", type=float)
    uv_vis_list_libraries.add_argument("--energy-max-ev", type=float)
    uv_vis_list_libraries.add_argument("--wavelength-min-nm", type=float)
    uv_vis_list_libraries.add_argument("--wavelength-max-nm", type=float)
    uv_vis_inspect = uv_vis_sub.add_parser("inspect", help="inspect an optical spectrum file and suggest UV-Vis columns/unit")
    uv_vis_inspect.add_argument("workspace", type=Path)
    uv_vis_inspect.add_argument("spectrum", type=Path)
    uv_vis_process = uv_vis_sub.add_parser("process", help="run review-gated UV-Vis processing")
    uv_vis_process.add_argument("workspace", type=Path)
    uv_vis_process.add_argument("--metadata", required=True, type=Path)
    uv_vis_process.add_argument("--project-id")
    uv_vis_process.add_argument("--sample-ref", action="append", default=[])
    uv_vis_process.add_argument("--x-column", required=True)
    uv_vis_process.add_argument("--y-column", required=True)
    uv_vis_process.add_argument("--x-unit", choices=["nm", "eV", "unknown"], required=True)
    uv_vis_process.add_argument("--signal-mode", choices=["absorbance", "transmittance", "reflectance"], required=True)
    uv_vis_process.add_argument("--column-review-ref", required=True)
    uv_vis_process.add_argument("--parameter-review-ref", required=True)
    uv_vis_process.add_argument("--parameters-file", type=Path)
    uv_vis_process.add_argument("--parameters-json")
    uv_vis_report = uv_vis_sub.add_parser("report", help="generate a UV-Vis analysis report from UV-Vis metadata")
    uv_vis_report.add_argument("workspace", type=Path)
    uv_vis_report.add_argument("--metadata", required=True, type=Path)
    uv_vis_report.add_argument("--project-id")
    uv_vis_report.add_argument("--experiment-ref", action="append", default=[])
    uv_vis_report.add_argument("--sample-ref", action="append", default=[])
    uv_vis_report.add_argument("--reference-id", action="append", default=[])
    uv_vis_report.add_argument("--interpretation-suggestion", action="append", default=[], type=Path)
    uv_vis_report.add_argument("--interpretation-review-ref", action="append", default=[])
    uv_vis_source_packet = uv_vis_sub.add_parser("build-source-packet", help="build a standard UV-Vis source packet")
    uv_vis_source_packet.add_argument("workspace", type=Path)
    uv_vis_source_packet.add_argument("--library-file", type=Path)
    uv_vis_source_packet.add_argument("--builtin-library", choices=builtin_uv_vis_source_libraries(), help="use a bundled UV-Vis source library")
    uv_vis_source_packet.add_argument("--literature-manifest", type=Path, help="build from a user-confirmed UV-Vis literature/source-candidate manifest")
    uv_vis_source_packet.add_argument("--output", type=Path)
    uv_vis_source_packet.add_argument("--project-id")
    uv_vis_source_packet.add_argument("--include-candidate", action="append", default=[])
    uv_vis_source_packet.add_argument(
        "--candidate-type",
        action="append",
        choices=[
            "optical_transition_model",
            "optical_gap_candidate",
            "optical_feature_assignment",
            "correction_context_candidate",
        ],
        default=[],
    )
    uv_vis_source_packet.add_argument("--optical-target", action="append", default=[])
    uv_vis_source_packet.add_argument("--write-template", action="store_true")
    uv_vis_suggest = uv_vis_sub.add_parser("suggest-interpretations", help="create source-backed UV-Vis interpretation suggestion records")
    uv_vis_suggest.add_argument("workspace", type=Path)
    uv_vis_suggest.add_argument("--metadata", required=True, type=Path)
    uv_vis_suggest.add_argument("--source-file", required=True, type=Path)
    uv_vis_suggest.add_argument("--project-id")
    uv_vis_suggest.add_argument("--related-record", action="append", default=[])
    uv_vis_prepare_review = uv_vis_sub.add_parser("prepare-review", help="prepare a grouped review package from UV-Vis interpretation suggestions")
    uv_vis_prepare_review.add_argument("workspace", type=Path)
    uv_vis_prepare_review.add_argument("--suggestion", required=True, type=Path)
    uv_vis_prepare_review.add_argument("--project-id")
    uv_vis_prepare_review.add_argument("--candidate-id", action="append", default=[])
    uv_vis_memory = uv_vis_sub.add_parser("propose-memory", help="propose draft memory candidates from reviewed UV-Vis interpretation suggestions")
    uv_vis_memory.add_argument("workspace", type=Path)
    uv_vis_memory.add_argument("--suggestion", required=True, type=Path)
    uv_vis_memory.add_argument("--review-ref", required=True)
    uv_vis_memory.add_argument("--project-id")
    uv_vis_memory.add_argument("--candidate-id", action="append", default=[])
    uv_vis_memory.add_argument("--allow-non-ready", action="store_true")
    uv_vis_compare = uv_vis_sub.add_parser("compare-replicates", help="compare multiple processed UV-Vis metadata records with descriptive statistics")
    uv_vis_compare.add_argument("workspace", type=Path)
    uv_vis_compare.add_argument("--metadata", required=True, action="append", type=Path)
    uv_vis_compare.add_argument("--project-id")
    uv_vis_compare.add_argument("--comparison-label")
    uv_vis_compare.add_argument("--feature-match-tolerance-ev", type=float)
    uv_vis_compare.add_argument("--feature-match-tolerance-nm", type=float)
    uv_vis_compare.add_argument("--feature-match-review-ref")

    xps = sub.add_parser("xps", help="XPS inspection, processing, and report helpers")
    xps_sub = xps.add_subparsers(dest="xps_command", required=True)
    xps_list_libraries = xps_sub.add_parser("list-parameter-libraries", help="list built-in XPS parameter libraries and candidates")
    xps_list_libraries.add_argument("--builtin-library", action="append", choices=builtin_xps_parameter_libraries(), default=[])
    xps_list_libraries.add_argument("--include-candidate", action="append", default=[])
    xps_list_libraries.add_argument(
        "--suggestion-type",
        action="append",
        choices=["spin_orbit_constraint", "tougaard_parameter", "binding_energy_candidate"],
        default=[],
    )
    xps_list_libraries.add_argument("--element", action="append", default=[])
    xps_list_libraries.add_argument("--core-level", action="append", default=[])
    xps_inspect = xps_sub.add_parser("inspect", help="inspect a surface spectroscopy file and suggest XPS columns/unit")
    xps_inspect.add_argument("workspace", type=Path)
    xps_inspect.add_argument("spectrum", type=Path)
    xps_process = xps_sub.add_parser("process", help="run review-gated XPS processing")
    xps_process.add_argument("workspace", type=Path)
    xps_process.add_argument("--metadata", required=True, type=Path)
    xps_process.add_argument("--project-id")
    xps_process.add_argument("--sample-ref", action="append", default=[])
    xps_process.add_argument("--x-column", required=True)
    xps_process.add_argument("--y-column", required=True)
    xps_process.add_argument("--x-unit", choices=["eV", "unknown"], required=True)
    xps_process.add_argument("--energy-shift-ev", type=float, default=0.0)
    xps_process.add_argument("--calibration-reference", default="")
    xps_process.add_argument("--column-review-ref", required=True)
    xps_process.add_argument("--calibration-review-ref", required=True)
    xps_process.add_argument("--parameter-review-ref", required=True)
    xps_process.add_argument("--parameters-file", type=Path)
    xps_process.add_argument("--parameters-json")
    xps_report = xps_sub.add_parser("report", help="generate an XPS analysis report from XPS metadata")
    xps_report.add_argument("workspace", type=Path)
    xps_report.add_argument("--metadata", required=True, type=Path)
    xps_report.add_argument("--project-id")
    xps_report.add_argument("--experiment-ref", action="append", default=[])
    xps_report.add_argument("--sample-ref", action="append", default=[])
    xps_report.add_argument("--reference-id", action="append", default=[])
    xps_report.add_argument("--parameter-suggestion", action="append", type=Path, default=[])
    xps_suggest = xps_sub.add_parser("suggest-parameters", help="record source-backed XPS parameter suggestions without applying them")
    xps_suggest.add_argument("workspace", type=Path)
    xps_suggest.add_argument("--source-file", required=True, type=Path)
    xps_suggest.add_argument("--project-id")
    xps_suggest.add_argument("--related-record", action="append", default=[])
    xps_prepare_review = xps_sub.add_parser("prepare-review", help="prepare a grouped review package from XPS parameter suggestions")
    xps_prepare_review.add_argument("workspace", type=Path)
    xps_prepare_review.add_argument("--suggestion", required=True, type=Path)
    xps_prepare_review.add_argument("--project-id")
    xps_prepare_review.add_argument("--candidate-id", action="append", default=[])
    xps_memory = xps_sub.add_parser("propose-memory", help="propose draft memory candidates from reviewed XPS parameter suggestions")
    xps_memory.add_argument("workspace", type=Path)
    xps_memory.add_argument("--suggestion", required=True, type=Path)
    xps_memory.add_argument("--review-ref", required=True)
    xps_memory.add_argument("--project-id")
    xps_memory.add_argument("--candidate-id", action="append", default=[])
    xps_memory.add_argument("--allow-non-ready", action="store_true")
    xps_source_packet = xps_sub.add_parser("build-source-packet", help="build a standard XPS parameter source packet")
    xps_source_packet.add_argument("workspace", type=Path)
    xps_source_packet.add_argument("--library-file", type=Path)
    xps_source_packet.add_argument("--builtin-library", choices=builtin_xps_parameter_libraries(), help="use a bundled XPS parameter library; defaults to generic_xps_parameters when no library file or template is supplied")
    xps_source_packet.add_argument("--literature-manifest", type=Path, help="build from a user-confirmed literature/source-candidate manifest")
    xps_source_packet.add_argument("--output", type=Path)
    xps_source_packet.add_argument("--project-id")
    xps_source_packet.add_argument("--include-candidate", action="append", default=[])
    xps_source_packet.add_argument(
        "--suggestion-type",
        action="append",
        choices=["spin_orbit_constraint", "tougaard_parameter", "binding_energy_candidate"],
        default=[],
    )
    xps_source_packet.add_argument("--element", action="append", default=[])
    xps_source_packet.add_argument("--core-level", action="append", default=[])
    xps_source_packet.add_argument("--write-template", action="store_true")

    electrochemistry = sub.add_parser("electrochemistry", help="Electrochemistry inspection, processing, and report helpers")
    electrochemistry_sub = electrochemistry.add_subparsers(dest="electrochemistry_command", required=True)
    electrochemistry_inspect = electrochemistry_sub.add_parser("inspect", help="inspect tabular electrochemistry data and suggest columns/units/mode")
    electrochemistry_inspect.add_argument("workspace", type=Path)
    electrochemistry_inspect.add_argument("spectrum", type=Path)
    electrochemistry_process = electrochemistry_sub.add_parser("process", help="run review-gated electrochemistry processing")
    electrochemistry_process.add_argument("workspace", type=Path)
    electrochemistry_process.add_argument("--metadata", required=True, type=Path)
    electrochemistry_process.add_argument("--project-id")
    electrochemistry_process.add_argument("--sample-ref", action="append", default=[])
    electrochemistry_process.add_argument("--x-column", required=True)
    electrochemistry_process.add_argument("--y-column", required=True)
    electrochemistry_process.add_argument("--x-unit", choices=["V", "mV", "s", "ohm", "unknown"], required=True)
    electrochemistry_process.add_argument("--current-unit", choices=["A", "mA", "uA", "µA", "unknown"], required=True)
    electrochemistry_process.add_argument("--measurement-mode", choices=["cv", "lsv", "chrono", "gcd", "eis", "unknown"], required=True)
    electrochemistry_process.add_argument("--context-summary", default="")
    electrochemistry_process.add_argument("--electrode-area-cm2", type=float)
    electrochemistry_process.add_argument("--column-review-ref", required=True)
    electrochemistry_process.add_argument("--context-review-ref", required=True)
    electrochemistry_process.add_argument("--parameter-review-ref", required=True)
    electrochemistry_process.add_argument("--parameters-file", type=Path)
    electrochemistry_process.add_argument("--parameters-json")
    electrochemistry_report = electrochemistry_sub.add_parser("report", help="generate an electrochemistry analysis report from electrochemistry metadata")
    electrochemistry_report.add_argument("workspace", type=Path)
    electrochemistry_report.add_argument("--metadata", required=True, type=Path)
    electrochemistry_report.add_argument("--project-id")
    electrochemistry_report.add_argument("--experiment-ref", action="append", default=[])
    electrochemistry_report.add_argument("--sample-ref", action="append", default=[])
    electrochemistry_report.add_argument("--reference-id", action="append", default=[])

    thermal = sub.add_parser("thermal", help="Thermal analysis inspection, processing, and report helpers")
    thermal_sub = thermal.add_subparsers(dest="thermal_command", required=True)
    thermal_inspect = thermal_sub.add_parser("inspect", help="inspect tabular TGA/DSC/DTG data and suggest columns/units/mode")
    thermal_inspect.add_argument("workspace", type=Path)
    thermal_inspect.add_argument("data", type=Path)
    thermal_process = thermal_sub.add_parser("process", help="run review-gated thermal analysis processing")
    thermal_process.add_argument("workspace", type=Path)
    thermal_process.add_argument("--metadata", required=True, type=Path)
    thermal_process.add_argument("--project-id")
    thermal_process.add_argument("--sample-ref", action="append", default=[])
    thermal_process.add_argument("--temperature-column", required=True)
    thermal_process.add_argument("--signal-column", required=True)
    thermal_process.add_argument("--temperature-unit", choices=["C", "K", "unknown"], required=True)
    thermal_process.add_argument("--signal-unit", choices=["%", "mg", "mW", "W/g", "mW/mg", "unknown"], required=True)
    thermal_process.add_argument("--measurement-mode", choices=["tga", "dsc", "dtg", "unknown"], required=True)
    thermal_process.add_argument("--context-summary", default="")
    thermal_process.add_argument("--column-review-ref", required=True)
    thermal_process.add_argument("--context-review-ref", required=True)
    thermal_process.add_argument("--parameter-review-ref", required=True)
    thermal_process.add_argument("--parameters-file", type=Path)
    thermal_process.add_argument("--parameters-json")
    thermal_report = thermal_sub.add_parser("report", help="generate a thermal analysis report from thermal metadata")
    thermal_report.add_argument("workspace", type=Path)
    thermal_report.add_argument("--metadata", required=True, type=Path)
    thermal_report.add_argument("--project-id")
    thermal_report.add_argument("--experiment-ref", action="append", default=[])
    thermal_report.add_argument("--sample-ref", action="append", default=[])
    thermal_report.add_argument("--reference-id", action="append", default=[])

    batch = sub.add_parser("batch", help="validate and run batch characterization manifests")
    batch_sub = batch.add_subparsers(dest="batch_command", required=True)
    batch_validate = batch_sub.add_parser("validate", help="validate a batch characterization manifest")
    batch_validate.add_argument("workspace", type=Path)
    batch_validate.add_argument("manifest", type=Path)
    batch_run = batch_sub.add_parser("run", help="run a review-gated batch characterization manifest")
    batch_run.add_argument("workspace", type=Path)
    batch_run.add_argument("manifest", type=Path)

    templates = sub.add_parser("templates", help="write editable EA YAML templates")
    templates_sub = templates.add_subparsers(dest="templates_command", required=True)
    parameter_template = templates_sub.add_parser("parameters", help="show or write method processing parameters")
    template_method_choices = list(SUPPORTED_TEMPLATE_METHODS) + ["uv-vis", "thermal"]
    parameter_template.add_argument("method", choices=template_method_choices)
    parameter_template.add_argument("--output", type=Path)
    batch_template = templates_sub.add_parser("batch-manifest", help="show or write a batch manifest skeleton")
    batch_template.add_argument("workspace", type=Path)
    batch_template.add_argument("--output", type=Path)
    batch_template.add_argument("--method", choices=template_method_choices, action="append", default=[])
    batch_template.add_argument("--project-id")
    batch_template.add_argument("--sample-ref", default="sample-001")
    batch_template.add_argument("--experiment-ref", default="exp-001")
    batch_template.add_argument("--no-reports", action="store_true")
    batch_template.add_argument("--stop-on-error", action="store_true")

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
    lit_rank = literature_sub.add_parser("rank-candidates", help="rank supplied literature candidates without live search or download")
    lit_rank.add_argument("workspace", type=Path)
    lit_rank.add_argument("--candidates", required=True, type=Path)
    lit_rank.add_argument("--top-n", type=int)
    lit_rank.add_argument("--reference-year", type=int)
    lit_rank.add_argument("--source-label")
    lit_rank.add_argument("--keyword", action="append", default=[])
    lit_search = literature_sub.add_parser("search-public", help="query public metadata APIs and rank candidates")
    lit_search.add_argument("workspace", type=Path)
    lit_search.add_argument("--source", action="append", choices=["crossref", "openalex", "arxiv"], default=[])
    lit_search.add_argument("--max-results", type=int, default=20)
    lit_search.add_argument("--query-limit", type=int, default=3)
    lit_search.add_argument("--page-limit", type=int, default=1)
    lit_search.add_argument("--delay-seconds", type=float, default=0.0)
    lit_search.add_argument("--resume", action="store_true")
    lit_search.add_argument("--top-n", type=int)
    lit_search.add_argument("--reference-year", type=int)
    lit_search.add_argument("--keyword", action="append", default=[])
    lit_search.add_argument("--confirm-large-work", action="store_true")
    lit_handoff = literature_sub.add_parser("handoff", help="prepare an acquisition handoff packet for a dedicated literature workflow")
    lit_handoff.add_argument("workspace", type=Path)
    lit_handoff.add_argument("--mode", choices=["dedicated_thread", "manual_agent", "same_thread"], default="dedicated_thread")
    lit_handoff.add_argument("--literature-thread-id")
    lit_request = literature_sub.add_parser("acquisition-request", help="prepare confirmed acquisition request and Zotero-Codex target manifests")
    lit_request.add_argument("workspace", type=Path)
    lit_request.add_argument("--confirm-large-work", action="store_true")
    lit_setup = literature_sub.add_parser("setup-preflight", help="diagnose literature setup readiness without launching Zotero/browser/downloads")
    lit_setup.add_argument("workspace", type=Path)
    lit_setup.add_argument("--lang", choices=["zh", "en"], default="zh")
    lit_setup.add_argument("--no-write", action="store_true")
    lit_access = literature_sub.add_parser("institution-access-guide", help="prepare public-safe institution access guidance")
    lit_access.add_argument("workspace", type=Path)
    lit_access.add_argument("--institution-name")
    lit_access.add_argument("--access-method")
    lit_access.add_argument("--access-url")
    lit_access.add_argument("--access-instructions")
    lit_access.add_argument("--browser-name")
    lit_access.add_argument("--browser-profile", type=Path)
    lit_access.add_argument("--zotero-config", type=Path)
    lit_access.add_argument("--cache-root", type=Path)
    lit_access.add_argument("--project-collection")
    lit_access.add_argument("--authorization-status")
    lit_access.add_argument("--note", action="append", default=[])
    lit_bridge = literature_sub.add_parser("zotero-bridge", help="prepare a Zotero-Codex acquisition bridge runbook")
    lit_bridge.add_argument("workspace", type=Path)
    lit_bridge.add_argument("--zotero-config", type=Path)
    lit_bridge.add_argument("--allow-default-config", action="store_true")
    lit_bridge.add_argument("--cache-root", type=Path)
    lit_bridge.add_argument("--project-collection")
    lit_bridge.add_argument("--enable-browser-assist", action="store_true")
    lit_bridge.add_argument("--browser-name")
    lit_bridge.add_argument("--browser-profile", type=Path)
    lit_bridge.add_argument("--institution-access")
    lit_readiness = literature_sub.add_parser("zotero-readiness", help="summarize EA readiness for Zotero-Codex literature handoff/import")
    lit_readiness.add_argument("workspace", type=Path)
    lit_readiness.add_argument("--no-write", action="store_true")
    lit_readiness.add_argument("--output", type=Path)
    lit_readiness.add_argument("--markdown-output", type=Path)
    lit_readiness.add_argument("--full", action="store_true")
    lit_import = literature_sub.add_parser("import-acquisition", help="import acquisition manifest output from a dedicated literature workflow")
    lit_import.add_argument("workspace", type=Path)
    lit_import.add_argument("--manifest", required=True, type=Path)
    lit_zotero_status = literature_sub.add_parser("import-zotero-status", help="import Zotero-Codex batch status into EA sync records")
    lit_zotero_status.add_argument("workspace", type=Path)
    lit_zotero_status.add_argument("--batch-status", type=Path)
    lit_zotero_status.add_argument("--sidecar-verification", type=Path)
    lit_zotero_status.add_argument("--status-markdown", type=Path)
    lit_zotero_status.add_argument("--no-sync", action="store_true")
    lit_zotero_status.add_argument("--full", action="store_true")
    lit_reconcile = literature_sub.add_parser("reconcile-acquisition", help="reconcile local literature acquisition records")
    lit_reconcile.add_argument("workspace", type=Path)
    lit_reconcile.add_argument("--full", action="store_true")
    lit_render_reconciliation = literature_sub.add_parser("render-reconciliation", help="render acquisition reconciliation markdown audit")
    lit_render_reconciliation.add_argument("workspace", type=Path)
    lit_render_reconciliation.add_argument("--reconciliation", type=Path)
    lit_acceptance = literature_sub.add_parser("acceptance-checklist", help="write a public-user literature workflow acceptance checklist")
    lit_acceptance.add_argument("workspace", type=Path)
    lit_acceptance.add_argument("--output", type=Path)
    lit_acceptance.add_argument("--markdown-output", type=Path)
    lit_sync = literature_sub.add_parser("sync-status", help="sync acquisition workflow status back into the origin project")
    lit_sync.add_argument("workspace", type=Path)
    lit_sync.add_argument("--update", type=Path)
    lit_prepare_sources = literature_sub.add_parser(
        "prepare-source-candidates",
        help="prepare an editable FTIR/UV-Vis/XPS source-candidate manifest from local literature items",
    )
    lit_prepare_sources.add_argument("workspace", type=Path)
    lit_prepare_sources.add_argument("--method", required=True, choices=["ftir", "uv_vis", "xps"])
    lit_prepare_sources.add_argument("--source-items", type=Path)
    lit_prepare_sources.add_argument("--output", type=Path)
    lit_prepare_sources.add_argument("--confirm-for-source-packet", action="store_true")
    lit_prepare_sources.add_argument("--user-response")
    lit_prepare_sources.add_argument("--max-items", type=int)
    lit_prepare_sources.add_argument("--confirm-large-work", action="store_true")
    lit_preflight_sources = literature_sub.add_parser(
        "preflight-source-candidates",
        help="preflight a confirmed FTIR/UV-Vis/XPS source-candidate manifest",
    )
    lit_preflight_sources.add_argument("workspace", type=Path)
    lit_preflight_sources.add_argument("--method", required=True, choices=["ftir", "uv_vis", "xps"])
    lit_preflight_sources.add_argument("--manifest", required=True, type=Path)
    lit_preflight_sources.add_argument("--output", type=Path)
    lit_data_plan = literature_sub.add_parser("data-plan", help="define a beta cross-paper property evidence dataset")
    lit_data_plan.add_argument("workspace", type=Path)
    lit_data_plan.add_argument("--property", required=True)
    lit_data_plan.add_argument("--kind", required=True, choices=sorted(PROPERTY_KINDS))
    lit_data_plan.add_argument("--material", required=True)
    lit_data_plan.add_argument("--dataset-id")
    lit_data_plan.add_argument("--source", action="append", type=Path, default=[])
    lit_data_plan.add_argument("--required-condition", action="append", default=[])
    lit_data_plan.add_argument("--comparability-rule", action="append", default=[])
    lit_data_plan.add_argument("--yes", action="store_true")
    lit_data_extract = literature_sub.add_parser("data-extract", help="extract resumable beta candidate values from searchable sources")
    lit_data_extract.add_argument("workspace", type=Path)
    lit_data_extract.add_argument("--dataset", required=True)
    lit_data_extract.add_argument("--max-sources", type=int)
    lit_data_extract.add_argument("--yes", action="store_true")
    lit_data_review = literature_sub.add_parser("data-review", help="review one extracted literature value")
    lit_data_review.add_argument("workspace", type=Path)
    lit_data_review.add_argument("--dataset", required=True)
    lit_data_review.add_argument("--record", required=True)
    lit_data_review.add_argument("--decision", required=True, choices=sorted(REVIEW_DECISIONS | {"not-comparable"}))
    lit_data_review.add_argument("--note", action="append", default=[])
    lit_data_review.add_argument("--reported-value", type=float)
    lit_data_review.add_argument("--reported-unit")
    lit_data_review.add_argument("--normalized-value", type=float)
    lit_data_review.add_argument("--normalized-unit")
    lit_data_review.add_argument("--condition", action="append", default=[], help="reviewed condition as name=value")
    lit_data_review.add_argument("--yes", action="store_true")
    lit_data_validate = literature_sub.add_parser("data-validate", help="validate beta evidence anchors, review state, units, and comparability")
    lit_data_validate.add_argument("workspace", type=Path)
    lit_data_validate.add_argument("--dataset", required=True)
    lit_data_validate.add_argument("--no-write", action="store_true")
    lit_data_plot = literature_sub.add_parser("data-plot", help="plot reviewed comparable literature records only")
    lit_data_plot.add_argument("workspace", type=Path)
    lit_data_plot.add_argument("--dataset", required=True)
    lit_data_plot.add_argument("--yes", action="store_true")
    lit_data_export = literature_sub.add_parser("data-export", help="export a reviewed beta evidence dataset bundle")
    lit_data_export.add_argument("workspace", type=Path)
    lit_data_export.add_argument("--dataset", required=True)
    lit_data_export.add_argument("--yes", action="store_true")

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
    ref_seed = references_sub.add_parser("register-seeds", help="explicitly register reference_seeds from a source packet")
    ref_seed.add_argument("workspace", type=Path)
    ref_seed.add_argument("--source-packet", required=True, type=Path)
    ref_seed.add_argument("--project-id")
    ref_seed.add_argument("--seed-id", action="append", default=[])
    ref_seed.add_argument("--source-type", choices=["literature_library", "manual", "web", "local_pdf", "report"], default="manual")
    ref_seed.add_argument("--dry-run", action="store_true")
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
    memory_refresh_project = memory_sub.add_parser("refresh-project", help="refresh compact project working memory")
    memory_refresh_project.add_argument("workspace", type=Path)
    memory_refresh_project.add_argument("--project-id")
    memory_refresh_project.add_argument("--max-items", type=int, default=8)
    memory_show_project = memory_sub.add_parser("show-project", help="show compact project working memory")
    memory_show_project.add_argument("workspace", type=Path)
    memory_show_project.add_argument("--full", action="store_true")

    estimate = sub.add_parser("estimate", help="estimate unusually large EA workflows before running them")
    estimate_sub = estimate.add_subparsers(dest="estimate_command", required=True)
    estimate_work = estimate_sub.add_parser("workflow", help="estimate a literature/report/handoff workflow")
    estimate_work.add_argument("workspace", type=Path)
    estimate_work.add_argument(
        "--workflow",
        required=True,
        choices=[
            "literature_search",
            "literature_acquisition",
            "literature_source_candidates",
            "literature_data_extraction",
            "literature_ocr",
            "literature_digitization",
            "analysis_report",
            "multi_method_report_bundle",
            "project_handoff",
        ],
    )
    estimate_work.add_argument("--items", type=int)
    estimate_work.add_argument("--mode", choices=["brief", "standard", "full"], default="standard")
    estimate_reminders = estimate_sub.add_parser("reminders", help="show or change large-work reminder preference for one project")
    estimate_reminders.add_argument("workspace", type=Path)
    reminder_group = estimate_reminders.add_mutually_exclusive_group()
    reminder_group.add_argument("--disable", action="store_true")
    reminder_group.add_argument("--enable", action="store_true")
    estimate_reminders.add_argument("--reason")

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

    materials = sub.add_parser("materials", help="inspect built-in material assignment records")
    materials_sub = materials.add_subparsers(dest="materials_command", required=True)
    materials_sub.add_parser("list", help="list materials with built-in assignment records")
    materials_audit = materials_sub.add_parser("audit-assignment-library", help="audit built-in assignment candidate and reference-hint coverage")
    materials_audit.add_argument("--material", action="append", default=[])
    materials_audit.add_argument("--method", action="append", choices=["raman", "pl", "xrd"], default=[])
    material_show = materials_sub.add_parser("show", help="show a material assignment profile")
    material_show.add_argument("material")
    material_assignments = materials_sub.add_parser("assignments", help="show assignment records for one method")
    material_assignments.add_argument("material")
    material_assignments.add_argument("--method", choices=["raman", "pl", "xrd"])

    trace = sub.add_parser("trace", help="build local traceability views across reports, figures, reviews, suggestions, and memory")
    trace_sub = trace.add_subparsers(dest="trace_command", required=True)
    trace_index = trace_sub.add_parser("index", help="write a compact project traceability index")
    trace_index.add_argument("workspace", type=Path)
    trace_index.add_argument("--output", type=Path)
    trace_index.add_argument("--json", action="store_true")
    trace_index.add_argument("--json-full", action="store_true")
    trace_view = trace_sub.add_parser("view", help="write a project traceability YAML/Markdown view")
    trace_view.add_argument("workspace", type=Path)
    trace_view.add_argument("--focus")
    trace_view.add_argument("--output", type=Path)
    trace_view.add_argument("--markdown-output", type=Path)
    trace_view.add_argument("--json", action="store_true")
    trace_view.add_argument("--json-full", action="store_true")
    trace_focus = trace_sub.add_parser("focus", help="write a depth-limited focus subgraph for one record")
    trace_focus.add_argument("workspace", type=Path)
    trace_focus.add_argument("record_ref")
    trace_focus.add_argument("--depth", type=int, default=2)
    trace_focus.add_argument("--output", type=Path)
    trace_focus.add_argument("--markdown-output", type=Path)
    trace_focus.add_argument("--json", action="store_true")
    trace_focus.add_argument("--json-full", action="store_true")
    trace_export = trace_sub.add_parser("export", help="export traceability artifacts")
    trace_export.add_argument("workspace", type=Path)
    trace_export.add_argument("--full", action="store_true", help="write the full project trace graph to disk")
    trace_export.add_argument("--output", type=Path)
    trace_export.add_argument("--markdown-output", type=Path)
    trace_export.add_argument("--json", action="store_true")
    trace_export.add_argument("--json-full", action="store_true")
    trace_lookup = trace_sub.add_parser("lookup", help="resolve one report/figure/result/reference/review/suggestion/memory ID through the trace graph")
    trace_lookup.add_argument("workspace", type=Path)
    trace_lookup.add_argument("record_ref")
    trace_lookup.add_argument("--output", type=Path)
    trace_lookup.add_argument("--markdown-output", type=Path)
    trace_lookup.add_argument("--json", action="store_true")
    trace_lookup.add_argument("--json-full", action="store_true")

    figure = sub.add_parser("lookup-figure", help="look up a figure by figure_id")
    figure.add_argument("workspace", type=Path)
    figure.add_argument("figure_id")

    return parser


def _print_json(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _compact_brief_result(result: dict) -> dict:
    keys = {
        "schema_version",
        "brief_type",
        "created_at",
        "workspace",
        "brief_id",
        "yaml_path",
        "markdown_path",
        "project",
        "evaluation",
        "key_outputs",
        "project_working_memory",
        "needs_user_confirmation",
        "next_actions",
        "scope",
    }
    return {key: value for key, value in result.items() if key in keys}


def _print_brief_summary(result: dict) -> None:
    project = result.get("project") or {}
    evaluation = result.get("evaluation") or {}
    key_outputs = result.get("key_outputs") or {}
    print("EA project brief")
    print(f"- status: {evaluation.get('status', 'unknown')}")
    print(f"- project: {project.get('project_id') or project.get('name') or 'unknown'}")
    if result.get("markdown_path"):
        print(f"- markdown: {result['markdown_path']}")
    if result.get("yaml_path"):
        print(f"- yaml: {result['yaml_path']}")
    print(f"- reports: {len(key_outputs.get('reports') or [])}")
    print(f"- next_actions: {len(result.get('next_actions') or [])}")
    if result.get("needs_user_confirmation"):
        print(f"- needs_user_confirmation: {len(result['needs_user_confirmation'])}")


def _compact_trace_result(result: dict) -> dict:
    keys = {
        "schema_version",
        "source",
        "status",
        "trace_id",
        "index_id",
        "trace_ref",
        "index_ref",
        "markdown_ref",
        "node_count",
        "edge_count",
        "missing_node_count",
        "focus_ref",
        "canonical_focus_ref",
        "focus_depth",
        "export_mode",
    }
    compact = {key: value for key, value in result.items() if key in keys}
    if "query" in result:
        related = result.get("related") or {}
        compact.update(
            {
                "query": result.get("query"),
                "canonical_ref": result.get("canonical_ref"),
                "node": result.get("node"),
                "related": {
                    "incoming_count": related.get("incoming_count", 0),
                    "outgoing_count": related.get("outgoing_count", 0),
                },
                "trace_ref": result.get("trace_ref"),
                "markdown_ref": result.get("markdown_ref"),
            }
        )
    return {key: value for key, value in compact.items() if value not in (None, "", [], {})}


def _print_trace_summary(result: dict, *, label: str) -> None:
    compact = _compact_trace_result(result)
    print(f"EA trace {label}")
    for key in [
        "status",
        "index_ref",
        "trace_ref",
        "markdown_ref",
        "focus_ref",
        "canonical_focus_ref",
        "focus_depth",
        "node_count",
        "edge_count",
        "missing_node_count",
    ]:
        if key in compact:
            print(f"- {key}: {compact[key]}")
    if "related" in compact:
        print(f"- incoming: {compact['related']['incoming_count']}")
        print(f"- outgoing: {compact['related']['outgoing_count']}")


def _trace_full_result(result: dict) -> dict:
    if result.get("index_path"):
        return {**result, "index": read_yaml(Path(result["index_path"]))}
    if result.get("trace_path"):
        return {**result, "trace": read_yaml(Path(result["trace_path"]))}
    return result


def _compact_zotero_import(result: dict) -> dict:
    imported = result.get("status_import") or result.get("status_update") or {}
    external = result.get("external_acquisition_state") or {}
    return {
        "status": imported.get("status"),
        "handoff_schema_version": imported.get("handoff_schema_version"),
        "target_count": imported.get("target_count", 0),
        "ready_count": (external.get("summary") or {}).get("ready_count", imported.get("success_count", 0)),
        "needs_user_login_count": imported.get("needs_user_login_count", 0),
        "blocked_count": imported.get("blocked_count", 0),
        "current_task_blocker_count": len(imported.get("current_task_blockers") or []),
        "stale_global_state_count": len(imported.get("stale_global_state") or []),
        "artifacts": {
            "external_state": imported.get("external_acquisition_state_ref"),
            "compact_status": imported.get("acquisition_status_compact_ref"),
            "compatibility_import": "literature/zotero_codex_status_import.yml",
        },
        "sync_status": (result.get("sync") or {}).get("status") if isinstance(result.get("sync"), dict) else None,
        "next_action": "Review current-task blockers or continue with verified cache evidence.",
    }


def _compact_zotero_readiness(result: dict) -> dict:
    readiness = result.get("readiness") or {}
    summary = readiness.get("summary") or {}
    return {
        "status": readiness.get("status"),
        "maturity": "experimental/companion",
        "target_count": summary.get("target_count", 0),
        "external_cache_used": summary.get("external_cache_used", False),
        "external_ready_count": summary.get("external_ready_count", 0),
        "current_task_blocker_count": len(readiness.get("current_task_blockers") or []),
        "optional_capability_count": len(readiness.get("optional_capabilities") or []),
        "stale_global_state_count": len(readiness.get("stale_global_state") or []),
        "next_actions": readiness.get("next_actions") or [],
        "artifacts": readiness.get("output_refs") or {},
    }


def _compact_reconciliation(result: dict) -> dict:
    reconciliation = result.get("reconciliation") or {}
    summary = reconciliation.get("summary") or {}
    return {
        "status": reconciliation.get("status"),
        "error_count": summary.get("error_count", 0),
        "warning_count": summary.get("warning_count", 0),
        "external_cache_used": summary.get("external_cache_used", False),
        "external_ready_count": summary.get("external_ready_count", 0),
        "repair_action_count": len(reconciliation.get("repair_actions") or []),
        "question_count": len(reconciliation.get("questions_for_user") or []),
        "artifacts": {
            "yaml": reconciliation.get("yaml_ref"),
            "markdown": reconciliation.get("markdown_ref"),
        },
        "next_action": "Open the reconciliation artifact for findings and advisory repair actions." if reconciliation.get("findings") else "Continue the reviewed literature workflow.",
    }


def _project_id_from_workspace(workspace: Path) -> str:
    project_path = workspace / "EA_PROJECT.md"
    if not project_path.exists():
        return "unknown-project"
    frontmatter, _ = read_markdown_record(project_path)
    return str(frontmatter.get("project_id", "unknown-project"))


def _project_path(workspace: Path, path: Path) -> Path:
    return path if path.is_absolute() else workspace / path


def _is_explicitly_read_only(args: argparse.Namespace) -> bool:
    if args.command in {"version", "capabilities", "mode", "status", "analyze", "doctor", "install-check", "onboarding", "healthcheck", "lookup-figure"}:
        return True
    if args.command == "diagnostics":
        return args.output is None and not args.debug_json
    if args.command == "import":
        return args.import_command == "preview"
    if args.command == "migrate":
        return args.migrate_command in {"status", "plan"}
    if args.command == "brief":
        return bool(args.no_write)
    if args.command == "eval":
        return bool(args.no_write)
    if args.command == "estimate":
        return args.estimate_command == "workflow" or (
            args.estimate_command == "reminders" and not args.disable and not args.enable
        )
    if args.command == "memory":
        return args.memory_command == "show-project"
    if args.command == "literature":
        return (
            (args.literature_command == "setup-preflight" and args.no_write)
            or (args.literature_command == "zotero-readiness" and args.no_write)
            or (args.literature_command == "data-validate" and args.no_write)
        )
    if args.command == "draft":
        return args.draft_command == "status"
    return False


def _mode_allows(args: argparse.Namespace) -> bool:
    if args.interaction_mode == "execute" or args.command == "mode":
        return True
    if args.interaction_mode in {"consult", "audit"}:
        return _is_explicitly_read_only(args)
    if args.interaction_mode == "record":
        if args.command in {
            "setup",
            "update",
            "rollback",
            "uninstall",
            "codex",
            "report",
            "export",
            "batch",
            "raman",
            "pl",
            "xrd",
            "ftir",
            "uv-vis",
            "xps",
            "electrochemistry",
            "thermal",
            "image-data",
            "trace",
        }:
            return False
        if args.command == "literature" and args.literature_command in {
            "search-public",
            "acquisition-request",
            "import-acquisition",
            "import-zotero-status",
            "reconcile-acquisition",
            "data-extract",
            "data-plot",
            "data-export",
        }:
            return False
        return True
    return False


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


def _ftir_processing_parameters(args: argparse.Namespace, workspace: Path) -> dict:
    parameters = default_ftir_processing_parameters()
    if args.parameters_file:
        parameters.update(read_yaml(_project_path(workspace, args.parameters_file)))
    if args.parameters_json:
        parameters.update(json.loads(args.parameters_json))
    return parameters


def _uv_vis_processing_parameters(args: argparse.Namespace, workspace: Path) -> dict:
    parameters = default_uv_vis_processing_parameters()
    if args.parameters_file:
        parameters.update(read_yaml(_project_path(workspace, args.parameters_file)))
    if args.parameters_json:
        parameters.update(json.loads(args.parameters_json))
    return parameters


def _xps_processing_parameters(args: argparse.Namespace, workspace: Path) -> dict:
    parameters = default_xps_processing_parameters()
    if args.parameters_file:
        parameters.update(read_yaml(_project_path(workspace, args.parameters_file)))
    if args.parameters_json:
        parameters.update(json.loads(args.parameters_json))
    return parameters


def _electrochemistry_processing_parameters(args: argparse.Namespace, workspace: Path) -> dict:
    parameters = default_electrochemistry_processing_parameters()
    if args.parameters_file:
        parameters.update(read_yaml(_project_path(workspace, args.parameters_file)))
    if args.parameters_json:
        parameters.update(json.loads(args.parameters_json))
    return parameters


def _thermal_processing_parameters(args: argparse.Namespace, workspace: Path) -> dict:
    parameters = default_thermal_processing_parameters()
    if args.parameters_file:
        parameters.update(read_yaml(_project_path(workspace, args.parameters_file)))
    if args.parameters_json:
        parameters.update(json.loads(args.parameters_json))
    return parameters


def _main_impl(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not _mode_allows(args):
        raise PermissionError(
            f"Interaction mode '{args.interaction_mode}' blocks this command before any project write. "
            "Use a read-only command or choose record/execute mode explicitly."
        )
    if args.command == "version":
        identity = identity_record()
        if args.json:
            _print_json(identity)
        else:
            print(
                f"{identity['product']} ({identity['public_version']})\n"
                f"Distribution: {identity['distribution_name']} {identity['package_version']}\n"
                f"Release label: {identity['release_label']}\n"
                f"Codex skill invocation: {identity['skill_invocation']}"
            )
        return 0
    if args.command == "capabilities":
        matrix = {args.maturity: CAPABILITY_MATURITY[args.maturity]} if args.maturity else CAPABILITY_MATURITY
        result = {
            "schema_version": "1.0",
            "release": RELEASE_LABEL,
            "capabilities": {key: list(values) for key, values in matrix.items()},
            "promotion_rule": "Beta or experimental capabilities do not inherit stable guarantees; scientific promotion requires benchmark and external review evidence.",
        }
        if args.json:
            _print_json(result)
        else:
            for maturity, names in result["capabilities"].items():
                print(f"{maturity}:")
                for name in names:
                    print(f"- {name}")
        return 0
    if args.command == "mode":
        result = {
            "schema_version": "1.0",
            "active_mode": args.interaction_mode,
            "modes": {
                "consult": {"writes": False, "purpose": "orientation, preview, discussion, and next-decision guidance"},
                "record": {"writes": True, "purpose": "structured records, review, references, and staging without analysis execution"},
                "execute": {"writes": True, "purpose": "confirmed processing, plotting, reports, exports, migration, and integrations"},
                "audit": {"writes": False, "purpose": "health, evaluation, diagnostics preview, and release evidence inspection"},
            },
            "selection": "Use global --mode or the EA_MODE environment variable; mode selection itself writes no project files.",
        }
        if args.json:
            _print_json(result)
        else:
            print(f"active mode: {args.interaction_mode}")
            for name, details in result["modes"].items():
                print(f"- {name}: writes={str(details['writes']).lower()}; {details['purpose']}")
        return 0
    if args.command == "diagnostics":
        result = collect_diagnostics(
            args.workspace,
            selected_logs=args.log,
            output_path=args.output,
            debug_json=args.debug_json,
        )
        _print_json(result)
        return 0 if result["status"] in {"ready", "attention"} else 2
    if args.command == "draft":
        if args.draft_command == "stage":
            result = stage_draft_artifact(
                args.workspace,
                source_path=args.source,
                target_ref=args.target,
                draft_id=args.draft_id,
                confirmed=args.yes,
            )
        elif args.draft_command == "status":
            result = draft_artifact_status(args.workspace, draft_id=args.draft_id)
        else:
            result = promote_draft_artifact(
                args.workspace,
                draft_id=args.draft_id,
                review_ref=args.review_ref,
                confirmed=args.yes,
            )
        _print_json(result)
        return 0
    if args.command == "setup":
        result = setup_installation(
            source=args.source,
            codex_home_path=args.codex_home,
            validator=args.quick_validate,
            release_ref=args.release_ref,
            lang=args.lang,
        )
        if args.json:
            _print_json(result)
        else:
            print(render_install_skill_summary(result["skill_install"]))
            print()
            print(render_onboarding_post_install(result["onboarding"]))
        return 0 if result["status"] == "pass" else 2
    if args.command == "start":
        result = start_project(
            args.workspace,
            project_name=args.name,
            research_direction=args.direction,
            material_system=args.material,
            experiment_type=args.experiment_type,
            report_language=args.report_language,
            confirmed=args.yes,
        )
        _print_json(result)
        return 0
    if args.command == "analyze":
        source = args.source if args.source.is_absolute() else args.workspace / args.source
        _print_json(inspect_analysis_source(args.method, source))
        return 0
    if args.command == "report":
        result = generate_user_report(
            args.workspace,
            method=args.method,
            metadata_path=args.metadata,
            sample_refs=args.sample_ref,
            experiment_refs=args.experiment_ref,
            reference_ids=args.reference_id,
            confirmed=args.yes,
        )
        _print_json(result)
        return 0
    if args.command == "import":
        if args.import_command == "preview":
            result = preview_import(
                args.source,
                encoding=args.encoding,
                delimiter=args.delimiter,
                allow_symlink=args.allow_symlink,
                max_rows=args.max_rows,
            )
        else:
            result = apply_import(
                args.workspace,
                args.source,
                characterization_type=args.characterization_type,
                sample_refs=args.sample_ref,
                experiment_refs=args.experiment_ref,
                encoding=args.encoding,
                delimiter=args.delimiter,
                allow_symlink=args.allow_symlink,
                preview_hash=args.preview_hash,
                confirmed=args.yes,
            )
        _print_json(result)
        return 0 if result["status"] in {"ready", "needs_confirmation", "completed", "duplicate_alias"} else 2
    if args.command in {"doctor", "install-check"}:
        result = install_check(
            codex_home_path=args.codex_home,
            skill_path=args.skill_path,
            validator=args.quick_validate,
            run_example=args.run_example_check,
            example_workspace=args.example_workspace,
            skip_codex_skill=args.skip_codex_skill,
        )
        if args.json:
            _print_json(result)
        else:
            print(render_install_summary(result))
        return 0 if result["status"] != "fail" else 2
    if args.command == "update":
        result = update_installation(release_ref=args.release_ref, confirmed=args.yes)
        _print_json(result) if args.json else print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] in {"completed", "needs_confirmation"} else 2
    if args.command == "rollback":
        result = rollback_installation(release_ref=args.release_ref, confirmed=args.yes)
        _print_json(result) if args.json else print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] in {"completed", "needs_confirmation"} else 2
    if args.command == "uninstall":
        result = uninstall_installation(codex_home_path=args.codex_home, confirmed=args.yes)
        _print_json(result) if args.json else print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] in {"completed", "needs_confirmation"} else 2
    if args.command == "codex":
        if args.codex_command == "install-skill":
            result = install_codex_skill(
                source=args.source,
                codex_home_path=args.codex_home,
                validator=args.quick_validate,
                backup_existing=not args.no_backup,
                allow_github_fetch=not args.no_github_fetch,
                release_ref=args.release_ref,
            )
            if args.json:
                _print_json(result)
            else:
                print(render_install_skill_summary(result))
            return 0 if result["status"] != "fail" else 2
        if args.codex_command == "rollback-skill":
            result = rollback_codex_skills(
                codex_home_path=args.codex_home,
                validator=args.quick_validate,
                confirmed=args.yes,
            )
            _print_json(result)
            return 0 if result["status"] in {"completed", "needs_confirmation"} else 2
        if args.codex_command == "uninstall-skills":
            result = uninstall_codex_skills(codex_home_path=args.codex_home, confirmed=args.yes)
            _print_json(result)
            return 0 if result["status"] in {"completed", "needs_confirmation"} else 2
    if args.command == "onboarding":
        if args.onboarding_command == "post-install":
            record = onboarding_post_install_record(event=args.event, lang=args.lang)
            if args.json:
                _print_json(record)
            else:
                print(render_onboarding_post_install(record))
            return 0
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
    if args.command == "migrate":
        if args.migrate_command == "status":
            _print_json(project_format_status(args.workspace))
            return 0
        if args.migrate_command == "plan":
            _print_json(plan_project_migration(args.workspace, target_version=args.target_version))
            return 0
        if args.migrate_command == "apply":
            result = apply_project_migration(
                args.workspace,
                target_version=args.target_version,
                confirmed=args.yes,
            )
            _print_json(result)
            return 0
        if args.migrate_command == "rollback":
            result = rollback_project_migration(
                args.workspace,
                migration_id=args.migration_id,
                confirmed=args.yes,
            )
            _print_json(result)
            return 0
    if args.command == "status":
        _print_json(build_project_dashboard(args.workspace))
        return 0
    if args.command == "brief":
        if args.brief_command == "project":
            output_path = args.output
            if output_path and not output_path.is_absolute():
                output_path = args.workspace / output_path
            result = build_project_brief(
                args.workspace,
                write_report=not args.no_write,
                output_path=output_path,
            )
            if args.print_markdown:
                print(result["markdown"])
                return 0 if result["evaluation"]["status"] != "fail" else 2
            if args.json_full:
                _print_json(result)
            elif args.json:
                _print_json(_compact_brief_result(result))
            else:
                _print_brief_summary(result)
            return 0 if result["evaluation"]["status"] != "fail" else 2
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
    if args.command == "export":
        if args.export_command == "report-bundle":
            output_dir = args.output
            if output_dir and not output_dir.is_absolute():
                output_dir = args.workspace / output_dir
            archive_path = args.zip_output
            if archive_path and not archive_path.is_absolute():
                archive_path = args.workspace / archive_path
            create_archive = args.zip or archive_path is not None
            try:
                result = export_report_bundle(
                    args.workspace,
                    report_id=args.report_id,
                    output_dir=output_dir,
                    create_archive=create_archive,
                    archive_path=archive_path,
                    include_trace=args.include_trace,
                )
            except ReportBundleError as exc:
                _print_json({"status": "fail", "error": str(exc)})
                return 2
            _print_json(result)
            return 0 if result["status"] == "complete" else 1
        if args.export_command == "report-html":
            output_path = args.output
            if output_path and not output_path.is_absolute():
                output_path = args.workspace / output_path
            try:
                result = export_report_html(
                    args.workspace,
                    report_id=args.report_id,
                    output_path=output_path,
                    embed_images=not args.no_embed_images,
                    include_audit=not args.no_audit,
                )
            except ReportBundleError as exc:
                _print_json({"status": "fail", "error": str(exc)})
                return 2
            _print_json(result)
            return 0 if result["status"] == "complete" else 1
        if args.export_command == "batch-bundle":
            output_dir = args.output
            if output_dir and not output_dir.is_absolute():
                output_dir = args.workspace / output_dir
            archive_path = args.zip_output
            if archive_path and not archive_path.is_absolute():
                archive_path = args.workspace / archive_path
            create_archive = args.zip or archive_path is not None
            try:
                result = export_batch_bundle(
                    args.workspace,
                    batch_id=args.batch_id,
                    output_dir=output_dir,
                    create_archive=create_archive,
                    archive_path=archive_path,
                    include_trace=args.include_trace,
                )
            except ReportBundleError as exc:
                _print_json({"status": "fail", "error": str(exc)})
                return 2
            _print_json(result)
            return 0 if result["status"] == "complete" else 1
        if args.export_command == "verify-bundle":
            result = verify_bundle_checksums(args.bundle)
            _print_json(result)
            return 0 if result["status"] == "pass" else 2
        if args.export_command == "verify-archive":
            result = verify_archive_checksum(args.archive, checksum_path=args.checksum)
            _print_json(result)
            return 0 if result["status"] == "pass" else 2
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
                confirm=args.confirm,
            )
            data = read_yaml(path)
            _print_json({"review": str(path), "review_id": path.stem, "review_status": data.get("review_status")})
            return 0
        if args.review_command == "promote":
            path = promote_review_record(
                args.workspace,
                args.review_ref,
                user_response=args.user_response,
            )
            data = read_yaml(path)
            _print_json(
                {
                    "review": str(path),
                    "review_id": path.stem,
                    "review_status": data.get("review_status"),
                    "decision": data.get("decision"),
                    "promoted_at": data.get("promoted_at"),
                }
            )
            return 0
    if args.command == "raman":
        project_id = getattr(args, "project_id", None)
        if args.raman_command in {"process", "report"} and not project_id:
            project_id = _project_id_from_workspace(args.workspace)
        if args.raman_command == "list-assignment-libraries":
            _print_json(
                summarize_raman_assignment_libraries(
                    materials=args.material,
                    features=args.feature,
                    shift_min_cm1=args.shift_min_cm1,
                    shift_max_cm1=args.shift_max_cm1,
                )
            )
            return 0
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
        if args.pl_command == "list-assignment-libraries":
            _print_json(
                summarize_pl_assignment_libraries(
                    materials=args.material,
                    features=args.feature,
                    energy_min_eV=args.energy_min_ev,
                    energy_max_eV=args.energy_max_ev,
                    wavelength_min_nm=args.wavelength_min_nm,
                    wavelength_max_nm=args.wavelength_max_nm,
                )
            )
            return 0
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
        if args.xrd_command in {"process", "report", "build-assignment-packet", "suggest-assignments", "prepare-review"} and not project_id:
            project_id = _project_id_from_workspace(args.workspace)
        if args.xrd_command == "list-assignment-libraries":
            _print_json(
                summarize_xrd_assignment_libraries(
                    materials=args.material,
                    features=args.feature,
                    two_theta_min_deg=args.two_theta_min_deg,
                    two_theta_max_deg=args.two_theta_max_deg,
                    d_spacing_min_angstrom=args.d_spacing_min_angstrom,
                    d_spacing_max_angstrom=args.d_spacing_max_angstrom,
                )
            )
            return 0
        if args.xrd_command == "build-assignment-packet":
            _print_json(
                build_xrd_assignment_source_packet(
                    args.workspace,
                    project_id=project_id,
                    library_path=_project_path(args.workspace, args.library_file) if args.library_file else None,
                    builtin_library=args.builtin_library,
                    literature_manifest_path=_project_path(args.workspace, args.literature_manifest) if args.literature_manifest else None,
                    output_path=args.output,
                    include_candidates=args.include_candidate,
                    materials=args.material,
                    features=args.feature,
                    two_theta_min_deg=args.two_theta_min_deg,
                    two_theta_max_deg=args.two_theta_max_deg,
                    d_spacing_min_angstrom=args.d_spacing_min_angstrom,
                    d_spacing_max_angstrom=args.d_spacing_max_angstrom,
                    template=args.write_template,
                )
            )
            return 0
        if args.xrd_command == "suggest-assignments":
            _print_json(
                suggest_xrd_assignments(
                    args.workspace,
                    project_id=project_id,
                    xrd_metadata_path=_project_path(args.workspace, args.metadata),
                    source_path=_project_path(args.workspace, args.source_file),
                    related_records=args.related_record,
                )
            )
            return 0
        if args.xrd_command == "prepare-review":
            _print_json(
                prepare_xrd_assignment_review_package(
                    args.workspace,
                    project_id=project_id,
                    suggestion_path=_project_path(args.workspace, args.suggestion),
                    candidate_ids=args.candidate_id,
                )
            )
            return 0
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
                assignment_suggestion_paths=[_project_path(args.workspace, path) for path in args.assignment_suggestion],
                assignment_review_refs=args.assignment_review_ref,
            )
            _print_json({"report": str(path)})
            return 0
    if args.command == "ftir":
        project_id = getattr(args, "project_id", None)
        if args.ftir_command in {"process", "report", "suggest-assignments", "prepare-review", "propose-memory", "build-assignment-packet"} and not project_id:
            project_id = _project_id_from_workspace(args.workspace)
        if args.ftir_command == "inspect":
            inspection = asdict(inspect_ftir_file(_project_path(args.workspace, args.spectrum)))
            inspection["path"] = str(inspection["path"])
            _print_json(inspection)
            return 0
        if args.ftir_command == "list-assignment-libraries":
            _print_json(
                summarize_ftir_assignment_libraries(
                    builtin_libraries=args.builtin_library,
                    include_candidates=args.include_candidate,
                    assignment_types=args.assignment_type,
                    material_scopes=args.material_scope,
                    wavenumber_min_cm1=args.wavenumber_min_cm1,
                    wavenumber_max_cm1=args.wavenumber_max_cm1,
                )
            )
            return 0
        if args.ftir_command == "process":
            parameters = _ftir_processing_parameters(args, args.workspace)
            path = process_ftir_result(
                args.workspace,
                characterization_metadata_path=_project_path(args.workspace, args.metadata),
                project_id=project_id,
                sample_refs=args.sample_ref,
                request=FTIRProcessingRequest(
                    x_column=args.x_column,
                    y_column=args.y_column,
                    x_unit=args.x_unit,
                    signal_mode=args.signal_mode,
                    processing_parameters=parameters,
                    column_review_ref=args.column_review_ref,
                    parameter_review_ref=args.parameter_review_ref,
                ),
            )
            _print_json({"metadata": str(path)})
            return 0
        if args.ftir_command == "report":
            path = generate_ftir_report(
                args.workspace,
                project_id=project_id,
                ftir_metadata_path=_project_path(args.workspace, args.metadata),
                related_experiments=args.experiment_ref,
                related_samples=args.sample_ref,
                reference_ids=args.reference_id,
                assignment_suggestion_paths=[_project_path(args.workspace, path) for path in args.assignment_suggestion],
            )
            _print_json({"report": str(path)})
            return 0
        if args.ftir_command == "suggest-assignments":
            _print_json(
                suggest_ftir_assignments(
                    args.workspace,
                    project_id=project_id,
                    ftir_metadata_path=_project_path(args.workspace, args.metadata),
                    source_path=_project_path(args.workspace, args.source_file),
                    related_records=args.related_record,
                )
            )
            return 0
        if args.ftir_command == "prepare-review":
            _print_json(
                prepare_ftir_assignment_review_package(
                    args.workspace,
                    project_id=project_id,
                    suggestion_path=_project_path(args.workspace, args.suggestion),
                    candidate_ids=args.candidate_id,
                )
            )
            return 0
        if args.ftir_command == "propose-memory":
            _print_json(
                propose_ftir_assignment_memory_candidates(
                    args.workspace,
                    project_id=project_id,
                    suggestion_path=_project_path(args.workspace, args.suggestion),
                    review_ref=args.review_ref,
                    candidate_ids=args.candidate_id,
                    allow_non_ready=args.allow_non_ready,
                )
            )
            return 0
        if args.ftir_command == "build-assignment-packet":
            _print_json(
                build_ftir_assignment_source_packet(
                    args.workspace,
                    project_id=project_id,
                    library_path=_project_path(args.workspace, args.library_file) if args.library_file else None,
                    builtin_library=args.builtin_library,
                    literature_manifest_path=_project_path(args.workspace, args.literature_manifest) if args.literature_manifest else None,
                    output_path=args.output,
                    include_candidates=args.include_candidate,
                    assignment_types=args.assignment_type,
                    material_scopes=args.material_scope,
                    template=args.write_template,
                )
            )
            return 0
    if args.command == "uv-vis":
        project_id = getattr(args, "project_id", None)
        if args.uv_vis_command in {"process", "report", "build-source-packet", "suggest-interpretations", "prepare-review", "propose-memory", "compare-replicates"} and not project_id:
            project_id = _project_id_from_workspace(args.workspace)
        if args.uv_vis_command == "list-source-libraries":
            _print_json(
                summarize_uv_vis_source_libraries(
                    builtin_libraries=args.builtin_library,
                    include_candidates=args.include_candidate,
                    candidate_types=args.candidate_type,
                    optical_targets=args.optical_target,
                    energy_min_eV=args.energy_min_ev,
                    energy_max_eV=args.energy_max_ev,
                    wavelength_min_nm=args.wavelength_min_nm,
                    wavelength_max_nm=args.wavelength_max_nm,
                )
            )
            return 0
        if args.uv_vis_command == "inspect":
            inspection = asdict(inspect_uv_vis_file(_project_path(args.workspace, args.spectrum)))
            inspection["path"] = str(inspection["path"])
            _print_json(inspection)
            return 0
        if args.uv_vis_command == "process":
            parameters = _uv_vis_processing_parameters(args, args.workspace)
            path = process_uv_vis_result(
                args.workspace,
                characterization_metadata_path=_project_path(args.workspace, args.metadata),
                project_id=project_id,
                sample_refs=args.sample_ref,
                request=UVVisProcessingRequest(
                    x_column=args.x_column,
                    y_column=args.y_column,
                    x_unit=args.x_unit,
                    signal_mode=args.signal_mode,
                    processing_parameters=parameters,
                    column_review_ref=args.column_review_ref,
                    parameter_review_ref=args.parameter_review_ref,
                ),
            )
            _print_json({"metadata": str(path)})
            return 0
        if args.uv_vis_command == "report":
            path = generate_uv_vis_report(
                args.workspace,
                project_id=project_id,
                uv_vis_metadata_path=_project_path(args.workspace, args.metadata),
                related_experiments=args.experiment_ref,
                related_samples=args.sample_ref,
                reference_ids=args.reference_id,
                interpretation_suggestion_paths=[_project_path(args.workspace, path) for path in args.interpretation_suggestion],
                interpretation_review_refs=args.interpretation_review_ref,
            )
            _print_json({"report": str(path)})
            return 0
        if args.uv_vis_command == "build-source-packet":
            _print_json(
                build_uv_vis_source_packet(
                    args.workspace,
                    project_id=project_id,
                    library_path=_project_path(args.workspace, args.library_file) if args.library_file else None,
                    builtin_library=args.builtin_library,
                    literature_manifest_path=_project_path(args.workspace, args.literature_manifest) if args.literature_manifest else None,
                    output_path=args.output,
                    include_candidates=args.include_candidate,
                    candidate_types=args.candidate_type,
                    optical_targets=args.optical_target,
                    template=args.write_template,
                )
            )
            return 0
        if args.uv_vis_command == "suggest-interpretations":
            _print_json(
                suggest_uv_vis_interpretations(
                    args.workspace,
                    project_id=project_id,
                    uv_vis_metadata_path=_project_path(args.workspace, args.metadata),
                    source_path=_project_path(args.workspace, args.source_file),
                    related_records=args.related_record,
                )
            )
            return 0
        if args.uv_vis_command == "prepare-review":
            _print_json(
                prepare_uv_vis_interpretation_review_package(
                    args.workspace,
                    project_id=project_id,
                    suggestion_path=_project_path(args.workspace, args.suggestion),
                    candidate_ids=args.candidate_id,
                )
            )
            return 0
        if args.uv_vis_command == "propose-memory":
            _print_json(
                propose_uv_vis_interpretation_memory_candidates(
                    args.workspace,
                    project_id=project_id,
                    suggestion_path=_project_path(args.workspace, args.suggestion),
                    review_ref=args.review_ref,
                    candidate_ids=args.candidate_id,
                    allow_non_ready=args.allow_non_ready,
                )
            )
            return 0
        if args.uv_vis_command == "compare-replicates":
            _print_json(
                compare_uv_vis_replicates(
                    args.workspace,
                    project_id=project_id,
                    metadata_paths=[_project_path(args.workspace, path) for path in args.metadata],
                    comparison_label=args.comparison_label,
                    feature_match_tolerance_eV=args.feature_match_tolerance_ev,
                    feature_match_tolerance_nm=args.feature_match_tolerance_nm,
                    feature_match_review_ref=args.feature_match_review_ref,
                )
            )
            return 0
    if args.command == "xps":
        project_id = getattr(args, "project_id", None)
        if args.xps_command in {"process", "report", "suggest-parameters", "prepare-review", "propose-memory", "build-source-packet"} and not project_id:
            project_id = _project_id_from_workspace(args.workspace)
        if args.xps_command == "inspect":
            inspection = asdict(inspect_xps_file(_project_path(args.workspace, args.spectrum)))
            inspection["path"] = str(inspection["path"])
            _print_json(inspection)
            return 0
        if args.xps_command == "list-parameter-libraries":
            _print_json(
                summarize_xps_parameter_libraries(
                    builtin_libraries=args.builtin_library,
                    include_candidates=args.include_candidate,
                    suggestion_types=args.suggestion_type,
                    elements=args.element,
                    core_levels=args.core_level,
                )
            )
            return 0
        if args.xps_command == "process":
            parameters = _xps_processing_parameters(args, args.workspace)
            path = process_xps_result(
                args.workspace,
                characterization_metadata_path=_project_path(args.workspace, args.metadata),
                project_id=project_id,
                sample_refs=args.sample_ref,
                request=XPSProcessingRequest(
                    x_column=args.x_column,
                    y_column=args.y_column,
                    x_unit=args.x_unit,
                    energy_shift_eV=args.energy_shift_ev,
                    calibration_reference=args.calibration_reference,
                    processing_parameters=parameters,
                    column_review_ref=args.column_review_ref,
                    calibration_review_ref=args.calibration_review_ref,
                    parameter_review_ref=args.parameter_review_ref,
                ),
            )
            _print_json({"metadata": str(path)})
            return 0
        if args.xps_command == "report":
            path = generate_xps_report(
                args.workspace,
                project_id=project_id,
                xps_metadata_path=_project_path(args.workspace, args.metadata),
                related_experiments=args.experiment_ref,
                related_samples=args.sample_ref,
                reference_ids=args.reference_id,
                parameter_suggestion_paths=[_project_path(args.workspace, path) for path in args.parameter_suggestion],
            )
            _print_json({"report": str(path)})
            return 0
        if args.xps_command == "suggest-parameters":
            _print_json(
                suggest_xps_parameters(
                    args.workspace,
                    project_id=project_id,
                    source_path=_project_path(args.workspace, args.source_file),
                    related_records=args.related_record,
                )
            )
            return 0
        if args.xps_command == "prepare-review":
            _print_json(
                prepare_xps_parameter_review_package(
                    args.workspace,
                    project_id=project_id,
                    suggestion_path=_project_path(args.workspace, args.suggestion),
                    candidate_ids=args.candidate_id,
                )
            )
            return 0
        if args.xps_command == "propose-memory":
            _print_json(
                propose_xps_parameter_memory_candidates(
                    args.workspace,
                    project_id=project_id,
                    suggestion_path=_project_path(args.workspace, args.suggestion),
                    review_ref=args.review_ref,
                    candidate_ids=args.candidate_id,
                    allow_non_ready=args.allow_non_ready,
                )
            )
            return 0
        if args.xps_command == "build-source-packet":
            _print_json(
                build_xps_parameter_source_packet(
                    args.workspace,
                    project_id=project_id,
                    library_path=_project_path(args.workspace, args.library_file) if args.library_file else None,
                    builtin_library=args.builtin_library,
                    literature_manifest_path=_project_path(args.workspace, args.literature_manifest) if args.literature_manifest else None,
                    output_path=args.output,
                    include_candidates=args.include_candidate,
                    suggestion_types=args.suggestion_type,
                    elements=args.element,
                    core_levels=args.core_level,
                    template=args.write_template,
                )
            )
            return 0
    if args.command == "electrochemistry":
        project_id = getattr(args, "project_id", None)
        if args.electrochemistry_command in {"process", "report"} and not project_id:
            project_id = _project_id_from_workspace(args.workspace)
        if args.electrochemistry_command == "inspect":
            inspection = asdict(inspect_electrochemistry_file(_project_path(args.workspace, args.spectrum)))
            inspection["path"] = str(inspection["path"])
            _print_json(inspection)
            return 0
        if args.electrochemistry_command == "process":
            parameters = _electrochemistry_processing_parameters(args, args.workspace)
            path = process_electrochemistry_result(
                args.workspace,
                characterization_metadata_path=_project_path(args.workspace, args.metadata),
                project_id=project_id,
                sample_refs=args.sample_ref,
                request=ElectrochemistryProcessingRequest(
                    x_column=args.x_column,
                    y_column=args.y_column,
                    x_unit=args.x_unit,
                    current_unit=args.current_unit,
                    measurement_mode=args.measurement_mode,
                    context_summary=args.context_summary,
                    electrode_area_cm2=args.electrode_area_cm2,
                    processing_parameters=parameters,
                    column_review_ref=args.column_review_ref,
                    context_review_ref=args.context_review_ref,
                    parameter_review_ref=args.parameter_review_ref,
                ),
            )
            _print_json({"metadata": str(path)})
            return 0
        if args.electrochemistry_command == "report":
            path = generate_electrochemistry_report(
                args.workspace,
                project_id=project_id,
                electrochemistry_metadata_path=_project_path(args.workspace, args.metadata),
                related_experiments=args.experiment_ref,
                related_samples=args.sample_ref,
                reference_ids=args.reference_id,
            )
            _print_json({"report": str(path)})
            return 0
    if args.command == "thermal":
        project_id = getattr(args, "project_id", None)
        if args.thermal_command in {"process", "report"} and not project_id:
            project_id = _project_id_from_workspace(args.workspace)
        if args.thermal_command == "inspect":
            inspection = asdict(inspect_thermal_file(_project_path(args.workspace, args.data)))
            inspection["path"] = str(inspection["path"])
            _print_json(inspection)
            return 0
        if args.thermal_command == "process":
            parameters = _thermal_processing_parameters(args, args.workspace)
            path = process_thermal_result(
                args.workspace,
                characterization_metadata_path=_project_path(args.workspace, args.metadata),
                project_id=project_id,
                sample_refs=args.sample_ref,
                request=ThermalAnalysisProcessingRequest(
                    temperature_column=args.temperature_column,
                    signal_column=args.signal_column,
                    temperature_unit=args.temperature_unit,
                    signal_unit=args.signal_unit,
                    measurement_mode=args.measurement_mode,
                    context_summary=args.context_summary,
                    processing_parameters=parameters,
                    column_review_ref=args.column_review_ref,
                    context_review_ref=args.context_review_ref,
                    parameter_review_ref=args.parameter_review_ref,
                ),
            )
            _print_json({"metadata": str(path)})
            return 0
        if args.thermal_command == "report":
            path = generate_thermal_report(
                args.workspace,
                project_id=project_id,
                thermal_metadata_path=_project_path(args.workspace, args.metadata),
                related_experiments=args.experiment_ref,
                related_samples=args.sample_ref,
                reference_ids=args.reference_id,
            )
            _print_json({"report": str(path)})
            return 0
    if args.command == "batch":
        if args.batch_command == "validate":
            result = validate_batch_manifest(args.workspace, args.manifest)
            _print_json(result)
            return 0 if result["status"] == "pass" else 2
        if args.batch_command == "run":
            try:
                result = run_batch_manifest(args.workspace, args.manifest)
            except BatchManifestError as exc:
                _print_json({"status": "fail", "error": str(exc)})
                return 2
            _print_json(result)
            return 0 if result["status"] == "success" else 2
    if args.command == "templates":
        if args.templates_command == "parameters":
            method = args.method.lower().strip().replace("-", "_")
            if method == "thermal":
                method = "thermal_analysis"
            written = None
            if args.output:
                written = write_processing_parameters_template(args.output, method)
            _print_json(
                {
                    "template_type": "processing_parameters",
                    "method": method,
                    "review_target_type": f"{method}_parameters",
                    "parameters": processing_parameters_template(method),
                    "written": str(written) if written else None,
                }
            )
            return 0
        if args.templates_command == "batch-manifest":
            project_id = args.project_id or _project_id_from_workspace(args.workspace)
            methods = [method.lower().strip().replace("-", "_") for method in (args.method or list(SUPPORTED_TEMPLATE_METHODS))]
            methods = ["thermal_analysis" if method == "thermal" else method for method in methods]
            output_path = None
            if args.output:
                output_path = args.output if args.output.is_absolute() else args.workspace / args.output
                write_batch_manifest_template(
                    output_path,
                    project_id=project_id,
                    methods=methods,
                    sample_ref=args.sample_ref,
                    experiment_ref=args.experiment_ref,
                    create_reports=not args.no_reports,
                    continue_on_error=not args.stop_on_error,
                )
            manifest = batch_manifest_template(
                project_id=project_id,
                methods=methods,
                sample_ref=args.sample_ref,
                experiment_ref=args.experiment_ref,
                create_reports=not args.no_reports,
                continue_on_error=not args.stop_on_error,
            )
            _print_json(
                {
                    "template_type": "batch_manifest",
                    "methods": methods,
                    "manifest": manifest,
                    "written": str(output_path) if output_path else None,
                }
            )
            return 0
    if args.command == "materials":
        if args.materials_command == "list":
            _print_json({"materials": available_materials()})
            return 0
        if args.materials_command == "audit-assignment-library":
            _print_json(audit_assignment_library(materials=args.material, methods=args.method))
            return 0
        if args.materials_command == "show":
            _print_json(get_material_profile(args.material))
            return 0
        if args.materials_command == "assignments":
            _print_json(assignment_candidates(args.material, args.method))
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
        if args.literature_command == "rank-candidates":
            candidates_path = args.candidates if args.candidates.is_absolute() else args.workspace / args.candidates
            _print_json(
                rank_literature_candidates(
                    args.workspace,
                    candidates_path=candidates_path,
                    top_n=args.top_n,
                    reference_year=args.reference_year,
                    source_label=args.source_label,
                    extra_keywords=args.keyword,
                )
            )
            return 0
        if args.literature_command == "search-public":
            requested_items = (args.max_results or 20) * max(1, len(args.source or []) or 1) * max(1, args.query_limit or 1) * max(1, args.page_limit or 1)
            gate = large_work_gate(
                args.workspace,
                workflow="literature_search",
                requested_items=requested_items,
                confirmed=args.confirm_large_work,
            )
            if gate["status"] == "needs_confirmation":
                _print_json(gate)
                return 2
            _print_json(
                search_public_literature_metadata(
                    args.workspace,
                    sources=args.source or None,
                    max_results=args.max_results,
                    query_limit=args.query_limit,
                    page_limit=args.page_limit,
                    delay_seconds=args.delay_seconds,
                    resume=args.resume,
                    top_n=args.top_n,
                    reference_year=args.reference_year,
                    extra_keywords=args.keyword,
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
        if args.literature_command == "acquisition-request":
            gate = large_work_gate(
                args.workspace,
                workflow="literature_acquisition",
                confirmed=args.confirm_large_work,
            )
            if gate["status"] == "needs_confirmation":
                _print_json(gate)
                return 2
            _print_json(prepare_literature_acquisition_request(args.workspace))
            return 0
        if args.literature_command == "setup-preflight":
            _print_json(
                setup_literature_preflight(
                    args.workspace,
                    lang=args.lang,
                    write_report=not args.no_write,
                )
            )
            return 0
        if args.literature_command == "institution-access-guide":
            _print_json(
                prepare_institution_access_guidance(
                    args.workspace,
                    institution_name=args.institution_name,
                    access_method=args.access_method,
                    access_url=args.access_url,
                    access_instructions=args.access_instructions,
                    browser_name=args.browser_name,
                    browser_profile=args.browser_profile,
                    zotero_config=args.zotero_config,
                    cache_root=args.cache_root,
                    project_collection=args.project_collection,
                    authorization_status=args.authorization_status,
                    note=args.note,
                )
            )
            return 0
        if args.literature_command == "zotero-bridge":
            _print_json(
                prepare_zotero_codex_acquisition_bridge(
                    args.workspace,
                    zotero_config=args.zotero_config,
                    allow_default_config=args.allow_default_config,
                    cache_root=args.cache_root,
                    project_collection=args.project_collection,
                    browser_assist=args.enable_browser_assist,
                    browser_name=args.browser_name,
                    browser_profile=args.browser_profile,
                    institution_access=args.institution_access,
                )
            )
            return 0
        if args.literature_command == "zotero-readiness":
            output_path = args.output
            if output_path and not output_path.is_absolute():
                output_path = args.workspace / output_path
            markdown_path = args.markdown_output
            if markdown_path and not markdown_path.is_absolute():
                markdown_path = args.workspace / markdown_path
            result = summarize_zotero_codex_readiness(
                    args.workspace,
                    output_path=output_path,
                    markdown_path=markdown_path,
                    write_report=not args.no_write,
                )
            _print_json(result if args.full else _compact_zotero_readiness(result))
            return 0
        if args.literature_command == "import-acquisition":
            manifest_path = args.manifest if args.manifest.is_absolute() else args.workspace / args.manifest
            _print_json(import_literature_acquisition_manifest(args.workspace, manifest_path=manifest_path))
            return 0
        if args.literature_command == "import-zotero-status":
            result = import_zotero_codex_batch_status(
                    args.workspace,
                    batch_status_path=args.batch_status,
                    sidecar_verification_path=args.sidecar_verification,
                    status_markdown_path=args.status_markdown,
                    sync=not args.no_sync,
                )
            _print_json(result if args.full else _compact_zotero_import(result))
            return 0
        if args.literature_command == "reconcile-acquisition":
            result = reconcile_literature_acquisition(args.workspace)
            _print_json(result if args.full else _compact_reconciliation(result))
            return 0
        if args.literature_command == "render-reconciliation":
            reconciliation_path = args.reconciliation
            if reconciliation_path and not reconciliation_path.is_absolute():
                reconciliation_path = args.workspace / reconciliation_path
            _print_json(render_literature_acquisition_reconciliation(args.workspace, reconciliation_path=reconciliation_path))
            return 0
        if args.literature_command == "acceptance-checklist":
            output_path = args.output
            if output_path and not output_path.is_absolute():
                output_path = args.workspace / output_path
            markdown_path = args.markdown_output
            if markdown_path and not markdown_path.is_absolute():
                markdown_path = args.workspace / markdown_path
            _print_json(
                prepare_literature_acceptance_checklist(
                    args.workspace,
                    output_path=output_path,
                    markdown_path=markdown_path,
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
        if args.literature_command == "prepare-source-candidates":
            source_items_path = args.source_items
            if source_items_path and not source_items_path.is_absolute():
                source_items_path = args.workspace / source_items_path
            output_path = args.output
            if output_path and not output_path.is_absolute():
                output_path = args.workspace / output_path
            gate = large_work_gate(
                args.workspace,
                workflow="literature_source_candidates",
                requested_items=args.max_items,
                confirmed=args.confirm_large_work,
            )
            if gate["status"] == "needs_confirmation":
                _print_json(gate)
                return 2
            _print_json(
                prepare_literature_source_candidate_manifest(
                    args.workspace,
                    method=args.method,
                    source_items_path=source_items_path,
                    output_path=output_path,
                    confirm_for_source_packet=args.confirm_for_source_packet,
                    user_response=args.user_response,
                    max_items=args.max_items,
                )
            )
            return 0
        if args.literature_command == "preflight-source-candidates":
            manifest_path = args.manifest if args.manifest.is_absolute() else args.workspace / args.manifest
            output_path = args.output
            if output_path and not output_path.is_absolute():
                output_path = args.workspace / output_path
            _print_json(
                preflight_literature_source_candidate_manifest(
                    args.workspace,
                    method=args.method,
                    manifest_path=manifest_path,
                    output_path=output_path,
                )
            )
            return 0
        if args.literature_command == "data-plan":
            _print_json(
                plan_literature_data_extraction(
                    args.workspace,
                    property_name=args.property,
                    property_kind=args.kind,
                    material_name=args.material,
                    sources=args.source,
                    required_conditions=args.required_condition,
                    comparability_rules=args.comparability_rule,
                    dataset_id=args.dataset_id,
                    confirmed=args.yes,
                )
            )
            return 0
        if args.literature_command == "data-extract":
            _print_json(
                extract_literature_data(
                    args.workspace,
                    dataset_id=args.dataset,
                    max_sources=args.max_sources,
                    confirmed=args.yes,
                )
            )
            return 0
        if args.literature_command == "data-review":
            conditions: dict[str, str] = {}
            for value in args.condition:
                if "=" not in value:
                    raise ValueError("--condition must use name=value")
                key, condition_value = value.split("=", 1)
                conditions[key.strip()] = condition_value.strip()
            _print_json(
                review_literature_data(
                    args.workspace,
                    dataset_id=args.dataset,
                    record_id=args.record,
                    decision=args.decision,
                    notes=args.note,
                    reported_value=args.reported_value,
                    reported_unit=args.reported_unit,
                    normalized_value=args.normalized_value,
                    normalized_unit=args.normalized_unit,
                    conditions=conditions,
                    confirmed=args.yes,
                )
            )
            return 0
        if args.literature_command == "data-validate":
            _print_json(validate_literature_data(args.workspace, dataset_id=args.dataset, write_report=not args.no_write))
            return 0
        if args.literature_command == "data-plot":
            _print_json(plot_literature_data(args.workspace, dataset_id=args.dataset, confirmed=args.yes))
            return 0
        if args.literature_command == "data-export":
            _print_json(export_literature_data(args.workspace, dataset_id=args.dataset, confirmed=args.yes))
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
        if args.references_command == "register-seeds":
            project_id = args.project_id or _project_id_from_workspace(args.workspace)
            _print_json(
                register_reference_seeds(
                    args.workspace,
                    _project_path(args.workspace, args.source_packet),
                    project_id=project_id,
                    seed_ids=args.seed_id,
                    source_type=args.source_type,
                    dry_run=args.dry_run,
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
            frontmatter, _ = read_markdown_record(path)
            review_id = (frontmatter.get("review_refs") or [None])[-1]
            review = read_yaml(args.workspace / "reviews" / f"{review_id}.yml") if review_id else {}
            candidate_status = frontmatter.get("status")
            if candidate_status == "user_confirmed":
                next_action = "Run `ea memory commit` with this candidate and review_id when the user wants durable project memory."
            elif candidate_status == "needs_revision":
                next_action = "Edit or repropose the candidate, then review it again before commit."
            elif candidate_status == "rejected":
                next_action = "No commit is allowed; keep the rejected candidate as audit history or propose a replacement."
            else:
                next_action = "Keep the candidate deferred; ask the user for a clearer confirmation before commit."
            _print_json(
                {
                    "candidate": str(path),
                    "memory_candidate_id": frontmatter.get("memory_candidate_id"),
                    "candidate_status": candidate_status,
                    "review_id": review_id,
                    "review_status": review.get("review_status"),
                    "decision": review.get("decision"),
                    "next_action": next_action,
                }
            )
            return 0
        if args.memory_command == "commit":
            path = commit_memory_candidate(
                args.workspace,
                candidate_path=args.candidate,
                review_ref=args.review_ref,
            )
            _print_json({"memory": str(path)})
            return 0
        if args.memory_command == "refresh-project":
            _print_json(
                refresh_project_working_memory(
                    args.workspace,
                    project_id=args.project_id,
                    max_items=args.max_items,
                )
            )
            return 0
        if args.memory_command == "show-project":
            _print_json(show_project_working_memory(args.workspace, compact=not args.full))
            return 0
    if args.command == "estimate":
        if args.estimate_command == "workflow":
            _print_json(
                estimate_workflow(
                    args.workspace,
                    workflow=args.workflow,
                    requested_items=args.items,
                    mode=args.mode,
                )
            )
            return 0
        if args.estimate_command == "reminders":
            if args.disable:
                _print_json(set_large_work_reminders(args.workspace, disabled=True, reason=args.reason or "user_disabled"))
                return 0
            if args.enable:
                _print_json(set_large_work_reminders(args.workspace, disabled=False, reason=args.reason or "user_enabled"))
                return 0
            _print_json(
                {
                    "preferences_path": str(args.workspace / ".ea" / "preferences.yml"),
                    "large_work_reminders_disabled": large_work_reminders_disabled(args.workspace),
                }
            )
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
    if args.command == "trace":
        if args.trace_command == "index":
            output_path = args.output
            if output_path and not output_path.is_absolute():
                output_path = args.workspace / output_path
            result = build_trace_index(args.workspace, output_path=output_path)
            if args.json_full:
                _print_json(_trace_full_result(result))
            elif args.json:
                _print_json(_compact_trace_result(result))
            else:
                _print_trace_summary(result, label="index")
            return 0
        if args.trace_command == "view":
            output_path = args.output
            if output_path and not output_path.is_absolute():
                output_path = args.workspace / output_path
            markdown_output_path = args.markdown_output
            if markdown_output_path and not markdown_output_path.is_absolute():
                markdown_output_path = args.workspace / markdown_output_path
            result = build_project_trace_view(
                args.workspace,
                focus_ref=args.focus,
                output_path=output_path,
                markdown_output_path=markdown_output_path,
            )
            if args.json_full:
                _print_json(_trace_full_result(result))
            elif args.json:
                _print_json(_compact_trace_result(result))
            else:
                _print_trace_summary(result, label="view")
            return 0
        if args.trace_command == "focus":
            output_path = args.output
            if output_path and not output_path.is_absolute():
                output_path = args.workspace / output_path
            markdown_output_path = args.markdown_output
            if markdown_output_path and not markdown_output_path.is_absolute():
                markdown_output_path = args.workspace / markdown_output_path
            result = build_trace_focus(
                args.workspace,
                args.record_ref,
                depth=args.depth,
                output_path=output_path,
                markdown_output_path=markdown_output_path,
            )
            if args.json_full:
                _print_json(_trace_full_result(result))
            elif args.json:
                _print_json(_compact_trace_result(result))
            else:
                _print_trace_summary(result, label="focus")
            return 0
        if args.trace_command == "export":
            if not args.full:
                _print_json({"status": "fail", "error": "trace export currently requires --full"})
                return 2
            output_path = args.output
            if output_path and not output_path.is_absolute():
                output_path = args.workspace / output_path
            markdown_output_path = args.markdown_output
            if markdown_output_path and not markdown_output_path.is_absolute():
                markdown_output_path = args.workspace / markdown_output_path
            result = export_full_trace(
                args.workspace,
                output_path=output_path,
                markdown_output_path=markdown_output_path,
            )
            if args.json_full:
                _print_json(_trace_full_result(result))
            elif args.json:
                _print_json(_compact_trace_result(result))
            else:
                _print_trace_summary(result, label="export")
            return 0
        if args.trace_command == "lookup":
            output_path = args.output
            if output_path and not output_path.is_absolute():
                output_path = args.workspace / output_path
            markdown_output_path = args.markdown_output
            if markdown_output_path and not markdown_output_path.is_absolute():
                markdown_output_path = args.workspace / markdown_output_path
            result = lookup_trace_record(
                args.workspace,
                args.record_ref,
                output_path=output_path,
                markdown_output_path=markdown_output_path,
            )
            if args.json_full:
                _print_json(_trace_full_result(result))
            elif args.json:
                _print_json(_compact_trace_result(result))
            else:
                _print_trace_summary(result, label="lookup")
            return 0
    if args.command == "lookup-figure":
        _print_json(lookup_figure(args.workspace, args.figure_id))
        return 0
    raise AssertionError(f"Unhandled command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    try:
        return _main_impl(argv)
    except (RuntimeError, ValueError, FileNotFoundError, KeyError, OSError) as exc:
        _print_json(error_record(exc))
        return 2
