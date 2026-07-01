from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from ea.storage.files import read_yaml


class SourcePacketManifestError(RuntimeError):
    """Raised when a literature source-candidate manifest is not confirmed or usable."""


CONFIRMED_STATUSES = {
    "confirmed",
    "user_confirmed",
    "source_packet_confirmed",
    "selected_by_user",
    "reviewed",
}
SKIP_STATUSES = {
    "rejected",
    "user_rejected",
    "deferred",
    "excluded",
    "not_selected",
    "do_not_use",
}


def _relative_to_root(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _coerce_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list | tuple | set):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _normal_status(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _confirmation_status(manifest: dict[str, Any]) -> str:
    for key in ["confirmation_status", "review_status", "selection_status"]:
        status = _normal_status(manifest.get(key))
        if status:
            return status
    for key in ["confirmation", "user_confirmation", "source_packet_confirmation"]:
        payload = manifest.get(key)
        if isinstance(payload, dict):
            for status_key in ["status", "review_status", "confirmation_status", "decision"]:
                status = _normal_status(payload.get(status_key))
                if status:
                    return status
    return "confirmed" if manifest.get("confirmed_for_source_packet") is True else ""


def _manifest_methods(manifest: dict[str, Any]) -> list[str]:
    for key in ["method", "methods", "method_scope", "target_method", "target_methods"]:
        values = _coerce_string_list(manifest.get(key))
        if values:
            return [_normal_status(value) for value in values]
    return []


def _candidate_method(candidate: dict[str, Any]) -> str:
    for key in ["method", "target_method", "source_packet_method", "characterization_type"]:
        value = _normal_status(candidate.get(key))
        if value:
            return value
    return ""


def _raw_candidates(manifest: dict[str, Any]) -> list[Any]:
    for key in ["candidates", "source_candidates", "assignment_candidates", "parameter_candidates", "suggestions"]:
        value = manifest.get(key)
        if isinstance(value, list):
            return value
    return []


def _candidate_should_copy(candidate: dict[str, Any]) -> bool:
    if candidate.get("include_in_source_packet") is False:
        return False
    if candidate.get("confirmed_for_source_packet") is False:
        return False
    status = _normal_status(
        candidate.get("source_packet_status")
        or candidate.get("review_status")
        or candidate.get("selection_status")
        or candidate.get("status")
    )
    return status not in SKIP_STATUSES


def confirmed_source_packet_library(
    root: Path,
    *,
    manifest_path: Path,
    method: str,
    method_aliases: set[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    resolved_path = manifest_path if manifest_path.is_absolute() else root / manifest_path
    if not resolved_path.exists():
        raise SourcePacketManifestError(f"Literature source-candidate manifest not found: {manifest_path}")
    manifest = read_yaml(resolved_path)
    if not isinstance(manifest, dict):
        raise SourcePacketManifestError(f"Literature source-candidate manifest must be a mapping: {manifest_path}")

    status = _confirmation_status(manifest)
    if status not in CONFIRMED_STATUSES:
        raise SourcePacketManifestError(
            "Literature source-candidate manifest must declare confirmed_for_source_packet: true "
            "or a user-confirmed confirmation_status before source packets can be populated."
        )

    normalized_method = _normal_status(method)
    aliases = {_normal_status(alias) for alias in method_aliases} | {normalized_method}
    manifest_methods = _manifest_methods(manifest)
    if manifest_methods and not any(item in aliases for item in manifest_methods):
        raise SourcePacketManifestError(
            f"Literature source-candidate manifest is scoped to {manifest_methods}, not {method} source packets."
        )

    warnings: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    for index, raw_candidate in enumerate(_raw_candidates(manifest), start=1):
        if not isinstance(raw_candidate, dict):
            warnings.append(
                {
                    "code": "literature_source_candidate_ignored",
                    "message": "A literature source-packet candidate was skipped because it was not a mapping.",
                    "severity": "medium",
                    "candidate_index": index,
                }
            )
            continue
        candidate_method = _candidate_method(raw_candidate)
        if candidate_method and candidate_method not in aliases:
            continue
        if not candidate_method and not manifest_methods:
            warnings.append(
                {
                    "code": "literature_source_candidate_method_missing",
                    "message": "A literature source-packet candidate was skipped because neither the manifest nor candidate declared a method.",
                    "severity": "medium",
                    "candidate_index": index,
                }
            )
            continue
        if not _candidate_should_copy(raw_candidate):
            continue
        candidate = deepcopy(raw_candidate)
        for key in [
            "method",
            "target_method",
            "source_packet_method",
            "characterization_type",
            "include_in_source_packet",
            "confirmed_for_source_packet",
            "source_packet_status",
            "selection_status",
        ]:
            candidate.pop(key, None)
        selected.append(candidate)

    source_ref = _relative_to_root(root, resolved_path)
    library = {
        "schema_version": "0.2",
        "source": "ea.literature.confirmed_source_packet_candidates:v0.2",
        "source_manifest_ref": source_ref,
        "confirmation_status": status,
        "confirmation": deepcopy(manifest.get("confirmation") or manifest.get("user_confirmation") or {}),
        "reference_seeds": deepcopy(manifest.get("reference_seeds") or {}),
        "guidance_notes": _coerce_string_list(manifest.get("guidance_notes")),
        "guidance_reference_ids": _coerce_string_list(manifest.get("guidance_reference_ids")),
        "candidates": selected,
    }
    return library, warnings
