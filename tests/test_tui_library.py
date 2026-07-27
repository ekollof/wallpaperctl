"""Library scan/filter for manage TUI."""

from __future__ import annotations

from pathlib import Path

from wallpaperctl.tui.library import filter_items, scan_library


def test_scan_and_filter(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    a = tmp_path / "a.jpg"
    b = tmp_path / "nested" / "b.png"
    a.write_bytes(b"1")
    b.write_bytes(b"2")

    items = scan_library(tmp_path, with_dimensions=False)
    assert len(items) == 2
    by_name = {i.name: i for i in items}
    assert "a.jpg" in by_name and "b.png" in by_name

    only = filter_items(items, query="nested")
    assert len(only) == 1 and only[0].name == "b.png"

    none = filter_items(items, query="zzzz")
    assert none == []
