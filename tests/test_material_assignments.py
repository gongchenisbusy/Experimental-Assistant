from __future__ import annotations

import json
from pathlib import Path

from ea.cli import main
from ea.materials import (
    assignment_candidates,
    available_materials,
    infer_material_from_text,
    infer_material_from_project,
    match_pl_peaks,
    match_raman_peaks,
    match_xrd_peaks,
)
from ea.storage import write_markdown_record


def _json_output(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def test_builtin_material_library_exposes_common_2d_material_methods() -> None:
    materials = available_materials()
    material_ids = {item["material_id"] for item in materials}
    assert {"hbn", "mos2", "ws2"}.issubset(material_ids)

    mos2 = next(item for item in materials if item["material_id"] == "mos2")
    ws2 = next(item for item in materials if item["material_id"] == "ws2")
    hbn = next(item for item in materials if item["material_id"] == "hbn")

    assert mos2["display_name"] == "MoS2"
    assert {"raman", "pl", "xrd"}.issubset(set(mos2["methods"]))
    assert ws2["display_name"] == "WS2"
    assert {"raman", "pl", "xrd"}.issubset(set(ws2["methods"]))
    assert hbn["display_name"] == "h-BN"
    assert {"raman", "xrd"}.issubset(set(hbn["methods"]))
    assert infer_material_from_text("prj-mos2-public") == "mos2"
    assert infer_material_from_text("prj-ws2-growth") == "ws2"
    assert infer_material_from_text("hexagonal boron nitride substrate") == "hbn"
    assert infer_material_from_text("generic BN code without material context") is None

    raman = assignment_candidates("MoS2", "raman")
    assert raman["assignment_source"] == "ea.materials.builtin:mos2:raman:v0.2"
    assert {rule["feature"] for rule in raman["feature_rules"]} == {"mos2_e2g_like", "mos2_a1g_like"}

    ws2_raman = assignment_candidates("tungsten disulfide", "raman")
    assert ws2_raman["assignment_source"] == "ea.materials.builtin:ws2:raman:v0.2"
    assert {rule["feature"] for rule in ws2_raman["feature_rules"]} == {"ws2_e2g_2la_like", "ws2_a1g_like"}

    hbn_raman = assignment_candidates("六方氮化硼", "raman")
    assert hbn_raman["assignment_source"] == "ea.materials.builtin:hbn:raman:v0.2"
    assert hbn_raman["feature_rules"][0]["feature"] == "hbn_e2g_like"
    assert assignment_candidates("BN", "xrd")["assignment_source"] == "ea.materials.builtin:hbn:xrd:v0.2"


def test_material_inference_uses_project_material_system(tmp_path: Path) -> None:
    write_markdown_record(
        tmp_path / "EA_PROJECT.md",
        {
            "project_id": "prj-cli-pl-workflow-20260630",
            "name": "CLI PL Workflow",
            "material_system": "MoS2",
            "direction": "PL workflow",
            "experiment_type": "CVD and PL",
        },
        "Project record",
    )

    assert infer_material_from_project(tmp_path, "prj-cli-pl-workflow-20260630") == "mos2"


def test_material_matchers_return_traceable_assignments() -> None:
    raman = match_raman_peaks(
        "mos2",
        [
            {"peak_id": "r1", "position_cm-1": 386.2},
            {"peak_id": "r2", "position_cm-1": 405.9},
        ],
    )
    assert raman["assignment_source"] == "ea.materials.builtin:mos2:raman:v0.2"
    assert raman["possible_interpretations"][0]["confidence"] == "medium"
    assert 18.0 <= raman["mode_separation_cm-1"] <= 22.5
    assert {update["assignment_feature"] for update in raman["peak_updates"]} == {"mos2_e2g_like", "mos2_a1g_like"}

    pl = match_pl_peaks(
        "mos2",
        [{"peak_id": "pl1", "position": 1.84, "position_unit": "eV", "position_eV": 1.84, "prominence": 10.0}],
        x_unit="eV",
    )
    assert pl["assignment_source"] == "ea.materials.builtin:mos2:pl:v0.2"
    assert pl["possible_interpretations"][0]["confidence"] == "medium"
    assert pl["peak_updates"][0]["assignment_feature"] == "mos2_near_band_edge_emission"

    xrd = match_xrd_peaks(
        "mos2",
        [{"peak_id": "x1", "two_theta_deg": 14.4, "d_spacing_angstrom": 6.15, "prominence": 100.0}],
    )
    assert xrd["assignment_source"] == "ea.materials.builtin:mos2:xrd:v0.2"
    assert xrd["possible_interpretations"][0]["confidence"] == "medium"
    assert xrd["peak_updates"][0]["assignment_feature"] == "mos2_002_layered_reflection"


def test_ws2_material_matchers_return_traceable_screening_assignments() -> None:
    raman = match_raman_peaks(
        "ws2",
        [
            {"peak_id": "w1", "position_cm-1": 356.5},
            {"peak_id": "w2", "position_cm-1": 418.4},
        ],
    )
    assert raman["assignment_source"] == "ea.materials.builtin:ws2:raman:v0.2"
    assert raman["possible_interpretations"][0]["confidence"] == "medium"
    assert raman["possible_interpretations"][0]["rule"] == "ws2_e2g_2la_a1g_pair_screen"
    assert {update["assignment_feature"] for update in raman["peak_updates"]} == {
        "ws2_e2g_2la_like",
        "ws2_a1g_like",
    }

    pl = match_pl_peaks(
        "ws2",
        [{"peak_id": "wpl1", "position": 1.98, "position_unit": "eV", "position_eV": 1.98, "prominence": 7.0}],
        x_unit="eV",
    )
    assert pl["assignment_source"] == "ea.materials.builtin:ws2:pl:v0.2"
    assert pl["possible_interpretations"][0]["confidence"] == "medium"
    assert pl["peak_updates"][0]["assignment_feature"] == "ws2_near_band_edge_emission"

    xrd = match_xrd_peaks(
        "ws2",
        [{"peak_id": "wx1", "two_theta_deg": 14.3, "d_spacing_angstrom": 6.18, "prominence": 90.0}],
    )
    assert xrd["assignment_source"] == "ea.materials.builtin:ws2:xrd:v0.2"
    assert xrd["possible_interpretations"][0]["confidence"] == "medium"
    assert xrd["peak_updates"][0]["assignment_feature"] == "ws2_002_layered_reflection"


def test_hbn_single_feature_and_xrd_matchers_return_traceable_assignments() -> None:
    raman = match_raman_peaks("hbn", [{"peak_id": "b1", "position_cm-1": 1367.5}])
    assert raman["assignment_source"] == "ea.materials.builtin:hbn:raman:v0.2"
    assert raman["possible_interpretations"][0]["confidence"] == "medium"
    assert raman["possible_interpretations"][0]["evidence"] == ["b1"]
    assert raman["peak_updates"][0]["assignment_feature"] == "hbn_e2g_like"

    xrd = match_xrd_peaks(
        "hbn",
        [{"peak_id": "bx1", "two_theta_deg": 26.7, "d_spacing_angstrom": 3.34, "prominence": 100.0}],
    )
    assert xrd["assignment_source"] == "ea.materials.builtin:hbn:xrd:v0.2"
    assert xrd["possible_interpretations"][0]["confidence"] == "medium"
    assert xrd["peak_updates"][0]["assignment_feature"] == "hbn_002_layered_reflection"


def test_materials_cli_lists_and_shows_assignments(capsys) -> None:
    assert main(["materials", "list"]) == 0
    listed = _json_output(capsys)
    assert {item["material_id"] for item in listed["materials"]} >= {"hbn", "mos2", "ws2"}

    assert main(["materials", "assignments", "mos2", "--method", "xrd"]) == 0
    xrd = _json_output(capsys)
    assert xrd["assignment_source"] == "ea.materials.builtin:mos2:xrd:v0.2"
    assert xrd["feature_rules"][0]["feature"] == "mos2_002_layered_reflection"

    assert main(["materials", "show", "hBN"]) == 0
    hbn = _json_output(capsys)
    assert hbn["material_id"] == "hbn"

    assert main(["materials", "assignments", "ws2", "--method", "pl"]) == 0
    pl = _json_output(capsys)
    assert pl["assignment_source"] == "ea.materials.builtin:ws2:pl:v0.2"
