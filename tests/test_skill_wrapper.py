from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml


def test_ea_skill_defaults_to_public_user_workflow() -> None:
    skill_doc = Path("skills/ea/SKILL.md").read_text(encoding="utf-8")

    assert (
        "without assuming developer-machine accounts, paths, or credentials"
        in skill_doc
    )
    assert "# Experimental Assistant v0.9.8" in skill_doc
    assert "$ea-v0-2` only as a temporary compatibility entry point" in skill_doc
    assert "ea start" in skill_doc
    assert "ea status" in skill_doc
    assert "Core Workflow" in skill_doc
    assert "references/routing-index.yml" in skill_doc
    assert "需要你补充：" in skill_doc
    assert "ea-feedback" in skill_doc
    assert (
        "Do not install it, collect diagnostics, or submit feedback without confirmation"
        in skill_doc
    )
    assert "tests/fixtures/public/" not in skill_doc

    routing_index = yaml.safe_load(
        Path("skills/ea/references/routing-index.yml").read_text(encoding="utf-8")
    )
    assert routing_index["schema_version"] == "0.9.8"
    assert "method_analysis" in routing_index["routes"]
    assert (
        routing_index["routes"]["method_analysis"]["choose_one_method_ref"]["xps"]
        == "references/xps-workflow.md"
    )
    assert (
        "ea trace focus"
        in routing_index["routes"]["traceability"]["preferred_commands"]
    )


def test_ea_v0_2_is_a_thin_compatibility_wrapper() -> None:
    wrapper = Path("skills/ea-v0-2/SKILL.md").read_text(encoding="utf-8")

    assert "temporary compatibility invocation" in wrapper
    assert "sibling `ea/SKILL.md`" in wrapper
    assert "stable public invocation is `$ea`" in wrapper
    assert "v1.0.x release line" in wrapper
    assert "references/raman-workflow.md" not in wrapper
    assert len(wrapper.encode("utf-8")) < 1500


def test_ea_skill_public_demo_command_runs(tmp_path: Path) -> None:
    workspace = tmp_path / "public-demo"
    script = Path("skills/ea/scripts/run_public_demo.py")

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--workspace",
            str(workspace),
            "--fixture-root",
            "tests/fixtures/public/test-case-001",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    summary = json.loads(result.stdout)

    report_path = Path(summary["report_path"])
    figure_path = Path(summary["figure_path"])
    processed_csv_path = Path(summary["processed_csv_path"])
    peak_table_path = Path(summary["peak_table_path"])

    assert report_path.exists()
    assert figure_path.exists()
    assert processed_csv_path.exists()
    assert peak_table_path.exists()
    assert "/reports/" in report_path.as_posix()
    assert "hidden_truth" not in result.stdout
    assert "下一步建议" not in report_path.read_text(encoding="utf-8")
