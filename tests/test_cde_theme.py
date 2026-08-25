"""CDE Style Manager palette generation."""

from __future__ import annotations

from pathlib import Path

from wallpaperctl.theme.cde import (
    PALETTE_NAME,
    _update_color_palette_line,
    build_cde_palette_lines,
    hex_to_cde_rgb,
    update_session_resources,
    write_cde_palette_file,
)


def test_hex_to_cde_rgb() -> None:
    assert hex_to_cde_rgb("#080b13") == "#08080b0b1313"
    assert hex_to_cde_rgb("#FFFFFF") == "#ffffffffffff"


def test_build_palette_eight_slots() -> None:
    colors = [f"#{i:02x}{i:02x}{i:02x}" for i in range(16)]
    lines = build_cde_palette_lines(colors)
    assert len(lines) == 8
    assert all(line.startswith("#") and len(line) == 13 for line in lines)


def test_write_palette_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("wallpaperctl.theme.cde.home", lambda: tmp_path)
    colors = [f"#{i:02x}0000" for i in range(8)]
    path = write_cde_palette_file(colors)
    assert path.name == PALETTE_NAME
    text = path.read_text(encoding="utf-8")
    assert text.count("\n") == 8
    assert text.splitlines()[0] == "#000000000000"


def test_update_color_palette_line_replaces() -> None:
    old = "*0*ColorPalette:\tGrayScale.dp\n*0*ColorUse:\tDEFAULT\n"
    new = _update_color_palette_line(old, "Wallpaperctl.dp")
    assert "*0*ColorPalette:\tWallpaperctl.dp" in new
    assert "GrayScale" not in new


def test_update_session_resources(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("wallpaperctl.theme.cde.home", lambda: tmp_path)
    sess = tmp_path / ".dt/sessions/current/dt.resources"
    sess.parent.mkdir(parents=True)
    sess.write_text("*0*ColorPalette:\tAlpine.dp\n*background:\t#fff\n", encoding="utf-8")
    written = update_session_resources(paths=[sess])
    assert written == [sess]
    body = sess.read_text(encoding="utf-8")
    assert "Wallpaperctl.dp" in body
    assert "Alpine" not in body
