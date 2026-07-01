from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from ea.config import doctor_project_config
from ea.provenance import file_sha256
from ea.references import validate_report_citations
from ea.storage.files import read_markdown_record, read_yaml

Severity = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class HealthFinding:
    severity: Severity
    code: str
    message: str
    path: str | None = None
    ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean_ref(ref: str) -> str:
    return ref.split("#", 1)[0]


def _project_path(root: Path, ref: str) -> Path:
    path = Path(_clean_ref(ref))
    return path if path.is_absolute() else root / path


def _registered_reference_ids(root: Path) -> set[str]:
    index_path = root / "literature" / "references" / "index.yml"
    if not index_path.exists():
        return set()
    index = read_yaml(index_path)
    references = index.get("references")
    if not isinstance(references, dict):
        return set()
    return {str(reference_id) for reference_id in references}


def _is_non_file_record_ref(root: Path, ref: str) -> bool:
    clean = _clean_ref(str(ref)).strip()
    if not clean:
        return False
    return clean.startswith("builtin:") or clean in _registered_reference_ids(root)


def _provenance_path(root: Path, ref: str) -> Path:
    path = Path(_clean_ref(ref))
    if path.suffix or len(path.parts) > 1:
        return path if path.is_absolute() else root / path
    return root / "provenance" / f"{ref}.yml"


def _safe_read_yaml(path: Path, findings: list[HealthFinding]) -> dict[str, Any]:
    try:
        return read_yaml(path)
    except Exception as exc:  # pragma: no cover - exact parser exceptions vary
        findings.append(
            HealthFinding(
                "error",
                "unreadable_yaml",
                f"Could not read YAML: {exc}",
                path=str(path),
            )
        )
        return {}


def _result_index(root: Path, findings: list[HealthFinding]) -> dict[str, Path]:
    results: dict[str, Path] = {}
    for path in sorted((root / "processed").glob("**/*.yml")):
        if "batches" in path.parts:
            continue
        data = _safe_read_yaml(path, findings)
        for key in ("result_id", "raman_result_id", "pl_result_id", "xrd_result_id"):
            value = data.get(key)
            if value:
                results[str(value)] = path
        for key, value in data.items():
            if key.endswith("_result_id") and value:
                results[str(value)] = path
    return results


def _raw_index(root: Path, findings: list[HealthFinding]) -> dict[str, Path]:
    raw: dict[str, Path] = {}
    for path in sorted((root / "raw").glob("*/*/metadata.yml")):
        data = _safe_read_yaml(path, findings)
        characterization_id = data.get("characterization_id")
        if characterization_id:
            raw[str(characterization_id)] = path
    return raw


def _check_project_config(root: Path, findings: list[HealthFinding]) -> None:
    doctor = doctor_project_config(root)
    if doctor["status"] == "missing":
        findings.append(
            HealthFinding(
                "warning",
                "missing_project_config",
                "Project config is missing; run `ea init-project` or create `.ea/project_config.yml`.",
                path=doctor["config_path"],
            )
        )
        return
    if doctor["status"] != "pass":
        findings.append(
            HealthFinding(
                "error",
                "project_config_failed",
                "Project config failed public-release portability checks.",
                path=doctor["config_path"],
                ref=",".join(doctor.get("errors", [])),
            )
        )


def _check_raw_files(root: Path, findings: list[HealthFinding]) -> None:
    for metadata_path in sorted((root / "raw").glob("*/*/metadata.yml")):
        metadata = _safe_read_yaml(metadata_path, findings)
        raw_ref = metadata.get("project_raw_path")
        if not raw_ref:
            findings.append(
                HealthFinding(
                    "error",
                    "raw_project_path_missing",
                    "Raw metadata is missing `project_raw_path`.",
                    path=str(metadata_path),
                )
            )
            continue
        raw_path = _project_path(root, str(raw_ref))
        if not raw_path.exists():
            findings.append(
                HealthFinding(
                    "error",
                    "raw_file_missing",
                    "Raw metadata points to a missing raw file.",
                    path=str(metadata_path),
                    ref=str(raw_ref),
                )
            )
            continue
        expected_hash = metadata.get("sha256")
        if expected_hash and file_sha256(raw_path) != expected_hash:
            findings.append(
                HealthFinding(
                    "error",
                    "raw_hash_mismatch",
                    "Raw file SHA256 no longer matches metadata.",
                    path=str(metadata_path),
                    ref=str(raw_ref),
                )
            )


def _check_review_ref(root: Path, review_ref: str, findings: list[HealthFinding], owner: Path) -> None:
    review_path = root / "reviews" / f"{review_ref}.yml"
    if not review_path.exists():
        findings.append(
            HealthFinding(
                "error",
                "review_ref_missing",
                "Referenced review record is missing.",
                path=str(owner),
                ref=review_ref,
            )
        )
        return
    review = _safe_read_yaml(review_path, findings)
    if review.get("review_status") != "user_confirmed":
        findings.append(
            HealthFinding(
                "error",
                "review_ref_not_confirmed",
                "Referenced review record is not user_confirmed.",
                path=str(owner),
                ref=review_ref,
            )
        )


def _check_record_refs(
    root: Path,
    *,
    owner: Path,
    refs: list[str],
    code: str,
    message: str,
    findings: list[HealthFinding],
) -> None:
    for ref in refs:
        path = _project_path(root, ref)
        if not path.exists() and not _is_non_file_record_ref(root, ref):
            findings.append(HealthFinding("error", code, message, path=str(owner), ref=ref))


def _check_file_refs(
    root: Path,
    *,
    owner: Path,
    refs: list[str],
    severity: Severity,
    code: str,
    message: str,
    findings: list[HealthFinding],
) -> None:
    for ref in refs:
        path = _project_path(root, ref)
        if not path.exists():
            findings.append(HealthFinding(severity, code, message, path=str(owner), ref=ref))


def _check_provenance(root: Path, findings: list[HealthFinding]) -> None:
    for path in sorted((root / "provenance").glob("*.yml")):
        provenance = _safe_read_yaml(path, findings)
        inputs = provenance.get("inputs") or {}
        outputs = provenance.get("outputs") or {}
        _check_record_refs(
            root,
            owner=path,
            refs=list(inputs.get("records") or []),
            code="provenance_input_record_missing",
            message="Provenance input record is missing.",
            findings=findings,
        )
        _check_record_refs(
            root,
            owner=path,
            refs=list(outputs.get("records") or []),
            code="provenance_output_record_missing",
            message="Provenance output record is missing.",
            findings=findings,
        )
        _check_file_refs(
            root,
            owner=path,
            refs=list(inputs.get("files") or []),
            severity="warning",
            code="provenance_input_file_missing",
            message="Provenance input file is missing; it may have been an external source.",
            findings=findings,
        )
        _check_file_refs(
            root,
            owner=path,
            refs=list(outputs.get("files") or []),
            severity="error",
            code="provenance_output_file_missing",
            message="Provenance output file is missing.",
            findings=findings,
        )
        workflow = str(provenance.get("workflow", ""))
        for output_file in outputs.get("files") or []:
            output_ref = _clean_ref(str(output_file))
            if output_ref.startswith("raw/") and workflow != "raw_file_import":
                findings.append(
                    HealthFinding(
                        "error",
                        "generated_output_under_raw",
                        "Generated workflow output is under raw/.",
                        path=str(path),
                        ref=output_ref,
                    )
                )
        for review_ref in provenance.get("review_refs") or []:
            _check_review_ref(root, str(review_ref), findings, path)


def _check_figures_and_reports(root: Path, findings: list[HealthFinding]) -> None:
    result_index = _result_index(root, findings)
    raw_index = _raw_index(root, findings)
    figures_index_path = root / "figures" / "index.yml"
    reports_index_path = root / "reports" / "index.yml"
    figures = _safe_read_yaml(figures_index_path, findings).get("figures", {}) if figures_index_path.exists() else {}
    reports = _safe_read_yaml(reports_index_path, findings).get("reports", {}) if reports_index_path.exists() else {}

    for figure_id, figure in figures.items():
        figure_path = root / str(figure.get("path", ""))
        if not figure_path.exists():
            findings.append(
                HealthFinding(
                    "error",
                    "figure_file_missing",
                    "Figure index points to a missing figure file.",
                    path=str(figures_index_path),
                    ref=str(figure_id),
                )
            )
        result_id = figure.get("result_id")
        if result_id and str(result_id) not in result_index:
            findings.append(
                HealthFinding(
                    "error",
                    "figure_result_missing",
                    "Figure result_id does not match any processed result metadata.",
                    path=str(figures_index_path),
                    ref=str(result_id),
                )
            )
        for raw_id in figure.get("raw_data_ids") or []:
            if str(raw_id) not in raw_index:
                findings.append(
                    HealthFinding(
                        "warning",
                        "figure_raw_ref_missing",
                        "Figure raw_data_id does not match imported raw metadata.",
                        path=str(figures_index_path),
                        ref=str(raw_id),
                    )
                )
        report_id = figure.get("report_id")
        if report_id and str(report_id) not in reports:
            findings.append(
                HealthFinding(
                    "error",
                    "figure_report_missing",
                    "Figure report_id does not match reports/index.yml.",
                    path=str(figures_index_path),
                    ref=str(report_id),
                )
            )

    for report_id, report in reports.items():
        report_ref = str(report.get("path", ""))
        report_path = root / report_ref
        if not report_path.exists():
            findings.append(
                HealthFinding(
                    "error",
                    "report_file_missing",
                    "Report index points to a missing report file.",
                    path=str(reports_index_path),
                    ref=str(report_id),
                )
            )
            continue
        frontmatter, _ = read_markdown_record(report_path)
        if frontmatter.get("report_id") != report_id:
            findings.append(
                HealthFinding(
                    "error",
                    "report_id_mismatch",
                    "Report frontmatter report_id does not match reports/index.yml.",
                    path=str(report_path),
                    ref=str(report_id),
                )
            )
        for result_id in report.get("result_ids") or []:
            if str(result_id) not in result_index:
                findings.append(
                    HealthFinding(
                        "error",
                        "report_result_missing",
                        "Report result_id does not match any processed result metadata.",
                        path=str(report_path),
                        ref=str(result_id),
                    )
                )
        for figure_id in report.get("figure_ids") or []:
            figure = figures.get(str(figure_id))
            if not figure:
                findings.append(
                    HealthFinding(
                        "error",
                        "report_figure_missing",
                        "Report figure_id does not match figures/index.yml.",
                        path=str(report_path),
                        ref=str(figure_id),
                    )
                )
            elif figure.get("report_id") != report_id:
                findings.append(
                    HealthFinding(
                        "error",
                        "report_figure_backlink_mismatch",
                        "Figure record does not point back to the report.",
                        path=str(report_path),
                        ref=str(figure_id),
                    )
                )

        report_reference_ids = list(report.get("reference_ids") or [])
        frontmatter_reference_ids = list(frontmatter.get("reference_ids") or [])
        for reference_id in sorted(set(str(item) for item in report_reference_ids + frontmatter_reference_ids)):
            _check_reference_id(root, reference_id, findings, report_path)
        if report_reference_ids and frontmatter_reference_ids and report_reference_ids != frontmatter_reference_ids:
            findings.append(
                HealthFinding(
                    "error",
                    "report_reference_index_mismatch",
                    "Report reference_ids do not match reports/index.yml.",
                    path=str(report_path),
                    ref=str(report_id),
                )
            )
        citation_result = validate_report_citations(report_path)
        if not citation_result["ok"]:
            findings.append(
                HealthFinding(
                    "error",
                    "report_reference_numbering_invalid",
                    "Report inline numeric citations do not match its References entries.",
                    path=str(report_path),
                    ref=str(citation_result),
                )
            )


def _check_reference_id(root: Path, reference_id: str, findings: list[HealthFinding], owner: Path) -> None:
    index_path = root / "literature" / "references" / "index.yml"
    index = _safe_read_yaml(index_path, findings).get("references", {}) if index_path.exists() else {}
    record = index.get(reference_id)
    if not record:
        findings.append(
            HealthFinding(
                "error",
                "reference_id_missing",
                "Report references an unknown reference_id.",
                path=str(owner),
                ref=reference_id,
            )
        )
        return
    record_path = _project_path(root, str(record.get("path") or f"literature/references/{reference_id}.yml"))
    if not record_path.exists():
        findings.append(
            HealthFinding(
                "error",
                "reference_record_missing",
                "Reference index points to a missing reference record.",
                path=str(index_path),
                ref=reference_id,
            )
        )
        return
    data = _safe_read_yaml(record_path, findings)
    if data.get("reference_id") != reference_id:
        findings.append(
            HealthFinding(
                "error",
                "reference_id_mismatch",
                "Reference record reference_id does not match literature/references/index.yml.",
                path=str(record_path),
                ref=reference_id,
            )
        )


def _check_references(root: Path, findings: list[HealthFinding]) -> None:
    index_path = root / "literature" / "references" / "index.yml"
    if not index_path.exists():
        return
    references = _safe_read_yaml(index_path, findings).get("references", {})
    for reference_id, record in references.items():
        record_path = _project_path(root, str(record.get("path") or f"literature/references/{reference_id}.yml"))
        if not record_path.exists():
            findings.append(
                HealthFinding(
                    "error",
                    "reference_record_missing",
                    "Reference index points to a missing reference record.",
                    path=str(index_path),
                    ref=str(reference_id),
                )
            )
            continue
        data = _safe_read_yaml(record_path, findings)
        if data.get("reference_id") != reference_id:
            findings.append(
                HealthFinding(
                    "error",
                    "reference_id_mismatch",
                    "Reference record reference_id does not match literature/references/index.yml.",
                    path=str(record_path),
                    ref=str(reference_id),
                )
            )
        if not str(data.get("citation") or "").strip():
            findings.append(
                HealthFinding(
                    "error",
                    "reference_citation_missing",
                    "Reference record is missing citation text.",
                    path=str(record_path),
                    ref=str(reference_id),
                )
            )
        local_path = data.get("local_path")
        if local_path and not _project_path(root, str(local_path)).exists():
            findings.append(
                HealthFinding(
                    "warning",
                    "reference_local_file_missing",
                    "Reference local_path does not exist in the project workspace.",
                    path=str(record_path),
                    ref=str(local_path),
                )
            )


def _check_candidate_record(
    root: Path,
    *,
    candidate_id: str,
    candidate_ref: str,
    index_record: dict[str, Any],
    findings: list[HealthFinding],
) -> dict[str, Any]:
    candidate_path = _project_path(root, candidate_ref)
    if not candidate_path.exists():
        findings.append(
            HealthFinding(
                "error",
                "memory_candidate_record_missing",
                "Memory candidate index points to a missing candidate record.",
                path=str(root / "memory" / "candidates" / "index.yml"),
                ref=candidate_id,
            )
        )
        return {}
    frontmatter, body = read_markdown_record(candidate_path)
    if frontmatter.get("memory_candidate_id") != candidate_id:
        findings.append(
            HealthFinding(
                "error",
                "memory_candidate_id_mismatch",
                "Memory candidate frontmatter ID does not match memory/candidates/index.yml.",
                path=str(candidate_path),
                ref=candidate_id,
            )
        )
    if index_record.get("status") and frontmatter.get("status") != index_record.get("status"):
        findings.append(
            HealthFinding(
                "error",
                "memory_candidate_status_mismatch",
                "Memory candidate status does not match memory/candidates/index.yml.",
                path=str(candidate_path),
                ref=candidate_id,
            )
        )
    if frontmatter.get("status") == "committed" and not frontmatter.get("committed_memory_id"):
        findings.append(
            HealthFinding(
                "error",
                "memory_candidate_committed_id_missing",
                "Committed memory candidate is missing committed_memory_id.",
                path=str(candidate_path),
                ref=candidate_id,
            )
        )
    if not body.strip():
        findings.append(
            HealthFinding(
                "warning",
                "memory_candidate_body_empty",
                "Memory candidate body is empty.",
                path=str(candidate_path),
                ref=candidate_id,
            )
        )
    for review_ref in frontmatter.get("review_refs") or []:
        _check_review_ref(root, str(review_ref), findings, candidate_path)
    for source_ref in frontmatter.get("source_refs") or []:
        if not _project_path(root, str(source_ref)).exists() and not _is_non_file_record_ref(root, str(source_ref)):
            findings.append(
                HealthFinding(
                    "warning",
                    "memory_candidate_source_ref_missing",
                    "Memory candidate source_ref is missing.",
                    path=str(candidate_path),
                    ref=str(source_ref),
                )
            )
    for provenance_ref in frontmatter.get("provenance_refs") or []:
        if not _provenance_path(root, str(provenance_ref)).exists():
            findings.append(
                HealthFinding(
                    "warning",
                    "memory_candidate_provenance_ref_missing",
                    "Memory candidate provenance_ref is missing.",
                    path=str(candidate_path),
                    ref=str(provenance_ref),
                )
            )
    return frontmatter


def _check_memory(root: Path, findings: list[HealthFinding]) -> None:
    candidates_index_path = root / "memory" / "candidates" / "index.yml"
    memory_index_path = root / "memory" / "index.yml"
    candidates: dict[str, Any] = {}
    if candidates_index_path.exists():
        candidates = _safe_read_yaml(candidates_index_path, findings).get("candidates", {})
        for candidate_id, candidate in candidates.items():
            _check_candidate_record(
                root,
                candidate_id=str(candidate_id),
                candidate_ref=str(candidate.get("path") or f"memory/candidates/{candidate_id}.md"),
                index_record=candidate,
                findings=findings,
            )
    if not memory_index_path.exists():
        return
    memories = _safe_read_yaml(memory_index_path, findings).get("memories", {})
    for memory_id, memory in memories.items():
        if memory.get("memory_id") and memory.get("memory_id") != memory_id:
            findings.append(
                HealthFinding(
                    "error",
                    "memory_id_mismatch",
                    "Memory index key does not match memory_id.",
                    path=str(memory_index_path),
                    ref=str(memory_id),
                )
            )
        target_ref = str(memory.get("target_ref") or "")
        target_path = _project_path(root, target_ref) if target_ref else root / "memory" / "missing-target"
        if not target_ref or not target_path.exists():
            findings.append(
                HealthFinding(
                    "error",
                    "memory_target_missing",
                    "Committed memory target file is missing.",
                    path=str(memory_index_path),
                    ref=str(memory_id),
                )
            )
        elif f"Memory {memory_id}" not in target_path.read_text(encoding="utf-8"):
            findings.append(
                HealthFinding(
                    "error",
                    "memory_target_block_missing",
                    "Committed memory target file does not contain the indexed memory block.",
                    path=str(target_path),
                    ref=str(memory_id),
                )
            )
        candidate_ref = str(memory.get("candidate_ref") or "")
        candidate_path = _project_path(root, candidate_ref) if candidate_ref else root / "memory" / "candidates" / "missing.md"
        if not candidate_ref or not candidate_path.exists():
            findings.append(
                HealthFinding(
                    "error",
                    "memory_candidate_ref_missing",
                    "Committed memory candidate_ref is missing.",
                    path=str(memory_index_path),
                    ref=str(memory_id),
                )
            )
        else:
            candidate_frontmatter, _ = read_markdown_record(candidate_path)
            if candidate_frontmatter.get("committed_memory_id") != memory_id:
                findings.append(
                    HealthFinding(
                        "error",
                        "memory_candidate_commit_mismatch",
                        "Memory candidate does not point back to the committed memory ID.",
                        path=str(candidate_path),
                        ref=str(memory_id),
                    )
                )
        for source_ref in memory.get("source_refs") or []:
            if not _project_path(root, str(source_ref)).exists() and not _is_non_file_record_ref(root, str(source_ref)):
                findings.append(
                    HealthFinding(
                        "error",
                        "memory_source_ref_missing",
                        "Committed memory source_ref is missing.",
                        path=str(memory_index_path),
                        ref=str(source_ref),
                    )
                )
        for provenance_ref in memory.get("provenance_refs") or []:
            if not _provenance_path(root, str(provenance_ref)).exists():
                findings.append(
                    HealthFinding(
                        "error",
                        "memory_provenance_ref_missing",
                        "Committed memory provenance_ref is missing.",
                        path=str(memory_index_path),
                        ref=str(provenance_ref),
                    )
                )
        for review_ref in memory.get("review_refs") or []:
            _check_review_ref(root, str(review_ref), findings, memory_index_path)


def _check_batch_record(
    root: Path,
    *,
    batch_id: str,
    index_record: dict[str, Any],
    record_path: Path,
    record: dict[str, Any],
    findings: list[HealthFinding],
) -> None:
    if record.get("batch_id") != batch_id:
        findings.append(
            HealthFinding(
                "error",
                "batch_record_id_mismatch",
                "Batch run record batch_id does not match processed/batches/index.yml.",
                path=str(record_path),
                ref=batch_id,
            )
        )

    for field in ["status", "item_count", "succeeded", "failed"]:
        if field in index_record and record.get(field) != index_record.get(field):
            findings.append(
                HealthFinding(
                    "error",
                    "batch_index_record_mismatch",
                    "Batch index summary does not match its batch run record.",
                    path=str(record_path),
                    ref=f"{batch_id}:{field}",
                )
            )

    manifest_ref = record.get("manifest_ref")
    if manifest_ref and not _project_path(root, str(manifest_ref)).exists():
        findings.append(
            HealthFinding(
                "warning",
                "batch_manifest_ref_missing",
                "Batch run manifest_ref is missing from the project workspace.",
                path=str(record_path),
                ref=str(manifest_ref),
            )
        )

    items = record.get("items")
    if not isinstance(items, list):
        findings.append(
            HealthFinding(
                "error",
                "batch_items_invalid",
                "Batch run record items must be a list.",
                path=str(record_path),
                ref=batch_id,
            )
        )
        return

    expected_count = record.get("item_count")
    if isinstance(expected_count, int) and len(items) != expected_count:
        findings.append(
            HealthFinding(
                "error",
                "batch_item_count_mismatch",
                "Batch run item_count does not match the number of item records.",
                path=str(record_path),
                ref=batch_id,
            )
        )

    succeeded = sum(1 for item in items if item.get("status") == "success")
    failed = sum(1 for item in items if item.get("status") == "failed")
    if record.get("succeeded") != succeeded or record.get("failed") != failed:
        findings.append(
            HealthFinding(
                "error",
                "batch_status_count_mismatch",
                "Batch run succeeded/failed counts do not match item statuses.",
                path=str(record_path),
                ref=batch_id,
            )
        )

    for item in items:
        item_id = str(item.get("item_id") or "unknown-item")
        for metadata_ref in [item.get("metadata_ref")]:
            if metadata_ref and not _project_path(root, str(metadata_ref)).exists():
                findings.append(
                    HealthFinding(
                        "error",
                        "batch_item_metadata_missing",
                        "Batch item metadata_ref is missing.",
                        path=str(record_path),
                        ref=f"{item_id}:{metadata_ref}",
                    )
                )
        for review_ref in item.get("review_refs") or []:
            _check_review_ref(root, str(review_ref), findings, record_path)

        if item.get("status") != "success":
            continue
        result_ref = item.get("result_metadata_ref")
        if not result_ref:
            findings.append(
                HealthFinding(
                    "error",
                    "batch_item_result_ref_missing",
                    "Successful batch item is missing result_metadata_ref.",
                    path=str(record_path),
                    ref=item_id,
                )
            )
        elif not _project_path(root, str(result_ref)).exists():
            findings.append(
                HealthFinding(
                    "error",
                    "batch_item_result_missing",
                    "Successful batch item result_metadata_ref is missing.",
                    path=str(record_path),
                    ref=f"{item_id}:{result_ref}",
                )
            )

        report_ref = item.get("report_ref")
        if report_ref and not _project_path(root, str(report_ref)).exists():
            findings.append(
                HealthFinding(
                    "error",
                    "batch_item_report_missing",
                    "Batch item report_ref is missing.",
                    path=str(record_path),
                    ref=f"{item_id}:{report_ref}",
                )
            )

    provenance_refs = list(record.get("provenance_refs") or [])
    if not provenance_refs:
        findings.append(
            HealthFinding(
                "error",
                "batch_provenance_refs_missing",
                "Batch run record is missing provenance_refs.",
                path=str(record_path),
                ref=batch_id,
            )
        )
    for provenance_ref in provenance_refs:
        provenance_path = _provenance_path(root, str(provenance_ref))
        if not provenance_path.exists():
            findings.append(
                HealthFinding(
                    "error",
                    "batch_provenance_ref_missing",
                    "Batch run provenance_ref is missing.",
                    path=str(record_path),
                    ref=str(provenance_ref),
                )
            )
            continue
        provenance = _safe_read_yaml(provenance_path, findings)
        if provenance.get("workflow") != "batch_characterization":
            findings.append(
                HealthFinding(
                    "warning",
                    "batch_provenance_workflow_unexpected",
                    "Batch run provenance_ref does not use the batch_characterization workflow.",
                    path=str(record_path),
                    ref=str(provenance_ref),
                )
            )


def _check_batches(root: Path, findings: list[HealthFinding]) -> None:
    index_path = root / "processed" / "batches" / "index.yml"
    if not index_path.exists():
        return
    batches = _safe_read_yaml(index_path, findings).get("batches", {})
    if not isinstance(batches, dict):
        findings.append(
            HealthFinding(
                "error",
                "batch_index_invalid",
                "processed/batches/index.yml field `batches` must be a mapping.",
                path=str(index_path),
            )
        )
        return

    for batch_id, index_record in batches.items():
        batch_id = str(batch_id)
        if not isinstance(index_record, dict):
            findings.append(
                HealthFinding(
                    "error",
                    "batch_index_record_invalid",
                    "Batch index entry must be a mapping.",
                    path=str(index_path),
                    ref=batch_id,
                )
            )
            continue
        if index_record.get("batch_id") and str(index_record.get("batch_id")) != batch_id:
            findings.append(
                HealthFinding(
                    "error",
                    "batch_index_id_mismatch",
                    "Batch index key does not match its batch_id field.",
                    path=str(index_path),
                    ref=batch_id,
                )
            )

        record_ref = str(index_record.get("record_ref") or "")
        summary_ref = str(index_record.get("summary_ref") or "")
        if not record_ref:
            findings.append(
                HealthFinding(
                    "error",
                    "batch_record_ref_missing",
                    "Batch index entry is missing record_ref.",
                    path=str(index_path),
                    ref=batch_id,
                )
            )
            continue
        record_path = _project_path(root, record_ref)
        if not record_path.exists():
            findings.append(
                HealthFinding(
                    "error",
                    "batch_record_missing",
                    "Batch index points to a missing batch run record.",
                    path=str(index_path),
                    ref=record_ref,
                )
            )
            continue

        if not summary_ref:
            findings.append(
                HealthFinding(
                    "error",
                    "batch_summary_ref_missing",
                    "Batch index entry is missing summary_ref.",
                    path=str(index_path),
                    ref=batch_id,
                )
            )
        else:
            summary_path = _project_path(root, summary_ref)
            if not summary_path.exists():
                findings.append(
                    HealthFinding(
                        "error",
                        "batch_summary_missing",
                        "Batch index points to a missing batch summary.",
                        path=str(index_path),
                        ref=summary_ref,
                    )
                )
            elif batch_id not in summary_path.read_text(encoding="utf-8"):
                findings.append(
                    HealthFinding(
                        "warning",
                        "batch_summary_id_missing",
                        "Batch summary does not mention its batch_id.",
                        path=str(summary_path),
                        ref=batch_id,
                    )
                )

        record = _safe_read_yaml(record_path, findings)
        _check_batch_record(
            root,
            batch_id=batch_id,
            index_record=index_record,
            record_path=record_path,
            record=record,
            findings=findings,
        )


def _check_material_assignments(root: Path, findings: list[HealthFinding]) -> None:
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
        if not str(peak_analysis.get("assignment_source") or "").strip():
            findings.append(
                HealthFinding(
                    "error",
                    "material_assignment_source_missing",
                    "Result metadata has assigned material features but no peak_analysis.assignment_source.",
                    path=str(path),
                )
            )
        if not str(peak_analysis.get("material_id") or "").strip():
            findings.append(
                HealthFinding(
                    "warning",
                    "material_assignment_id_missing",
                    "Result metadata has assigned material features but no peak_analysis.material_id.",
                    path=str(path),
                )
            )
        for index, feature in enumerate(assigned_features, start=1):
            if not isinstance(feature, dict):
                findings.append(
                    HealthFinding(
                        "error",
                        "material_assignment_feature_invalid",
                        "Assigned material feature must be a mapping.",
                        path=str(path),
                        ref=f"feature-{index:03d}",
                    )
                )
                continue
            if not str(feature.get("assignment_source") or "").strip():
                findings.append(
                    HealthFinding(
                        "error",
                        "material_assignment_feature_source_missing",
                        "Assigned material feature is missing assignment_source.",
                        path=str(path),
                        ref=str(feature.get("feature") or f"feature-{index:03d}"),
                    )
                )
            if not str(feature.get("confidence") or "").strip():
                findings.append(
                    HealthFinding(
                        "warning",
                        "material_assignment_confidence_missing",
                        "Assigned material feature is missing confidence.",
                        path=str(path),
                        ref=str(feature.get("feature") or f"feature-{index:03d}"),
                    )
                )


def run_healthcheck(root: Path) -> dict[str, Any]:
    root = root.resolve()
    findings: list[HealthFinding] = []
    if not root.exists():
        findings.append(
            HealthFinding("error", "workspace_missing", "Workspace path does not exist.", path=str(root))
        )
    else:
        _check_project_config(root, findings)
        _check_raw_files(root, findings)
        _check_provenance(root, findings)
        _check_figures_and_reports(root, findings)
        _check_references(root, findings)
        _check_memory(root, findings)
        _check_batches(root, findings)
        _check_material_assignments(root, findings)
    error_count = sum(1 for finding in findings if finding.severity == "error")
    warning_count = sum(1 for finding in findings if finding.severity == "warning")
    return {
        "schema_version": "0.2",
        "workspace": str(root),
        "status": "pass" if error_count == 0 else "fail",
        "error_count": error_count,
        "warning_count": warning_count,
        "findings": [finding.to_dict() for finding in findings],
    }
