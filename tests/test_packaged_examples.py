from __future__ import annotations

import importlib.util
import zipfile
from pathlib import Path

from ea.evaluation import run_project_evaluation
from ea.healthcheck import run_healthcheck
from ea.release_manifest import build_release_manifest
from ea.release_package import write_release_package
from ea.storage import read_yaml


EXAMPLE_ROOT = Path("examples/public-raman-project")
EXAMPLE_MANIFEST = EXAMPLE_ROOT / "example_manifest.yml"
FORBIDDEN_PUBLIC_DEFAULTS = [
    "/Users/geecoe",
    "New project 4",
    "zotero.sqlite",
    "Chrome Profile",
    "institution password",
    "tests/fixtures",
]


def _load_builder_module():
    script = Path("scripts/build_packaged_example_project.py")
    spec = importlib.util.spec_from_file_location("build_packaged_example_project", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _text_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if path.is_file() and path.suffix.lower() not in {".png"}]


def test_packaged_public_raman_example_is_public_safe_and_evaluable() -> None:
    manifest = read_yaml(EXAMPLE_MANIFEST)

    assert manifest["example_type"] == "packaged_public_project"
    assert manifest["project_id"] == "prj-public-raman-example"
    assert manifest["public_boundary"]["uses_developer_machine_defaults"] is False
    assert manifest["public_boundary"]["zotero_enabled"] is False
    assert manifest["public_boundary"]["browser_assist_enabled"] is False
    assert manifest["validation"]["healthcheck_status"] == "pass"
    assert manifest["validation"]["evaluation_status"] == "pass"
    for rel in manifest["key_artifacts"].values():
        assert (EXAMPLE_ROOT / rel).exists(), rel

    raw_metadata = read_yaml(EXAMPLE_ROOT / manifest["key_artifacts"]["raw_metadata"])
    assert raw_metadata["original_source_path"] == manifest["key_artifacts"]["source_input"]

    healthcheck = run_healthcheck(EXAMPLE_ROOT)
    assert healthcheck["status"] == "pass"
    assert healthcheck["findings"] == []

    evaluation = run_project_evaluation(EXAMPLE_ROOT, write_report=False, created_at="2026-06-02T17:30:00")
    assert evaluation["status"] == "pass"
    assert evaluation["error_count"] == 0
    assert evaluation["warning_count"] == 0
    assert evaluation["material_assignments"]["traceable_feature_count"] >= 1

    for path in _text_files(EXAMPLE_ROOT):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for forbidden in FORBIDDEN_PUBLIC_DEFAULTS:
            assert forbidden not in text, path


def test_packaged_example_builder_creates_evaluable_project(tmp_path: Path) -> None:
    builder = _load_builder_module()
    output = tmp_path / "public-raman-project"

    summary = builder.build_example(output, force=True)

    assert summary["healthcheck_status"] == "pass"
    assert summary["evaluation_status"] == "pass"
    assert (output / "example_manifest.yml").exists()
    assert run_healthcheck(output)["status"] == "pass"


def test_packaged_example_is_in_default_release_inputs_and_package(tmp_path: Path) -> None:
    manifest = build_release_manifest(Path.cwd())
    paths = {record["path"] for record in manifest["release_inputs"]["files"]}

    assert "examples/public-raman-project/example_manifest.yml" in paths
    assert "examples/public-raman-project/EA_PROJECT.md" in paths
    assert "examples/public-raman-project/reports/rpt-public-raman-example-20260602-001.md" in paths
    assert "examples/public-raman-project/source-inputs/raw/mos2-raman-public-fixture.txt" in paths

    package = write_release_package(Path.cwd(), output=tmp_path / "release.zip", archive_root="ea-release-example-test")
    with zipfile.ZipFile(package["archive_path"]) as archive:
        names = set(archive.namelist())
        assert "ea-release-example-test/examples/public-raman-project/example_manifest.yml" in names
        assert "ea-release-example-test/examples/public-raman-project/EA_PROJECT.md" in names
        assert "ea-release-example-test/examples/public-raman-project/README.md" in names
