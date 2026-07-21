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
from ea.healthcheck import run_healthcheck
from ea.projects import initialize_project
from ea.raw_import import import_raw_file
from ea.references import register_reference_seeds
from ea.reports import generate_xps_report
from ea.review import write_review_record
from ea.samples import save_sample_record
from ea.storage import read_markdown_record, read_yaml, write_yaml
from ea.xps import (
    XPSProcessingRequest,
    build_xps_parameter_source_packet,
    default_xps_processing_parameters,
    prepare_xps_parameter_review_package,
    process_xps_result,
    propose_xps_parameter_memory_candidates,
    suggest_xps_parameters,
)


DEFAULT_OUTPUT = REPO_ROOT / "examples" / "public-xps-be-project"
PROJECT_CREATED_AT = "2026-06-03T09:00:00"
EXPERIMENT_DATE = "2026-06-03"
SAMPLE_ID = "sample-example-si-sio2-xps-001"
FIXED_SOURCE_MTIME = datetime(2026, 6, 3, 9, 4, tzinfo=timezone.utc).timestamp()

EXAMPLE_DIALOGUE = (
    "公开 XPS 示例：Si/SiO2 表面样品，存在弱 adventitious carbon。"
    "本示例只演示 source-backed binding-energy 候选如何进入 review package、报告和草稿 interpretation memory，"
    "不把任何候选峰位当作自动校准、扣电荷或化学态证明。"
)

README_TEXT = """# Experimental Assistant v1.1.0 Public XPS Binding-Energy Candidate Example

This folder is a packaged, public-safe EA project example for the XPS source-backed binding-energy candidate workflow. It is meant for inspection, smoke testing, and agent orientation after installing or unpacking an Experimental Assistant v1.1.0 package.

The example contains a minimal review-gated XPS workflow:

- project, rule-card, experiment, and sample records;
- one project-local synthetic XPS source input and a controlled raw copy;
- column, calibration, and parameter review records;
- processed XPS metadata, CSV, peak table, and figure;
- a built-in `binding_energy_candidate` source packet for C 1s and Si 2p starter discussion;
- an optional O 1s / oxide-surface source packet from `oxide_o1s_binding_energy`;
- registered source seeds, XPS parameter suggestion records, and grouped review packages;
- one XPS report displaying advisory source-backed BE candidates with registered references;
- draft interpretation memory candidates generated only after confirmed suggestion reviews.

Run local checks from the repository root:

```bash
ea healthcheck examples/public-xps-be-project
ea eval project examples/public-xps-be-project --no-write
```

Copy this folder before experimenting with edits. The packaged example is not a product default, does not configure Zotero, browser profiles, institution access, private caches, or signing keys, and should not be treated as a user's real project memory.

Maintainers can regenerate it with:

```bash
python3 scripts/build_public_xps_be_example_project.py --force
```
"""


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _write_public_xps_fixture(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# x_unit = eV",
        "# x_label = binding energy",
        "# y_label = counts",
        "binding_energy_eV intensity",
    ]
    for index in range(2400):
        energy = 1200.0 - index * 0.5
        baseline = 0.026 + 0.000018 * energy
        signal = baseline
        for center, amplitude, width in [
            (103.5, 0.30, 1.2),
            (99.4, 0.16, 1.0),
            (284.8, 0.18, 1.35),
            (286.0, 0.08, 1.5),
            (532.3, 0.22, 1.8),
        ]:
            signal += amplitude * math.exp(-((energy - center) ** 2) / (2.0 * width**2))
        lines.append(f"{energy:.2f} {signal:.8f}")
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

    source_copy = _write_public_xps_fixture(output / "source-inputs" / "raw" / "si-sio2-xps-public-fixture.txt")
    project_outputs = initialize_project(
        output,
        project_name="EA Public XPS BE Example",
        project_slug="public-xps-be-example",
        research_direction="Review-gated source-backed XPS binding-energy candidate discussion",
        material_system="Si/SiO2 with adventitious carbon",
        experiment_type="XPS characterization",
        enable_literature=False,
        created_at=PROJECT_CREATED_AT,
    )
    project_frontmatter, _ = read_markdown_record(project_outputs["project"])
    project_id = project_frontmatter["project_id"]

    draft = structure_experiment_log(EXAMPLE_DIALOGUE)
    experiment_path = save_confirmed_experiment(
        output,
        project_id=project_id,
        material_system="Si/SiO2",
        experiment_type="XPS characterization",
        experiment_date=EXPERIMENT_DATE,
        draft=draft,
        user_response="可以，保存",
        saved_at="2026-06-03T09:05:00",
    )
    experiment_frontmatter, _ = read_markdown_record(experiment_path)
    experiment_id = experiment_frontmatter["experiment_id"]

    sample_path = save_sample_record(
        output,
        sample_id=SAMPLE_ID,
        project_id=project_id,
        material_system="Si/SiO2",
        created_from_experiment=experiment_id,
        quality_status="candidate_medium",
        morphology_observations=["synthetic public-safe XPS example; no private sample information"],
        quality_notes=["Used only to demonstrate review-gated source-backed BE candidates."],
        source_refs=[experiment_id],
        created_at="2026-06-03T09:06:00",
    )

    raw = import_raw_file(
        output,
        source_copy,
        project_id=project_id,
        characterization_type="xps",
        sample_refs=[SAMPLE_ID],
        experiment_refs=[experiment_id],
        imported_at="2026-06-03T09:10:00",
    )
    raw_metadata_ref = raw.metadata_path.relative_to(output).as_posix()
    column_review = write_review_record(
        output,
        target_type="xps_columns",
        target_ref=raw_metadata_ref,
        user_response="可以，保存",
        reviewed_content="x=binding_energy_eV, y=intensity, unit=eV",
        reviewed_at="2026-06-03T09:12:00",
    )
    calibration_review = write_review_record(
        output,
        target_type="xps_calibration",
        target_ref=raw_metadata_ref,
        user_response="可以，保存",
        reviewed_content="Synthetic example uses energy_shift_eV=0.0; C 1s context is discussion-only and not a universal charge reference.",
        reviewed_at="2026-06-03T09:13:00",
    )
    parameter_review = write_review_record(
        output,
        target_type="xps_parameters",
        target_ref=raw_metadata_ref,
        user_response="可以，保存",
        reviewed_content=json.dumps(default_xps_processing_parameters(), ensure_ascii=False),
        reviewed_at="2026-06-03T09:14:00",
    )

    xps_metadata_path = process_xps_result(
        output,
        characterization_metadata_path=raw.metadata_path,
        project_id=project_id,
        sample_refs=[SAMPLE_ID],
        request=XPSProcessingRequest(
            x_column="binding_energy_eV",
            y_column="intensity",
            x_unit="eV",
            energy_shift_eV=0.0,
            calibration_reference="Synthetic public example; no automatic charge correction. C 1s/Si 2p BE candidates are advisory discussion starters only.",
            processing_parameters=default_xps_processing_parameters(),
            column_review_ref=column_review.stem,
            calibration_review_ref=calibration_review.stem,
            parameter_review_ref=parameter_review.stem,
        ),
        created_at="2026-06-03T09:16:00",
    )

    packet_output = build_xps_parameter_source_packet(
        output,
        project_id=project_id,
        builtin_library="generic_xps_parameters",
        suggestion_types=["binding_energy_candidate"],
        output_path=Path("suggestions/xps/source-packets/xps_binding_energy_candidates.yml"),
        created_at="2026-06-03T09:18:00",
    )
    source_packet_path = Path(packet_output["source_packet"])
    source_packet_ref = source_packet_path.relative_to(output).as_posix()
    register_reference_seeds(
        output,
        Path(source_packet_ref),
        project_id=project_id,
        created_at="2026-06-03T09:19:00",
    )
    suggestion_output = suggest_xps_parameters(
        output,
        project_id=project_id,
        source_path=source_packet_path,
        related_records=[xps_metadata_path.relative_to(output).as_posix()],
        created_at="2026-06-03T09:20:00",
    )
    suggestion_path = Path(suggestion_output["record"])
    suggestion_ref = suggestion_path.relative_to(output).as_posix()
    review_package_output = prepare_xps_parameter_review_package(
        output,
        project_id=project_id,
        suggestion_path=suggestion_path,
        created_at="2026-06-03T09:21:00",
    )
    suggestion_review = write_review_record(
        output,
        target_type="xps_parameter_suggestions",
        target_ref=suggestion_ref,
        user_response="可以，保存",
        reviewed_content="User reviewed built-in C 1s/Si 2p binding-energy candidates as advisory interpretation discussion only.",
        reviewed_at="2026-06-03T09:22:00",
    )

    o1s_packet_output = build_xps_parameter_source_packet(
        output,
        project_id=project_id,
        builtin_library="oxide_o1s_binding_energy",
        suggestion_types=["binding_energy_candidate"],
        output_path=Path("suggestions/xps/source-packets/xps_o1s_oxide_candidates.yml"),
        created_at="2026-06-03T09:23:00",
    )
    o1s_source_packet_path = Path(o1s_packet_output["source_packet"])
    o1s_source_packet_ref = o1s_source_packet_path.relative_to(output).as_posix()
    register_reference_seeds(
        output,
        Path(o1s_source_packet_ref),
        project_id=project_id,
        created_at="2026-06-03T09:24:00",
    )
    o1s_suggestion_output = suggest_xps_parameters(
        output,
        project_id=project_id,
        source_path=o1s_source_packet_path,
        related_records=[xps_metadata_path.relative_to(output).as_posix()],
        created_at="2026-06-03T09:25:00",
    )
    o1s_suggestion_path = Path(o1s_suggestion_output["record"])
    o1s_suggestion_ref = o1s_suggestion_path.relative_to(output).as_posix()
    o1s_review_package_output = prepare_xps_parameter_review_package(
        output,
        project_id=project_id,
        suggestion_path=o1s_suggestion_path,
        created_at="2026-06-03T09:26:00",
    )
    o1s_suggestion_review = write_review_record(
        output,
        target_type="xps_parameter_suggestions",
        target_ref=o1s_suggestion_ref,
        user_response="可以，保存",
        reviewed_content="User reviewed optional O 1s oxide-surface binding-energy candidates as advisory interpretation discussion only.",
        reviewed_at="2026-06-03T09:27:00",
    )
    report_path = generate_xps_report(
        output,
        project_id=project_id,
        xps_metadata_path=xps_metadata_path,
        related_experiments=[experiment_id],
        related_samples=[SAMPLE_ID],
        parameter_suggestion_paths=[suggestion_path, o1s_suggestion_path],
        created_at="2026-06-03T09:28:00",
    )
    memory_output = propose_xps_parameter_memory_candidates(
        output,
        project_id=project_id,
        suggestion_path=suggestion_path,
        review_ref=suggestion_review.stem,
        candidate_ids=[
            "xps-builtin-c1s-adventitious-cc-binding-energy-candidate",
            "xps-builtin-si2p-sio2-binding-energy-candidate",
        ],
        created_at="2026-06-03T09:29:00",
    )
    o1s_memory_output = propose_xps_parameter_memory_candidates(
        output,
        project_id=project_id,
        suggestion_path=o1s_suggestion_path,
        review_ref=o1s_suggestion_review.stem,
        candidate_ids=[
            "xps-builtin-o1s-silica-organic-co-binding-energy-candidate",
        ],
        created_at="2026-06-03T09:30:00",
    )

    xps_metadata = read_yaml(xps_metadata_path)
    report_frontmatter, _ = read_markdown_record(report_path)
    healthcheck = run_healthcheck(output)
    evaluation = run_project_evaluation(output, write_report=False, created_at="2026-06-03T09:30:00")

    manifest = {
        "schema_version": "0.2",
        "example_id": "public-xps-be-project",
        "example_type": "packaged_public_project",
        "project_id": project_id,
        "report_id": report_frontmatter["report_id"],
        "result_id": xps_metadata["xps_result_id"],
        "figure_id": xps_metadata["figure_id"],
        "suggestion_id": suggestion_output["suggestion_id"],
        "o1s_suggestion_id": o1s_suggestion_output["suggestion_id"],
        "suggestion_ids": [suggestion_output["suggestion_id"], o1s_suggestion_output["suggestion_id"]],
        "public_boundary": {
            "uses_developer_machine_defaults": False,
            "zotero_enabled": False,
            "browser_assist_enabled": False,
            "institution_access": None,
            "private_cache_required": False,
        },
        "workflow_boundary": {
            "auto_applies_binding_energy_candidates": False,
            "auto_calibrates_or_charge_corrects": False,
            "proves_chemical_state_or_composition": False,
            "writes_confirmed_memory": False,
        },
        "key_artifacts": {
            "project": _relative(project_outputs["project"], output),
            "rule_card": _relative(project_outputs["rule_card"], output),
            "source_input": _relative(source_copy, output),
            "raw_metadata": raw_metadata_ref,
            "raw_file": _relative(raw.project_raw_path or output / "missing", output),
            "sample": _relative(sample_path, output),
            "experiment": _relative(experiment_path, output),
            "xps_metadata": _relative(xps_metadata_path, output),
            "processed_csv": xps_metadata["outputs"]["processed_csv"],
            "peak_table": xps_metadata["outputs"]["peak_table"],
            "figure": xps_metadata["outputs"]["figure"],
            "source_packet": source_packet_ref,
            "suggestion_record": suggestion_ref,
            "suggestion_table": read_yaml(suggestion_path)["table_ref"],
            "review_package": Path(review_package_output["review_package"]).relative_to(output).as_posix(),
            "review_package_markdown": Path(review_package_output["review_package_markdown"]).relative_to(output).as_posix(),
            "suggestion_review": _relative(suggestion_review, output),
            "o1s_source_packet": o1s_source_packet_ref,
            "o1s_suggestion_record": o1s_suggestion_ref,
            "o1s_suggestion_table": read_yaml(o1s_suggestion_path)["table_ref"],
            "o1s_review_package": Path(o1s_review_package_output["review_package"]).relative_to(output).as_posix(),
            "o1s_review_package_markdown": Path(o1s_review_package_output["review_package_markdown"]).relative_to(output).as_posix(),
            "o1s_suggestion_review": _relative(o1s_suggestion_review, output),
            "report": _relative(report_path, output),
            "memory_candidates": [
                *[item["memory_candidate_ref"] for item in memory_output["memory_candidates"]],
                *[item["memory_candidate_ref"] for item in o1s_memory_output["memory_candidates"]],
            ],
            "reference_index": "literature/references/index.yml",
        },
        "validation": {
            "healthcheck_status": healthcheck["status"],
            "healthcheck_errors": healthcheck["error_count"],
            "evaluation_status": evaluation["status"],
            "evaluation_errors": evaluation["error_count"],
        },
        "regenerate": "python3 scripts/build_public_xps_be_example_project.py --force",
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
        "result_id": xps_metadata["xps_result_id"],
        "figure_id": xps_metadata["figure_id"],
        "suggestion_id": suggestion_output["suggestion_id"],
        "o1s_suggestion_id": o1s_suggestion_output["suggestion_id"],
        "memory_candidate_count": len(memory_output["memory_candidates"]) + len(o1s_memory_output["memory_candidates"]),
        "healthcheck_status": healthcheck["status"],
        "evaluation_status": evaluation["status"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the packaged Experimental Assistant v1.1.0 public XPS BE candidate example project.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    summary = build_example(args.output, force=args.force)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
