from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ea.schema import SampleRecord
from ea.schema.models import EARecord
from ea.storage.files import read_markdown_record, write_markdown_record


@dataclass(frozen=True)
class RamanCandidate:
    sample_id: str
    quality_status: str
    reason: str
    source_label: str
    source_ref: str


QUALITY_SCORE = {
    "candidate_good": 100,
    "candidate_medium": 60,
    "unknown": 10,
    "candidate_poor": -100,
}


def save_sample_record(
    root: Path,
    *,
    sample_id: str,
    project_id: str,
    material_system: str,
    created_from_experiment: str,
    status: str = "active",
    quality_status: str = "unknown",
    morphology_observations: list[str] | None = None,
    quality_notes: list[str] | None = None,
    source_refs: list[str] | None = None,
    created_at: str | None = None,
) -> Path:
    record = SampleRecord(
        sample_id=sample_id,
        project_id=project_id,
        material_system=material_system,
        created_from_experiment=created_from_experiment,
        status=status,
        quality_status=quality_status,  # type: ignore[arg-type]
        morphology_observations=morphology_observations or [],
        quality_notes=quality_notes or [],
        source_refs=source_refs or [created_from_experiment],
        created_at=created_at or EARecord.now_iso(),
        updated_at=created_at or EARecord.now_iso(),
    )
    return write_markdown_record(
        root / "samples" / f"{sample_id}.md",
        record.model_dump(exclude_none=True),
        "## Sample Notes\n\n" + "\n".join(record.quality_notes),
    )


def recommend_raman_candidates(root: Path, *, limit: int = 3) -> list[RamanCandidate]:
    candidates: list[tuple[int, RamanCandidate]] = []
    for sample_file in sorted((root / "samples").glob("*.md")):
        frontmatter, _ = read_markdown_record(sample_file)
        quality_status = frontmatter.get("quality_status", "unknown")
        if quality_status == "candidate_poor":
            continue
        notes = frontmatter.get("quality_notes") or []
        morphology = frontmatter.get("morphology_observations") or []
        source_refs = frontmatter.get("source_refs") or []
        source_ref = source_refs[0] if source_refs else frontmatter.get("created_from_experiment", "")
        reason_parts = []
        if morphology:
            reason_parts.append("; ".join(morphology))
        if notes:
            reason_parts.append("; ".join(notes))
        reason = " | ".join(reason_parts) or "sample has no disqualifying note"
        sample_id = frontmatter["sample_id"]
        candidates.append(
            (
                QUALITY_SCORE.get(quality_status, 0),
                RamanCandidate(
                    sample_id=sample_id,
                    quality_status=quality_status,
                    reason=reason,
                    source_label=source_ref,
                    source_ref=source_ref,
                ),
            )
        )
    ordered = sorted(candidates, key=lambda item: (-item[0], item[1].sample_id))
    return [candidate for _, candidate in ordered[:limit]]
