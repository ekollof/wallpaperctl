from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import call, patch

from wallpaperctl.config import OpsConfig
from wallpaperctl.context import WallpaperContext
from wallpaperctl.detect.desktop import DesktopEnvironment
from wallpaperctl.set.animated import AnimatedSetter


def _ctx(tmp_path: Path, *, wayland: bool) -> WallpaperContext:
    video = tmp_path / "wall.mp4"
    video.write_bytes(b"video")
    if wayland:
        de = DesktopEnvironment(hyprland=True)
    else:
        de = DesktopEnvironment(awesome=True)
    return WallpaperContext(video, de, OpsConfig())


def test_mpvpaper_uses_all_outputs_and_ipc_socket(tmp_path: Path) -> None:
    setter = AnimatedSetter()
    ctx = _ctx(tmp_path, wayland=True)
    fake = type("Process", (), {"pid": 1234, "poll": lambda self: None})()
    with (
        patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-1"}, clear=False),
        patch("wallpaperctl.set.animated.have", return_value=True),
        patch("wallpaperctl.set.animated.subprocess.Popen", return_value=fake) as popen,
        patch.object(setter, "_stop_previous"),
    ):
        assert setter.set_wallpaper(ctx)
    args = popen.call_args.args[0]
    assert args[0] == "mpvpaper"
    assert "ALL" in args
    assert "input-ipc-server=" in args[args.index("--mpv-options") + 1]


def test_x11_uses_xwinwrap_and_mpv(tmp_path: Path) -> None:
    setter = AnimatedSetter()
    ctx = _ctx(tmp_path, wayland=False)
    fake = type("Process", (), {"pid": 1234, "poll": lambda self: None})()
    with (
        patch.dict(os.environ, {"DISPLAY": ":0", "WAYLAND_DISPLAY": ""}, clear=False),
        patch("wallpaperctl.set.animated.have", return_value=True),
        patch("wallpaperctl.set.animated.subprocess.Popen", return_value=fake) as popen,
        patch.object(setter, "_stop_previous"),
        patch.object(setter, "_x11_geometries", return_value=["1920x1080+0+0"]),
    ):
        assert setter.set_wallpaper(ctx)
    args = popen.call_args.args[0]
    assert args[:2] == ["xwinwrap", "-b"]
    assert "-ni" in args
    assert args[args.index("--") + 1] == "mpv"
    assert "%WID" in args


def test_x11_starts_one_wrapper_per_output(tmp_path: Path) -> None:
    setter = AnimatedSetter()
    ctx = _ctx(tmp_path, wayland=False)
    processes = [
        type("Process", (), {"pid": pid, "poll": lambda self: None})()
        for pid in (1001, 1002, 1003)
    ]
    with (
        patch.dict(os.environ, {"DISPLAY": ":0", "WAYLAND_DISPLAY": ""}, clear=False),
        patch("wallpaperctl.set.animated.have", return_value=True),
        patch("wallpaperctl.set.animated.subprocess.Popen", side_effect=processes) as popen,
        patch.object(setter, "_stop_previous"),
        patch.object(
            setter,
            "_x11_geometries",
            return_value=["1920x1080+0+0", "2560x1080+1920+0", "1920x1080+4480+0"],
        ),
    ):
        assert setter.set_wallpaper(ctx)
    assert popen.call_count == 3
    assert [call.args[0][call.args[0].index("-g") + 1] for call in popen.call_args_list] == [
        "1920x1080+0+0",
        "2560x1080+1920+0",
        "1920x1080+4480+0",
    ]


def test_static_cleanup_discovers_untracked_xwinwrap() -> None:
    setter = AnimatedSetter()
    with (
        patch("wallpaperctl.set.animated.have", return_value=True),
        patch(
            "wallpaperctl.set.animated.run",
            return_value=type("Result", (), {"returncode": 0, "stdout": "2001\n"})(),
        ),
        patch.object(setter, "_terminate") as terminate,
    ):
        setter._stop_previous()
    assert call(2001) in terminate.call_args_list
