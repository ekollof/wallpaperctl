"""wallust color scheme generation."""

from __future__ import annotations

from wallpaperctl.context import WallpaperContext
from wallpaperctl.theme.base import debug_op
from wallpaperctl.util import have, run


class WallustOp:
    name = "wallust"

    def enabled(self, ctx: WallpaperContext) -> bool:
        return ctx.ops.enable_wallust

    def run(self, ctx: WallpaperContext) -> bool:
        if not have("wallust"):
            debug_op(self.name, "wallust not found, skipping", ctx)
            return True
        backend = ctx.ops.wallust_backend
        palette = ctx.ops.wallust_palette
        debug_op(
            self.name,
            f"generating scheme backend={backend} palette={palette}",
            ctx,
        )
        r = run(
            [
                "wallust",
                "run",
                "--backend",
                backend,
                "--palette",
                palette,
                str(ctx.path),
            ],
            timeout=ctx.ops.wallust_timeout,
        )
        if r.returncode == 0:
            debug_op(self.name, "ok", ctx)
            return True
        out = (r.stdout or "") + (r.stderr or "")
        if "couldn't generate a suitable palette" in out:
            debug_op(self.name, "palette generation issue (ok)", ctx)
            return True
        if "index out of bounds" in out:
            debug_op(self.name, "wallust panic (ok)", ctx)
            return True
        if "No such file or directory" in out:
            return False
        debug_op(self.name, f"failed: {out[:200]}", ctx)
        return False
