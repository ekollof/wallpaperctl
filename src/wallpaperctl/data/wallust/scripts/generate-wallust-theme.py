#!/usr/bin/env python3
"""Generate an opencode theme from pywal/wallust colors.json."""

import json
import sys
from pathlib import Path

WAL_COLORS_PATH = Path.home() / ".cache" / "wal" / "colors.json"
THEME_OUTPUT_PATH = Path.home() / ".config" / "opencode" / "themes" / "wallust.json"
TUI_PATH = Path.home() / ".config" / "opencode" / "tui.json"
OPENCODE_PLUGIN_SPEC = "./plugins/wallust-hot-reload.ts"
OPENCODE_PLUGIN_PATH = Path.home() / ".config" / "opencode" / "plugins" / "wallust-hot-reload.ts"


def _write_json(path: Path, data: object) -> None:
    """Atomically write JSON so OpenCode's theme watcher sees a complete file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    tmp.replace(path)


def plugin_spec_listed(tui: dict, spec: str = OPENCODE_PLUGIN_SPEC) -> bool:
    plugins = tui.get("plugin")
    if not isinstance(plugins, list):
        return False
    for entry in plugins:
        if entry == spec:
            return True
        if isinstance(entry, list) and entry and entry[0] == spec:
            return True
    return False


def ensure_plugin_spec(tui: dict, spec: str = OPENCODE_PLUGIN_SPEC) -> bool:
    """Add *spec* to tui.json plugin list. Returns True if modified."""
    plugins = tui.get("plugin")
    if not isinstance(plugins, list):
        tui["plugin"] = [spec]
        return True
    if plugin_spec_listed(tui, spec):
        return False
    plugins.append(spec)
    return True


def lighten(hex_color: str, factor: float = 0.15) -> str:
    """Lighten a hex color by mixing with white."""
    return mix(hex_color, (255, 255, 255), factor)


def darken(hex_color: str, factor: float = 0.15) -> str:
    """Darken a hex color by mixing with black."""
    return mix(hex_color, (0, 0, 0), factor)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def mix(hex_color: str, target: tuple[int, int, int], factor: float) -> str:
    """Mix a hex color toward *target* by *factor* (0..1)."""
    r, g, b = _hex_to_rgb(hex_color)
    tr, tg, tb = target
    return _rgb_to_hex(
        round(r + (tr - r) * factor),
        round(g + (tg - g) * factor),
        round(b + (tb - b) * factor),
    )


def _channel_lin(value: int) -> float:
    v = value / 255
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def _relative_luminance(hex_color: str) -> float:
    r, g, b = _hex_to_rgb(hex_color)
    return 0.2126 * _channel_lin(r) + 0.7152 * _channel_lin(g) + 0.0722 * _channel_lin(b)


def contrast_ratio(a: str, b: str) -> float:
    """WCAG contrast ratio between two hex colors (1..21)."""
    la = _relative_luminance(a)
    lb = _relative_luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def ensure_contrast(
    hex_color: str, against: str, min_ratio: float = 4.5, prefer: str = "lighten"
) -> str:
    """Return hex_color adjusted until it has >= min_ratio contrast vs against.

    wallust's "bright black" (color8) frequently ends up nearly identical to
    the background on dark wallpapers, which renders muted text (sidebar
    labels, comments, diff context) invisible. Mixing toward white (dark
    surfaces) or black (light surfaces) preserves the hue while restoring
    legibility.
    """
    target = (255, 255, 255) if prefer == "lighten" else (0, 0, 0)
    color = hex_color
    for step in range(1, 13):
        if contrast_ratio(color, against) >= min_ratio:
            return color
        color = mix(hex_color, target, min(0.08 * step, 0.96))
    return color


def generate_theme():
    if not WAL_COLORS_PATH.exists():
        print(f"Error: {WAL_COLORS_PATH} not found. Run pywal/wallust first.")
        sys.exit(1)

    with open(WAL_COLORS_PATH) as f:
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

    # Muted text / comments: guarantee legibility on the surfaces they are
    # rendered on instead of trusting color8 blindly.
    muted_dark = c.get("color8") or lighten(bg, 0.45)
    muted_light = c.get("color8") or darken(bg_light, 0.45)
    text_muted_dark = ensure_contrast(muted_dark, panel_dark, 4.5, "lighten")
    text_muted_light = ensure_contrast(muted_light, panel_light, 4.5, "darken")
    comment_dark = ensure_contrast(muted_dark, bg, 4.5, "lighten")
    comment_light = ensure_contrast(muted_light, bg_light, 4.5, "darken")

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
            "wal_comment_dark": comment_dark,
            "wal_comment_light": comment_light,
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
            "diffContext": {"dark": "wal_comment_dark", "light": "wal_comment_light"},
            "diffHunkHeader": {"dark": "wal_comment_dark", "light": "wal_comment_light"},
            "diffHighlightAdded": {"dark": "wal_c10", "light": "wal_c2"},
            "diffHighlightRemoved": {"dark": "wal_c9", "light": "wal_c1"},
            "diffAddedBg": {"dark": "wal_panel_dark", "light": "wal_panel_light"},
            "diffRemovedBg": {"dark": "wal_panel_dark", "light": "wal_panel_light"},
            "diffContextBg": {"dark": "wal_bg", "light": "wal_bg_light"},
            "diffLineNumber": {"dark": "wal_comment_dark", "light": "wal_comment_light"},
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
            "markdownHorizontalRule": {"dark": "wal_comment_dark", "light": "wal_comment_light"},
            "markdownListItem": {"dark": "wal_c4", "light": "wal_c12"},
            "markdownListEnumeration": {"dark": "wal_c6", "light": "wal_c14"},
            "markdownImage": {"dark": "wal_c4", "light": "wal_c12"},
            "markdownImageText": {"dark": "wal_c6", "light": "wal_c14"},
            "markdownCodeBlock": {"dark": "wal_fg", "light": "wal_fg_light"},
            "syntaxComment": {"dark": "wal_comment_dark", "light": "wal_comment_light"},
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

    _write_json(THEME_OUTPUT_PATH, theme)
    print(f"Theme written to {THEME_OUTPUT_PATH}")


def set_tui_theme():
    tui = {}
    if TUI_PATH.exists():
        try:
            with open(TUI_PATH) as f:
                tui = json.load(f)
        except (json.JSONDecodeError, OSError):
            tui = {}

    tui["$schema"] = "https://opencode.ai/tui.json"
    tui["theme"] = "wallust"
    if OPENCODE_PLUGIN_PATH.is_file():
        ensure_plugin_spec(tui)

    _write_json(TUI_PATH, tui)
    print(f"Set theme 'wallust' in {TUI_PATH}")


if __name__ == "__main__":
    generate_theme()
    set_tui_theme()
