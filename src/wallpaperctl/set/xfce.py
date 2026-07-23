"""XFCE wallpaper via xfconf-query."""

from __future__ import annotations

import logging
import re

from wallpaperctl.context import WallpaperContext
from wallpaperctl.set.base import debug_set
from wallpaperctl.util import have, run

log = logging.getLogger("wallpaperctl")


class XfceSetter:
    name = "xfce"

    def applies(self, ctx: WallpaperContext) -> bool:
        return ctx.de.xfce

    def set_wallpaper(self, ctx: WallpaperContext) -> bool:
        path = str(ctx.path.resolve())
        if not have("xfconf-query"):
            debug_set(self.name, "xfconf-query not found", ctx)
            return False

        r = run(["xfconf-query", "-c", "xfce4-desktop", "-l"], timeout=10)
        lines = r.stdout.splitlines() if r.returncode == 0 else []
        monitors = sorted(
            {
                m.group(0)
                for line in lines
                for m in [re.search(r"monitor[^/]*", line)]
                if m and "/backdrop/screen0/monitor" in line
            }
        )

        if not monitors:
            debug_set(self.name, "no monitors, trying default", ctx)
            ok = self._set_props("monitor0", "0", path)
            return ok

        success = 0
        total = 0
        for mon in monitors:
            workspaces = sorted(
                {
                    m.group(1)
                    for line in lines
                    if f"/backdrop/screen0/{mon}/workspace" in line
                    for m in [re.search(r"workspace(\d+)", line)]
                    if m
                }
            ) or ["0"]
            for ws in workspaces:
                total += 1
                if self._set_props(mon, ws, path):
                    success += 1
                    debug_set(self.name, f"set {mon} workspace{ws}", ctx)
        debug_set(self.name, f"updated {success}/{total}", ctx)
        return success > 0

    def _set_props(self, monitor: str, workspace: str, path: str) -> bool:
        base = f"/backdrop/screen0/{monitor}/workspace{workspace}"
        r1 = run(
            [
                "xfconf-query",
                "-c",
                "xfce4-desktop",
                "-p",
                f"{base}/image-path",
                "-s",
                path,
                "--create",
                "-t",
                "string",
            ],
            timeout=10,
        )
        run(
            [
                "xfconf-query",
                "-c",
                "xfce4-desktop",
                "-p",
                f"{base}/last-image",
                "-s",
                path,
                "--create",
                "-t",
                "string",
            ],
            timeout=10,
        )
        return r1.returncode == 0
