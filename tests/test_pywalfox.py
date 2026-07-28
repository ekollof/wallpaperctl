"""Pywalfox contrast boosting for browser UI."""

from __future__ import annotations

from wallpaperctl.theme.pywalfox import (
    _contrast_ratio,
    improve_browser_contrast,
)


def test_improve_raises_muddy_mid_tones() -> None:
    data = {
        "wallpaper": "/tmp/w.jpg",
        "special": {"background": "#0A0A0A", "foreground": "#3A3A3A", "cursor": "#3A3A3A"},
        "colors": {
            f"color{i}": c
            for i, c in enumerate(
                [
                    "#0A0A0A",
                    "#1A1A1A",  # muddy — too close to bg
                    "#2A2020",
                    "#202A20",
                    "#20202A",
                    "#2A2A1A",
                    "#1A2A2A",
                    "#4A4A4A",  # weak fg
                    "#0A0A0A",
                    "#3A2020",
                    "#203A20",
                    "#20203A",
                    "#3A3A20",
                    "#203A3A",
                    "#3A203A",
                    "#5A5A5A",
                ]
            )
        },
    }
    out = improve_browser_contrast(data, text_min=7.0, icon_min=4.5, control_min=4.5)
    bg = out["special"]["background"]
    fg = out["special"]["foreground"]
    assert _contrast_ratio(fg, bg) >= 7.0
    assert _contrast_ratio(out["colors"]["color7"], bg) >= 7.0
    assert _contrast_ratio(out["colors"]["color1"], bg) >= 4.5
    assert out["colors"]["color1"].upper() != "#1A1A1A"


def test_improve_lifts_borderline_icons() -> None:
    data = {
        "wallpaper": "/x",
        "special": {"background": "#030F0C", "foreground": "#D9DFE0", "cursor": "#D9DFE0"},
        "colors": {f"color{i}": "#D9DFE0" if i >= 7 else "#030F0C" for i in range(16)},
    }
    data["colors"]["color1"] = "#2A5258"  # ~3.7:1 — looks muddy in Firefox chrome
    data["colors"]["color4"] = "#AB4B33"
    out = improve_browser_contrast(data)
    bg = "#030F0C"
    assert _contrast_ratio(out["colors"]["color1"], bg) >= 4.5
    assert out["colors"]["color1"].upper() != "#2A5258"
