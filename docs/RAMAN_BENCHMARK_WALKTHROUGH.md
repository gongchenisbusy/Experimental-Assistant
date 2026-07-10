# Raman Benchmark Walkthrough

Raman is a beta capability in v0.9.7. The repository includes a deterministic software golden so maintainers and users can verify that the same reviewed MoS2 fixture produces bounded peak-fitting and assignment outputs.

Run:

```bash
python3 scripts/run_scientific_benchmarks.py \
  --output build/raman-benchmark-result.yml
```

The benchmark verifies the fixture hash, peak-count range, E2g-like and A1g-like fitted centers, mode separation, assignment confidence, and rejection of a wrong Raman axis unit. Expected values and tolerances live in `benchmarks/raman-v1/benchmark.yml`.

This is an internal reproducibility test. It does not prove material identity, layer number, universal instrument accuracy, or scientific correctness across instruments and samples. Peak positions can depend on calibration, excitation, substrate, strain, doping, temperature, preprocessing, and fitting choices.

Stable promotion additionally requires an independent Raman/materials reviewer to complete `benchmarks/raman-v1/scientific-review.yml`, including units, preprocessing, fitting, assignment windows, uncertainty, invalid use, and report-language review. Until that record is approved, machine-pass results leave Raman at `beta`.
