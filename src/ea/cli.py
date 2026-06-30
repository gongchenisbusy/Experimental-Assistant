from __future__ import annotations

import argparse
from pathlib import Path

from ea.projects.service import initialize_project


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ea")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="initialize a local EA project workspace")
    init.add_argument("workspace", type=Path)
    init.add_argument("--name", required=True)
    init.add_argument("--direction", required=True)
    init.add_argument("--material", required=True)
    init.add_argument("--experiment-type", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "init":
        initialize_project(
            args.workspace,
            project_name=args.name,
            research_direction=args.direction,
            material_system=args.material,
            experiment_type=args.experiment_type,
        )
        return 0
    raise AssertionError(f"Unhandled command: {args.command}")
