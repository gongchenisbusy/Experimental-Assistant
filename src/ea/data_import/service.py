from __future__ import annotations

import csv
import hashlib
from pathlib import Path
import re
from typing import Any

from ea.raw_import import import_raw_file
from ea.storage.files import read_markdown_record


SUPPORTED_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "cp936", "cp1252")
SUPPORTED_DELIMITERS = {",": "comma", "\t": "tab", ";": "semicolon"}
PREVIEW_BYTES = 256 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decode_sample(data: bytes, requested: str | None) -> tuple[str, str, list[str]]:
    if b"\x00" in data:
        raise ValueError("Input appears to be binary or UTF-16; this importer accepts supported delimited text files.")
    candidates = (requested,) if requested and requested != "auto" else SUPPORTED_ENCODINGS
    successful: list[tuple[str, str]] = []
    for encoding in candidates:
        if encoding is None:
            continue
        try:
            successful.append((encoding, data.decode(encoding)))
        except (UnicodeDecodeError, LookupError):
            continue
    if not successful:
        raise UnicodeError(f"Could not decode the preview using: {', '.join(str(value) for value in candidates)}")

    selected_encoding, text = successful[0]
    warnings: list[str] = []
    if requested in {None, "auto"} and len(successful) > 1:
        alternatives = [encoding for encoding, candidate_text in successful[1:] if candidate_text != text]
        if alternatives:
            warnings.append(f"encoding_ambiguous:{selected_encoding}|{','.join(alternatives)}")
    return selected_encoding, text, warnings


def _detect_delimiter(text: str, requested: str | None) -> tuple[str, list[str]]:
    if requested and requested != "auto":
        delimiter = "\t" if requested in {"tab", "\\t"} else requested
        if delimiter not in SUPPORTED_DELIMITERS:
            raise ValueError("delimiter must be comma, tab, semicolon, ',', '\\t', ';', or auto")
        return delimiter, []
    sample = "\n".join(text.splitlines()[:20])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
        return dialect.delimiter, []
    except csv.Error:
        counts = {delimiter: sample.count(delimiter) for delimiter in SUPPORTED_DELIMITERS}
        best = max(counts, key=counts.get)
        if counts[best] == 0:
            raise ValueError("Could not detect a supported delimiter from the preview.")
        return best, ["delimiter_ambiguous"]


def _unit_proposal(column: str) -> str | None:
    normalized = re.sub(r"[^a-z0-9]+", "_", column.lower()).strip("_")
    proposals = (
        (("wavenumber", "raman_shift", "cm_1", "cm1"), "cm^-1"),
        (("wavelength", "nm"), "nm"),
        (("energy_ev", "binding_energy"), "eV"),
        (("temperature_c", "temp_c"), "degC"),
        (("temperature_k", "temp_k"), "K"),
        (("time_s", "seconds"), "s"),
        (("conductivity", "s_m"), "S/m"),
        (("resistivity", "ohm_m"), "ohm*m"),
    )
    for needles, unit in proposals:
        if any(needle in normalized for needle in needles):
            return unit
    return None


def _looks_numeric_cell(value: str) -> bool:
    value = value.strip().replace(",", "")
    if not value:
        return False
    try:
        float(value)
    except ValueError:
        return False
    return True


def preview_import(
    source_path: Path,
    *,
    encoding: str | None = "auto",
    delimiter: str | None = "auto",
    allow_symlink: bool = False,
    max_rows: int = 5,
) -> dict[str, Any]:
    source_path = source_path.expanduser()
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    if not source_path.is_file():
        raise IsADirectoryError(f"Import source is not a file: {source_path}")
    if source_path.is_symlink() and not allow_symlink:
        raise PermissionError("Symlink import is disabled by default; inspect the resolved source and pass --allow-symlink explicitly.")
    size = source_path.stat().st_size
    if size == 0:
        raise ValueError(f"Import source is empty: {source_path}")
    with source_path.open("rb") as handle:
        data = handle.read(PREVIEW_BYTES)
    selected_encoding, text, warnings = _decode_sample(data, encoding)
    selected_delimiter, delimiter_warnings = _detect_delimiter(text, delimiter)
    warnings.extend(delimiter_warnings)
    rows = list(csv.reader(text.splitlines(), delimiter=selected_delimiter))
    if not rows:
        raise ValueError("No rows were detected in the import preview.")
    first_row_is_data = bool(rows[0]) and all(_looks_numeric_cell(str(value)) for value in rows[0])
    if first_row_is_data:
        columns = [f"col_{index}" for index in range(len(rows[0]))]
        preview_rows = [row for row in rows[:max_rows]]
        warnings.append("header_row_not_detected")
    else:
        columns = [str(value).strip() or f"column_{index}" for index, value in enumerate(rows[0])]
        preview_rows = [row for row in rows[1 : max_rows + 1]]
    inconsistent = [index + 2 for index, row in enumerate(preview_rows) if len(row) != len(columns)]
    if inconsistent:
        warnings.append(f"inconsistent_column_count_rows:{','.join(map(str, inconsistent))}")
    return {
        "schema_version": "1.0",
        "status": "ready" if not inconsistent else "needs_confirmation",
        "read_only": True,
        "source": str(source_path),
        "resolved_source": str(source_path.resolve()),
        "is_symlink": source_path.is_symlink(),
        "size_bytes": size,
        "sha256": _sha256(source_path),
        "encoding": selected_encoding,
        "delimiter": selected_delimiter,
        "delimiter_name": SUPPORTED_DELIMITERS[selected_delimiter],
        "columns": columns,
        "unit_proposals": {column: unit for column in columns if (unit := _unit_proposal(column))},
        "preview_rows": preview_rows,
        "warnings": warnings,
        "truncated_preview": size > len(data),
        "next_steps": ["Review columns, units, encoding, and delimiter; then run `ea import apply ... --preview-hash <sha256> --yes`."],
    }


def _project_id(root: Path) -> str:
    project_path = root / "EA_PROJECT.md"
    if not project_path.is_file():
        raise FileNotFoundError(f"EA_PROJECT.md was not found: {project_path}")
    frontmatter, _ = read_markdown_record(project_path)
    value = frontmatter.get("project_id")
    if not value:
        raise KeyError("project_id")
    return str(value)


def apply_import(
    root: Path,
    source_path: Path,
    *,
    characterization_type: str,
    sample_refs: list[str] | None = None,
    experiment_refs: list[str] | None = None,
    encoding: str | None = "auto",
    delimiter: str | None = "auto",
    allow_symlink: bool = False,
    preview_hash: str | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    preview = preview_import(
        source_path,
        encoding=encoding,
        delimiter=delimiter,
        allow_symlink=allow_symlink,
    )
    if not confirmed:
        return {
            "schema_version": "1.0",
            "status": "needs_confirmation",
            "preview": preview,
            "will_write": [f"raw/{characterization_type}/<characterization-id>/"],
        }
    if not preview_hash:
        raise ValueError("--preview-hash is required for a confirmed import.")
    if preview_hash != preview["sha256"]:
        raise ValueError("The source changed after preview; run preview again and confirm the new SHA-256.")
    result = import_raw_file(
        root,
        source_path,
        project_id=_project_id(root),
        characterization_type=characterization_type,
        sample_refs=sample_refs,
        experiment_refs=experiment_refs,
    )
    return {
        "schema_version": "1.0",
        "status": "completed" if result.import_status in {"imported", "duplicate_alias"} else result.import_status,
        "preview": {
            "sha256": preview["sha256"],
            "encoding": preview["encoding"],
            "delimiter": preview["delimiter"],
            "columns": preview["columns"],
            "unit_proposals": preview["unit_proposals"],
        },
        "characterization_id": result.characterization_id,
        "import_status": result.import_status,
        "metadata_path": str(result.metadata_path),
        "project_raw_path": str(result.project_raw_path) if result.project_raw_path else None,
        "canonical_metadata_path": str(result.canonical_metadata_path) if result.canonical_metadata_path else None,
    }
