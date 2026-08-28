"""NotificationsOp: never hijack an existing notification daemon."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from wallpaperctl.config import OpsConfig
from wallpaperctl.context import WallpaperContext
from wallpaperctl.detect.desktop import DesktopEnvironment
from wallpaperctl.theme.notifications import NotificationsOp


def _ctx() -> WallpaperContext:
    return WallpaperContext(
        path=Path("/tmp/wall.jpg"),
        de=DesktopEnvironment(),
        ops=OpsConfig(),
        debug=True,
    )


def test_skips_when_foreign_daemon_owns_bus() -> None:
    """qtile/GNOME/xfce4-notifyd own the name: touch nothing."""
    op = NotificationsOp()
    with (
        patch(
            "wallpaperctl.theme.notifications.name_has_owner", return_value=True
        ),
        patch(
            "wallpaperctl.theme.notifications.pgrep_exact", return_value=False
        ) as pgrep,
        patch("wallpaperctl.theme.notifications.have", return_value=True),
        patch(
            "wallpaperctl.theme.notifications.spawn_detached"
        ) as spawn,
        patch("wallpaperctl.theme.notifications.run") as run,
    ):
        assert op.run(_ctx()) is True
    assert pgrep.call_args_list[0].args[0] == "dunst"
    spawn.assert_not_called()
    run.assert_not_called()


def test_reloads_dunst_when_dunst_is_the_daemon() -> None:
    op = NotificationsOp()
    with (
        patch(
            "wallpaperctl.theme.notifications.name_has_owner", return_value=True
        ),
        patch(
            "wallpaperctl.theme.notifications.pgrep_exact",
            side_effect=lambda name: name == "dunst",
        ),
        patch(
            "wallpaperctl.theme.notifications.have",
            side_effect=lambda cmd: cmd in ("dunst", "dunstctl"),
        ),
        patch(
            "wallpaperctl.theme.notifications.run",
            return_value=type("Result", (), {"returncode": 0})(),
        ) as run,
        patch("wallpaperctl.theme.notifications.spawn_detached") as spawn,
    ):
        assert op.run(_ctx()) is True
    run.assert_called_once()
    assert run.call_args.args[0][:2] == ["dunstctl", "reload"]
    spawn.assert_not_called()


def test_starts_dunst_when_no_daemon() -> None:
    op = NotificationsOp()
    with (
        patch(
            "wallpaperctl.theme.notifications.name_has_owner", return_value=False
        ),
        patch(
            "wallpaperctl.theme.notifications.have",
            side_effect=lambda cmd: cmd == "dunst",
        ),
        patch("wallpaperctl.theme.notifications.run"),
        patch(
            "wallpaperctl.theme.notifications.time.sleep"
        ),
        patch("wallpaperctl.theme.notifications.spawn_detached") as spawn,
    ):
        assert op.run(_ctx()) is True
    spawn.assert_called_once_with(["dunst"])
