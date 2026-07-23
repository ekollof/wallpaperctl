"""Hyprland wallpaper via hyprpaper."""

from __future__ import annotations

import logging

from wallpaperctl.context import WallpaperContext
from wallpaperctl.set.base import debug_set
from wallpaperctl.util import have, run

log = logging.getLogger("wallpaperctl")


class HyprlandSetter:
    name = "hyprland"

    def applies(self, ctx: WallpaperContext) -> bool:
        return ctx.de.hyprland and not ctx.de.noctalia

    def set_wallpaper(self, ctx: WallpaperContext) -> bool:
        path = ctx.path.resolve()
        if not path.is_file():
            return False
        if not have("hyprctl"):
            debug_set(self.name, "hyprctl not found", ctx)
            return False
        ver = run(["hyprctl", "hyprpaper", "version"], timeout=5)
        if ver.returncode != 0:
            debug_set(self.name, "hyprpaper not available", ctx)
            return False

        preload = run(["hyprctl", "hyprpaper", "preload", str(path)], timeout=30)
        if preload.returncode != 0:
            debug_set(self.name, "preload failed", ctx)
            return False

        # Comma syntax sets all monitors
        set_r = run(["hyprctl", "hyprpaper", "wallpaper", f",{path}"], timeout=15)
        if set_r.returncode != 0:
            run(["hyprctl", "hyprpaper", "unload", str(path)], timeout=10)
            debug_set(self.name, "wallpaper set failed", ctx)
            return False
        debug_set(self.name, "wallpaper set successfully", ctx)
        return True
