"""Wallpaper setter protocol."""

from __future__ import annotations

import logging
from typing import Protocol

from wallpaperctl.context import WallpaperContext

log = logging.getLogger("wallpaperctl")


class WallpaperSetter(Protocol):
    name: str

    def applies(self, ctx: WallpaperContext) -> bool: ...

    def set_wallpaper(self, ctx: WallpaperContext) -> bool: ...


def debug_set(name: str, msg: str, ctx: WallpaperContext) -> None:
    if ctx.debug:
        log.debug("[%s] %s", name, msg)
