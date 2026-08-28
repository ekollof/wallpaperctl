"""Reload dunst/mako/waybar notification styling."""

from __future__ import annotations

import time

from wallpaperctl.context import WallpaperContext
from wallpaperctl.dbus_session import name_has_owner
from wallpaperctl.theme.base import debug_op
from wallpaperctl.util import have, home, pgrep_exact, run, spawn_detached

NOTIFICATIONS_BUS = "org.freedesktop.Notifications"


def _foreign_daemon_active() -> bool:
    """True if a non-dunst/mako daemon owns the notification bus name.

    Covers WMs/desktops with a built-in notification daemon (qtile, GNOME,
    xfce4-notifyd, ...). Restarting dunst in that case would hijack the bus
    name away from the WM's own notifier.
    """
    if not name_has_owner(NOTIFICATIONS_BUS):
        return False
    return not (pgrep_exact("dunst") or pgrep_exact("mako"))


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
        if _foreign_daemon_active():
            debug_op(
                self.name,
                "notification daemon already active; not starting dunst/mako",
                ctx,
            )
            return True
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
        # Start detached only (do not also run dunst in the foreground)
        spawn_detached(["dunst"])
        return True

    def _reload_mako(self, ctx: WallpaperContext) -> bool:
        if have("makoctl"):
            r = run(["makoctl", "reload"], timeout=10)
            if r.returncode != 0:
                run(["pkill", "mako"], timeout=5)
                time.sleep(0.5)
                spawn_detached(["mako"])
        else:
            run(["pkill", "mako"], timeout=5)
            time.sleep(0.5)
            spawn_detached(["mako"])

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
                spawn_detached(["waybar"])
        return True
