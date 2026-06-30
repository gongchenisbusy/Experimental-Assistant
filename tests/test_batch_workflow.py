from __future__ import annotations

import json
import math
from pathlib import Path

from ea.cli import main
from ea.ftir import default_ftir_processing_parameters
from ea.pl import default_pl_processing_parameters
from ea.projects import initialize_project
from ea.raman import default_processing_parameters
from ea.raw_import import import_raw_file
from ea.review import write_review_record
from ea.storage import read_markdown_record, read_yaml, write_yaml
from ea.xrd import default_xrd_processing_parameters


PUBLIC_RAW = Path("tests/fixtures/public/test-case-001/raw_data").resolve()


def _json_output(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def _write_ftir_fixture(path: Path) -> Path:
    lines = [
        "# x_unit = cm^-1",
        "# y_label = absorbance",
        "wavenumber absorbance",
    ]
    for index in range(1200):
        wavenumber = 4000.0 - index * 3.0
        signal = 0.02
        for center, amplitude, width in [
            (3400.0, 0.28, 55.0),
            (1720.0, 0.24, 30.0),
            (1100.0, 0.32, 45.0),
        ]:
            signal += amplitude * math.exp(-((wavenumber - center) ** 2) / (2.0 * width**2))
        lines.append(f"{wavenumber:.2f} {signal:.8f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _project(tmp_path: Path) -> tuple[Path, str]:
    workspace = tmp_path / "batch-project"
    outputs = initialize_project(
        workspace,
        project_name="Batch Characterization",
        project_slug="batch-characterization",
        research_direction="Batch Raman PL XRD workflow",
        material_system="MoS2",
        experiment_type="CVD characterization",
        created_at="2026-06-30T09:00:00",
    )
    frontmatter, _ = read_markdown_record(outputs["project"])
    return workspace, frontmatter["project_id"]


def _confirmed_reviews(workspace: Path, target_ref: str, method: str, column_text: str, parameter_text: str) -> tuple[str, str]:
    column_review = write_review_record(
        workspace,
        target_type=f"{method}_columns",
        target_ref=target_ref,
        user_response="可以，保存",
        reviewed_content=column_text,
        reviewed_at="2026-06-30T09:10:00",
    )
    parameter_review = write_review_record(
        workspace,
        target_type=f"{method}_parameters",
        target_ref=target_ref,
        user_response="可以，保存",
        reviewed_content=parameter_text,
        reviewed_at="2026-06-30T09:11:00",
    )
    return column_review.stem, parameter_review.stem


def _import_with_reviews(workspace: Path, project_id: str, method: str, source: Path, sample: str, experiment: str) -> dict:
    raw = import_raw_file(
        workspace,
        source,
        project_id=project_id,
        characterization_type=method,
        sample_refs=[sample],
        experiment_refs=[experiment],
        imported_at="2026-06-30T09:05:00",
    )
    metadata_ref = raw.metadata_path.relative_to(workspace).as_posix()
    if method == "xrd":
        x_column, y_column, x_unit = "two_theta", "intensity", "2theta_deg"
        parameters = default_xrd_processing_parameters()
    elif method == "pl":
        x_column, y_column, x_unit = "col_0", "col_1", "eV"
        parameters = default_pl_processing_parameters()
    elif method == "ftir":
        x_column, y_column, x_unit = "wavenumber", "absorbance", "cm^-1"
        parameters = default_ftir_processing_parameters()
    else:
        x_column, y_column, x_unit = "col_0", "col_1", "cm^-1"
        parameters = default_processing_parameters()
    column_review, parameter_review = _confirmed_reviews(
        workspace,
        metadata_ref,
        method,
        f"x={x_column}, y={y_column}, unit={x_unit}",
        json.dumps(parameters, ensure_ascii=False),
    )
    result = {
        "method": method,
        "metadata": metadata_ref,
        "sample_refs": [sample],
        "experiment_refs": [experiment],
        "x_column": x_column,
        "y_column": y_column,
        "x_unit": x_unit,
        "column_review_ref": column_review,
        "parameter_review_ref": parameter_review,
        "processing_parameters": parameters,
    }
    if method == "ftir":
        result["signal_mode"] = "absorbance"
    return result


def test_cli_runs_mixed_characterization_batch(tmp_path: Path, capsys) -> None:
    workspace, project_id = _project(tmp_path)
    ftir_fixture = _write_ftir_fixture(tmp_path / "batch-ftir-spectrum.txt")
    items = [
        {
            "item_id": "raman-001",
            **_import_with_reviews(workspace, project_id, "raman", PUBLIC_RAW / "MoS-2(1).txt", "sample-batch-001", "exp-batch-001"),
        },
        {
            "item_id": "pl-001",
            **_import_with_reviews(workspace, project_id, "pl", PUBLIC_RAW / "MoS-PL-2(1).txt", "sample-batch-001", "exp-batch-001"),
        },
        {
            "item_id": "xrd-001",
            **_import_with_reviews(workspace, project_id, "xrd", PUBLIC_RAW / "MoS-XRD-1.txt", "sample-batch-001", "exp-batch-001"),
        },
        {
            "item_id": "ftir-001",
            **_import_with_reviews(workspace, project_id, "ftir", ftir_fixture, "sample-batch-001", "exp-batch-001"),
        },
    ]
    manifest = workspace / "batch_manifest.yml"
    write_yaml(
        manifest,
        {
            "batch": {
                "project_id": project_id,
                "create_reports": True,
                "continue_on_error": True,
                "items": items,
            }
        },
    )

    assert main(["batch", "validate", str(workspace), "batch_manifest.yml"]) == 0
    validation = _json_output(capsys)
    assert validation["status"] == "pass"
    assert validation["item_count"] == 4

    assert main(["batch", "run", str(workspace), "batch_manifest.yml"]) == 0
    output = _json_output(capsys)
    assert output["status"] == "success"
    assert output["succeeded"] == 4
    assert output["failed"] == 0

    record = read_yaml(Path(output["record"]))
    assert record["status"] == "success"
    assert record["provenance_refs"]
    assert all(item["status"] == "success" for item in record["items"])
    assert all(item.get("result_metadata_ref") for item in record["items"])
    assert all(item.get("report_ref") for item in record["items"])
    assert Path(output["summary"]).exists()
    index = read_yaml(workspace / "processed" / "batches" / "index.yml")
    assert record["batch_id"] in index["batches"]

    assert main(["healthcheck", str(workspace)]) == 0
    health = _json_output(capsys)
    assert health["status"] == "pass"


def test_batch_run_records_item_failures(tmp_path: Path, capsys) -> None:
    workspace, project_id = _project(tmp_path)
    item = _import_with_reviews(
        workspace,
        project_id,
        "raman",
        PUBLIC_RAW / "MoS-2(1).txt",
        "sample-fail-001",
        "exp-fail-001",
    )
    item["item_id"] = "bad-column"
    item["x_column"] = "not_a_column"
    manifest = workspace / "bad_batch.yml"
    write_yaml(
        manifest,
        {
            "batch": {
                "project_id": project_id,
                "create_reports": True,
                "continue_on_error": True,
                "items": [item],
            }
        },
    )

    assert main(["batch", "validate", str(workspace), "bad_batch.yml"]) == 0
    _json_output(capsys)
    assert main(["batch", "run", str(workspace), "bad_batch.yml"]) == 2
    output = _json_output(capsys)
    assert output["status"] == "failed"
    assert output["failed"] == 1

    record = read_yaml(Path(output["record"]))
    assert record["items"][0]["status"] == "failed"
    assert record["items"][0]["x_column"] == "not_a_column"
    assert "columns are not present" in record["items"][0]["error"]
    summary = Path(output["summary"]).read_text(encoding="utf-8")
    assert "bad-column" in summary
    assert "failed" in summary
