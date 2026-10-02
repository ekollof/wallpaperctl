"""Core apply pipeline: set wallpaper file, run setters + theme ops."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from wallpaperctl.config import OpsConfig
from wallpaperctl.context import WallpaperContext
from wallpaperctl.detect.desktop import detect_desktop
from wallpaperctl.media import extract_frame, is_animated
from wallpaperctl.notify import safe_notify
from wallpaperctl.set.runner import run_wallpaper_setters
from wallpaperctl.theme.runner import run_theme_ops
from wallpaperctl.util import spawn_detached

log = logging.getLogger("wallpaperctl")

THEME_WORKER_CMD = "__theme__"


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


def _wants_sync(explicit_sync: bool, ops: OpsConfig) -> bool:
    """True when theme ops must run in the foreground.

    Explicit --sync wins; otherwise WALLPAPERCTL_SYNC=1 or
    background_theme=false in config forces sync (debugging).
    """
    if explicit_sync:
        return True
    if os.environ.get("WALLPAPERCTL_SYNC") == "1":
        return True
    return not ops.background_theme


def build_context(
    path: Path,
    ops: OpsConfig,
    *,
    photographer_name: str = "",
    photographer_username: str = "",
    provider_name: str = "",
    debug: bool = False,
):
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

    static_path = extract_frame(path, ops) if is_animated(path) else path
    return WallpaperContext(
        path=path.resolve(),
        de=de,
        ops=ops,
        static_path=static_path,
        photographer_name=photographer_name,
        photographer_username=photographer_username,
        provider_name=provider_name,
        debug=debug,
    )


def _report_theme_result(ctx: WallpaperContext, set_ok: int, set_total: int) -> bool:
    """Run theme ops synchronously and report. Returns True (setters won)."""
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

    name = ctx.path.name
    if "_credited" in name:
        safe_notify("Wallpaper Script", f"Wallpaper set with credits: {name}")
    else:
        safe_notify("Wallpaper Script", f"Wallpaper set: {name}")
    return True


def theme_worker_argv(
    path: Path,
    *,
    photographer_name: str = "",
    photographer_username: str = "",
    provider_name: str = "",
    debug: bool = False,
) -> list[str]:
    """Detached worker command re-running only the theme phase."""
    argv = [sys.executable, "-m", "wallpaperctl", THEME_WORKER_CMD, str(path)]
    if photographer_name:
        argv += ["--photographer-name", photographer_name]
    if photographer_username:
        argv += ["--photographer-username", photographer_username]
    if provider_name:
        argv += ["--provider-name", provider_name]
    if debug:
        argv += ["--debug"]
    return argv


def spawn_theme_background(ctx: WallpaperContext) -> bool:
    """Detach the slow theme phase; return False if the spawn itself failed."""
    argv = theme_worker_argv(
        ctx.path,
        photographer_name=ctx.photographer_name,
        photographer_username=ctx.photographer_username,
        provider_name=ctx.provider_name,
        debug=ctx.debug,
    )
    proc = spawn_detached(argv)
    if proc is None:
        log.warning("Background theme spawn failed; running theme ops in foreground")
        return False
    log.debug("Theme ops backgrounded (pid %s) for %s", proc.pid, ctx.path)
    return True


def apply_wallpaper(
    path: Path,
    ops: OpsConfig,
    *,
    photographer_name: str = "",
    photographer_username: str = "",
    provider_name: str = "",
    debug: bool = False,
    sync: bool = False,
) -> bool:
    """Set wallpaper and run theme ops.

    By default the slow theme phase runs in a detached background worker so
    the CLI returns as soon as the wallpaper is visible. Pass sync=True
    (--sync) to run theme ops in the foreground for debugging.

    Returns True if at least one wallpaper setter succeeded. Theme-op failures
    are soft (warnings only) and do not flip the return value to False.
    """
    ctx = build_context(
        path,
        ops,
        photographer_name=photographer_name,
        photographer_username=photographer_username,
        provider_name=provider_name,
        debug=debug,
    )
    log.debug("Applying wallpaper %s on DE %s", ctx.path, ctx.de.name)

    set_ok, set_total = run_wallpaper_setters(ctx)
    if set_total == 0 or set_ok == 0:
        msg = (
            "Error: Failed to set wallpaper "
            f"(setters attempted={set_total}, succeeded={set_ok}, DE={ctx.de.name})"
        )
        print(msg, file=sys.stderr)
        safe_notify("Wallpaper Script", msg)
        return False

    if _wants_sync(sync, ops):
        return _report_theme_result(ctx, set_ok, set_total)

    if spawn_theme_background(ctx):
        name = ctx.path.name
        if "_credited" in name:
            safe_notify(
                "Wallpaper Script",
                f"Wallpaper set with credits: {name} (theming in background)",
            )
        else:
            safe_notify(
                "Wallpaper Script", f"Wallpaper set: {name} (theming in background)"
            )
        return True

    # Spawn failed: fall back to foreground so theming still happens.
    return _report_theme_result(ctx, set_ok, set_total)


def run_theme_worker(
    path: Path,
    ops: OpsConfig,
    *,
    photographer_name: str = "",
    photographer_username: str = "",
    provider_name: str = "",
    debug: bool = False,
) -> int:
    """Entry point for the detached __theme__ worker. Returns exit code."""
    ctx = build_context(
        path,
        ops,
        photographer_name=photographer_name,
        photographer_username=photographer_username,
        provider_name=provider_name,
        debug=debug,
    )
    # A newer `set` may have superseded us while we were spawning; don't let
    # a stale palette overwrite the current wallpaper's theme.
    try:
        current = load_current_wallpaper(ops)
        if current.resolve() != ctx.path.resolve():
            log.debug(
                "Skipping stale theme worker for %s (current is %s)",
                ctx.path,
                current,
            )
            return 0
    except SystemExit:
        pass
    except OSError as e:
        log.debug("Stale-check skipped: %s", e)

    theme_failed, theme_total = run_theme_ops(ctx)
    if theme_failed:
        msg = f"Warning: {theme_failed} of {theme_total} theme operations failed"
        print(msg, file=sys.stderr)
        safe_notify("Wallpaper Script", msg)
        return 0
    log.debug("Background theme ops completed for %s", ctx.path)
    return 0
