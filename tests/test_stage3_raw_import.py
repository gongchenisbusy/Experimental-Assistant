from pathlib import Path

import pytest

from ea.raw_import import RawPathBoundaryError, assert_not_raw_output_path, import_raw_file
from ea.storage import read_yaml


def test_raw_import_copies_readonly_file_and_writes_metadata(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("300\t100\n301\t120\n", encoding="utf-8")
    project = tmp_path / "project"

    result = import_raw_file(
        project,
        source,
        project_id="project-20260602-mos2",
        sample_refs=["sample-1"],
        imported_at="2026-06-02T14:00:00",
    )

    assert result.import_status == "imported"
    assert result.project_raw_path is not None
    assert result.project_raw_path.exists()
    assert result.project_raw_path.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
    assert not (result.project_raw_path.stat().st_mode & 0o222)

    metadata = read_yaml(result.metadata_path)
    assert metadata["original_source_path"] == str(source)
    assert metadata["project_raw_path"].startswith("raw/raman/char-")
    assert metadata["sha256"] == result.sha256
    assert metadata["file_size_bytes"] == source.stat().st_size
    assert metadata["import_status"] == "imported"
    assert metadata["sample_refs"] == ["sample-1"]
    assert metadata["provenance_refs"]


def test_raw_import_uses_reviewed_date_ids_and_project_relative_source_refs(tmp_path: Path) -> None:
    project = tmp_path / "project"
    source = project / "source-inputs" / "raw" / "source.txt"
    source.parent.mkdir(parents=True)
    source.write_text("300\t100\n301\t120\n", encoding="utf-8")

    result = import_raw_file(
        project,
        source,
        project_id="project-20260602-mos2",
        sample_refs=["sample-1"],
        imported_at="2026-06-02T14:00:00",
    )

    assert result.characterization_id == "char-20260602-001"
    metadata = read_yaml(result.metadata_path)
    assert metadata["original_source_path"] == "source-inputs/raw/source.txt"
    provenance = read_yaml(project / "provenance" / f"{metadata['provenance_refs'][0]}.yml")
    assert provenance["provenance_id"] == "prov-20260602-001"
    assert provenance["inputs"]["files"] == ["source-inputs/raw/source.txt"]


def test_duplicate_raw_import_creates_alias_without_second_copy(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    renamed = tmp_path / "renamed.txt"
    source.write_text("300\t100\n301\t120\n", encoding="utf-8")
    renamed.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    project = tmp_path / "project"

    first = import_raw_file(
        project,
        source,
        project_id="project-20260602-mos2",
        sample_refs=["sample-1"],
    )
    second = import_raw_file(
        project,
        renamed,
        project_id="project-20260602-mos2",
        sample_refs=["sample-1"],
        imported_at="2026-06-02T14:05:00",
    )

    assert second.import_status == "duplicate_alias"
    assert second.project_raw_path is None
    assert second.canonical_metadata_path == first.metadata_path

    raw_files = [
        path
        for path in (project / "raw").glob("raman/*/*")
        if path.name != "metadata.yml"
    ]
    assert raw_files == [first.project_raw_path]

    canonical = read_yaml(first.metadata_path)
    alias_metadata = read_yaml(second.metadata_path)
    assert canonical["aliases"][0]["original_filename"] == "renamed.txt"
    assert alias_metadata["canonical_raw_ref"] == first.characterization_id
    assert alias_metadata["import_status"] == "duplicate_alias"


def test_duplicate_raw_import_with_ref_conflict_needs_review(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    renamed = tmp_path / "renamed.txt"
    source.write_text("300\t100\n301\t120\n", encoding="utf-8")
    renamed.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    project = tmp_path / "project"

    first = import_raw_file(
        project,
        source,
        project_id="project-20260602-mos2",
        sample_refs=["sample-1"],
    )
    second = import_raw_file(
        project,
        renamed,
        project_id="project-20260602-mos2",
        sample_refs=["sample-2"],
    )

    assert second.import_status == "needs_review"
    assert second.canonical_metadata_path == first.metadata_path
    canonical = read_yaml(first.metadata_path)
    assert canonical["aliases"] == []
    alias_metadata = read_yaml(second.metadata_path)
    assert alias_metadata["alias_reason"] == "same_sha256_refs_conflict"


def test_processed_outputs_are_rejected_inside_raw_tree(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / "raw").mkdir(parents=True)
    assert_not_raw_output_path(project, project / "processed" / "result.csv")
    with pytest.raises(RawPathBoundaryError):
        assert_not_raw_output_path(project, project / "raw" / "raman" / "bad.csv")
