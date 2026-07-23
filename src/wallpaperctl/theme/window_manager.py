"""Standalone WM signals: xsetroot, xsettingsd, awesome."""

from __future__ import annotations

import subprocess
import time

from wallpaperctl.context import WallpaperContext
from wallpaperctl.theme.base import debug_op
from wallpaperctl.util import have, pgrep_exact, run



class WindowManagerOp:
    name = "window-manager"

    def enabled(self, ctx: WallpaperContext) -> bool:
        if not ctx.ops.enable_window_manager:
            return False
        de = ctx.de
        return not (de.plasma or de.hyprland or de.xfce or de.cinnamon)

    def run(self, ctx: WallpaperContext) -> bool:
        if have("xsetroot"):
            run(["xsetroot", "-name", "fsignal:2"], timeout=5)

        if have("xsettingsd"):
            run(["pkill", "-f", "xsettingsd"], timeout=5)
            time.sleep(0.2)
            subprocess.Popen(
                ["xsettingsd"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            debug_op(self.name, "xsettingsd restarted", ctx)

        if pgrep_exact("awesome") and have("awesome-client"):
            run(
                ["awesome-client"],
                input_text="awesome.restart()",
                timeout=10,
            )
            debug_op(self.name, "awesome reload", ctx)

        return True
