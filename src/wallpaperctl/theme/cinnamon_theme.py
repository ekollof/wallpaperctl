"""Cinnamon dynamic glass CSS + WM theme from wallust colors.

CSS/GTK templates live under ``data/cinnamon/`` (ported from the shell
``09-cinnamon-theme`` op). GTK *application* theme is not forced to
``cinnamon-dynamic`` so system notifications keep working.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import time
from importlib import resources
from pathlib import Path
from string import Template

from wallpaperctl.context import WallpaperContext
from wallpaperctl.theme.base import debug_op
from wallpaperctl.util import have, hex_to_rgb, home, read_wal_colors, run

log = logging.getLogger("wallpaperctl")

_MINT_METACITY_COLORS = (
    "#5d7555",
    "#8fb876",
    "#9cbf83",
    "#7d8f75",
    "#404040",
    "#666666",
    "#808080",
    "#999999",
    "#aaaaaa",
    "#bbbbbb",
    "#cccccc",
    "#dddddd",
    "#eeeeee",
    "#f5f5f5",
    "#f0f0f0",
    "#e8e8e8",
    "#e0e0e0",
    "#d9d9d9",
    "#d0d0d0",
    "#bababa",
    "#b5b5b5",
    "#a5a5a5",
    "#9d9d9d",
    "#35a854",
)

_SVG_REPLACEMENTS = (
    ("#5d7555", "accent"),
    ("#7d8f75", "hover"),
    ("#404040", "bg"),
    ("#666666", "fg"),
    ("#8fb876", "accent"),
    ("#9cbf83", "hover"),
)


class CinnamonThemeOp:
    name = "cinnamon-theme"

    def enabled(self, ctx: WallpaperContext) -> bool:
        return ctx.ops.enable_cinnamon_theme and ctx.de.cinnamon

    def run(self, ctx: WallpaperContext) -> bool:
        colors = read_wal_colors()

        if len(colors) < 8:
            debug_op(self.name, "not enough wal colors", ctx)
            return False

        def strip(c: str) -> str:
            return c.lstrip("#")

        color0 = strip(colors[0])
        color1 = strip(colors[1])  # often red — close button
        color2 = strip(colors[2])
        color3 = strip(colors[3])
        color4 = strip(colors[4])
        color7 = strip(colors[7])

        try:
            bg_rgb = ",".join(str(x) for x in hex_to_rgb(color0))
            accent_rgb = ",".join(str(x) for x in hex_to_rgb(color4))
            hover_rgb = ",".join(str(x) for x in hex_to_rgb(color2))
            fg_rgb = ",".join(str(x) for x in hex_to_rgb(color7))
        except ValueError as e:
            debug_op(self.name, f"bad color: {e}", ctx)
            return False

        theme_dir = home() / ".themes" / "cinnamon-dynamic"
        cin_dir = theme_dir / "cinnamon"
        gtk_dir = theme_dir / "gtk-3.0"
        gtk320_dir = theme_dir / "gtk-3.20"
        meta_dir = theme_dir / "metacity-1"
        for d in (cin_dir, gtk_dir, gtk320_dir, meta_dir):
            d.mkdir(parents=True, exist_ok=True)

        (theme_dir / "index.theme").write_text(
            "\n".join(
                [
                    "[Desktop Entry]",
                    "Type=X-GNOME-Metatheme",
                    "Name=Cinnamon Dynamic",
                    "Comment=Generated from wallpaper via wallust/wallpaperctl",
                    "Encoding=UTF-8",
                    "",
                    "[X-GNOME-Metatheme]",
                    "GtkTheme=cinnamon-dynamic",
                    "MetacityTheme=cinnamon-dynamic",
                    "IconTheme=Mint-Y",
                    "CursorTheme=Adwaita",
                    "ButtonLayout=menu:minimize,maximize,close",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        mapping = {
            "color0": color0,
            "color1": color1,
            "color2": color2,
            "color3": color3,
            "color4": color4,
            "color7": color7,
            "bg_rgb": bg_rgb,
            "accent_rgb": accent_rgb,
            "hover_rgb": hover_rgb,
            "color7_rgb": fg_rgb,
            "color4_rgb": accent_rgb,
        }

        cin_css = _render_template("cinnamon.css.tpl", mapping)
        if not cin_css:
            debug_op(self.name, "failed to render cinnamon.css template", ctx)
            return False
        (cin_dir / "cinnamon.css").write_text(cin_css, encoding="utf-8")

        gtk_css = _render_template("gtk.css.tpl", mapping)
        if gtk_css:
            (gtk_dir / "gtk.css").write_text(gtk_css, encoding="utf-8")
            (gtk320_dir / "gtk.css").write_text(gtk_css, encoding="utf-8")
        else:
            # Fallback minimal gtk.css if packaged template missing
            (gtk_dir / "gtk.css").write_text(
                _gtk_css_fallback(color0, color2, color4, color7, bg_rgb, accent_rgb, fg_rgb),
                encoding="utf-8",
            )

        _write_metacity_theme(
            meta_dir,
            bg=color0,
            fg=color7,
            accent=color4,
            hover=color2,
            color1=color1,
        )

        if not have("gsettings"):
            return True

        scaling = ctx.ops.wallpaper_scaling_cinnamon
        uri = ctx.path.resolve().as_uri()
        run(
            ["gsettings", "set", "org.cinnamon.desktop.background", "picture-uri", uri],
            timeout=10,
        )
        run(
            [
                "gsettings",
                "set",
                "org.cinnamon.desktop.background",
                "picture-options",
                scaling,
            ],
            timeout=10,
        )
        # Cinnamon shell + WM only — do not force GTK (notifications)
        run(["gsettings", "set", "org.cinnamon.theme", "name", "cinnamon-dynamic"], timeout=10)
        run(
            [
                "gsettings",
                "set",
                "org.cinnamon.desktop.wm.preferences",
                "theme",
                "cinnamon-dynamic",
            ],
            timeout=10,
        )

        _reload_cinnamon_theme(color0, ctx)
        _maybe_restart_cinnamon(ctx)

        debug_op(self.name, "dynamic cinnamon theme applied", ctx)
        return True


def _template_path(name: str) -> Path | None:
    here = Path(__file__).resolve().parent.parent / "data" / "cinnamon" / name
    if here.is_file():
        return here
    try:
        root = resources.files("wallpaperctl").joinpath("data", "cinnamon", name)
        if root.is_file():
            return Path(str(root))
    except Exception:
        pass
    return None


def _render_template(name: str, mapping: dict[str, str]) -> str:
    path = _template_path(name)
    if path is None:
        log.warning("Cinnamon template missing: %s", name)
        return ""
    text = path.read_text(encoding="utf-8")
    return Template(text).safe_substitute(mapping)


def _brightness_sum(hex_color: str) -> int:
    try:
        r, g, b = hex_to_rgb(hex_color)
        return r + g + b
    except ValueError:
        return 0


def _intermediate_theme(bg_hex: str) -> str:
    # Shell used 384 (= 128*3) as dark/light cutoff
    return "Mint-Y-Dark" if _brightness_sum(bg_hex) < 384 else "Mint-Y"


def _reload_cinnamon_theme(bg_hex: str, ctx: WallpaperContext) -> None:
    """Clear caches, toggle themes via intermediate Mint-Y, ReloadTheme."""
    for cache in (
        home() / ".cache" / "gtk-3.0",
        home() / ".cache" / "cinnamon",
        home() / ".local" / "share" / "cinnamon" / "theme-cache",
    ):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)

    intermediate = _intermediate_theme(bg_hex)
    debug_op(self_name := "cinnamon-theme", f"reload via intermediate {intermediate}", ctx)

    # WM + cinnamon only (leave GTK app theme alone)
    for schema, key in (
        ("org.cinnamon.desktop.wm.preferences", "theme"),
        ("org.cinnamon.theme", "name"),
    ):
        run(["gsettings", "set", schema, key, intermediate], timeout=5)

    if have("cinnamon-dbus-command"):
        run(["cinnamon-dbus-command", "ReloadTheme"], timeout=15)
    time.sleep(0.3)

    for schema, key in (
        ("org.cinnamon.desktop.wm.preferences", "theme"),
        ("org.cinnamon.theme", "name"),
    ):
        run(["gsettings", "set", schema, key, "cinnamon-dynamic"], timeout=5)

    if have("cinnamon-dbus-command"):
        run(["cinnamon-dbus-command", "ReloadTheme"], timeout=15)

    # Quiet nudge for settings daemon
    run(["pkill", "-HUP", "cinnamon-settings-daemon"], timeout=5)
    debug_op(self_name, "theme reload sequence completed", ctx)


def _maybe_restart_cinnamon(ctx: WallpaperContext) -> None:
    """Full Cinnamon restart only when RESTART_CINNAMON_AFTER_THEME=1."""
    if os.environ.get("RESTART_CINNAMON_AFTER_THEME") != "1":
        debug_op(
            "cinnamon-theme",
            "for immediate window decorations: "
            "RESTART_CINNAMON_AFTER_THEME=1 wallpaperctl … "
            "or: wallpaperctl reload-wm --restart",
            ctx,
        )
        return
    if have("cinnamon-dbus-command"):
        debug_op("cinnamon-theme", "RESTART_CINNAMON_AFTER_THEME=1 — restarting", ctx)
        run(["cinnamon-dbus-command", "RestartCinnamon", "true"], timeout=30)
    else:
        debug_op("cinnamon-theme", "cinnamon-dbus-command missing; cannot restart", ctx)


def _write_metacity_theme(
    meta_dir: Path,
    *,
    bg: str,
    fg: str,
    accent: str,
    hover: str,
    color1: str,
) -> None:
    """Prefer Mint-Y metacity assets + recolored XML; else minimal stub."""
    base = Path("/usr/share/themes/Mint-Y/metacity-1")
    if base.is_dir():
        for svg in base.glob("*.svg"):
            text = svg.read_text(encoding="utf-8", errors="replace")
            for old, key in _SVG_REPLACEMENTS:
                rep = {"accent": accent, "hover": hover, "bg": bg, "fg": fg}[key]
                text = re.sub(re.escape(old), f"#{rep}", text, flags=re.IGNORECASE)
            (meta_dir / svg.name).write_text(text, encoding="utf-8")
        thumb = base / "thumbnail.png"
        if thumb.is_file():
            shutil.copy2(thumb, meta_dir / "thumbnail.png")

        base_xml = base / "metacity-theme-3.xml"
        if base_xml.is_file():
            xml = base_xml.read_text(encoding="utf-8", errors="replace")
            for old in _MINT_METACITY_COLORS:
                xml = re.sub(re.escape(old), f"#{accent}", xml, flags=re.IGNORECASE)
            xml = re.sub(r"#000000", f"#{fg}", xml, flags=re.IGNORECASE)
            xml = re.sub(r"#333333", f"#{fg}", xml, flags=re.IGNORECASE)
            xml = xml.replace("Mint-Y", "cinnamon-dynamic")
            (meta_dir / "metacity-theme-3.xml").write_text(xml, encoding="utf-8")
            # Also theme-1 if present
            base1 = base / "metacity-theme-1.xml"
            if base1.is_file():
                x1 = base1.read_text(encoding="utf-8", errors="replace")
                for old in _MINT_METACITY_COLORS:
                    x1 = re.sub(re.escape(old), f"#{accent}", x1, flags=re.IGNORECASE)
                x1 = re.sub(r"#000000", f"#{fg}", x1, flags=re.IGNORECASE)
                x1 = x1.replace("Mint-Y", "cinnamon-dynamic")
                (meta_dir / "metacity-theme-1.xml").write_text(x1, encoding="utf-8")
            return

    (meta_dir / "metacity-theme-3.xml").write_text(
        _metacity_stub(bg, fg, accent, color1),
        encoding="utf-8",
    )


def _gtk_css_fallback(
    c0: str, c2: str, c4: str, c7: str, bg: str, accent: str, fg: str
) -> str:
    return f"""/* Fallback GTK3 dynamic theme — wallpaperctl */
@define-color theme_bg_color #{c0};
@define-color theme_fg_color #{c7};
@define-color theme_selected_bg_color #{c4};
@define-color theme_selected_fg_color #{c7};
window, .background {{
  background-color: rgba({bg}, 0.95);
  color: #{c7};
}}
button {{
  background-color: rgba({accent}, 0.3);
  color: #{c7};
  border-radius: 4px;
}}
button:hover {{ background-color: rgba({accent}, 0.5); }}
entry {{
  background-color: rgba({bg}, 0.8);
  color: #{c7};
  border: 1px solid #{c4};
}}
"""


def _metacity_stub(c0: str, c7: str, c4: str, c1: str = "c01c28") -> str:
    return f"""<?xml version="1.0"?>
<metacity_theme>
  <info>
    <name>cinnamon-dynamic</name>
    <author>wallpaperctl</author>
    <description>Dynamic metacity/muffin theme bg=#{c0} fg=#{c7} accent=#{c4}</description>
  </info>
  <frame_geometry name="normal" title_scale="medium"
                  rounded_top_left="true" rounded_top_right="true">
    <distance name="left_width" value="1"/>
    <distance name="right_width" value="1"/>
    <distance name="bottom_height" value="1"/>
    <distance name="left_titlebar_edge" value="0"/>
    <distance name="right_titlebar_edge" value="0"/>
    <distance name="button_width" value="20"/>
    <distance name="button_height" value="20"/>
    <border name="title_border" left="4" right="4" top="3" bottom="3"/>
    <border name="button_border" left="1" right="1" top="2" bottom="2"/>
  </frame_geometry>
  <draw_ops name="frame">
    <rectangle color="#{c0}" x="0" y="0" width="width" height="height" filled="true"/>
    <rectangle color="#{c4}" x="0" y="0" width="width" height="1" filled="true"/>
  </draw_ops>
  <draw_ops name="title_text">
    <title color="#{c7}" x="(0 `max` ((width - title_width) / 2))"
           y="((height - title_height) / 2)"/>
  </draw_ops>
  <frame style_set="normal" focus="yes" state="normal" resize="both" geometry="normal">
    <piece position="entire_background" draw_ops="frame"/>
    <piece position="title" draw_ops="title_text"/>
  </frame>
  <frame style_set="normal" focus="no" state="normal" resize="both" geometry="normal">
    <piece position="entire_background" draw_ops="frame"/>
    <piece position="title" draw_ops="title_text"/>
  </frame>
</metacity_theme>
"""
