from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path
from typing import Any

from ea.schema.models import EARecord
from ea.storage.files import read_markdown_record, read_yaml, write_yaml


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


def _default_archive_path(bundle_dir: Path) -> Path:
    return bundle_dir.parent / f"{bundle_dir.name}.zip"


def _write_zip_archive(bundle_dir: Path, archive_path: Path) -> Path:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_resolved = archive_path.resolve()
    if archive_path.exists():
        archive_path.unlink()
    with zipfile.ZipFile(archive_path, "w") as archive:
        for path in sorted(item for item in bundle_dir.rglob("*") if item.is_file()):
            if path.resolve() == archive_resolved:
                continue
            zip_info = zipfile.ZipInfo(path.relative_to(bundle_dir).as_posix())
            zip_info.date_time = (1980, 1, 1, 0, 0, 0)
            zip_info.compress_type = zipfile.ZIP_DEFLATED
            zip_info.external_attr = 0o644 << 16
            archive.writestr(zip_info, path.read_bytes())
    return archive_path


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


def export_report_bundle(
    root: Path,
    *,
    report_id: str,
    output_dir: Path | None = None,
    created_at: str | None = None,
    create_archive: bool = False,
    archive_path: Path | None = None,
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
        },
        "provenance_inputs": [],
        "missing_refs": [],
        "archive_created": False,
        "archive_path": None,
        "archive_ref": None,
    }

    report_ref = str(report_record.get("path") or "")
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

    manifest["status"] = "complete" if not manifest["missing_refs"] else "warning"
    if create_archive:
        archive_target = archive_path or _default_archive_path(bundle_dir)
        if not archive_target.is_absolute():
            archive_target = root / archive_target
        manifest["archive_created"] = True
        manifest["archive_path"] = str(archive_target)
        manifest["archive_ref"] = _project_ref(root, archive_target)

    manifest_path = bundle_dir / "bundle_manifest.yml"
    manifest["manifest_path"] = str(manifest_path)
    write_yaml(manifest_path, manifest)
    if create_archive:
        try:
            _write_zip_archive(bundle_dir, archive_target)
        except OSError as exc:
            raise ReportBundleError(f"Failed to create report bundle archive: {archive_target}: {exc}") from exc
    return manifest
