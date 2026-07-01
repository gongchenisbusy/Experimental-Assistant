from __future__ import annotations

import json
from pathlib import Path

from ea.cli import main
from ea.projects import initialize_project
from ea.references import build_report_reference_block, import_bibtex_references, register_reference, register_reference_seeds, validate_report_citations
from ea.reports import generate_raman_report
from ea.review import write_review_record
from ea.raman import RamanProcessingRequest, default_processing_parameters, process_raman_result
from ea.raw_import import import_raw_file
from ea.storage import read_markdown_record, read_yaml, write_markdown_record


def _project(tmp_path: Path) -> str:
    outputs = initialize_project(
        tmp_path,
        project_name="Reference demo",
        project_slug="reference-demo",
        research_direction="Raman literature citation workflow",
        material_system="MoS2",
        experiment_type="CVD and Raman",
        created_at="2026-06-30T08:00:00",
    )
    frontmatter, _ = read_markdown_record(outputs["project"])
    return frontmatter["project_id"]


def test_reference_registry_builds_numbered_report_block(tmp_path: Path) -> None:
    project_id = _project(tmp_path)
    ref_a = register_reference(
        tmp_path,
        project_id=project_id,
        citation="Lee C. et al. Anomalous lattice vibrations of single- and few-layer MoS2. ACS Nano (2010).",
        title="Anomalous lattice vibrations of single- and few-layer MoS2",
        authors=["Lee C.", "Yan H."],
        year=2010,
        venue="ACS Nano",
        doi="10.1021/nn1003937",
        url="https://doi.org/10.1021/nn1003937",
        local_path="literature/fulltext/lee-2010.pdf",
        source_type="literature_library",
        created_at="2026-06-30T08:10:00",
    )
    ref_b = register_reference(
        tmp_path,
        project_id=project_id,
        citation="Li H. et al. From bulk to monolayer MoS2. Advanced Functional Materials (2012).",
        year=2012,
        venue="Advanced Functional Materials",
        doi="10.1002/adfm.201102111",
        created_at="2026-06-30T08:11:00",
    )

    ref_a_id = ref_a.stem
    ref_b_id = ref_b.stem
    block = build_report_reference_block(tmp_path, [ref_a_id, ref_b_id, ref_a_id])
    index = read_yaml(tmp_path / "literature" / "references" / "index.yml")

    assert ref_a_id == "ref-20260630-001"
    assert ref_b_id == "ref-20260630-002"
    assert block["reference_ids"] == [ref_a_id, ref_b_id]
    assert block["inline_citation"] == "[1][2]"
    assert "[1] Lee C. et al." in block["references_markdown"]
    assert "DOI: 10.1021/nn1003937" in block["references_markdown"]
    assert "Local: literature/fulltext/lee-2010.pdf" in block["references_markdown"]
    assert index["references"][ref_a_id]["source_type"] == "literature_library"


def test_import_bibtex_references_reuses_duplicates(tmp_path: Path) -> None:
    project_id = _project(tmp_path)
    bibtex = tmp_path / "references.bib"
    bibtex.write_text(
        """
@article{lee2010,
  author = {Lee, C. and Yan, H.},
  title = {Anomalous lattice vibrations of single- and few-layer MoS2},
  journal = {ACS Nano},
  year = {2010},
  doi = {https://doi.org/10.1021/nn1003937},
  url = {https://doi.org/10.1021/nn1003937}
}

@article{lee2010copy,
  author = {Lee, C. and Yan, H.},
  title = {Anomalous lattice vibrations of single- and few-layer MoS2},
  journal = {ACS Nano},
  year = {2010},
  doi = {10.1021/nn1003937}
}

@article{li2012,
  author = {Li, H. and Zhang, Q.},
  title = {From bulk to monolayer MoS2},
  journal = {Advanced Functional Materials},
  year = {2012},
  doi = {10.1002/adfm.201102111}
}
""",
        encoding="utf-8",
    )

    result = import_bibtex_references(
        tmp_path,
        bibtex,
        project_id=project_id,
        created_at="2026-06-30T08:30:00",
    )
    index = read_yaml(tmp_path / "literature" / "references" / "index.yml")
    first_ref = read_yaml(tmp_path / "literature" / "references" / "ref-20260630-001.yml")

    assert result["entry_count"] == 3
    assert result["imported_count"] == 2
    assert result["reused_count"] == 1
    assert result["reused"][0]["entry_key"] == "lee2010copy"
    assert result["reused"][0]["match"] == "doi"
    assert sorted(index["references"]) == ["ref-20260630-001", "ref-20260630-002"]
    assert first_ref["doi"] == "10.1021/nn1003937"
    assert first_ref["authors"] == ["Lee C.", "Yan H."]
    assert first_ref["source_type"] == "literature_library"


def test_register_reference_seeds_from_source_packet_is_explicit_and_reusable(tmp_path: Path) -> None:
    project_id = _project(tmp_path)
    packet = tmp_path / "suggestions" / "ftir" / "source-packets" / "packet.yml"
    packet.parent.mkdir(parents=True, exist_ok=True)
    packet.write_text(
        """
source_packet_id: ftir-source-packet-demo
reference_seeds:
  builtin-ftir-socrates-2001:
    citation: "Socrates, G. Infrared and Raman Characteristic Group Frequencies: Tables and Charts, 3rd ed.; Wiley, 2001."
    title: "Infrared and Raman Characteristic Group Frequencies: Tables and Charts"
    author:
      - "George Socrates"
    year: 2001
    venue: Wiley
    source_type: manual
    notes: "Built-in seed; register explicitly before report use."
  builtin-ftir-colthup-1990:
    citation: "Colthup, N. B.; Daly, L. H.; Wiberley, S. E. Introduction to Infrared and Raman Spectroscopy, 3rd ed.; Academic Press, 1990."
    title: "Introduction to Infrared and Raman Spectroscopy"
    author:
      - "Norman B. Colthup"
      - "Lawrence H. Daly"
      - "Stephen E. Wiberley"
    year: 1990
    venue: Academic Press
    source_type: manual
""".strip()
        + "\n",
        encoding="utf-8",
    )

    dry_run = register_reference_seeds(
        tmp_path,
        packet.relative_to(tmp_path),
        project_id=project_id,
        seed_ids=["builtin-ftir-socrates-2001"],
        dry_run=True,
    )

    assert dry_run["dry_run"] is True
    assert dry_run["imported_count"] == 1
    assert not (tmp_path / "literature" / "references" / "builtin-ftir-socrates-2001.yml").exists()

    first = register_reference_seeds(
        tmp_path,
        packet.relative_to(tmp_path),
        project_id=project_id,
        seed_ids=["builtin-ftir-socrates-2001"],
    )
    record = read_yaml(tmp_path / "literature" / "references" / "builtin-ftir-socrates-2001.yml")
    block = build_report_reference_block(tmp_path, ["builtin-ftir-socrates-2001"])

    assert first["imported_count"] == 1
    assert first["imported"][0]["reference_id"] == "builtin-ftir-socrates-2001"
    assert record["reference_id"] == "builtin-ftir-socrates-2001"
    assert record["authors"] == ["George Socrates"]
    assert record["source_type"] == "manual"
    assert "does not add report citations" in " ".join(first["boundaries"])
    assert block["inline_citation"] == "[1]"

    second = register_reference_seeds(tmp_path, packet.relative_to(tmp_path), project_id=project_id)

    assert second["imported_count"] == 1
    assert second["reused_count"] == 1
    assert second["reused"][0]["reference_id"] == "builtin-ftir-socrates-2001"
    assert second["imported"][0]["reference_id"] == "builtin-ftir-colthup-1990"


def test_validate_report_citations_matches_inline_numbers_to_references(tmp_path: Path) -> None:
    report = tmp_path / "reports" / "rpt-reference-demo-20260630-001.md"
    write_markdown_record(
        report,
        {
            "report_id": "rpt-reference-demo-20260630-001",
            "reference_ids": ["ref-20260630-001"],
        },
        """
# Report

MoS2 layer assignment is supported by Raman mode separation[1].

## References

[1] Lee C. et al. Anomalous lattice vibrations of single- and few-layer MoS2. DOI: 10.1021/nn1003937
""",
    )
    bad_report = tmp_path / "reports" / "rpt-reference-demo-20260630-002.md"
    write_markdown_record(
        bad_report,
        {"report_id": "rpt-reference-demo-20260630-002", "reference_ids": ["ref-20260630-001"]},
        """
# Report

This sentence cites a missing entry[2].

## References

[1] Lee C. et al.
""",
    )

    assert validate_report_citations(report)["ok"] is True
    bad = validate_report_citations(bad_report)
    assert bad["ok"] is False
    assert bad["missing_entries"] == [2]
    assert bad["uncited_entries"] == [1]


def test_cli_registers_reference_and_validates_report(tmp_path: Path, capsys) -> None:
    project_id = _project(tmp_path)

    assert main(
        [
            "references",
            "add",
            str(tmp_path),
            "--project-id",
            project_id,
            "--citation",
            "Lee C. et al. Anomalous lattice vibrations of single- and few-layer MoS2. ACS Nano (2010).",
            "--doi",
            "10.1021/nn1003937",
            "--url",
            "https://doi.org/10.1021/nn1003937",
        ]
    ) == 0
    out = json.loads(capsys.readouterr().out)
    assert "/literature/references/ref-" in out["reference"]
    ref_id = Path(out["reference"]).stem
    block = build_report_reference_block(tmp_path, [ref_id])
    report = tmp_path / "reports" / "rpt-reference-demo-20260630-001.md"
    write_markdown_record(
        report,
        {"report_id": "rpt-reference-demo-20260630-001", "reference_ids": [ref_id]},
        f"""
# Report

The Raman interpretation uses a registered reference{block["inline_citation"]}.

## References

{block["references_markdown"]}
""",
    )

    assert main(["references", "validate-report", str(tmp_path), "reports/rpt-reference-demo-20260630-001.md"]) == 0
    validation = json.loads(capsys.readouterr().out)
    assert validation["ok"] is True
    assert validation["inline_numbers"] == [1]


def test_cli_imports_bibtex_and_reuses_existing_references(tmp_path: Path, capsys) -> None:
    project_id = _project(tmp_path)
    bibtex = tmp_path / "cli-references.bib"
    bibtex.write_text(
        """
@article{lee2010,
  author = {Lee, C. and Yan, H.},
  title = {Anomalous lattice vibrations of single- and few-layer MoS2},
  journal = {ACS Nano},
  year = {2010},
  doi = {10.1021/nn1003937}
}
""",
        encoding="utf-8",
    )

    assert main(["references", "import-bibtex", str(tmp_path), str(bibtex), "--project-id", project_id]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["imported_count"] == 1
    assert first["reused_count"] == 0

    assert main(["references", "import-bibtex", str(tmp_path), str(bibtex), "--project-id", project_id]) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["imported_count"] == 0
    assert second["reused_count"] == 1
    assert second["reused"][0]["reference_id"] == first["imported"][0]["reference_id"]


def test_cli_registers_reference_seeds_from_source_packet(tmp_path: Path, capsys) -> None:
    project_id = _project(tmp_path)
    packet = tmp_path / "packet.yml"
    packet.write_text(
        """
reference_seeds:
  seed-reference-001:
    citation: "Seed Author. Seed reference title. Journal (2026)."
    title: "Seed reference title"
    year: 2026
""".strip()
        + "\n",
        encoding="utf-8",
    )

    assert (
        main(
            [
                "references",
                "register-seeds",
                str(tmp_path),
                "--source-packet",
                packet.relative_to(tmp_path).as_posix(),
                "--project-id",
                project_id,
                "--seed-id",
                "seed-reference-001",
            ]
        )
        == 0
    )
    out = json.loads(capsys.readouterr().out)
    assert out["imported_count"] == 1
    assert out["imported"][0]["reference_id"] == "seed-reference-001"
    assert (tmp_path / "literature" / "references" / "seed-reference-001.yml").exists()


def test_raman_report_can_embed_registered_references(tmp_path: Path) -> None:
    project_id = _project(tmp_path)
    raw = import_raw_file(
        tmp_path,
        Path("tests/fixtures/public/test-case-001/raw_data/MoS-2(1).txt"),
        project_id=project_id,
        sample_refs=["sample-ref-001"],
        experiment_refs=["exp-ref-001"],
        imported_at="2026-06-30T08:05:00",
    )
    column_review = write_review_record(
        tmp_path,
        target_type="raman_columns",
        target_ref=raw.metadata_path.relative_to(tmp_path).as_posix(),
        user_response="可以，保存",
        reviewed_content="x=col_0, y=col_1, unit=cm^-1",
    )
    parameter_review = write_review_record(
        tmp_path,
        target_type="raman_parameters",
        target_ref=raw.metadata_path.relative_to(tmp_path).as_posix(),
        user_response="可以，保存",
        reviewed_content=str(default_processing_parameters()),
    )
    result_path = process_raman_result(
        tmp_path,
        characterization_metadata_path=raw.metadata_path,
        project_id=project_id,
        sample_refs=["sample-ref-001"],
        request=RamanProcessingRequest(
            x_column="col_0",
            y_column="col_1",
            x_unit="cm^-1",
            processing_parameters=default_processing_parameters(),
            column_review_ref=column_review.stem,
            parameter_review_ref=parameter_review.stem,
        ),
        created_at="2026-06-30T08:15:00",
    )
    ref_path = register_reference(
        tmp_path,
        project_id=project_id,
        citation="Lee C. et al. Anomalous lattice vibrations of single- and few-layer MoS2. ACS Nano (2010).",
        doi="10.1021/nn1003937",
        created_at="2026-06-30T08:16:00",
    )

    report_path = generate_raman_report(
        tmp_path,
        project_id=project_id,
        raman_metadata_path=result_path,
        related_experiments=["exp-ref-001"],
        related_samples=["sample-ref-001"],
        reference_ids=[ref_path.stem],
        created_at="2026-06-30T08:20:00",
    )
    frontmatter, body = read_markdown_record(report_path)
    reports_index = read_yaml(tmp_path / "reports" / "index.yml")

    assert "[1]" in body.split("## References", 1)[0]
    assert "[1] Lee C. et al." in body
    assert frontmatter["reference_ids"] == [ref_path.stem]
    assert reports_index["reports"][frontmatter["report_id"]]["reference_ids"] == [ref_path.stem]
    assert validate_report_citations(report_path)["ok"] is True
