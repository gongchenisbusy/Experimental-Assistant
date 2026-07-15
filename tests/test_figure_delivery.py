from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image

from ea.figures import (
    figure_footer,
    figure_path_for_report,
    lookup_figure,
    register_figure,
    source_data_entry,
    update_figure_report_ref,
)
from ea.storage.files import write_yaml


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_report_bound_figure_has_one_final_footer_and_is_deterministic(
    tmp_path: Path,
) -> None:
    base = tmp_path / "figures" / "figure.png"
    base.parent.mkdir(parents=True)
    Image.new("RGB", (320, 180), "white").save(base)
    source = tmp_path / "processed" / "trace.csv"
    source.parent.mkdir(parents=True)
    source.write_text("x,y\n1,2\n", encoding="utf-8")
    figure_id = "fig-demo-001"
    report_id = "rpt-demo-001"

    register_figure(
        tmp_path,
        figure_id=figure_id,
        path=base.relative_to(tmp_path).as_posix(),
        report_id=None,
        result_id="res-demo-001",
        raw_data_ids=["raw-demo-001"],
        sample_ids=["sample-1"],
        source_data_refs=[source.relative_to(tmp_path).as_posix()],
        source_data=[
            source_data_entry(
                tmp_path,
                source.relative_to(tmp_path).as_posix(),
                role="primary_plotting_dataset",
                purpose="Trace plotted in the figure.",
                primary=True,
            )
        ],
    )
    assert figure_footer(figure_id, None) == ""
    base_sha = _sha256(base)

    first = update_figure_report_ref(tmp_path, figure_id, report_id)
    final_path = tmp_path / figure_path_for_report(first, report_id)
    first_sha = _sha256(final_path)
    with Image.open(final_path) as image:
        assert image.info["ea_footer"] == f"FigID: {figure_id} | Report: {report_id}"
        assert image.info["ea_footer"].count("FigID:") == 1
        assert image.info["ea_footer"].count("Report:") == 1
        assert "pending" not in image.info["ea_footer"]

    second = update_figure_report_ref(tmp_path, figure_id, report_id)
    assert _sha256(tmp_path / figure_path_for_report(second, report_id)) == first_sha
    assert _sha256(base) == base_sha
    assert second["source_data"][0]["columns"] == ["x", "y"]

    other_report = "rpt-demo-002"
    third = update_figure_report_ref(tmp_path, figure_id, other_report)
    assert _sha256(final_path) == first_sha
    assert set(third["renderings"]) == {report_id, other_report}


def test_legacy_figure_is_not_automatically_rewritten(tmp_path: Path) -> None:
    legacy = tmp_path / "figures" / "legacy.png"
    legacy.parent.mkdir(parents=True)
    Image.new("RGB", (64, 64), "white").save(legacy)
    before = _sha256(legacy)
    write_yaml(
        tmp_path / "figures" / "index.yml",
        {
            "schema_version": "0.2",
            "figures": {
                "fig-legacy": {
                    "figure_id": "fig-legacy",
                    "path": "figures/legacy.png",
                    "footer": "FigID: fig-legacy | Report: pending",
                }
            },
        },
    )

    record = update_figure_report_ref(tmp_path, "fig-legacy", "rpt-new")

    assert _sha256(legacy) == before
    assert record["upgrade_plan"]["status"] == "explicit_rerender_required"
    assert record["upgrade_plan"]["legacy_sha256"] == before
    assert lookup_figure(tmp_path, "fig-legacy")["path"] == "figures/legacy.png"
