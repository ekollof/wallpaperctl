#!/usr/bin/env python3
"""Generate an opencode theme from pywal/wallust colors.json."""

import json
import os
import sys
from pathlib import Path

WAL_COLORS_PATH = Path.home() / ".cache" / "wal" / "colors.json"
THEME_OUTPUT_PATH = Path.home() / ".config" / "opencode" / "themes" / "wallust.json"


def lighten(hex_color: str, factor: float = 0.15) -> str:
    """Lighten a hex color by mixing with white."""
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)
    return f"#{r:02x}{g:02x}{b:02x}"


def darken(hex_color: str, factor: float = 0.15) -> str:
    """Darken a hex color by mixing with black."""
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    r = int(r * (1 - factor))
    g = int(g * (1 - factor))
    b = int(b * (1 - factor))
    return f"#{r:02x}{g:02x}{b:02x}"


def generate_theme():
    if not WAL_COLORS_PATH.exists():
        print(f"Error: {WAL_COLORS_PATH} not found. Run pywal/wallust first.")
        sys.exit(1)

    with open(WAL_COLORS_PATH, "r") as f:
        wal = json.load(f)

    bg = wal["special"]["background"]
    fg = wal["special"]["foreground"]
    c = wal["colors"]

    # Generate a light-mode background by lightening the background significantly
    bg_light = lighten(bg, 0.88)
    fg_light = darken(fg, 0.60)

    # Panel / element backgrounds
    panel_dark = lighten(bg, 0.08)
    panel_light = darken(bg_light, 0.08)
    element_dark = lighten(bg, 0.12)
    element_light = darken(bg_light, 0.12)
    menu_dark = lighten(bg, 0.18)
    menu_light = darken(bg_light, 0.18)

    # Borders
    border_dark = lighten(bg, 0.25)
    border_light = darken(bg_light, 0.25)
    border_active_dark = c.get("color7", lighten(bg, 0.45))
    border_active_light = c.get("color7", darken(bg_light, 0.45))
    border_subtle_dark = lighten(bg, 0.15)
    border_subtle_light = darken(bg_light, 0.15)

    # Muted text
    text_muted_dark = c.get("color8", lighten(bg, 0.45))
    text_muted_light = c.get("color8", darken(bg_light, 0.45))

    theme = {
        "$schema": "https://opencode.ai/theme.json",
        "defs": {
            "wal_bg": bg,
            "wal_fg": fg,
            "wal_c0": c["color0"],
            "wal_c1": c["color1"],
            "wal_c2": c["color2"],
            "wal_c3": c["color3"],
            "wal_c4": c["color4"],
            "wal_c5": c["color5"],
            "wal_c6": c["color6"],
            "wal_c7": c["color7"],
            "wal_c8": c["color8"],
            "wal_c9": c["color9"],
            "wal_c10": c["color10"],
            "wal_c11": c["color11"],
            "wal_c12": c["color12"],
            "wal_c13": c["color13"],
            "wal_c14": c["color14"],
            "wal_c15": c["color15"],
            "wal_panel_dark": panel_dark,
            "wal_panel_light": panel_light,
            "wal_element_dark": element_dark,
            "wal_element_light": element_light,
            "wal_menu_dark": menu_dark,
            "wal_menu_light": menu_light,
            "wal_border_dark": border_dark,
            "wal_border_light": border_light,
            "wal_text_muted_dark": text_muted_dark,
            "wal_text_muted_light": text_muted_light,
            "wal_bg_light": bg_light,
            "wal_fg_light": fg_light,
        },
        "theme": {
            "primary": {"dark": "wal_c4", "light": "wal_c12"},
            "secondary": {"dark": "wal_c6", "light": "wal_c14"},
            "accent": {"dark": "wal_c5", "light": "wal_c13"},
            "error": {"dark": "wal_c1", "light": "wal_c9"},
            "warning": {"dark": "wal_c3", "light": "wal_c11"},
            "success": {"dark": "wal_c2", "light": "wal_c10"},
            "info": {"dark": "wal_c6", "light": "wal_c14"},
            "text": {"dark": "wal_fg", "light": "wal_fg_light"},
            "textMuted": {"dark": "wal_text_muted_dark", "light": "wal_text_muted_light"},
            "selectedListItemText": {"dark": "wal_fg", "light": "wal_fg_light"},
            "background": {"dark": "wal_bg", "light": "wal_bg_light"},
            "backgroundPanel": {"dark": "wal_panel_dark", "light": "wal_panel_light"},
            "backgroundElement": {"dark": "wal_element_dark", "light": "wal_element_light"},
            "backgroundMenu": {"dark": "wal_menu_dark", "light": "wal_menu_light"},
            "border": {"dark": "wal_border_dark", "light": "wal_border_light"},
            "borderActive": {"dark": "wal_c7", "light": "wal_c7"},
            "borderSubtle": {"dark": "wal_border_dark", "light": "wal_border_light"},
            "diffAdded": {"dark": "wal_c2", "light": "wal_c10"},
            "diffRemoved": {"dark": "wal_c1", "light": "wal_c9"},
            "diffContext": {"dark": "wal_c8", "light": "wal_c8"},
            "diffHunkHeader": {"dark": "wal_c8", "light": "wal_c8"},
            "diffHighlightAdded": {"dark": "wal_c10", "light": "wal_c2"},
            "diffHighlightRemoved": {"dark": "wal_c9", "light": "wal_c1"},
            "diffAddedBg": {"dark": "wal_panel_dark", "light": "wal_panel_light"},
            "diffRemovedBg": {"dark": "wal_panel_dark", "light": "wal_panel_light"},
            "diffContextBg": {"dark": "wal_bg", "light": "wal_bg_light"},
            "diffLineNumber": {"dark": "wal_c8", "light": "wal_c8"},
            "diffAddedLineNumberBg": {"dark": "wal_panel_dark", "light": "wal_panel_light"},
            "diffRemovedLineNumberBg": {"dark": "wal_panel_dark", "light": "wal_panel_light"},
            "markdownText": {"dark": "wal_fg", "light": "wal_fg_light"},
            "markdownHeading": {"dark": "wal_c4", "light": "wal_c12"},
            "markdownLink": {"dark": "wal_c6", "light": "wal_c14"},
            "markdownLinkText": {"dark": "wal_c14", "light": "wal_c6"},
            "markdownCode": {"dark": "wal_c2", "light": "wal_c10"},
            "markdownBlockQuote": {"dark": "wal_c3", "light": "wal_c11"},
            "markdownEmph": {"dark": "wal_c5", "light": "wal_c13"},
            "markdownStrong": {"dark": "wal_c7", "light": "wal_c15"},
            "markdownHorizontalRule": {"dark": "wal_c8", "light": "wal_c8"},
            "markdownListItem": {"dark": "wal_c4", "light": "wal_c12"},
            "markdownListEnumeration": {"dark": "wal_c6", "light": "wal_c14"},
            "markdownImage": {"dark": "wal_c4", "light": "wal_c12"},
            "markdownImageText": {"dark": "wal_c6", "light": "wal_c14"},
            "markdownCodeBlock": {"dark": "wal_fg", "light": "wal_fg_light"},
            "syntaxComment": {"dark": "wal_c8", "light": "wal_c8"},
            "syntaxKeyword": {"dark": "wal_c1", "light": "wal_c9"},
            "syntaxFunction": {"dark": "wal_c4", "light": "wal_c12"},
            "syntaxVariable": {"dark": "wal_c5", "light": "wal_c13"},
            "syntaxString": {"dark": "wal_c2", "light": "wal_c10"},
            "syntaxNumber": {"dark": "wal_c3", "light": "wal_c11"},
            "syntaxType": {"dark": "wal_c6", "light": "wal_c14"},
            "syntaxOperator": {"dark": "wal_c7", "light": "wal_c15"},
            "syntaxPunctuation": {"dark": "wal_fg", "light": "wal_fg_light"},
            "thinkingOpacity": 0.5,
        },
    }

    THEME_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(THEME_OUTPUT_PATH, "w") as f:
        json.dump(theme, f, indent=2)

    print(f"Theme written to {THEME_OUTPUT_PATH}")


def set_tui_theme():
    TUI_PATH = Path.home() / ".config" / "opencode" / "tui.json"
    TUI_PATH.parent.mkdir(parents=True, exist_ok=True)

    tui = {}
    if TUI_PATH.exists():
        try:
            with open(TUI_PATH, "r") as f:
                tui = json.load(f)
        except (json.JSONDecodeError, OSError):
            tui = {}

    tui["$schema"] = "https://opencode.ai/tui.json"
    tui["theme"] = "wallust"

    with open(TUI_PATH, "w") as f:
        json.dump(tui, f, indent=2)

    print(f"Set theme 'wallust' in {TUI_PATH}")


if __name__ == "__main__":
    generate_theme()
    set_tui_theme()
