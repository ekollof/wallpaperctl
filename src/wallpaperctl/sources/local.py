"""Local wallpaper library selection."""

from __future__ import annotations

import logging
import random
from pathlib import Path

from wallpaperctl.config import OpsConfig
from wallpaperctl.util import home

log = logging.getLogger("wallpaperctl")


def wallpaper_dir(ops: OpsConfig | None = None) -> Path:
    if ops:
        return ops.path("wallpaper_dir")
    return home() / "Wallpapers"


def pick_random_wallpaper(ops: OpsConfig | None = None) -> Path:
    directory = wallpaper_dir(ops)
    if not directory.is_dir():
        raise SystemExit(f"Error: Wallpaper directory '{directory}' not found!")
    files = [
        p
        for p in directory.iterdir()
        if p.is_file() and not p.name.startswith(".")
    ]
    if not files:
        raise SystemExit(f"Error: No wallpapers found in '{directory}'!")
    choice = random.choice(files)
    log.debug("Picked local wallpaper: %s", choice)
    return choice
