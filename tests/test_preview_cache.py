"""Preview payload cache."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from wallpaperctl.tui.preview_cache import PreviewCache


def test_png_cache_hit(tmp_path: Path) -> None:
    img = tmp_path / "a.jpg"
    Image.new("RGB", (80, 60), color=(1, 2, 3)).save(img)
    cache = PreviewCache(max_entries=8, disk=True, disk_dir=tmp_path / "disk")

    a = cache.get_png(img, max_w=200, max_h=200)
    b = cache.get_png(img, max_w=200, max_h=200)
    assert a is not None and b is not None
    assert a.data == b.data
    assert a.width > 0 and a.height > 0

    # Second call should be memory hit; force new cache that only has disk
    cache2 = PreviewCache(max_entries=8, disk=True, disk_dir=tmp_path / "disk")
    c = cache2.get_png(img, max_w=200, max_h=200)
    assert c is not None
    assert c.data == a.data


def test_sixel_cache_optional(tmp_path: Path) -> None:
    img = tmp_path / "b.png"
    Image.new("RGB", (40, 40), color=(9, 9, 9)).save(img)
    cache = PreviewCache(max_entries=4, disk=False)
    # Without chafa/img2sixel may return None — still must not crash
    cache.get_sixel(img, cols=20, rows=10)


def test_size_cache(tmp_path: Path) -> None:
    img = tmp_path / "c.png"
    Image.new("RGB", (123, 45), color=(0, 0, 0)).save(img)
    cache = PreviewCache(disk=False)
    assert cache.get_image_size(img) == (123, 45)
    assert cache.get_image_size(img) == (123, 45)
