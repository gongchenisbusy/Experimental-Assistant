from __future__ import annotations

from pathlib import Path

from scripts.check_docs_links import check_docs_links


def test_docs_link_check_reports_only_missing_local_targets(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "present.md").write_text("# Present\n", encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "[present](docs/present.md) [section](#section) [web](https://example.com) [missing](docs/missing.md)\n",
        encoding="utf-8",
    )

    result = check_docs_links(tmp_path)

    assert result["status"] == "fail"
    assert result["local_links_checked"] == 2
    assert result["findings"] == [{"source": "README.md", "target": "docs/missing.md", "line": 1}]
