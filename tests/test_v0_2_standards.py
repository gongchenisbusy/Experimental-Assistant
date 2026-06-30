from __future__ import annotations

import json
from pathlib import Path

from ea.cli import main
from ea.config import doctor_project_config
from ea.figures import figure_footer, lookup_figure, register_figure
from ea.literature import ensure_literature_status, recommended_top_n
from ea.projects import initialize_project
from ea.skills import validate_skill_manifest
from ea.standards import format_standard_id, standard_project_id
from ea.storage import read_markdown_record, read_yaml


def test_v0_2_public_project_init_writes_portable_config(tmp_path: Path) -> None:
    outputs = initialize_project(
        tmp_path,
        project_name="MoS2 public project",
        project_slug="mos2-public",
        research_direction="single-layer MoS2",
        material_system="MoS2",
        experiment_type="CVD and Raman",
        enable_literature=True,
        default_language="en",
    )

    frontmatter, _ = read_markdown_record(outputs["project"])
    config = read_yaml(outputs["config"])

    assert frontmatter["project_id"] == "prj-mos2-public"
    assert frontmatter["project_slug"] == "mos2-public"
    assert frontmatter["default_language"] == "en"
    assert config["public_initialization"]["uses_developer_machine_defaults"] is False
    assert config["zotero"]["enabled"] is False
    assert config["browser_assist"]["enabled"] is False
    assert "/Users/geecoe" not in json.dumps(config, ensure_ascii=False)
    assert doctor_project_config(tmp_path)["status"] == "pass"
    assert outputs["literature_status"].exists()


def test_v0_2_standard_ids_and_figure_index(tmp_path: Path) -> None:
    assert standard_project_id("LM MoS2") == "prj-lm-mos2"
    assert (
        format_standard_id("raw", "lm-mos2", day="2026-06-30", sequence=14, hash8="a1b2c3d4")
        == "raw-lm-mos2-20260630-014-a1b2c3d4"
    )
    figure_id = format_standard_id("figure", "lm-mos2", method="raman", day="2026-06-30", sequence=3)
    report_id = format_standard_id("report", "lm-mos2", day="2026-06-30", sequence=1)
    assert figure_footer(figure_id, report_id) == (
        "FigID: fig-lm-mos2-raman-20260630-003 | Report: rpt-lm-mos2-20260630-001"
    )

    register_figure(
        tmp_path,
        figure_id=figure_id,
        path="figures/fig-lm-mos2-raman-20260630-003.png",
        report_id=report_id,
        result_id="res-lm-mos2-raman-20260630-001",
        raw_data_ids=["raw-lm-mos2-20260630-014-a1b2c3d4"],
        sample_ids=["s12"],
        experiment_ids=["exp-20260630-001"],
        generation={"script": "src/ea/raman/service.py"},
        caption="Raman spectrum.",
        purpose="analysis_report",
    )
    record = lookup_figure(tmp_path, figure_id)

    assert record["report_id"] == report_id
    assert record["raw_data_ids"] == ["raw-lm-mos2-20260630-014-a1b2c3d4"]
    assert record["sample_ids"] == ["s12"]


def test_v0_2_literature_defaults_and_status(tmp_path: Path) -> None:
    assert recommended_top_n("narrow") == 30
    assert recommended_top_n("ordinary") == 50
    assert recommended_top_n("review") == (100, 200)

    path = ensure_literature_status(tmp_path, project_id="prj-lm-mos2", scope="ordinary")
    status = read_yaml(path)

    assert status["recommended_top_n"] == 50
    assert status["status"] == "not_started"
    assert status["selected_top_n"] is None
    assert "Ask the user before bulk search" in status["summary_for_origin_thread"]


def test_v0_2_add_skills_manifest_validation(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.yml"
    manifest.write_text(
        """
ea_skill:
  id: ea.raman-analysis
  version: 0.2.0
  category: characterization.spectrum
  input_artifacts: [raw_spectrum, sample_context, project_context]
  output_artifacts: [processed_result, figure_record, report_section, provenance_record, memory_candidate]
  review_gates: [confirm_method, confirm_processing_parameters, confirm_interpretation_before_memory_write]
  required_indices: [raw/index.yml, reports/index.yml, figures/index.yml, provenance/index.yml]
""".strip(),
        encoding="utf-8",
    )
    bad_manifest = tmp_path / "bad.yml"
    bad_manifest.write_text(
        """
ea_skill:
  id: ea.unsafe-analysis
  version: 0.1.0
  category: characterization
  input_artifacts: [raw_spectrum]
  output_artifacts: [processed_result]
  review_gates: []
  required_indices: []
""".strip(),
        encoding="utf-8",
    )

    assert validate_skill_manifest(manifest).ok is True
    bad = validate_skill_manifest(bad_manifest)
    assert bad.ok is False
    assert "missing_output:figure_record" in bad.errors
    assert "missing_output:provenance_record" in bad.errors


def test_v0_2_builtin_raman_manifest_is_valid() -> None:
    result = validate_skill_manifest(Path("skill-registry/builtins/raman-analysis.yml"))

    assert result.ok is True
    assert result.manifest["id"] == "ea.raman-analysis"
    assert "confirm_interpretation_before_memory_write" in result.manifest["review_gates"]


def test_v0_2_cli_public_init_and_doctor(tmp_path: Path, capsys) -> None:
    workspace = tmp_path / "cli-v02"
    result = main(
        [
            "init-project",
            str(workspace),
            "--name",
            "CLI v02",
            "--slug",
            "cli-v02",
            "--direction",
            "Raman workflow",
            "--material",
            "MoS2",
            "--experiment-type",
            "CVD",
            "--enable-literature",
        ]
    )
    assert result == 0
    out = json.loads(capsys.readouterr().out)
    assert out["config"].endswith(".ea/project_config.yml")

    assert main(["config", "doctor", str(workspace)]) == 0
    doctor = json.loads(capsys.readouterr().out)
    assert doctor["status"] == "pass"
