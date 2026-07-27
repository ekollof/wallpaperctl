"""CLI wiring for manage / -m."""

from __future__ import annotations

from unittest.mock import patch

from wallpaperctl.cli import main


def test_classic_m_flag_launches_tui() -> None:
    with patch("wallpaperctl.tui.run_manage_tui", return_value=0) as run:
        # Import path used by classic_main
        with patch("wallpaperctl.cli.run_manage_tui", run, create=True):
            # classic imports inside if args.m
            pass
    with patch("wallpaperctl.tui.run_manage_tui", return_value=42) as mock:
        code = main(["-m"])
    assert code == 42
    mock.assert_called_once()


def test_manage_subcommand() -> None:
    with patch("wallpaperctl.tui.run_manage_tui", return_value=0) as mock:
        code = main(["manage", "/tmp", "--no-kitty"])
    assert code == 0
    mock.assert_called_once_with(
        directory="/tmp",
        no_kitty=True,
        warm_cache=False,
        warm_only=False,
    )


def test_manage_warm_only() -> None:
    with patch("wallpaperctl.tui.run_manage_tui", return_value=0) as mock:
        code = main(["manage", "--warm-only"])
    assert code == 0
    mock.assert_called_once_with(
        directory=None,
        no_kitty=False,
        warm_cache=False,
        warm_only=True,
    )
