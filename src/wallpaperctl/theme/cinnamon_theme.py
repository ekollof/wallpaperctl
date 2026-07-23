"""Cinnamon dynamic glass CSS + WM theme from wallust colors."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

from wallpaperctl.context import WallpaperContext
from wallpaperctl.theme.base import debug_op
from wallpaperctl.util import have, hex_to_rgb, home, read_wal_colors, run

log = logging.getLogger("wallpaperctl")


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
        color2 = strip(colors[2])
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
        meta_dir = theme_dir / "metacity-1"
        cin_dir.mkdir(parents=True, exist_ok=True)
        gtk_dir.mkdir(parents=True, exist_ok=True)
        meta_dir.mkdir(parents=True, exist_ok=True)

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

        css = _cinnamon_css(color0, color2, color4, color7, bg_rgb, accent_rgb, hover_rgb, fg_rgb)
        (cin_dir / "cinnamon.css").write_text(css, encoding="utf-8")
        (gtk_dir / "gtk.css").write_text(
            _gtk_css(color0, color2, color4, color7, bg_rgb, accent_rgb, fg_rgb),
            encoding="utf-8",
        )
        (meta_dir / "metacity-theme-3.xml").write_text(
            _metacity_stub(color0, color7, color4),
            encoding="utf-8",
        )

        if not have("gsettings"):
            return True

        # Apply theme settings
        scaling = ctx.ops.wallpaper_scaling_cinnamon
        uri = ctx.path.resolve().as_uri()
        run(["gsettings", "set", "org.cinnamon.desktop.background", "picture-uri", uri], timeout=10)
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
        run(
            [
                "gsettings",
                "set",
                "org.cinnamon.desktop.interface",
                "gtk-theme",
                "cinnamon-dynamic",
            ],
            timeout=10,
        )
        run(
            ["gsettings", "set", "org.gnome.desktop.interface", "gtk-theme", "cinnamon-dynamic"],
            timeout=10,
        )

        # Cache clear + toggle reload
        for cache in (home() / ".cache" / "gtk-3.0", home() / ".cache" / "cinnamon"):
            if cache.is_dir():
                import shutil

                shutil.rmtree(cache, ignore_errors=True)

        for schema, key in (
            ("org.cinnamon.desktop.wm.preferences", "theme"),
            ("org.cinnamon.desktop.interface", "gtk-theme"),
            ("org.cinnamon.theme", "name"),
        ):
            run(["gsettings", "set", schema, key, "Mint-Y"], timeout=5)
        time.sleep(0.3)
        for schema, key in (
            ("org.cinnamon.desktop.wm.preferences", "theme"),
            ("org.cinnamon.desktop.interface", "gtk-theme"),
            ("org.cinnamon.theme", "name"),
        ):
            run(["gsettings", "set", schema, key, "cinnamon-dynamic"], timeout=5)

        debug_op(self.name, "dynamic cinnamon theme applied", ctx)
        return True


def _cinnamon_css(
    c0: str, c2: str, c4: str, c7: str, bg: str, accent: str, hover: str, fg: str
) -> str:
    return f"""/* Dynamic Cinnamon theme — wallpaperctl */
/* Generated {datetime.now().isoformat(timespec="seconds")} */
/* Colors: bg=#{c0}, fg=#{c7}, accent=#{c4}, hover=#{c2} */

@import url("resource:///org/cinnamon/theme/cinnamon.css");

stage {{
    color: #{c7};
}}

#panel {{
    font-weight: bold;
    height: 40px;
    width: 32px;
    color: #{c7};
    background-gradient-direction: vertical;
    background-gradient-start: rgba({bg}, 1.0);
    background-gradient-end: rgba({accent}, 0.8);
}}

#panel:highlight {{
    border-image: none;
    background-color: rgba({accent}, 0.8);
}}

#panelLeft, #panelCenter {{
    spacing: 4px;
}}

.popup-menu-content {{
    padding: 6px;
    background-color: #{c0};
    border-radius: 16px;
    border: 1px solid rgba({accent}, 0.5);
    box-shadow: 0 0 6px rgba(0, 0, 0, 0.5);
}}

.popup-menu-item {{
    font-weight: normal;
    spacing: 6px;
    transition-duration: 100ms;
    padding: 8px 12px;
    margin: 0 4px;
    border-radius: 8px;
    color: #{c7};
    background-color: transparent;
}}

.popup-menu-item:active {{
    background-color: rgba({accent}, 0.3);
    color: #{c7};
}}

.popup-menu-item:insensitive {{
    color: rgba({fg}, 0.4);
    background: none;
}}

.popup-menu-arrow, .popup-menu-icon {{
    icon-size: 16px;
    color: #{c7};
}}

.popup-sub-menu {{
    border-radius: 9px;
    margin: 0 4px 6px 4px;
    border: 1px solid rgba(0, 0, 0, 0.1);
}}

.popup-sub-menu .popup-menu-item {{
    border-radius: 0;
    background-color: rgba({bg}, 0.8);
    margin: 0;
    padding: 8px 0 8px 12px;
}}

.popup-sub-menu .popup-menu-item:active {{
    background-color: rgba({accent}, 0.2);
}}

.popup-separator-menu-item {{
    -gradient-height: 1px;
    -gradient-start: rgba({accent}, 0.3);
    -gradient-end: rgba({accent}, 0.3);
    height: 1px;
}}

.menu {{
    min-width: 15em;
    color: #{c7};
    padding: 6px;
}}

.menu-favorites-box {{
    padding: 9px;
    background-color: rgba({bg}, 0.6);
    border: 1px solid rgba(0, 0, 0, 0.1);
    border-radius: 8px;
}}

.menu-favorites-button:hover {{
    background-color: rgba({accent}, 0.25);
    border-radius: 8px;
}}

.menu-categories-box {{
    padding: 9px;
}}

.menu-category-button-selected, .menu-application-button-selected {{
    background-color: rgba({accent}, 0.35);
    color: #{c7};
    border-radius: 8px;
}}

.menu-selected-app-title {{
    font-weight: bold;
    color: #{c7};
}}

.menu-selected-app-description {{
    max-width: 150px;
    color: rgba({fg}, 0.7);
}}

.menu-search-entry {{
    padding: 6px 10px;
    border-radius: 8px;
    color: #{c7};
    border: 1px solid rgba({accent}, 0.4);
    background-color: rgba({bg}, 0.9);
    selected-color: #{c7};
    caret-color: #{c4};
    selection-background-color: rgba({accent}, 0.4);
}}

.window-list-item-box {{
    color: #{c7};
    background-color: transparent;
    border-radius: 6px;
    transition-duration: 100ms;
}}

.window-list-item-box:hover {{
    background-color: rgba({hover}, 0.25);
}}

.window-list-item-box:active, .window-list-item-box:checked, .window-list-item-box:focus {{
    background-color: rgba({accent}, 0.4);
}}

.sound-player {{
    padding: 0;
    background-color: #{c0};
}}

.notification-banner {{
    font-size: 1em;
    color: #{c7};
    border: 1px solid rgba({accent}, 0.4);
    border-radius: 12px;
    background-color: rgba({bg}, 0.95);
    padding: 10px;
}}

.notification-banner .notification-button {{
    border-radius: 6px;
    padding: 4px 8px;
}}

.notification-banner .notification-button:hover {{
    background-color: rgba({accent}, 0.3);
}}

.switcher-list {{
    background-color: rgba({bg}, 0.95);
    border: 1px solid rgba({accent}, 0.4);
    border-radius: 12px;
    color: #{c7};
}}

.switcher-list .item-box:selected {{
    background-color: rgba({accent}, 0.35);
    border-radius: 8px;
}}

.expo-workspaces-name-entry {{
    color: #{c7};
    background-color: rgba({bg}, 0.9);
    border: 1px solid rgba({accent}, 0.4);
    border-radius: 6px;
}}

.workspace-thumbnails {{
    color: #{c7};
}}

.workspace-add-button {{
    background-color: rgba({accent}, 0.3);
    border-radius: 8px;
}}

.calendar {{
    padding: 6px;
    color: #{c7};
}}

.calendar-day-base {{
    border-radius: 6px;
}}

.calendar-today {{
    background-color: rgba({accent}, 0.45);
    border-radius: 6px;
    font-weight: bold;
}}

.calendar-selected-date {{
    background-color: rgba({hover}, 0.35);
}}

.slider {{
    height: 1em;
    min-width: 15em;
    -slider-height: 0.3em;
    -slider-background-color: rgba({fg}, 0.2);
    -slider-border-color: transparent;
    -slider-active-background-color: #{c4};
    -slider-active-border-color: transparent;
    -slider-border-width: 1px;
    -slider-handle-radius: 0.5em;
}}

.separator {{
    -margin-horizontal: 1em;
    -gradient-height: 1px;
    -gradient-start: rgba({accent}, 0.3);
    -gradient-end: rgba({accent}, 0.3);
}}
"""


def _gtk_css(c0: str, c2: str, c4: str, c7: str, bg: str, accent: str, fg: str) -> str:
    return f"""/* cinnamon-dynamic GTK3 — wallpaperctl */
@define-color theme_bg_color #{c0};
@define-color theme_fg_color #{c7};
@define-color theme_selected_bg_color #{c4};
@define-color theme_selected_fg_color #{c7};
@define-color borders rgba({accent}, 0.4);

* {{
    color: #{c7};
    background-color: #{c0};
}}

window, .background {{
    background-color: #{c0};
    color: #{c7};
}}

button {{
    background-color: rgba({accent}, 0.25);
    border: 1px solid rgba({accent}, 0.45);
    border-radius: 6px;
    color: #{c7};
    padding: 4px 10px;
}}

button:hover {{
    background-color: rgba({accent}, 0.4);
}}

button:active, button:checked {{
    background-color: #{c4};
    color: #{c7};
}}

entry {{
    background-color: rgba({bg}, 0.9);
    border: 1px solid rgba({accent}, 0.4);
    border-radius: 6px;
    color: #{c7};
    caret-color: #{c4};
}}

entry:focus {{
    border-color: #{c4};
}}

headerbar {{
    background-color: rgba({bg}, 1.0);
    color: #{c7};
    border-bottom: 1px solid rgba({accent}, 0.3);
}}

notebook > header tab:checked {{
    background-color: rgba({accent}, 0.3);
    color: #{c7};
}}

scrollbar slider {{
    background-color: rgba({accent}, 0.45);
    border-radius: 4px;
}}

selection {{
    background-color: rgba({accent}, 0.45);
    color: #{c7};
}}

menuitem:hover {{
    background-color: rgba({accent}, 0.3);
}}

switch:checked {{
    background-color: #{c4};
}}

progressbar progress {{
    background-color: #{c4};
}}

/* accent from wallust hover green for links */
link, a {{
    color: #{c2};
}}
"""


def _metacity_stub(c0: str, c7: str, c4: str) -> str:
    return f"""<?xml version="1.0"?>
<metacity_theme>
  <info>
    <name>cinnamon-dynamic</name>
    <author>wallpaperctl</author>
    <copyright>Generated</copyright>
    <date>{datetime.now().date()}</date>
    <description>Dynamic metacity/muffin theme bg=#{c0} fg=#{c7} accent=#{c4}</description>
  </info>
  <frame_geometry name="normal" title_scale="medium" rounded_top_left="true" rounded_top_right="true">
    <distance name="left_width" value="1"/>
    <distance name="right_width" value="1"/>
    <distance name="bottom_height" value="1"/>
    <distance name="left_titlebar_edge" value="4"/>
    <distance name="right_titlebar_edge" value="4"/>
    <distance name="button_width" value="20"/>
    <distance name="button_height" value="20"/>
    <distance name="title_vertical_pad" value="4"/>
    <border name="title_border" left="3" right="3" top="2" bottom="2"/>
    <border name="button_border" left="1" right="1" top="2" bottom="2"/>
  </frame_geometry>
  <draw_ops name="titlebar_fill">
    <rectangle color="#{c0}" x="0" y="0" width="width" height="height" filled="true"/>
  </draw_ops>
  <draw_ops name="title_text">
    <title color="#{c7}" x="(0 `max` ((width - title_width) / 2))" y="((height - title_height) / 2)"/>
  </draw_ops>
  <frame style_set="normal" focus="yes" state="normal" resize="both" geometry="normal">
    <piece position="entire_background" draw_ops="titlebar_fill"/>
    <piece position="title" draw_ops="title_text"/>
  </frame>
  <frame style_set="normal" focus="no" state="normal" resize="both" geometry="normal">
    <piece position="entire_background" draw_ops="titlebar_fill"/>
    <piece position="title" draw_ops="title_text"/>
  </frame>
</metacity_theme>
"""
