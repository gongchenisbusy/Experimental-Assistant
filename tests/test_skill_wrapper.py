from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_ea_v0_2_skill_defaults_to_public_user_workflow() -> None:
    skill_doc = Path("skills/ea-v0-2/SKILL.md").read_text(encoding="utf-8")

    assert "Do not assume developer-machine Zotero, browser, institution, cache, or test paths." in skill_doc
    assert "# Experimental Assistant (EA v0.9 RC)" in skill_doc
    assert "In new Codex threads, invoke this compatibility skill as `$ea-v0-2`." in skill_doc
    assert "ea codex install-skill" in skill_doc
    assert "ea install-check" in skill_doc
    assert "Default Workflow" in skill_doc
    assert "Install Check" in skill_doc
    assert "References" in skill_doc
    assert "tests/fixtures/public/" not in skill_doc


def test_ea_v0_2_skill_public_demo_command_runs(tmp_path: Path) -> None:
    workspace = tmp_path / "public-demo"
    script = Path("skills/ea-v0-2/scripts/run_public_demo.py")

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
    assert "/reports/" in summary["report_path"]
    assert "hidden_truth" not in result.stdout
    assert "下一步建议" not in report_path.read_text(encoding="utf-8")
