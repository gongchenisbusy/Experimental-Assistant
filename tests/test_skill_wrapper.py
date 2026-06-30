from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_ea_v0_1_skill_defaults_to_user_workflow() -> None:
    skill_doc = Path(".agents/skills/ea-v0-1/SKILL.md").read_text(encoding="utf-8")

    assert "Do not run the bundled public demo by default." in skill_doc
    assert "Default Codex Behavior" in skill_doc
    assert "Developer Demo Only" in skill_doc
    assert "Use `工作指南/test_cases/test-case-001/public/` only for explicit developer/demo validation." in skill_doc


def test_ea_v0_1_skill_public_demo_command_runs(tmp_path: Path) -> None:
    workspace = tmp_path / "public-demo"
    script = Path(".agents/skills/ea-v0-1/scripts/run_public_demo.py")

    result = subprocess.run(
        [sys.executable, str(script), "--workspace", str(workspace)],
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
