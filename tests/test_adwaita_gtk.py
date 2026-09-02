"""Adwaita tint: Omarchy-style palette-driven GTK without a vendored theme."""

from __future__ import annotations

from pathlib import Path

from wallpaperctl.config import OpsConfig
from wallpaperctl.context import WallpaperContext
from wallpaperctl.detect.desktop import DesktopEnvironment
from wallpaperctl.theme import adwaita
from wallpaperctl.theme.adwaita import (
    MARKER,
    build_adwaita_css,
    write_adwaita_css,
)
from wallpaperctl.theme.gtk_theme import GtkThemeOp

COLORS = {
    "special": {"background": "#080F14", "foreground": "#C7D2B1"},
    "colors": {
        "color0": "#0A1217",
        "color1": "#3E544E",
        "color2": "#387464",
        "color3": "#63805E",
        "color4": "#45885D",
        "color5": "#5A9880",
        "color6": "#93A858",
        "color7": "#C7D2B1",
        "color8": "#20272B",
        "color9": "#3E544E",
        "color10": "#387464",
        "color11": "#63805E",
        "color12": "#45885D",
        "color13": "#5A9880",
        "color14": "#93A858",
        "color15": "#C7D2B1",
    },
}


def test_build_adwaita_css_tints_named_colors() -> None:
    gtk4_css, gtk3_css = build_adwaita_css(COLORS)
    assert MARKER in gtk4_css
    assert MARKER in gtk3_css
    # Surfaces follow the wallpaper background
    assert "@define-color window_bg_color #080f14;" in gtk4_css
    assert "@define-color view_fg_color #c7d2b1;" in gtk4_css
    # Accent resolved through the palette strategy (warmest → color6 here)
    assert "@define-color accent_color #93a858;" in gtk4_css
    assert "@define-color accent_bg_color #93a858;" in gtk4_css
    # GTK3 side overrides the Adwaita theme_* aliases
    assert "@define-color theme_bg_color #080f14;" in gtk3_css
    assert "@define-color theme_selected_bg_color #93a858;" in gtk3_css
    # Headerbar softened toward the background (Omarchy-style soft chrome)
    assert "@define-color headerbar_bg_color" in gtk4_css


def test_write_adwaita_css_backs_up_unmarked_files_once(tmp_path: Path) -> None:
    gtk4 = tmp_path / "gtk-4.0" / "gtk.css"
    gtk4.parent.mkdir(parents=True)
    user_css = "/* my rules */"
    gtk4.write_text(user_css, encoding="utf-8")

    gtk4_css, gtk3_css = build_adwaita_css(COLORS)
    written = write_adwaita_css(gtk4_css, gtk3_css, base_dir=tmp_path)
    assert [p.name for p in written] == ["gtk.css", "gtk.css"]

    backup = gtk4.parent / "gtk.css.pre-wallpaperctl"
    assert backup.read_text(encoding="utf-8") == user_css
    assert MARKER in gtk4.read_text(encoding="utf-8")

    # Second run: marked file is rewritten, backup untouched
    write_adwaita_css(gtk4_css, gtk3_css, base_dir=tmp_path)
    assert backup.read_text(encoding="utf-8") == user_css


def _op_ctx() -> WallpaperContext:
    return WallpaperContext(
        path=Path("/tmp/wall.jpg"),
        de=DesktopEnvironment(),
        ops=OpsConfig(),
        debug=True,
    )


def test_standalone_op_applies_adwaita_tint(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "wallpaperctl.theme.gtk_theme.load_colors_json", lambda: COLORS
    )
    monkeypatch.setattr(adwaita, "home", lambda: tmp_path)
    op = GtkThemeOp()
    gsets: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        op, "_gset", lambda schema, key, value: gsets.append((schema, key, value))
    )
    reloaded = []
    monkeypatch.setattr(
        op, "_reload_gtk", lambda ctx: reloaded.append(ctx) or True
    )

    assert op.run(_op_ctx()) is True
    gtk4 = tmp_path / ".config" / "gtk-4.0" / "gtk.css"
    gtk3 = tmp_path / ".config" / "gtk-3.0" / "gtk.css"
    assert MARKER in gtk4.read_text(encoding="utf-8")
    assert MARKER in gtk3.read_text(encoding="utf-8")
    assert ("org.gnome.desktop.interface", "gtk-theme", "Adwaita-dark") in gsets
    assert len(reloaded) == 1


def test_standalone_op_falls_back_when_tint_disabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("wallpaperctl.theme.gtk_theme.have", lambda cmd: True)
    op = GtkThemeOp()
    ctx = _op_ctx()
    ctx.ops.gtk_adwaita_tint = False
    tinted = []
    monkeypatch.setattr(op, "_adwaita_tint", lambda c: tinted.append(c) or True)
    monkeypatch.setattr(op, "_gget", lambda schema, key: "")
    monkeypatch.setattr(op, "_gset", lambda schema, key, value: None)
    monkeypatch.setattr(op, "_reload_gtk", lambda c: True)

    assert op.run(ctx) is True
    assert tinted == []
