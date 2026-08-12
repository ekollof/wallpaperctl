"""OpenLinkHub RGB from wallust palette (same color strategy as OpenRGB).

Talks to a local OpenLinkHub daemon (default http://127.0.0.1:27003) via REST.
Uses POST /api/color/all — the WebUI "apply color to all devices" path — so Corsair
devices managed by OpenLinkHub (iCUE LINK, Commander Pro, …) match OpenRGB lighting.
"""

from __future__ import annotations

import logging

import httpx

from wallpaperctl.context import WallpaperContext
from wallpaperctl.theme.base import debug_op
from wallpaperctl.theme.palette import pick_theme_color
from wallpaperctl.util import hex_to_rgb

log = logging.getLogger("wallpaperctl")

DEFAULT_URL = "http://127.0.0.1:27003"


class OpenlinkhubOp:
    name = "openlinkhub"

    def enabled(self, ctx: WallpaperContext) -> bool:
        return ctx.ops.enable_openlinkhub

    def run(self, ctx: WallpaperContext) -> bool:
        base = (ctx.ops.openlinkhub_url or DEFAULT_URL).rstrip("/")
        timeout = float(ctx.ops.openlinkhub_timeout)

        if not self._is_running(base, timeout, ctx):
            debug_op(self.name, f"not reachable at {base}, skip", ctx)
            return True

        strategy = ctx.ops.rgb_color_strategy
        fixed = (
            ctx.ops.openrgb_color_line_plasma
            if ctx.de.plasma
            else ctx.ops.openrgb_color_line_standalone
        )
        color, line = pick_theme_color(strategy, fixed_line=fixed)
        if not color:
            debug_op(self.name, f"no color at line {line}", ctx)
            return False

        try:
            r, g, b = hex_to_rgb(color)
        except ValueError:
            debug_op(self.name, f"bad color {color}", ctx)
            return False

        brightness = float(ctx.ops.openlinkhub_brightness)
        payload = {
            "color": {
                "red": r,
                "green": g,
                "blue": b,
                "brightness": brightness,
            }
        }
        debug_op(
            self.name,
            f"setting RGB {color} (line {line}) via {base}/api/color/all",
            ctx,
        )
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(f"{base}/api/color/all", json=payload)
            if resp.status_code != 200:
                debug_op(
                    self.name,
                    f"HTTP {resp.status_code}: {resp.text[:200]}",
                    ctx,
                )
                return False
            try:
                body = resp.json()
            except Exception:
                body = {}
            # OpenLinkHub uses status==1 for success on most write endpoints
            status = body.get("status")
            if status is not None and status != 1 and body.get("code") != 200:
                debug_op(self.name, f"API status={status}: {body.get('message')}", ctx)
                return False
            debug_op(self.name, f"ok: {body.get('message', 'applied')}", ctx)
            return True
        except httpx.HTTPError as e:
            debug_op(self.name, f"request failed: {e}", ctx)
            return False

    @staticmethod
    def _is_running(base: str, timeout: float, ctx: WallpaperContext) -> bool:
        try:
            with httpx.Client(timeout=min(timeout, 2.0)) as client:
                resp = client.get(f"{base}/api/")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False
