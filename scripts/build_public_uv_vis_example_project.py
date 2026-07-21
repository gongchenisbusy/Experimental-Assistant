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
from ea.reports import generate_uv_vis_report
from ea.review import write_review_record
from ea.samples import save_sample_record
from ea.storage import read_markdown_record, read_yaml, write_yaml
from ea.uv_vis import UVVisProcessingRequest, default_uv_vis_processing_parameters, process_uv_vis_result


DEFAULT_OUTPUT = REPO_ROOT / "examples" / "public-uv-vis-project"
PROJECT_CREATED_AT = "2026-06-05T11:00:00"
EXPERIMENT_DATE = "2026-06-05"
SAMPLE_ID = "sample-example-semiconductor-film-uv-vis-001"
FIXED_SOURCE_MTIME = datetime(2026, 6, 5, 11, 4, tzinfo=timezone.utc).timestamp()

EXAMPLE_DIALOGUE = (
    "公开 UV-Vis 示例：合成 semiconductor thin-film absorbance 光谱，包含接近 2 eV 的 Tauc-like onset "
    "和一个宽光学吸收特征。本示例只演示 reviewed Tauc screening、derivative screening 和 correction context "
    "如何进入报告、图件和 provenance，不把筛查截距当作最终 band gap 或跃迁机制证明。"
)

README_TEXT = """# Experimental Assistant v1.1.0 Public UV-Vis Example

This folder is a packaged, public-safe EA project example for the UV-Vis reviewed optical-screening workflow. It is meant for inspection, smoke testing, and agent orientation after installing or unpacking an Experimental Assistant v1.1.0 package.

The example contains a minimal review-gated UV-Vis workflow:

- project, rule-card, experiment, and sample records;
- one project-local synthetic UV-Vis source input and a controlled raw copy;
- column and parameter review records;
- processed UV-Vis metadata, CSV, feature table, figure, Tauc table, derivative table, and correction-context record;
- one UV-Vis report displaying reviewed Tauc/Kubelka-Munk screening, derivative screening, and correction context;
- provenance records and an example manifest.

Run local checks from the repository root:

```bash
ea healthcheck examples/public-uv-vis-project
ea eval project examples/public-uv-vis-project --no-write
```

Copy this folder before experimenting with edits. The packaged example is not a product default, does not configure Zotero, browser profiles, institution access, private caches, or signing keys, and should not be treated as a user's real project memory.

Maintainers can regenerate it with:

```bash
python3 scripts/build_public_uv_vis_example_project.py --force
```
"""


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _write_public_uv_vis_fixture(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# x_unit = eV",
        "# x_label = photon energy",
        "# y_label = absorbance",
        "energy_eV absorbance",
    ]
    band_gap = 2.05
    for index in range(440):
        energy = 1.15 + index * 0.006
        onset = math.sqrt(max(energy - band_gap, 0.0)) / energy if energy > band_gap else 0.0015
        shoulder = 0.07 * math.exp(-((energy - 2.72) ** 2) / (2.0 * 0.085**2))
        high_energy_band = 0.045 * math.exp(-((energy - 3.25) ** 2) / (2.0 * 0.13**2))
        baseline = 0.008 + 0.0025 * max(energy - 1.15, 0.0)
        absorbance = baseline + onset + shoulder + high_energy_band
        lines.append(f"{energy:.5f} {absorbance:.8f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.utime(path, (FIXED_SOURCE_MTIME, FIXED_SOURCE_MTIME))
    return path


def _reviewed_parameters() -> dict[str, object]:
    parameters = default_uv_vis_processing_parameters()
    parameters["tauc_analysis"].update(
        {
            "enabled": True,
            "transform": "absorbance",
            "transition": "direct_allowed",
            "fit_window_eV": [2.18, 2.52],
            "min_points": 16,
        }
    )
    parameters["derivative_analysis"].update(
        {
            "enabled": True,
            "axis": "energy_eV",
            "min_points": 20,
        }
    )
    parameters["correction_context"].update(
        {
            "enabled": True,
            "sample_geometry": {"sample_form": "thin_film", "path_length": "not_applicable"},
            "substrate": {"material": "quartz", "status": "reviewed", "subtraction": "not_applied"},
            "reference": {
                "reference_type": "blank_quartz",
                "reference_ref": "synthetic public blank context",
                "status": "reviewed",
            },
            "background": {
                "background_ref": "synthetic instrument dark baseline context",
                "status": "reviewed",
                "numeric_correction": "not_applied_by_ea",
            },
            "diffuse_reflectance": {"integrating_sphere": False, "kubelka_munk_context": "not_used"},
            "correction_notes": [
                "No substrate, reference, or background numeric correction is applied by EA in this public example.",
                "Correction context is recorded only to make interpretation assumptions visible.",
            ],
        }
    )
    return parameters


def build_example(output: Path, *, force: bool = False) -> dict[str, object]:
    output = output.resolve()
    if output.exists():
        if not force:
            raise SystemExit(f"Example output already exists; pass --force to replace it: {output}")
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    source_copy = _write_public_uv_vis_fixture(output / "source-inputs" / "raw" / "semiconductor-film-uv-vis-public-fixture.txt")
    project_outputs = initialize_project(
        output,
        project_name="EA Public UV-Vis Example",
        project_slug="public-uv-vis-example",
        research_direction="Review-gated UV-Vis optical screening of a synthetic thin-film spectrum",
        material_system="synthetic semiconductor thin film",
        experiment_type="UV-Vis characterization",
        enable_literature=False,
        created_at=PROJECT_CREATED_AT,
    )
    project_frontmatter, _ = read_markdown_record(project_outputs["project"])
    project_id = project_frontmatter["project_id"]

    draft = structure_experiment_log(EXAMPLE_DIALOGUE)
    experiment_path = save_confirmed_experiment(
        output,
        project_id=project_id,
        material_system="synthetic semiconductor thin film",
        experiment_type="UV-Vis characterization",
        experiment_date=EXPERIMENT_DATE,
        draft=draft,
        user_response="可以，保存",
        saved_at="2026-06-05T11:05:00",
    )
    experiment_frontmatter, _ = read_markdown_record(experiment_path)
    experiment_id = experiment_frontmatter["experiment_id"]

    sample_path = save_sample_record(
        output,
        sample_id=SAMPLE_ID,
        project_id=project_id,
        material_system="synthetic semiconductor thin film",
        created_from_experiment=experiment_id,
        quality_status="candidate_medium",
        morphology_observations=["synthetic public-safe UV-Vis example; no private sample information"],
        quality_notes=["Used only to demonstrate review-gated UV-Vis optical-screening records."],
        source_refs=[experiment_id],
        created_at="2026-06-05T11:06:00",
    )

    raw = import_raw_file(
        output,
        source_copy,
        project_id=project_id,
        characterization_type="uv_vis",
        sample_refs=[SAMPLE_ID],
        experiment_refs=[experiment_id],
        imported_at="2026-06-05T11:10:00",
    )
    raw_metadata_ref = raw.metadata_path.relative_to(output).as_posix()
    column_review = write_review_record(
        output,
        target_type="uv_vis_columns",
        target_ref=raw_metadata_ref,
        user_response="可以，保存",
        reviewed_content="x=energy_eV, y=absorbance, unit=eV, signal_mode=absorbance",
        reviewed_at="2026-06-05T11:12:00",
    )
    parameters = _reviewed_parameters()
    parameter_review = write_review_record(
        output,
        target_type="uv_vis_parameters",
        target_ref=raw_metadata_ref,
        user_response="可以，保存",
        reviewed_content=json.dumps(parameters, ensure_ascii=False),
        reviewed_at="2026-06-05T11:13:00",
    )

    uv_vis_metadata_path = process_uv_vis_result(
        output,
        characterization_metadata_path=raw.metadata_path,
        project_id=project_id,
        sample_refs=[SAMPLE_ID],
        request=UVVisProcessingRequest(
            x_column="energy_eV",
            y_column="absorbance",
            x_unit="eV",
            signal_mode="absorbance",
            processing_parameters=parameters,
            column_review_ref=column_review.stem,
            parameter_review_ref=parameter_review.stem,
        ),
        created_at="2026-06-05T11:16:00",
    )
    report_path = generate_uv_vis_report(
        output,
        project_id=project_id,
        uv_vis_metadata_path=uv_vis_metadata_path,
        related_experiments=[experiment_id],
        related_samples=[SAMPLE_ID],
        created_at="2026-06-05T11:24:00",
    )

    uv_vis_metadata = read_yaml(uv_vis_metadata_path)
    report_frontmatter, _ = read_markdown_record(report_path)
    healthcheck = run_healthcheck(output)
    evaluation = run_project_evaluation(output, write_report=False, created_at="2026-06-05T11:30:00")

    manifest = {
        "schema_version": "0.2",
        "example_id": "public-uv-vis-project",
        "example_type": "packaged_public_project",
        "project_id": project_id,
        "report_id": report_frontmatter["report_id"],
        "result_id": uv_vis_metadata["result_id"],
        "figure_id": uv_vis_metadata["figure_id"],
        "public_boundary": {
            "uses_developer_machine_defaults": False,
            "zotero_enabled": False,
            "browser_assist_enabled": False,
            "institution_access": None,
            "private_cache_required": False,
        },
        "workflow_boundary": {
            "source_backed_suggestion_workflow": False,
            "proves_band_gap_or_transition": False,
            "proves_defect_or_thickness_effect": False,
            "applies_numeric_substrate_or_background_correction": False,
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
            "uv_vis_metadata": _relative(uv_vis_metadata_path, output),
            "processed_csv": uv_vis_metadata["outputs"]["processed_csv"],
            "feature_table": uv_vis_metadata["outputs"]["peak_table"],
            "tauc_table": uv_vis_metadata["outputs"]["tauc_table"],
            "derivative_table": uv_vis_metadata["outputs"]["derivative_table"],
            "correction_context": uv_vis_metadata["outputs"]["correction_context"],
            "figure": uv_vis_metadata["outputs"]["figure"],
            "report": _relative(report_path, output),
        },
        "screening_summary": {
            "tauc_status": uv_vis_metadata["peak_analysis"]["tauc_analysis"]["status"],
            "tauc_intercept_energy_eV": uv_vis_metadata["peak_analysis"]["tauc_analysis"].get("intercept_energy_eV"),
            "derivative_status": uv_vis_metadata["peak_analysis"]["derivative_analysis"]["status"],
            "correction_context_status": uv_vis_metadata["peak_analysis"]["correction_context"]["status"],
        },
        "validation": {
            "healthcheck_status": healthcheck["status"],
            "healthcheck_errors": healthcheck["error_count"],
            "evaluation_status": evaluation["status"],
            "evaluation_errors": evaluation["error_count"],
        },
        "regenerate": "python3 scripts/build_public_uv_vis_example_project.py --force",
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
        "result_id": uv_vis_metadata["result_id"],
        "figure_id": uv_vis_metadata["figure_id"],
        "tauc_status": uv_vis_metadata["peak_analysis"]["tauc_analysis"]["status"],
        "derivative_status": uv_vis_metadata["peak_analysis"]["derivative_analysis"]["status"],
        "correction_context_status": uv_vis_metadata["peak_analysis"]["correction_context"]["status"],
        "healthcheck_status": healthcheck["status"],
        "evaluation_status": evaluation["status"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the packaged Experimental Assistant v1.1.0 public UV-Vis example project.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    summary = build_example(args.output, force=args.force)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
