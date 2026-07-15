#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ea.evaluation import run_project_evaluation
from ea.experiments import save_confirmed_experiment, structure_experiment_log
from ea.ftir import (
    FTIRProcessingRequest,
    build_ftir_assignment_source_packet,
    default_ftir_processing_parameters,
    prepare_ftir_assignment_review_package,
    process_ftir_result,
    propose_ftir_assignment_memory_candidates,
    suggest_ftir_assignments,
)
from ea.healthcheck import run_healthcheck
from ea.projects import initialize_project
from ea.raw_import import import_raw_file
from ea.references import register_reference_seeds
from ea.reports import generate_ftir_report
from ea.review import write_review_record
from ea.samples import save_sample_record
from ea.storage import read_markdown_record, read_yaml, write_yaml


DEFAULT_OUTPUT = REPO_ROOT / "examples" / "public-ftir-assignment-project"
PROJECT_CREATED_AT = "2026-06-04T10:00:00"
EXPERIMENT_DATE = "2026-06-04"
SAMPLE_ID = "sample-example-polymer-silica-ftir-001"
FIXED_SOURCE_MTIME = datetime(2026, 6, 4, 10, 4, tzinfo=timezone.utc).timestamp()
ASSIGNMENT_CANDIDATES = [
    "ftir-builtin-oh-nh-stretching-generic",
    "ftir-builtin-aliphatic-ch-stretching-generic",
    "ftir-builtin-carbonyl-co-stretching-generic",
    "ftir-builtin-sio-stretching-generic",
]
MEMORY_CANDIDATES = [
    "ftir-builtin-carbonyl-co-stretching-generic",
    "ftir-builtin-sio-stretching-generic",
]

EXAMPLE_DIALOGUE = (
    "公开 FTIR 示例：polymer-silica hybrid film 的合成光谱，包含 broad O-H/N-H、aliphatic C-H、"
    "carbonyl 和 Si-O/fingerprint 区域特征。本示例只演示 source-backed assignment candidate "
    "如何进入 review package、报告和草稿 interpretation memory，不把 band-window match 当作功能团或组成证明。"
)

README_TEXT = """# Experimental Assistant v0.9.9 Public FTIR Assignment Example

This folder is a packaged, public-safe EA project example for the FTIR source-backed assignment workflow. It is meant for inspection, smoke testing, and agent orientation after installing or unpacking an Experimental Assistant v0.9.9 package.

The example contains a minimal review-gated FTIR workflow:

- project, rule-card, experiment, and sample records;
- one project-local synthetic FTIR source input and a controlled raw copy;
- column and parameter review records;
- processed FTIR metadata, CSV, band table, and figure;
- a built-in `generic_materials` assignment source packet with selected public-safe candidates;
- registered source seeds, an FTIR assignment suggestion record, and a grouped review package;
- one FTIR report displaying advisory source-backed assignment candidates with registered references;
- draft interpretation memory candidates generated only after a confirmed suggestion review.

Run local checks from the repository root:

```bash
ea healthcheck examples/public-ftir-assignment-project
ea eval project examples/public-ftir-assignment-project --no-write
```

Copy this folder before experimenting with edits. The packaged example is not a product default, does not configure Zotero, browser profiles, institution access, private caches, or signing keys, and should not be treated as a user's real project memory.

Maintainers can regenerate it with:

```bash
python3 scripts/build_public_ftir_assignment_example_project.py --force
```
"""


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _write_public_ftir_fixture(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# x_unit = cm^-1",
        "# x_label = wavenumber",
        "# y_label = absorbance",
        "wavenumber absorbance",
    ]
    for index in range(1800):
        wavenumber = 4000.0 - index * 2.0
        baseline = 0.022 + 0.000006 * (4000.0 - wavenumber)
        signal = baseline
        for center, amplitude, width in [
            (3400.0, 0.30, 58.0),
            (2920.0, 0.20, 34.0),
            (1720.0, 0.27, 30.0),
            (1100.0, 0.35, 46.0),
        ]:
            signal += amplitude * math.exp(-((wavenumber - center) ** 2) / (2.0 * width**2))
        lines.append(f"{wavenumber:.2f} {signal:.8f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.utime(path, (FIXED_SOURCE_MTIME, FIXED_SOURCE_MTIME))
    return path


def build_example(output: Path, *, force: bool = False) -> dict[str, object]:
    output = output.resolve()
    if output.exists():
        if not force:
            raise SystemExit(f"Example output already exists; pass --force to replace it: {output}")
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    source_copy = _write_public_ftir_fixture(output / "source-inputs" / "raw" / "polymer-silica-ftir-public-fixture.txt")
    project_outputs = initialize_project(
        output,
        project_name="EA Public FTIR Assignment Example",
        project_slug="public-ftir-assignment-example",
        research_direction="Review-gated source-backed FTIR assignment candidate discussion",
        material_system="polymer-silica hybrid film",
        experiment_type="FTIR characterization",
        enable_literature=False,
        created_at=PROJECT_CREATED_AT,
    )
    project_frontmatter, _ = read_markdown_record(project_outputs["project"])
    project_id = project_frontmatter["project_id"]

    draft = structure_experiment_log(EXAMPLE_DIALOGUE)
    experiment_path = save_confirmed_experiment(
        output,
        project_id=project_id,
        material_system="polymer-silica hybrid film",
        experiment_type="FTIR characterization",
        experiment_date=EXPERIMENT_DATE,
        draft=draft,
        user_response="可以，保存",
        saved_at="2026-06-04T10:05:00",
    )
    experiment_frontmatter, _ = read_markdown_record(experiment_path)
    experiment_id = experiment_frontmatter["experiment_id"]

    sample_path = save_sample_record(
        output,
        sample_id=SAMPLE_ID,
        project_id=project_id,
        material_system="polymer-silica hybrid film",
        created_from_experiment=experiment_id,
        quality_status="candidate_medium",
        morphology_observations=["synthetic public-safe FTIR example; no private sample information"],
        quality_notes=["Used only to demonstrate review-gated source-backed FTIR assignment candidates."],
        source_refs=[experiment_id],
        created_at="2026-06-04T10:06:00",
    )

    raw = import_raw_file(
        output,
        source_copy,
        project_id=project_id,
        characterization_type="ftir",
        sample_refs=[SAMPLE_ID],
        experiment_refs=[experiment_id],
        imported_at="2026-06-04T10:10:00",
    )
    raw_metadata_ref = raw.metadata_path.relative_to(output).as_posix()
    column_review = write_review_record(
        output,
        target_type="ftir_columns",
        target_ref=raw_metadata_ref,
        user_response="可以，保存",
        reviewed_content="x=wavenumber, y=absorbance, unit=cm^-1, signal_mode=absorbance",
        reviewed_at="2026-06-04T10:12:00",
    )
    parameter_review = write_review_record(
        output,
        target_type="ftir_parameters",
        target_ref=raw_metadata_ref,
        user_response="可以，保存",
        reviewed_content=json.dumps(default_ftir_processing_parameters(), ensure_ascii=False),
        reviewed_at="2026-06-04T10:13:00",
    )

    ftir_metadata_path = process_ftir_result(
        output,
        characterization_metadata_path=raw.metadata_path,
        project_id=project_id,
        sample_refs=[SAMPLE_ID],
        request=FTIRProcessingRequest(
            x_column="wavenumber",
            y_column="absorbance",
            x_unit="cm^-1",
            signal_mode="absorbance",
            processing_parameters=default_ftir_processing_parameters(),
            column_review_ref=column_review.stem,
            parameter_review_ref=parameter_review.stem,
        ),
        created_at="2026-06-04T10:16:00",
    )

    packet_output = build_ftir_assignment_source_packet(
        output,
        project_id=project_id,
        builtin_library="generic_materials",
        include_candidates=ASSIGNMENT_CANDIDATES,
        output_path=Path("suggestions/ftir/source-packets/ftir_hybrid_assignment_candidates.yml"),
        created_at="2026-06-04T10:18:00",
    )
    source_packet_path = Path(packet_output["source_packet"])
    source_packet_ref = source_packet_path.relative_to(output).as_posix()
    register_reference_seeds(
        output,
        Path(source_packet_ref),
        project_id=project_id,
        created_at="2026-06-04T10:19:00",
    )
    suggestion_output = suggest_ftir_assignments(
        output,
        project_id=project_id,
        ftir_metadata_path=ftir_metadata_path,
        source_path=source_packet_path,
        related_records=[ftir_metadata_path.relative_to(output).as_posix()],
        created_at="2026-06-04T10:20:00",
    )
    suggestion_path = Path(suggestion_output["record"])
    suggestion_ref = suggestion_path.relative_to(output).as_posix()
    review_package_output = prepare_ftir_assignment_review_package(
        output,
        project_id=project_id,
        suggestion_path=suggestion_path,
        created_at="2026-06-04T10:21:00",
    )
    suggestion_review = write_review_record(
        output,
        target_type="ftir_assignment_suggestions",
        target_ref=suggestion_ref,
        user_response="可以，保存",
        reviewed_content="User reviewed carbonyl and Si-O candidates as advisory source-backed FTIR interpretation candidates.",
        reviewed_at="2026-06-04T10:22:00",
    )
    report_path = generate_ftir_report(
        output,
        project_id=project_id,
        ftir_metadata_path=ftir_metadata_path,
        related_experiments=[experiment_id],
        related_samples=[SAMPLE_ID],
        assignment_suggestion_paths=[suggestion_path],
        created_at="2026-06-04T10:24:00",
    )
    memory_output = propose_ftir_assignment_memory_candidates(
        output,
        project_id=project_id,
        suggestion_path=suggestion_path,
        review_ref=suggestion_review.stem,
        candidate_ids=MEMORY_CANDIDATES,
        created_at="2026-06-04T10:25:00",
    )

    ftir_metadata = read_yaml(ftir_metadata_path)
    report_frontmatter, _ = read_markdown_record(report_path)
    healthcheck = run_healthcheck(output)
    evaluation = run_project_evaluation(output, write_report=False, created_at="2026-06-04T10:30:00")
    memory_candidates = [item["memory_candidate_ref"] for item in memory_output.get("memory_candidates", [])]

    manifest = {
        "schema_version": "0.2",
        "example_id": "public-ftir-assignment-project",
        "example_type": "packaged_public_project",
        "project_id": project_id,
        "report_id": report_frontmatter["report_id"],
        "result_id": ftir_metadata["result_id"],
        "figure_id": ftir_metadata["figure_id"],
        "suggestion_id": suggestion_output["suggestion_id"],
        "public_boundary": {
            "uses_developer_machine_defaults": False,
            "zotero_enabled": False,
            "browser_assist_enabled": False,
            "institution_access": None,
            "private_cache_required": False,
        },
        "workflow_boundary": {
            "auto_applies_assignments": False,
            "proves_functional_groups_or_composition": False,
            "writes_confirmed_memory": False,
            "performs_live_lookup_or_pdf_download": False,
        },
        "key_artifacts": {
            "project": _relative(project_outputs["project"], output),
            "rule_card": _relative(project_outputs["rule_card"], output),
            "source_input": _relative(source_copy, output),
            "raw_metadata": raw_metadata_ref,
            "raw_file": _relative(raw.project_raw_path or output / "missing", output),
            "sample": _relative(sample_path, output),
            "experiment": _relative(experiment_path, output),
            "ftir_metadata": _relative(ftir_metadata_path, output),
            "processed_csv": ftir_metadata["outputs"]["processed_csv"],
            "band_table": ftir_metadata["outputs"]["peak_table"],
            "figure": ftir_metadata["outputs"]["figure"],
            "source_packet": source_packet_ref,
            "suggestion_record": suggestion_ref,
            "suggestion_table": Path(suggestion_output["table"]).relative_to(output).as_posix(),
            "review_package": review_package_output["review_package_ref"],
            "review_package_markdown": review_package_output["review_package_markdown_ref"],
            "suggestion_review": _relative(suggestion_review, output),
            "report": _relative(report_path, output),
            "memory_candidates": memory_candidates,
            "reference_index": "literature/references/index.yml",
        },
        "validation": {
            "healthcheck_status": healthcheck["status"],
            "healthcheck_errors": healthcheck["error_count"],
            "evaluation_status": evaluation["status"],
            "evaluation_errors": evaluation["error_count"],
        },
        "regenerate": "python3 scripts/build_public_ftir_assignment_example_project.py --force",
    }
    write_yaml(output / "example_manifest.yml", manifest)
    (output / "README.md").write_text(README_TEXT, encoding="utf-8")

    if healthcheck["status"] != "pass" or evaluation["status"] != "pass":
        raise RuntimeError(json.dumps({"healthcheck": healthcheck, "evaluation": evaluation}, ensure_ascii=False, indent=2))

    return {
        "status": "complete",
        "example": str(output),
        "project_id": project_id,
        "report_id": report_frontmatter["report_id"],
        "result_id": ftir_metadata["result_id"],
        "figure_id": ftir_metadata["figure_id"],
        "suggestion_id": suggestion_output["suggestion_id"],
        "memory_candidate_count": len(memory_candidates),
        "healthcheck_status": healthcheck["status"],
        "evaluation_status": evaluation["status"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the packaged Experimental Assistant v0.9.9 public FTIR assignment example project.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    summary = build_example(args.output, force=args.force)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
