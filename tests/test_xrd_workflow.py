from __future__ import annotations

import csv
import json
from pathlib import Path

from ea.cli import main
from ea.storage import read_markdown_record, read_yaml
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
        ]
    ) == 0
    report_output = _json_output(capsys)
    report_frontmatter, report_body = read_markdown_record(Path(report_output["report"]))
    assert report_frontmatter["report_type"] == "xrd_analysis"
    assert "## XRD 峰参数" in report_body
    assert "processed CSV" in report_body

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
