from __future__ import annotations

import os
from pathlib import Path

from ea.storage.files import atomic_copy_file
from ea.storage.ids import _pid_is_alive


def test_atomic_copy_flushes_with_writable_descriptor(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    destination = tmp_path / "nested" / "destination.txt"
    source.write_bytes(b"portable copy\n")
    opened_modes: list[str] = []
    original_open = Path.open

    def recording_open(path: Path, mode: str = "r", *args, **kwargs):
        opened_modes.append(mode)
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", recording_open)

    atomic_copy_file(source, destination)

    assert destination.read_bytes() == source.read_bytes()
    assert "rb+" in opened_modes


def test_current_process_is_alive_without_platform_signal_probe(monkeypatch) -> None:
    def fail_probe(pid: int, signal: int) -> None:
        raise OSError("platform probe unavailable")

    monkeypatch.setattr("ea.storage.ids.os.kill", fail_probe)

    assert _pid_is_alive(os.getpid()) is True
