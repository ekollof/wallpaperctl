"""Local wallpaper library selection."""

from __future__ import annotations

import logging
import random
from pathlib import Path

from wallpaperctl.config import OpsConfig
from wallpaperctl.media import ANIMATED_SUFFIXES
from wallpaperctl.util import home

log = logging.getLogger("wallpaperctl")

# Common still-image extensions (case-insensitive). Matches shell library intent
# while skipping non-images that may sit under ~/Wallpapers.
_IMAGE_SUFFIXES = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".bmp",
        ".gif",
        ".tif",
        ".tiff",
        ".jxl",
        ".avif",
        ".heic",
        ".heif",
    }
)


def wallpaper_dir(ops: OpsConfig | None = None) -> Path:
    if ops:
        return ops.path("wallpaper_dir")
    return home() / "Wallpapers"


def list_wallpaper_files(directory: Path) -> list[Path]:
    """Collect image files under *directory* recursively (skip hidden names)."""
    if not directory.is_dir():
        return []
    files: list[Path] = []
    for p in directory.rglob("*"):
        if not p.is_file():
            continue
        # Skip hidden files and anything under a hidden path component
        if any(part.startswith(".") for part in p.relative_to(directory).parts):
            continue
        if p.suffix.lower() not in _IMAGE_SUFFIXES:
            continue
        files.append(p)
    return files


def list_animated_files(directory: Path) -> list[Path]:
    """Collect animated files under *directory* recursively (skip hidden)."""
    if not directory.is_dir():
        return []
    return [
        p
        for p in directory.rglob("*")
        if p.is_file() and p.suffix.lower() in ANIMATED_SUFFIXES
    ]


def pick_random_wallpaper(
    ops: OpsConfig | None = None, *, animated_only: bool = False
) -> Path:
    directory = wallpaper_dir(ops)
    if not directory.is_dir():
        raise SystemExit(f"Error: Wallpaper directory '{directory}' not found!")
    if animated_only:
        animated_dir = directory / "animated"
        files = list_animated_files(animated_dir)
        if not files:
            raise SystemExit(f"Error: No animated wallpapers found in '{animated_dir}'!")
    else:
        files = list_wallpaper_files(directory)
        if not files:
            raise SystemExit(f"Error: No wallpapers found in '{directory}'!")
    choice = random.choice(files)
    log.debug("Picked local wallpaper: %s", choice)
    return choice
