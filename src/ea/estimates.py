from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from ea.storage.files import read_yaml, write_yaml

LARGE_WORK_THRESHOLD_CODEX_CREDITS = 100.0
UNCACHED_INPUT_CREDITS_PER_MILLION = 125.0
CACHED_INPUT_CREDITS_PER_MILLION = 12.5
OUTPUT_CREDITS_PER_MILLION = 750.0
PREFERENCE_REF = ".ea/preferences.yml"

WorkflowKind = Literal[
    "literature_search",
    "literature_acquisition",
    "literature_source_candidates",
    "analysis_report",
    "multi_method_report_bundle",
    "project_handoff",
]


WORKFLOW_PROFILES: dict[str, dict[str, int]] = {
    "literature_search": {"base_input_tokens": 20000, "per_item_input_tokens": 2500, "output_tokens": 6000},
    "literature_acquisition": {"base_input_tokens": 70000, "per_item_input_tokens": 18000, "output_tokens": 12000},
    "literature_source_candidates": {"base_input_tokens": 35000, "per_item_input_tokens": 7000, "output_tokens": 9000},
    "analysis_report": {"base_input_tokens": 25000, "per_item_input_tokens": 8000, "output_tokens": 18000},
    "multi_method_report_bundle": {"base_input_tokens": 80000, "per_item_input_tokens": 16000, "output_tokens": 30000},
    "project_handoff": {"base_input_tokens": 50000, "per_item_input_tokens": 6000, "output_tokens": 12000},
}


def _safe_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return read_yaml(path)
    except Exception:
        return {}


def _preferences_path(root: Path) -> Path:
    return root / PREFERENCE_REF


def large_work_reminders_disabled(root: Path) -> bool:
    return bool((_safe_yaml(_preferences_path(root)).get("large_work_reminders") or {}).get("disabled"))


def set_large_work_reminders(root: Path, *, disabled: bool, reason: str | None = None) -> dict[str, Any]:
    path = _preferences_path(root)
    prefs = _safe_yaml(path)
    prefs.setdefault("schema_version", "0.9.6")
    prefs["large_work_reminders"] = {
        "disabled": disabled,
        "reason": reason,
        "scope": "project",
        "preserves_safety_permission_and_review_gates": True,
    }
    write_yaml(path, prefs)
    return {"preferences_path": str(path), "large_work_reminders_disabled": disabled}


def _selected_literature_count(root: Path) -> int:
    selected = _safe_yaml(root / "literature" / "selected_items.yml")
    items = selected.get("items") or []
    if items:
        return len(items)
    status = _safe_yaml(root / "literature" / "deployment_status.yml")
    return int(status.get("selected_top_n") or status.get("recommended_top_n") or 0)


def _report_input_count(root: Path) -> int:
    reports = (_safe_yaml(root / "reports" / "index.yml").get("reports") or {})
    if reports:
        return len(reports)
    processed_files = list((root / "processed").glob("**/*_metadata.yml"))
    return len(processed_files)


def _default_item_count(root: Path, workflow: str, requested_items: int | None) -> int:
    if requested_items is not None:
        return max(0, requested_items)
    if workflow.startswith("literature"):
        return _selected_literature_count(root) or 20
    if workflow in {"analysis_report", "multi_method_report_bundle"}:
        return _report_input_count(root) or 1
    if workflow == "project_handoff":
        return len(list((root / "reports").glob("*.md"))) + len(list((root / "open-items").glob("*.yml")))
    return 1


def _credit_equivalent(*, uncached_input_tokens: int, cached_input_tokens: int, output_tokens: int) -> float:
    return (
        uncached_input_tokens / 1_000_000 * UNCACHED_INPUT_CREDITS_PER_MILLION
        + cached_input_tokens / 1_000_000 * CACHED_INPUT_CREDITS_PER_MILLION
        + output_tokens / 1_000_000 * OUTPUT_CREDITS_PER_MILLION
    )


def estimate_workflow(
    root: Path,
    *,
    workflow: WorkflowKind,
    requested_items: int | None = None,
    cached_fraction: float = 0.25,
    mode: Literal["brief", "standard", "full"] = "standard",
) -> dict[str, Any]:
    if workflow not in WORKFLOW_PROFILES:
        raise ValueError(f"Unsupported workflow estimate: {workflow}")
    profile = WORKFLOW_PROFILES[workflow]
    item_count = _default_item_count(root, workflow, requested_items)
    mode_factor = {"brief": 0.45, "standard": 1.0, "full": 1.8}[mode]
    total_input = int((profile["base_input_tokens"] + profile["per_item_input_tokens"] * item_count) * mode_factor)
    cached_fraction = max(0.0, min(0.9, cached_fraction))
    cached_input = int(total_input * cached_fraction)
    uncached_input = total_input - cached_input
    output_tokens = int(profile["output_tokens"] * mode_factor)
    credits = _credit_equivalent(
        uncached_input_tokens=uncached_input,
        cached_input_tokens=cached_input,
        output_tokens=output_tokens,
    )
    reminders_disabled = large_work_reminders_disabled(root)
    exceeds = credits > LARGE_WORK_THRESHOLD_CODEX_CREDITS
    return {
        "schema_version": "0.9.6",
        "estimate_type": "ea_workflow_scale_estimate",
        "workflow": workflow,
        "mode": mode,
        "item_count": item_count,
        "threshold_codex_credit_equivalent": LARGE_WORK_THRESHOLD_CODEX_CREDITS,
        "estimated_uncached_input_tokens": uncached_input,
        "estimated_cached_input_tokens": cached_input,
        "estimated_output_tokens": output_tokens,
        "estimated_codex_credit_equivalent": round(credits, 2),
        "exceeds_large_work_threshold": exceeds,
        "large_work_reminders_disabled": reminders_disabled,
        "requires_confirmation_before_run": exceeds and not reminders_disabled,
        "basis": (
            "v0.9.6 fixed threshold: 100 Codex-credit-equivalent, roughly 20% of a practical "
            "Plus/GPT-5.5 5-hour estimate; local estimate uses workflow profile, item count, "
            "mode, and prompt-cache assumption."
        ),
        "alternatives": [
            "Run brief mode first.",
            "Generate only status/outline manifests.",
            "Split by source batch, method, sample group, or report section.",
            "Continue the full run after explicit confirmation.",
        ],
    }


def large_work_gate(
    root: Path,
    *,
    workflow: WorkflowKind,
    requested_items: int | None = None,
    mode: Literal["brief", "standard", "full"] = "standard",
    confirmed: bool = False,
) -> dict[str, Any]:
    estimate = estimate_workflow(root, workflow=workflow, requested_items=requested_items, mode=mode)
    if estimate["requires_confirmation_before_run"] and not confirmed:
        return {
            "status": "needs_confirmation",
            "estimate": estimate,
            "message": "This workflow is estimated to be unusually large. Confirm before continuing or choose a smaller alternative.",
        }
    return {"status": "ok", "estimate": estimate}
