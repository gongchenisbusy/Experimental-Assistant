from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ea.storage.files import write_yaml


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class OperationJournal:
    root: Path
    operation_id: str
    operation: str
    expected_outputs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.path = self.root / ".ea" / "operations" / f"{self.operation_id}.yml"
        self.record: dict[str, Any] = {
            "schema_version": "1.0",
            "operation_id": self.operation_id,
            "operation": self.operation,
            "status": "planned",
            "expected_outputs": list(self.expected_outputs),
            "artifacts_written": [],
            "metadata": dict(self.metadata),
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "error": None,
        }

    def _write(self) -> None:
        self.record["updated_at"] = _now_iso()
        write_yaml(self.path, self.record)

    def __enter__(self) -> "OperationJournal":
        if self.path.exists():
            from ea.storage.files import read_yaml

            existing = read_yaml(self.path)
            if existing.get("status") == "completed":
                raise FileExistsError(f"Operation already completed: {self.operation_id}")
        self.record["status"] = "in_progress"
        self._write()
        return self

    def add_artifact(self, path: Path | str) -> None:
        value = str(path)
        if value not in self.record["artifacts_written"]:
            self.record["artifacts_written"].append(value)
            self._write()

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc is None:
            self.record["status"] = "completed"
            self.record["completed_at"] = _now_iso()
        else:
            self.record["status"] = "failed"
            self.record["error"] = {"type": exc_type.__name__, "message": str(exc)}
        self._write()
        return False
