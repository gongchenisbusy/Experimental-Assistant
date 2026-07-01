from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from ea.cli import main
from ea.ftir import default_ftir_processing_parameters, inspect_ftir_file
from ea.storage import read_markdown_record, read_yaml


def _json_output(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def _write_ftir_fixture(path: Path) -> Path:
    lines = [
        "# x_unit = cm^-1",
        "# y_label = absorbance",
        "wavenumber absorbance",
    ]
    for index in range(1800):
        wavenumber = 4000.0 - index * 2.0
        baseline = 0.025 + 0.00001 * (4000.0 - wavenumber)
        signal = baseline
        for center, amplitude, width in [
            (3400.0, 0.32, 55.0),
            (2920.0, 0.22, 35.0),
            (1720.0, 0.28, 28.0),
            (1100.0, 0.36, 45.0),
        ]:
            signal += amplitude * math.exp(-((wavenumber - center) ** 2) / (2.0 * width**2))
        lines.append(f"{wavenumber:.2f} {signal:.8f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_inspect_synthetic_ftir_fixture(tmp_path: Path) -> None:
    fixture = _write_ftir_fixture(tmp_path / "synthetic-ftir-spectrum.txt")

    inspection = inspect_ftir_file(fixture)

    assert inspection.file_kind == "ftir"
    assert inspection.row_count == 1800
    assert inspection.x_column_candidate == "wavenumber"
    assert inspection.y_column_candidate == "absorbance"
    assert inspection.x_unit == "cm^-1"
    assert inspection.signal_mode_candidate == "absorbance"
    assert inspection.requires_user_confirmation is True


def test_cli_runs_synthetic_ftir_workflow_end_to_end(tmp_path: Path, capsys) -> None:
    fixture = _write_ftir_fixture(tmp_path / "synthetic-ftir-spectrum.txt")
    workspace = tmp_path / "cli-ftir-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "CLI FTIR Workflow",
            "--slug",
            "cli-ftir-workflow",
            "--direction",
            "FTIR workflow",
            "--material",
            "polymer composite",
            "--experiment-type",
            "materials FTIR characterization",
        ]
    ) == 0
    project = _json_output(capsys)
    project_frontmatter, _ = read_markdown_record(Path(project["project"]))
    project_id = project_frontmatter["project_id"]

    assert main(
        [
            "raw",
            "import",
            str(workspace),
            str(fixture),
            "--characterization-type",
            "ftir",
            "--sample-ref",
            "sample-ftir-001",
            "--experiment-ref",
            "exp-ftir-001",
        ]
    ) == 0
    raw_output = _json_output(capsys)
    raw_metadata = Path(raw_output["metadata"])
    raw_metadata_ref = raw_metadata.relative_to(workspace).as_posix()

    assert raw_output["import_status"] == "imported"
    assert main(["ftir", "inspect", str(workspace), raw_output["project_raw_path"]]) == 0
    inspection = _json_output(capsys)
    assert inspection["file_kind"] == "ftir"
    assert inspection["x_unit"] == "cm^-1"
    assert inspection["signal_mode_candidate"] == "absorbance"

    assert main(
        [
            "review",
            "add",
            str(workspace),
            "--target-type",
            "ftir_columns",
            "--target-ref",
            raw_metadata_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            "x=wavenumber, y=absorbance, unit=cm^-1, signal_mode=absorbance",
        ]
    ) == 0
    column_review = _json_output(capsys)
    assert column_review["review_status"] == "user_confirmed"

    assert main(
        [
            "review",
            "add",
            str(workspace),
            "--target-type",
            "ftir_parameters",
            "--target-ref",
            raw_metadata_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            json.dumps(default_ftir_processing_parameters(), ensure_ascii=False),
        ]
    ) == 0
    parameter_review = _json_output(capsys)
    assert parameter_review["review_status"] == "user_confirmed"

    assert main(
        [
            "ftir",
            "process",
            str(workspace),
            "--metadata",
            raw_metadata_ref,
            "--project-id",
            project_id,
            "--sample-ref",
            "sample-ftir-001",
            "--x-column",
            "wavenumber",
            "--y-column",
            "absorbance",
            "--x-unit",
            "cm^-1",
            "--signal-mode",
            "absorbance",
            "--column-review-ref",
            column_review["review_id"],
            "--parameter-review-ref",
            parameter_review["review_id"],
        ]
    ) == 0
    process_output = _json_output(capsys)
    ftir_metadata = Path(process_output["metadata"])
    ftir = read_yaml(ftir_metadata)

    assert ftir["result_id"].startswith("res-cli-ftir-workflow-ftir-")
    assert ftir["ftir_result_id"] == ftir["result_id"]
    assert ftir["signal_mode"] == "absorbance"
    assert ftir["peak_analysis"]["band_count"] > 0
    assert ftir["peak_analysis"]["possible_interpretations"]
    assert any("builtin_band_windows" in item["assignment_source"] for item in ftir["peak_analysis"]["possible_interpretations"])
    assert (workspace / ftir["outputs"]["peak_table"]).exists()
    assert (workspace / ftir["outputs"]["figure"]).exists()
    figure_record = read_yaml(workspace / "figures" / "index.yml")["figures"][ftir["figure_id"]]
    assert figure_record["style_profile"] == "nature_like_clean"
    assert figure_record["generation"]["parameters"]["signal_mode"] == "absorbance"
    assert ftir["outputs"]["processed_csv"] in figure_record["source_data_refs"]
    assert ftir["outputs"]["peak_table"] in figure_record["source_data_refs"]

    assert main(
        [
            "ftir",
            "report",
            str(workspace),
            "--metadata",
            ftir_metadata.relative_to(workspace).as_posix(),
            "--project-id",
            project_id,
            "--sample-ref",
            "sample-ftir-001",
            "--experiment-ref",
            "exp-ftir-001",
        ]
    ) == 0
    report_output = _json_output(capsys)
    report_frontmatter, report_body = read_markdown_record(Path(report_output["report"]))
    assert report_frontmatter["report_type"] == "ftir_analysis"
    assert "## FTIR band 参数" in report_body
    assert "![FTIR spectrum]" in report_body
    assert "processed CSV" in report_body

    assert main(["healthcheck", str(workspace)]) == 0
    health = _json_output(capsys)
    assert health["status"] == "pass"

    assert main(["eval", "project", str(workspace), "--no-write"]) == 0
    evaluation = _json_output(capsys)
    assert evaluation["status"] == "pass"
    assert evaluation["figures"]["analysis_figure_count"] == 1
    assert evaluation["reports"]["report_count"] == 1


def test_ftir_context_record_preserves_reviewed_method_metadata(tmp_path: Path, capsys) -> None:
    fixture = _write_ftir_fixture(tmp_path / "synthetic-ftir-context-spectrum.txt")
    workspace = tmp_path / "ftir-context-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "FTIR Context Workflow",
            "--slug",
            "ftir-context-workflow",
            "--direction",
            "FTIR context records",
            "--material",
            "polymer composite film",
            "--experiment-type",
            "materials FTIR context record",
        ]
    ) == 0
    project = _json_output(capsys)
    project_frontmatter, _ = read_markdown_record(Path(project["project"]))
    project_id = project_frontmatter["project_id"]

    assert main(
        [
            "raw",
            "import",
            str(workspace),
            str(fixture),
            "--characterization-type",
            "ftir",
            "--sample-ref",
            "sample-ftir-context-001",
            "--experiment-ref",
            "exp-ftir-context-001",
        ]
    ) == 0
    raw_output = _json_output(capsys)
    raw_metadata_ref = Path(raw_output["metadata"]).relative_to(workspace).as_posix()

    assert main(
        [
            "review",
            "add",
            str(workspace),
            "--target-type",
            "ftir_columns",
            "--target-ref",
            raw_metadata_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            "x=wavenumber, y=absorbance, unit=cm^-1, signal_mode=absorbance",
        ]
    ) == 0
    column_review = _json_output(capsys)

    parameters = default_ftir_processing_parameters()
    parameters["context_record"].update(
        {
            "enabled": True,
            "instrument_accessory": {"instrument": "public-user FTIR", "accessory": "ATR", "crystal": "diamond", "status": "reviewed"},
            "atmosphere": {"purge": "dry_air", "co2_h2o_status": "background_reviewed"},
            "sample_preparation": {"sample_form": "thin_film", "contact_quality": "user_reviewed"},
            "background": {"background_ref": "fresh ATR background", "numeric_correction": "instrument_applied", "status": "reviewed"},
            "reference": {"reference_type": "project reference spectrum pending", "status": "not_applied"},
            "correction_notes": ["EA records context only; no automatic FTIR correction was applied."],
        }
    )
    assert main(
        [
            "review",
            "add",
            str(workspace),
            "--target-type",
            "ftir_parameters",
            "--target-ref",
            raw_metadata_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            json.dumps(parameters, ensure_ascii=False),
        ]
    ) == 0
    parameter_review = _json_output(capsys)

    assert main(
        [
            "ftir",
            "process",
            str(workspace),
            "--metadata",
            raw_metadata_ref,
            "--project-id",
            project_id,
            "--sample-ref",
            "sample-ftir-context-001",
            "--x-column",
            "wavenumber",
            "--y-column",
            "absorbance",
            "--x-unit",
            "cm^-1",
            "--signal-mode",
            "absorbance",
            "--parameters-json",
            json.dumps({"context_record": parameters["context_record"]}, ensure_ascii=False),
            "--column-review-ref",
            column_review["review_id"],
            "--parameter-review-ref",
            parameter_review["review_id"],
        ]
    ) == 0
    process_output = _json_output(capsys)
    ftir_metadata = Path(process_output["metadata"])
    ftir = read_yaml(ftir_metadata)
    context_record = ftir["peak_analysis"]["context_record"]

    assert context_record["status"] == "reviewed_context_recorded"
    assert context_record["confidence"] == "low"
    assert "instrument_accessory" in context_record["reviewed_context_fields"]
    assert context_record["instrument_accessory"]["accessory"] == "ATR"
    assert "metadata/provenance only" in context_record["boundary"]
    assert ftir["outputs"]["context_record"].endswith("ftir_context.yml")
    saved_context = read_yaml(workspace / ftir["outputs"]["context_record"])
    assert saved_context["background"]["background_ref"] == "fresh ATR background"
    assert saved_context["record_ref"] == ftir["outputs"]["context_record"]

    figure_record = read_yaml(workspace / "figures" / "index.yml")["figures"][ftir["figure_id"]]
    assert ftir["outputs"]["context_record"] in figure_record["source_data_refs"]

    assert main(
        [
            "ftir",
            "report",
            str(workspace),
            "--metadata",
            ftir_metadata.relative_to(workspace).as_posix(),
            "--project-id",
            project_id,
            "--sample-ref",
            "sample-ftir-context-001",
            "--experiment-ref",
            "exp-ftir-context-001",
        ]
    ) == 0
    report_output = _json_output(capsys)
    _, report_body = read_markdown_record(Path(report_output["report"]))
    assert "## FTIR context record" in report_body
    assert "ATR" in report_body
    assert "context record" in report_body
    assert "不执行自动背景/参比数值校正" in report_body


def test_cli_builds_ftir_assignment_source_packet_and_suggestions(tmp_path: Path, capsys) -> None:
    fixture = _write_ftir_fixture(tmp_path / "synthetic-ftir-assignment-spectrum.txt")
    workspace = tmp_path / "ftir-assignment-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "FTIR Assignment Workflow",
            "--slug",
            "ftir-assignment-workflow",
            "--direction",
            "FTIR source-backed assignment records",
            "--material",
            "polymer composite film",
            "--experiment-type",
            "materials FTIR characterization",
        ]
    ) == 0
    project = _json_output(capsys)
    project_frontmatter, _ = read_markdown_record(Path(project["project"]))
    project_id = project_frontmatter["project_id"]

    assert main(
        [
            "raw",
            "import",
            str(workspace),
            str(fixture),
            "--characterization-type",
            "ftir",
            "--sample-ref",
            "sample-ftir-assignment-001",
            "--experiment-ref",
            "exp-ftir-assignment-001",
        ]
    ) == 0
    raw_output = _json_output(capsys)
    raw_metadata_ref = Path(raw_output["metadata"]).relative_to(workspace).as_posix()

    assert main(
        [
            "review",
            "add",
            str(workspace),
            "--target-type",
            "ftir_columns",
            "--target-ref",
            raw_metadata_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            "x=wavenumber, y=absorbance, unit=cm^-1, signal_mode=absorbance",
        ]
    ) == 0
    column_review = _json_output(capsys)
    assert main(
        [
            "review",
            "add",
            str(workspace),
            "--target-type",
            "ftir_parameters",
            "--target-ref",
            raw_metadata_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            json.dumps(default_ftir_processing_parameters(), ensure_ascii=False),
        ]
    ) == 0
    parameter_review = _json_output(capsys)

    assert main(
        [
            "ftir",
            "process",
            str(workspace),
            "--metadata",
            raw_metadata_ref,
            "--project-id",
            project_id,
            "--sample-ref",
            "sample-ftir-assignment-001",
            "--x-column",
            "wavenumber",
            "--y-column",
            "absorbance",
            "--x-unit",
            "cm^-1",
            "--signal-mode",
            "absorbance",
            "--column-review-ref",
            column_review["review_id"],
            "--parameter-review-ref",
            parameter_review["review_id"],
        ]
    ) == 0
    process_output = _json_output(capsys)
    ftir_metadata_ref = Path(process_output["metadata"]).relative_to(workspace).as_posix()

    assert main(
        [
            "references",
            "add",
            str(workspace),
            "--project-id",
            project_id,
            "--citation",
            "Example FTIR reference spectrum note.",
            "--title",
            "Example FTIR reference spectrum",
            "--year",
            "2026",
            "--url",
            "https://example.org/ftir-reference",
        ]
    ) == 0
    reference_output = _json_output(capsys)
    reference_id = Path(reference_output["reference"]).stem

    library = workspace / "project_ftir_assignment_library.yml"
    library.write_text(
        f"""
candidates:
  - candidate_id: ftir-assignment-carbonyl-001
    assignment_type: functional_group
    assignment_label: ester/carbonyl C=O stretching
    band_label: carbonyl stretching band
    material_scope: polymer composite film
    sample_scope: reviewed synthetic fixture
    wavenumber_window_cm1: [1700, 1745]
    expected_feature: absorbance_maximum
    source_summary: Example reference spectrum reports a carbonyl stretching band in this region.
    applicability_notes:
      - Applies only when project chemistry supports oxygen-containing organic groups.
    reference_ids:
      - {reference_id}
    confidence: medium
    caveats:
      - Band overlap requires review before durable interpretation.
  - candidate_id: ftir-assignment-ch-001
    assignment_type: functional_group
    assignment_label: aliphatic C-H stretching
    band_label: C-H stretching band
    material_scope: polymer composite film
    sample_scope: reviewed synthetic fixture
    wavenumber_window_cm1: [2860, 2960]
    expected_feature: absorbance_maximum
    source_summary: Example reference spectrum reports aliphatic C-H stretching in this region.
    applicability_notes:
      - Review organic residues, ligands, or binders before interpretation.
    reference_ids:
      - ref-missing-ftir-001
    confidence: low
    caveats:
      - Missing project reference should block report use until registered.
  - candidate_id: ftir-assignment-no-match-001
    assignment_type: functional_group
    assignment_label: nitrile C=N or C≡N candidate
    band_label: high-frequency triple-bond candidate
    material_scope: polymer composite film
    sample_scope: reviewed synthetic fixture
    wavenumber_window_cm1: [2100, 2150]
    expected_feature: absorbance_maximum
    source_summary: Example source records this as a possible triple-bond region.
    applicability_notes:
      - Use only if detected bands and chemistry support it.
    reference_ids:
      - {reference_id}
    confidence: low
    caveats:
      - Included to verify no-feature-match behavior.
""".strip()
        + "\n",
        encoding="utf-8",
    )

    assert main(
        [
            "ftir",
            "build-assignment-packet",
            str(workspace),
            "--project-id",
            project_id,
            "--library-file",
            library.relative_to(workspace).as_posix(),
            "--material-scope",
            "polymer",
        ]
    ) == 0
    packet_output = _json_output(capsys)
    assert packet_output["status"] == "ready_for_suggest_assignments"
    assert packet_output["candidate_count"] == 3
    packet = read_yaml(Path(packet_output["source_packet"]))
    assert packet["source"] == "ea.ftir.assignment_source_packet:v0.2"
    assert packet["source_library_ref"] == library.relative_to(workspace).as_posix()
    assert "suggest-assignments" in " ".join(packet["next_steps"])
    assert "does not run live lookup" in " ".join(packet["boundaries"])

    packet_ref = Path(packet_output["source_packet"]).relative_to(workspace).as_posix()
    assert main(
        [
            "ftir",
            "suggest-assignments",
            str(workspace),
            "--project-id",
            project_id,
            "--metadata",
            ftir_metadata_ref,
            "--source-file",
            packet_ref,
            "--related-record",
            ftir_metadata_ref,
        ]
    ) == 0
    suggestion_output = _json_output(capsys)
    assert suggestion_output["status"] == "ready_for_user_review"
    assert suggestion_output["ready_for_user_review_count"] == 1
    assert suggestion_output["needs_reference_registration_count"] == 1
    assert suggestion_output["no_feature_match_count"] == 1

    record = read_yaml(Path(suggestion_output["record"]))
    table = pd.read_csv(Path(suggestion_output["table"]))
    assert record["source"] == "ea.ftir.assignment_suggestions:v0.2"
    assert record["candidates"][0]["status"] == "ready_for_user_review"
    assert record["candidates"][0]["matched_band_ids"]
    assert record["candidates"][0]["auto_applied"] is False
    assert record["candidates"][1]["status"] == "needs_reference_registration"
    assert "ref-missing-ftir-001" in record["candidates"][1]["unresolved_reference_ids"]
    assert record["candidates"][2]["status"] == "no_feature_match"
    assert "composition proof" in " ".join(record["next_steps"])
    assert "does not run live lookup" in " ".join(record["boundaries"])
    assert (workspace / record["provenance_ref"]).exists()
    assert set(table["status"]) == {"ready_for_user_review", "needs_reference_registration", "no_feature_match"}

    assert main(
        [
            "ftir",
            "report",
            str(workspace),
            "--metadata",
            ftir_metadata_ref,
            "--project-id",
            project_id,
            "--sample-ref",
            "sample-ftir-assignment-001",
            "--experiment-ref",
            "exp-ftir-assignment-001",
            "--assignment-suggestion",
            Path(suggestion_output["record"]).relative_to(workspace).as_posix(),
        ]
    ) == 0
    report_output = _json_output(capsys)
    report_frontmatter, report_body = read_markdown_record(Path(report_output["report"]))
    assert reference_id in report_frontmatter["reference_ids"]
    assert "ref-missing-ftir-001" not in report_frontmatter["reference_ids"]
    assert "## Source-backed FTIR assignment suggestions" in report_body
    assert "ester/carbonyl C=O stretching[1]" in report_body
    assert "ready_for_user_review" in report_body
    assert "needs_reference_registration" in report_body
    assert "ref-missing-ftir-001" in report_body
    assert "no_feature_match" in report_body
    assert "不能单独证明化学组成" in report_body
    assert "Example FTIR reference spectrum note." in report_body

    assert main(["ftir", "build-assignment-packet", str(workspace), "--project-id", project_id, "--write-template"]) == 0
    template_output = _json_output(capsys)
    template = read_yaml(Path(template_output["source_packet"]))
    assert template["status"] == "template_requires_user_edit"
    assert (workspace / "templates" / "ftir_assignment_source_packet.yml").exists()


def test_cli_builds_builtin_ftir_assignment_source_packet(tmp_path: Path, capsys) -> None:
    workspace = tmp_path / "ftir-builtin-library-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "FTIR Builtin Library Workflow",
            "--slug",
            "ftir-builtin-library-workflow",
            "--direction",
            "FTIR built-in assignment source packet",
            "--material",
            "polymer oxide composite",
            "--experiment-type",
            "materials FTIR characterization",
        ]
    ) == 0
    project = _json_output(capsys)
    project_frontmatter, _ = read_markdown_record(Path(project["project"]))
    project_id = project_frontmatter["project_id"]

    assert main(["ftir", "build-assignment-packet", str(workspace), "--project-id", project_id]) == 0
    packet_output = _json_output(capsys)
    packet = read_yaml(Path(packet_output["source_packet"]))
    assert packet_output["status"] == "ready_for_suggest_assignments"
    assert packet_output["candidate_count"] >= 8
    assert packet_output["reference_seed_count"] == 2
    assert packet["source_library_kind"] == "built_in"
    assert packet["source_library_ref"] == "builtin:generic_materials"
    assert "builtin-ftir-socrates-2001" in packet["reference_seeds"]
    assert "builtin-ftir-colthup-1990" in packet["reference_seeds"]
    assert "builtin-ftir-socrates-2001" in packet["reference_ids"]
    assert any(candidate["candidate_id"] == "ftir-builtin-carbonyl-co-stretching-generic" for candidate in packet["candidates"])
    assert "built-in reference_seeds" in " ".join(packet["next_steps"])
    assert "does not run live lookup" in " ".join(packet["boundaries"])
    assert (workspace / packet["provenance_ref"]).exists()

    assert (
        main(
            [
                "ftir",
                "build-assignment-packet",
                str(workspace),
                "--project-id",
                project_id,
                "--builtin-library",
                "generic_materials",
                "--include-candidate",
                "ftir-builtin-carbonyl-co-stretching-generic",
                "--material-scope",
                "polymer",
            ]
        )
        == 0
    )
    filtered_output = _json_output(capsys)
    filtered_packet = read_yaml(Path(filtered_output["source_packet"]))
    assert filtered_output["candidate_count"] == 1
    assert filtered_packet["candidates"][0]["candidate_id"] == "ftir-builtin-carbonyl-co-stretching-generic"
    assert filtered_packet["filters"]["material_scopes"] == ["polymer"]


def test_ftir_docs_and_skill_references_are_discoverable() -> None:
    root = Path.cwd()

    readme = (root / "README.md").read_text(encoding="utf-8")
    skill = (root / "skills" / "ea-v0-2" / "SKILL.md").read_text(encoding="utf-8")
    ftir_reference = root / "skills" / "ea-v0-2" / "references" / "ftir-workflow.md"
    registry = read_yaml(root / "skill-registry" / "index.yml")

    assert "ea ftir inspect" in readme
    assert "ea ftir process" in skill
    assert "ea ftir suggest-assignments" in skill
    assert "--assignment-suggestion" in skill
    assert "--builtin-library" in skill
    assert "register-seeds" in skill
    assert "references/ftir-workflow.md" in skill
    assert ftir_reference.exists()
    reference_text = ftir_reference.read_text(encoding="utf-8")
    assert "signal_mode" in reference_text
    assert "context_record" in reference_text
    assert "build-assignment-packet" in reference_text
    assert "suggest-assignments" in reference_text
    assert "--assignment-suggestion" in reference_text
    assert "generic_materials" in reference_text
    assert "register-seeds" in reference_text
    ftir_record = next(item for item in registry["skills"] if item["id"] == "ea.ftir-analysis")
    assert "Minimal FTIR workflow implemented" in ftir_record["notes"]
    assert "context_records" in ftir_record["notes"]
    assert "assignment_suggestions" in ftir_record["notes"]
    assert "built_in_assignment_library" in ftir_record["notes"]
    assert "reference_seed registration" in ftir_record["notes"]
