from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

from ea.projects import initialize_project
from ea.raman import RamanProcessingError, RamanProcessingRequest, default_processing_parameters, process_raman_result
from ea.raw_import import import_raw_file
from ea.review import write_review_record
from ea.storage.files import read_markdown_record, read_yaml, write_yaml


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check(checks: list[dict[str, Any]], *, code: str, actual: Any, expected: Any, passed: bool, tolerance: float | None = None) -> None:
    checks.append(
        {
            "code": code,
            "status": "pass" if passed else "fail",
            "actual": actual,
            "expected": expected,
            "absolute_tolerance": tolerance,
        }
    )


def run_raman_golden_benchmark(
    repository_root: Path,
    *,
    benchmark_path: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    benchmark_path = benchmark_path or repository_root / "benchmarks" / "raman-v1" / "benchmark.yml"
    benchmark = read_yaml(benchmark_path)
    source = repository_root / benchmark["source"]["path"]
    checks: list[dict[str, Any]] = []
    source_hash = _sha256(source)
    _check(
        checks,
        code="source_hash",
        actual=source_hash,
        expected=benchmark["source"]["sha256"],
        passed=source_hash == benchmark["source"]["sha256"],
    )

    with tempfile.TemporaryDirectory(prefix="ea-raman-benchmark-") as directory:
        workspace = Path(directory)
        outputs = initialize_project(
            workspace,
            project_name="EA Raman Golden Benchmark",
            project_slug="ea-raman-golden-benchmark",
            research_direction="deterministic Raman software benchmark",
            material_system=benchmark["source"]["material"],
            experiment_type="Raman",
            created_at="2026-07-10T17:00:00",
        )
        project, _ = read_markdown_record(outputs["project"])
        raw = import_raw_file(
            workspace,
            source,
            project_id=project["project_id"],
            sample_refs=["sample-benchmark-001"],
            imported_at="2026-07-10T17:01:00",
        )
        column_review = write_review_record(
            workspace,
            target_type="raman_columns",
            target_ref=raw.metadata_path.relative_to(workspace).as_posix(),
            user_response="confirmed",
            reviewed_content=benchmark["processing"]["reviewed_columns"],
            reviewed_at="2026-07-10T17:02:00",
        )
        parameter_review = write_review_record(
            workspace,
            target_type="raman_parameters",
            target_ref=raw.metadata_path.relative_to(workspace).as_posix(),
            user_response="confirmed",
            reviewed_content=str(default_processing_parameters()),
            reviewed_at="2026-07-10T17:03:00",
        )
        request = RamanProcessingRequest(
            x_column="col_0",
            y_column="col_1",
            x_unit=benchmark["source"]["x_unit"],
            processing_parameters=default_processing_parameters(),
            column_review_ref=column_review.stem,
            parameter_review_ref=parameter_review.stem,
        )
        metadata_path = process_raman_result(
            workspace,
            characterization_metadata_path=raw.metadata_path,
            project_id=project["project_id"],
            sample_refs=["sample-benchmark-001"],
            request=request,
            created_at="2026-07-10T17:04:00",
        )
        metadata = read_yaml(metadata_path)
        peak_table = pd.read_csv(workspace / metadata["outputs"]["peak_table"])
        expected = benchmark["expected"]
        peak_count = int(metadata["peak_analysis"]["peak_count"])
        _check(
            checks,
            code="peak_count_range",
            actual=peak_count,
            expected=[expected["peak_count"]["minimum"], expected["peak_count"]["maximum"]],
            passed=expected["peak_count"]["minimum"] <= peak_count <= expected["peak_count"]["maximum"],
        )
        assigned = {item["feature"]: item for item in metadata["peak_analysis"]["assigned_features"]}
        for feature, rule in expected["assigned_features"].items():
            actual = assigned.get(feature, {}).get("observed_cm-1")
            tolerance = float(rule["absolute_tolerance_cm-1"])
            _check(
                checks,
                code=f"assigned_center_{feature}",
                actual=actual,
                expected=rule["center_cm-1"],
                tolerance=tolerance,
                passed=actual is not None and abs(float(actual) - float(rule["center_cm-1"])) <= tolerance,
            )
        actual_separation = metadata["peak_analysis"].get("mode_separation_cm-1")
        separation_rule = expected["mode_separation_cm-1"]
        _check(
            checks,
            code="mode_separation",
            actual=actual_separation,
            expected=separation_rule["value"],
            tolerance=separation_rule["absolute_tolerance_cm-1"],
            passed=actual_separation is not None
            and abs(float(actual_separation) - float(separation_rule["value"])) <= float(separation_rule["absolute_tolerance_cm-1"]),
        )
        confidence_values = set(peak_table.loc[peak_table["assignment"].notna(), "assignment_confidence"].dropna())
        _check(
            checks,
            code="assignment_confidence",
            actual=sorted(confidence_values),
            expected=[expected["assignment_confidence"]],
            passed=confidence_values == {expected["assignment_confidence"]},
        )
        wrong_unit_rejected = False
        try:
            process_raman_result(
                workspace,
                characterization_metadata_path=raw.metadata_path,
                project_id=project["project_id"],
                sample_refs=["sample-benchmark-001"],
                request=RamanProcessingRequest(
                    x_column="col_0",
                    y_column="col_1",
                    x_unit="eV",
                    processing_parameters=default_processing_parameters(),
                    column_review_ref=column_review.stem,
                    parameter_review_ref=parameter_review.stem,
                ),
                created_at="2026-07-10T17:05:00",
            )
        except (RamanProcessingError, ValueError):
            wrong_unit_rejected = True
        _check(
            checks,
            code="invalid_wrong_axis_unit",
            actual="rejected" if wrong_unit_rejected else "accepted",
            expected="rejected",
            passed=wrong_unit_rejected,
        )

    reviewer_path = benchmark_path.parent / "scientific-review.yml"
    reviewer = read_yaml(reviewer_path)
    machine_status = "pass" if all(item["status"] == "pass" for item in checks) else "fail"
    result = {
        "schema_version": "1.0",
        "benchmark_id": benchmark["benchmark_id"],
        "benchmark_type": benchmark["benchmark_type"],
        "machine_status": machine_status,
        "scientific_review_status": reviewer.get("review_status"),
        "promotion_status": "eligible_for_release" if machine_status == "pass" and reviewer.get("review_status") == "approved" else "review_required",
        "checks": checks,
        "limitations": [
            "This is a software reproducibility golden, not independent external scientific validation.",
            "Release acceptance requires the declared simulated scientific review and manual artifact inspection.",
        ],
    }
    if output_path:
        write_yaml(output_path, result)
    return result
