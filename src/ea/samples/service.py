from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ea.schema import SampleRecord
from ea.schema.models import EARecord
from ea.provenance import write_provenance_entry
from ea.review import classify_user_response, write_review_record
from ea.storage.files import read_markdown_record, write_markdown_record, write_yaml
from ea.storage.ids import next_id


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


def add_sample_record(
    root: Path,
    *,
    project_id: str,
    material_system: str,
    created_from_experiment: str,
    sample_id: str | None = None,
    quality_status: str = "unknown",
    morphology_observations: list[str] | None = None,
    quality_notes: list[str] | None = None,
    created_at: str | None = None,
) -> Path:
    sample_id = sample_id or next_id(
        root, "sample", created_at[:10] if created_at else None
    )
    path = root / "samples" / f"{sample_id}.md"
    if path.exists():
        raise FileExistsError(f"Sample already exists: {sample_id}")
    path = save_sample_record(
        root,
        sample_id=sample_id,
        project_id=project_id,
        material_system=material_system,
        created_from_experiment=created_from_experiment,
        quality_status=quality_status,
        morphology_observations=morphology_observations,
        quality_notes=quality_notes,
        source_refs=[created_from_experiment],
        created_at=created_at,
    )
    provenance = write_provenance_entry(
        root,
        workflow="sample_record_add",
        inputs={"records": [f"experiments/{created_from_experiment}.md"], "files": []},
        outputs={"records": [path.relative_to(root).as_posix()], "files": []},
        parameters={"quality_status": quality_status},
        created_at=created_at,
    )
    record, body = read_markdown_record(path)
    record["provenance_refs"] = [provenance.stem]
    write_markdown_record(path, record, body)
    return path


def select_best_sample(
    root: Path,
    *,
    sample_id: str,
    user_response: str,
    rationale: str | None = None,
    selected_at: str | None = None,
) -> dict:
    sample_path = root / "samples" / f"{sample_id}.md"
    if not sample_path.is_file():
        raise FileNotFoundError(sample_path)
    classification = classify_user_response(user_response)
    if not classification.can_save:
        return {
            "status": "needs_clear_confirmation",
            "selected_sample_id": sample_id,
            "writes": False,
        }
    selection_ref = "samples/selection.yml"
    reviewed_content = repr({"sample_id": sample_id, "rationale": rationale})
    review = write_review_record(
        root,
        target_type="sample_selection",
        target_ref=selection_ref,
        user_response=user_response,
        reviewed_content=reviewed_content,
        reviewed_at=selected_at,
    )
    record = {
        "schema_version": "1.1",
        "status": "user_confirmed",
        "selected_sample_id": sample_id,
        "rationale": rationale,
        "review_refs": [review.stem],
        "selected_at": selected_at or EARecord.now_iso(),
        "source_refs": [sample_path.relative_to(root).as_posix()],
    }
    write_yaml(root / selection_ref, record)
    provenance = write_provenance_entry(
        root,
        workflow="best_sample_selection",
        inputs={"records": record["source_refs"], "files": []},
        outputs={"records": [selection_ref], "files": []},
        parameters={"selected_sample_id": sample_id, "rationale": rationale},
        review_refs=[review.stem],
        created_at=selected_at,
    )
    record["provenance_refs"] = [provenance.stem]
    write_yaml(root / selection_ref, record)
    return {**record, "selection_ref": selection_ref}
