"""Apply pipeline hard-fail behavior."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from wallpaperctl.app import apply_wallpaper
from wallpaperctl.config import OpsConfig
from wallpaperctl.detect.desktop import DesktopEnvironment


def _ops(tmp_path: Path) -> OpsConfig:
    ops = OpsConfig()
    ops.current_wallpaper_file = str(tmp_path / ".wallpaper")
    ops.wallpaper_dir = str(tmp_path)
    return ops


def test_apply_wallpaper_hard_fails_when_no_setter_succeeds(tmp_path: Path) -> None:
    img = tmp_path / "w.jpg"
    img.write_bytes(b"fake")
    ops = _ops(tmp_path)
    de = DesktopEnvironment(hyprland=True)

    with (
        patch("wallpaperctl.app.detect_desktop", return_value=de),
        patch("wallpaperctl.app.run_wallpaper_setters", return_value=(0, 1)),
        patch("wallpaperctl.app.run_theme_ops") as theme,
        patch("wallpaperctl.app.safe_notify"),
    ):
        ok = apply_wallpaper(img, ops)
    assert ok is False
    theme.assert_not_called()


def test_apply_wallpaper_hard_fails_when_no_setter_applies(tmp_path: Path) -> None:
    img = tmp_path / "w.jpg"
    img.write_bytes(b"fake")
    ops = _ops(tmp_path)
    de = DesktopEnvironment()

    with (
        patch("wallpaperctl.app.detect_desktop", return_value=de),
        patch("wallpaperctl.app.run_wallpaper_setters", return_value=(0, 0)),
        patch("wallpaperctl.app.run_theme_ops") as theme,
        patch("wallpaperctl.app.safe_notify"),
    ):
        ok = apply_wallpaper(img, ops)
    assert ok is False
    theme.assert_not_called()


def test_apply_wallpaper_runs_theme_ops_after_successful_set(tmp_path: Path) -> None:
    img = tmp_path / "w.jpg"
    img.write_bytes(b"fake")
    ops = _ops(tmp_path)
    de = DesktopEnvironment(xfce=True)

    with (
        patch("wallpaperctl.app.detect_desktop", return_value=de),
        patch("wallpaperctl.app.run_wallpaper_setters", return_value=(1, 1)),
        patch("wallpaperctl.app.run_theme_ops", return_value=(0, 3)) as theme,
        patch("wallpaperctl.app.safe_notify"),
    ):
        ok = apply_wallpaper(img, ops)
    assert ok is True
    theme.assert_called_once()
