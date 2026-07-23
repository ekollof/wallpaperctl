"""Cinnamon wallpaper via gsettings."""

from __future__ import annotations

import logging
import time

from wallpaperctl.context import WallpaperContext
from wallpaperctl.set.base import debug_set
from wallpaperctl.util import have, run

log = logging.getLogger("wallpaperctl")


class CinnamonSetter:
    name = "cinnamon"

    def applies(self, ctx: WallpaperContext) -> bool:
        return ctx.de.cinnamon

    def set_wallpaper(self, ctx: WallpaperContext) -> bool:
        path = ctx.path.resolve()
        if not have("gsettings"):
            debug_set(self.name, "gsettings not found", ctx)
            return False
        uri = path.as_uri()
        scaling = ctx.ops.wallpaper_scaling_cinnamon

        ok = False
        r = run(
            ["gsettings", "set", "org.gnome.desktop.background", "picture-uri", uri],
            timeout=10,
        )
        if r.returncode == 0:
            ok = True
            debug_set(self.name, "set via GNOME schema", ctx)
        else:
            r2 = run(
                [
                    "gsettings",
                    "set",
                    "org.cinnamon.desktop.background",
                    "picture-uri",
                    uri,
                ],
                timeout=10,
            )
            ok = r2.returncode == 0
            debug_set(self.name, f"direct cinnamon set: {ok}", ctx)

        run(
            [
                "gsettings",
                "set",
                "org.gnome.desktop.background",
                "picture-options",
                scaling,
            ],
            timeout=10,
        )
        run(
            [
                "gsettings",
                "set",
                "org.cinnamon.desktop.background",
                "picture-options",
                scaling,
            ],
            timeout=10,
        )
        time.sleep(0.5)
        return ok
