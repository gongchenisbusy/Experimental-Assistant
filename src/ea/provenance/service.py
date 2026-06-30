from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ea import __version__
from ea.schema import ProvenanceEntry
from ea.schema.models import EARecord
from ea.storage.files import write_yaml
from ea.storage.ids import next_id


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_provenance_entry(
    root: Path,
    *,
    workflow: str,
    inputs: dict[str, list[str]] | None = None,
    outputs: dict[str, list[str]] | None = None,
    parameters: dict[str, Any] | None = None,
    review_refs: list[str] | None = None,
    warnings: list[Any] | None = None,
    source_refs: list[str] | None = None,
    scripts: list[dict[str, Any]] | None = None,
    skill_name: str = "ea-core",
    created_at: str | None = None,
) -> Path:
    provenance_id = next_id(root, "provenance", created_at[:10] if created_at else None)
    entry = ProvenanceEntry(
        provenance_id=provenance_id,
        workflow=workflow,
        created_at=created_at or EARecord.now_iso(),
        skill_name=skill_name,
        skill_version=__version__,
        inputs=inputs or {"records": [], "files": []},
        outputs=outputs or {"records": [], "files": []},
        parameters=parameters or {},
        review_refs=review_refs or [],
        warnings=warnings or [],
        source_refs=source_refs or [],
        scripts=scripts or [],
    )
    return write_yaml(
        root / "provenance" / f"{provenance_id}.yml",
        entry.model_dump(exclude_none=True),
    )
