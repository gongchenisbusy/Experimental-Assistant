from __future__ import annotations

import re
from pathlib import Path

import pytest

from ea.reports.service import (
    _electrochemistry_interpretation_text,
    _ftir_interpretation_text,
    _interpretation_text,
    _localized_dynamic_interpretation,
    _pl_interpretation_text,
    _prepare_localized_report,
    _thermal_interpretation_text,
    _uv_vis_interpretation_text,
    _xps_interpretation_text,
    _xrd_interpretation_text,
    lint_report_locale,
)
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
    assert zh_semantic["locale_lint"] == {"status": "pass", "violations": []}


@pytest.mark.parametrize(
    ("method", "renderer"),
    [
        ("raman", _interpretation_text),
        ("pl", _pl_interpretation_text),
        ("xrd", _xrd_interpretation_text),
        ("ftir", _ftir_interpretation_text),
        ("uv_vis", _uv_vis_interpretation_text),
        ("xps", _xps_interpretation_text),
        ("electrochemistry", _electrochemistry_interpretation_text),
        ("thermal", _thermal_interpretation_text),
    ],
)
def test_all_methods_degrade_unkeyed_english_dynamic_text_without_leak(
    method: str, renderer
) -> None:
    metadata = {
        "peak_analysis": {
            "possible_interpretations": [
                {
                    "text": "This deliberately unknown generated interpretation remains an English sentence that must not leak into a Chinese report.",
                    "confidence": "low",
                    "evidence": ["evidence-001"],
                }
            ]
        }
    }
    rendered = renderer(metadata, "[1]")
    assert "deliberately unknown" not in rendered
    assert "候选解释" in rendered
    assert "evidence-001" in rendered
    assert method


def test_stable_message_key_renders_both_locales_and_locale_lint_flags_raw_leak() -> None:
    item = {
        "message_key": "raman.mos2_pair_thin_layer",
        "message_args": {"separation": 19.76},
        "confidence": "medium",
        "evidence": ["peak-005", "peak-006"],
        "mode_separation_cm-1": 19.76,
    }
    zh = _localized_dynamic_interpretation(item, "raman", language="zh")
    en = _localized_dynamic_interpretation(item, "raman", language="en")
    assert "19.76 cm^-1" in zh
    assert "薄层" in zh
    assert "19.76 cm^-1" in en
    assert "thin-layer" in en

    lint = lint_report_locale(
        "# 报告\n\n## 可能结论与可信度\n\nThis unknown generated sentence must be localized before release.\n",
        "zh",
    )
    assert lint["status"] == "fail"
    assert lint["violations"][0]["code"] == "unlocalized_dynamic_sentence"
