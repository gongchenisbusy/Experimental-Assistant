from __future__ import annotations

from contextlib import contextmanager
from datetime import date
import os
from pathlib import Path
import time

from ea.storage.files import read_yaml, write_yaml
from ea.standards import format_standard_id

KIND_PREFIX = {
    "project": "project",
    "experiment": "exp",
    "characterization": "char",
    "raman_result": "raman-result",
    "image_result": "image-result",
    "report": "report",
    "review": "review",
    "provenance": "prov",
    "progress": "progress",
    "suggestion": "suggestion",
    "decision": "decision",
    "knowledge": "knowledge",
    "open_item": "openitem",
    "memory": "mem",
    "memory_candidate": "memcand",
    "reference": "ref",
    "evaluation": "eval",
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


@contextmanager
def _counter_lock(root: Path):
    lock_path = root / ".ea" / "id_counters.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd: int | None = None
    for _ in range(400):
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode("utf-8"))
            break
        except FileExistsError:
            time.sleep(0.005)
    if fd is None:
        raise TimeoutError(f"Timed out waiting for ID counter lock: {lock_path}")
    try:
        yield
    finally:
        os.close(fd)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def next_id(root: Path, kind: str, day: date | str | None = None) -> str:
    day_key = today_key(day)
    counter_path = root / ".ea" / "id_counters.yml"
    with _counter_lock(root):
        counters = read_yaml(counter_path) if counter_path.exists() else {}
        key = f"{kind}:{day_key}"
        sequence = int(counters.get(key, 0)) + 1
        counters[key] = sequence
        write_yaml(counter_path, counters)
    return format_id(kind, day_key, sequence)


def next_standard_id(
    root: Path,
    kind: str,
    project_slug: str,
    *,
    day: date | str | None = None,
    method: str | None = None,
    hash8: str | None = None,
) -> str:
    day_key = today_key(day)
    method_key = method or "none"
    counter_path = root / ".ea" / "id_counters.yml"
    with _counter_lock(root):
        counters = read_yaml(counter_path) if counter_path.exists() else {}
        key = f"standard:{kind}:{project_slug}:{method_key}:{day_key}"
        sequence = int(counters.get(key, 0)) + 1
        counters[key] = sequence
        write_yaml(counter_path, counters)
    return format_standard_id(
        kind,
        project_slug,
        day=day_key,
        sequence=sequence,
        method=method,
        hash8=hash8,
    )
