"""Desktop environment / compositor detection."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from wallpaperctl.util import have, pgrep_exact, pgrep_full, run

log = logging.getLogger("wallpaperctl")


@dataclass
class DesktopEnvironment:
    plasma: bool = False
    hyprland: bool = False
    xfce: bool = False
    cinnamon: bool = False
    noctalia: bool = False
    awesome: bool = False

    @property
    def name(self) -> str:
        if self.plasma:
            return "plasma"
        if self.hyprland and self.noctalia:
            return "hyprland+noctalia"
        if self.hyprland:
            return "hyprland"
        if self.xfce:
            return "xfce"
        if self.cinnamon:
            return "cinnamon"
        if self.awesome:
            return "awesome"
        return "fallback"

    @property
    def is_de(self) -> bool:
        return self.plasma or self.hyprland or self.xfce or self.cinnamon


def is_plasma_running() -> bool:
    if pgrep_exact("plasmashell"):
        log.debug("KDE Plasma detected (plasmashell is running)")
        return True
    if have("dbus-send"):
        r = run(
            [
                "dbus-send",
                "--session",
                "--dest=org.kde.plasmashell",
                "--type=method_call",
                "--print-reply",
                "/PlasmaShell",
                "org.freedesktop.DBus.Peer.Ping",
            ],
            timeout=3,
        )
        if r.returncode == 0:
            log.debug("KDE Plasma detected (dbus service available)")
            return True
    return False


def is_hyprland_running() -> bool:
    if pgrep_exact("Hyprland"):
        log.debug("Hyprland detected (Hyprland process is running)")
        return True
    if have("hyprctl"):
        r = run(["hyprctl", "version"], timeout=3)
        if r.returncode == 0:
            log.debug("Hyprland detected (hyprctl is available)")
            return True
    return False


def is_xfce_running() -> bool:
    if os.environ.get("XDG_CURRENT_DESKTOP", "").upper() == "XFCE":
        log.debug("XFCE detected (XDG_CURRENT_DESKTOP)")
        return True
    if os.environ.get("DESKTOP_SESSION", "").lower() == "xfce":
        log.debug("XFCE detected (DESKTOP_SESSION)")
        return True
    if pgrep_exact("xfce4-session") or pgrep_exact("xfce4-panel"):
        log.debug("XFCE detected (session/panel process)")
        return True
    return False


def is_cinnamon_running() -> bool:
    if pgrep_exact("cinnamon") or pgrep_exact("cinnamon-session"):
        log.debug("Cinnamon detected (process)")
        return True
    if pgrep_full("cinnamon --replace"):
        return True
    xdg = os.environ.get("XDG_CURRENT_DESKTOP", "")
    session = os.environ.get("DESKTOP_SESSION", "")
    if xdg in ("X-Cinnamon", "CINNAMON") or session in (
        "cinnamon",
        "cinnamon2d",
        "cinnamon-session",
    ):
        log.debug("Cinnamon detected (environment)")
        return True
    return False


def is_noctalia_running() -> bool:
    if pgrep_full("qs -c noctalia-shell"):
        log.debug("Noctalia detected (qs process)")
        return True
    if have("qs"):
        r = run(
            ["qs", "-c", "noctalia-shell", "ipc", "call", "wallpaper", "get", "all"],
            timeout=5,
        )
        if r.returncode == 0:
            log.debug("Noctalia detected (qs IPC)")
            return True
    return False


def is_awesome_running() -> bool:
    return pgrep_exact("awesome")


def detect_desktop() -> DesktopEnvironment:
    de = DesktopEnvironment(
        plasma=is_plasma_running(),
        hyprland=is_hyprland_running(),
        xfce=is_xfce_running(),
        cinnamon=is_cinnamon_running(),
        noctalia=is_noctalia_running(),
        awesome=is_awesome_running(),
    )
    log.debug("Detected desktop: %s", de.name)
    return de
