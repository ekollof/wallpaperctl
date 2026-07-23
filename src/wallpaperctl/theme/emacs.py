"""Emacs ewal theme reload via emacs-daemon helper."""

from __future__ import annotations

from wallpaperctl.context import WallpaperContext
from wallpaperctl.theme.base import debug_op
from wallpaperctl.util import have, run


class EmacsOp:
    name = "emacs"

    def enabled(self, ctx: WallpaperContext) -> bool:
        return ctx.ops.enable_emacs

    def run(self, ctx: WallpaperContext) -> bool:
        if not have("emacs-daemon"):
            debug_op(self.name, "emacs-daemon not found", ctx)
            return True
        check = run(["emacs-daemon", "--check"], timeout=10)
        if check.returncode != 0:
            debug_op(self.name, "emacs server not running", ctx)
            return True
        theme = ctx.ops.emacs_theme
        expr = f"(progn (ewal-load-colors) (load-theme '{theme} t))"
        r = run(["emacs-daemon", "-e", expr], timeout=30)
        return r.returncode == 0
