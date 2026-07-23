"""Theme operation protocol."""

from __future__ import annotations

import logging
from typing import Protocol

from wallpaperctl.context import WallpaperContext

log = logging.getLogger("wallpaperctl")


class ThemeOp(Protocol):
    name: str

    def enabled(self, ctx: WallpaperContext) -> bool: ...

    def run(self, ctx: WallpaperContext) -> bool: ...


def debug_op(name: str, msg: str, ctx: WallpaperContext) -> None:
    if ctx.debug:
        log.debug("OPS [%s]: %s", name, msg)
