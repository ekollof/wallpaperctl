"""Run applicable wallpaper setters."""

from __future__ import annotations

import logging
import sys

from wallpaperctl.context import WallpaperContext
from wallpaperctl.set.cinnamon import CinnamonSetter
from wallpaperctl.set.fallback import FallbackSetter
from wallpaperctl.set.hyprland import HyprlandSetter
from wallpaperctl.set.noctalia import NoctaliaSetter
from wallpaperctl.set.plasma import PlasmaSetter
from wallpaperctl.set.xfce import XfceSetter

log = logging.getLogger("wallpaperctl")

SETTERS = [
    PlasmaSetter(),
    NoctaliaSetter(),  # before hyprland so noctalia wins when both apply
    HyprlandSetter(),
    XfceSetter(),
    CinnamonSetter(),
    FallbackSetter(),
]


def run_wallpaper_setters(ctx: WallpaperContext) -> tuple[int, int]:
    """Returns (succeeded, attempted)."""
    succeeded = 0
    attempted = 0
    for setter in SETTERS:
        if not setter.applies(ctx):
            continue
        attempted += 1
        log.debug("Running wallpaper setter: %s", setter.name)
        try:
            ok = setter.set_wallpaper(ctx)
        except Exception as e:
            log.warning("Wallpaper setter %s raised: %s", setter.name, e)
            ok = False
        if ok:
            succeeded += 1
            log.debug("Setter %s ok", setter.name)
        else:
            print(f"Warning: Wallpaper operation {setter.name} failed", file=sys.stderr)
    return succeeded, attempted
