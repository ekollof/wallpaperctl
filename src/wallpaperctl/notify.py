"""Desktop notifications via the session bus (no notify-send / dbus-send)."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

log = logging.getLogger("wallpaperctl")

APP_NAME = "wallpaperctl"

# FreeDesktop theme names used if the packaged icon cannot be resolved.
_THEME_ICON_FALLBACK = "preferences-desktop-wallpaper"


def safe_notify(title: str, message: str, *, timeout_ms: int = 5000) -> None:
    """Send a FreeDesktop notification, or fall back to stderr."""
    has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    if has_display and _dbus_notify(title, message, timeout_ms=timeout_ms):
        return
    print(f"Notification: {title} - {message}", file=sys.stderr)


def notification_icon() -> str:
    """
    Absolute path to the packaged icon, or a themed icon name.

    Notification daemons accept either a filesystem path or an icon-theme name
    in the Notify app_icon field.
    """
    path = _packaged_icon_path()
    if path is not None:
        return str(path)
    return _THEME_ICON_FALLBACK


def _packaged_icon_path() -> Path | None:
    """Prefer a real file path so daemons do not depend on icon themes."""
    # Editable / source tree
    here = Path(__file__).resolve().parent / "assets"
    for name in ("icon-128.png", "icon-64.png", "icon-48.png"):
        candidate = here / name
        if candidate.is_file():
            return candidate

    # Installed package (wheel / zip)
    try:
        from importlib.resources import as_file, files

        root = files("wallpaperctl").joinpath("assets")
        for name in ("icon-128.png", "icon-64.png", "icon-48.png"):
            resource = root.joinpath(name)
            try:
                with as_file(resource) as p:
                    if p.is_file():
                        return Path(p)
            except (FileNotFoundError, TypeError, OSError):
                continue
    except Exception as e:
        log.debug("Could not resolve packaged notification icon: %s", e)

    return None


def _dbus_notify(title: str, message: str, *, timeout_ms: int) -> bool:
    from wallpaperctl.dbus_session import call as dbus_call
    from wallpaperctl.dbus_session import jeepney_available

    if not jeepney_available():
        log.debug("jeepney not installed; cannot send D-Bus notification")
        return False

    icon = notification_icon()
    # jeepney encodes a{sv} values as (signature, value) tuples
    hints: dict[str, tuple] = {
        "desktop-entry": ("s", APP_NAME),
        "urgency": ("y", 1),  # 0=low, 1=normal, 2=critical
    }
    if icon.startswith("/"):
        hints["image-path"] = ("s", icon)

    ok, err = dbus_call(
        bus_name="org.freedesktop.Notifications",
        path="/org/freedesktop/Notifications",
        interface="org.freedesktop.Notifications",
        method="Notify",
        signature="susssasa{sv}i",
        body=(
            APP_NAME,
            0,
            icon,
            title,
            message,
            [],
            hints,
            int(timeout_ms),
        ),
        timeout=5.0,
    )
    if ok:
        log.debug("D-Bus notification sent with icon %s: %s", icon, title)
        return True
    log.debug("D-Bus notification failed: %s", err)
    return False
