"""Cinnamon theme: no forced GTK; templates render; metacity/reload paths."""

from __future__ import annotations

import subprocess
from pathlib import Path

from wallpaperctl.config import OpsConfig
from wallpaperctl.context import WallpaperContext
from wallpaperctl.detect.desktop import DesktopEnvironment
from wallpaperctl.theme import cinnamon_theme as ct
from wallpaperctl.theme.cinnamon_theme import CinnamonThemeOp


def test_cinnamon_theme_does_not_set_gtk_theme(tmp_path: Path, monkeypatch) -> None:
    img = tmp_path / "wall.jpg"
    img.write_bytes(b"x")
    (tmp_path / ".themes").mkdir()

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(list(cmd), 0, "", "")

    monkeypatch.setattr(ct, "home", lambda: tmp_path)
    monkeypatch.setattr(
        ct,
        "read_wal_colors",
        lambda *a, **k: [f"#{i:02x}{i:02x}{i:02x}" for i in range(8, 16)],
    )
    monkeypatch.setattr(ct, "have", lambda c: c == "gsettings")
    monkeypatch.setattr(ct, "run", fake_run)
    monkeypatch.setattr(ct.time, "sleep", lambda s: None)
    monkeypatch.setenv("RESTART_CINNAMON_AFTER_THEME", "0")

    ctx = WallpaperContext(
        path=img,
        de=DesktopEnvironment(cinnamon=True),
        ops=OpsConfig(),
    )
    assert CinnamonThemeOp().run(ctx) is True

    # Templates should have been written
    css = tmp_path / ".themes" / "cinnamon-dynamic" / "cinnamon" / "cinnamon.css"
    assert css.is_file()
    text = css.read_text(encoding="utf-8")
    assert "cinnamon-dynamic" in text or "#panel" in text or "stage" in text
    assert len(text) > 2000  # full shell-port template, not the old stub

    gsettings_sets = [c for c in calls if c[:2] == ["gsettings", "set"]]
    gtk_sets = [c for c in gsettings_sets if len(c) >= 4 and c[3] == "gtk-theme"]
    assert gtk_sets == [], f"unexpected GTK theme sets: {gtk_sets}"

    schemas_keys = {(c[2], c[3]) for c in gsettings_sets if len(c) >= 4}
    assert ("org.cinnamon.theme", "name") in schemas_keys
    assert ("org.cinnamon.desktop.wm.preferences", "theme") in schemas_keys
    assert ("org.cinnamon.desktop.interface", "gtk-theme") not in schemas_keys
    assert ("org.gnome.desktop.interface", "gtk-theme") not in schemas_keys


def test_intermediate_theme_brightness() -> None:
    assert ct._intermediate_theme("000000") == "Mint-Y-Dark"
    assert ct._intermediate_theme("ffffff") == "Mint-Y"


def test_render_cinnamon_template_has_selectors() -> None:
    css = ct._render_template(
        "cinnamon.css.tpl",
        {
            "color0": "111111",
            "color1": "ff0000",
            "color2": "222222",
            "color3": "333333",
            "color4": "444444",
            "color7": "eeeeee",
            "bg_rgb": "17,17,17",
            "accent_rgb": "68,68,68",
            "hover_rgb": "34,34,34",
            "color7_rgb": "238,238,238",
            "color4_rgb": "68,68,68",
        },
    )
    assert css
    for sel in (".tooltip", ".workspace-button", "#notification", ".menu-application-button"):
        assert sel in css


def test_restart_env_triggers_dbus(tmp_path: Path, monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(list(cmd), 0, "", "")

    monkeypatch.setattr(ct, "have", lambda c: c == "cinnamon-dbus-command")
    monkeypatch.setattr(ct, "run", fake_run)
    monkeypatch.setenv("RESTART_CINNAMON_AFTER_THEME", "1")
    ctx = WallpaperContext(
        path=tmp_path / "w.jpg",
        de=DesktopEnvironment(cinnamon=True),
        ops=OpsConfig(),
        debug=True,
    )
    ct._maybe_restart_cinnamon(ctx)
    assert any("RestartCinnamon" in c for c in calls)
