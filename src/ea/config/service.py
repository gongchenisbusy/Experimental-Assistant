from __future__ import annotations

from pathlib import Path
from typing import Any

from ea.storage.files import read_yaml, write_yaml

FORBIDDEN_PUBLIC_DEFAULT_FRAGMENTS = [
    "/Users/geecoe",
    "zotero.sqlite",
    "Chrome/Profile",
    "Library/Application Support/Google/Chrome",
]


def build_project_config(
    *,
    project_slug: str,
    report_language: str = "zh",
    enable_literature: bool = False,
    enable_zotero: bool = False,
    literature_cache_root: str | None = None,
    zotero_local_api_url: str | None = None,
    zotero_collection: str | None = None,
    browser_assist_enabled: bool = False,
    browser_name: str | None = None,
    browser_profile: str | None = None,
    institution_access: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "0.2",
        "project_slug": project_slug,
        "report_language": report_language,
        "public_initialization": {
            "uses_developer_machine_defaults": False,
            "required_user_supplied_fields": [],
        },
        "literature": {
            "enabled": enable_literature,
            "cache_root": literature_cache_root,
            "deployment_status": "literature/deployment_status.yml",
        },
        "zotero": {
            "enabled": enable_zotero,
            "local_api_url": zotero_local_api_url,
            "collection": zotero_collection,
        },
        "browser_assist": {
            "enabled": browser_assist_enabled,
            "browser": browser_name,
            "profile": browser_profile,
        },
        "institution_access": {
            "enabled": bool(institution_access),
            "note": institution_access,
            "stores_credentials": False,
        },
    }


def write_project_config(root: Path, config: dict[str, Any]) -> Path:
    return write_yaml(root / ".ea" / "project_config.yml", config)


def _string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        result: list[str] = []
        for item in value.values():
            result.extend(_string_values(item))
        return result
    if isinstance(value, list):
        result = []
        for item in value:
            result.extend(_string_values(item))
        return result
    return []


def doctor_project_config(root: Path) -> dict[str, Any]:
    config_path = root / ".ea" / "project_config.yml"
    if not config_path.exists():
        return {
            "status": "missing",
            "config_path": str(config_path),
            "errors": ["missing_project_config"],
            "warnings": [],
        }
    config = read_yaml(config_path)
    strings = _string_values(config)
    forbidden = [
        fragment
        for fragment in FORBIDDEN_PUBLIC_DEFAULT_FRAGMENTS
        if any(fragment in value for value in strings)
    ]
    errors = []
    if config.get("public_initialization", {}).get("uses_developer_machine_defaults"):
        errors.append("developer_machine_defaults_enabled")
    if forbidden:
        errors.append("forbidden_local_default_fragment")
    return {
        "status": "pass" if not errors else "fail",
        "config_path": str(config_path),
        "errors": errors,
        "warnings": [],
        "forbidden_fragments": forbidden,
    }
