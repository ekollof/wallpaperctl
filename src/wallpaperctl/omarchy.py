"""Omarchy integration helpers (paths, theme state, tooling invocation)."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from wallpaperctl.util import have, home, pgrep_exact, pgrep_full, run

log = logging.getLogger("wallpaperctl")

THEME_SLUG = "dynamic-wallpapers"
THEME_DISPLAY = "Dynamic Wallpapers"

DEFAULT_OMARCHY_PATH = "/usr/share/omarchy"
MOTION_VIDEO_EXTENSIONS = ("mp4", "webm", "mkv", "mov")


def state_dir() -> Path:
    """Omarchy per-session state (~/.local/state/omarchy/current)."""
    return home() / ".local" / "state" / "omarchy" / "current"


def theme_name_file() -> Path:
    return state_dir() / "theme.name"


def background_link() -> Path:
    return state_dir() / "background"


def user_themes_dir() -> Path:
    return home() / ".config" / "omarchy" / "themes"


def user_theme_dir(slug: str = THEME_SLUG) -> Path:
    return user_themes_dir() / slug


def omarchy_config_dir() -> Path:
    return home() / ".config" / "omarchy"


def omarchy_available() -> bool:
    """True when the omarchy tooling or its user config is present."""
    return have("omarchy") or omarchy_config_dir().is_dir()


def is_omarchy_shell_running() -> bool:
    """True when the omarchy-shell (quickshell) UI is up."""
    if pgrep_full("omarchy/shell"):
        return True
    return pgrep_exact("omarchy-shell")


def current_theme_name() -> str | None:
    """Slug of the active Omarchy theme, or None when unreadable."""
    path = theme_name_file()
    try:
        name = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    return name or None


def is_dynamic_theme_active(slug: str = THEME_SLUG) -> bool:
    return current_theme_name() == slug


def omarchy_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Environment for omarchy subprocesses (OMARCHY_PATH defaulted)."""
    env = dict(os.environ)
    if not env.get("OMARCHY_PATH"):
        env["OMARCHY_PATH"] = DEFAULT_OMARCHY_PATH
    if extra:
        env.update(extra)
    return env


def run_omarchy(
    args: list[str],
    *,
    timeout: float = 30,
    env_extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run `omarchy <args>` through the official dispatcher."""
    if not have("omarchy"):
        return subprocess.CompletedProcess(
            args=["omarchy", *args], returncode=127, stdout="", stderr="omarchy not found"
        )
    return run(
        ["omarchy", *args],
        timeout=timeout,
        env=omarchy_env(env_extra),
    )


def shell_ipc(args: list[str], *, timeout: float = 5) -> bool:
    """Best-effort omarchy-shell IPC (returns False when shell is down)."""
    if not have("omarchy-shell"):
        return False
    r = run(
        ["omarchy-shell", *args],
        timeout=timeout,
        env=omarchy_env(),
    )
    return r.returncode == 0


def motion_wallpaper_play(video: Path, *, timeout: float = 5) -> bool:
    return shell_ipc(["motion-wallpaper", "play", str(video)], timeout=timeout)


def motion_wallpaper_stop(*, timeout: float = 5) -> bool:
    return shell_ipc(["motion-wallpaper", "stop"], timeout=timeout)
