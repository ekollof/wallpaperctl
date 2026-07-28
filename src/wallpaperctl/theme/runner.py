"""Execute theme operations in order."""

from __future__ import annotations

import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout

from wallpaperctl.context import WallpaperContext
from wallpaperctl.theme.cinnamon_theme import CinnamonThemeOp
from wallpaperctl.theme.cosmic import CosmicThemeOp
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
    CosmicThemeOp(),  # needs wallust colors; COSMIC v2 hex accent files
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


def _timeout_for(op_name: str, ctx: WallpaperContext) -> float:
    if op_name == "wallust":
        return float(ctx.ops.wallust_timeout)
    if op_name == "openrgb":
        return float(ctx.ops.openrgb_timeout)
    return float(ctx.ops.operation_timeout)


def _run_op_once(op, ctx: WallpaperContext, timeout: float) -> bool:
    """Run op.run(ctx) with a wall-clock timeout. Returns False on timeout/error."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(op.run, ctx)
        try:
            return bool(fut.result(timeout=timeout))
        except FuturesTimeout:
            log.warning(
                "Theme op %s timed out after %ss",
                op.name,
                timeout,
            )
            return False


def run_theme_ops(ctx: WallpaperContext) -> tuple[int, int]:
    """Returns (failed, total_enabled)."""
    if not ctx.ops.operations_enabled:
        log.debug("Theme operations disabled globally")
        return 0, 0

    failed = 0
    total = 0
    max_retries = max(1, int(ctx.ops.max_retries))
    retry_delay = float(ctx.ops.retry_delay)

    for op in THEME_OPS:
        if not op.enabled(ctx):
            log.debug("Skipping theme op %s (disabled/N/A)", op.name)
            continue
        total += 1
        timeout = _timeout_for(op.name, ctx)
        log.debug(
            "Executing theme operation: %s (timeout=%ss, max_attempts=%s)",
            op.name,
            timeout,
            max_retries,
        )
        ok = False
        for attempt in range(1, max_retries + 1):
            try:
                ok = _run_op_once(op, ctx, timeout)
            except Exception as e:
                log.warning("Theme op %s raised: %s", op.name, e)
                ok = False
            if ok:
                break
            if attempt < max_retries:
                log.debug(
                    "Theme op %s failed attempt %s/%s; retrying in %ss",
                    op.name,
                    attempt,
                    max_retries,
                    retry_delay,
                )
                time.sleep(retry_delay)

        if ok:
            log.debug("Theme op %s ok", op.name)
        else:
            print(f"Warning: Theme operation {op.name} failed", file=sys.stderr)
            failed += 1
            if not ctx.ops.continue_on_error:
                break
    time.sleep(1)
    return failed, total
