from __future__ import annotations

import hashlib
import re
from datetime import date


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or "project"


def short_hash(value: bytes | str, length: int = 8) -> str:
    payload = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()[:length]


def _day_key(value: date | str | None = None) -> str:
    if value is None:
        return date.today().strftime("%Y%m%d")
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    return value.replace("-", "")


def standard_project_id(project_slug: str) -> str:
    return f"prj-{slugify(project_slug)}"


def infer_project_slug(project_id: str, fallback: str = "project") -> str:
    if project_id.startswith("prj-"):
        return slugify(project_id[4:])
    match = re.match(r"project-\d{8}-(?P<slug>.+)$", project_id)
    if match:
        return slugify(match.group("slug"))
    return slugify(fallback)


def format_standard_id(
    kind: str,
    project_slug: str,
    *,
    day: date | str | None = None,
    sequence: int = 1,
    method: str | None = None,
    hash8: str | None = None,
) -> str:
    day_key = _day_key(day)
    slug = slugify(project_slug)
    if kind == "project":
        return standard_project_id(slug)
    if kind == "raw":
        if not hash8:
            raise ValueError("raw IDs require hash8")
        return f"raw-{slug}-{day_key}-{sequence:03d}-{hash8[:8]}"
    if kind == "result":
        if not method:
            raise ValueError("result IDs require method")
        return f"res-{slug}-{slugify(method)}-{day_key}-{sequence:03d}"
    if kind == "report":
        return f"rpt-{slug}-{day_key}-{sequence:03d}"
    if kind == "figure":
        if not method:
            raise ValueError("figure IDs require method")
        return f"fig-{slug}-{slugify(method)}-{day_key}-{sequence:03d}"
    raise ValueError(f"Unsupported standard ID kind: {kind}")
