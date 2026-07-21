from __future__ import annotations

import argparse


READ_ONLY_TOP_LEVEL_COMMANDS = frozenset(
    {
        "version",
        "capabilities",
        "mode",
        "status",
        "analyze",
        "doctor",
        "install-check",
        "onboarding",
        "healthcheck",
        "lookup-figure",
        "journey",
    }
)

# One registry owns unconditional subcommand effects. Conditional commands such
# as `brief project --no-write` stay in the CLI evaluator next to their flags.
READ_ONLY_SUBCOMMANDS: dict[str, tuple[str, frozenset[str]]] = {
    "raman": (
        "raman_command",
        frozenset({"inspect", "list-assignment-libraries"}),
    ),
    "pl": (
        "pl_command",
        frozenset({"inspect", "list-assignment-libraries"}),
    ),
    "xrd": (
        "xrd_command",
        frozenset({"inspect", "list-assignment-libraries"}),
    ),
    "ftir": (
        "ftir_command",
        frozenset({"inspect", "list-assignment-libraries"}),
    ),
    "uv-vis": (
        "uv_vis_command",
        frozenset({"inspect", "list-source-libraries"}),
    ),
    "xps": (
        "xps_command",
        frozenset({"inspect", "list-parameter-libraries"}),
    ),
    "electrochemistry": (
        "electrochemistry_command",
        frozenset({"inspect"}),
    ),
    "thermal": (
        "thermal_command",
        frozenset({"inspect"}),
    ),
    "materials": (
        "materials_command",
        frozenset({"list", "audit-assignment-library", "show", "assignments"}),
    ),
    "experiment": (
        "experiment_command",
        frozenset({"runs"}),
    ),
}


def is_unconditionally_read_only(args: argparse.Namespace) -> bool:
    command = str(getattr(args, "command", ""))
    if command in READ_ONLY_TOP_LEVEL_COMMANDS:
        return True
    entry = READ_ONLY_SUBCOMMANDS.get(command)
    if entry is None:
        return False
    attribute, read_only_subcommands = entry
    return getattr(args, attribute, None) in read_only_subcommands
