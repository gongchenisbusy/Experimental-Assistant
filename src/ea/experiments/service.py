from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ea.provenance import write_provenance_entry
from ea.review import classify_user_response, write_review_record
from ea.schema import ExperimentRecord
from ea.schema.models import EARecord
from ea.storage.files import write_markdown_record
from ea.storage.files import read_markdown_record
from ea.storage.ids import next_id


class ReviewRequiredError(RuntimeError):
    """Raised when a formal save is attempted without clear user confirmation."""


CHINESE_NUMBERS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
}


@dataclass
class ExperimentDraft:
    user_original_text: str
    status: str = "needs_user_review"
    process_conditions: dict[str, Any] = field(default_factory=dict)
    observations: list[str] = field(default_factory=list)
    initial_judgement: str | None = None
    uncertainties: list[str] = field(default_factory=list)
    sample_refs: list[str] = field(default_factory=list)

    def reviewed_content(self) -> str:
        return repr(
            {
                "process_conditions": self.process_conditions,
                "observations": self.observations,
                "initial_judgement": self.initial_judgement,
                "uncertainties": self.uncertainties,
                "sample_refs": self.sample_refs,
            }
        )


def _number(value: str) -> int:
    if value.isdigit():
        return int(value)
    return CHINESE_NUMBERS[value]


def _search_number(pattern: str, text: str) -> int | None:
    match = re.search(pattern, text)
    if not match:
        return None
    return _number(match.group(1))


def structure_experiment_log(text: str) -> ExperimentDraft:
    draft = ExperimentDraft(user_original_text=text)
    conditions = draft.process_conditions

    if flow_match := re.search(r"流速\s*(\d+)", text):
        conditions["flow_rate"] = int(flow_match.group(1))
        conditions["flow_rate_unit"] = "unknown"
        draft.uncertainties.append("flow_rate_unit_and_carrier_gas")

    substrate_count = _search_number(r"(?:一共)?([一二两三四五六0-9]+)片(?:mica)?(?:衬底|，|,|$)", text)
    if substrate_count is not None:
        conditions["substrate_count"] = substrate_count
        draft.uncertainties.append("substrate_positions_or_ids")

    if run_match := re.search(r"(今天)?(第[一二三四五六0-9]+炉|第一炉|第二炉|第三炉)", text):
        conditions["run_label"] = run_match.group(2)
        if "今天" in run_match.group(0) or text.startswith(("第一炉", "第二炉", "第三炉")):
            draft.uncertainties.append("actual_experiment_date")

    if sulfur_match := re.search(r"硫源\s*(\d+)\s*°?C\s*开启", text):
        conditions["sulfur_start_temperature_c"] = int(sulfur_match.group(1))

    if hold_match := re.search(r"保温时间(?:缩短到|为)?\s*(\d+)\s*min", text):
        conditions["hold_time_min"] = int(hold_match.group(1))

    if "有有" in text:
        draft.uncertainties.append("possible_typo_grown_count")

    grown_count = _search_number(r"(?:有有|有)?([一二两三四五六0-9]+)片长上", text)
    if grown_count is not None:
        conditions["grown_substrate_count"] = grown_count
        draft.uncertainties.append("which_substrates_grew")

    size_values = [int(value) for value in re.findall(r"(\d+)\s*(?:到|-|～)?\s*(?:\d+)?\s*微米", text)]
    if size_values:
        observations = conditions.setdefault("size_mentions_um", [])
        observations.extend(size_values)

    if "三角形" in text:
        draft.observations.append("triangular_morphology_mentioned")
    if "正三角形" in text:
        draft.observations.append("regular_triangle_morphology_mentioned")
    if "刺细胞" in text:
        draft.observations.append("user_described_spiky_irregular_morphology")
    if "多层" in text or "双层" in text:
        draft.observations.append("possible_multilayer_or_bilayer_mentioned")
    if "污染" in text:
        draft.observations.append("possible_contamination_mentioned")

    if "可能" in text or "初步认为" in text:
        draft.initial_judgement = "user_preliminary_judgement_or_hypothesis"

    if "保存为阶段实验的标准条件" in text:
        conditions["stage_standard"] = True
        draft.uncertainties.append("requires_explicit_decision_log_confirmation")
    elif "保存为阶段实验的标准条件" in text.replace("了", ""):
        conditions["stage_standard"] = True

    return draft


def save_confirmed_experiment(
    root: Path,
    *,
    project_id: str,
    material_system: str,
    experiment_type: str,
    experiment_date: str,
    draft: ExperimentDraft,
    user_response: str,
    structured_by: str = "ea-experiment-log",
    saved_at: str | None = None,
) -> Path:
    classification = classify_user_response(user_response)
    if not classification.can_save:
        raise ReviewRequiredError(
            f"Experiment cannot be saved with review status {classification.review_status}"
        )

    experiment_id = next_id(root, "experiment", experiment_date)
    rel_path = Path("experiments") / f"{experiment_id}.md"
    review_path = write_review_record(
        root,
        target_type="experiment_record",
        target_ref=str(rel_path),
        user_response=user_response,
        reviewed_content=draft.reviewed_content(),
        reviewed_at=saved_at,
    )
    review_id = review_path.stem
    record = ExperimentRecord(
        experiment_id=experiment_id,
        project_id=project_id,
        experiment_date=experiment_date,
        material_system=material_system,
        experiment_type=experiment_type,
        user_original_text=draft.user_original_text,
        structured_by=structured_by,
        sample_refs=draft.sample_refs,
        process_conditions=draft.process_conditions,
        observations=draft.observations,
        initial_judgement=draft.initial_judgement,
        uncertainties=draft.uncertainties,
        review_refs=[review_id],
        created_at=saved_at or EARecord.now_iso(),
        updated_at=saved_at or EARecord.now_iso(),
    )
    experiment_path = write_markdown_record(
        root / rel_path,
        record.model_dump(exclude_none=True),
        "## User Original Text\n\n" + draft.user_original_text,
    )
    provenance_path = write_provenance_entry(
        root,
        workflow="experiment_log_save",
        inputs={"records": [], "files": []},
        outputs={"records": [str(rel_path)], "files": []},
        parameters={"structured_by": structured_by, "review_gate": "required"},
        review_refs=[review_id],
        source_refs=["user_original_text"],
        created_at=saved_at,
    )
    # Store the provenance reference after the path is known.
    frontmatter = record.model_dump(exclude_none=True)
    frontmatter["provenance_refs"] = [provenance_path.stem]
    write_markdown_record(
        experiment_path,
        frontmatter,
        "## User Original Text\n\n" + draft.user_original_text,
    )
    return experiment_path


def list_experiment_runs(root: Path) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    for path in sorted((root / "experiments").glob("*.md")):
        record, _ = read_markdown_record(path)
        conditions = record.get("process_conditions") or {}
        runs.append(
            {
                "experiment_id": record.get("experiment_id"),
                "experiment_date": record.get("experiment_date"),
                "run_label": conditions.get("run_label"),
                "flow_rate": conditions.get("flow_rate"),
                "sulfur_start_temperature_c": conditions.get(
                    "sulfur_start_temperature_c"
                ),
                "hold_time_min": conditions.get("hold_time_min"),
                "substrate_count": conditions.get("substrate_count"),
                "grown_substrate_count": conditions.get("grown_substrate_count"),
                "stage_standard": bool(conditions.get("stage_standard")),
                "sample_refs": record.get("sample_refs") or [],
                "ref": path.relative_to(root).as_posix(),
            }
        )
    return {
        "schema_version": "1.1",
        "status": "ready",
        "read_only": True,
        "run_count": len(runs),
        "runs": runs,
    }


def update_confirmed_experiment(
    root: Path,
    *,
    experiment_ref: str,
    condition_updates: dict[str, Any] | None = None,
    observation: str | None = None,
    user_response: str,
    updated_at: str | None = None,
) -> Path:
    classification = classify_user_response(user_response)
    if not classification.can_save:
        raise ReviewRequiredError(
            f"Experiment cannot be updated with review status {classification.review_status}"
        )
    path = root / experiment_ref
    if not path.is_file():
        candidate = root / "experiments" / f"{experiment_ref}.md"
        path = candidate if candidate.is_file() else path
    if not path.is_file():
        raise FileNotFoundError(path)
    record, body = read_markdown_record(path)
    updates = condition_updates or {}
    reviewed_content = repr(
        {"condition_updates": updates, "observation": observation}
    )
    review_path = write_review_record(
        root,
        target_type="experiment_record",
        target_ref=path.relative_to(root).as_posix(),
        user_response=user_response,
        reviewed_content=reviewed_content,
        reviewed_at=updated_at,
    )
    record.setdefault("process_conditions", {}).update(updates)
    if observation:
        record.setdefault("observations", []).append(observation)
    record.setdefault("review_refs", []).append(review_path.stem)
    record["updated_at"] = updated_at or EARecord.now_iso()
    record.setdefault("update_history", []).append(
        {
            "updated_at": record["updated_at"],
            "review_ref": review_path.stem,
            "condition_keys": sorted(updates),
            "observation_added": bool(observation),
        }
    )
    write_markdown_record(path, record, body)
    provenance_path = write_provenance_entry(
        root,
        workflow="experiment_log_update",
        inputs={"records": [path.relative_to(root).as_posix()], "files": []},
        outputs={"records": [path.relative_to(root).as_posix()], "files": []},
        parameters={"condition_updates": updates, "observation": observation},
        review_refs=[review_path.stem],
        created_at=updated_at,
    )
    record["provenance_refs"] = [
        *(record.get("provenance_refs") or []),
        provenance_path.stem,
    ]
    write_markdown_record(path, record, body)
    return path
