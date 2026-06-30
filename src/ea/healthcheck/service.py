from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from ea.config import doctor_project_config
from ea.provenance import file_sha256
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
        data = _safe_read_yaml(path, findings)
        for key in ("result_id", "raman_result_id"):
            value = data.get(key)
            if value:
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
        if not path.exists():
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
