"""Wallpaper library index for the manage TUI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from wallpaperctl.sources.local import list_wallpaper_files


@dataclass
class WallpaperItem:
    path: Path
    rel: str
    size: int = 0
    mtime: float = 0.0
    width: int = 0
    height: int = 0

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def mtime_label(self) -> str:
        if not self.mtime:
            return ""
        return datetime.fromtimestamp(self.mtime).strftime("%Y-%m-%d %H:%M")

    @property
    def size_label(self) -> str:
        n = self.size
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024 or unit == "GB":
                return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
            n /= 1024
        return f"{self.size} B"

    @property
    def dim_label(self) -> str:
        if self.width and self.height:
            return f"{self.width}×{self.height}"
        return "?"


def scan_library(
    root: Path,
    tags: object | None = None,  # unused; kept for call-site compatibility
    *,
    with_dimensions: bool = False,
) -> list[WallpaperItem]:
    """List wallpapers under *root* with optional dimensions."""
    root = root.expanduser().resolve()
    files = list_wallpaper_files(root)
    items: list[WallpaperItem] = []
    for p in files:
        try:
            st = p.stat()
            size, mtime = st.st_size, st.st_mtime
        except OSError:
            size, mtime = 0, 0.0
        try:
            rel = str(p.relative_to(root))
        except ValueError:
            rel = p.name
        w = h = 0
        if with_dimensions:
            w, h = _image_size(p)
        items.append(
            WallpaperItem(
                path=p,
                rel=rel,
                size=size,
                mtime=mtime,
                width=w,
                height=h,
            )
        )
    items.sort(key=lambda i: i.mtime, reverse=True)
    return items


def _image_size(path: Path) -> tuple[int, int]:
    try:
        from PIL import Image

        with Image.open(path) as img:
            return img.size
    except Exception:
        return 0, 0


def filter_items(
    items: list[WallpaperItem],
    *,
    query: str = "",
    tag: str = "",  # unused (legacy); multi-select is in-memory marks
) -> list[WallpaperItem]:
    q = query.strip().lower()
    if not q:
        return list(items)
    return [it for it in items if q in it.rel.lower()]
