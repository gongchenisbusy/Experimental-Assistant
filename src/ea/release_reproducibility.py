from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any

from ea import __version__
from ea.identity import DISTRIBUTION_NAME
from ea.storage.files import atomic_write_bytes, atomic_write_text


DEFAULT_OUTPUT = (
    Path("dist") / f"experimental-assistant-{__version__}-reproducibility.json"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_date_epoch(root: Path) -> str:
    completed = subprocess.run(
        ["git", "show", "-s", "--format=%ct", "HEAD"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return (
        completed.stdout.strip()
        if completed.returncode == 0 and completed.stdout.strip()
        else "0"
    )


def canonicalize_sdist(path: Path, *, source_date_epoch: str) -> dict[str, Any]:
    entries: list[tuple[tarfile.TarInfo, bytes | None]] = []
    with tarfile.open(path, "r:gz") as source:
        for original in source.getmembers():
            member = copy.copy(original)
            payload = source.extractfile(original).read() if original.isfile() else None
            member.mtime = int(source_date_epoch)
            member.uid = 0
            member.gid = 0
            member.uname = ""
            member.gname = ""
            member.pax_headers = {}
            entries.append((member, payload))

    tar_buffer = io.BytesIO()
    with tarfile.open(
        fileobj=tar_buffer, mode="w", format=tarfile.PAX_FORMAT
    ) as target:
        for member, payload in sorted(entries, key=lambda item: item[0].name):
            target.addfile(member, io.BytesIO(payload) if payload is not None else None)

    gzip_buffer = io.BytesIO()
    with gzip.GzipFile(
        filename="",
        mode="wb",
        fileobj=gzip_buffer,
        compresslevel=9,
        mtime=int(source_date_epoch),
    ) as compressed:
        compressed.write(tar_buffer.getvalue())
    atomic_write_bytes(path, gzip_buffer.getvalue())
    return {
        "artifact": path.name,
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
    }


def canonicalize_distribution_sdists(
    root: Path, *, source_date_epoch: str
) -> list[dict[str, Any]]:
    normalized = DISTRIBUTION_NAME.replace("-", "_")
    return [
        canonicalize_sdist(path, source_date_epoch=source_date_epoch)
        for path in sorted((root / "dist").glob(f"{normalized}-{__version__}.tar.gz"))
    ]


def _build_once(
    root: Path, output: Path, *, python_executable: str, source_date_epoch: str
) -> dict[str, Any]:
    env = os.environ.copy()
    env["SOURCE_DATE_EPOCH"] = source_date_epoch
    constraints = root / "requirements" / "release.txt"
    if constraints.is_file():
        env["PIP_CONSTRAINT"] = constraints.resolve().as_uri()
    completed = subprocess.run(
        [python_executable, "-m", "build", "--outdir", str(output)],
        cwd=root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode == 0:
        for sdist in output.glob("*.tar.gz"):
            canonicalize_sdist(sdist, source_date_epoch=source_date_epoch)
    return {
        "status": "pass" if completed.returncode == 0 else "fail",
        "returncode": completed.returncode,
        "detail": (completed.stderr or completed.stdout).strip()[-2000:]
        if completed.returncode
        else "",
    }


def _artifact_records(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for item in sorted(path.iterdir() if path.is_dir() else []):
        if not item.is_file() or not (
            item.name.endswith(".whl") or item.name.endswith(".tar.gz")
        ):
            continue
        records[item.name] = {
            "sha256": _sha256(item),
            "size_bytes": item.stat().st_size,
        }
    return records


def publish_reproducible_artifacts(root: Path, source: Path) -> list[dict[str, Any]]:
    """Publish the already-compared deterministic artifacts into ``dist/``."""
    dist = root / "dist"
    records: list[dict[str, Any]] = []
    for name, record in _artifact_records(source).items():
        target = dist / name
        atomic_write_bytes(target, (source / name).read_bytes())
        records.append({"artifact": name, **record})
    return records


def compare_build_directories(
    first: Path, second: Path, *, source_date_epoch: str
) -> dict[str, Any]:
    first_records = _artifact_records(first)
    second_records = _artifact_records(second)
    names_match = set(first_records) == set(second_records)
    comparisons = []
    for name in sorted(set(first_records) | set(second_records)):
        left = first_records.get(name)
        right = second_records.get(name)
        comparisons.append(
            {
                "artifact": name,
                "status": "pass" if left == right and left is not None else "fail",
                "first": left,
                "second": right,
            }
        )
    kinds = {"wheel" if name.endswith(".whl") else "sdist" for name in first_records}
    status = (
        "pass"
        if names_match
        and kinds == {"wheel", "sdist"}
        and all(item["status"] == "pass" for item in comparisons)
        else "fail"
    )
    return {
        "schema_version": "1.0",
        "check_type": "experimental_assistant_reproducible_build",
        "status": status,
        "distribution": DISTRIBUTION_NAME,
        "version": __version__,
        "source_date_epoch": source_date_epoch,
        "scope": "byte-identical wheel and canonicalized sdist built twice from one checkout with the same interpreter and SOURCE_DATE_EPOCH",
        "artifacts": comparisons,
    }


def build_reproducibility_report(
    root: Path, *, python_executable: str = sys.executable
) -> dict[str, Any]:
    root = root.resolve()
    epoch = _source_date_epoch(root)
    release_sdists = canonicalize_distribution_sdists(root, source_date_epoch=epoch)
    with tempfile.TemporaryDirectory(prefix="ea-reproducibility-") as temporary:
        first = Path(temporary) / "first"
        second = Path(temporary) / "second"
        first.mkdir()
        second.mkdir()
        first_build = _build_once(
            root, first, python_executable=python_executable, source_date_epoch=epoch
        )
        second_build = _build_once(
            root, second, python_executable=python_executable, source_date_epoch=epoch
        )
        if first_build["status"] != "pass" or second_build["status"] != "pass":
            return {
                "schema_version": "1.0",
                "check_type": "experimental_assistant_reproducible_build",
                "status": "fail",
                "distribution": DISTRIBUTION_NAME,
                "version": __version__,
                "source_date_epoch": epoch,
                "builds": [first_build, second_build],
                "artifacts": [],
            }
        report = compare_build_directories(first, second, source_date_epoch=epoch)
        report["builds"] = [first_build, second_build]
        report["canonicalized_release_sdists"] = release_sdists
        report["published_release_artifacts"] = (
            publish_reproducible_artifacts(root, first)
            if report["status"] == "pass"
            else []
        )
        return report


def write_reproducibility_report(
    root: Path,
    *,
    python_executable: str = sys.executable,
    output: Path = DEFAULT_OUTPUT,
) -> tuple[Path, dict[str, Any]]:
    root = root.resolve()
    report = build_reproducibility_report(root, python_executable=python_executable)
    output_path = output if output.is_absolute() else root / output
    atomic_write_text(
        output_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    return output_path, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build EA wheel and sdist twice and record byte-level reproducibility evidence."
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    output, report = write_reproducibility_report(
        args.root, python_executable=args.python, output=args.output
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "output": str(output),
                "artifacts": report["artifacts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
