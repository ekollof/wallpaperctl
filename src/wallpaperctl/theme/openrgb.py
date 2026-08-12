"""OpenRGB lighting from wallust palette."""

from __future__ import annotations

from wallpaperctl.context import WallpaperContext
from wallpaperctl.theme.base import debug_op
from wallpaperctl.theme.palette import pick_theme_color
from wallpaperctl.util import have, run


class OpenrgbOp:
    name = "openrgb"

    def enabled(self, ctx: WallpaperContext) -> bool:
        return ctx.ops.enable_openrgb

    def run(self, ctx: WallpaperContext) -> bool:
        if not have("openrgb"):
            debug_op(self.name, "openrgb not found", ctx)
            return True
        strategy = ctx.ops.rgb_color_strategy
        fixed = (
            ctx.ops.openrgb_color_line_plasma
            if ctx.de.plasma
            else ctx.ops.openrgb_color_line_standalone
        )
        color, line = pick_theme_color(strategy, fixed_line=fixed)
        if not color:
            debug_op(self.name, f"no color at line {line}", ctx)
            return False
        hex_only = color.lstrip("#").upper()
        debug_op(self.name, f"setting RGB #{hex_only} (line {line})", ctx)
        r = run(
            ["openrgb", "-m", "Direct", "-c", hex_only],
            timeout=ctx.ops.openrgb_timeout,
        )
        return r.returncode == 0
