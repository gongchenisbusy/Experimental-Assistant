#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import sys


MIN_PYTHON = (3, 11)
REPOSITORY_URL = "https://github.com/gongchenisbusy/Experimental-Assistant"
RELEASE_LABEL = "v0.9.6"


def main() -> int:
    version = sys.version_info[:3]
    python_ok = version >= MIN_PYTHON
    uv_path = shutil.which("uv")
    result = {
        "schema_version": "0.9",
        "check_type": "ea_install_environment_preflight",
        "status": "pass" if python_ok else "fail",
        "product": "Experimental Assistant",
        "public_version": "Experimental Assistant v0.9.6",
        "python": {
            "executable": sys.executable,
            "version": ".".join(str(part) for part in version),
            "required": f">={MIN_PYTHON[0]}.{MIN_PYTHON[1]}",
            "status": "pass" if python_ok else "fail",
        },
        "uv": {
            "path": uv_path,
            "status": "available" if uv_path else "not_found",
        },
        "next_steps": [],
    }
    if not python_ok:
        result["next_steps"] = [
            "Do not continue with python3 -m pip install until python3 is 3.11 or newer.",
            "Recommended: uv python install 3.12",
            f"Then install EA with: uv tool install --python 3.12 git+{REPOSITORY_URL}.git@{RELEASE_LABEL}",
        ]
    else:
        result["next_steps"] = [
            "Python is compatible.",
            f"Recommended public install: uv tool install --python 3.12 git+{REPOSITORY_URL}.git@{RELEASE_LABEL}",
            "Then run: ea codex install-skill",
            "Then run: ea install-check",
        ]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if python_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
