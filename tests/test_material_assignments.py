from __future__ import annotations

import json

from ea.cli import main
from ea.materials import (
    assignment_candidates,
    available_materials,
    infer_material_from_text,
    match_pl_peaks,
    match_raman_peaks,
    match_xrd_peaks,
)


def _json_output(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def test_builtin_material_library_exposes_mos2_methods() -> None:
    materials = available_materials()
    mos2 = next(item for item in materials if item["material_id"] == "mos2")

    assert mos2["display_name"] == "MoS2"
    assert {"raman", "pl", "xrd"}.issubset(set(mos2["methods"]))
    assert infer_material_from_text("prj-mos2-public") == "mos2"

    raman = assignment_candidates("MoS2", "raman")
    assert raman["assignment_source"] == "ea.materials.builtin:mos2:raman:v0.2"
    assert {rule["feature"] for rule in raman["feature_rules"]} == {"mos2_e2g_like", "mos2_a1g_like"}


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


def test_materials_cli_lists_and_shows_assignments(capsys) -> None:
    assert main(["materials", "list"]) == 0
    listed = _json_output(capsys)
    assert listed["materials"][0]["material_id"] == "mos2"

    assert main(["materials", "assignments", "mos2", "--method", "xrd"]) == 0
    xrd = _json_output(capsys)
    assert xrd["assignment_source"] == "ea.materials.builtin:mos2:xrd:v0.2"
    assert xrd["feature_rules"][0]["feature"] == "mos2_002_layered_reflection"
