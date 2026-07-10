from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse


LINK_RE = re.compile(r"!?\[[^\]]*\]\((?P<target>[^)]+)\)")
DEFAULT_ROOTS = [Path("README.md"), Path("docs")]


def _markdown_files(root: Path, scan_roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for relative in scan_roots:
        path = root / relative
        if path.is_file() and path.suffix.lower() == ".md":
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(path.rglob("*.md")))
    return sorted(set(files))


def _link_path(raw: str) -> str | None:
    target = raw.strip()
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    else:
        target = target.split(maxsplit=1)[0]
    if not target or target.startswith("#"):
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return None
    if parsed.path.startswith("/"):
        return None
    return unquote(parsed.path)


def check_docs_links(
    root: Path, *, scan_roots: list[Path] | None = None
) -> dict[str, object]:
    root = root.resolve()
    files = _markdown_files(root, scan_roots or DEFAULT_ROOTS)
    findings = []
    checked = 0
    for source in files:
        text = source.read_text(encoding="utf-8")
        for match in LINK_RE.finditer(text):
            target = _link_path(match.group("target"))
            if target is None:
                continue
            checked += 1
            destination = Path(target)
            resolved = (
                destination
                if destination.is_absolute()
                else source.parent / destination
            )
            if not resolved.exists():
                findings.append(
                    {
                        "source": source.relative_to(root).as_posix(),
                        "target": target,
                        "line": text.count("\n", 0, match.start()) + 1,
                    }
                )
    return {
        "check": "documentation_links",
        "status": "pass" if not findings else "fail",
        "files_scanned": len(files),
        "local_links_checked": checked,
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    root = Path(args[0]).resolve() if args else Path.cwd().resolve()
    result = check_docs_links(root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
