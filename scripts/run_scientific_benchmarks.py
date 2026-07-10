#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ea.scientific_benchmarks import run_raman_golden_benchmark


def main() -> int:
    parser = argparse.ArgumentParser(description="Run EA scientific reproducibility benchmarks.")
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_raman_golden_benchmark(args.repository, output_path=args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["machine_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
