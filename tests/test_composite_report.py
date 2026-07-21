from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from ea.cli import main
from ea.figures import register_figure, source_data_entry
from ea.projects import initialize_project
from ea.storage import read_markdown_record, read_yaml, write_yaml


def _json_output(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def _result(root: Path, method: str, result_id: str, figure_id: str) -> None:
    output_dir = root / "processed" / "sample-best-001" / method / result_id
    output_dir.mkdir(parents=True, exist_ok=True)
    figure = output_dir / f"{figure_id}.png"
    Image.new("RGB", (32, 24), "white").save(figure)
    data = output_dir / f"{method}_processed.csv"
    data.write_text("x,y\n1,2\n", encoding="utf-8")
    metadata = output_dir / f"{method}_metadata.yml"
    write_yaml(
        metadata,
        {
            f"{method}_result_id": result_id,
            "result_id": result_id,
            "project_id": "prj-composite-report",
            "sample_refs": ["sample-best-001"],
            "figure_id": figure_id,
            "outputs": {
                "figure": figure.relative_to(root).as_posix(),
                "processed_csv": data.relative_to(root).as_posix(),
                "metadata": metadata.relative_to(root).as_posix(),
            },
            "warnings": [],
            "provenance_refs": [],
        },
    )
    register_figure(
        root,
        figure_id=figure_id,
        path=figure.relative_to(root).as_posix(),
        report_id=None,
        result_id=result_id,
        raw_data_ids=[],
        sample_ids=["sample-best-001"],
        source_data=[
            source_data_entry(
                root,
                data.relative_to(root).as_posix(),
                role="processed_spectrum",
                purpose=f"Processed {method} data for composite report.",
                primary=True,
            )
        ],
    )


def test_reviewed_composite_report_delivers_html_and_exportable_bundle(
    tmp_path: Path, capsys
) -> None:
    initialize_project(
        tmp_path,
        project_name="Composite report",
        project_slug="composite-report",
        research_direction="multi-method analysis",
        material_system="MoS2",
        experiment_type="Raman, PL, and AFM",
    )
    results = [
        ("raman", "res-composite-raman-001", "fig-composite-raman-001"),
        ("pl", "res-composite-pl-001", "fig-composite-pl-001"),
        ("afm", "res-composite-afm-001", "fig-composite-afm-001"),
    ]
    for item in results:
        _result(tmp_path, *item)

    command = [
        "composite-report",
        str(tmp_path),
        "--sample-ref",
        "sample-best-001",
        "--user-response",
        "可以，保存",
    ]
    for _, result_id, _ in results:
        command.extend(["--result-id", result_id])
    assert main(command) == 0
    output = _json_output(capsys)
    report_path = Path(output["report_path"])
    html_path = Path(output["html_path"])
    frontmatter, body = read_markdown_record(report_path)

    assert output["status"] == "complete"
    assert html_path.exists()
    assert frontmatter["report_type"] == "composite_analysis"
    assert frontmatter["status"] == "user_reviewed"
    assert frontmatter["related_results"] == [item[1] for item in results]
    assert frontmatter["review_refs"]
    assert "Raman + PL + AFM" in body
    figure_index = read_yaml(tmp_path / "figures" / "index.yml")
    assert all(
        frontmatter["report_id"] in figure_index["figures"][item[2]]["report_ids"]
        for item in results
    )

    assert main(
        [
            "export",
            "report-bundle",
            str(tmp_path),
            "--report-id",
            frontmatter["report_id"],
        ]
    ) == 0
    bundle = _json_output(capsys)
    assert bundle["status"] == "complete"
