from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from ea.literature import (
    import_zotero_codex_batch_status,
    normalize_acquisition_handoff,
    reconcile_literature_acquisition,
)
from ea.projects import initialize_project
from ea.storage import read_yaml


FIXTURE = Path("tests/fixtures/v0_9_9/mock_zotero_five_target.yml")


def test_five_target_mock_covers_transactions_blockers_privacy_and_resume(
    tmp_path: Path,
) -> None:
    payload = read_yaml(FIXTURE)
    original = deepcopy(payload)
    first = normalize_acquisition_handoff(payload, updated_at="2026-07-16T10:00:00+08:00")

    assert payload == original
    assert first["summary"] == {
        "target_count": 5,
        "ready_count": 2,
        "acquired_count": 0,
        "cache_verified_count": 2,
        "blocked_count": 3,
    }
    assert first["transaction_counts"] == {
        "created": 2,
        "reused": 1,
        "rolled_back": 0,
        "partial": 1,
    }
    assert first["targets"][0]["zotero"]["attachment_verified"] is True
    assert first["targets"][2]["zotero"]["parent_key"] == "PARENT003"
    assert first["targets"][2]["zotero"]["attachment_key"] is None
    covered_codes = {
        attempt.get("error_code")
        for target in first["targets"]
        for attempt in target["attempts"]
    }
    assert {
        "http_401_unauthorized",
        "http_403_forbidden",
        "http_429_rate_limited",
        "timeout",
        "captcha_required",
        "permission_denied",
    } <= covered_codes
    serialized = json.dumps(first, ensure_ascii=False)
    assert "credential" not in serialized.lower()
    assert "secret" not in serialized.lower()
    assert first["privacy"]["session_ids"] == "omitted"

    resumed = deepcopy(payload)
    for index, target in enumerate(resumed["targets"], start=1):
        target.update(
            {
                "status": "cached",
                "zotero_parent_key": target.get("zotero_parent_key") or f"PARENT{index:03d}",
                "zotero_attachment_key": target.get("zotero_attachment_key") or f"ATTACH{index:03d}",
                "source_hash": chr(96 + index) * 64,
                "cache_path": f"knowledge/project/fulltext/{index:02d}/mock{index:03d}",
            }
        )
        target.pop("error", None)
        target.pop("reason", None)
    resumed["transaction_counts"] = {
        "created": 2,
        "reused": 4,
        "rolled_back": 0,
        "partial": 0,
    }
    final = normalize_acquisition_handoff(
        resumed, updated_at="2026-07-16T10:05:00+08:00"
    )

    assert final["status"] == "complete"
    assert final["summary"]["ready_count"] == 5
    assert final["current_task_blockers"] == []
    assert [item["doi"] for item in final["targets"]] == [
        item["doi"] for item in first["targets"]
    ]
    assert final["targets"][2]["zotero"]["parent_key"] == "PARENT003"
    assert len({item["zotero"]["parent_key"] for item in final["targets"]}) == 5
    assert len({item["cache"]["object_ref"] for item in final["targets"]}) == 5


def test_five_target_mock_import_and_reconciliation_are_local_and_repeatable(
    tmp_path: Path,
) -> None:
    initialize_project(
        tmp_path,
        project_name="v0.9.9 mock acquisition",
        project_slug="v0-9-9-mock-acquisition",
        research_direction="deterministic integration validation",
        material_system="public mock records",
        experiment_type="literature acquisition",
        enable_literature=False,
    )
    source = tmp_path / "literature" / "mock-status.json"
    source.write_text(json.dumps(read_yaml(FIXTURE)), encoding="utf-8")

    imported = import_zotero_codex_batch_status(
        tmp_path,
        batch_status_path=Path("literature/mock-status.json"),
        imported_at="2026-07-16T10:10:00+08:00",
    )
    first_state = read_yaml(tmp_path / "literature" / "external_acquisition_state.yml")
    reconciliation = reconcile_literature_acquisition(
        tmp_path, reconciled_at="2026-07-16T10:11:00+08:00"
    )["reconciliation"]
    imported_again = import_zotero_codex_batch_status(
        tmp_path,
        batch_status_path=Path("literature/mock-status.json"),
        imported_at="2026-07-16T10:10:00+08:00",
    )
    second_state = read_yaml(tmp_path / "literature" / "external_acquisition_state.yml")

    assert imported["status_update"]["status"] == "acquisition_partial_with_blockers"
    assert imported_again["status_update"]["status"] == "acquisition_partial_with_blockers"
    assert first_state == second_state
    assert reconciliation["summary"]["external_cache_used"] is True
    assert reconciliation["status"] != "fail"
