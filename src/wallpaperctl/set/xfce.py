"""XFCE wallpaper via xfconf-query.

Handles docking laptops where connector names change (eDP-1, DP-8, …) and
xfconf still only has *old* monitor keys from previous docks. We:

  1. Discover **currently connected** outputs (xrandr)
  2. Merge with any keys already under xfce4-desktop backdrop
  3. Ensure full property trees exist (--create) before setting paths
  4. Cover all workspaces (xfwm4 count or discovered)
  5. Best-effort xfdesktop reload
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from wallpaperctl.context import WallpaperContext
from wallpaperctl.set.base import debug_set
from wallpaperctl.util import have, run

log = logging.getLogger("wallpaperctl")

# XFCE image-style: 0=Auto, 1=Centered, 2=Tiled, 3=Stretched, 4=Scaled, 5=Zoom
DEFAULT_IMAGE_STYLE = 5


class XfceSetter:
    name = "xfce"

    def applies(self, ctx: WallpaperContext) -> bool:
        return ctx.de.xfce

    def set_wallpaper(self, ctx: WallpaperContext) -> bool:
        path = str(ctx.path.resolve())
        if not have("xfconf-query"):
            debug_set(self.name, "xfconf-query not found", ctx)
            return False
        if not Path(path).is_file():
            debug_set(self.name, f"file not found: {path}", ctx)
            return False

        prop_lines = self._list_backdrop_props()
        connected = self._connected_outputs()
        monitors = self._monitor_keys(connected, prop_lines)
        workspaces = self._workspace_ids(prop_lines)

        debug_set(
            self.name,
            f"outputs={connected or ['?']} monitors={monitors} workspaces={workspaces}",
            ctx,
        )

        if not monitors:
            # Last resort single-head defaults
            monitors = ["monitor0", "monitoreDP-1", "monitorLVDS-1"]
            debug_set(self.name, f"no monitors discovered; trying defaults {monitors}", ctx)

        success = 0
        total = 0
        for mon in monitors:
            for ws in workspaces:
                total += 1
                if self._ensure_and_set(mon, ws, path, ctx):
                    success += 1

        # Also stamp every *existing* image-path/last-image node (covers odd trees)
        success += self._set_all_existing_image_props(prop_lines, path, ctx)

        self._reload_xfdesktop(ctx)
        debug_set(self.name, f"updated {success} property path(s) (targets={total})", ctx)
        return success > 0

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def _list_backdrop_props(self) -> list[str]:
        r = run(["xfconf-query", "-c", "xfce4-desktop", "-l"], timeout=10)
        if r.returncode != 0:
            return []
        return [ln.strip() for ln in r.stdout.splitlines() if "/backdrop/" in ln]

    def _connected_outputs(self) -> list[str]:
        """Return X11 connector names that are currently connected (xrandr)."""
        outputs: list[str] = []
        if have("xrandr"):
            r = run(["xrandr", "--query"], timeout=10)
            if r.returncode == 0:
                for line in r.stdout.splitlines():
                    # "eDP-1 connected primary 1920x1200+0+0 ..."
                    m = re.match(r"^(\S+)\s+connected\b", line)
                    if m:
                        outputs.append(m.group(1))
        if outputs:
            return outputs

        # Fallback: parse unique monitor* keys already in xfconf
        return []

    def _monitor_keys(
        self, connected: list[str], prop_lines: list[str]
    ) -> list[str]:
        """
        XFCE stores connectors as /backdrop/screen0/monitor<NAME>/...
        e.g. eDP-1 → monitoreDP-1, DP-8 → monitorDP-8.
        """
        keys: set[str] = set()

        for out in connected:
            keys.add(f"monitor{out}")

        # Existing keys (including stale docks — still update so re-plug works
        # if the same name returns; cheap and harmless)
        for line in prop_lines:
            m = re.search(r"/backdrop/screen\d+/(monitor[^/]+)/", line)
            if m:
                keys.add(m.group(1))

        # Prefer currently connected first for logging/ordering
        ordered: list[str] = []
        for out in connected:
            k = f"monitor{out}"
            if k in keys and k not in ordered:
                ordered.append(k)
        for k in sorted(keys):
            if k not in ordered:
                ordered.append(k)
        return ordered

    def _workspace_ids(self, prop_lines: list[str]) -> list[str]:
        ids: set[int] = set()
        for line in prop_lines:
            m = re.search(r"/workspace(\d+)/", line)
            if m:
                ids.add(int(m.group(1)))

        # xfwm4 workspace count
        if have("xfconf-query"):
            r = run(
                ["xfconf-query", "-c", "xfwm4", "-p", "/general/workspace_count"],
                timeout=5,
            )
            if r.returncode == 0:
                try:
                    count = int(r.stdout.strip())
                    for i in range(max(count, 1)):
                        ids.add(i)
                except ValueError:
                    pass

        if not ids:
            ids = {0}
        return [str(i) for i in sorted(ids)]

    # ------------------------------------------------------------------
    # Property create / set
    # ------------------------------------------------------------------

    def _ensure_and_set(
        self, monitor: str, workspace: str, path: str, ctx: WallpaperContext
    ) -> bool:
        """Create backdrop props if missing (first-time / new dock output), then set."""
        base = f"/backdrop/screen0/{monitor}/workspace{workspace}"
        ok_any = False

        # Strings first — these are what xfdesktop actually reads
        for leaf in ("last-image", "image-path"):
            if self._set_string(f"{base}/{leaf}", path):
                ok_any = True

        # image-style (int): only create if absent; don't fight user prefs if set
        style_prop = f"{base}/image-style"
        if not self._prop_exists(style_prop):
            if self._create_int(style_prop, DEFAULT_IMAGE_STYLE):
                debug_set(self.name, f"created {style_prop}={DEFAULT_IMAGE_STYLE}", ctx)

        # image-show (bool) — some builds need this true for backdrop to paint
        show_prop = f"{base}/image-show"
        if not self._prop_exists(show_prop):
            self._create_bool(show_prop, True)

        if ok_any:
            debug_set(self.name, f"set {monitor} workspace{workspace}", ctx)
        else:
            debug_set(self.name, f"failed {monitor} workspace{workspace}", ctx)
        return ok_any

    def _set_all_existing_image_props(
        self, prop_lines: list[str], path: str, ctx: WallpaperContext
    ) -> int:
        """Update every last-image / image-path node already in the channel."""
        n = 0
        for line in prop_lines:
            if line.endswith("/last-image") or line.endswith("/image-path"):
                if self._set_string(line, path, create=False):
                    n += 1
        if n:
            debug_set(self.name, f"patched {n} existing image properties", ctx)
        return n

    def _prop_exists(self, prop: str) -> bool:
        r = run(
            ["xfconf-query", "-c", "xfce4-desktop", "-p", prop],
            timeout=5,
        )
        return r.returncode == 0

    def _set_string(self, prop: str, value: str, *, create: bool = True) -> bool:
        # Prefer plain set when property exists (avoids type-mismatch on --create)
        if self._prop_exists(prop):
            r = run(
                ["xfconf-query", "-c", "xfce4-desktop", "-p", prop, "-s", value],
                timeout=10,
            )
            return r.returncode == 0
        if not create:
            return False
        # First-time property for this monitor/workspace (common after docking)
        r = run(
            [
                "xfconf-query",
                "-c",
                "xfce4-desktop",
                "-p",
                prop,
                "-n",
                "-t",
                "string",
                "-s",
                value,
            ],
            timeout=10,
        )
        if r.returncode == 0:
            return True
        # Older xfconf-query: --create instead of -n
        r2 = run(
            [
                "xfconf-query",
                "-c",
                "xfce4-desktop",
                "-p",
                prop,
                "--create",
                "-t",
                "string",
                "-s",
                value,
            ],
            timeout=10,
        )
        return r2.returncode == 0

    def _create_int(self, prop: str, value: int) -> bool:
        r = run(
            [
                "xfconf-query",
                "-c",
                "xfce4-desktop",
                "-p",
                prop,
                "-n",
                "-t",
                "int",
                "-s",
                str(value),
            ],
            timeout=10,
        )
        if r.returncode == 0:
            return True
        r2 = run(
            [
                "xfconf-query",
                "-c",
                "xfce4-desktop",
                "-p",
                prop,
                "--create",
                "-t",
                "int",
                "-s",
                str(value),
            ],
            timeout=10,
        )
        return r2.returncode == 0

    def _create_bool(self, prop: str, value: bool) -> bool:
        r = run(
            [
                "xfconf-query",
                "-c",
                "xfce4-desktop",
                "-p",
                prop,
                "-n",
                "-t",
                "bool",
                "-s",
                "true" if value else "false",
            ],
            timeout=10,
        )
        return r.returncode == 0

    def _reload_xfdesktop(self, ctx: WallpaperContext) -> None:
        if have("xfdesktop"):
            # Soft reload if supported
            r = run(["xfdesktop", "--reload"], timeout=10)
            if r.returncode == 0:
                debug_set(self.name, "xfdesktop --reload", ctx)
                return
        # HUP xfdesktop as fallback
        run(["pkill", "-HUP", "xfdesktop"], timeout=5)
