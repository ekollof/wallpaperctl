"""Merge wallust Xresources."""

from __future__ import annotations

from pathlib import Path

from wallpaperctl.context import WallpaperContext
from wallpaperctl.theme.base import debug_op
from wallpaperctl.util import have, home, run


class XresourcesOp:
    name = "xresources"

    def enabled(self, ctx: WallpaperContext) -> bool:
        return ctx.ops.enable_xresources and not (
            ctx.de.plasma or ctx.de.hyprland or ctx.de.xfce
        )

    def run(self, ctx: WallpaperContext) -> bool:
        path = home() / ".cache" / "wal" / "colors.Xresources"
        if not path.is_file():
            debug_op(self.name, f"missing {path}", ctx)
            return False
        if not have("xrdb"):
            debug_op(self.name, "xrdb not found", ctx)
            return False
        r = run(["xrdb", "-merge", str(path)], timeout=10)
        return r.returncode == 0
