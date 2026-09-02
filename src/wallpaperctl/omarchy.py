"""Omarchy integration helpers (paths, theme state, tooling invocation)."""

from __future__ import annotations

import base64
import json
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


def is_omarchy_session() -> bool:
    """True when this looks like a live Omarchy desktop session.

    A leftover ``~/.config/omarchy`` directory is not enough — that would
    steal the wallpaper setter from hyprpaper on a non-Omarchy Hyprland
    session. Require the shell, or the CLI plus a staged current theme.
    """
    if is_omarchy_shell_running():
        return True
    return have("omarchy") and theme_name_file().is_file()


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


def motion_state_file() -> Path:
    return home() / ".local" / "state" / "motion-wallpaper" / "state.json"


def motion_wallpaper_playing() -> bool:
    """Best-effort read of the motion-wallpaper plugin's persisted state."""
    path = motion_state_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    if not isinstance(data, dict):
        return False
    enabled = data.get("enabled")
    return enabled is True or str(enabled).lower() == "true"


def apply_shell_theme_live(
    colors_file: Path,
    shell_file: Path | None = None,
    *,
    timeout: float = 3,
) -> bool:
    """Push a new palette to the running omarchy-shell without a full refresh.

    Only the bar/chrome. Kitty and Hyprland borders are retinted separately
    from the generated theme files (no compositor reload).
    """
    if not colors_file.is_file():
        return False
    try:
        colors_b64 = base64.b64encode(colors_file.read_bytes()).decode("ascii")
    except OSError:
        return False
    shell_b64 = ""
    if shell_file is not None and shell_file.is_file():
        try:
            shell_b64 = base64.b64encode(shell_file.read_bytes()).decode("ascii")
        except OSError:
            shell_b64 = ""
    return shell_ipc(["shell", "applyTheme", colors_b64, shell_b64], timeout=timeout)
