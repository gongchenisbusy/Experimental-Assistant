from __future__ import annotations

import os
from pathlib import Path

from ea.storage.files import atomic_copy_file
from ea.storage.ids import _pid_is_alive


def test_atomic_copy_preserves_readonly_source_without_reopening_temp_for_write(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.txt"
    destination = tmp_path / "nested" / "destination.txt"
    source.write_bytes(b"portable copy\n")
    source.chmod(0o400)

    atomic_copy_file(source, destination)

    assert destination.read_bytes() == source.read_bytes()
    assert destination.stat().st_mode & 0o777 == source.stat().st_mode & 0o777


def test_current_process_is_alive_without_platform_signal_probe(monkeypatch) -> None:
    def fail_probe(pid: int, signal: int) -> None:
        raise OSError("platform probe unavailable")

    monkeypatch.setattr("ea.storage.ids.os.kill", fail_probe)

    assert _pid_is_alive(os.getpid()) is True
