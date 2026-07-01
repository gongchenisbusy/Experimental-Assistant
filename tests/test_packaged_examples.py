from __future__ import annotations

import importlib.util
import zipfile
from pathlib import Path

from ea.evaluation import run_project_evaluation
from ea.healthcheck import run_healthcheck
from ea.release_manifest import build_release_manifest
from ea.release_package import write_release_package
from ea.storage import read_markdown_record, read_yaml


RAMAN_EXAMPLE_ROOT = Path("examples/public-raman-project")
RAMAN_EXAMPLE_MANIFEST = RAMAN_EXAMPLE_ROOT / "example_manifest.yml"
FTIR_EXAMPLE_ROOT = Path("examples/public-ftir-assignment-project")
FTIR_EXAMPLE_MANIFEST = FTIR_EXAMPLE_ROOT / "example_manifest.yml"
UV_VIS_EXAMPLE_ROOT = Path("examples/public-uv-vis-project")
UV_VIS_EXAMPLE_MANIFEST = UV_VIS_EXAMPLE_ROOT / "example_manifest.yml"
XPS_EXAMPLE_ROOT = Path("examples/public-xps-be-project")
XPS_EXAMPLE_MANIFEST = XPS_EXAMPLE_ROOT / "example_manifest.yml"
FORBIDDEN_PUBLIC_DEFAULTS = [
    "/Users/geecoe",
    "New project 4",
    "zotero.sqlite",
    "Chrome Profile",
    "institution password",
    "tests/fixtures",
]


def _load_builder_module(script_name: str):
    script = Path("scripts") / script_name
    spec = importlib.util.spec_from_file_location("build_packaged_example_project", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _text_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if path.is_file() and path.suffix.lower() not in {".png"}]


def test_packaged_public_raman_example_is_public_safe_and_evaluable() -> None:
    manifest = read_yaml(RAMAN_EXAMPLE_MANIFEST)

    assert manifest["example_type"] == "packaged_public_project"
    assert manifest["project_id"] == "prj-public-raman-example"
    assert manifest["public_boundary"]["uses_developer_machine_defaults"] is False
    assert manifest["public_boundary"]["zotero_enabled"] is False
    assert manifest["public_boundary"]["browser_assist_enabled"] is False
    assert manifest["validation"]["healthcheck_status"] == "pass"
    assert manifest["validation"]["evaluation_status"] == "pass"
    for rel in manifest["key_artifacts"].values():
        assert (RAMAN_EXAMPLE_ROOT / rel).exists(), rel

    raw_metadata = read_yaml(RAMAN_EXAMPLE_ROOT / manifest["key_artifacts"]["raw_metadata"])
    assert raw_metadata["original_source_path"] == manifest["key_artifacts"]["source_input"]

    healthcheck = run_healthcheck(RAMAN_EXAMPLE_ROOT)
    assert healthcheck["status"] == "pass"
    assert healthcheck["findings"] == []

    evaluation = run_project_evaluation(RAMAN_EXAMPLE_ROOT, write_report=False, created_at="2026-06-02T17:30:00")
    assert evaluation["status"] == "pass"
    assert evaluation["error_count"] == 0
    assert evaluation["warning_count"] == 0
    assert evaluation["material_assignments"]["traceable_feature_count"] >= 1

    for path in _text_files(RAMAN_EXAMPLE_ROOT):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for forbidden in FORBIDDEN_PUBLIC_DEFAULTS:
            assert forbidden not in text, path


def test_packaged_public_xps_be_example_is_public_safe_and_evaluable() -> None:
    manifest = read_yaml(XPS_EXAMPLE_MANIFEST)

    assert manifest["example_type"] == "packaged_public_project"
    assert manifest["project_id"] == "prj-public-xps-be-example"
    assert manifest["public_boundary"]["uses_developer_machine_defaults"] is False
    assert manifest["public_boundary"]["zotero_enabled"] is False
    assert manifest["public_boundary"]["browser_assist_enabled"] is False
    assert manifest["workflow_boundary"]["auto_applies_binding_energy_candidates"] is False
    assert manifest["workflow_boundary"]["auto_calibrates_or_charge_corrects"] is False
    assert manifest["workflow_boundary"]["proves_chemical_state_or_composition"] is False
    assert manifest["workflow_boundary"]["writes_confirmed_memory"] is False
    assert manifest["suggestion_id"] == "suggestion-20260603-001"
    assert manifest["o1s_suggestion_id"] == "suggestion-20260603-002"
    assert manifest["suggestion_ids"] == ["suggestion-20260603-001", "suggestion-20260603-002"]
    assert manifest["validation"]["healthcheck_status"] == "pass"
    assert manifest["validation"]["evaluation_status"] == "pass"
    for rel in manifest["key_artifacts"].values():
        if isinstance(rel, list):
            for item in rel:
                assert (XPS_EXAMPLE_ROOT / item).exists(), item
        else:
            assert (XPS_EXAMPLE_ROOT / rel).exists(), rel

    suggestion = read_yaml(XPS_EXAMPLE_ROOT / manifest["key_artifacts"]["suggestion_record"])
    o1s_source_packet = read_yaml(XPS_EXAMPLE_ROOT / manifest["key_artifacts"]["o1s_source_packet"])
    o1s_suggestion = read_yaml(XPS_EXAMPLE_ROOT / manifest["key_artifacts"]["o1s_suggestion_record"])
    report = (XPS_EXAMPLE_ROOT / manifest["key_artifacts"]["report"]).read_text(encoding="utf-8")
    memory_candidates = [
        (XPS_EXAMPLE_ROOT / rel).read_text(encoding="utf-8")
        for rel in manifest["key_artifacts"]["memory_candidates"]
    ]
    assert suggestion["ready_for_user_review_count"] == 5
    assert {candidate["suggestion_type"] for candidate in suggestion["candidates"]} == {"binding_energy_candidate"}
    assert o1s_source_packet["source_library_ref"] == "builtin:oxide_o1s_binding_energy"
    assert o1s_source_packet["candidate_count"] == 4
    assert o1s_suggestion["ready_for_user_review_count"] == 4
    assert {candidate["suggestion_type"] for candidate in o1s_suggestion["candidates"]} == {
        "binding_energy_candidate"
    }
    assert "builtin-xps-thermo-o" in o1s_suggestion["reference_ids"]
    assert "Source-backed XPS parameter suggestions" in report
    assert "suggestion-20260603-002" in report
    assert o1s_suggestion["source_packet_ref"] == "suggestions/xps/source-packets/xps_o1s_oxide_candidates.yml"
    assert "xps-builtin-o1s-silica-organic-co-binding-energy-candidate" in report
    assert "Not an oxygen-vacancy proof" in report
    assert "binding_energy_candidate" in report
    assert "[1]" in report and "[2]" in report and "[3]" in report and "[7]" in report
    assert any(
        "xps-builtin-o1s-silica-organic-co-binding-energy-candidate" in text
        for text in memory_candidates
    )
    assert all("does not copy values into processing parameters" in text for text in memory_candidates)
    assert all("prove chemical state/composition" in text for text in memory_candidates)

    healthcheck = run_healthcheck(XPS_EXAMPLE_ROOT)
    assert healthcheck["status"] == "pass"
    assert healthcheck["findings"] == []

    evaluation = run_project_evaluation(XPS_EXAMPLE_ROOT, write_report=False, created_at="2026-06-03T09:30:00")
    assert evaluation["status"] == "pass"
    assert evaluation["error_count"] == 0
    assert evaluation["warning_count"] == 0

    for path in _text_files(XPS_EXAMPLE_ROOT):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for forbidden in FORBIDDEN_PUBLIC_DEFAULTS:
            assert forbidden not in text, path


def test_packaged_public_ftir_assignment_example_is_public_safe_and_evaluable() -> None:
    manifest = read_yaml(FTIR_EXAMPLE_MANIFEST)

    assert manifest["example_type"] == "packaged_public_project"
    assert manifest["project_id"] == "prj-public-ftir-assignment-example"
    assert manifest["public_boundary"]["uses_developer_machine_defaults"] is False
    assert manifest["public_boundary"]["zotero_enabled"] is False
    assert manifest["public_boundary"]["browser_assist_enabled"] is False
    assert manifest["workflow_boundary"]["auto_applies_assignments"] is False
    assert manifest["workflow_boundary"]["proves_functional_groups_or_composition"] is False
    assert manifest["workflow_boundary"]["writes_confirmed_memory"] is False
    assert manifest["workflow_boundary"]["performs_live_lookup_or_pdf_download"] is False
    assert manifest["suggestion_id"] == "suggestion-20260604-001"
    assert manifest["validation"]["healthcheck_status"] == "pass"
    assert manifest["validation"]["evaluation_status"] == "pass"
    for rel in manifest["key_artifacts"].values():
        if isinstance(rel, list):
            for item in rel:
                assert (FTIR_EXAMPLE_ROOT / item).exists(), item
        else:
            assert (FTIR_EXAMPLE_ROOT / rel).exists(), rel

    source_packet = read_yaml(FTIR_EXAMPLE_ROOT / manifest["key_artifacts"]["source_packet"])
    suggestion = read_yaml(FTIR_EXAMPLE_ROOT / manifest["key_artifacts"]["suggestion_record"])
    review_package = read_yaml(FTIR_EXAMPLE_ROOT / manifest["key_artifacts"]["review_package"])
    report = (FTIR_EXAMPLE_ROOT / manifest["key_artifacts"]["report"]).read_text(encoding="utf-8")
    memory_records = [
        read_markdown_record(FTIR_EXAMPLE_ROOT / rel)
        for rel in manifest["key_artifacts"]["memory_candidates"]
    ]

    assert source_packet["source_library_ref"] == "builtin:generic_materials"
    assert source_packet["candidate_count"] == 4
    assert "builtin-ftir-socrates-2001" in source_packet["reference_seeds"]
    assert suggestion["ready_for_user_review_count"] == 4
    assert suggestion["needs_reference_registration_count"] == 0
    assert suggestion["no_feature_match_count"] == 0
    assert {candidate["status"] for candidate in suggestion["candidates"]} == {"ready_for_user_review"}
    assert {candidate["auto_applied"] for candidate in suggestion["candidates"]} == {False}
    assert "builtin-ftir-socrates-2001" in suggestion["reference_ids"]
    assert "builtin-ftir-colthup-1990" in suggestion["reference_ids"]
    assert review_package["review_target_type"] == "ftir_assignment_suggestions"
    assert review_package["selected_status_counts"]["ready_for_user_review"] == 4
    assert "Source-backed FTIR assignment suggestions" in report
    assert "ftir-builtin-carbonyl-co-stretching-generic" in report
    assert "ftir-builtin-sio-stretching-generic" in report
    assert "[1]" in report and "[2]" in report
    assert "不能单独证明化学组成" in report
    assert len(memory_records) == 2
    memory_bodies = [body for _, body in memory_records]
    assert any("ftir-builtin-carbonyl-co-stretching-generic" in body for body in memory_bodies)
    assert any("ftir-builtin-sio-stretching-generic" in body for body in memory_bodies)
    for frontmatter, body in memory_records:
        assert frontmatter["status"] == "draft"
        assert frontmatter["category"] == "interpretation"
        assert manifest["key_artifacts"]["suggestion_record"] in frontmatter["source_refs"]
        assert "does not by itself prove chemical composition" in body

    healthcheck = run_healthcheck(FTIR_EXAMPLE_ROOT)
    assert healthcheck["status"] == "pass"
    assert healthcheck["findings"] == []

    evaluation = run_project_evaluation(FTIR_EXAMPLE_ROOT, write_report=False, created_at="2026-06-04T10:30:00")
    assert evaluation["status"] == "pass"
    assert evaluation["error_count"] == 0
    assert evaluation["warning_count"] == 0

    for path in _text_files(FTIR_EXAMPLE_ROOT):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for forbidden in FORBIDDEN_PUBLIC_DEFAULTS:
            assert forbidden not in text, path


def test_packaged_public_uv_vis_example_is_public_safe_and_evaluable() -> None:
    manifest = read_yaml(UV_VIS_EXAMPLE_MANIFEST)

    assert manifest["example_type"] == "packaged_public_project"
    assert manifest["project_id"] == "prj-public-uv-vis-example"
    assert manifest["public_boundary"]["uses_developer_machine_defaults"] is False
    assert manifest["public_boundary"]["zotero_enabled"] is False
    assert manifest["public_boundary"]["browser_assist_enabled"] is False
    assert manifest["workflow_boundary"]["source_backed_suggestion_workflow"] is False
    assert manifest["workflow_boundary"]["proves_band_gap_or_transition"] is False
    assert manifest["workflow_boundary"]["proves_defect_or_thickness_effect"] is False
    assert manifest["workflow_boundary"]["applies_numeric_substrate_or_background_correction"] is False
    assert manifest["workflow_boundary"]["writes_confirmed_memory"] is False
    assert manifest["screening_summary"]["tauc_status"] == "screening_fit_recorded"
    assert manifest["screening_summary"]["derivative_status"] == "screening_derivative_recorded"
    assert manifest["screening_summary"]["correction_context_status"] == "reviewed_correction_context_recorded"
    assert manifest["validation"]["healthcheck_status"] == "pass"
    assert manifest["validation"]["evaluation_status"] == "pass"
    for rel in manifest["key_artifacts"].values():
        assert (UV_VIS_EXAMPLE_ROOT / rel).exists(), rel

    uv_vis = read_yaml(UV_VIS_EXAMPLE_ROOT / manifest["key_artifacts"]["uv_vis_metadata"])
    report = (UV_VIS_EXAMPLE_ROOT / manifest["key_artifacts"]["report"]).read_text(encoding="utf-8")
    correction_context = read_yaml(UV_VIS_EXAMPLE_ROOT / manifest["key_artifacts"]["correction_context"])

    assert uv_vis["peak_analysis"]["tauc_analysis"]["status"] == "screening_fit_recorded"
    assert abs(uv_vis["peak_analysis"]["tauc_analysis"]["intercept_energy_eV"] - 2.05) < 0.05
    assert "Screening Tauc/Kubelka-Munk fit only" in uv_vis["peak_analysis"]["tauc_analysis"]["boundary"]
    assert uv_vis["peak_analysis"]["derivative_analysis"]["status"] == "screening_derivative_recorded"
    assert "screening-only" in uv_vis["peak_analysis"]["derivative_analysis"]["boundary"]
    assert uv_vis["peak_analysis"]["correction_context"]["status"] == "reviewed_correction_context_recorded"
    assert "metadata/provenance record only" in uv_vis["peak_analysis"]["correction_context"]["boundary"]
    assert correction_context["record_ref"] == manifest["key_artifacts"]["correction_context"]
    assert "Tauc/Kubelka-Munk screening" in report
    assert "Derivative screening" in report
    assert "Correction context 记录" in report
    assert "不等同于最终 optical band gap" in report
    assert "不执行自动数值校正" in report
    assert "尚未绑定外部文献或项目参考谱" in report

    healthcheck = run_healthcheck(UV_VIS_EXAMPLE_ROOT)
    assert healthcheck["status"] == "pass"
    assert healthcheck["findings"] == []

    evaluation = run_project_evaluation(UV_VIS_EXAMPLE_ROOT, write_report=False, created_at="2026-06-05T11:30:00")
    assert evaluation["status"] == "pass"
    assert evaluation["error_count"] == 0
    assert evaluation["warning_count"] == 0

    for path in _text_files(UV_VIS_EXAMPLE_ROOT):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for forbidden in FORBIDDEN_PUBLIC_DEFAULTS:
            assert forbidden not in text, path


def test_packaged_example_builders_create_evaluable_projects(tmp_path: Path) -> None:
    builder = _load_builder_module("build_packaged_example_project.py")
    output = tmp_path / "public-raman-project"

    summary = builder.build_example(output, force=True)

    assert summary["healthcheck_status"] == "pass"
    assert summary["evaluation_status"] == "pass"
    assert (output / "example_manifest.yml").exists()
    assert run_healthcheck(output)["status"] == "pass"

    xps_builder = _load_builder_module("build_public_xps_be_example_project.py")
    xps_output = tmp_path / "public-xps-be-project"

    xps_summary = xps_builder.build_example(xps_output, force=True)

    assert xps_summary["healthcheck_status"] == "pass"
    assert xps_summary["evaluation_status"] == "pass"
    assert xps_summary["o1s_suggestion_id"] == "suggestion-20260603-002"
    assert xps_summary["memory_candidate_count"] == 3
    assert (xps_output / "example_manifest.yml").exists()
    assert run_healthcheck(xps_output)["status"] == "pass"

    ftir_builder = _load_builder_module("build_public_ftir_assignment_example_project.py")
    ftir_output = tmp_path / "public-ftir-assignment-project"

    ftir_summary = ftir_builder.build_example(ftir_output, force=True)

    assert ftir_summary["healthcheck_status"] == "pass"
    assert ftir_summary["evaluation_status"] == "pass"
    assert ftir_summary["suggestion_id"] == "suggestion-20260604-001"
    assert ftir_summary["memory_candidate_count"] == 2
    assert (ftir_output / "example_manifest.yml").exists()
    assert run_healthcheck(ftir_output)["status"] == "pass"

    uv_vis_builder = _load_builder_module("build_public_uv_vis_example_project.py")
    uv_vis_output = tmp_path / "public-uv-vis-project"

    uv_vis_summary = uv_vis_builder.build_example(uv_vis_output, force=True)

    assert uv_vis_summary["healthcheck_status"] == "pass"
    assert uv_vis_summary["evaluation_status"] == "pass"
    assert uv_vis_summary["tauc_status"] == "screening_fit_recorded"
    assert uv_vis_summary["derivative_status"] == "screening_derivative_recorded"
    assert uv_vis_summary["correction_context_status"] == "reviewed_correction_context_recorded"
    assert (uv_vis_output / "example_manifest.yml").exists()
    assert run_healthcheck(uv_vis_output)["status"] == "pass"


def test_packaged_example_is_in_default_release_inputs_and_package(tmp_path: Path) -> None:
    manifest = build_release_manifest(Path.cwd())
    paths = {record["path"] for record in manifest["release_inputs"]["files"]}

    assert "examples/public-raman-project/example_manifest.yml" in paths
    assert "examples/public-raman-project/EA_PROJECT.md" in paths
    assert "examples/public-raman-project/reports/rpt-public-raman-example-20260602-001.md" in paths
    assert "examples/public-raman-project/source-inputs/raw/mos2-raman-public-fixture.txt" in paths
    assert "examples/public-ftir-assignment-project/example_manifest.yml" in paths
    assert "examples/public-ftir-assignment-project/EA_PROJECT.md" in paths
    assert "examples/public-ftir-assignment-project/reports/rpt-public-ftir-assignment-example-20260604-001.md" in paths
    assert "examples/public-ftir-assignment-project/suggestions/ftir/source-packets/ftir_hybrid_assignment_candidates.yml" in paths
    assert "examples/public-ftir-assignment-project/suggestions/ftir/suggestion-20260604-001/ftir_assignment_suggestions.yml" in paths
    assert "examples/public-ftir-assignment-project/memory/candidates/memcand-20260604-001.md" in paths
    assert "examples/public-ftir-assignment-project/source-inputs/raw/polymer-silica-ftir-public-fixture.txt" in paths
    assert "examples/public-uv-vis-project/example_manifest.yml" in paths
    assert "examples/public-uv-vis-project/EA_PROJECT.md" in paths
    assert "examples/public-uv-vis-project/reports/rpt-public-uv-vis-example-20260605-001.md" in paths
    assert "examples/public-uv-vis-project/processed/sample-example-semiconductor-film-uv-vis-001/uv_vis/res-public-uv-vis-example-uv-vis-20260605-001/uv_vis_tauc.csv" in paths
    assert "examples/public-uv-vis-project/processed/sample-example-semiconductor-film-uv-vis-001/uv_vis/res-public-uv-vis-example-uv-vis-20260605-001/uv_vis_derivative.csv" in paths
    assert "examples/public-uv-vis-project/source-inputs/raw/semiconductor-film-uv-vis-public-fixture.txt" in paths
    assert "examples/public-xps-be-project/example_manifest.yml" in paths
    assert "examples/public-xps-be-project/EA_PROJECT.md" in paths
    assert "examples/public-xps-be-project/reports/rpt-public-xps-be-example-20260603-001.md" in paths
    assert "examples/public-xps-be-project/suggestions/xps/suggestion-20260603-001/xps_parameter_suggestions.yml" in paths
    assert "examples/public-xps-be-project/suggestions/xps/source-packets/xps_o1s_oxide_candidates.yml" in paths
    assert "examples/public-xps-be-project/suggestions/xps/suggestion-20260603-002/xps_parameter_suggestions.yml" in paths
    assert "examples/public-xps-be-project/memory/candidates/memcand-20260603-003.md" in paths
    assert "examples/public-xps-be-project/source-inputs/raw/si-sio2-xps-public-fixture.txt" in paths

    package = write_release_package(Path.cwd(), output=tmp_path / "release.zip", archive_root="ea-release-example-test")
    with zipfile.ZipFile(package["archive_path"]) as archive:
        names = set(archive.namelist())
        assert "ea-release-example-test/examples/public-raman-project/example_manifest.yml" in names
        assert "ea-release-example-test/examples/public-raman-project/EA_PROJECT.md" in names
        assert "ea-release-example-test/examples/public-raman-project/README.md" in names
        assert "ea-release-example-test/examples/public-ftir-assignment-project/example_manifest.yml" in names
        assert "ea-release-example-test/examples/public-ftir-assignment-project/EA_PROJECT.md" in names
        assert "ea-release-example-test/examples/public-ftir-assignment-project/README.md" in names
        assert (
            "ea-release-example-test/examples/public-ftir-assignment-project/suggestions/ftir/source-packets/ftir_hybrid_assignment_candidates.yml"
            in names
        )
        assert (
            "ea-release-example-test/examples/public-ftir-assignment-project/suggestions/ftir/suggestion-20260604-001/ftir_assignment_suggestions.yml"
            in names
        )
        assert "ea-release-example-test/examples/public-ftir-assignment-project/memory/candidates/memcand-20260604-001.md" in names
        assert "ea-release-example-test/examples/public-uv-vis-project/example_manifest.yml" in names
        assert "ea-release-example-test/examples/public-uv-vis-project/EA_PROJECT.md" in names
        assert "ea-release-example-test/examples/public-uv-vis-project/README.md" in names
        assert (
            "ea-release-example-test/examples/public-uv-vis-project/processed/sample-example-semiconductor-film-uv-vis-001/uv_vis/res-public-uv-vis-example-uv-vis-20260605-001/uv_vis_tauc.csv"
            in names
        )
        assert (
            "ea-release-example-test/examples/public-uv-vis-project/processed/sample-example-semiconductor-film-uv-vis-001/uv_vis/res-public-uv-vis-example-uv-vis-20260605-001/uv_vis_derivative.csv"
            in names
        )
        assert "ea-release-example-test/examples/public-xps-be-project/example_manifest.yml" in names
        assert "ea-release-example-test/examples/public-xps-be-project/EA_PROJECT.md" in names
        assert "ea-release-example-test/examples/public-xps-be-project/README.md" in names
        assert (
            "ea-release-example-test/examples/public-xps-be-project/suggestions/xps/source-packets/xps_o1s_oxide_candidates.yml"
            in names
        )
        assert (
            "ea-release-example-test/examples/public-xps-be-project/suggestions/xps/suggestion-20260603-002/xps_parameter_suggestions.yml"
            in names
        )
        assert "ea-release-example-test/examples/public-xps-be-project/memory/candidates/memcand-20260603-003.md" in names
