"""Wallpaper library index for the manage TUI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from wallpaperctl.config import OpsConfig
from wallpaperctl.sources.local import list_animated_files, list_wallpaper_files


@dataclass
class WallpaperItem:
    path: Path
    rel: str
    size: int = 0
    mtime: float = 0.0
    width: int = 0
    height: int = 0
    is_video: bool = False

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
    videos: bool = False,
    ops: OpsConfig | None = None,
) -> list[WallpaperItem]:
    """List wallpapers under *root* with optional dimensions.

    With ``videos=True`` the scan returns animated wallpapers instead of
    images; dimensions come from the cached extracted frame (a representative
    still), which is also what the TUI uses as the thumbnail.
    """
    root = root.expanduser().resolve()
    if videos:
        files = list_animated_files(root)
    else:
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
            if videos:
                w, h = _video_size(p, ops)
            else:
                w, h = _image_size(p)
        items.append(
            WallpaperItem(
                path=p,
                rel=rel,
                size=size,
                mtime=mtime,
                width=w,
                height=h,
                is_video=videos,
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


def video_frame(path: Path, ops: OpsConfig | None = None) -> Path | None:
    """Cached representative still for an animated file (thumbnail source)."""
    from wallpaperctl.media import extract_frame

    return extract_frame(path, ops or OpsConfig())


def _video_size(path: Path, ops: OpsConfig | None) -> tuple[int, int]:
    frame = video_frame(path, ops)
    if frame is None:
        return 0, 0
    return _image_size(frame)


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
