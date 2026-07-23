"""Core apply pipeline: set wallpaper file, run setters + theme ops."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from wallpaperctl.config import OpsConfig
from wallpaperctl.context import WallpaperContext
from wallpaperctl.detect.desktop import detect_desktop
from wallpaperctl.notify import safe_notify
from wallpaperctl.set.runner import run_wallpaper_setters
from wallpaperctl.theme.runner import run_theme_ops
from wallpaperctl.util import home

log = logging.getLogger("wallpaperctl")


def save_current_wallpaper(path: Path, ops: OpsConfig) -> None:
    target = ops.path("current_wallpaper_file")
    try:
        target.write_text(str(path.resolve()) + "\n", encoding="utf-8")
    except OSError as e:
        raise SystemExit(f"Error: Failed to write to {target}: {e}") from e


def load_current_wallpaper(ops: OpsConfig) -> Path:
    target = ops.path("current_wallpaper_file")
    if not target.is_file():
        raise SystemExit(f"Error: No previous wallpaper file found at {target}")
    text = target.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        raise SystemExit(f"Error: Empty wallpaper file at {target}")
    return Path(text)


def apply_wallpaper(
    path: Path,
    ops: OpsConfig,
    *,
    photographer_name: str = "",
    photographer_username: str = "",
    provider_name: str = "",
    debug: bool = False,
) -> None:
    path = path.expanduser()
    if not path.is_file():
        raise SystemExit(f"Error: File '{path}' not found!")

    de = detect_desktop()
    ops.apply_env_overrides(
        is_plasma=de.plasma,
        is_hyprland=de.hyprland,
        is_xfce=de.xfce,
        is_cinnamon=de.cinnamon,
    )

    ctx = WallpaperContext(
        path=path.resolve(),
        de=de,
        ops=ops,
        photographer_name=photographer_name,
        photographer_username=photographer_username,
        provider_name=provider_name,
        debug=debug,
    )

    log.debug("Applying wallpaper %s on DE %s", ctx.path, de.name)

    set_ok, set_total = run_wallpaper_setters(ctx)
    theme_failed, theme_total = run_theme_ops(ctx)

    set_failed = set_total - set_ok
    total_failed = set_failed + theme_failed
    total_ops = set_total + theme_total

    if total_failed == 0:
        log.debug("All %s operations completed successfully", total_ops)
    else:
        msg = f"Warning: {total_failed} of {total_ops} operations failed"
        print(msg, file=sys.stderr)
        safe_notify("Wallpaper Script", msg)

    name = path.name
    if "_credited" in name:
        safe_notify("Wallpaper Script", f"Wallpaper set with credits: {name}")
    else:
        safe_notify("Wallpaper Script", f"Wallpaper set: {name}")
