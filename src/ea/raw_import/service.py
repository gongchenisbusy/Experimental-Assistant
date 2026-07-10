from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ea.provenance import file_sha256, write_provenance_entry
from ea.schema import CharacterizationFile
from ea.schema.models import EARecord
from ea.storage.files import atomic_copy_file, read_yaml, write_yaml
from ea.storage.ids import next_id


class RawPathBoundaryError(ValueError):
    """Raised when generated output is directed into the raw data area."""


@dataclass(frozen=True)
class RawImportResult:
    characterization_id: str
    import_status: str
    metadata_path: Path
    project_raw_path: Path | None
    sha256: str
    canonical_metadata_path: Path | None = None


def _metadata_files(root: Path) -> list[Path]:
    raw_root = root / "raw"
    if not raw_root.exists():
        return []
    return sorted(raw_root.glob("*/*/metadata.yml"))


def _find_by_sha(root: Path, sha256: str) -> tuple[Path, dict[str, Any]] | None:
    for metadata_path in _metadata_files(root):
        metadata = read_yaml(metadata_path)
        if metadata.get("sha256") == sha256 and metadata.get("import_status") != "duplicate_alias":
            return metadata_path, metadata
    return None


def _source_ref(root: Path, source_path: Path) -> str:
    try:
        return source_path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(source_path)


def _set_readonly(path: Path) -> str | None:
    try:
        current = path.stat().st_mode
        path.chmod(current & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
        return None
    except OSError as exc:
        return f"readonly_chmod_failed: {exc}"


def assert_not_raw_output_path(root: Path, output_path: Path) -> None:
    raw_root = (root / "raw").resolve()
    resolved = output_path.resolve()
    if resolved == raw_root or raw_root in resolved.parents:
        raise RawPathBoundaryError(f"processed output cannot be written under raw/: {output_path}")


def import_raw_file(
    root: Path,
    source_path: Path,
    *,
    project_id: str,
    characterization_type: str = "raman",
    sample_refs: list[str] | None = None,
    experiment_refs: list[str] | None = None,
    imported_at: str | None = None,
) -> RawImportResult:
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    if not source_path.is_file():
        raise IsADirectoryError(f"raw source path is not a file: {source_path}")
    if source_path.stat().st_size == 0:
        raise ValueError(f"raw file is empty: {source_path}")

    root.mkdir(parents=True, exist_ok=True)
    imported_at = imported_at or EARecord.now_iso()
    sample_refs = sample_refs or []
    experiment_refs = experiment_refs or []
    sha256 = file_sha256(source_path)
    source_ref = _source_ref(root, source_path)
    file_size = source_path.stat().st_size
    original_mtime = source_path.stat().st_mtime
    duplicate = _find_by_sha(root, sha256)

    if duplicate:
        canonical_metadata_path, canonical_metadata = duplicate
        characterization_id = next_id(root, "characterization", imported_at[:10])
        metadata_path = root / "raw" / characterization_type / characterization_id / "metadata.yml"
        canonical_samples = set(canonical_metadata.get("sample_refs") or [])
        canonical_experiments = set(canonical_metadata.get("experiment_refs") or [])
        incoming_samples = set(sample_refs)
        incoming_experiments = set(experiment_refs)
        refs_conflict = bool(
            (incoming_samples and canonical_samples and incoming_samples != canonical_samples)
            or (incoming_experiments and canonical_experiments and incoming_experiments != canonical_experiments)
        )
        alias = {
            "characterization_id": characterization_id,
            "original_filename": source_path.name,
            "original_source_path": source_ref,
            "imported_at": imported_at,
            "sample_refs": sample_refs,
            "experiment_refs": experiment_refs,
            "alias_reason": "same_sha256",
        }
        import_status = "needs_review" if refs_conflict else "duplicate_alias"
        if not refs_conflict:
            canonical_metadata.setdefault("aliases", []).append(alias)
            write_yaml(canonical_metadata_path, canonical_metadata)
        metadata = {
            "characterization_id": characterization_id,
            "characterization_type": characterization_type,
            "project_id": project_id,
            "sample_refs": sample_refs,
            "experiment_refs": experiment_refs,
            "original_filename": source_path.name,
            "original_source_path": source_ref,
            "project_raw_path": canonical_metadata["project_raw_path"],
            "sha256": sha256,
            "file_size_bytes": file_size,
            "original_mtime": original_mtime,
            "imported_at": imported_at,
            "import_status": import_status,
            "canonical_raw_ref": canonical_metadata["characterization_id"],
            "alias_reason": "same_sha256_refs_conflict" if refs_conflict else "same_sha256",
            "aliases": [],
            "provenance_refs": [],
            "review_refs": [],
        }
        write_yaml(metadata_path, metadata)
        provenance_path = write_provenance_entry(
            root,
            workflow="raw_file_import",
            inputs={"records": [], "files": [source_ref]},
            outputs={"records": [metadata_path.relative_to(root).as_posix()], "files": []},
            parameters={"import_status": import_status, "sha256": sha256},
            warnings=[{"code": "duplicate_refs_need_review", "message": "Duplicate raw file was linked to different sample or experiment refs.", "severity": "high"}] if refs_conflict else [],
            created_at=imported_at,
        )
        metadata["provenance_refs"] = [provenance_path.stem]
        write_yaml(metadata_path, metadata)
        return RawImportResult(
            characterization_id=characterization_id,
            import_status=import_status,
            metadata_path=metadata_path,
            project_raw_path=None,
            sha256=sha256,
            canonical_metadata_path=canonical_metadata_path,
        )

    characterization_id = next_id(root, "characterization", imported_at[:10])
    raw_dir = root / "raw" / characterization_type / characterization_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    destination = raw_dir / source_path.name
    atomic_copy_file(source_path, destination)
    readonly_warning = _set_readonly(destination)
    warnings = []
    if readonly_warning:
        warnings.append({"code": "raw_readonly_chmod_failed", "message": readonly_warning, "severity": "medium"})

    metadata_path = raw_dir / "metadata.yml"
    record = CharacterizationFile(
        characterization_id=characterization_id,
        characterization_type=characterization_type,
        project_id=project_id,
        sample_refs=sample_refs,
        experiment_refs=experiment_refs,
        original_filename=source_path.name,
        original_source_path=source_ref,
        project_raw_path=destination.relative_to(root).as_posix(),
        sha256=sha256,
        file_size_bytes=file_size,
        original_mtime=original_mtime,
        imported_at=imported_at,
        import_status="imported",
        aliases=[],
        notes=None,
        provenance_refs=[],
        review_refs=[],
    )
    write_yaml(metadata_path, record.model_dump(exclude_none=True))
    provenance_path = write_provenance_entry(
        root,
        workflow="raw_file_import",
        inputs={"records": [], "files": [source_ref]},
        outputs={
            "records": [metadata_path.relative_to(root).as_posix()],
            "files": [destination.relative_to(root).as_posix()],
        },
        parameters={"import_status": "imported", "sha256": sha256},
        warnings=warnings,
        created_at=imported_at,
    )
    metadata = read_yaml(metadata_path)
    metadata["provenance_refs"] = [provenance_path.stem]
    metadata["warnings"] = warnings
    write_yaml(metadata_path, metadata)
    return RawImportResult(
        characterization_id=characterization_id,
        import_status="imported",
        metadata_path=metadata_path,
        project_raw_path=destination,
        sha256=sha256,
    )
