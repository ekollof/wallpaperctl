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
    try:
        from jeepney import DBusAddress, MessageType, new_method_call
        from jeepney.io.blocking import open_dbus_connection
    except ImportError:
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

    # org.freedesktop.Notifications.Notify — signature: susssasa{sv}i
    addr = DBusAddress(
        "/org/freedesktop/Notifications",
        bus_name="org.freedesktop.Notifications",
        interface="org.freedesktop.Notifications",
    )
    msg = new_method_call(
        addr,
        "Notify",
        "susssasa{sv}i",
        (
            APP_NAME,  # app_name
            0,  # replaces_id
            icon,  # app_icon (path or theme name)
            title,  # summary
            message,  # body
            [],  # actions (as)
            hints,  # hints (a{sv})
            int(timeout_ms),  # expire_timeout
        ),
    )

    try:
        with open_dbus_connection(bus="SESSION") as conn:
            reply = conn.send_and_get_reply(msg, timeout=5)
        if reply.header.message_type == MessageType.method_return:
            log.debug("D-Bus notification sent with icon %s: %s", icon, title)
            return True
        log.debug("D-Bus Notify error reply: %s", reply)
        return False
    except Exception as e:
        log.debug("D-Bus notification failed: %s", e)
        return False
