"""GTK_THEME environment pin maintenance and portal dark-mode nudging."""

from __future__ import annotations

from pathlib import Path

from wallpaperctl.config import OpsConfig
from wallpaperctl.context import WallpaperContext
from wallpaperctl.detect.desktop import DesktopEnvironment
from wallpaperctl.theme.gtk_theme import GtkThemeOp


def _ctx(**de_kwargs) -> WallpaperContext:
    return WallpaperContext(
        path=Path("/tmp/wall.jpg"),
        de=DesktopEnvironment(**de_kwargs),
        ops=OpsConfig(),
        debug=True,
    )


def _write_env(home: Path, theme: str) -> Path:
    conf = home / ".config" / "environment.d" / "gtk-theme.conf"
    conf.parent.mkdir(parents=True, exist_ok=True)
    conf.write_text(
        "# LibAdwaita apps use GTK3 themes via GTK_THEME environment variable\n"
        f"GTK_THEME={theme}\n",
        encoding="utf-8",
    )
    return conf


def test_env_pin_repaired_to_adwaita_when_tint_enabled(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("wallpaperctl.theme.gtk_theme.home", lambda: tmp_path)
    conf = _write_env(tmp_path, "FlatColor-dark")
    op = GtkThemeOp()
    op._ensure_gtk_theme_env(_ctx())
    assert "GTK_THEME=Adwaita-dark" in conf.read_text(encoding="utf-8")


def test_env_pin_repairs_missing_theme_to_existing_fallback(
    tmp_path: Path, monkeypatch
):
    """FlatColor-dark pinned but gone, standalone default also gone → Adwaita."""
    monkeypatch.setattr("wallpaperctl.theme.gtk_theme.home", lambda: tmp_path)
    conf = _write_env(tmp_path, "FlatColor-dark")
    ctx = _ctx()  # standalone, tint disabled
    ctx.ops.gtk_adwaita_tint = False
    op = GtkThemeOp()
    monkeypatch.setattr(
        op, "_theme_exists", lambda theme: theme == "Adwaita-dark"
    )
    op._ensure_gtk_theme_env(ctx)
    assert "GTK_THEME=Adwaita-dark" in conf.read_text(encoding="utf-8")


def test_env_pin_keeps_existing_dark_theme_when_tint_disabled(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr("wallpaperctl.theme.gtk_theme.home", lambda: tmp_path)
    conf = _write_env(tmp_path, "FlatColor-dark")
    ctx = _ctx()
    ctx.ops.gtk_adwaita_tint = False
    op = GtkThemeOp()
    monkeypatch.setattr(op, "_theme_exists", lambda theme: True)
    op._ensure_gtk_theme_env(ctx)
    assert "GTK_THEME=FlatColor-dark" in conf.read_text(encoding="utf-8")


def test_env_pin_keeps_breeze_on_plasma(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("wallpaperctl.theme.gtk_theme.home", lambda: tmp_path)
    conf = _write_env(tmp_path, "Breeze-Dark")
    op = GtkThemeOp()
    op._ensure_gtk_theme_env(_ctx(plasma=True))
    assert "GTK_THEME=Breeze-Dark" in conf.read_text(encoding="utf-8")


def test_reload_gtk_toggles_scheme_when_already_dark(tmp_path: Path, monkeypatch):
    """Same-value gsettings writes emit nothing; Chromium needs a real change."""
    monkeypatch.setattr("wallpaperctl.theme.gtk_theme.home", lambda: tmp_path)
    monkeypatch.setattr("wallpaperctl.theme.gtk_theme.time.sleep", lambda s: None)
    op = GtkThemeOp()
    writes: list[tuple[str, str]] = []
    monkeypatch.setattr(
        op,
        "_gget",
        lambda schema, key: "Adwaita-dark" if key == "gtk-theme" else "prefer-dark",
    )
    monkeypatch.setattr(
        op,
        "_gset",
        lambda schema, key, value: writes.append((key, value)),
    )
    for name in (
        "_ensure_settings_ini",
        "_ensure_gtk_theme_env",
        "_reload_kde_gtkconfig",
        "_ensure_portal",
        "_emit_portal_signal",
        "_update_xsettingsd",
    ):
        monkeypatch.setattr(op, name, lambda *a, **k: None)

    assert op._reload_gtk(_ctx()) is True
    scheme_writes = [v for k, v in writes if k == "color-scheme"]
    assert scheme_writes == ["default", "prefer-dark"]


def test_xsettingsd_left_alone_on_plasma(tmp_path: Path, monkeypatch):
    """Plasma's kded gtkconfig owns the GTK sync; we never rewrite/spawn."""
    monkeypatch.setattr("wallpaperctl.theme.gtk_theme.home", lambda: tmp_path)
    conf = tmp_path / "xsettingsd.conf"
    conf.write_text('Net/ThemeName "Breeze-Dark"\n', encoding="utf-8")
    spawned = []
    monkeypatch.setattr(
        "wallpaperctl.theme.gtk_theme.pgrep_exact", lambda name: False
    )
    monkeypatch.setattr(
        "wallpaperctl.theme.gtk_theme.run", lambda *a, **k: spawned.append(a)
    )
    monkeypatch.setattr(
        "wallpaperctl.theme.gtk_theme.spawn_detached",
        lambda args: spawned.append(args),
    )
    op = GtkThemeOp()
    op._update_xsettingsd("Breeze-Dark", _ctx(plasma=True))
    assert spawned == []
    assert conf.read_text(encoding="utf-8") == 'Net/ThemeName "Breeze-Dark"\n'
