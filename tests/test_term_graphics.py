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
