from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ea.ftir import FTIRProcessingRequest, default_ftir_processing_parameters, process_ftir_result
from ea.pl import PLProcessingRequest, default_pl_processing_parameters, process_pl_result
from ea.provenance import write_provenance_entry
from ea.raman import RamanProcessingRequest, default_processing_parameters, process_raman_result
from ea.reports import generate_ftir_report, generate_pl_report, generate_raman_report, generate_xrd_report
from ea.review import require_confirmed_review
from ea.schema.models import EARecord
from ea.storage.files import read_markdown_record, read_yaml, write_yaml
from ea.storage.ids import next_id
from ea.xrd import XRDProcessingRequest, default_xrd_processing_parameters, process_xrd_result


SUPPORTED_METHODS = {"raman", "pl", "xrd", "ftir"}
METHOD_UNITS = {
    "raman": {"cm^-1", "unknown"},
    "pl": {"eV", "nm", "unknown"},
    "xrd": {"2theta_deg", "unknown"},
    "ftir": {"cm^-1", "unknown"},
}


class BatchManifestError(RuntimeError):
    """Raised when a batch characterization manifest is invalid."""


def _project_id_from_root(root: Path) -> str:
    project_path = root / "EA_PROJECT.md"
    if not project_path.exists():
        return "unknown-project"
    frontmatter, _ = read_markdown_record(project_path)
    return str(frontmatter.get("project_id", "unknown-project"))


def _project_path(root: Path, path_value: str | Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else root / path


def _path_ref(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _load_manifest(root: Path, manifest_path: Path) -> tuple[Path, dict[str, Any], list[dict[str, Any]]]:
    path = _project_path(root, manifest_path)
    if not path.exists():
        raise BatchManifestError(f"Batch manifest does not exist: {manifest_path}")
    manifest = read_yaml(path)
    batch_section = manifest.get("batch", manifest)
    items = batch_section.get("items", manifest.get("items", []))
    if not isinstance(items, list):
        raise BatchManifestError("Batch manifest field `items` must be a list.")
    return path, batch_section, items


def _manifest_defaults(batch_section: dict[str, Any]) -> dict[str, Any]:
    return {
        "project_id": batch_section.get("project_id"),
        "create_reports": bool(batch_section.get("create_reports", True)),
        "continue_on_error": bool(batch_section.get("continue_on_error", True)),
        "reference_ids": list(batch_section.get("reference_ids", [])),
    }


def _default_parameters(method: str) -> dict[str, Any]:
    if method == "raman":
        return default_processing_parameters()
    if method == "pl":
        return default_pl_processing_parameters()
    if method == "xrd":
        return default_xrd_processing_parameters()
    if method == "ftir":
        return default_ftir_processing_parameters()
    raise BatchManifestError(f"Unsupported batch method: {method}")


def _processing_parameters(root: Path, method: str, item: dict[str, Any]) -> dict[str, Any]:
    parameters = _default_parameters(method)
    parameters_path = item.get("parameters_file") or item.get("processing_parameters_file")
    if parameters_path:
        parameters.update(read_yaml(_project_path(root, parameters_path)))
    parameters.update(item.get("processing_parameters") or {})
    return parameters


def _validate_item(root: Path, item: dict[str, Any], index: int) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    item_id = str(item.get("item_id") or f"item-{index:03d}")
    method = str(item.get("method", "")).lower()
    required = ["method", "metadata", "x_column", "y_column", "x_unit", "column_review_ref", "parameter_review_ref"]
    for field in required:
        if field not in item or item.get(field) in [None, ""]:
            errors.append({"item_id": item_id, "field": field, "message": "Required field is missing."})
    if method and method not in SUPPORTED_METHODS:
        errors.append({"item_id": item_id, "field": "method", "message": f"Unsupported method: {method}"})
    x_unit = item.get("x_unit")
    if method in METHOD_UNITS and x_unit not in METHOD_UNITS[method]:
        errors.append({"item_id": item_id, "field": "x_unit", "message": f"Unsupported x_unit for {method}: {x_unit}"})
    if method == "ftir" and item.get("signal_mode") not in {"absorbance", "transmittance"}:
        errors.append({"item_id": item_id, "field": "signal_mode", "message": "FTIR signal_mode must be absorbance or transmittance."})
    metadata = item.get("metadata")
    if metadata and not _project_path(root, metadata).exists():
        errors.append({"item_id": item_id, "field": "metadata", "message": f"Metadata file does not exist: {metadata}"})
    parameters_path = item.get("parameters_file") or item.get("processing_parameters_file")
    if parameters_path and not _project_path(root, parameters_path).exists():
        errors.append({"item_id": item_id, "field": "parameters_file", "message": f"Parameters file does not exist: {parameters_path}"})
    for review_field in ["column_review_ref", "parameter_review_ref"]:
        review_ref = item.get(review_field)
        if not review_ref:
            continue
        try:
            require_confirmed_review(root, str(review_ref))
        except Exception as exc:  # noqa: BLE001 - validation must report all manifest problems.
            errors.append({"item_id": item_id, "field": review_field, "message": str(exc)})
    return errors


def validate_batch_manifest(root: Path, manifest_path: Path) -> dict[str, Any]:
    path, batch_section, items = _load_manifest(root, manifest_path)
    item_summaries = []
    errors: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        item_id = str(item.get("item_id") or f"item-{index:03d}")
        method = str(item.get("method", "")).lower()
        item_errors = _validate_item(root, item, index)
        errors.extend(item_errors)
        item_summaries.append(
            {
                "item_id": item_id,
                "method": method or None,
                "metadata": item.get("metadata"),
                "status": "valid" if not item_errors else "invalid",
                "error_count": len(item_errors),
            }
        )
    if not items:
        errors.append({"item_id": None, "field": "items", "message": "Batch manifest has no items."})
    return {
        "schema_version": "0.2",
        "manifest_ref": _path_ref(root, path),
        "status": "pass" if not errors else "fail",
        "item_count": len(items),
        "items": item_summaries,
        "errors": errors,
    }


def _run_method(root: Path, method: str, project_id: str, item: dict[str, Any], created_at: str | None) -> Path:
    metadata_path = _project_path(root, item["metadata"])
    sample_refs = list(item.get("sample_refs", item.get("sample_ref", [])) or [])
    parameters = _processing_parameters(root, method, item)
    common = {
        "x_column": str(item["x_column"]),
        "y_column": str(item["y_column"]),
        "x_unit": str(item["x_unit"]),
        "processing_parameters": parameters,
        "column_review_ref": str(item["column_review_ref"]),
        "parameter_review_ref": str(item["parameter_review_ref"]),
    }
    if method == "raman":
        return process_raman_result(
            root,
            characterization_metadata_path=metadata_path,
            project_id=project_id,
            sample_refs=sample_refs,
            request=RamanProcessingRequest(**common),
            created_at=created_at,
        )
    if method == "pl":
        return process_pl_result(
            root,
            characterization_metadata_path=metadata_path,
            project_id=project_id,
            sample_refs=sample_refs,
            request=PLProcessingRequest(**common),
            created_at=created_at,
        )
    if method == "xrd":
        return process_xrd_result(
            root,
            characterization_metadata_path=metadata_path,
            project_id=project_id,
            sample_refs=sample_refs,
            request=XRDProcessingRequest(**common),
            created_at=created_at,
        )
    if method == "ftir":
        return process_ftir_result(
            root,
            characterization_metadata_path=metadata_path,
            project_id=project_id,
            sample_refs=sample_refs,
            request=FTIRProcessingRequest(
                **common,
                signal_mode=str(item.get("signal_mode") or "absorbance"),
            ),
            created_at=created_at,
        )
    raise BatchManifestError(f"Unsupported batch method: {method}")


def _report_generator(method: str) -> Callable[..., Path]:
    if method == "raman":
        return generate_raman_report
    if method == "pl":
        return generate_pl_report
    if method == "xrd":
        return generate_xrd_report
    if method == "ftir":
        return generate_ftir_report
    raise BatchManifestError(f"Unsupported report method: {method}")


def _generate_report(
    root: Path,
    *,
    method: str,
    project_id: str,
    result_metadata_path: Path,
    item: dict[str, Any],
    default_reference_ids: list[str],
    created_at: str | None,
) -> Path:
    generator = _report_generator(method)
    sample_refs = list(item.get("sample_refs", item.get("sample_ref", [])) or [])
    experiment_refs = list(item.get("experiment_refs", item.get("experiment_ref", [])) or [])
    reference_ids = list(item.get("reference_ids", default_reference_ids) or [])
    metadata_arg = {
        "raman": "raman_metadata_path",
        "pl": "pl_metadata_path",
        "xrd": "xrd_metadata_path",
        "ftir": "ftir_metadata_path",
    }[method]
    return generator(
        root,
        project_id=project_id,
        **{metadata_arg: result_metadata_path},
        related_experiments=experiment_refs,
        related_samples=sample_refs,
        reference_ids=reference_ids,
        created_at=created_at,
    )


def _write_summary(path: Path, record: dict[str, Any]) -> Path:
    lines = [
        f"# Batch Characterization Summary: {record['batch_id']}",
        "",
        f"- status: `{record['status']}`",
        f"- project_id: `{record['project_id']}`",
        f"- manifest: `{record['manifest_ref']}`",
        f"- total_items: `{record['item_count']}`",
        f"- succeeded: `{record['succeeded']}`",
        f"- failed: `{record['failed']}`",
        "",
        "| item_id | method | status | result metadata | report | error |",
        "|---|---|---|---|---|---|",
    ]
    for item in record["items"]:
        lines.append(
            "| {item_id} | {method} | {status} | {metadata} | {report} | {error} |".format(
                item_id=item.get("item_id", ""),
                method=item.get("method", ""),
                status=item.get("status", ""),
                metadata=item.get("result_metadata_ref", "") or "",
                report=item.get("report_ref", "") or "",
                error=str(item.get("error", "") or "").replace("|", "\\|"),
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _update_batch_index(root: Path, record: dict[str, Any], record_ref: str, summary_ref: str) -> None:
    index_path = root / "processed" / "batches" / "index.yml"
    index = read_yaml(index_path) if index_path.exists() else {"schema_version": "0.2", "batches": {}}
    index.setdefault("batches", {})[record["batch_id"]] = {
        "batch_id": record["batch_id"],
        "project_id": record["project_id"],
        "status": record["status"],
        "manifest_ref": record["manifest_ref"],
        "record_ref": record_ref,
        "summary_ref": summary_ref,
        "item_count": record["item_count"],
        "succeeded": record["succeeded"],
        "failed": record["failed"],
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
    }
    write_yaml(index_path, index)


def run_batch_manifest(root: Path, manifest_path: Path, *, created_at: str | None = None) -> dict[str, Any]:
    manifest_ref, batch_section, items = _load_manifest(root, manifest_path)
    validation = validate_batch_manifest(root, manifest_ref)
    if validation["status"] == "fail":
        raise BatchManifestError("Batch manifest validation failed.")

    defaults = _manifest_defaults(batch_section)
    project_id = str(defaults["project_id"] or _project_id_from_root(root))
    continue_on_error = bool(defaults["continue_on_error"])
    create_reports = bool(defaults["create_reports"])
    timestamp = created_at or EARecord.now_iso()
    batch_id = str(batch_section.get("batch_id") or next_id(root, "batch", timestamp[:10]))
    batch_dir = root / "processed" / "batches" / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)

    item_records: list[dict[str, Any]] = []
    output_records: list[str] = []
    warnings: list[dict[str, str]] = []
    for index, item in enumerate(items, start=1):
        item_id = str(item.get("item_id") or f"item-{index:03d}")
        method = str(item["method"]).lower()
        item_project_id = str(item.get("project_id") or project_id)
        item_record: dict[str, Any] = {
            "item_id": item_id,
            "method": method,
            "metadata_ref": item["metadata"],
            "sample_refs": list(item.get("sample_refs", item.get("sample_ref", [])) or []),
            "experiment_refs": list(item.get("experiment_refs", item.get("experiment_ref", [])) or []),
            "x_column": str(item["x_column"]),
            "y_column": str(item["y_column"]),
            "x_unit": str(item["x_unit"]),
            "signal_mode": item.get("signal_mode"),
            "review_refs": [str(item["column_review_ref"]), str(item["parameter_review_ref"])],
            "status": "pending",
        }
        try:
            result_path = _run_method(root, method, item_project_id, item, timestamp)
            item_record["result_metadata_ref"] = _path_ref(root, result_path)
            output_records.append(item_record["result_metadata_ref"])
            if create_reports and bool(item.get("create_report", True)):
                report_path = _generate_report(
                    root,
                    method=method,
                    project_id=item_project_id,
                    result_metadata_path=result_path,
                    item=item,
                    default_reference_ids=defaults["reference_ids"],
                    created_at=timestamp,
                )
                item_record["report_ref"] = _path_ref(root, report_path)
                output_records.append(item_record["report_ref"])
            item_record["status"] = "success"
        except Exception as exc:  # noqa: BLE001 - batch execution must preserve item-level failures.
            item_record["status"] = "failed"
            item_record["error"] = str(exc)
            warnings.append({"item_id": item_id, "message": str(exc)})
            if not continue_on_error:
                item_records.append(item_record)
                break
        item_records.append(item_record)

    failed = sum(1 for item in item_records if item["status"] == "failed")
    succeeded = sum(1 for item in item_records if item["status"] == "success")
    status = "success" if failed == 0 else "failed"
    record_path = batch_dir / "batch_run.yml"
    summary_path = batch_dir / "batch_summary.md"
    record_ref = _path_ref(root, record_path)
    summary_ref = _path_ref(root, summary_path)
    record = {
        "schema_version": "0.2",
        "batch_id": batch_id,
        "project_id": project_id,
        "manifest_ref": _path_ref(root, manifest_ref),
        "status": status,
        "item_count": len(items),
        "succeeded": succeeded,
        "failed": failed,
        "create_reports": create_reports,
        "continue_on_error": continue_on_error,
        "items": item_records,
        "warnings": warnings,
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    write_yaml(record_path, record)
    _write_summary(summary_path, record)
    _update_batch_index(root, record, record_ref, summary_ref)

    provenance_path = write_provenance_entry(
        root,
        workflow="batch_characterization",
        inputs={"records": [_path_ref(root, manifest_ref)], "files": []},
        outputs={
            "records": [record_ref, summary_ref, "processed/batches/index.yml", *output_records],
            "files": [],
        },
        parameters={"create_reports": create_reports, "continue_on_error": continue_on_error},
        review_refs=sorted({review for item in item_records for review in item.get("review_refs", [])}),
        warnings=warnings,
        scripts=[{"path": "src/ea/batch/service.py", "version": "0.2.0"}],
        created_at=timestamp,
    )
    record["provenance_refs"] = [provenance_path.stem]
    write_yaml(record_path, record)
    _update_batch_index(root, record, record_ref, summary_ref)
    return {
        "batch_id": batch_id,
        "status": status,
        "record": str(record_path),
        "summary": str(summary_path),
        "item_count": len(items),
        "succeeded": succeeded,
        "failed": failed,
    }
