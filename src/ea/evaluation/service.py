from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
import re
from typing import Any, Literal

from ea.config import doctor_project_config
from ea.figures import NATURE_LIKE_STYLE_PROFILE
from ea.healthcheck import run_healthcheck
from ea.references import validate_report_citations
from ea.storage.files import read_markdown_record, read_yaml, write_yaml
from ea.storage.ids import next_id

EvaluationSeverity = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class EvaluationFinding:
    severity: EvaluationSeverity
    code: str
    message: str
    path: str | None = None
    ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _project_path(root: Path, ref: str) -> Path:
    path = Path(str(ref).split("#", 1)[0])
    return path if path.is_absolute() else root / path


def _safe_read_yaml(path: Path, findings: list[EvaluationFinding]) -> dict[str, Any]:
    try:
        return read_yaml(path)
    except Exception as exc:  # pragma: no cover - parser exception classes vary
        findings.append(
            EvaluationFinding(
                "error",
                "unreadable_yaml",
                f"Could not read YAML during evaluation: {exc}",
                path=str(path),
            )
        )
        return {}


def _safe_read_markdown(path: Path, findings: list[EvaluationFinding]) -> tuple[dict[str, Any], str]:
    try:
        return read_markdown_record(path)
    except Exception as exc:  # pragma: no cover - parser exception classes vary
        findings.append(
            EvaluationFinding(
                "error",
                "unreadable_markdown_record",
                f"Could not read Markdown record during evaluation: {exc}",
                path=str(path),
            )
        )
        return {}, ""


def _evaluation_status(error_count: int, warning_count: int) -> str:
    if error_count:
        return "fail"
    if warning_count:
        return "warning"
    return "pass"


def _external_literature_summary(root: Path, findings: list[EvaluationFinding]) -> dict[str, Any]:
    path = root / "literature" / "external_acquisition_state.yml"
    if not path.exists():
        return {
            "external_cache_used": False,
            "ready_count": 0,
            "blocked_count": 0,
            "state_ref": None,
        }
    state = _safe_read_yaml(path, findings)
    summary = state.get("summary") or {}
    return {
        "external_cache_used": bool(int(summary.get("ready_count") or 0)),
        "ready_count": int(summary.get("ready_count") or 0),
        "blocked_count": int(summary.get("blocked_count") or 0),
        "current_task_blocker_count": len(state.get("current_task_blockers") or []),
        "optional_capability_count": len(state.get("optional_capabilities") or []),
        "stale_global_state_count": len(state.get("stale_global_state") or []),
        "state_ref": "literature/external_acquisition_state.yml",
    }


def _check_project_record(root: Path, findings: list[EvaluationFinding]) -> dict[str, Any]:
    project_path = root / "EA_PROJECT.md"
    if not project_path.exists():
        findings.append(
            EvaluationFinding(
                "error",
                "project_record_missing",
                "EA_PROJECT.md is missing; initialize the project before evaluation.",
                path=str(project_path),
            )
        )
        return {"project_id": None, "project_slug": None}
    frontmatter, _ = _safe_read_markdown(project_path, findings)
    if not frontmatter.get("project_id"):
        findings.append(
            EvaluationFinding(
                "error",
                "project_id_missing",
                "EA_PROJECT.md frontmatter is missing project_id.",
                path=str(project_path),
            )
        )
    if not frontmatter.get("project_slug"):
        findings.append(
            EvaluationFinding(
                "warning",
                "project_slug_missing",
                "EA_PROJECT.md frontmatter is missing project_slug; ID generation may be less readable.",
                path=str(project_path),
            )
        )
    return {
        "project_id": frontmatter.get("project_id"),
        "project_slug": frontmatter.get("project_slug"),
        "project_name": frontmatter.get("project_name"),
    }


def _check_config(root: Path, findings: list[EvaluationFinding]) -> dict[str, Any]:
    doctor = doctor_project_config(root)
    status = doctor.get("status")
    if status == "missing":
        findings.append(
            EvaluationFinding(
                "warning",
                "config_missing",
                "Project config is missing; public-user portability cannot be evaluated fully.",
                path=str(doctor.get("config_path")),
            )
        )
    elif status != "pass":
        findings.append(
            EvaluationFinding(
                "error",
                "config_portability_failed",
                "Project config failed public-release portability checks.",
                path=str(doctor.get("config_path")),
                ref=",".join(doctor.get("errors") or []),
            )
        )

    config_path = root / ".ea" / "project_config.yml"
    config = _safe_read_yaml(config_path, findings) if config_path.exists() else {}
    literature = config.get("literature") or {}
    if literature.get("enabled") and not (root / "literature" / "deployment_status.yml").exists():
        findings.append(
            EvaluationFinding(
                "warning",
                "literature_status_missing",
                "Literature support is enabled but literature/deployment_status.yml is missing.",
                path=str(config_path),
            )
        )
    return {
        "doctor_status": status,
        "doctor_errors": doctor.get("errors", []),
        "doctor_warnings": doctor.get("warnings", []),
        "literature_enabled": bool(literature.get("enabled")),
    }


def _include_healthcheck_findings(healthcheck: dict[str, Any], findings: list[EvaluationFinding]) -> None:
    for item in healthcheck.get("findings") or []:
        severity = item.get("severity")
        if severity not in {"error", "warning", "info"}:
            severity = "warning"
        findings.append(
            EvaluationFinding(
                severity,  # type: ignore[arg-type]
                f"healthcheck.{item.get('code', 'unknown')}",
                f"Healthcheck finding: {item.get('message', '')}",
                path=item.get("path"),
                ref=item.get("ref"),
            )
        )


def _check_figures(root: Path, findings: list[EvaluationFinding]) -> dict[str, Any]:
    index_path = root / "figures" / "index.yml"
    processed_results = list((root / "processed").glob("**/*.yml"))
    if not index_path.exists():
        if processed_results:
            findings.append(
                EvaluationFinding(
                    "warning",
                    "figure_index_missing",
                    "Processed result metadata exists but figures/index.yml is missing.",
                    path=str(index_path),
                )
            )
        return {"figure_count": 0, "analysis_figure_count": 0, "style_profile_count": 0, "source_data_ref_count": 0}

    figures = _safe_read_yaml(index_path, findings).get("figures", {})
    analysis_count = 0
    style_count = 0
    source_ref_count = 0
    for figure_id, figure in figures.items():
        is_analysis_figure = bool(figure.get("result_id") or figure.get("purpose") == "analysis_report")
        if not is_analysis_figure:
            continue
        analysis_count += 1
        style_profile = figure.get("style_profile")
        if style_profile:
            style_count += 1
            if style_profile != NATURE_LIKE_STYLE_PROFILE:
                findings.append(
                    EvaluationFinding(
                        "warning",
                        "figure_style_profile_unexpected",
                        "Analysis figure uses a style_profile other than EA's shared scientific profile.",
                        path=str(index_path),
                        ref=str(figure_id),
                    )
                )
        else:
            findings.append(
                EvaluationFinding(
                    "warning",
                    "figure_style_profile_missing",
                    "Analysis figure is missing style_profile metadata.",
                    path=str(index_path),
                    ref=str(figure_id),
                )
            )
        source_refs = list(figure.get("source_data_refs") or [])
        source_ref_count += len(source_refs)
        if not source_refs:
            findings.append(
                EvaluationFinding(
                    "warning",
                    "figure_source_data_refs_missing",
                    "Analysis figure is missing source_data_refs; later agents may not find the exact plotted data.",
                    path=str(index_path),
                    ref=str(figure_id),
                )
            )
            continue
        for source_ref in source_refs:
            if not _project_path(root, str(source_ref)).exists():
                findings.append(
                    EvaluationFinding(
                        "error",
                        "figure_source_data_ref_missing",
                        "Analysis figure source_data_refs points to a missing file.",
                        path=str(index_path),
                        ref=f"{figure_id}:{source_ref}",
                    )
                )
    return {
        "figure_count": len(figures),
        "analysis_figure_count": analysis_count,
        "style_profile_count": style_count,
        "source_data_ref_count": source_ref_count,
    }


def _check_reports(root: Path, findings: list[EvaluationFinding]) -> dict[str, Any]:
    index_path = root / "reports" / "index.yml"
    if not index_path.exists():
        if list((root / "processed").glob("**/*.yml")):
            findings.append(
                EvaluationFinding(
                    "warning",
                    "report_index_missing",
                    "Processed results exist but reports/index.yml is missing.",
                    path=str(index_path),
                )
            )
        return {"report_count": 0, "citation_validated_count": 0, "provenance_backed_count": 0}

    reports = _safe_read_yaml(index_path, findings).get("reports", {})
    citation_validated_count = 0
    provenance_backed_count = 0
    for report_id, report in reports.items():
        report_ref = report.get("path")
        if not report_ref:
            findings.append(
                EvaluationFinding(
                    "error",
                    "report_path_missing",
                    "Report index record is missing path.",
                    path=str(index_path),
                    ref=str(report_id),
                )
            )
            continue
        report_path = _project_path(root, str(report_ref))
        if not report_path.exists():
            continue
        frontmatter, body = _safe_read_markdown(report_path, findings)
        if frontmatter.get("provenance_refs"):
            provenance_backed_count += 1
        else:
            findings.append(
                EvaluationFinding(
                    "warning",
                    "report_provenance_refs_missing",
                    "Report frontmatter is missing provenance_refs.",
                    path=str(report_path),
                    ref=str(report_id),
                )
            )
        citation_result = validate_report_citations(report_path)
        citation_validated_count += 1
        if not citation_result["ok"]:
            findings.append(
                EvaluationFinding(
                    "error",
                    "report_citation_validation_failed",
                    "Report inline numeric citations do not match References entries.",
                    path=str(report_path),
                    ref=str(citation_result),
                )
            )
        if frontmatter.get("reference_ids") and not re.search(
            r"(?m)^##\s+(?:References|参考文献)\s*$", body
        ):
            findings.append(
                EvaluationFinding(
                    "error",
                    "report_references_section_missing",
                    "Report has reference_ids but no References section.",
                    path=str(report_path),
                    ref=str(report_id),
                )
            )
    return {
        "report_count": len(reports),
        "citation_validated_count": citation_validated_count,
        "provenance_backed_count": provenance_backed_count,
    }


def _check_batches(root: Path, findings: list[EvaluationFinding]) -> dict[str, Any]:
    index_path = root / "processed" / "batches" / "index.yml"
    if not index_path.exists():
        return {
            "batch_count": 0,
            "item_count": 0,
            "succeeded": 0,
            "failed": 0,
            "provenance_backed_count": 0,
        }

    batches = _safe_read_yaml(index_path, findings).get("batches", {})
    if not isinstance(batches, dict):
        return {
            "batch_count": 0,
            "item_count": 0,
            "succeeded": 0,
            "failed": 0,
            "provenance_backed_count": 0,
        }

    item_count = 0
    succeeded = 0
    failed = 0
    provenance_backed_count = 0
    for batch_id, batch in batches.items():
        if not isinstance(batch, dict):
            continue
        item_count += int(batch.get("item_count") or 0)
        succeeded += int(batch.get("succeeded") or 0)
        failed += int(batch.get("failed") or 0)
        if int(batch.get("failed") or 0) > 0:
            findings.append(
                EvaluationFinding(
                    "warning",
                    "batch_run_has_failed_items",
                    "Batch run is traceable but contains failed characterization items.",
                    path=str(index_path),
                    ref=str(batch_id),
                )
            )
        record_ref = batch.get("record_ref")
        if not record_ref:
            continue
        record_path = _project_path(root, str(record_ref))
        if not record_path.exists():
            continue
        record = _safe_read_yaml(record_path, findings)
        if record.get("provenance_refs"):
            provenance_backed_count += 1
        else:
            findings.append(
                EvaluationFinding(
                    "warning",
                    "batch_provenance_refs_missing",
                    "Batch run record is missing provenance_refs.",
                    path=str(record_path),
                    ref=str(batch_id),
                )
            )

    return {
        "batch_count": len(batches),
        "item_count": item_count,
        "succeeded": succeeded,
        "failed": failed,
        "provenance_backed_count": provenance_backed_count,
    }


def _check_material_assignments(root: Path, findings: list[EvaluationFinding]) -> dict[str, Any]:
    assigned_result_count = 0
    assigned_feature_count = 0
    traceable_feature_count = 0
    missing_source_count = 0
    for path in sorted((root / "processed").glob("**/*.yml")):
        if "batches" in path.parts:
            continue
        metadata = _safe_read_yaml(path, findings)
        peak_analysis = metadata.get("peak_analysis")
        if not isinstance(peak_analysis, dict):
            continue
        assigned_features = peak_analysis.get("assigned_features") or []
        if not assigned_features:
            continue
        assigned_result_count += 1
        result_source_missing = not str(peak_analysis.get("assignment_source") or "").strip()
        result_has_missing_source = result_source_missing
        if result_source_missing:
            missing_source_count += 1
        for feature in assigned_features:
            assigned_feature_count += 1
            if isinstance(feature, dict) and str(feature.get("assignment_source") or "").strip():
                traceable_feature_count += 1
            else:
                result_has_missing_source = True
                missing_source_count += 1
        if result_has_missing_source:
            findings.append(
                EvaluationFinding(
                    "error",
                    "material_assignment_traceability_missing",
                    "Material assignments must preserve assignment_source at result and feature level.",
                    path=str(path),
                )
            )

    return {
        "assigned_result_count": assigned_result_count,
        "assigned_feature_count": assigned_feature_count,
        "traceable_feature_count": traceable_feature_count,
        "missing_source_count": missing_source_count,
    }


def _write_evaluation_report(
    root: Path,
    result: dict[str, Any],
    *,
    output_path: Path | None,
    created_at: str,
) -> dict[str, str]:
    evaluation_id = next_id(root, "evaluation", day=created_at[:10])
    target = output_path or root / "evaluation" / f"{evaluation_id}.yml"
    if not target.is_absolute():
        target = root / target
    result["evaluation_id"] = evaluation_id
    result["report_path"] = str(target)
    write_yaml(target, result)
    return {"evaluation_id": evaluation_id, "report_path": str(target)}


def run_project_evaluation(
    root: Path,
    *,
    suite: str = "public_release",
    write_report: bool = True,
    output_path: Path | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    created_at = created_at or _now_iso()
    normalized_suite = suite.replace("-", "_")
    findings: list[EvaluationFinding] = []

    project_summary = _check_project_record(root, findings)
    config_summary = _check_config(root, findings)
    healthcheck = run_healthcheck(root)
    _include_healthcheck_findings(healthcheck, findings)
    figure_summary = _check_figures(root, findings)
    report_summary = _check_reports(root, findings)
    batch_summary = _check_batches(root, findings)
    material_assignment_summary = _check_material_assignments(root, findings)
    literature_summary = _external_literature_summary(root, findings)

    error_count = sum(1 for finding in findings if finding.severity == "error")
    warning_count = sum(1 for finding in findings if finding.severity == "warning")
    info_count = sum(1 for finding in findings if finding.severity == "info")
    result: dict[str, Any] = {
        "schema_version": "0.2",
        "suite": normalized_suite,
        "workspace": str(root),
        "created_at": created_at,
        "evaluation_id": None,
        "report_path": None,
        "status": _evaluation_status(error_count, warning_count),
        "error_count": error_count,
        "warning_count": warning_count,
        "info_count": info_count,
        "project": project_summary,
        "config": config_summary,
        "healthcheck": {
            "status": healthcheck.get("status"),
            "error_count": healthcheck.get("error_count", 0),
            "warning_count": healthcheck.get("warning_count", 0),
        },
        "figures": figure_summary,
        "reports": report_summary,
        "batches": batch_summary,
        "material_assignments": material_assignment_summary,
        "literature": literature_summary,
        "scope": {
            "local_only": True,
            "live_literature_search": False,
            "doi_resolution": False,
            "pdf_download": False,
            "browser_or_zotero_access": False,
            "scientific_truth_scoring": False,
        },
        "findings": [finding.to_dict() for finding in findings],
    }

    if write_report:
        persisted = _write_evaluation_report(root, result, output_path=output_path, created_at=created_at)
        result.update(persisted)
        write_yaml(Path(result["report_path"]), result)
    return result
