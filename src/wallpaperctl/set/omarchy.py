"""Omarchy wallpaper setter (background via omarchy tooling).

Omarchy renders the desktop background itself through omarchy-shell; hyprpaper
does not run in an Omarchy session. Static images are applied with
`omarchy theme bg set` (symlink + live shell IPC). Animated wallpapers use
omarchy's own motion-wallpaper playback with the extracted still frame as the
underlay, so letterbox margins never show stale content.
"""

from __future__ import annotations

import logging

from wallpaperctl.context import WallpaperContext
from wallpaperctl.omarchy import motion_wallpaper_play, motion_wallpaper_stop, run_omarchy
from wallpaperctl.set.base import debug_set

log = logging.getLogger("wallpaperctl")


class OmarchySetter:
    name = "omarchy"

    def applies(self, ctx: WallpaperContext) -> bool:
        return ctx.de.omarchy

    def set_wallpaper(self, ctx: WallpaperContext) -> bool:
        if ctx.is_animated:
            return self._set_animated(ctx)
        return self._set_static(ctx)

    def _set_static(self, ctx: WallpaperContext) -> bool:
        path = ctx.image_path.resolve()
        if not path.is_file():
            debug_set(self.name, f"image missing: {path}", ctx)
            return False
        motion_wallpaper_stop()
        r = run_omarchy(["theme", "bg", "set", str(path)], timeout=15)
        if r.returncode != 0:
            debug_set(
                self.name,
                f"omarchy theme bg set failed: {(r.stderr or r.stdout or '')[:200]}",
                ctx,
            )
            return False
        debug_set(self.name, f"background set via omarchy: {path.name}", ctx)
        return True

    def _set_animated(self, ctx: WallpaperContext) -> bool:
        video = ctx.path.resolve()
        if not video.is_file():
            debug_set(self.name, f"video missing: {video}", ctx)
            return False
        underlay = ctx.image_path
        if underlay is not None and underlay.is_file():
            r = run_omarchy(
                ["theme", "bg", "set", str(underlay.resolve())], timeout=15
            )
            if r.returncode != 0:
                debug_set(self.name, "still underlay via omarchy failed", ctx)
        if not motion_wallpaper_play(video, timeout=10):
            debug_set(self.name, "motion-wallpaper play failed", ctx)
            return False
        debug_set(self.name, f"motion wallpaper playing: {video.name}", ctx)
        return True
