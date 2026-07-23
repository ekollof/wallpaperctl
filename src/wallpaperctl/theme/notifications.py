"""Reload dunst/mako/waybar notification styling."""

from __future__ import annotations

import time

from wallpaperctl.context import WallpaperContext

from wallpaperctl.theme.base import debug_op
from wallpaperctl.util import have, home, pgrep_exact, run


class NotificationsOp:
    name = "notifications"

    def enabled(self, ctx: WallpaperContext) -> bool:
        if not ctx.ops.enable_notifications:
            return False
        if ctx.de.plasma or ctx.de.xfce:
            return False
        if ctx.de.awesome:
            return False
        return True

    def run(self, ctx: WallpaperContext) -> bool:
        if ctx.de.hyprland:
            if have("mako") or have("makoctl"):
                return self._reload_mako(ctx)
            debug_op(self.name, "mako not found", ctx)
            return True
        if have("dunst"):
            return self._reload_dunst(ctx)
        debug_op(self.name, "dunst not found", ctx)
        return True

    def _reload_dunst(self, ctx: WallpaperContext) -> bool:
        if have("dunst_xrdb"):
            run(["dunst_xrdb"], timeout=15)
        if have("dunstctl"):
            r = run(["dunstctl", "reload"], timeout=10)
            if r.returncode == 0:
                return True
        run(["pkill", "dunst"], timeout=5)
        time.sleep(0.5)
        run(["dunst"], timeout=5, capture=True)
        # start detached
        import subprocess

        subprocess.Popen(
            ["dunst"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True

    def _reload_mako(self, ctx: WallpaperContext) -> bool:
        if have("makoctl"):
            r = run(["makoctl", "reload"], timeout=10)
            if r.returncode != 0:
                run(["pkill", "mako"], timeout=5)
                time.sleep(0.5)
                import subprocess

                subprocess.Popen(
                    ["mako"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
        else:
            run(["pkill", "mako"], timeout=5)
            time.sleep(0.5)
            import subprocess

            subprocess.Popen(
                ["mako"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

        if pgrep_exact("waybar"):
            style = home() / ".config" / "waybar" / "style.css"
            conf = home() / ".config" / "waybar" / "config"
            uses_wal = False
            for f in (style, conf):
                if f.is_file():
                    text = f.read_text(encoding="utf-8", errors="replace")
                    if any(k in text for k in ("pywal", "wal", "@import", "colors")):
                        uses_wal = True
                        break
            if uses_wal and have("waybar"):
                debug_op(self.name, "restarting waybar", ctx)
                run(["pkill", "waybar"], timeout=5)
                time.sleep(0.5)
                import subprocess

                subprocess.Popen(
                    ["waybar"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
        return True
