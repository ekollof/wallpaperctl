"""Preview cache warming."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from wallpaperctl.tui.preview_cache import PreviewCache, warm_preview_cache


def test_warm_preview_cache_png(tmp_path: Path) -> None:
    imgs = []
    for i in range(3):
        p = tmp_path / f"w{i}.jpg"
        Image.new("RGB", (64, 48), color=(i * 40, 10, 10)).save(p)
        imgs.append(p)

    cache = PreviewCache(max_entries=32, disk=True, disk_dir=tmp_path / "disk")
    stats = warm_preview_cache(
        imgs,
        cache=cache,
        kitty=True,
        sixel=False,
        png_size=(128, 128),
    )
    assert stats["ok_png"] == 3
    assert stats["fail"] == 0
    # Second warm should still succeed (disk/memory hits)
    stats2 = warm_preview_cache(
        imgs, cache=cache, kitty=True, sixel=False, png_size=(128, 128)
    )
    assert stats2["ok_png"] == 3
