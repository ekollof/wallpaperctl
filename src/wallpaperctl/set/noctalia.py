"""Noctalia shell wallpaper via qs IPC."""

from __future__ import annotations

import logging

from wallpaperctl.context import WallpaperContext
from wallpaperctl.set.base import debug_set
from wallpaperctl.util import have, run

log = logging.getLogger("wallpaperctl")


class NoctaliaSetter:
    name = "noctalia"

    def applies(self, ctx: WallpaperContext) -> bool:
        return ctx.de.noctalia

    def set_wallpaper(self, ctx: WallpaperContext) -> bool:
        path = ctx.path.resolve()
        if not path.is_file():
            return False
        if not have("qs"):
            debug_set(self.name, "qs not found", ctx)
            return False
        r = run(
            [
                "qs",
                "-c",
                "noctalia-shell",
                "ipc",
                "call",
                "wallpaper",
                "set",
                str(path),
                "all",
            ],
            timeout=15,
        )
        if r.returncode != 0:
            debug_set(self.name, "qs IPC wallpaper set failed", ctx)
            return False
        debug_set(self.name, "Noctalia wallpaper set", ctx)
        return True
