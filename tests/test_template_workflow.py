from __future__ import annotations

import json
from pathlib import Path

from ea.cli import main
from ea.electrochemistry import default_electrochemistry_processing_parameters
from ea.ftir import default_ftir_processing_parameters
from ea.pl import default_pl_processing_parameters
from ea.projects import initialize_project
from ea.raman import default_processing_parameters
from ea.raw_import import import_raw_file
from ea.review import write_review_record
from ea.storage import read_markdown_record, read_yaml, write_yaml
from ea.thermal import default_thermal_processing_parameters
from ea.uv_vis import default_uv_vis_processing_parameters
from ea.xps import default_xps_processing_parameters
from ea.xrd import default_xrd_processing_parameters


FIXTURE_RAW = Path("tests/fixtures/public/test-case-001/raw_data/MoS-2(1).txt").resolve()


def _json_output(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def _project(tmp_path: Path) -> tuple[Path, str]:
    workspace = tmp_path / "template-project"
    outputs = initialize_project(
        workspace,
        project_name="Template Workflow",
        project_slug="template-workflow",
        research_direction="Template ergonomics",
        material_system="MoS2",
        experiment_type="CVD and Raman",
        created_at="2026-06-30T14:00:00",
    )
    frontmatter, _ = read_markdown_record(outputs["project"])
    return workspace, frontmatter["project_id"]


def _import_raman_with_reviews(workspace: Path, project_id: str) -> dict[str, str]:
    raw = import_raw_file(
        workspace,
        FIXTURE_RAW,
        project_id=project_id,
        characterization_type="raman",
        sample_refs=["sample-template-001"],
        experiment_refs=["exp-template-001"],
        imported_at="2026-06-30T14:05:00",
    )
    metadata_ref = raw.metadata_path.relative_to(workspace).as_posix()
    column_review = write_review_record(
        workspace,
        target_type="raman_columns",
        target_ref=metadata_ref,
        user_response="可以，保存",
        reviewed_content="x=col_0, y=col_1, unit=cm^-1",
        reviewed_at="2026-06-30T14:10:00",
    )
    parameter_review = write_review_record(
        workspace,
        target_type="raman_parameters",
        target_ref=metadata_ref,
        user_response="可以，保存",
        reviewed_content=json.dumps(default_processing_parameters(), ensure_ascii=False),
        reviewed_at="2026-06-30T14:11:00",
    )
    return {
        "metadata": metadata_ref,
        "column_review": column_review.stem,
        "parameter_review": parameter_review.stem,
    }


def test_cli_writes_processing_parameter_templates(capsys, tmp_path: Path) -> None:
    expected = {
        "raman": default_processing_parameters(),
        "pl": default_pl_processing_parameters(),
        "xrd": default_xrd_processing_parameters(),
        "ftir": default_ftir_processing_parameters(),
        "uv_vis": default_uv_vis_processing_parameters(),
        "xps": default_xps_processing_parameters(),
        "electrochemistry": default_electrochemistry_processing_parameters(),
        "thermal_analysis": default_thermal_processing_parameters(),
    }
    for method, defaults in expected.items():
        output_path = tmp_path / f"{method}_parameters.yml"

        assert main(["templates", "parameters", method, "--output", str(output_path)]) == 0
        output = _json_output(capsys)

        assert output["template_type"] == "processing_parameters"
        assert output["method"] == method
        assert output["review_target_type"] == f"{method}_parameters"
        assert output["written"] == str(output_path)
        assert read_yaml(output_path) == defaults


def test_parameter_template_file_can_drive_raman_processing(capsys, tmp_path: Path) -> None:
    workspace, project_id = _project(tmp_path)
    refs = _import_raman_with_reviews(workspace, project_id)
    parameter_path = tmp_path / "raman_parameters.yml"
    assert main(["templates", "parameters", "raman", "--output", str(parameter_path)]) == 0
    _json_output(capsys)

    assert main(
        [
            "raman",
            "process",
            str(workspace),
            "--metadata",
            refs["metadata"],
            "--project-id",
            project_id,
            "--sample-ref",
            "sample-template-001",
            "--x-column",
            "col_0",
            "--y-column",
            "col_1",
            "--x-unit",
            "cm^-1",
            "--column-review-ref",
            refs["column_review"],
            "--parameter-review-ref",
            refs["parameter_review"],
            "--parameters-file",
            str(parameter_path),
        ]
    ) == 0
    result = _json_output(capsys)
    metadata = read_yaml(Path(result["metadata"]))

    assert metadata["processing_parameters"] == default_processing_parameters()
    assert metadata["result_id"].startswith("res-template-workflow-raman-")


def test_batch_manifest_template_can_be_filled_and_validated(capsys, tmp_path: Path) -> None:
    workspace, project_id = _project(tmp_path)
    refs = _import_raman_with_reviews(workspace, project_id)
    manifest_path = workspace / "batch_manifest.yml"

    assert (
        main(
            [
                "templates",
                "batch-manifest",
                str(workspace),
                "--method",
                "raman",
                "--output",
                "batch_manifest.yml",
                "--sample-ref",
                "sample-template-001",
                "--experiment-ref",
                "exp-template-001",
            ]
        )
        == 0
    )
    output = _json_output(capsys)
    assert output["template_type"] == "batch_manifest"
    assert output["written"] == str(manifest_path)

    manifest = read_yaml(manifest_path)
    item = manifest["batch"]["items"][0]
    assert item["method"] == "raman"
    assert item["processing_parameters"] == {}
    item["metadata"] = refs["metadata"]
    item["column_review_ref"] = refs["column_review"]
    item["parameter_review_ref"] = refs["parameter_review"]
    write_yaml(manifest_path, manifest)

    assert main(["batch", "validate", str(workspace), "batch_manifest.yml"]) == 0
    validation = _json_output(capsys)
    assert validation["status"] == "pass"
    assert validation["items"][0]["item_id"] == "raman-001"
