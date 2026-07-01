from __future__ import annotations

import hashlib
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any, Iterable

from ea.schema.models import EARecord
from ea.storage.files import read_markdown_record, read_yaml, write_yaml
from ea.traceability import build_project_trace_view


class ReportBundleError(RuntimeError):
    """Raised when a report bundle cannot be produced from project indices."""


def _clean_ref(ref: str) -> str:
    return ref.split("#", 1)[0]


def _project_path(root: Path, ref: str) -> Path:
    path = Path(_clean_ref(ref))
    return path if path.is_absolute() else root / path


def _project_ref(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _provenance_path(root: Path, ref: str) -> Path:
    path = Path(_clean_ref(ref))
    if path.suffix or len(path.parts) > 1:
        return path if path.is_absolute() else root / path
    return root / "provenance" / f"{ref}.yml"


def _safe_name(value: str) -> str:
    value = _clean_ref(value).strip("/")
    return re.sub(r"[^A-Za-z0-9_.-]+", "__", value) or "artifact"


def _is_inside(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _copy_project_file(
    root: Path,
    bundle_dir: Path,
    *,
    ref: str,
    subdir: str,
    kind: str,
    label: str | None = None,
) -> dict[str, Any]:
    source = _project_path(root, ref)
    record: dict[str, Any] = {
        "kind": kind,
        "label": label,
        "source_ref": ref,
        "exists": source.exists(),
        "copied": False,
        "bundle_ref": None,
    }
    if not source.exists():
        record["skip_reason"] = "missing_source"
        return record
    if not _is_inside(root, source):
        record["skip_reason"] = "outside_project_root"
        return record
    target = bundle_dir / subdir / _safe_name(_project_ref(root, source))
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    record["copied"] = True
    record["bundle_ref"] = target.relative_to(bundle_dir).as_posix()
    record["source_ref"] = _project_ref(root, source)
    return record


def _reports_index(root: Path) -> dict[str, Any]:
    path = root / "reports" / "index.yml"
    if not path.exists():
        raise ReportBundleError(f"Report index is missing: {path}")
    return read_yaml(path).get("reports", {})


def _batch_index(root: Path) -> dict[str, Any]:
    path = root / "processed" / "batches" / "index.yml"
    if not path.exists():
        raise ReportBundleError(f"Batch index is missing: {path}")
    return read_yaml(path).get("batches", {})


def _figures_index(root: Path) -> dict[str, Any]:
    path = root / "figures" / "index.yml"
    return read_yaml(path).get("figures", {}) if path.exists() else {}


def _reference_index(root: Path) -> dict[str, Any]:
    path = root / "literature" / "references" / "index.yml"
    return read_yaml(path).get("references", {}) if path.exists() else {}


def _result_metadata_index(root: Path) -> dict[str, Path]:
    results: dict[str, Path] = {}
    for path in sorted((root / "processed").glob("**/*.yml")):
        if "batches" in path.parts:
            continue
        data = read_yaml(path)
        for key, value in data.items():
            if (key == "result_id" or key.endswith("_result_id")) and value:
                results[str(value)] = path
    return results


def _record_missing(manifest: dict[str, Any], *, kind: str, ref: str, reason: str) -> None:
    manifest.setdefault("missing_refs", []).append({"kind": kind, "ref": ref, "reason": reason})


def _bundle_trace_view(
    root: Path,
    bundle_dir: Path,
    *,
    label: str,
    focus_ref: str,
    created_at: str,
) -> dict[str, Any]:
    trace_path = bundle_dir / "traceability" / f"{_safe_name(label)}_trace.yml"
    markdown_path = trace_path.with_suffix(".md")
    result = build_project_trace_view(
        root,
        focus_ref=focus_ref,
        output_path=trace_path,
        markdown_output_path=markdown_path,
        created_at=created_at,
    )
    return {
        "kind": "traceability_view",
        "label": label,
        "source": "ea.traceability.project_trace_view:v0.2",
        "generated": True,
        "status": result["status"],
        "focus_ref": focus_ref,
        "canonical_focus_ref": result.get("canonical_focus_ref"),
        "bundle_ref": trace_path.relative_to(bundle_dir).as_posix(),
        "markdown_bundle_ref": markdown_path.relative_to(bundle_dir).as_posix(),
        "trace_ref": result["trace_ref"],
        "markdown_ref": result["markdown_ref"],
        "node_count": result["node_count"],
        "edge_count": result["edge_count"],
        "missing_node_count": result["missing_node_count"],
        "boundaries": result["boundaries"],
    }


def _default_archive_path(bundle_dir: Path) -> Path:
    return bundle_dir.parent / f"{bundle_dir.name}.zip"


def _archive_checksum_path(archive_path: Path) -> Path:
    return archive_path.with_name(f"{archive_path.name}.sha256")


def _resolved_paths(paths: Iterable[Path | None]) -> set[Path]:
    return {path.resolve() for path in paths if path is not None}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_zip_archive(bundle_dir: Path, archive_path: Path, *, exclude_paths: Iterable[Path | None] = ()) -> Path:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    excluded = _resolved_paths([archive_path, *exclude_paths])
    if archive_path.exists():
        archive_path.unlink()
    with zipfile.ZipFile(archive_path, "w") as archive:
        for path in sorted(item for item in bundle_dir.rglob("*") if item.is_file()):
            if path.resolve() in excluded:
                continue
            zip_info = zipfile.ZipInfo(path.relative_to(bundle_dir).as_posix())
            zip_info.date_time = (1980, 1, 1, 0, 0, 0)
            zip_info.compress_type = zipfile.ZIP_DEFLATED
            zip_info.external_attr = 0o644 << 16
            archive.writestr(zip_info, path.read_bytes())
    return archive_path


def _write_archive_checksum(archive_path: Path, checksum_path: Path) -> Path:
    checksum_path.parent.mkdir(parents=True, exist_ok=True)
    checksum_path.write_text(f"{_sha256_file(archive_path)}  {archive_path.name}\n", encoding="utf-8")
    return checksum_path


def _write_bundle_checksums(
    root: Path,
    bundle_dir: Path,
    manifest: dict[str, Any],
    *,
    exclude_paths: Iterable[Path | None] = (),
) -> Path:
    checksum_path = bundle_dir / "bundle_checksums.yml"
    excluded = _resolved_paths([checksum_path, *exclude_paths])
    files = []
    for path in sorted(item for item in bundle_dir.rglob("*") if item.is_file()):
        if path.resolve() in excluded:
            continue
        files.append(
            {
                "path": path.relative_to(bundle_dir).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    checksum_manifest = {
        "schema_version": "0.2",
        "checksum_manifest_id": f"checksums-{manifest['bundle_id']}",
        "bundle_id": manifest["bundle_id"],
        "created_at": manifest["created_at"],
        "algorithm": "sha256",
        "bundle_path": str(bundle_dir),
        "checksum_manifest_path": str(checksum_path),
        "checksum_manifest_ref": _project_ref(root, checksum_path),
        "excluded_paths": sorted(
            path.relative_to(bundle_dir).as_posix()
            for path in (bundle_dir / rel for rel in ["bundle_checksums.yml"])
            if path.resolve() in excluded
        ),
        "files": files,
    }
    write_yaml(checksum_path, checksum_manifest)
    return checksum_path


def verify_bundle_checksums(bundle_dir: Path) -> dict[str, Any]:
    bundle_dir = bundle_dir.resolve()
    checksum_path = bundle_dir / "bundle_checksums.yml"
    result: dict[str, Any] = {
        "schema_version": "0.2",
        "check_type": "bundle",
        "status": "pass",
        "bundle_path": str(bundle_dir),
        "checksum_manifest_path": str(checksum_path),
        "algorithm": "sha256",
        "checked_count": 0,
        "failures": [],
    }
    if not bundle_dir.is_dir():
        result["status"] = "fail"
        result["failures"].append({"path": str(bundle_dir), "reason": "missing_bundle_dir"})
        return result
    if not checksum_path.exists():
        result["status"] = "fail"
        result["failures"].append({"path": "bundle_checksums.yml", "reason": "missing_checksum_manifest"})
        return result

    checksum_manifest = read_yaml(checksum_path)
    algorithm = str(checksum_manifest.get("algorithm") or "")
    result["algorithm"] = algorithm
    if algorithm != "sha256":
        result["status"] = "fail"
        result["failures"].append({"path": "bundle_checksums.yml", "reason": "unsupported_algorithm", "algorithm": algorithm})
        return result

    for entry in checksum_manifest.get("files") or []:
        ref = str(entry.get("path") or "")
        file_path = bundle_dir / ref
        expected_size = entry.get("size_bytes")
        expected_sha = str(entry.get("sha256") or "")
        if not ref or not _is_inside(bundle_dir, file_path):
            result["failures"].append({"path": ref, "reason": "outside_bundle"})
            continue
        if not file_path.exists():
            result["failures"].append({"path": ref, "reason": "missing_file"})
            continue
        result["checked_count"] += 1
        actual_size = file_path.stat().st_size
        actual_sha = _sha256_file(file_path)
        if expected_size != actual_size:
            result["failures"].append(
                {
                    "path": ref,
                    "reason": "size_mismatch",
                    "expected_size_bytes": expected_size,
                    "actual_size_bytes": actual_size,
                }
            )
        if expected_sha != actual_sha:
            result["failures"].append(
                {
                    "path": ref,
                    "reason": "sha256_mismatch",
                    "expected_sha256": expected_sha,
                    "actual_sha256": actual_sha,
                }
            )
    result["status"] = "pass" if not result["failures"] else "fail"
    return result


def verify_archive_checksum(archive_path: Path, checksum_path: Path | None = None) -> dict[str, Any]:
    archive_path = archive_path.resolve()
    checksum_path = (checksum_path or _archive_checksum_path(archive_path)).resolve()
    result: dict[str, Any] = {
        "schema_version": "0.2",
        "check_type": "archive",
        "status": "pass",
        "archive_path": str(archive_path),
        "checksum_path": str(checksum_path),
        "algorithm": "sha256",
        "failures": [],
    }
    if not archive_path.exists():
        result["status"] = "fail"
        result["failures"].append({"path": str(archive_path), "reason": "missing_archive"})
        return result
    if not checksum_path.exists():
        result["status"] = "fail"
        result["failures"].append({"path": str(checksum_path), "reason": "missing_archive_checksum"})
        return result
    sidecar = checksum_path.read_text(encoding="utf-8").strip().split()
    if not sidecar:
        result["status"] = "fail"
        result["failures"].append({"path": str(checksum_path), "reason": "empty_archive_checksum"})
        return result
    expected_sha = sidecar[0]
    actual_sha = _sha256_file(archive_path)
    result["expected_sha256"] = expected_sha
    result["actual_sha256"] = actual_sha
    if expected_sha != actual_sha:
        result["status"] = "fail"
        result["failures"].append(
            {
                "path": str(archive_path),
                "reason": "sha256_mismatch",
                "expected_sha256": expected_sha,
                "actual_sha256": actual_sha,
            }
        )
    return result


def _copy_provenance(
    root: Path,
    bundle_dir: Path,
    manifest: dict[str, Any],
    provenance_refs: list[str],
) -> list[dict[str, Any]]:
    copied = []
    seen = set()
    for provenance_ref in provenance_refs:
        if provenance_ref in seen:
            continue
        seen.add(provenance_ref)
        provenance_path = _provenance_path(root, provenance_ref)
        record = _copy_project_file(
            root,
            bundle_dir,
            ref=_project_ref(root, provenance_path),
            subdir="provenance",
            kind="provenance_record",
            label=provenance_ref,
        )
        copied.append(record)
        if not record["copied"]:
            _record_missing(manifest, kind="provenance_record", ref=provenance_ref, reason=str(record.get("skip_reason")))
            continue
        provenance = read_yaml(provenance_path)
        inputs = provenance.get("inputs") or {}
        for input_ref in list(inputs.get("records") or []) + list(inputs.get("files") or []):
            input_record = _copy_project_file(
                root,
                bundle_dir,
                ref=str(input_ref),
                subdir="provenance-inputs",
                kind="provenance_input",
                label=provenance_ref,
            )
            manifest.setdefault("provenance_inputs", []).append(input_record)
            if not input_record["copied"]:
                _record_missing(
                    manifest,
                    kind="provenance_input",
                    ref=str(input_ref),
                    reason=str(input_record.get("skip_reason")),
                )
    return copied


def _report_id_from_ref(root: Path, report_ref: str) -> str | None:
    report_path = _project_path(root, report_ref)
    if not report_path.exists():
        return None
    frontmatter, _ = read_markdown_record(report_path)
    report_id = frontmatter.get("report_id")
    return str(report_id) if report_id else None


def export_report_bundle(
    root: Path,
    *,
    report_id: str,
    output_dir: Path | None = None,
    created_at: str | None = None,
    create_archive: bool = False,
    archive_path: Path | None = None,
    include_trace: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    reports = _reports_index(root)
    report_record = reports.get(report_id)
    if not report_record:
        raise ReportBundleError(f"Unknown report_id: {report_id}")

    bundle_dir = output_dir or root / "exports" / "report-bundles" / report_id
    if not bundle_dir.is_absolute():
        bundle_dir = root / bundle_dir
    bundle_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "schema_version": "0.2",
        "bundle_id": f"bundle-{report_id}",
        "report_id": report_id,
        "created_at": created_at or EARecord.now_iso(),
        "workspace": str(root),
        "bundle_path": str(bundle_dir),
        "artifacts": {
            "reports": [],
            "figures": [],
            "source_data": [],
            "results": [],
            "references": [],
            "reference_files": [],
            "provenance": [],
            "traceability": [],
        },
        "trace_export": {
            "included": include_trace,
            "focus_ref": None,
            "strategy": "focused_report_trace_view" if include_trace else "not_requested",
            "boundaries": [
                "Trace export writes audit YAML/Markdown into the bundle only.",
                "It does not mutate reports, create ReviewRecords, commit memory, register references, inject citations, generate source packets/suggestions, or prove scientific conclusions.",
            ],
        },
        "provenance_inputs": [],
        "missing_refs": [],
        "archive_created": False,
        "archive_path": None,
        "archive_ref": None,
        "archive_checksum_path": None,
        "archive_checksum_ref": None,
        "checksum_manifest_path": None,
        "checksum_manifest_ref": None,
        "checksum_manifest_bundle_ref": None,
    }

    report_ref = str(report_record.get("path") or "")
    manifest["trace_export"]["focus_ref"] = report_ref or None
    report_copy = _copy_project_file(root, bundle_dir, ref=report_ref, subdir="reports", kind="report", label=report_id)
    manifest["artifacts"]["reports"].append(report_copy)
    report_frontmatter: dict[str, Any] = {}
    if report_copy["copied"]:
        report_frontmatter, _ = read_markdown_record(_project_path(root, report_ref))
    else:
        _record_missing(manifest, kind="report", ref=report_ref, reason=str(report_copy.get("skip_reason")))

    result_index = _result_metadata_index(root)
    for result_id in report_record.get("result_ids") or []:
        result_path = result_index.get(str(result_id))
        if not result_path:
            _record_missing(manifest, kind="result_metadata", ref=str(result_id), reason="unknown_result_id")
            continue
        result_ref = _project_ref(root, result_path)
        result_copy = _copy_project_file(
            root,
            bundle_dir,
            ref=result_ref,
            subdir="results",
            kind="result_metadata",
            label=str(result_id),
        )
        manifest["artifacts"]["results"].append(result_copy)
        if result_copy["copied"]:
            result_data = read_yaml(result_path)
            for provenance_ref in result_data.get("provenance_refs") or []:
                manifest["artifacts"]["provenance"].extend(
                    _copy_provenance(root, bundle_dir, manifest, [str(provenance_ref)])
                )

    figures = _figures_index(root)
    seen_source_refs: set[str] = set()
    for figure_id in report_record.get("figure_ids") or []:
        figure = figures.get(str(figure_id))
        if not figure:
            _record_missing(manifest, kind="figure_record", ref=str(figure_id), reason="unknown_figure_id")
            continue
        figure_copy = _copy_project_file(
            root,
            bundle_dir,
            ref=str(figure.get("path") or ""),
            subdir="figures",
            kind="figure_file",
            label=str(figure_id),
        )
        figure_copy["figure_record"] = figure
        manifest["artifacts"]["figures"].append(figure_copy)
        if not figure_copy["copied"]:
            _record_missing(manifest, kind="figure_file", ref=str(figure_id), reason=str(figure_copy.get("skip_reason")))
        for source_ref in figure.get("source_data_refs") or []:
            source_ref = str(source_ref)
            if source_ref in seen_source_refs:
                continue
            seen_source_refs.add(source_ref)
            source_copy = _copy_project_file(
                root,
                bundle_dir,
                ref=source_ref,
                subdir="source-data",
                kind="source_data",
                label=str(figure_id),
            )
            manifest["artifacts"]["source_data"].append(source_copy)
            if not source_copy["copied"]:
                _record_missing(manifest, kind="source_data", ref=source_ref, reason=str(source_copy.get("skip_reason")))

    references = _reference_index(root)
    for reference_id in report_record.get("reference_ids") or report_frontmatter.get("reference_ids") or []:
        reference = references.get(str(reference_id))
        if not reference:
            _record_missing(manifest, kind="reference_record", ref=str(reference_id), reason="unknown_reference_id")
            continue
        record_ref = str(reference.get("path") or f"literature/references/{reference_id}.yml")
        reference_copy = _copy_project_file(
            root,
            bundle_dir,
            ref=record_ref,
            subdir="references",
            kind="reference_record",
            label=str(reference_id),
        )
        manifest["artifacts"]["references"].append(reference_copy)
        if not reference_copy["copied"]:
            _record_missing(manifest, kind="reference_record", ref=str(reference_id), reason=str(reference_copy.get("skip_reason")))
            continue
        reference_data = read_yaml(_project_path(root, record_ref))
        local_path = reference_data.get("local_path")
        if local_path:
            file_copy = _copy_project_file(
                root,
                bundle_dir,
                ref=str(local_path),
                subdir="references/files",
                kind="reference_file",
                label=str(reference_id),
            )
            manifest["artifacts"]["reference_files"].append(file_copy)
            if not file_copy["copied"]:
                _record_missing(
                    manifest,
                    kind="reference_file",
                    ref=str(local_path),
                    reason=str(file_copy.get("skip_reason")),
                )

    report_provenance_refs = [str(item) for item in report_frontmatter.get("provenance_refs") or []]
    manifest["artifacts"]["provenance"].extend(_copy_provenance(root, bundle_dir, manifest, report_provenance_refs))

    if include_trace and report_ref:
        trace_record = _bundle_trace_view(
            root,
            bundle_dir,
            label=report_id,
            focus_ref=report_ref,
            created_at=str(manifest["created_at"]),
        )
        manifest["artifacts"]["traceability"].append(trace_record)
        manifest["trace_export"]["trace_bundle_ref"] = trace_record["bundle_ref"]
        manifest["trace_export"]["markdown_bundle_ref"] = trace_record["markdown_bundle_ref"]
        manifest["trace_export"]["canonical_focus_ref"] = trace_record.get("canonical_focus_ref")

    manifest["status"] = "complete" if not manifest["missing_refs"] else "warning"
    archive_target: Path | None = None
    archive_checksum: Path | None = None
    if create_archive:
        archive_target = archive_path or _default_archive_path(bundle_dir)
        if not archive_target.is_absolute():
            archive_target = root / archive_target
        archive_checksum = _archive_checksum_path(archive_target)
        manifest["archive_created"] = True
        manifest["archive_path"] = str(archive_target)
        manifest["archive_ref"] = _project_ref(root, archive_target)
        manifest["archive_checksum_path"] = str(archive_checksum)
        manifest["archive_checksum_ref"] = _project_ref(root, archive_checksum)

    manifest_path = bundle_dir / "bundle_manifest.yml"
    manifest["manifest_path"] = str(manifest_path)
    checksum_path = bundle_dir / "bundle_checksums.yml"
    manifest["checksum_manifest_path"] = str(checksum_path)
    manifest["checksum_manifest_ref"] = _project_ref(root, checksum_path)
    manifest["checksum_manifest_bundle_ref"] = checksum_path.relative_to(bundle_dir).as_posix()
    write_yaml(manifest_path, manifest)
    _write_bundle_checksums(root, bundle_dir, manifest, exclude_paths=[archive_target, archive_checksum])
    if create_archive:
        try:
            _write_zip_archive(bundle_dir, archive_target, exclude_paths=[archive_checksum])
            _write_archive_checksum(archive_target, archive_checksum)
        except OSError as exc:
            raise ReportBundleError(f"Failed to create report bundle archive: {archive_target}: {exc}") from exc
    return manifest


def export_batch_bundle(
    root: Path,
    *,
    batch_id: str,
    output_dir: Path | None = None,
    created_at: str | None = None,
    create_archive: bool = False,
    archive_path: Path | None = None,
    include_trace: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    batches = _batch_index(root)
    batch_index_record = batches.get(batch_id)
    if not batch_index_record:
        raise ReportBundleError(f"Unknown batch_id: {batch_id}")

    bundle_dir = output_dir or root / "exports" / "batch-bundles" / batch_id
    if not bundle_dir.is_absolute():
        bundle_dir = root / bundle_dir
    bundle_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "schema_version": "0.2",
        "bundle_id": f"bundle-{batch_id}",
        "batch_id": batch_id,
        "created_at": created_at or EARecord.now_iso(),
        "workspace": str(root),
        "bundle_path": str(bundle_dir),
        "artifacts": {
            "batch_records": [],
            "report_bundles": [],
            "provenance": [],
        },
        "trace_export": {
            "included": include_trace,
            "strategy": "nested_report_focused_trace_views" if include_trace else "not_requested",
            "batch_level_trace_included": False,
            "batch_level_trace_reason": "project_trace_view_does_not_model_batch_nodes_yet" if include_trace else None,
            "boundaries": [
                "Batch trace export currently delegates to nested report bundle focused trace views.",
                "It does not mutate source reports, create ReviewRecords, commit memory, register references, inject citations, generate source packets/suggestions, or prove scientific conclusions.",
            ],
        },
        "provenance_inputs": [],
        "missing_refs": [],
        "archive_created": False,
        "archive_path": None,
        "archive_ref": None,
        "archive_checksum_path": None,
        "archive_checksum_ref": None,
        "checksum_manifest_path": None,
        "checksum_manifest_ref": None,
        "checksum_manifest_bundle_ref": None,
    }

    batch_refs = [
        ("batch_index", "processed/batches/index.yml"),
        ("batch_run", str(batch_index_record.get("record_ref") or "")),
        ("batch_summary", str(batch_index_record.get("summary_ref") or "")),
        ("batch_manifest", str(batch_index_record.get("manifest_ref") or "")),
    ]
    for kind, ref in batch_refs:
        if not ref:
            _record_missing(manifest, kind=kind, ref=ref, reason="empty_ref")
            continue
        copied = _copy_project_file(root, bundle_dir, ref=ref, subdir="batch", kind=kind, label=batch_id)
        manifest["artifacts"]["batch_records"].append(copied)
        if not copied["copied"]:
            _record_missing(manifest, kind=kind, ref=ref, reason=str(copied.get("skip_reason")))

    batch_record_path = _project_path(root, str(batch_index_record.get("record_ref") or ""))
    batch_record = read_yaml(batch_record_path) if batch_record_path.exists() else {}
    manifest["batch_status"] = batch_record.get("status") or batch_index_record.get("status")
    manifest["item_count"] = batch_record.get("item_count") or batch_index_record.get("item_count")
    manifest["items"] = []

    for item in batch_record.get("items") or []:
        item_summary = {
            "item_id": item.get("item_id"),
            "method": item.get("method"),
            "status": item.get("status"),
            "report_ref": item.get("report_ref"),
            "report_id": None,
            "report_bundle_ref": None,
            "report_manifest_ref": None,
        }
        manifest["items"].append(item_summary)
        report_ref = str(item.get("report_ref") or "")
        if not report_ref:
            if item.get("status") == "success":
                _record_missing(
                    manifest,
                    kind="item_report",
                    ref=str(item.get("item_id") or ""),
                    reason="missing_report_ref",
                )
            continue
        report_id = _report_id_from_ref(root, report_ref)
        if not report_id:
            _record_missing(manifest, kind="item_report", ref=report_ref, reason="missing_or_unreadable_report")
            continue
        report_bundle = export_report_bundle(
            root,
            report_id=report_id,
            output_dir=bundle_dir / "report-bundles" / report_id,
            created_at=str(manifest["created_at"]),
            create_archive=False,
            include_trace=include_trace,
        )
        report_bundle_ref = _project_ref(root, Path(report_bundle["bundle_path"]))
        report_manifest_ref = _project_ref(root, Path(report_bundle["manifest_path"]))
        item_summary["report_id"] = report_id
        item_summary["report_bundle_ref"] = report_bundle_ref
        item_summary["report_manifest_ref"] = report_manifest_ref
        nested = {
            "kind": "report_bundle",
            "label": report_id,
            "item_id": item.get("item_id"),
            "status": report_bundle["status"],
            "bundle_ref": Path(report_bundle["bundle_path"]).relative_to(bundle_dir).as_posix(),
            "manifest_ref": Path(report_bundle["manifest_path"]).relative_to(bundle_dir).as_posix(),
            "missing_ref_count": len(report_bundle.get("missing_refs") or []),
            "traceability": report_bundle.get("artifacts", {}).get("traceability", []),
        }
        manifest["artifacts"]["report_bundles"].append(nested)
        for missing in report_bundle.get("missing_refs") or []:
            manifest["missing_refs"].append(
                {
                    "kind": f"report_bundle.{missing.get('kind')}",
                    "ref": str(missing.get("ref")),
                    "reason": str(missing.get("reason")),
                    "report_id": report_id,
                    "item_id": item.get("item_id"),
                }
            )

    manifest["artifacts"]["provenance"].extend(
        _copy_provenance(root, bundle_dir, manifest, [str(ref) for ref in batch_record.get("provenance_refs") or []])
    )

    manifest["status"] = "complete" if not manifest["missing_refs"] else "warning"
    archive_target: Path | None = None
    archive_checksum: Path | None = None
    if create_archive:
        archive_target = archive_path or _default_archive_path(bundle_dir)
        if not archive_target.is_absolute():
            archive_target = root / archive_target
        archive_checksum = _archive_checksum_path(archive_target)
        manifest["archive_created"] = True
        manifest["archive_path"] = str(archive_target)
        manifest["archive_ref"] = _project_ref(root, archive_target)
        manifest["archive_checksum_path"] = str(archive_checksum)
        manifest["archive_checksum_ref"] = _project_ref(root, archive_checksum)

    manifest_path = bundle_dir / "batch_bundle_manifest.yml"
    manifest["manifest_path"] = str(manifest_path)
    checksum_path = bundle_dir / "bundle_checksums.yml"
    manifest["checksum_manifest_path"] = str(checksum_path)
    manifest["checksum_manifest_ref"] = _project_ref(root, checksum_path)
    manifest["checksum_manifest_bundle_ref"] = checksum_path.relative_to(bundle_dir).as_posix()
    write_yaml(manifest_path, manifest)
    _write_bundle_checksums(root, bundle_dir, manifest, exclude_paths=[archive_target, archive_checksum])
    if create_archive:
        try:
            _write_zip_archive(bundle_dir, archive_target, exclude_paths=[archive_checksum])
            _write_archive_checksum(archive_target, archive_checksum)
        except OSError as exc:
            raise ReportBundleError(f"Failed to create batch bundle archive: {archive_target}: {exc}") from exc
    return manifest
