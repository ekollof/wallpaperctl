"""Execute theme operations in order."""

from __future__ import annotations

import logging
import sys
import time

from wallpaperctl.context import WallpaperContext
from wallpaperctl.theme.cinnamon_theme import CinnamonThemeOp
from wallpaperctl.theme.dynamic_icons import DynamicIconsOp
from wallpaperctl.theme.emacs import EmacsOp
from wallpaperctl.theme.gtk_theme import GtkThemeOp
from wallpaperctl.theme.homeassistant import HomeassistantOp
from wallpaperctl.theme.notifications import NotificationsOp
from wallpaperctl.theme.nwg_look import NwgLookOp
from wallpaperctl.theme.openrgb import OpenrgbOp
from wallpaperctl.theme.steam import SteamOp
from wallpaperctl.theme.wallust import WallustOp
from wallpaperctl.theme.window_manager import WindowManagerOp
from wallpaperctl.theme.xresources import XresourcesOp

log = logging.getLogger("wallpaperctl")

THEME_OPS = [
    WallustOp(),
    XresourcesOp(),
    NwgLookOp(),
    NotificationsOp(),
    OpenrgbOp(),
    EmacsOp(),
    WindowManagerOp(),
    GtkThemeOp(),
    CinnamonThemeOp(),
    DynamicIconsOp(),
    HomeassistantOp(),
    SteamOp(),
]


def list_ops() -> list[str]:
    return [op.name for op in THEME_OPS]


def run_theme_ops(ctx: WallpaperContext) -> tuple[int, int]:
    """Returns (failed, total_enabled)."""
    if not ctx.ops.operations_enabled:
        log.debug("Theme operations disabled globally")
        return 0, 0

    failed = 0
    total = 0
    for op in THEME_OPS:
        if not op.enabled(ctx):
            log.debug("Skipping theme op %s (disabled/N/A)", op.name)
            continue
        total += 1
        log.debug("Executing theme operation: %s", op.name)
        try:
            ok = op.run(ctx)
        except Exception as e:
            log.warning("Theme op %s raised: %s", op.name, e)
            ok = False
        if ok:
            log.debug("Theme op %s ok", op.name)
        else:
            print(f"Warning: Theme operation {op.name} failed", file=sys.stderr)
            failed += 1
            if not ctx.ops.continue_on_error:
                break
    time.sleep(1)
    return failed, total
