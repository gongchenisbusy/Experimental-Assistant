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
    ),
    "beta": (
        "raman_analysis_pending_external_benchmark_signoff",
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
