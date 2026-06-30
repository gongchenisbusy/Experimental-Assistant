from __future__ import annotations

from datetime import date
from pathlib import Path

from ea.storage.files import read_yaml, write_yaml

KIND_PREFIX = {
    "project": "project",
    "experiment": "exp",
    "characterization": "char",
    "raman_result": "raman-result",
    "report": "report",
    "review": "review",
    "provenance": "prov",
    "progress": "progress",
    "suggestion": "suggestion",
    "decision": "decision",
    "knowledge": "knowledge",
    "open_item": "openitem",
}


def today_key(value: date | str | None = None) -> str:
    if value is None:
        return date.today().strftime("%Y%m%d")
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    return value.replace("-", "")


def format_id(kind: str, day: date | str | None = None, sequence: int = 1) -> str:
    prefix = KIND_PREFIX.get(kind, kind)
    if kind == "project":
        return f"{prefix}-{today_key(day)}"
    return f"{prefix}-{today_key(day)}-{sequence:03d}"


def next_id(root: Path, kind: str, day: date | str | None = None) -> str:
    day_key = today_key(day)
    counter_path = root / ".ea" / "id_counters.yml"
    counters = read_yaml(counter_path) if counter_path.exists() else {}
    key = f"{kind}:{day_key}"
    sequence = int(counters.get(key, 0)) + 1
    counters[key] = sequence
    write_yaml(counter_path, counters)
    return format_id(kind, day_key, sequence)
