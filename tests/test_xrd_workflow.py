from __future__ import annotations

import csv
import json
from pathlib import Path

from ea.cli import main
from ea.storage import read_markdown_record, read_yaml, write_yaml
from ea.xrd import default_xrd_processing_parameters, inspect_xrd_file


FIXTURE_XRD = Path("tests/fixtures/public/test-case-001/raw_data/MoS-XRD-1.txt").resolve()


def _json_output(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def _init_xrd_project(tmp_path: Path, capsys, *, slug: str, material: str = "MoS2") -> tuple[Path, str]:
    workspace = tmp_path / slug
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            slug.replace("-", " ").title(),
            "--slug",
            slug,
            "--direction",
            "XRD source-packet workflow",
            "--material",
            material,
            "--experiment-type",
            "Materials XRD",
        ]
    ) == 0
    project = _json_output(capsys)
    project_frontmatter, _ = read_markdown_record(Path(project["project"]))
    return workspace, project_frontmatter["project_id"]


def test_inspect_public_xrd_fixture() -> None:
    inspection = inspect_xrd_file(FIXTURE_XRD)

    assert inspection.file_kind == "xrd"
    assert inspection.row_count == 40
    assert inspection.x_column_candidate == "two_theta"
    assert inspection.y_column_candidate == "intensity"
    assert inspection.x_unit == "2theta_deg"
    assert inspection.requires_user_confirmation is True


def test_cli_runs_public_xrd_workflow_end_to_end(tmp_path: Path, capsys) -> None:
    workspace = tmp_path / "cli-xrd-project"
    assert main(
        [
            "init-project",
            str(workspace),
            "--name",
            "CLI XRD Workflow",
            "--slug",
            "mos2-xrd-workflow",
            "--direction",
            "XRD workflow",
            "--material",
            "MoS2",
            "--experiment-type",
            "CVD and XRD",
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
            str(FIXTURE_XRD),
            "--characterization-type",
            "xrd",
            "--sample-ref",
            "sample-xrd-001",
            "--experiment-ref",
            "exp-xrd-001",
        ]
    ) == 0
    raw_output = _json_output(capsys)
    raw_metadata = Path(raw_output["metadata"])
    raw_metadata_ref = raw_metadata.relative_to(workspace).as_posix()

    assert raw_output["import_status"] == "imported"
    assert main(["xrd", "inspect", str(workspace), raw_output["project_raw_path"]]) == 0
    inspection = _json_output(capsys)
    assert inspection["file_kind"] == "xrd"
    assert inspection["x_unit"] == "2theta_deg"

    assert main(
        [
            "review",
            "add",
            str(workspace),
            "--target-type",
            "xrd_columns",
            "--target-ref",
            raw_metadata_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            "x=two_theta, y=intensity, unit=2theta_deg",
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
            "xrd_parameters",
            "--target-ref",
            raw_metadata_ref,
            "--user-response",
            "可以，保存",
            "--reviewed-content",
            json.dumps(default_xrd_processing_parameters(), ensure_ascii=False),
        ]
    ) == 0
    parameter_review = _json_output(capsys)
    assert parameter_review["review_status"] == "user_confirmed"

    assert main(
        [
            "xrd",
            "process",
            str(workspace),
            "--metadata",
            raw_metadata_ref,
            "--project-id",
            project_id,
            "--sample-ref",
            "sample-xrd-001",
            "--x-column",
            "two_theta",
            "--y-column",
            "intensity",
            "--x-unit",
            "2theta_deg",
            "--column-review-ref",
            column_review["review_id"],
            "--parameter-review-ref",
            parameter_review["review_id"],
        ]
    ) == 0
    process_output = _json_output(capsys)
    xrd_metadata = Path(process_output["metadata"])
    xrd = read_yaml(xrd_metadata)

    assert xrd["result_id"].startswith("res-mos2-xrd-workflow-xrd-")
    assert xrd["xrd_result_id"] == xrd["result_id"]
    assert xrd["wavelength_angstrom"] == 1.5406
    assert xrd["peak_analysis"]["peak_count"] > 0
    assert xrd["peak_analysis"]["assignment_source"] == "ea.materials.builtin:mos2:xrd:v0.2"
    assert xrd["peak_analysis"]["possible_interpretations"][0]["confidence"] == "medium"
    assert (workspace / xrd["outputs"]["peak_table"]).exists()
    assert (workspace / xrd["outputs"]["figure"]).exists()
    figure_record = read_yaml(workspace / "figures" / "index.yml")["figures"][xrd["figure_id"]]
    assert figure_record["style_profile"] == "nature_like_clean"
    assert figure_record["generation"]["style_profile"] == "nature_like_clean"
    assert xrd["outputs"]["processed_csv"] in figure_record["source_data_refs"]
    assert xrd["outputs"]["peak_table"] in figure_record["source_data_refs"]

    with (workspace / xrd["outputs"]["peak_table"]).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert any(13.5 <= float(row["two_theta_deg"]) <= 15.5 for row in rows)
    assert any("MoS2" in row["possible_phase"] for row in rows)
    assert all("d_spacing_angstrom" in row for row in rows)

    assert (
        main(
            [
                "xrd",
                "build-assignment-packet",
                str(workspace),
                "--project-id",
                project_id,
                "--material",
                "MoS2",
                "--feature",
                "002",
            ]
        )
        == 0
    )
    packet_output = _json_output(capsys)
    packet_path = Path(packet_output["source_packet"])

    assert (
        main(
            [
                "references",
                "register-seeds",
                str(workspace),
                "--source-packet",
                packet_path.relative_to(workspace).as_posix(),
                "--project-id",
                project_id,
            ]
        )
        == 0
    )
    seed_output = _json_output(capsys)
    assert seed_output["imported_count"] == 1

    assert (
        main(
            [
                "xrd",
                "suggest-assignments",
                str(workspace),
                "--metadata",
                xrd_metadata.relative_to(workspace).as_posix(),
                "--source-file",
                packet_path.relative_to(workspace).as_posix(),
                "--project-id",
                project_id,
                "--related-record",
                raw_metadata_ref,
            ]
        )
        == 0
    )
    suggestion_output = _json_output(capsys)
    suggestion_record = read_yaml(Path(suggestion_output["record"]))
    assert suggestion_output["status"] == "ready_for_user_review"
    assert suggestion_output["ready_for_user_review_count"] == 1
    assert suggestion_record["source"] == "ea.xrd.assignment_suggestions:v0.2"
    assert suggestion_record["source_packet_ref"] == packet_path.relative_to(workspace).as_posix()
    assert suggestion_record["xrd_metadata_ref"] == xrd_metadata.relative_to(workspace).as_posix()
    assert suggestion_record["candidates"][0]["candidate_id"] == "xrd-builtin-mos2-mos2_002_layered_reflection"
    assert suggestion_record["candidates"][0]["status"] == "ready_for_user_review"
    assert suggestion_record["candidates"][0]["matched_peak_ids"]
    assert suggestion_record["candidates"][0]["unresolved_reference_ids"] == []
    assert suggestion_record["candidates"][0]["auto_applied"] is False
    assert (workspace / suggestion_record["table_ref"]).exists()
    assert suggestion_record["provenance_ref"]

    assert (
        main(
            [
                "xrd",
                "prepare-review",
                str(workspace),
                "--suggestion",
                Path(suggestion_output["record"]).relative_to(workspace).as_posix(),
                "--project-id",
                project_id,
            ]
        )
        == 0
    )
    review_package_output = _json_output(capsys)
    review_package = read_yaml(Path(review_package_output["review_package"]))
    review_package_markdown = Path(review_package_output["review_package_markdown"]).read_text(encoding="utf-8")
    assert review_package_output["status"] == "review_package_prepared"
    assert review_package_output["selected_candidate_count"] == 1
    assert review_package_output["selected_status_counts"]["ready_for_user_review"] == 1
    assert review_package["source"] == "ea.xrd.assignment_review_package:v0.2"
    assert review_package["review_target_type"] == "xrd_assignment_suggestions"
    assert review_package["review_target_ref"] == Path(suggestion_output["record"]).relative_to(workspace).as_posix()
    assert review_package["groups"][0]["group"] == "ready_for_user_review"
    assert review_package["groups"][0]["candidate_ids"] == ["xrd-builtin-mos2-mos2_002_layered_reflection"]
    assert "builtin-xrd-jagminas-2019-mos2-xrd" in review_package["reference_ids"]
    assert "ea review add /path/to/ea-project" in review_package["recommended_commands"]["create_review_record"]
    assert "ea xrd suggest-assignments" in review_package["recommended_commands"]["rerun_after_reference_registration"]
    assert "does not create a ReviewRecord" in " ".join(review_package["boundaries"])
    assert read_yaml(Path(review_package_output["provenance"]))["workflow"] == "xrd_assignment_review_package"
    assert "XRD Assignment Suggestion Review Package" in review_package_markdown
    assert "MoS2 (002)/(00l)-type layered reflection candidate" in review_package_markdown
    assert "does not apply XRD assignments" in review_package_markdown

    suggestion_ref = Path(suggestion_output["record"]).relative_to(workspace).as_posix()
    assert (
        main(
            [
                "xrd",
                "report",
                str(workspace),
                "--metadata",
                xrd_metadata.relative_to(workspace).as_posix(),
                "--project-id",
                project_id,
                "--assignment-suggestion",
                suggestion_ref,
            ]
        )
        == 2
    )
    boundary_error = _json_output(capsys)
    assert boundary_error["status"] == "error"
    assert boundary_error["cause"]["type"] == "ValueError"
    assert "Each --assignment-suggestion requires one matching --assignment-review-ref" in boundary_error["cause"]["message"]

    assert (
        main(
            [
                "review",
                "add",
                str(workspace),
                "--target-type",
                "xrd_assignment_suggestions",
                "--target-ref",
                suggestion_ref,
                "--user-response",
                "可以，保存",
                "--reviewed-content",
                "User reviewed XRD assignment suggestion xrd-builtin-mos2-mos2_002_layered_reflection as report discussion context.",
            ]
        )
        == 0
    )
    assignment_review = _json_output(capsys)
    assert assignment_review["review_status"] == "user_confirmed"

    assert main(
        [
            "xrd",
            "report",
            str(workspace),
            "--metadata",
            xrd_metadata.relative_to(workspace).as_posix(),
            "--project-id",
            project_id,
            "--sample-ref",
            "sample-xrd-001",
            "--experiment-ref",
            "exp-xrd-001",
            "--assignment-suggestion",
            suggestion_ref,
            "--assignment-review-ref",
            assignment_review["review_id"],
        ]
    ) == 0
    report_output = _json_output(capsys)
    report_frontmatter, report_body = read_markdown_record(Path(report_output["report"]))
    assert report_frontmatter["report_type"] == "xrd_analysis"
    assert "builtin-xrd-jagminas-2019-mos2-xrd" in report_frontmatter["reference_ids"]
    assert assignment_review["review_id"] in read_yaml(workspace / "provenance" / f"{report_frontmatter['provenance_refs'][0]}.yml")["review_refs"]
    assert "## XRD 峰参数" in report_body
    assert "## Reviewed source-backed XRD assignment suggestions" in report_body
    assert f"review_ref: `{assignment_review['review_id']}`" in report_body
    assert "MoS2 (002)/(00l)-type layered reflection candidate[1]" in report_body
    assert "report_use: `reviewed_assignment_context`" in report_body
    assert "matched_peak_ids" in report_body
    assert "不能单独证明相组成" in report_body
    assert "## 图件" in report_body
    assert f"### `{xrd['figure_id']}`" in report_body
    assert Path(xrd["outputs"]["processed_csv"]).name in report_body
    assert "## 输出文件" not in report_body

    assert main(["healthcheck", str(workspace)]) == 0
    health = _json_output(capsys)
    assert health["status"] == "pass"


def test_cli_builds_xrd_assignment_source_packet_from_builtin_library(tmp_path: Path, capsys) -> None:
    workspace, project_id = _init_xrd_project(tmp_path, capsys, slug="xrd-builtin-packet")

    assert (
        main(
            [
                "xrd",
                "build-assignment-packet",
                str(workspace),
                "--project-id",
                project_id,
                "--material",
                "MoS2",
                "--feature",
                "002",
                "--two-theta-min-deg",
                "14.0",
                "--two-theta-max-deg",
                "14.6",
            ]
        )
        == 0
    )
    output = _json_output(capsys)
    packet_path = Path(output["source_packet"])
    packet = read_yaml(packet_path)

    assert output["status"] == "ready_for_review"
    assert output["source_library_kind"] == "built_in"
    assert output["candidate_count"] == 1
    assert packet["source"] == "ea.xrd.assignment_source_packet:v0.2"
    assert packet["source_library_ref"] == "builtin:builtin_material_assignments"
    assert packet["reference_seed_count"] == 1
    assert packet["reference_ids"] == ["builtin-xrd-jagminas-2019-mos2-xrd"]
    assert packet["reference_seeds"]["builtin-xrd-jagminas-2019-mos2-xrd"]["doi"] == "10.1038/s41598-019-44085-7"
    candidate = packet["candidates"][0]
    assert candidate["candidate_id"] == "xrd-builtin-mos2-mos2_002_layered_reflection"
    assert candidate["assignment_type"] == "diffraction_feature_assignment"
    assert candidate["two_theta_window_deg"] == [13.5, 15.5]
    assert candidate["auto_applied"] is False
    assert candidate["requires_user_review"] is True
    assert "live lookup" in " ".join(packet["boundaries"])
    assert packet["provenance_ref"]

    assert (
        main(
            [
                "references",
                "register-seeds",
                str(workspace),
                "--source-packet",
                packet_path.relative_to(workspace).as_posix(),
                "--project-id",
                project_id,
                "--dry-run",
            ]
        )
        == 0
    )
    seed_output = _json_output(capsys)
    assert seed_output["dry_run"] is True
    assert seed_output["imported_count"] == 1
    assert seed_output["imported"][0]["reference_id"] == "builtin-xrd-jagminas-2019-mos2-xrd"


def test_cli_builds_xrd_assignment_source_packet_from_local_library(tmp_path: Path, capsys) -> None:
    workspace, project_id = _init_xrd_project(tmp_path, capsys, slug="xrd-local-packet")
    library = workspace / "xrd_local_assignment_library.yml"
    library.write_text(
        """
reference_seeds:
  local-xrd-ref-001:
    citation: "Local XRD reference for MoS2 layered reflection."
    title: "Local XRD reference for MoS2 layered reflection"
    year: 2026
guidance_notes:
  - "Use this local packet only after user review."
candidates:
  - candidate_id: local-xrd-mos2-002
    candidate_type: diffraction_feature_assignment
    material_id: mos2
    feature: mos2_002_layered_reflection
    label: MoS2 layered (002) reflection
    two_theta_window_deg: [14.0, 14.8]
    d_spacing_window_angstrom: [5.9, 6.4]
    source_summary: Local reviewed source candidate.
    applicability_notes:
      - Review radiation wavelength and sample context.
    reference_ids:
      - local-xrd-ref-001
    confidence: low
    caveats:
      - Local candidate only.
""".lstrip(),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "xrd",
                "build-assignment-packet",
                str(workspace),
                "--project-id",
                project_id,
                "--library-file",
                library.relative_to(workspace).as_posix(),
                "--include-candidate",
                "local-xrd-mos2-002",
            ]
        )
        == 0
    )
    output = _json_output(capsys)
    packet = read_yaml(Path(output["source_packet"]))

    assert output["source_library_kind"] == "local_file"
    assert packet["source_library_ref"] == "xrd_local_assignment_library.yml"
    assert packet["candidate_count"] == 1
    assert packet["reference_seed_count"] == 1
    assert packet["reference_seeds"]["local-xrd-ref-001"]["year"] == 2026
    assert packet["guidance_notes"] == ["Use this local packet only after user review."]


def test_cli_writes_xrd_assignment_source_packet_template(tmp_path: Path, capsys) -> None:
    workspace, project_id = _init_xrd_project(tmp_path, capsys, slug="xrd-template-packet")

    assert main(["xrd", "build-assignment-packet", str(workspace), "--project-id", project_id, "--write-template"]) == 0
    output = _json_output(capsys)
    packet_path = Path(output["source_packet"])
    packet = read_yaml(packet_path)

    assert packet_path == workspace / "templates" / "xrd_assignment_source_packet.yml"
    assert packet["status"] == "template_requires_user_edit"
    assert packet["source_library_kind"] == "template"
    assert packet["candidate_count"] == 1
    assert packet["candidates"][0]["candidate_id"] == "xrd-assignment-template-001"
    assert packet["candidates"][0]["auto_applied"] is False


def test_cli_builds_xrd_assignment_source_packet_from_confirmed_literature_manifest(tmp_path: Path, capsys) -> None:
    workspace, project_id = _init_xrd_project(tmp_path, capsys, slug="xrd-literature-packet")
    manifest = workspace / "literature" / "confirmed_xrd_source_candidates.yml"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        """
confirmed_for_source_packet: true
method: xrd
reference_seeds:
  lit-xrd-ref-001:
    citation: "Literature XRD source for MoS2 (002)."
    title: "Literature XRD source for MoS2 (002)"
    doi: "10.1234/example.xrd"
  lit-xrd-unused:
    citation: "Unused reference."
guidance_reference_ids:
  - lit-xrd-ref-001
source_candidates:
  - candidate_id: lit-xrd-mos2-002
    method: xrd
    include_in_source_packet: true
    material_id: mos2
    feature: mos2_002_layered_reflection
    label: MoS2 layered (002) reflection
    two_theta_window_deg: [14.0, 14.8]
    d_spacing_window_angstrom: [5.9, 6.4]
    source_summary: Confirmed literature candidate.
    applicability_notes:
      - Review substrate and radiation wavelength.
    reference_ids:
      - lit-xrd-ref-001
    confidence: low
    caveats:
      - Literature candidate only.
  - candidate_id: lit-xrd-excluded
    method: xrd
    include_in_source_packet: false
    material_id: ws2
    feature: ws2_002_layered_reflection
    reference_ids:
      - lit-xrd-unused
""".lstrip(),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "xrd",
                "build-assignment-packet",
                str(workspace),
                "--project-id",
                project_id,
                "--literature-manifest",
                manifest.relative_to(workspace).as_posix(),
                "--output",
                "suggestions/xrd/source-packets/literature_xrd_packet.yml",
                "--material",
                "MoS2",
                "--feature",
                "002",
            ]
        )
        == 0
    )
    output = _json_output(capsys)
    packet_path = workspace / "suggestions" / "xrd" / "source-packets" / "literature_xrd_packet.yml"
    packet = read_yaml(packet_path)

    assert Path(output["source_packet"]) == packet_path
    assert packet["source_library_kind"] == "confirmed_literature_manifest"
    assert packet["source_manifest_ref"] == "literature/confirmed_xrd_source_candidates.yml"
    assert packet["confirmation_status"] == "confirmed"
    assert packet["candidate_count"] == 1
    assert packet["candidates"][0]["candidate_id"] == "lit-xrd-mos2-002"
    assert packet["reference_ids"] == ["lit-xrd-ref-001"]
    assert sorted(packet["reference_seeds"]) == ["lit-xrd-ref-001"]


def test_cli_records_xrd_assignment_suggestion_no_match(tmp_path: Path, capsys) -> None:
    workspace, project_id = _init_xrd_project(tmp_path, capsys, slug="xrd-suggestion-no-match")
    peak_table = workspace / "processed" / "sample-001" / "xrd" / "res-xrd-synthetic" / "xrd_peaks.csv"
    metadata = peak_table.parent / "xrd_metadata.yml"
    peak_table.parent.mkdir(parents=True, exist_ok=True)
    peak_table.write_text(
        "peak_id,two_theta_deg,d_spacing_angstrom,height,prominence,possible_phase,assignment_feature,assignment_confidence\n"
        "xrd-peak-001,14.4,6.14,1.0,0.8,,,\n",
        encoding="utf-8",
    )
    write_yaml(
        metadata,
        {
            "schema_version": "0.2",
            "result_id": "res-xrd-synthetic",
            "project_id": project_id,
            "outputs": {"peak_table": peak_table.relative_to(workspace).as_posix()},
        },
    )
    library = workspace / "xrd_no_match_library.yml"
    library.write_text(
        """
reference_seeds:
  local-xrd-ref-001:
    citation: "Local XRD reference."
    title: "Local XRD reference"
    year: 2026
candidates:
  - candidate_id: local-xrd-no-match
    assignment_type: diffraction_feature_assignment
    material_id: mos2
    feature: remote_peak
    label: Remote XRD feature
    two_theta_window_deg: [30.0, 31.0]
    d_spacing_window_angstrom: [2.8, 3.0]
    source_summary: Local no-match candidate.
    applicability_notes:
      - Review this only when a matching peak exists.
    reference_ids:
      - local-xrd-ref-001
    confidence: low
    caveats:
      - Synthetic no-match candidate.
""".lstrip(),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "xrd",
                "build-assignment-packet",
                str(workspace),
                "--project-id",
                project_id,
                "--library-file",
                library.relative_to(workspace).as_posix(),
            ]
        )
        == 0
    )
    packet_output = _json_output(capsys)
    packet_path = Path(packet_output["source_packet"])

    assert (
        main(
            [
                "references",
                "register-seeds",
                str(workspace),
                "--source-packet",
                packet_path.relative_to(workspace).as_posix(),
                "--project-id",
                project_id,
            ]
        )
        == 0
    )
    _json_output(capsys)

    assert (
        main(
            [
                "xrd",
                "suggest-assignments",
                str(workspace),
                "--project-id",
                project_id,
                "--metadata",
                metadata.relative_to(workspace).as_posix(),
                "--source-file",
                packet_path.relative_to(workspace).as_posix(),
            ]
        )
        == 0
    )
    output = _json_output(capsys)
    record = read_yaml(Path(output["record"]))
    assert output["status"] == "no_feature_match"
    assert output["no_feature_match_count"] == 1
    assert record["candidates"][0]["status"] == "no_feature_match"
    assert record["candidates"][0]["matched_peak_ids"] == []
    assert record["warnings"][0]["code"] == "xrd_assignment_suggestion_no_feature_match"

    assert (
        main(
            [
                "xrd",
                "prepare-review",
                str(workspace),
                "--project-id",
                project_id,
                "--suggestion",
                Path(output["record"]).relative_to(workspace).as_posix(),
                "--candidate-id",
                "local-xrd-no-match",
                "--candidate-id",
                "missing-xrd-candidate",
            ]
        )
        == 0
    )
    package_output = _json_output(capsys)
    package = read_yaml(Path(package_output["review_package"]))
    package_markdown = Path(package_output["review_package_markdown"]).read_text(encoding="utf-8")
    assert package_output["status"] == "review_package_prepared"
    assert package_output["selected_candidate_count"] == 1
    assert package_output["selected_status_counts"]["no_feature_match"] == 1
    assert package_output["missing_candidate_ids"] == ["missing-xrd-candidate"]
    assert package["groups"][0]["group"] == "no_feature_match"
    assert package["warnings"][0]["code"] == "xrd_review_package_candidate_not_found"
    assert "local-xrd-no-match" in package_markdown
    assert "no-match context" in package_markdown
