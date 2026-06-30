from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ea.schema.models import EARecord
from ea.standards import slugify
from ea.storage.files import read_yaml, write_yaml

REQUIRED_MANIFEST_KEYS = [
    "id",
    "version",
    "category",
    "input_artifacts",
    "output_artifacts",
    "review_gates",
    "required_indices",
]

CHARACTERIZATION_REQUIRED_OUTPUTS = {
    "processed_result",
    "figure_record",
    "report_section",
    "provenance_record",
    "memory_candidate",
}

LITERATURE_REQUIRED_OUTPUTS = {
    "literature_status",
    "reference_record",
    "report_section",
    "provenance_record",
}

VISUALIZATION_REQUIRED_OUTPUTS = {
    "figure_record",
    "report_section",
    "provenance_record",
}

DEFAULT_REQUIRED_OUTPUTS = {
    "report_section",
    "provenance_record",
}

SAMPLE_OUTPUT_REQUIRED_FIELDS = {
    "processed_result": {"result_id"},
    "figure_record": {"figure_id", "path", "raw_data_ids", "sample_ids"},
    "literature_status": {"status_path"},
    "reference_record": {"reference_id", "citation"},
    "report_section": set(),
    "provenance_record": {"workflow", "inputs", "outputs"},
    "memory_candidate": {"status", "text"},
}


@dataclass(frozen=True)
class SkillManifestCheck:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    manifest: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SkillDryRunResult:
    ok: bool
    dry_run_id: str
    manifest_path: str
    sample_output_path: str | None
    report_path: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    manifest: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "0.2",
            "ok": self.ok,
            "dry_run_id": self.dry_run_id,
            "manifest_path": self.manifest_path,
            "sample_output_path": self.sample_output_path,
            "report_path": self.report_path,
            "errors": self.errors,
            "warnings": self.warnings,
            "manifest": self.manifest,
        }


def required_outputs_for_manifest(manifest: dict[str, Any]) -> set[str]:
    category = str(manifest.get("category") or "")
    if category == "characterization" or category.startswith("characterization."):
        return set(CHARACTERIZATION_REQUIRED_OUTPUTS)
    if category == "literature" or category.startswith("literature."):
        return set(LITERATURE_REQUIRED_OUTPUTS)
    if category == "visualization" or category.startswith("visualization."):
        return set(VISUALIZATION_REQUIRED_OUTPUTS)
    return set(DEFAULT_REQUIRED_OUTPUTS)


def validate_skill_manifest(path: Path) -> SkillManifestCheck:
    raw = read_yaml(path)
    manifest = raw.get("ea_skill", raw)
    errors: list[str] = []
    warnings: list[str] = []
    for key in REQUIRED_MANIFEST_KEYS:
        if key not in manifest:
            errors.append(f"missing:{key}")
    outputs = set(manifest.get("output_artifacts") or [])
    required_outputs = required_outputs_for_manifest(manifest)
    missing_outputs = sorted(required_outputs - outputs)
    for output in missing_outputs:
        errors.append(f"missing_output:{output}")
    if "confirm_interpretation_before_memory_write" not in (manifest.get("review_gates") or []):
        warnings.append("memory_write_review_gate_not_declared")
    indices = set(manifest.get("required_indices") or [])
    recommended_indices = {"reports/index.yml", "provenance/index.yml"}
    if "figure_record" in outputs:
        recommended_indices.add("figures/index.yml")
    for required in recommended_indices:
        if required not in indices:
            warnings.append(f"recommended_index_missing:{required}")
    return SkillManifestCheck(ok=not errors, errors=errors, warnings=warnings, manifest=manifest)


def _manifest_id(manifest: dict[str, Any]) -> str:
    return str(manifest.get("id") or "unknown-skill")


def _timestamp_key(value: str) -> str:
    return (
        value.replace("-", "")
        .replace(":", "")
        .replace("+", "")
        .replace(".", "")
        .replace("T", "T")[:15]
    )


def _path_for_record(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _sample_outputs(sample_output: dict[str, Any]) -> dict[str, Any]:
    outputs = sample_output.get("outputs")
    if isinstance(outputs, dict):
        return outputs
    return sample_output


def _check_sample_output(
    sample_output_path: Path,
    manifest: dict[str, Any],
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    sample = _sample_outputs(read_yaml(sample_output_path))
    declared_outputs = set(manifest.get("output_artifacts") or [])

    for artifact in sorted(required_outputs_for_manifest(manifest) & declared_outputs):
        if artifact not in sample:
            errors.append(f"sample_missing_output:{artifact}")
            continue
        value = sample.get(artifact)
        if not isinstance(value, dict):
            errors.append(f"sample_output_not_object:{artifact}")
            continue
        for field_name in sorted(SAMPLE_OUTPUT_REQUIRED_FIELDS.get(artifact, set())):
            if field_name not in value:
                errors.append(f"sample_output_missing_field:{artifact}.{field_name}")

    if "memory_candidate" in declared_outputs:
        memory_candidate = sample.get("memory_candidate")
        if memory_candidate is None:
            warnings.append("sample_memory_candidate_missing")
        elif isinstance(memory_candidate, dict) and memory_candidate.get("status") == "confirmed":
            errors.append("sample_memory_candidate_must_not_be_confirmed")

    report_section = sample.get("report_section")
    if isinstance(report_section, dict) and not (
        report_section.get("markdown") or report_section.get("text")
    ):
        errors.append("sample_report_section_missing_text")

    provenance = sample.get("provenance_record")
    if isinstance(provenance, dict) and not provenance.get("review_refs"):
        warnings.append("sample_provenance_review_refs_empty")

    return errors, warnings


def run_skill_dry_run(
    workspace: Path,
    manifest_path: Path,
    *,
    sample_output_path: Path | None = None,
    created_at: str | None = None,
) -> SkillDryRunResult:
    workspace.mkdir(parents=True, exist_ok=True)
    created_at = created_at or EARecord.now_iso()
    manifest_path = manifest_path.resolve()
    check = validate_skill_manifest(manifest_path)
    errors = list(check.errors)
    warnings = list(check.warnings)
    manifest = check.manifest

    if manifest.get("writes_to_raw") is True:
        errors.append("manifest_writes_to_raw")
    if manifest.get("direct_memory_write") is True:
        errors.append("manifest_direct_memory_write")
    if manifest.get("requires_credentials") and not manifest.get("user_setup_required"):
        errors.append("manifest_credentials_without_user_setup")
    if manifest.get("requires_network") and not manifest.get("user_confirmation_required"):
        warnings.append("manifest_network_requires_user_confirmation")

    sample_ref: str | None = None
    if sample_output_path is not None:
        sample_output_path = sample_output_path.resolve()
        sample_ref = str(sample_output_path)
        sample_errors, sample_warnings = _check_sample_output(sample_output_path, manifest)
        errors.extend(sample_errors)
        warnings.extend(sample_warnings)

    dry_run_id = f"dryrun-{slugify(_manifest_id(manifest))}-{_timestamp_key(created_at)}"
    report_path = workspace / "skill-registry" / "dry-runs" / f"{dry_run_id}.yml"
    result = SkillDryRunResult(
        ok=not errors,
        dry_run_id=dry_run_id,
        manifest_path=_path_for_record(workspace, manifest_path),
        sample_output_path=sample_ref,
        report_path=report_path.relative_to(workspace).as_posix(),
        errors=errors,
        warnings=warnings,
        manifest=manifest,
    )
    write_yaml(report_path, result.to_dict())
    return result


def register_skill_manifest(
    workspace: Path,
    manifest_path: Path,
    *,
    sample_output_path: Path | None = None,
    status: str = "active",
    created_at: str | None = None,
) -> dict[str, Any]:
    if status not in {"active", "sandbox"}:
        raise ValueError("status must be active or sandbox")
    dry_run = run_skill_dry_run(
        workspace,
        manifest_path,
        sample_output_path=sample_output_path,
        created_at=created_at,
    )
    if not dry_run.ok:
        return {
            "ok": False,
            "installed": False,
            "dry_run": dry_run.to_dict(),
            "registry_path": str(workspace / "skill-registry" / "index.yml"),
        }

    index_path = workspace / "skill-registry" / "index.yml"
    index = read_yaml(index_path) if index_path.exists() else {
        "schema_version": "0.2",
        "registry_type": "ea_project_skill_registry",
        "skills": [],
    }
    skills = [item for item in index.get("skills", []) if item.get("id") != dry_run.manifest.get("id")]
    record = {
        "id": dry_run.manifest["id"],
        "version": dry_run.manifest.get("version"),
        "manifest": dry_run.manifest_path,
        "status": status,
        "category": dry_run.manifest.get("category"),
        "method": dry_run.manifest.get("method"),
        "source_type": "user_manifest",
        "dry_run_report": dry_run.report_path,
        "registered_at": created_at or EARecord.now_iso(),
    }
    skills.append(record)
    index["skills"] = sorted(skills, key=lambda item: str(item.get("id", "")))
    write_yaml(index_path, index)
    return {
        "ok": True,
        "installed": True,
        "registry_path": str(index_path),
        "record": record,
        "dry_run": dry_run.to_dict(),
    }
