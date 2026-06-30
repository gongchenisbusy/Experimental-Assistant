from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from ea.batch import BatchManifestError, run_batch_manifest, validate_batch_manifest
from ea.config import doctor_project_config
from ea.electrochemistry import (
    ElectrochemistryProcessingRequest,
    default_electrochemistry_processing_parameters,
    inspect_electrochemistry_file,
    process_electrochemistry_result,
)
from ea.evaluation import run_project_evaluation
from ea.exports import (
    ReportBundleError,
    export_batch_bundle,
    export_report_bundle,
    verify_archive_checksum,
    verify_bundle_checksums,
)
from ea.figures import lookup_figure
from ea.ftir import FTIRProcessingRequest, default_ftir_processing_parameters, inspect_ftir_file, process_ftir_result
from ea.healthcheck import run_healthcheck
from ea.image_data import create_image_analysis_record, generate_image_analysis_report
from ea.literature import (
    confirm_literature_selection,
    ensure_literature_status,
    import_literature_acquisition_manifest,
    import_zotero_codex_batch_status,
    plan_literature_deployment,
    prepare_literature_acquisition_request,
    prepare_literature_acquisition_handoff,
    prepare_zotero_codex_acquisition_bridge,
    rank_literature_candidates,
    search_public_literature_metadata,
    sync_literature_acquisition_status,
)
from ea.materials import assignment_candidates, available_materials, get_material_profile
from ea.memory import commit_memory_candidate, propose_memory_candidate, review_memory_candidate
from ea.pl import PLProcessingRequest, default_pl_processing_parameters, inspect_pl_file, process_pl_result
from ea.projects.service import initialize_project
from ea.raman import RamanProcessingRequest, default_processing_parameters, inspect_spectrum_file, process_raman_result
from ea.raw_import import import_raw_file
from ea.references import import_bibtex_references, register_reference, validate_report_citations
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
from ea.review import write_review_record
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
from ea.uv_vis import UVVisProcessingRequest, default_uv_vis_processing_parameters, inspect_uv_vis_file, process_uv_vis_result
from ea.xps import XPSProcessingRequest, default_xps_processing_parameters, inspect_xps_file, process_xps_result
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

    export_parser = sub.add_parser("export", help="export local EA handoff bundles")
    export_sub = export_parser.add_subparsers(dest="export_command", required=True)
    report_bundle = export_sub.add_parser("report-bundle", help="bundle one report with figures, source data, and traceability records")
    report_bundle.add_argument("workspace", type=Path)
    report_bundle.add_argument("--report-id", required=True)
    report_bundle.add_argument("--output", type=Path)
    report_bundle.add_argument("--zip", action="store_true", help="also create a deterministic zip archive next to the bundle")
    report_bundle.add_argument("--zip-output", type=Path, help="write the optional zip archive to this path")
    batch_bundle = export_sub.add_parser("batch-bundle", help="bundle one batch run with nested report bundles")
    batch_bundle.add_argument("workspace", type=Path)
    batch_bundle.add_argument("--batch-id", required=True)
    batch_bundle.add_argument("--output", type=Path)
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

    ftir = sub.add_parser("ftir", help="FTIR inspection, processing, and report helpers")
    ftir_sub = ftir.add_subparsers(dest="ftir_command", required=True)
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

    uv_vis = sub.add_parser("uv-vis", help="UV-Vis inspection, processing, and report helpers")
    uv_vis_sub = uv_vis.add_subparsers(dest="uv_vis_command", required=True)
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

    xps = sub.add_parser("xps", help="XPS inspection, processing, and report helpers")
    xps_sub = xps.add_subparsers(dest="xps_command", required=True)
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
    electrochemistry_process.add_argument("--x-unit", choices=["V", "mV", "s", "unknown"], required=True)
    electrochemistry_process.add_argument("--current-unit", choices=["A", "mA", "uA", "µA", "unknown"], required=True)
    electrochemistry_process.add_argument("--measurement-mode", choices=["cv", "lsv", "chrono", "gcd", "unknown"], required=True)
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
    lit_handoff = literature_sub.add_parser("handoff", help="prepare an acquisition handoff packet for a dedicated literature workflow")
    lit_handoff.add_argument("workspace", type=Path)
    lit_handoff.add_argument("--mode", choices=["dedicated_thread", "manual_agent", "same_thread"], default="dedicated_thread")
    lit_handoff.add_argument("--literature-thread-id")
    lit_request = literature_sub.add_parser("acquisition-request", help="prepare confirmed acquisition request and Zotero-Codex target manifests")
    lit_request.add_argument("workspace", type=Path)
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
    lit_import = literature_sub.add_parser("import-acquisition", help="import acquisition manifest output from a dedicated literature workflow")
    lit_import.add_argument("workspace", type=Path)
    lit_import.add_argument("--manifest", required=True, type=Path)
    lit_zotero_status = literature_sub.add_parser("import-zotero-status", help="import Zotero-Codex batch status into EA sync records")
    lit_zotero_status.add_argument("workspace", type=Path)
    lit_zotero_status.add_argument("--batch-status", type=Path)
    lit_zotero_status.add_argument("--sidecar-verification", type=Path)
    lit_zotero_status.add_argument("--status-markdown", type=Path)
    lit_zotero_status.add_argument("--no-sync", action="store_true")
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

    materials = sub.add_parser("materials", help="inspect built-in material assignment records")
    materials_sub = materials.add_subparsers(dest="materials_command", required=True)
    materials_sub.add_parser("list", help="list materials with built-in assignment records")
    material_show = materials_sub.add_parser("show", help="show a material assignment profile")
    material_show.add_argument("material")
    material_assignments = materials_sub.add_parser("assignments", help="show assignment records for one method")
    material_assignments.add_argument("material")
    material_assignments.add_argument("--method", choices=["raman", "pl", "xrd"])

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
    if args.command == "ftir":
        project_id = getattr(args, "project_id", None)
        if args.ftir_command in {"process", "report"} and not project_id:
            project_id = _project_id_from_workspace(args.workspace)
        if args.ftir_command == "inspect":
            inspection = asdict(inspect_ftir_file(_project_path(args.workspace, args.spectrum)))
            inspection["path"] = str(inspection["path"])
            _print_json(inspection)
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
            )
            _print_json({"report": str(path)})
            return 0
    if args.command == "uv-vis":
        project_id = getattr(args, "project_id", None)
        if args.uv_vis_command in {"process", "report"} and not project_id:
            project_id = _project_id_from_workspace(args.workspace)
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
            )
            _print_json({"report": str(path)})
            return 0
    if args.command == "xps":
        project_id = getattr(args, "project_id", None)
        if args.xps_command in {"process", "report"} and not project_id:
            project_id = _project_id_from_workspace(args.workspace)
        if args.xps_command == "inspect":
            inspection = asdict(inspect_xps_file(_project_path(args.workspace, args.spectrum)))
            inspection["path"] = str(inspection["path"])
            _print_json(inspection)
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
            )
            _print_json({"report": str(path)})
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
            _print_json(prepare_literature_acquisition_request(args.workspace))
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
        if args.literature_command == "import-acquisition":
            manifest_path = args.manifest if args.manifest.is_absolute() else args.workspace / args.manifest
            _print_json(import_literature_acquisition_manifest(args.workspace, manifest_path=manifest_path))
            return 0
        if args.literature_command == "import-zotero-status":
            _print_json(
                import_zotero_codex_batch_status(
                    args.workspace,
                    batch_status_path=args.batch_status,
                    sidecar_verification_path=args.sidecar_verification,
                    status_markdown_path=args.status_markdown,
                    sync=not args.no_sync,
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
