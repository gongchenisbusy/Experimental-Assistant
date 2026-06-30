from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ea.storage.files import read_yaml

REQUIRED_MANIFEST_KEYS = [
    "id",
    "version",
    "category",
    "input_artifacts",
    "output_artifacts",
    "review_gates",
    "required_indices",
]

REQUIRED_OUTPUTS = {
    "processed_result",
    "figure_record",
    "report_section",
    "provenance_record",
}


@dataclass(frozen=True)
class SkillManifestCheck:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    manifest: dict[str, Any] = field(default_factory=dict)


def validate_skill_manifest(path: Path) -> SkillManifestCheck:
    raw = read_yaml(path)
    manifest = raw.get("ea_skill", raw)
    errors: list[str] = []
    warnings: list[str] = []
    for key in REQUIRED_MANIFEST_KEYS:
        if key not in manifest:
            errors.append(f"missing:{key}")
    outputs = set(manifest.get("output_artifacts") or [])
    missing_outputs = sorted(REQUIRED_OUTPUTS - outputs)
    for output in missing_outputs:
        errors.append(f"missing_output:{output}")
    if "confirm_interpretation_before_memory_write" not in (manifest.get("review_gates") or []):
        warnings.append("memory_write_review_gate_not_declared")
    indices = set(manifest.get("required_indices") or [])
    for required in {"figures/index.yml", "reports/index.yml", "provenance/index.yml"}:
        if required not in indices:
            warnings.append(f"recommended_index_missing:{required}")
    return SkillManifestCheck(ok=not errors, errors=errors, warnings=warnings, manifest=manifest)
