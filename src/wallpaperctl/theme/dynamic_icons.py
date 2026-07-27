"""Dynamic SVG icon theme from wallust colors (Cinnamon-focused)."""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

from wallpaperctl.context import WallpaperContext
from wallpaperctl.theme.base import debug_op
from wallpaperctl.util import have, home, read_wal_colors, run

log = logging.getLogger("wallpaperctl")

SIZES = (16, 22, 24, 32, 48)
CONTEXTS = ("actions", "apps", "devices", "places", "status")


class DynamicIconsOp:
    name = "dynamic-icons"

    def enabled(self, ctx: WallpaperContext) -> bool:
        return ctx.ops.enable_dynamic_icons and ctx.de.cinnamon

    def run(self, ctx: WallpaperContext) -> bool:
        colors = read_wal_colors()

        if len(colors) < 8:
            debug_op(self.name, "not enough colors", ctx)
            return False

        def strip(c: str) -> str:
            return c.lstrip("#")

        red, green, accent, fg = (
            strip(colors[1]),
            strip(colors[2]),
            strip(colors[4]),
            strip(colors[7]),
        )
        theme_name = ctx.ops.dynamic_icon_theme_name
        theme_dir = home() / ".local" / "share" / "icons" / theme_name
        if theme_dir.exists():
            shutil.rmtree(theme_dir, ignore_errors=True)
        for size in (*SIZES, "scalable"):
            for ctx_name in CONTEXTS:
                (theme_dir / str(size) / ctx_name).mkdir(parents=True, exist_ok=True)

        (theme_dir / "index.theme").write_text(_index_theme(), encoding="utf-8")
        _write_icons(theme_dir, fg, accent, red, green)
        debug_op(self.name, f"generated icons in {theme_dir}", ctx)

        if have("gtk-update-icon-cache"):
            run(["gtk-update-icon-cache", "-f", "-t", str(theme_dir)], timeout=30)

        if have("gsettings"):
            for schema in (
                "org.gnome.desktop.interface",
                "org.cinnamon.desktop.interface",
            ):
                run(["gsettings", "set", schema, "icon-theme", theme_name], timeout=5)
            run(["gsettings", "set", "org.gnome.desktop.interface", "icon-theme", ""], timeout=5)
            time.sleep(0.5)
            run(
                ["gsettings", "set", "org.gnome.desktop.interface", "icon-theme", theme_name],
                timeout=5,
            )
        return True


def _index_theme() -> str:
    dirs = []
    sections = []
    for size in SIZES:
        for ctx_name in CONTEXTS:
            d = f"{size}/{ctx_name}"
            dirs.append(d)
            context = {
                "actions": "Actions",
                "apps": "Applications",
                "devices": "Devices",
                "places": "Places",
                "status": "Status",
            }[ctx_name]
            sections.append(
                f"[{d}]\nSize={size}\nContext={context}\nType=Fixed\n"
            )
    for ctx_name in CONTEXTS:
        d = f"scalable/{ctx_name}"
        dirs.append(d)
        context = {
            "actions": "Actions",
            "apps": "Applications",
            "devices": "Devices",
            "places": "Places",
            "status": "Status",
        }[ctx_name]
        sections.append(
            f"[{d}]\nSize=64\nMinSize=16\nMaxSize=512\nContext={context}\nType=Scalable\n"
        )
    head = (
        "[Icon Theme]\n"
        "Name=Wallust Dynamic\n"
        "Comment=Dynamically generated icon theme based on wallpaper colors\n"
        "Inherits=Mint-Y,Mint-X,Adwaita,hicolor\n"
        "Hidden=false\n"
        f"Directories={','.join(dirs)}\n\n"
    )
    return head + "\n".join(sections)


def _write_icons(theme_dir: Path, fg: str, accent: str, red: str, green: str) -> None:
    folder_d = (
        "M2 6v8c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-6"
        "L8 4H4c-1.1 0-2 .9-2 2z"
    )
    folder_open_d = (
        "M2 6v6l2 2h12c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-6L8 4H4c-1.1 0-2 .9-2 2z"
    )
    home_d = "M8 2L2 8v6c0 1.1.9 2 2 2h3v-4h2v4h3c1.1 0 2-.9 2-2V8L8 2z"

    for size in SIZES:
        s = size
        # places
        _svg(
            theme_dir / str(s) / "places" / "folder.svg",
            s,
            f'<path fill="#{accent}" d="{folder_d}"/>',
        )
        _svg(
            theme_dir / str(s) / "places" / "folder-open.svg",
            s,
            f'<path fill="#{accent}" d="{folder_open_d}"/>',
        )
        _svg(
            theme_dir / str(s) / "places" / "user-home.svg",
            s,
            f'<path fill="#{accent}" d="{home_d}"/>',
        )
        _svg(
            theme_dir / str(s) / "places" / "folder-documents.svg",
            s,
            f'<path fill="#{accent}" d="{folder_d}"/>'
            f'<rect x="6" y="9" width="4" height="1" fill="#{fg}"/>'
            f'<rect x="6" y="11" width="6" height="1" fill="#{fg}"/>',
        )
        _svg(
            theme_dir / str(s) / "places" / "folder-download.svg",
            s,
            f'<path fill="#{accent}" d="{folder_d}"/>'
            f'<path fill="#{fg}" d="M8 9v2m-1 1l1 1 1-1"/>',
        )
        _svg(
            theme_dir / str(s) / "places" / "user-desktop.svg",
            s,
            f'<rect x="2" y="4" width="12" height="8" rx="1" fill="#{accent}"/>'
            f'<rect x="7" y="12" width="2" height="2" fill="#{accent}"/>',
        )
        # status
        # status (panel indicators — shell parity)
        _batt = (
            "M 3,6 V 14 C 3,14.55 3.45,15 4,15 H 12 C 12.55,15 13,14.55 13,14 V 6 "
            "C 13,5.45 12.55,5 12,5 H 10 V 4 C 10,3.45 9.55,3 9,3 H 7 C 6.45,3 6,3.45 "
            "6,4 V 5 H 4 C 3.45,5 3,5.45 3,6 Z"
        )
        _svg(
            theme_dir / str(s) / "status" / "network-wireless-signal-excellent-symbolic.svg",
            s,
            f'<path fill="#{fg}" d="M2 10c0-4.4 3.6-8 8-8s8 3.6 8 8"/>'
            f'<path fill="#{fg}" d="M5 10c0-2.8 2.2-5 5-5s5 2.2 5 5"/>'
            f'<path fill="#{fg}" d="M8 10c0-1.1.9-2 2-2s2 .9 2 2"/>'
            f'<circle cx="10" cy="12" r="1" fill="#{accent}"/>',
        )
        _svg(
            theme_dir / str(s) / "status" / "network-wireless-offline-symbolic.svg",
            s,
            f'<path fill="#{red}" d="M2 10c0-4.4 3.6-8 8-8s8 3.6 8 8" opacity="0.3"/>'
            f'<path fill="#{red}" d="M2 2l16 16" stroke-width="2"/>',
        )
        _svg(
            theme_dir / str(s) / "status" / "audio-volume-high-symbolic.svg",
            s,
            f'<path fill="#{fg}" d="M6 4v8l4-2V6L6 4z"/>'
            f'<path fill="#{fg}" d="M12 6v4c1.1 0 2-.9 2-2s-.9-2-2-2"/>'
            f'<path fill="#{accent}" d="M14 4v8c2.2 0 4-1.8 4-4s-1.8-4-4-4"/>',
        )
        _svg(
            theme_dir / str(s) / "status" / "audio-volume-muted-symbolic.svg",
            s,
            f'<path fill="#{fg}" d="M6 4v8l4-2V6L6 4z"/>'
            f'<path fill="#{red}" d="M12 6l4 4m0-4l-4 4" stroke-width="2"/>',
        )
        _svg(
            theme_dir / str(s) / "status" / "battery-full-symbolic.svg",
            s,
            f'<path d="{_batt}" fill="none" stroke="#{fg}" stroke-width="1"/>'
            f'<rect x="4" y="7" width="8" height="6" fill="#{green}"/>',
        )
        _svg(
            theme_dir / str(s) / "status" / "battery-good-symbolic.svg",
            s,
            f'<path d="{_batt}" fill="none" stroke="#{fg}" stroke-width="1"/>'
            f'<rect x="4" y="10" width="8" height="3" fill="#{green}"/>',
        )
        _svg(
            theme_dir / str(s) / "status" / "battery-low-symbolic.svg",
            s,
            f'<path d="{_batt}" fill="none" stroke="#{fg}" stroke-width="1"/>'
            f'<rect x="4" y="12" width="8" height="1" fill="#{red}"/>',
        )
        _svg(
            theme_dir / str(s) / "status" / "battery-caution-symbolic.svg",
            s,
            f'<path d="{_batt}" fill="none" stroke="#{fg}" stroke-width="1"/>'
            f'<rect x="4" y="11" width="8" height="2" fill="#{accent}"/>',
        )
        _svg(
            theme_dir / str(s) / "status" / "bluetooth-active-symbolic.svg",
            s,
            f'<path fill="#{accent}" d="M8 2l3 3-2 2 2 2-3 3V8l-2 2-1-1 3-3-3-3 1-1 2 2V2z"/>',
        )
        _svg(
            theme_dir / str(s) / "status" / "notification-symbolic.svg",
            s,
            f'<path fill="#{fg}" d="M10 2C8.9 2 8 2.9 8 4v4c0 1.1-.9 2-2 2H4v2h12v-2h-2'
            f'c-1.1 0-2-.9-2-2V4c0-1.1-.9-2-2-2z"/>'
            f'<circle cx="10" cy="15" r="1" fill="#{accent}"/>',
        )
        _svg(
            theme_dir / str(s) / "status" / "user-available-symbolic.svg",
            s,
            f'<circle cx="10" cy="7" r="3" fill="#{fg}"/>'
            f'<path fill="#{fg}" d="M4 18c0-3.3 2.7-6 6-6s6 2.7 6 6"/>',
        )
        _svg(
            theme_dir / str(s) / "status" / "view-app-grid-symbolic.svg",
            s,
            f'<rect x="2" y="2" width="6" height="6" fill="#{fg}"/>'
            f'<rect x="12" y="2" width="6" height="6" fill="#{fg}"/>'
            f'<rect x="2" y="12" width="6" height="6" fill="#{fg}"/>'
            f'<rect x="12" y="12" width="6" height="6" fill="#{accent}"/>',
        )
        _svg(
            theme_dir / str(s) / "status" / "dialog-warning-symbolic.svg",
            s,
            f'<path fill="#{red}" d="M8 2L1 14h14L8 2z"/>'
            f'<rect x="7.5" y="6" width="1" height="4" fill="#{fg}"/>'
            f'<circle cx="8" cy="12" r="0.7" fill="#{fg}"/>',
        )
        # actions
        _svg(
            theme_dir / str(s) / "actions" / "system-search-symbolic.svg",
            s,
            f'<circle cx="7" cy="7" r="4" fill="none" stroke="#{fg}" stroke-width="1.5"/>'
            f'<line x1="10" y1="10" x2="14" y2="14" stroke="#{accent}" stroke-width="1.5"/>',
        )
        _svg(
            theme_dir / str(s) / "actions" / "window-close-symbolic.svg",
            s,
            f'<line x1="4" y1="4" x2="12" y2="12" stroke="#{red}" stroke-width="2"/>'
            f'<line x1="12" y1="4" x2="4" y2="12" stroke="#{red}" stroke-width="2"/>',
        )
        # apps / devices placeholders
        _svg(
            theme_dir / str(s) / "apps" / "utilities-terminal-symbolic.svg",
            s,
            f'<rect x="2" y="3" width="12" height="10" rx="1" fill="none" '
            f'stroke="#{fg}" stroke-width="1"/>'
            f'<path fill="#{accent}" d="M4 6l2 2-2 2" stroke="#{accent}" fill="none"/>',
        )
        _svg(
            theme_dir / str(s) / "devices" / "drive-harddisk-symbolic.svg",
            s,
            f'<rect x="3" y="4" width="10" height="8" rx="1" fill="#{accent}"/>'
            f'<circle cx="11" cy="8" r="1" fill="#{fg}"/>',
        )

    # Scalable copies (shell uses 24px as base)
    _STATUS_SCALABLE = (
        "network-wireless-signal-excellent-symbolic",
        "network-wireless-offline-symbolic",
        "audio-volume-high-symbolic",
        "audio-volume-muted-symbolic",
        "battery-full-symbolic",
        "battery-good-symbolic",
        "battery-low-symbolic",
        "battery-caution-symbolic",
        "bluetooth-active-symbolic",
        "notification-symbolic",
        "user-available-symbolic",
        "view-app-grid-symbolic",
        "dialog-warning-symbolic",
    )
    _PLACES_SCALABLE = (
        "folder",
        "folder-open",
        "user-home",
        "folder-documents",
        "folder-download",
        "user-desktop",
    )
    for icon in _STATUS_SCALABLE:
        src = theme_dir / "24" / "status" / f"{icon}.svg"
        if src.is_file():
            shutil.copy(src, theme_dir / "scalable" / "status" / f"{icon}.svg")
    for icon in _PLACES_SCALABLE:
        src = theme_dir / "24" / "places" / f"{icon}.svg"
        if src.is_file():
            shutil.copy(src, theme_dir / "scalable" / "places" / f"{icon}.svg")
    for name, folder in (
        ("window-close-symbolic.svg", "actions"),
        ("system-search-symbolic.svg", "actions"),
    ):
        src = theme_dir / "24" / folder / name
        if src.is_file():
            shutil.copy(src, theme_dir / "scalable" / folder / name)


def _svg(path: Path, size: int, body: str) -> None:
    path.write_text(
        f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" '
        f'xmlns="http://www.w3.org/2000/svg">\n  {body}\n</svg>\n',
        encoding="utf-8",
    )
