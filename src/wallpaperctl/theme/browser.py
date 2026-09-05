"""Chromium-family browser tinting via managed policies (Omarchy-style).

Writes ``color.json`` into each existing managed-policy directory:

    {"BrowserThemeColor": "#rrggbb", "BrowserColorScheme": "dark"}

``BrowserThemeColor`` tints the browser UI (frame, toolbar, titlebar) from
the wallpaper palette — no GTK theme or env vars involved.
``BrowserColorScheme`` pins the scheme ("dark" | "light" | "device"),
bypassing the GTK/portal detection Chromium normally uses, which covers
web-content ``prefers-color-scheme`` reliably.

Running browsers pick changes up live via ``--refresh-platform-policy``.
The policy directories live under /etc and are created once by
``wallpaperctl setup browser-policies`` (sudo/doas/pkexec). On Omarchy this
op stays out of the way: omarchy-theme-set-browser owns the same policies,
and the Omarchy theme op (theme/omarchy.py) re-runs it after each palette
retint so wallpaper changes re-tint browser chrome too.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from wallpaperctl.context import WallpaperContext
from wallpaperctl.theme.adwaita import ensure_hash, hex_palette
from wallpaperctl.theme.base import debug_op
from wallpaperctl.theme.cosmic import pick_accent
from wallpaperctl.theme.pywalfox import load_colors_json
from wallpaperctl.util import have, pgrep_exact, run

log = logging.getLogger("wallpaperctl")

BROWSER_POLICY_DIRS = [
    "/etc/brave/policies/managed",
    "/etc/chromium/policies/managed",
    "/etc/opt/chrome/policies/managed",
    "/etc/opt/edge/policies/managed",
]
# (pgrep process name, launch command) for live policy refresh.
BROWSERS = [
    ("brave", "brave"),
    ("chromium", "chromium"),
    ("chrome", "google-chrome-stable"),
    ("msedge", "microsoft-edge-stable"),
]
REFRESH_ARGS = ["--refresh-platform-policy", "--no-startup-window"]


def build_color_policy(theme_color: str, color_scheme: str) -> str:
    return json.dumps(
        {"BrowserThemeColor": theme_color, "BrowserColorScheme": color_scheme}
    )


class BrowserPolicyOp:
    name = "browser-policy"

    def enabled(self, ctx: WallpaperContext) -> bool:
        if not ctx.ops.enable_browser_policy:
            return False
        # omarchy-theme-set-browser owns the same policies there; the omarchy
        # theme op re-runs it after each palette retint (theme/omarchy.py).
        if ctx.de.omarchy:
            return False
        return True

    def run(self, ctx: WallpaperContext) -> bool:
        colors = load_colors_json()
        if not colors:
            debug_op(self.name, "no wal colors.json; skipping browser policy", ctx)
            return True
        palette = hex_palette(colors)
        accent, accent_soft = pick_accent(
            palette, strategy=ctx.ops.rgb_color_strategy
        )
        # Soft accent (mixed toward bg) matches the Adwaita tint headerbar.
        theme_color = ensure_hash(accent_soft) or ensure_hash(accent)
        payload = build_color_policy(theme_color, ctx.ops.browser_color_scheme)
        written = self._write_policies(payload, ctx)
        self._refresh_running(ctx)
        debug_op(
            self.name,
            f"BrowserThemeColor {theme_color} written to {written} policy dir(s)",
            ctx,
        )
        return True

    def _write_policies(self, payload: str, ctx: WallpaperContext) -> int:
        written = 0
        for directory in BROWSER_POLICY_DIRS:
            path = Path(directory)
            if not path.is_dir():
                continue
            try:
                (path / "color.json").write_text(payload, encoding="utf-8")
            except OSError as e:
                debug_op(
                    self.name,
                    f"could not write {directory}/color.json: {e} — "
                    f"run: wallpaperctl setup browser-policies",
                    ctx,
                )
                continue
            written += 1
        return written

    def _refresh_running(self, ctx: WallpaperContext) -> None:
        for process, command in BROWSERS:
            if not pgrep_exact(process) or not have(command):
                continue
            debug_op(self.name, f"refreshing policies for {command}", ctx)
            run([command, *REFRESH_ARGS], timeout=15)
