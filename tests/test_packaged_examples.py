from __future__ import annotations

import importlib.util
import zipfile
from pathlib import Path

from ea.evaluation import run_project_evaluation
from ea.healthcheck import run_healthcheck
from ea.release_manifest import build_release_manifest
from ea.release_package import write_release_package
from ea.storage import read_yaml


RAMAN_EXAMPLE_ROOT = Path("examples/public-raman-project")
RAMAN_EXAMPLE_MANIFEST = RAMAN_EXAMPLE_ROOT / "example_manifest.yml"
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


def test_packaged_example_is_in_default_release_inputs_and_package(tmp_path: Path) -> None:
    manifest = build_release_manifest(Path.cwd())
    paths = {record["path"] for record in manifest["release_inputs"]["files"]}

    assert "examples/public-raman-project/example_manifest.yml" in paths
    assert "examples/public-raman-project/EA_PROJECT.md" in paths
    assert "examples/public-raman-project/reports/rpt-public-raman-example-20260602-001.md" in paths
    assert "examples/public-raman-project/source-inputs/raw/mos2-raman-public-fixture.txt" in paths
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
