from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from ea.cli import main
from ea.ftir import default_ftir_processing_parameters, inspect_ftir_file, summarize_ftir_assignment_libraries
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
    assert "does not perform unconfirmed live lookup" in " ".join(packet["boundaries"])
    assert "EA may use those sources to prepare assignment candidates" in " ".join(packet["boundaries"])

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
    assert "does not perform unconfirmed live lookup" in " ".join(record["boundaries"])
    assert "EA may prepare source packets" in " ".join(record["boundaries"])
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

    suggestion_ref = Path(suggestion_output["record"]).relative_to(workspace).as_posix()
    review_count_before_package = len(list((workspace / "reviews").glob("*.yml")))
    assert main(["ftir", "prepare-review", str(workspace), "--project-id", project_id, "--suggestion", suggestion_ref]) == 0
    review_package_output = _json_output(capsys)
    assert review_package_output["status"] == "review_package_prepared"
    assert review_package_output["selected_candidate_count"] == 3
    assert review_package_output["selected_status_counts"]["ready_for_user_review"] == 1
    assert review_package_output["selected_status_counts"]["needs_reference_registration"] == 1
    assert review_package_output["selected_status_counts"]["no_feature_match"] == 1
    assert len(list((workspace / "reviews").glob("*.yml"))) == review_count_before_package

    review_package = read_yaml(Path(review_package_output["review_package"]))
    review_package_markdown = Path(review_package_output["review_package_markdown"]).read_text(encoding="utf-8")
    assert review_package["source"] == "ea.ftir.assignment_review_package:v0.2"
    assert review_package["review_target_type"] == "ftir_assignment_suggestions"
    assert review_package["review_target_ref"] == suggestion_ref
    assert review_package["groups"][0]["group"] == "ready_for_user_review"
    assert "ftir-assignment-carbonyl-001" in review_package["groups"][0]["candidate_ids"]
    assert "ref-missing-ftir-001" in review_package["unresolved_reference_ids"]
    assert "ea review add /path/to/ea-project" in review_package["recommended_commands"]["create_review_record"]
    assert "ea ftir propose-memory" in review_package["recommended_commands"]["propose_memory_after_review"]
    assert "does not create a ReviewRecord" in " ".join(review_package["boundaries"])
    assert "FTIR Assignment Suggestion Review Package" in review_package_markdown
    assert "ester/carbonyl C=O stretching" in review_package_markdown
    assert "does not apply FTIR assignments" in review_package_markdown

    assert main(
        [
            "review",
            "add",
            str(workspace),
            "--target-type",
            "ftir_assignment_suggestions",
            "--target-ref",
            suggestion_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            "用户确认 carbonyl candidate 可作为后续讨论的 FTIR source-backed 解释候选。",
        ]
    ) == 0
    suggestion_review = _json_output(capsys)

    assert main(
        [
            "ftir",
            "propose-memory",
            str(workspace),
            "--project-id",
            project_id,
            "--suggestion",
            suggestion_ref,
            "--review-ref",
            suggestion_review["review_id"],
        ]
    ) == 0
    memory_output = _json_output(capsys)
    assert memory_output["status"] == "memory_candidates_proposed"
    assert memory_output["proposed_count"] == 1
    assert memory_output["skipped_count"] == 2
    assert memory_output["provenance_ref"]
    assert "does not commit confirmed memory" in " ".join(memory_output["boundaries"])
    skipped_reasons = {item["candidate_id"]: item["details"] for item in memory_output["skipped"] if item["reason"] == "not_memory_candidate_eligible"}
    assert "unresolved_reference_ids" in skipped_reasons["ftir-assignment-ch-001"]
    assert "status:no_feature_match" in skipped_reasons["ftir-assignment-no-match-001"]

    memory_candidate_path = Path(memory_output["memory_candidates"][0]["memory_candidate"])
    memory_frontmatter, memory_body = read_markdown_record(memory_candidate_path)
    assert memory_frontmatter["status"] == "draft"
    assert memory_frontmatter["category"] == "interpretation"
    assert memory_frontmatter["confidence"] == "medium"
    assert suggestion_ref in memory_frontmatter["source_refs"]
    assert record["table_ref"] in memory_frontmatter["source_refs"]
    assert reference_id in memory_frontmatter["source_refs"]
    assert record["provenance_ref"] in memory_frontmatter["provenance_refs"]
    assert memory_frontmatter["review_refs"] == []
    assert "ftir-assignment-carbonyl-001" in memory_body
    assert "ester/carbonyl C=O stretching" in memory_body
    assert reference_id in memory_body
    assert "does not by itself prove chemical composition" in memory_body
    candidate_index = read_yaml(workspace / "memory" / "candidates" / "index.yml")
    assert memory_frontmatter["memory_candidate_id"] in candidate_index["candidates"]

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
    assert packet_output["candidate_count"] >= 18
    assert packet_output["reference_seed_count"] >= 5
    assert packet["source_library_kind"] == "built_in"
    assert packet["source_library_ref"] == "builtin:generic_materials"
    assert "builtin-ftir-socrates-2001" in packet["reference_seeds"]
    assert "builtin-ftir-colthup-1990" in packet["reference_seeds"]
    assert "builtin-ftir-farmer-1974" in packet["reference_seeds"]
    assert "builtin-ftir-nakamoto-2009" in packet["reference_seeds"]
    assert "builtin-ftir-socrates-2001" in packet["reference_ids"]
    candidate_ids = {candidate["candidate_id"] for candidate in packet["candidates"]}
    assert "ftir-builtin-carbonyl-co-stretching-generic" in candidate_ids
    assert "ftir-builtin-carbonate-asymmetric-stretch-generic" in candidate_ids
    assert "ftir-builtin-phosphate-stretching-generic" in candidate_ids
    assert "ftir-builtin-sulfate-stretching-generic" in candidate_ids
    assert "ftir-builtin-water-bending-adsorbate-generic" in candidate_ids
    carbonate = next(candidate for candidate in packet["candidates"] if candidate["candidate_id"] == "ftir-builtin-carbonate-asymmetric-stretch-generic")
    assert "air exposure" in " ".join(carbonate["applicability_notes"]).lower()
    assert "carbonate phase" in " ".join(carbonate["caveats"]).lower()
    assert "built-in reference_seeds" in " ".join(packet["next_steps"])
    assert "does not perform unconfirmed live lookup" in " ".join(packet["boundaries"])
    assert "EA may use those sources to prepare assignment candidates" in " ".join(packet["boundaries"])
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


def test_ftir_assignment_library_summary_filters_source_backed_candidates() -> None:
    summary = summarize_ftir_assignment_libraries(
        builtin_libraries=["generic_materials"],
        assignment_types=["inorganic_ion"],
        material_scopes=["oxide"],
        wavenumber_min_cm1=1300,
        wavenumber_max_cm1=1500,
    )

    assert summary["status"] == "ready"
    assert summary["library_count"] == 1
    assert summary["matching_candidate_count"] == 2
    assert summary["filters"]["builtin_libraries"] == ["generic_materials"]
    assert summary["filters"]["assignment_types"] == ["inorganic_ion"]
    assert summary["filters"]["material_scopes"] == ["oxide"]
    assert summary["filters"]["wavenumber_min_cm1"] == 1300
    assert summary["filters"]["wavenumber_max_cm1"] == 1500
    assert "inorganic_ion" in summary["available_assignment_types"]
    assert "oxides" in summary["available_material_scopes"]
    assert summary["available_wavenumber_range_cm1"] == [400.0, 3600.0]
    assert "builtin-ftir-nakamoto-2009" in summary["matching_reference_ids"]

    library = summary["libraries"][0]
    assert library["library_id"] == "generic_materials"
    assert library["total_candidate_count"] >= 18
    assert library["matching_candidate_count"] == 2
    assert "builtin-ftir-nakamoto-2009" in library["matching_reference_seed_ids"]
    candidates = {candidate["candidate_id"]: candidate for candidate in library["candidates"]}
    carbonate = candidates["ftir-builtin-carbonate-asymmetric-stretch-generic"]
    assert carbonate["wavenumber_window_cm1"] == [1350.0, 1500.0]
    assert carbonate["expected_feature"] == "absorbance_maximum"
    assert carbonate["auto_applied"] is False
    assert carbonate["requires_user_review"] is True
    nitrate = candidates["ftir-builtin-nitrate-stretching-generic"]
    assert nitrate["assignment_label"] == "nitrate NO3 stretching candidate"
    command = summary["next_commands"]["build_assignment_packet"][0]
    assert "build-assignment-packet" in command
    assert "--include-candidate ftir-builtin-carbonate-asymmetric-stretch-generic" in command
    assert "--include-candidate ftir-builtin-nitrate-stretching-generic" in command
    assert "does not run live literature search" in " ".join(summary["boundaries"])


def test_cli_lists_ftir_assignment_libraries_and_reports_no_matches(capsys) -> None:
    assert (
        main(
            [
                "ftir",
                "list-assignment-libraries",
                "--builtin-library",
                "generic_materials",
                "--assignment-type",
                "functional_group",
                "--material-scope",
                "polymer",
                "--wavenumber-min-cm1",
                "1650",
                "--wavenumber-max-cm1",
                "1800",
            ]
        )
        == 0
    )
    summary = _json_output(capsys)
    assert summary["status"] == "ready"
    assert summary["libraries"][0]["library_id"] == "generic_materials"
    assert "ftir-builtin-carbonyl-co-stretching-generic" in summary["libraries"][0]["candidate_ids"]
    assert "suggest-assignments" in summary["next_commands"]["suggest_assignments"]

    assert (
        main(
            [
                "ftir",
                "list-assignment-libraries",
                "--builtin-library",
                "generic_materials",
                "--assignment-type",
                "inorganic_ion",
                "--material-scope",
                "polymer",
                "--wavenumber-min-cm1",
                "2800",
                "--wavenumber-max-cm1",
                "3000",
            ]
        )
        == 0
    )
    no_match = _json_output(capsys)
    assert no_match["status"] == "no_matching_candidates"
    assert no_match["matching_candidate_count"] == 0
    assert no_match["next_commands"]["build_assignment_packet"] == []


def test_cli_builds_ftir_assignment_source_packet_from_confirmed_literature_manifest(tmp_path: Path, capsys) -> None:
    workspace = tmp_path / "ftir-literature-manifest-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "FTIR Literature Source Packet",
            "--slug",
            "ftir-literature-source-packet",
            "--direction",
            "FTIR literature source packet workflow",
            "--material",
            "polymer oxide composite",
            "--experiment-type",
            "materials FTIR characterization",
        ]
    ) == 0
    project = _json_output(capsys)
    project_frontmatter, _ = read_markdown_record(Path(project["project"]))
    project_id = project_frontmatter["project_id"]

    manifest = workspace / "literature" / "confirmed_ftir_source_candidates.yml"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        """
schema_version: "0.2"
source: ea.literature.source_candidates:v0.2
confirmed_for_source_packet: true
method_scope:
  - ftir
confirmation:
  status: user_confirmed
  reviewed_by: user
  reviewed_content: Literature-derived FTIR carbonyl assignment candidate approved for source-packet staging.
reference_seeds:
  ref-lit-ftir-carbonyl-001:
    citation: "Literature FTIR carbonyl reference. Example Journal (2026)."
    title: "Literature FTIR carbonyl reference"
    year: 2026
    url: "https://example.org/lit-ftir-carbonyl"
    source_type: literature_library
  ref-lit-ftir-excluded-001:
    citation: "Excluded FTIR reference. Example Journal (2026)."
    title: "Excluded FTIR reference"
    year: 2026
    url: "https://example.org/lit-ftir-excluded"
    source_type: literature_library
candidates:
  - method: ftir
    candidate_id: ftir-lit-carbonyl-001
    assignment_type: functional_group
    assignment_label: literature carbonyl C=O candidate
    wavenumber_window_cm1: [1705, 1740]
    expected_feature: absorbance_maximum
    source_summary: Literature source reports a carbonyl stretching region relevant to the reviewed polymer context.
    applicability_notes:
      - Use only after sample chemistry and band overlap are reviewed.
    reference_ids:
      - ref-lit-ftir-carbonyl-001
    confidence: medium
    caveats:
      - Literature-derived candidate only; not composition proof.
  - method: xps
    candidate_id: xps-lit-ignored-001
    suggestion_type: tougaard_parameter
    reference_ids:
      - ref-lit-ftir-excluded-001
  - method: ftir
    include_in_source_packet: false
    candidate_id: ftir-lit-excluded-001
    assignment_label: excluded assignment
    reference_ids:
      - ref-lit-ftir-excluded-001
""".strip()
        + "\n",
        encoding="utf-8",
    )

    assert (
        main(
            [
                "ftir",
                "build-assignment-packet",
                str(workspace),
                "--project-id",
                project_id,
                "--literature-manifest",
                manifest.relative_to(workspace).as_posix(),
                "--output",
                "suggestions/ftir/source-packets/literature_ftir_packet.yml",
            ]
        )
        == 0
    )
    packet_output = _json_output(capsys)
    packet = read_yaml(Path(packet_output["source_packet"]))
    assert packet_output["status"] == "ready_for_suggest_assignments"
    assert packet_output["candidate_count"] == 1
    assert packet_output["reference_seed_count"] == 1
    assert packet_output["source_library_kind"] == "confirmed_literature_manifest"
    assert packet["source_library_kind"] == "confirmed_literature_manifest"
    assert packet["source_manifest_ref"] == manifest.relative_to(workspace).as_posix()
    assert packet["confirmation_status"] == "user_confirmed"
    assert packet["candidates"][0]["candidate_id"] == "ftir-lit-carbonyl-001"
    assert "ref-lit-ftir-carbonyl-001" in packet["reference_seeds"]
    assert "ref-lit-ftir-excluded-001" not in packet["reference_seeds"]
    assert "confirmed-literature reference_seeds" in " ".join(packet["next_steps"])
    assert "does not perform unconfirmed live lookup" in " ".join(packet["boundaries"])
    assert "do not register references" in " ".join(packet["boundaries"])
    assert (workspace / packet["provenance_ref"]).exists()


def test_ftir_docs_and_skill_references_are_discoverable() -> None:
    root = Path.cwd()

    readme = (root / "README.md").read_text(encoding="utf-8")
    skill = (root / "skills" / "ea-v0-2" / "SKILL.md").read_text(encoding="utf-8")
    ftir_reference = root / "skills" / "ea-v0-2" / "references" / "ftir-workflow.md"
    registry = read_yaml(root / "skill-registry" / "index.yml")

    assert "ea ftir inspect" in readme
    assert "ea ftir list-assignment-libraries" in readme
    assert "ea ftir process" in skill
    assert "ea ftir list-assignment-libraries" in skill
    assert "ea ftir suggest-assignments" in skill
    assert "ea ftir propose-memory" in skill
    assert "--assignment-suggestion" in skill
    assert "--builtin-library" in skill
    assert "register-seeds" in skill
    assert "references/ftir-workflow.md" in skill
    assert ftir_reference.exists()
    reference_text = ftir_reference.read_text(encoding="utf-8")
    assert "signal_mode" in reference_text
    assert "context_record" in reference_text
    assert "list-assignment-libraries" in reference_text
    assert "candidate counts, assignment types, material scopes, wavenumber ranges" in reference_text
    assert "build-assignment-packet" in reference_text
    assert "suggest-assignments" in reference_text
    assert "propose-memory" in reference_text
    assert "--assignment-suggestion" in reference_text
    assert "generic_materials" in reference_text
    assert "register-seeds" in reference_text
    assert "does not perform unconfirmed live lookup" in reference_text
    assert "EA may still prepare source-backed candidates" in reference_text
    ftir_record = next(item for item in registry["skills"] if item["id"] == "ea.ftir-analysis")
    assert "Minimal FTIR workflow implemented" in ftir_record["notes"]
    assert "context_records" in ftir_record["notes"]
    assert "assignment_library_discovery_summary" in ftir_record["notes"]
    assert "ea ftir list-assignment-libraries" in ftir_record["notes"]
    assert "assignment_suggestions" in ftir_record["notes"]
    assert "memory_candidate proposals" in ftir_record["notes"]
    assert "built_in_assignment_library" in ftir_record["notes"]
    assert "reference_seed registration" in ftir_record["notes"]
