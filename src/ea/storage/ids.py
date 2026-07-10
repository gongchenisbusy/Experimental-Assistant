from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import socket
import time
from uuid import uuid4

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

LOCK_STALE_AFTER_SECONDS = 30.0
LOCK_WAIT_ATTEMPTS = 400
LOCK_WAIT_INTERVAL_SECONDS = 0.005


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


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _read_lock_record(lock_path: Path) -> dict:
    try:
        return json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


def recover_stale_counter_lock(root: Path, *, stale_after_seconds: float = LOCK_STALE_AFTER_SECONDS) -> dict:
    lock_path = root / ".ea" / "id_counters.lock"
    if not lock_path.exists():
        return {"status": "not_present", "path": str(lock_path), "recovered": False}
    record = _read_lock_record(lock_path)
    try:
        age_seconds = max(0.0, time.time() - lock_path.stat().st_mtime)
    except FileNotFoundError:
        return {"status": "not_present", "path": str(lock_path), "recovered": False}
    owner_host = str(record.get("hostname") or "")
    owner_pid = int(record.get("pid") or 0)
    same_host = not owner_host or owner_host == socket.gethostname()
    owner_alive = same_host and _pid_is_alive(owner_pid)
    stale = (same_host and owner_pid > 0 and not owner_alive) or (age_seconds >= stale_after_seconds and not owner_alive)
    if not stale:
        return {
            "status": "active",
            "path": str(lock_path),
            "recovered": False,
            "pid": owner_pid or None,
            "hostname": owner_host or None,
            "age_seconds": round(age_seconds, 3),
        }
    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass
    return {
        "status": "recovered",
        "path": str(lock_path),
        "recovered": True,
        "pid": owner_pid or None,
        "hostname": owner_host or None,
        "age_seconds": round(age_seconds, 3),
    }


@contextmanager
def _counter_lock(root: Path):
    lock_path = root / ".ea" / "id_counters.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd: int | None = None
    owner_token = uuid4().hex
    for _ in range(LOCK_WAIT_ATTEMPTS):
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            record = {
                "pid": os.getpid(),
                "hostname": socket.gethostname(),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "owner_token": owner_token,
            }
            os.write(fd, json.dumps(record, sort_keys=True).encode("utf-8"))
            os.fsync(fd)
            break
        except FileExistsError:
            recovered = recover_stale_counter_lock(root)
            if recovered["recovered"]:
                continue
            time.sleep(LOCK_WAIT_INTERVAL_SECONDS)
    if fd is None:
        raise TimeoutError(f"Timed out waiting for ID counter lock: {lock_path}")
    try:
        yield
    finally:
        os.close(fd)
        if _read_lock_record(lock_path).get("owner_token") == owner_token:
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
