#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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
from ea.raman import RamanProcessingRequest, default_processing_parameters, process_raman_result
from ea.raw_import import import_raw_file
from ea.reports import generate_raman_report
from ea.review import write_review_record
from ea.samples import save_sample_record
from ea.storage import read_markdown_record, read_yaml, write_yaml


DEFAULT_FIXTURE_RAW = REPO_ROOT / "tests" / "fixtures" / "public" / "test-case-001" / "raw_data" / "MoS-2(1).txt"
DEFAULT_OUTPUT = REPO_ROOT / "examples" / "public-raman-project"
PROJECT_CREATED_AT = "2026-06-02T17:00:00"
EXPERIMENT_DATE = "2026-05-16"
SAMPLE_ID = "sample-example-mos2-001"
FIXED_SOURCE_MTIME = datetime(2026, 6, 2, 17, 9, tzinfo=timezone.utc).timestamp()

EXAMPLE_DIALOGUE = (
    "第一炉，流速60，四片 mica 衬底，硫源660°C开启，保温时间缩短到1min。"
    "其中一片长得很好，呈现标准的正三角形形状，单边尺寸约55微米；"
    "另外两片也有10到30微米的三角形区域，可以作为后续 Raman 表征候选样品。"
)

README_TEXT = """# Experimental Assistant v1.1.0 Public Raman Example Project

This folder is a packaged, public-safe EA project example. It is meant for inspection, smoke testing, and agent orientation after installing or unpacking an Experimental Assistant v1.1.0 package.

The example contains a minimal review-gated Raman workflow:

- project and rule-card records;
- one confirmed experiment record;
- one sample record;
- one project-local source input and a controlled raw copy;
- column and parameter review records;
- processed Raman metadata, CSV, peak table, and figure;
- one Raman report;
- provenance records and an example manifest.

Run local checks from the repository root:

```bash
ea healthcheck examples/public-raman-project
ea eval project examples/public-raman-project --no-write
```

Copy this folder before experimenting with edits. The packaged example is not a product default, does not configure Zotero, browser profiles, institution access, private caches, or signing keys, and should not be treated as a user's real project memory.

Maintainers can regenerate it with:

```bash
python3 scripts/build_packaged_example_project.py --force
```
"""


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def build_example(output: Path, *, fixture_raw: Path = DEFAULT_FIXTURE_RAW, force: bool = False) -> dict[str, object]:
    output = output.resolve()
    fixture_raw = fixture_raw.resolve()
    if not fixture_raw.exists():
        raise FileNotFoundError(fixture_raw)
    if output.exists():
        if not force:
            raise SystemExit(f"Example output already exists; pass --force to replace it: {output}")
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    source_dir = output / "source-inputs" / "raw"
    source_dir.mkdir(parents=True, exist_ok=True)
    source_copy = source_dir / "mos2-raman-public-fixture.txt"
    lines = [line.rstrip() for line in fixture_raw.read_text(encoding="utf-8").splitlines()]
    source_copy.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.utime(source_copy, (FIXED_SOURCE_MTIME, FIXED_SOURCE_MTIME))

    project_outputs = initialize_project(
        output,
        project_name="EA Public Raman Example",
        project_slug="public-raman-example",
        research_direction="Review-gated Raman analysis of a MoS2 public example",
        material_system="MoS2",
        experiment_type="CVD growth and Raman characterization",
        enable_literature=False,
        created_at=PROJECT_CREATED_AT,
    )
    project_frontmatter, _ = read_markdown_record(project_outputs["project"])
    project_id = project_frontmatter["project_id"]

    draft = structure_experiment_log(EXAMPLE_DIALOGUE)
    experiment_path = save_confirmed_experiment(
        output,
        project_id=project_id,
        material_system="MoS2",
        experiment_type="CVD growth",
        experiment_date=EXPERIMENT_DATE,
        draft=draft,
        user_response="可以，保存",
        saved_at="2026-06-02T17:05:00",
    )
    experiment_frontmatter, _ = read_markdown_record(experiment_path)
    experiment_id = experiment_frontmatter["experiment_id"]

    sample_path = save_sample_record(
        output,
        sample_id=SAMPLE_ID,
        project_id=project_id,
        material_system="MoS2",
        created_from_experiment=experiment_id,
        quality_status="candidate_good",
        morphology_observations=["regular triangular MoS2-like domains"],
        quality_notes=["Public example sample selected for review-gated Raman analysis."],
        source_refs=[experiment_id],
        created_at="2026-06-02T17:06:00",
    )

    raw = import_raw_file(
        output,
        source_copy,
        project_id=project_id,
        characterization_type="raman",
        sample_refs=[SAMPLE_ID],
        experiment_refs=[experiment_id],
        imported_at="2026-06-02T17:10:00",
    )
    raw_metadata_ref = raw.metadata_path.relative_to(output).as_posix()
    column_review = write_review_record(
        output,
        target_type="raman_columns",
        target_ref=raw_metadata_ref,
        user_response="可以，保存",
        reviewed_content="x=col_0, y=col_1, unit=cm^-1",
        reviewed_at="2026-06-02T17:12:00",
    )
    parameter_review = write_review_record(
        output,
        target_type="raman_parameters",
        target_ref=raw_metadata_ref,
        user_response="可以，保存",
        reviewed_content=json.dumps(default_processing_parameters(), ensure_ascii=False),
        reviewed_at="2026-06-02T17:13:00",
    )
    raman_metadata_path = process_raman_result(
        output,
        characterization_metadata_path=raw.metadata_path,
        project_id=project_id,
        sample_refs=[SAMPLE_ID],
        request=RamanProcessingRequest(
            x_column="col_0",
            y_column="col_1",
            x_unit="cm^-1",
            processing_parameters=default_processing_parameters(),
            column_review_ref=column_review.stem,
            parameter_review_ref=parameter_review.stem,
        ),
        created_at="2026-06-02T17:15:00",
    )
    report_path = generate_raman_report(
        output,
        project_id=project_id,
        raman_metadata_path=raman_metadata_path,
        related_experiments=[experiment_id],
        related_samples=[SAMPLE_ID],
        created_at="2026-06-02T17:20:00",
    )

    raman_metadata = read_yaml(raman_metadata_path)
    report_frontmatter, _ = read_markdown_record(report_path)
    healthcheck = run_healthcheck(output)
    evaluation = run_project_evaluation(output, write_report=False, created_at="2026-06-02T17:30:00")

    manifest = {
        "schema_version": "0.2",
        "example_id": "public-raman-project",
        "example_type": "packaged_public_project",
        "project_id": project_id,
        "report_id": report_frontmatter["report_id"],
        "result_id": raman_metadata["result_id"],
        "figure_id": raman_metadata["figure_id"],
        "public_boundary": {
            "uses_developer_machine_defaults": False,
            "zotero_enabled": False,
            "browser_assist_enabled": False,
            "institution_access": None,
            "private_cache_required": False,
        },
        "key_artifacts": {
            "project": _relative(project_outputs["project"], output),
            "rule_card": _relative(project_outputs["rule_card"], output),
            "source_input": _relative(source_copy, output),
            "raw_metadata": raw_metadata_ref,
            "raw_file": _relative(raw.project_raw_path or output / "missing", output),
            "sample": _relative(sample_path, output),
            "experiment": _relative(experiment_path, output),
            "raman_metadata": _relative(raman_metadata_path, output),
            "processed_csv": raman_metadata["outputs"]["processed_csv"],
            "peak_table": raman_metadata["outputs"]["peak_table"],
            "figure": raman_metadata["outputs"]["figure"],
            "report": _relative(report_path, output),
        },
        "validation": {
            "healthcheck_status": healthcheck["status"],
            "healthcheck_errors": healthcheck["error_count"],
            "evaluation_status": evaluation["status"],
            "evaluation_errors": evaluation["error_count"],
        },
        "regenerate": "python3 scripts/build_packaged_example_project.py --force",
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
        "result_id": raman_metadata["result_id"],
        "figure_id": raman_metadata["figure_id"],
        "healthcheck_status": healthcheck["status"],
        "evaluation_status": evaluation["status"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the packaged Experimental Assistant v1.1.0 public Raman example project.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--fixture-raw", type=Path, default=DEFAULT_FIXTURE_RAW)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    summary = build_example(args.output, fixture_raw=args.fixture_raw, force=args.force)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
