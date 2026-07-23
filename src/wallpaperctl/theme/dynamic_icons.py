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

        bg, red, green, accent, fg = (
            strip(colors[0]),
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
    for size in SIZES:
        s = size
        # places
        _svg(
            theme_dir / str(s) / "places" / "folder.svg",
            s,
            f'<path fill="#{accent}" d="M2 6v8c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-6L8 4H4c-1.1 0-2 .9-2 2z"/>',
        )
        _svg(
            theme_dir / str(s) / "places" / "folder-open.svg",
            s,
            f'<path fill="#{accent}" d="M2 6v6l2 2h12c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-6L8 4H4c-1.1 0-2 .9-2 2z"/>',
        )
        _svg(
            theme_dir / str(s) / "places" / "user-home.svg",
            s,
            f'<path fill="#{accent}" d="M8 2L2 8v6c0 1.1.9 2 2 2h3v-4h2v4h3c1.1 0 2-.9 2-2V8L8 2z"/>',
        )
        _svg(
            theme_dir / str(s) / "places" / "folder-documents.svg",
            s,
            f'<path fill="#{accent}" d="M2 6v8c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-6L8 4H4c-1.1 0-2 .9-2 2z"/>'
            f'<rect x="6" y="9" width="4" height="1" fill="#{fg}"/>'
            f'<rect x="6" y="11" width="6" height="1" fill="#{fg}"/>',
        )
        _svg(
            theme_dir / str(s) / "places" / "folder-download.svg",
            s,
            f'<path fill="#{accent}" d="M2 6v8c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-6L8 4H4c-1.1 0-2 .9-2 2z"/>'
            f'<path fill="#{fg}" d="M8 9v2m-1 1l1 1 1-1"/>',
        )
        _svg(
            theme_dir / str(s) / "places" / "user-desktop.svg",
            s,
            f'<rect x="2" y="4" width="12" height="8" rx="1" fill="#{accent}"/>'
            f'<rect x="7" y="12" width="2" height="2" fill="#{accent}"/>',
        )
        # status
        _svg(
            theme_dir / str(s) / "status" / "network-wireless-signal-excellent-symbolic.svg",
            s,
            f'<path fill="#{fg}" d="M2 10c0-4.4 3.6-8 8-8s8 3.6 8 8"/>'
            f'<path fill="#{fg}" d="M5 10c0-2.8 2.2-5 5-5s5 2.2 5 5"/>'
            f'<circle cx="10" cy="12" r="1" fill="#{accent}"/>',
        )
        _svg(
            theme_dir / str(s) / "status" / "audio-volume-high-symbolic.svg",
            s,
            f'<path fill="#{fg}" d="M6 4v8l4-2V6L6 4z"/>'
            f'<path fill="#{accent}" d="M14 4v8c2.2 0 4-1.8 4-4s-1.8-4-4-4"/>',
        )
        _svg(
            theme_dir / str(s) / "status" / "battery-full-symbolic.svg",
            s,
            f'<rect x="3" y="6" width="10" height="8" rx="1" fill="none" stroke="#{fg}" stroke-width="1"/>'
            f'<rect x="4" y="7" width="8" height="6" fill="#{green}"/>',
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
            f'<rect x="2" y="3" width="12" height="10" rx="1" fill="none" stroke="#{fg}" stroke-width="1"/>'
            f'<path fill="#{accent}" d="M4 6l2 2-2 2" stroke="#{accent}" fill="none"/>',
        )
        _svg(
            theme_dir / str(s) / "devices" / "drive-harddisk-symbolic.svg",
            s,
            f'<rect x="3" y="4" width="10" height="8" rx="1" fill="#{accent}"/>'
            f'<circle cx="11" cy="8" r="1" fill="#{fg}"/>',
        )

        # scalable copies of key icons
    for name, folder in (
        ("folder.svg", "places"),
        ("user-home.svg", "places"),
        ("window-close-symbolic.svg", "actions"),
    ):
        src = theme_dir / "48" / folder / name
        if src.is_file():
            shutil.copy(src, theme_dir / "scalable" / folder / name)


def _svg(path: Path, size: int, body: str) -> None:
    path.write_text(
        f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" '
        f'xmlns="http://www.w3.org/2000/svg">\n  {body}\n</svg>\n',
        encoding="utf-8",
    )
