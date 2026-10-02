"""Async theme ops: background by default, --sync for debugging."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

from wallpaperctl.app import (
    _run_theme_locked,
    _wants_sync,
    apply_wallpaper,
    run_theme_worker,
    theme_worker_argv,
)
from wallpaperctl.config import OpsConfig
from wallpaperctl.detect.desktop import DesktopEnvironment


def _ops(tmp_path: Path) -> OpsConfig:
    ops = OpsConfig()
    ops.current_wallpaper_file = str(tmp_path / ".wallpaper")
    ops.wallpaper_dir = str(tmp_path)
    return ops


def _img(tmp_path: Path) -> Path:
    img = tmp_path / "w.jpg"
    img.write_bytes(b"fake")
    return img


def test_background_theme_defaults_on() -> None:
    assert OpsConfig().background_theme is True


def test_wants_sync_explicit_flag_wins(tmp_path: Path) -> None:
    ops = _ops(tmp_path)
    assert _wants_sync(True, ops) is True


def test_wants_sync_env_forces_sync(tmp_path: Path, monkeypatch) -> None:
    ops = _ops(tmp_path)
    monkeypatch.setenv("WALLPAPERCTL_SYNC", "1")
    assert _wants_sync(False, ops) is True


def test_wants_sync_config_disables_background(tmp_path: Path, monkeypatch) -> None:
    ops = _ops(tmp_path)
    ops.background_theme = False
    monkeypatch.delenv("WALLPAPERCTL_SYNC", raising=False)
    assert _wants_sync(False, ops) is True


def test_wants_sync_default_is_background(tmp_path: Path, monkeypatch) -> None:
    ops = _ops(tmp_path)
    monkeypatch.delenv("WALLPAPERCTL_SYNC", raising=False)
    assert _wants_sync(False, ops) is False


def test_apply_wallpaper_backgrounds_theme_by_default(tmp_path: Path) -> None:
    img = _img(tmp_path)
    ops = _ops(tmp_path)
    de = DesktopEnvironment(xfce=True)
    with (
        patch("wallpaperctl.app.detect_desktop", return_value=de),
        patch("wallpaperctl.app.run_wallpaper_setters", return_value=(1, 1)),
        patch("wallpaperctl.app.run_theme_ops") as theme,
        patch("wallpaperctl.app.spawn_theme_background", return_value=True) as spawn,
        patch("wallpaperctl.app.safe_notify"),
    ):
        ok = apply_wallpaper(img, ops)
    assert ok is True
    theme.assert_not_called()
    spawn.assert_called_once()


def test_apply_wallpaper_sync_runs_theme_inline(tmp_path: Path) -> None:
    img = _img(tmp_path)
    ops = _ops(tmp_path)
    de = DesktopEnvironment(xfce=True)
    with (
        patch("wallpaperctl.app.detect_desktop", return_value=de),
        patch("wallpaperctl.app.run_wallpaper_setters", return_value=(1, 1)),
        patch("wallpaperctl.app.run_theme_ops", return_value=(0, 2)) as theme,
        patch("wallpaperctl.app.spawn_theme_background") as spawn,
        patch("wallpaperctl.app.safe_notify"),
    ):
        ok = apply_wallpaper(img, ops, sync=True)
    assert ok is True
    theme.assert_called_once()
    spawn.assert_not_called()


def test_apply_wallpaper_falls_back_to_sync_when_spawn_fails(
    tmp_path: Path,
) -> None:
    img = _img(tmp_path)
    ops = _ops(tmp_path)
    de = DesktopEnvironment(xfce=True)
    with (
        patch("wallpaperctl.app.detect_desktop", return_value=de),
        patch("wallpaperctl.app.run_wallpaper_setters", return_value=(1, 1)),
        patch("wallpaperctl.app.run_theme_ops", return_value=(0, 2)) as theme,
        patch("wallpaperctl.app.spawn_theme_background", return_value=False),
        patch("wallpaperctl.app.safe_notify"),
    ):
        ok = apply_wallpaper(img, ops)
    assert ok is True
    theme.assert_called_once()


def test_theme_worker_argv_shape(tmp_path: Path) -> None:
    img = _img(tmp_path)
    argv = theme_worker_argv(img, photographer_name="a", debug=True)
    assert argv[:4] == [sys.executable, "-m", "wallpaperctl", "__theme__"]
    assert str(img) in argv
    assert "--photographer-name" in argv
    assert "--debug" in argv


def test_theme_worker_skips_stale_wallpaper(tmp_path: Path) -> None:
    old = _img(tmp_path)
    ops = _ops(tmp_path)
    newer = tmp_path / "new.jpg"
    newer.write_bytes(b"new")
    ops.current_wallpaper_file = str(tmp_path / ".wallpaper")
    Path(ops.current_wallpaper_file).write_text(str(newer.resolve()) + "\n")
    de = DesktopEnvironment()
    with (
        patch("wallpaperctl.app.detect_desktop", return_value=de),
        patch("wallpaperctl.app.run_theme_ops") as theme,
    ):
        rc = run_theme_worker(old, ops)
    assert rc == 0
    theme.assert_not_called()


def test_theme_worker_runs_current_wallpaper(tmp_path: Path) -> None:
    img = _img(tmp_path)
    ops = _ops(tmp_path)
    Path(ops.current_wallpaper_file).write_text(str(img.resolve()) + "\n")
    de = DesktopEnvironment()
    with (
        patch("wallpaperctl.app.detect_desktop", return_value=de),
        patch("wallpaperctl.app.run_theme_ops", return_value=(0, 1)) as theme,
        patch("wallpaperctl.app.safe_notify"),
    ):
        rc = run_theme_worker(img, ops)
    assert rc == 0
    theme.assert_called_once()


def test_cli_classic_sync_flag(tmp_path: Path, monkeypatch) -> None:
    from wallpaperctl import cli as cli_mod

    img = _img(tmp_path)
    ops = _ops(tmp_path)
    seen: dict = {}
    monkeypatch.setattr(cli_mod, "load_ops_config", lambda: ops)
    monkeypatch.setattr(cli_mod.WallpaperLock, "acquire", lambda self: None)
    monkeypatch.setattr(cli_mod.WallpaperLock, "release", lambda self: None)
    monkeypatch.setattr(
        cli_mod, "pick_random_wallpaper", lambda _ops, animated_only=False: img
    )
    monkeypatch.setattr(cli_mod, "save_current_wallpaper", lambda *a, **k: None)

    def fake_apply(path, _ops, **kw):
        seen.update(kw)
        return True

    monkeypatch.setattr(cli_mod, "apply_wallpaper", fake_apply)
    assert cli_mod.main(["--sync", str(img)]) == 0
    assert seen.get("sync") is True


def test_cli_set_sync_flag(monkeypatch, tmp_path: Path) -> None:
    from wallpaperctl import cli as cli_mod

    img = _img(tmp_path)
    ops = _ops(tmp_path)
    seen: dict = {}
    monkeypatch.setattr(cli_mod, "load_ops_config", lambda: ops)
    monkeypatch.setattr(cli_mod.WallpaperLock, "acquire", lambda self: None)
    monkeypatch.setattr(cli_mod.WallpaperLock, "release", lambda self: None)
    monkeypatch.setattr(cli_mod, "save_current_wallpaper", lambda *a, **k: None)

    def fake_apply(path, _ops, **kw):
        seen.update(kw)
        return True

    monkeypatch.setattr(cli_mod, "apply_wallpaper", fake_apply)
    assert cli_mod.main(["set", "--sync", str(img)]) == 0
    assert seen.get("sync") is True
    seen.clear()
    assert cli_mod.main(["set", str(img)]) == 0
    assert seen.get("sync") is False


class _FakeThemeLock:
    """Captures the lock name; controllable hold result."""

    instances: list = []
    hold_result: bool = True

    def __init__(self, name: str = "wallpaper") -> None:
        self.name = name
        _FakeThemeLock.instances.append(self)

    def acquire_waiting(self, timeout=0.0, poll=0.0, abort_if=None) -> bool:
        return _FakeThemeLock.hold_result

    def release(self) -> None:
        pass


def _ctx_for(img):
    from wallpaperctl.context import WallpaperContext

    return WallpaperContext(
        path=img,
        de=DesktopEnvironment(),
        ops=_ops(img.parent),
    )


def test_run_theme_locked_uses_theme_lock(tmp_path: Path, monkeypatch) -> None:
    from wallpaperctl import app as app_mod

    _FakeThemeLock.instances.clear()
    _FakeThemeLock.hold_result = True
    monkeypatch.setattr(app_mod, "WallpaperLock", _FakeThemeLock)
    img = _img(tmp_path)
    ctx = _ctx_for(img)
    with patch("wallpaperctl.app.run_theme_ops", return_value=(0, 2)) as theme:
        assert _run_theme_locked(ctx, abort_on_superseded=False) == (0, 2)
    theme.assert_called_once()
    assert _FakeThemeLock.instances
    assert all(lock.name == "wallpaper-theme" for lock in _FakeThemeLock.instances)


def test_run_theme_locked_skips_stale_without_running(
    tmp_path: Path, monkeypatch
) -> None:
    from wallpaperctl import app as app_mod

    _FakeThemeLock.instances.clear()
    _FakeThemeLock.hold_result = True
    monkeypatch.setattr(app_mod, "WallpaperLock", _FakeThemeLock)
    old = _img(tmp_path)
    ops = _ops(tmp_path)
    newer = tmp_path / "new.jpg"
    newer.write_bytes(b"new")
    Path(ops.current_wallpaper_file).write_text(str(newer.resolve()) + "\n")
    ctx = _ctx_for(old)
    ctx.ops = ops
    with patch("wallpaperctl.app.run_theme_ops") as theme:
        assert _run_theme_locked(ctx, abort_on_superseded=True) == (0, 0)
    theme.assert_not_called()


def test_run_theme_locked_runs_anyway_when_lock_busy(
    tmp_path: Path, monkeypatch
) -> None:
    from wallpaperctl import app as app_mod

    _FakeThemeLock.instances.clear()
    _FakeThemeLock.hold_result = False
    monkeypatch.setattr(app_mod, "WallpaperLock", _FakeThemeLock)
    img = _img(tmp_path)
    Path(_ops(tmp_path).current_wallpaper_file).write_text(
        str(img.resolve()) + "\n"
    )
    ops = _ops(tmp_path)
    ctx = _ctx_for(img)
    ctx.ops = ops
    with patch("wallpaperctl.app.run_theme_ops", return_value=(0, 1)) as theme:
        assert _run_theme_locked(ctx, abort_on_superseded=True) == (0, 1)
    theme.assert_called_once()


def test_sync_apply_holds_theme_lock(tmp_path: Path, monkeypatch) -> None:
    from wallpaperctl import app as app_mod

    _FakeThemeLock.instances.clear()
    _FakeThemeLock.hold_result = True
    monkeypatch.setattr(app_mod, "WallpaperLock", _FakeThemeLock)
    img = _img(tmp_path)
    ops = _ops(tmp_path)
    de = DesktopEnvironment(xfce=True)
    with (
        patch("wallpaperctl.app.detect_desktop", return_value=de),
        patch("wallpaperctl.app.run_wallpaper_setters", return_value=(1, 1)),
        patch("wallpaperctl.app.run_theme_ops", return_value=(0, 1)),
        patch("wallpaperctl.app.safe_notify"),
    ):
        assert apply_wallpaper(img, ops, sync=True) is True
    assert _FakeThemeLock.instances
    assert all(lock.name == "wallpaper-theme" for lock in _FakeThemeLock.instances)


def test_worker_superseded_mid_run_reports_nothing(tmp_path: Path) -> None:
    img = _img(tmp_path)
    ops = _ops(tmp_path)
    Path(ops.current_wallpaper_file).write_text(str(img.resolve()) + "\n")
    de = DesktopEnvironment()

    def _flip_and_ok(ctx, abort_if=None):
        newer = tmp_path / "newer.jpg"
        newer.write_bytes(b"new")
        Path(ops.current_wallpaper_file).write_text(str(newer.resolve()) + "\n")
        return (0, 1)

    with (
        patch("wallpaperctl.app.detect_desktop", return_value=de),
        patch("wallpaperctl.app.run_theme_ops", side_effect=_flip_and_ok),
        patch("wallpaperctl.app.safe_notify") as notify,
    ):
        assert run_theme_worker(img, ops) == 0
    notify.assert_not_called()
