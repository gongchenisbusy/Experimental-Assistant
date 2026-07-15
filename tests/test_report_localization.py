from __future__ import annotations

import re
from pathlib import Path

import pytest

from ea.reports.service import _prepare_localized_report
from ea.schema import ReportRecord
from ea.storage.files import write_yaml


METHODS = (
    "raman_analysis",
    "pl_analysis",
    "xrd_analysis",
    "ftir_analysis",
    "uv_vis_analysis",
    "xps_analysis",
    "electrochemistry_analysis",
    "thermal_analysis",
)


@pytest.mark.parametrize("report_type", METHODS)
def test_all_method_reports_share_zh_en_semantic_contract(
    tmp_path: Path, report_type: str
) -> None:
    config_path = tmp_path / ".ea" / "project_config.yml"
    metadata = {
        "result_id": f"res-{report_type}",
        "x_unit": "cm^-1",
        "peak": {"position": 383.4, "confidence": "low", "evidence_refs": ["ref-001"]},
        "warnings": [
            {"code": "quality-review-required", "message": "Review required."}
        ],
    }
    report = ReportRecord(
        report_id=f"report-{report_type}",
        project_id="prj-localization",
        report_type=report_type,
        related_results=[f"res-{report_type}"],
        figure_ids=[f"fig-{report_type}"],
        status="draft",
        created_at="2026-07-15T10:00:00",
        updated_at="2026-07-15T10:00:00",
    )
    body = "# 报告\n\n- confidence: `low`；evidence peaks: `peak-1`；mode separation: `18.2 cm^-1`；assignment_source: `reviewed`.\n"
    reference_block = {
        "reference_ids": ["ref-001"],
        "references_markdown": "1. Example reference.",
    }

    write_yaml(config_path, {"default_report_language": "zh"})
    zh_language, zh_body, zh_semantic = _prepare_localized_report(
        tmp_path,
        report=report,
        body=body,
        metadata=metadata,
        outputs={"processed_csv": "processed/data.csv"},
        reference_block=reference_block,
    )
    write_yaml(config_path, {"default_report_language": "en"})
    en_language, en_body, en_semantic = _prepare_localized_report(
        tmp_path,
        report=report,
        body=body,
        metadata=metadata,
        outputs={"processed_csv": "processed/data.csv"},
        reference_block=reference_block,
    )

    assert zh_language == "zh"
    assert "confidence:" not in zh_body
    assert "evidence peaks:" not in zh_body
    assert "mode separation:" not in zh_body
    assert "assignment_source:" not in zh_body
    assert en_language == "en"
    assert not re.search(r"[\u4e00-\u9fff]", en_body)
    assert zh_semantic == en_semantic
    assert zh_semantic["confidence_enums"] == ["low"]
    assert zh_semantic["warning_codes"] == ["quality-review-required"]
    assert zh_semantic["reference_ids"] == ["ref-001"]
