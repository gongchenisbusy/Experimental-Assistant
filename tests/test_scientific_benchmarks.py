from pathlib import Path

from ea.scientific_benchmarks import run_raman_golden_benchmark
from ea.storage import read_yaml


def test_raman_golden_is_machine_reproducible_but_not_externally_approved(tmp_path: Path) -> None:
    output = tmp_path / "raman-result.yml"
    result = run_raman_golden_benchmark(Path.cwd(), output_path=output)

    assert result["machine_status"] == "pass"
    assert result["scientific_review_status"] == "pending_external_reviewer"
    assert result["promotion_status"] == "remain_beta"
    assert all(check["status"] == "pass" for check in result["checks"])
    assert {check["code"] for check in result["checks"]} >= {
        "source_hash",
        "peak_count_range",
        "assigned_center_mos2_e2g_like",
        "assigned_center_mos2_a1g_like",
        "mode_separation",
        "invalid_wrong_axis_unit",
    }
    assert read_yaml(output)["promotion_status"] == "remain_beta"
