"""Terminal graphics backend selection and block preview."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from wallpaperctl.term_graphics import (
    GraphicsBackend,
    detect_backend,
    render_ansi_preview,
    render_halfblocks,
)


def test_detect_backend_blocks_when_forced() -> None:
    info = detect_backend(prefer="blocks")
    assert info.backend == GraphicsBackend.BLOCKS


def test_detect_backend_no_kitty_skips_kitty() -> None:
    info = detect_backend(no_kitty=True, prefer="auto")
    assert info.backend != GraphicsBackend.KITTY


def test_render_halfblocks_produces_output(tmp_path: Path) -> None:
    img_path = tmp_path / "t.png"
    Image.new("RGB", (32, 32), color=(20, 40, 200)).save(img_path)
    text = render_halfblocks(img_path, cols=16, rows=8)
    assert "▀" in text
    assert "\033[38;2;" in text


def test_render_ansi_preview_blocks(tmp_path: Path) -> None:
    img_path = tmp_path / "t.jpg"
    Image.new("RGB", (64, 48), color=(255, 0, 0)).save(img_path)
    backend, text = render_ansi_preview(
        img_path, cols=20, rows=10, backend=GraphicsBackend.BLOCKS
    )
    assert backend == GraphicsBackend.BLOCKS
    assert len(text) > 10


def test_fit_cells_preserves_wide_aspect() -> None:
    from wallpaperctl.term_graphics import fit_cells

    # 16:9 image in a square-ish pane with square cells → width-limited
    cols, rows = fit_cells(1920, 1080, max_cols=40, max_rows=40, cell_w=10, cell_h=10)
    assert cols <= 40 and rows <= 40
    # width/height in cells ≈ 16/9
    ratio = cols / rows
    assert 1.5 < ratio < 2.0
    # Must not use full 40×40 (that would stretch)
    assert not (cols == 40 and rows == 40)


def test_fit_cells_preserves_tall_aspect() -> None:
    from wallpaperctl.term_graphics import fit_cells

    cols, rows = fit_cells(100, 200, max_cols=40, max_rows=20, cell_w=10, cell_h=20)
    assert cols <= 40 and rows <= 20
    # Image aspect 0.5; cell aspect 0.5 → roughly square in cells
    assert rows >= cols
