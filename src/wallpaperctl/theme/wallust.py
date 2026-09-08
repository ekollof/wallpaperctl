"""wallust color scheme generation."""

from __future__ import annotations

from wallpaperctl.context import WallpaperContext
from wallpaperctl.theme.base import debug_op
from wallpaperctl.theme.palette_contrast import fix_installed_palette
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
                str(ctx.image_path),
            ],
            timeout=ctx.ops.wallust_timeout,
        )
        ok = r.returncode == 0
        if not ok:
            out = (r.stdout or "") + (r.stderr or "")
            if "couldn't generate a suitable palette" in out:
                debug_op(self.name, "palette generation issue (ok)", ctx)
                ok = True
            elif "index out of bounds" in out:
                debug_op(self.name, "wallust panic (ok)", ctx)
                ok = True
            elif "No such file or directory" in out:
                return False
            else:
                debug_op(self.name, f"failed: {out[:200]}", ctx)
                return False
        if ok and ctx.ops.wallust_fix_contrast:
            # wallust's check_contrast only does a mild bg-relative check;
            # enforce WCAG ratios on the canonical palette and patch the
            # generated files (shell, kitty, starship, opencode, ...).
            fixed = fix_installed_palette(
                text_min=ctx.ops.wallust_text_contrast,
                accent_min=ctx.ops.wallust_accent_contrast,
            )
            debug_op(self.name, "palette contrast fix ok" if fixed else
                     "palette contrast fix skipped (no colors.json)", ctx)
        from wallpaperctl.theme.terminal_opacity import (
            apply_terminal_background_opacity,
            reload_terminals_for_opacity,
        )

        patched = apply_terminal_background_opacity(
            getattr(ctx.ops, "terminal_background_opacity", 0.85)
        )
        if patched:
            reload_terminals_for_opacity()
        if patched:
            debug_op(
                self.name,
                "terminal background opacity "
                f"{getattr(ctx.ops, 'terminal_background_opacity', 0.85)} "
                f"on {', '.join(p.name for p in patched)}",
                ctx,
            )
        debug_op(self.name, "ok", ctx)
        return True
