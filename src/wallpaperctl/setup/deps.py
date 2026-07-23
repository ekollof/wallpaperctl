"""Declarative dependency catalog for wallpaperctl."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from wallpaperctl.detect.desktop import DesktopEnvironment
from wallpaperctl.util import have


class Kind(str, Enum):
    CORE = "core"  # always useful
    PYTHON = "python"  # pip/uv package (already in pyproject)
    DE = "desktop"  # required for active DE
    THEME = "theme"  # wallust / theming
    OPTIONAL = "optional"


@dataclass
class Dep:
    """One installable / checkable dependency."""

    id: str
    description: str
    kind: Kind
    # Check: binary name, or special "python:module"
    check: str
    # Package names per package manager
    pacman: str | None = None
    apt: str | None = None
    dnf: str | None = None
    freebsd_pkg: str | None = None
    openbsd_pkg: str | None = None
    # Which DE ids need this for "required" (empty = always when kind matches)
    for_de: tuple[str, ...] = ()
    # pip name if python package
    pip: str | None = None
    notes: str = ""

    def is_present(self) -> bool:
        if self.check.startswith("python:"):
            mod = self.check.removeprefix("python:")
            try:
                __import__(mod)
                return True
            except ImportError:
                return False
        if self.check == "any-x11-setter":
            return any(
                have(c) for c in ("feh", "nitrogen", "hsetroot", "xwallpaper", "xsetbg")
            )
        return have(self.check)

    def package_for(self, pm: str) -> str | None:
        return {
            "pacman": self.pacman,
            "apt": self.apt,
            "dnf": self.dnf,
            "freebsd_pkg": self.freebsd_pkg,
            "openbsd_pkg": self.openbsd_pkg,
            "pip": self.pip,
        }.get(pm)


# ── Catalog ──────────────────────────────────────────────────────────────

DEPS: list[Dep] = [
    # Python (normally installed with wallpaperctl itself)
    Dep(
        "pillow",
        "Image resize, credits, validation",
        Kind.PYTHON,
        "python:PIL",
        pip="Pillow",
    ),
    Dep(
        "imagehash",
        "Perceptual dedup",
        Kind.PYTHON,
        "python:imagehash",
        pip="imagehash",
    ),
    Dep(
        "httpx",
        "Remote wallpaper fetch",
        Kind.PYTHON,
        "python:httpx",
        pip="httpx",
    ),
    Dep(
        "jeepney",
        "Session D-Bus (Plasma wallpaper, notifications)",
        Kind.PYTHON,
        "python:jeepney",
        pip="jeepney",
    ),
    # Core
    Dep(
        "wallust",
        "Color schemes from wallpaper (pywal-compatible cache)",
        Kind.THEME,
        "wallust",
        pacman="wallust-git",  # AUR/chaotic; also try wallust
        apt=None,  # often cargo install
        freebsd_pkg=None,
        notes="Also: cargo install wallust  |  paru -S wallust-git",
    ),
    Dep(
        "xrandr",
        "Detect connected monitors (XFCE multihead / docking)",
        Kind.CORE,
        "xrandr",
        pacman="xorg-xrandr",
        apt="x11-xserver-utils",
        dnf="xorg-x11-server-utils",
        freebsd_pkg="xrandr",
        openbsd_pkg="xrandr",
    ),
    # Plasma
    Dep(
        "kwriteconfig6",
        "Plasma 6 lockscreen wallpaper (kscreenlockerrc)",
        Kind.DE,
        "kwriteconfig6",
        pacman="plasma-workspace",
        apt="plasma-workspace",
        dnf="plasma-workspace",
        for_de=("plasma",),
    ),
    Dep(
        "plasmashell",
        "KDE Plasma desktop shell",
        Kind.DE,
        "plasmashell",
        pacman="plasma-workspace",
        apt="plasma-workspace",
        for_de=("plasma",),
    ),
    # Hyprland
    Dep(
        "hyprctl",
        "Hyprland control (hyprpaper wallpaper)",
        Kind.DE,
        "hyprctl",
        pacman="hyprland",
        for_de=("hyprland", "hyprland+noctalia"),
    ),
    Dep(
        "hyprpaper",
        "Hyprland wallpaper backend",
        Kind.DE,
        "hyprpaper",
        pacman="hyprpaper",
        for_de=("hyprland",),
        notes="Not needed when Noctalia manages wallpaper",
    ),
    # Noctalia
    Dep(
        "qs",
        "Quickshell / Noctalia IPC",
        Kind.DE,
        "qs",
        pacman="quickshell",
        for_de=("hyprland+noctalia",),
        notes="Package name varies (quickshell / noctalia-shell)",
    ),
    # XFCE
    Dep(
        "xfconf-query",
        "XFCE config (wallpaper + appearance channel)",
        Kind.DE,
        "xfconf-query",
        pacman="xfconf",
        apt="xfconf",
        dnf="xfconf",
        for_de=("xfce",),
    ),
    Dep(
        "xfsettingsd",
        "XFCE settings daemon (Appearance must have this running)",
        Kind.DE,
        "xfsettingsd",
        pacman="xfce4-settings",
        apt="xfce4-settings",
        dnf="xfce4-settings",
        for_de=("xfce",),
    ),
    Dep(
        "xfdesktop",
        "XFCE desktop (reload after wallpaper set)",
        Kind.DE,
        "xfdesktop",
        pacman="xfdesktop",
        apt="xfdesktop4",
        dnf="xfdesktop",
        for_de=("xfce",),
    ),
    # Cinnamon
    Dep(
        "gsettings",
        "GSettings (Cinnamon / GTK themes)",
        Kind.DE,
        "gsettings",
        pacman="glib2",
        apt="libglib2.0-bin",
        dnf="glib2",
        freebsd_pkg="glib",
        for_de=("cinnamon", "fallback"),
    ),
    # Fallback X11
    Dep(
        "feh",
        "X11 wallpaper setter (fallback)",
        Kind.DE,
        "feh",
        pacman="feh",
        apt="feh",
        dnf="feh",
        freebsd_pkg="feh",
        openbsd_pkg="feh",
        for_de=("fallback",),
    ),
    Dep(
        "xwallpaper",
        "X11 wallpaper setter (fallback alternative)",
        Kind.OPTIONAL,
        "xwallpaper",
        pacman="xwallpaper",
        apt="xwallpaper",
        for_de=("fallback",),
    ),
    # Theme / UX optional
    Dep(
        "xrdb",
        "Merge wallust Xresources",
        Kind.THEME,
        "xrdb",
        pacman="xorg-xrdb",
        apt="x11-xserver-utils",
        dnf="xorg-x11-server-utils",
        freebsd_pkg="xrdb",
    ),
    Dep(
        "nwg-look",
        "GTK settings reload (Hyprland / standalone)",
        Kind.OPTIONAL,
        "nwg-look",
        pacman="nwg-look",
        notes="Wayland-friendly GTK theme applier",
    ),
    Dep(
        "mako",
        "Notification daemon (Hyprland)",
        Kind.OPTIONAL,
        "mako",
        pacman="mako",
        apt="mako-notifier",
        for_de=("hyprland", "hyprland+noctalia"),
    ),
    Dep(
        "dunst",
        "Notification daemon (X11)",
        Kind.OPTIONAL,
        "dunst",
        pacman="dunst",
        apt="dunst",
        for_de=("fallback", "xfce"),
    ),
    Dep(
        "openrgb",
        "RGB lighting from palette",
        Kind.OPTIONAL,
        "openrgb",
        pacman="openrgb",
        apt="openrgb",
    ),
    Dep(
        "xsettingsd",
        "Standalone XSETTINGS (Hyprland / tiling — not with XFCE)",
        Kind.OPTIONAL,
        "xsettingsd",
        pacman="xsettingsd",
        apt="xsettingsd",
        for_de=("hyprland", "fallback"),
        notes="Do not run together with xfsettingsd",
    ),
]


@dataclass
class DepStatus:
    dep: Dep
    present: bool
    relevant: bool  # for current DE / setup profile
    required: bool


def de_profile(de: DesktopEnvironment) -> str:
    if de.plasma:
        return "plasma"
    if de.hyprland and de.noctalia:
        return "hyprland+noctalia"
    if de.hyprland:
        return "hyprland"
    if de.xfce:
        return "xfce"
    if de.cinnamon:
        return "cinnamon"
    return "fallback"


def classify_deps(
    de: DesktopEnvironment,
    *,
    include_optional: bool = True,
) -> list[DepStatus]:
    profile = de_profile(de)
    out: list[DepStatus] = []
    for dep in DEPS:
        if dep.for_de and profile not in dep.for_de and dep.kind == Kind.DE:
            # DE-specific and not our DE — still show as not relevant
            relevant = False
            required = False
        elif dep.for_de and profile not in dep.for_de and dep.kind == Kind.OPTIONAL:
            relevant = False
            required = False
        else:
            relevant = True
            if dep.kind in (Kind.CORE, Kind.PYTHON, Kind.THEME):
                required = dep.kind != Kind.OPTIONAL and dep.kind != Kind.THEME
                # wallust is strongly recommended but soft-fail at runtime
                if dep.id == "wallust":
                    required = False
                if dep.kind == Kind.PYTHON:
                    required = True
            elif dep.kind == Kind.DE:
                required = True
                # hyprpaper not required under noctalia
                if dep.id == "hyprpaper" and de.noctalia:
                    required = False
                    relevant = not de.noctalia
            else:
                required = False

        if not include_optional and dep.kind == Kind.OPTIONAL and not required:
            if not (relevant and dep.kind == Kind.DE):
                continue

        # Special: fallback needs at least one setter
        if dep.id == "feh" and profile == "fallback":
            required = not any(
                have(c)
                for c in ("feh", "nitrogen", "hsetroot", "xwallpaper", "xsetbg")
            )

        present = dep.is_present()
        out.append(
            DepStatus(dep=dep, present=present, relevant=relevant, required=required)
        )
    return out
