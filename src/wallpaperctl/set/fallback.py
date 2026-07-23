"""Fallback X11 wallpaper setters for standalone WMs."""

from __future__ import annotations

import logging

from wallpaperctl.context import WallpaperContext
from wallpaperctl.set.base import debug_set
from wallpaperctl.util import have, run

log = logging.getLogger("wallpaperctl")

# (command presence, argv builder)
SETTERS = [
    ("feh", lambda p: ["feh", "--bg-max", p]),
    ("nitrogen", lambda p: ["nitrogen", "--set-zoom-fill", p]),
    ("hsetroot", lambda p: ["hsetroot", "-fill", p]),
    ("xwallpaper", lambda p: ["xwallpaper", "--zoom", p]),
    ("xsetbg", lambda p: ["xsetbg", p]),
]


class FallbackSetter:
    name = "fallback"

    def applies(self, ctx: WallpaperContext) -> bool:
        de = ctx.de
        return not (de.plasma or de.hyprland or de.xfce or de.cinnamon)

    def set_wallpaper(self, ctx: WallpaperContext) -> bool:
        path = str(ctx.path.resolve())
        for cmd, builder in SETTERS:
            if not have(cmd):
                debug_set(self.name, f"{cmd} not found", ctx)
                continue
            debug_set(self.name, f"trying {cmd}", ctx)
            r = run(builder(path), timeout=30)
            if r.returncode == 0:
                debug_set(self.name, f"set with {cmd}", ctx)
                return True
            debug_set(self.name, f"{cmd} failed", ctx)
        debug_set(self.name, "no suitable wallpaper setter", ctx)
        return False
