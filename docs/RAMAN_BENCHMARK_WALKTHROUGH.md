# Raman Benchmark Walkthrough

The repository includes a deterministic Raman software golden so maintainers and users can verify that the same reviewed MoS2 fixture produces bounded peak-fitting and assignment outputs.

Run:

```bash
python3 scripts/run_scientific_benchmarks.py \
  --output build/raman-benchmark-result.yml
```

The benchmark verifies the fixture hash, peak-count range, E2g-like and A1g-like fitted centers, mode separation, assignment confidence, and rejection of a wrong Raman axis unit. Expected values and tolerances live in `benchmarks/raman-v1/benchmark.yml`.

This is an internal reproducibility test. It does not prove material identity, layer number, universal instrument accuracy, or scientific correctness across instruments and samples. Peak positions can depend on calibration, excitation, substrate, strain, doping, temperature, preprocessing, and fitting choices.

Release acceptance also requires a clearly labeled simulated scientific review of units, preprocessing, fitting, assignment windows, uncertainty, invalid use, and report language in `benchmarks/raman-v1/scientific-review.yml`. The review must be bound to the candidate commit and its findings fixed or dispositioned. It validates the release contract but is not independent expert endorsement.
