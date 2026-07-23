"""nwg-look GTK / xsettingsd reload."""

from __future__ import annotations

from wallpaperctl.context import WallpaperContext
from wallpaperctl.theme.base import debug_op
from wallpaperctl.util import have, run


class NwgLookOp:
    name = "nwg-look"

    def enabled(self, ctx: WallpaperContext) -> bool:
        return ctx.ops.enable_nwg_look and not (
            ctx.de.plasma or ctx.de.xfce or ctx.de.cinnamon
        )

    def run(self, ctx: WallpaperContext) -> bool:
        if not have("nwg-look"):
            debug_op(self.name, "nwg-look not found", ctx)
            return True
        r = run(["nwg-look", "-x", "-a"], timeout=30)
        return r.returncode == 0
