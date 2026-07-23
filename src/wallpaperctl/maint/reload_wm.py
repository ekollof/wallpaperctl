"""Force Cinnamon/Muffin window-manager theme reload (wallpaper-reload-wm)."""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

from wallpaperctl.util import have, hex_to_rgb, home, read_wal_colors, run


def run_reload_wm(*, restart: bool = False) -> int:
    if restart:
        return _restart_cinnamon()
    return _try_hotreload()


def _restart_cinnamon() -> int:
    print("Restarting Cinnamon for immediate window decoration updates...")
    if have("cinnamon-dbus-command"):
        r = run(["cinnamon-dbus-command", "RestartCinnamon", "true"], timeout=30)
        if r.returncode == 0:
            print("Cinnamon restart initiated")
            return 0
        print(r.stderr or "cinnamon-dbus-command failed", file=sys.stderr)
        return 1
    print("cinnamon-dbus-command not found", file=sys.stderr)
    print("Please manually restart Cinnamon: Alt+F2 → r → Enter", file=sys.stderr)
    return 1


def _gsettings_get(schema: str, key: str) -> str:
    r = run(["gsettings", "get", schema, key], timeout=5)
    if r.returncode != 0:
        return ""
    return r.stdout.strip().strip("'")


def _gsettings_set(schema: str, key: str, value: str) -> bool:
    r = run(["gsettings", "set", schema, key, value], timeout=5)
    return r.returncode == 0


def _intermediate_theme() -> str:
    """Pick Mint-Y vs Mint-Y-Dark from wallust background brightness."""
    colors = read_wal_colors()
    if not colors:
        return "Mint-Y-Dark"
    try:
        r, g, b = hex_to_rgb(colors[0])
        brightness = r + g + b
    except ValueError:
        return "Mint-Y-Dark"
    if brightness < 384:
        return "Mint-Y-Dark"
    return "Mint-Y"


def _try_hotreload() -> int:
    print("Attempting hot-reload of window manager theme...")

    if not have("gsettings"):
        print("gsettings not found", file=sys.stderr)
        return 1

    current = _gsettings_get("org.cinnamon.desktop.wm.preferences", "theme")
    if current != "cinnamon-dynamic":
        print(f"Current WM theme is not cinnamon-dynamic: {current or '(unset)'}")
        print("Run wallpaperctl first to generate the dynamic theme")
        return 1

    print("Forcing theme reload sequence with minimal visual disruption...")

    # Clear theme caches
    for cache in (home() / ".cache" / "gtk-3.0", home() / ".cache" / "cinnamon"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)

    intermediate = _intermediate_theme()
    if intermediate.endswith("Dark"):
        print("Using dark intermediate theme to minimize flashing")
    else:
        print("Using light intermediate theme to minimize flashing")

    _gsettings_set("org.cinnamon.desktop.wm.preferences", "theme", intermediate)
    time.sleep(0.3)
    _gsettings_set("org.cinnamon.desktop.wm.preferences", "theme", "cinnamon-dynamic")

    if have("cinnamon-dbus-command"):
        run(["cinnamon-dbus-command", "ReloadTheme"], timeout=15)

    print("Hot-reload attempted. If decorations haven't changed, try:")
    print("  wallpaperctl reload-wm --restart")
    print("  or manually: Alt+F2 → r → Enter")
    return 0
