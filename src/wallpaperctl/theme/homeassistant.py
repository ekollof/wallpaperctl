"""Home Assistant light color sync from wallust palette."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import httpx

from wallpaperctl.context import WallpaperContext
from wallpaperctl.theme.base import debug_op
from wallpaperctl.theme.palette import color_at_line, select_palette_line
from wallpaperctl.util import hex_to_rgb, home

log = logging.getLogger("wallpaperctl")


class HomeassistantOp:
    name = "homeassistant"

    def enabled(self, ctx: WallpaperContext) -> bool:
        return ctx.ops.enable_homeassistant

    def run(self, ctx: WallpaperContext) -> bool:
        cfg_path = home() / ".config" / "hass.cfg"
        if not cfg_path.is_file():
            debug_op(self.name, f"config not found: {cfg_path}", ctx)
            return True
        try:
            mode = cfg_path.stat().st_mode & 0o777
            if mode & 0o077:
                debug_op(self.name, f"config perms {oct(mode)}, should be 600", ctx)
        except OSError:
            pass

        auth = self._read_auth(cfg_path)
        if not auth:
            debug_op(self.name, "missing auth fields", ctx)
            return True
        server, token, lamps = auth

        strategy = ctx.ops.rgb_color_strategy
        fixed = (
            ctx.ops.openrgb_color_line_plasma
            if ctx.de.plasma
            else ctx.ops.openrgb_color_line_standalone
        )
        if strategy == "fixed":
            line = fixed
        else:
            line = select_palette_line(strategy)
        color = color_at_line(line)
        if not color:
            debug_op(self.name, "no wal color", ctx)
            return True

        debug_op(self.name, f"using color {color}", ctx)
        try:
            r, g, b = hex_to_rgb(color)
        except ValueError:
            return True

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=10.0) as client:
            for lamp in lamps:
                self._set_lamp(client, server, headers, lamp, r, g, b, ctx)
        return True

    def _set_lamp(
        self,
        client: httpx.Client,
        server: str,
        headers: dict,
        entity: str,
        r: int,
        g: int,
        b: int,
        ctx: WallpaperContext,
    ) -> None:
        try:
            st = client.get(f"{server}/api/states/{entity}", headers=headers)
            if st.status_code != 200:
                return
            if st.json().get("state") != "on":
                debug_op(self.name, f"{entity} not on, skip", ctx)
                return
            client.post(
                f"{server}/api/services/light/turn_on",
                headers=headers,
                json={"entity_id": entity, "rgb_color": [r, g, b]},
            )
            debug_op(self.name, f"set {entity}", ctx)
        except Exception as e:
            debug_op(self.name, f"failed {entity}: {e}", ctx)

    @staticmethod
    def _read_auth(path: Path) -> tuple[str, str, list[str]] | None:
        text = path.read_text(encoding="utf-8", errors="replace")
        # [auth] section
        m = re.search(r"\[auth\](.*?)(?:\n\[|\Z)", text, re.S | re.I)
        if not m:
            return None
        section = m.group(1)
        vals: dict[str, str] = {}
        for line in section.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip()
        server = vals.get("server", "")
        token = vals.get("token", "")
        lamps_raw = vals.get("lamp", "")
        if not server or not token or not lamps_raw:
            return None
        lamps = [x.strip() for x in lamps_raw.split(",") if x.strip()]
        return server.rstrip("/"), token, lamps
