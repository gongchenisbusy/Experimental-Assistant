from __future__ import annotations

import json
from pathlib import Path

import pytest

from ea.cli import main
from ea.data_import import apply_import, preview_import
from ea.projects import initialize_project
from ea.pl import inspect_pl_file


FIXTURE_PL = Path(
    "tests/fixtures/public/test-case-001/raw_data/MoS-PL-2(1).txt"
).resolve()


@pytest.mark.parametrize(
    ("encoding", "content"),
    [
        ("utf-8", "波数_cm1,强度\n100,5\n"),
        ("utf-8-sig", "波数_cm1,强度\n100,5\n"),
        ("gb18030", "波数_cm1,强度\n100,5\n"),
        ("cp1252", "wavelength_nm;absorbance\n500;0.25\n"),
    ],
)
def test_preview_detects_supported_encodings_and_delimiters(tmp_path: Path, encoding: str, content: str) -> None:
    suffix = ".csv" if "," in content else ".txt"
    source = tmp_path / f"中文 数据{suffix}"
    source.write_bytes(content.encode(encoding))

    result = preview_import(source)

    assert result["status"] == "ready"
    assert result["read_only"] is True
    assert result["encoding"] in {encoding, "utf-8-sig", "utf-8", "gb18030", "cp936", "cp1252"}
    assert result["delimiter_name"] in {"comma", "semicolon"}
    assert result["columns"]
    assert len(result["sha256"]) == 64


def test_preview_supports_tab_and_unit_proposals(tmp_path: Path) -> None:
    source = tmp_path / "raman.tsv"
    source.write_text("raman_shift_cm1\tintensity\n100\t5\n", encoding="utf-8")

    result = preview_import(source)

    assert result["delimiter_name"] == "tab"
    assert result["unit_proposals"]["raman_shift_cm1"] == "cm^-1"


def test_preview_rejects_directory_binary_and_symlink_by_default(tmp_path: Path) -> None:
    with pytest.raises(IsADirectoryError):
        preview_import(tmp_path)

    binary = tmp_path / "binary.dat"
    binary.write_bytes(b"a\x00b")
    with pytest.raises(ValueError, match="binary"):
        preview_import(binary)

    source = tmp_path / "source.csv"
    source.write_text("x,y\n1,2\n", encoding="utf-8")
    link = tmp_path / "link.csv"
    try:
        link.symlink_to(source)
    except OSError:
        pytest.skip("symlinks are unavailable on this platform")
    with pytest.raises(PermissionError, match="Symlink import"):
        preview_import(link)


def test_apply_requires_same_preview_hash_and_confirmation(tmp_path: Path) -> None:
    project = tmp_path / "project"
    initialize_project(
        project,
        project_name="Import project",
        research_direction="test",
        material_system="MoS2",
        experiment_type="Raman",
    )
    source = tmp_path / "数据.csv"
    source.write_text("raman_shift_cm1,intensity\n100,5\n", encoding="utf-8")
    preview = preview_import(source)

    plan = apply_import(project, source, characterization_type="raman")
    assert plan["status"] == "needs_confirmation"
    assert not list((project / "raw" / "raman").glob("*/*"))

    with pytest.raises(ValueError, match="source changed"):
        apply_import(
            project,
            source,
            characterization_type="raman",
            preview_hash="0" * 64,
            confirmed=True,
        )

    result = apply_import(
        project,
        source,
        characterization_type="raman",
        preview_hash=preview["sha256"],
        confirmed=True,
    )
    assert result["status"] == "completed"
    assert Path(result["project_raw_path"]).read_bytes() == source.read_bytes()


def test_import_cli_preview_is_compact_json(tmp_path: Path, capsys) -> None:
    source = tmp_path / "sample.csv"
    source.write_text("temperature_C,value\n25,1\n", encoding="utf-8")

    assert main(["import", "preview", str(source)]) == 0
    result = json.loads(capsys.readouterr().out)

    assert result["read_only"] is True
    assert result["unit_proposals"]["temperature_C"] == "degC"


def test_method_aware_pl_preview_matches_pl_inspection() -> None:
    inspection = inspect_pl_file(FIXTURE_PL)

    preview = preview_import(FIXTURE_PL, characterization_type="pl")

    assert preview["characterization_type"] == "pl"
    assert preview["row_count"] == inspection.row_count == 8280
    assert preview["columns"] == inspection.columns == ["col_0", "col_1"]
    assert preview["x_column_candidate"] == inspection.x_column_candidate
    assert preview["y_column_candidate"] == inspection.y_column_candidate
    assert preview["x_unit"] == inspection.x_unit == "eV"
    assert preview["method_metadata"]["instrument_metadata"]["instrument_model"] == "LabRAM HR Evol"


def test_import_cli_accepts_method_aware_preview(tmp_path: Path, capsys) -> None:
    assert main(
        ["import", "preview", str(FIXTURE_PL), "--characterization-type", "pl"]
    ) == 0
    result = json.loads(capsys.readouterr().out)

    assert result["row_count"] == 8280
    assert result["x_unit"] == "eV"
