from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class EARecord(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    schema_version: str = "0.2"
    created_at: str | None = None
    updated_at: str | None = None
    status: str | None = None
    source_refs: list[str] = Field(default_factory=list)
    provenance_refs: list[str] = Field(default_factory=list)
    review_refs: list[str] = Field(default_factory=list)

    @staticmethod
    def now_iso() -> str:
        return datetime.now().replace(microsecond=0).isoformat()


class Project(EARecord):
    project_id: str
    project_name: str
    project_slug: str | None = None
    research_direction: str
    material_system: str
    experiment_type: str
    default_language: Literal["zh", "en"] = "zh"
    workspace_mode: Literal["single_project"] = "single_project"
    rule_card_ref: str = "PROJECT_RULE_CARD.md"
    knowledge_global_dir: str = "knowledge/global/"
    knowledge_project_dir: str = "knowledge/project/"
    current_stage: str | None = None
    description: str | None = None
    owner: str | None = None
    notes: str | None = None


class ProjectRuleCard(EARecord):
    rule_card_id: str
    project_id: str
    version: int = 1
    status: Literal["draft", "user_confirmed", "needs_update"] = "draft"
    research_direction: str
    material_system: str
    experiment_type: str
    sample_id_rule_ref: str = "needs_user_review"
    sample_quality_rule_ref: str = "needs_user_review"
    default_report_language: Literal["zh", "en"] = "zh"
    raw_file_policy: Literal["controlled_readonly_copy"] = "controlled_readonly_copy"
    knowledge_policy_ref: str = "needs_user_review"


class ExperimentRecord(EARecord):
    experiment_id: str
    project_id: str
    experiment_date: str
    material_system: str
    experiment_type: str
    status: Literal["user_confirmed"] = "user_confirmed"
    user_original_text: str
    structured_by: str
    sample_refs: list[str] = Field(default_factory=list)
    process_conditions: dict[str, Any] = Field(default_factory=dict)
    observations: list[str] = Field(default_factory=list)
    initial_judgement: str | None = None
    uncertainties: list[str] = Field(default_factory=list)
    related_files: list[str] = Field(default_factory=list)


class SampleRecord(EARecord):
    sample_id: str
    project_id: str
    material_system: str
    created_from_experiment: str
    status: str
    substrate: str | None = None
    sample_type: str | None = None
    morphology_observations: list[str] = Field(default_factory=list)
    quality_notes: list[str] = Field(default_factory=list)
    quality_status: Literal[
        "unknown", "candidate_good", "candidate_medium", "candidate_poor"
    ] = "unknown"
    characterization_refs: list[str] = Field(default_factory=list)
    report_refs: list[str] = Field(default_factory=list)


class CharacterizationFile(EARecord):
    characterization_id: str
    project_id: str
    sample_refs: list[str] = Field(default_factory=list)
    characterization_type: str = "raman"
    original_source_path: str
    project_raw_path: str
    sha256: str
    file_size_bytes: int
    imported_at: str
    import_status: Literal["imported", "duplicate_alias", "needs_review", "failed"]
    original_filename: str | None = None
    aliases: list[dict[str, Any]] = Field(default_factory=list)
    instrument_metadata: dict[str, Any] = Field(default_factory=dict)
    column_candidates: list[dict[str, Any]] = Field(default_factory=list)
    notes: str | None = None


class RamanProcessingResult(EARecord):
    raman_result_id: str
    project_id: str
    characterization_file_ref: str
    sample_refs: list[str] = Field(default_factory=list)
    status: Literal["success", "warning", "failed"]
    x_column: str
    y_column: str
    x_unit: Literal["cm^-1", "unknown"] = "unknown"
    processing_parameters: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)
    warnings: list[Any] = Field(default_factory=list)


class PLProcessingResult(EARecord):
    pl_result_id: str
    result_id: str
    project_id: str
    characterization_file_ref: str
    sample_refs: list[str] = Field(default_factory=list)
    status: Literal["success", "warning", "failed"]
    x_column: str
    y_column: str
    x_unit: Literal["eV", "nm", "unknown"] = "unknown"
    processing_parameters: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)
    peak_analysis: dict[str, Any] = Field(default_factory=dict)
    figure_id: str | None = None
    warnings: list[Any] = Field(default_factory=list)


class XRDProcessingResult(EARecord):
    xrd_result_id: str
    result_id: str
    project_id: str
    characterization_file_ref: str
    sample_refs: list[str] = Field(default_factory=list)
    status: Literal["success", "warning", "failed"]
    x_column: str
    y_column: str
    x_unit: Literal["2theta_deg", "unknown"] = "unknown"
    wavelength_angstrom: float | None = None
    processing_parameters: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)
    peak_analysis: dict[str, Any] = Field(default_factory=dict)
    figure_id: str | None = None
    warnings: list[Any] = Field(default_factory=list)


class FTIRProcessingResult(EARecord):
    ftir_result_id: str
    result_id: str
    project_id: str
    characterization_file_ref: str
    sample_refs: list[str] = Field(default_factory=list)
    status: Literal["success", "warning", "failed"]
    x_column: str
    y_column: str
    x_unit: Literal["cm^-1", "unknown"] = "unknown"
    signal_mode: Literal["absorbance", "transmittance"] = "absorbance"
    processing_parameters: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)
    peak_analysis: dict[str, Any] = Field(default_factory=dict)
    figure_id: str | None = None
    warnings: list[Any] = Field(default_factory=list)


class UVVisProcessingResult(EARecord):
    uv_vis_result_id: str
    result_id: str
    project_id: str
    characterization_file_ref: str
    sample_refs: list[str] = Field(default_factory=list)
    status: Literal["success", "warning", "failed"]
    x_column: str
    y_column: str
    x_unit: Literal["nm", "eV", "unknown"] = "unknown"
    signal_mode: Literal["absorbance", "transmittance", "reflectance"] = "absorbance"
    processing_parameters: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)
    peak_analysis: dict[str, Any] = Field(default_factory=dict)
    figure_id: str | None = None
    warnings: list[Any] = Field(default_factory=list)


class XPSProcessingResult(EARecord):
    xps_result_id: str
    result_id: str
    project_id: str
    characterization_file_ref: str
    sample_refs: list[str] = Field(default_factory=list)
    status: Literal["success", "warning", "failed"]
    x_column: str
    y_column: str
    x_unit: Literal["eV", "unknown"] = "unknown"
    energy_shift_eV: float = 0.0
    calibration_reference: str | None = None
    processing_parameters: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)
    peak_analysis: dict[str, Any] = Field(default_factory=dict)
    figure_id: str | None = None
    warnings: list[Any] = Field(default_factory=list)


class ImageAnalysisResult(EARecord):
    image_result_id: str
    result_id: str
    project_id: str
    characterization_file_ref: str
    sample_refs: list[str] = Field(default_factory=list)
    method: str
    analysis_mode: Literal["user_described", "agent_visual_review", "mixed"] = "user_described"
    user_description: str
    ea_observations: list[str] = Field(default_factory=list)
    interpretation: str | None = None
    confidence: Literal["high", "medium", "low", "insufficient"] = "insufficient"
    scale_bar: str | None = None
    imaging_conditions: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)
    figure_id: str | None = None
    warnings: list[Any] = Field(default_factory=list)
    references: list[dict[str, Any]] = Field(default_factory=list)
    reference_ids: list[str] = Field(default_factory=list)


class ReportRecord(EARecord):
    report_id: str
    project_id: str
    report_type: Literal["raman_analysis", "pl_analysis", "xrd_analysis", "ftir_analysis", "uv_vis_analysis", "xps_analysis", "image_analysis"]
    language: Literal["zh", "en"] = "zh"
    audience: Literal["self"] = "self"
    related_experiments: list[str] = Field(default_factory=list)
    related_samples: list[str] = Field(default_factory=list)
    related_results: list[str] = Field(default_factory=list)
    figure_ids: list[str] = Field(default_factory=list)
    include_next_step_suggestions: bool = False
    status: Literal["draft", "user_reviewed"] = "draft"


class ReferenceRecord(EARecord):
    reference_id: str
    project_id: str
    citation: str
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    url: str | None = None
    local_path: str | None = None
    source_type: Literal["manual", "literature_library", "web", "local_pdf", "report"] = "manual"
    notes: str | None = None


class ReviewRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    review_id: str
    target_type: str
    target_ref: str
    review_status: Literal[
        "user_confirmed", "user_edited", "user_rejected", "deferred"
    ]
    decision: str
    reviewed_at: str
    user_original_text: str
    reviewed_content_hash: str
    previous_target_hash: str | None = None
    notes: str | None = None
    previous_review_ref: str | None = None
    replacement_target_ref: str | None = None


class ProvenanceEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    provenance_id: str
    workflow: str
    created_at: str
    skill_name: str
    skill_version: str
    inputs: dict[str, list[str]] = Field(
        default_factory=lambda: {"records": [], "files": []}
    )
    outputs: dict[str, list[str]] = Field(
        default_factory=lambda: {"records": [], "files": []}
    )
    parameters: dict[str, Any] = Field(default_factory=dict)
    review_refs: list[str] = Field(default_factory=list)
    warnings: list[Any] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    scripts: list[dict[str, Any]] = Field(default_factory=list)


class ProgressEvent(BaseModel):
    progress_id: str
    recorded_at: str
    user_original_text: str
    ea_summary: str
    event_type: Literal[
        "experiment", "characterization", "data_upload", "analysis", "report", "decision"
    ]
    source_refs: list[str] = Field(default_factory=list)
    review_refs: list[str] = Field(default_factory=list)
    occurred_at: str | None = None
    related_experiments: list[str] = Field(default_factory=list)
    related_samples: list[str] = Field(default_factory=list)
    related_files: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)


class SuggestionRecord(BaseModel):
    suggestion_id: str
    project_id: str
    status: Literal["draft", "accepted", "modified", "rejected"] = "draft"
    created_at: str
    trigger: str
    related_records: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    suggestion_text: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    user_response: str | None = None
    review_refs: list[str] = Field(default_factory=list)


class OpenItem(BaseModel):
    open_item_id: str
    created_at: str
    item_type: str
    description: str
    related_records: list[str] = Field(default_factory=list)
    priority: Literal["high", "medium", "low"] = "medium"
    status: Literal["open", "resolved", "deferred"] = "open"
    source_refs: list[str] = Field(default_factory=list)
