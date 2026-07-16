from __future__ import annotations

from ea import __version__


PRODUCT_NAME = "Experimental Assistant"
PRODUCT_SUBTITLE = "local-first materials research assistant"
DISPLAY_VERSION = f"v{__version__}"
PUBLIC_VERSION = f"{PRODUCT_NAME} {DISPLAY_VERSION}"
RELEASE_LABEL = DISPLAY_VERSION

DISTRIBUTION_NAME = "experimental-assistant"
LEGACY_DISTRIBUTION_NAMES = ("ea-v0-2",)
IMPORT_PACKAGE_NAME = "ea"
CLI_NAME = "ea"

SKILL_NAME = "ea"
SKILL_INVOCATION = "$ea"
# Retained only so setup/doctor can remove stale pre-v1 compatibility installs.
# It is not a supported public skill or invocation.
RETIRED_SKILL_NAMES = ("ea-v0-2",)

PROJECT_FORMAT_VERSION = "1.0"
SUPPORTED_PYTHON_MINORS = ((3, 11), (3, 12), (3, 13))
OBSERVATION_PYTHON_MINORS = ((3, 14),)
REPOSITORY_URL = "https://github.com/gongchenisbusy/Experimental-Assistant"


CAPABILITY_MATURITY = {
    "stable": (
        "installation_lifecycle",
        "project_lifecycle_and_migration",
        "protected_raw_import",
        "review_provenance_and_references",
        "health_evaluation_brief_and_traceability",
        "html_reports_and_verified_exports",
        "raman_benchmark_bounded_analysis",
    ),
    "beta": (
        "pl_analysis",
        "xrd_analysis",
        "ftir_source_backed_assignments",
        "uv_vis_screening",
        "xps_assistance",
        "electrochemistry_derived_metrics",
        "thermal_analysis",
        "batch_workflows",
        "public_literature_metadata_search",
        "literature_evidence_datasets",
    ),
    "experimental": (
        "zotero_browser_and_institution_acquisition_orchestration",
        "broad_full_text_acquisition",
        "advanced_image_interpretation",
    ),
}


PUBLIC_CAPABILITY_CONTRACT = {
    "supported_workflows": (
        "project_lifecycle_and_migration",
        "protected_raw_import_and_duplicate_detection",
        "review_records_provenance_and_references",
        "characterization_inspect_process_report_workflows",
        "raman_benchmark_bounded_analysis",
        "user_defined_literature_data_collection",
        "health_evaluation_trace_and_verified_exports",
    ),
    "review_required": (
        "scientific_interpretations",
        "literature_extraction_candidates",
        "parameters_and_durable_memory",
    ),
    "optional_integrations": (
        "public_literature_metadata_search",
        "zotero_browser_and_institution_access_handoff",
    ),
    "boundaries": (
        "no_autonomous_scientific_proof",
        "no_exhaustive_literature_coverage_claim",
        "no_access_control_bypass_or_credential_storage",
    ),
}
