"""Steam theme — disabled stub (same as shell 12-steam-theme)."""

from __future__ import annotations

from wallpaperctl.context import WallpaperContext


class SteamOp:
    name = "steam-theme"

    def enabled(self, ctx: WallpaperContext) -> bool:
        return ctx.ops.enable_steam_theme

    def run(self, ctx: WallpaperContext) -> bool:
        return True
