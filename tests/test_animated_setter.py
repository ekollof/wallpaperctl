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


def _fake_process(pid: int) -> object:
    return type("Process", (), {"pid": pid, "poll": lambda self: None})()


def test_mpvpaper_uses_all_outputs_and_ipc_socket(tmp_path: Path) -> None:
    setter = AnimatedSetter()
    ctx = _ctx(tmp_path, wayland=True)
    fake = _fake_process(1234)
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
    assert args[args.index("--layer") + 1] == "background"
    mpv_options = args[args.index("--mpv-options") + 1]
    assert "input-ipc-server=" in mpv_options
    assert "panscan=0" in mpv_options
    assert "background=color" in mpv_options
    assert "background-color=#000000" in mpv_options


def test_mpvpaper_supports_plasma_wayland() -> None:
    assert AnimatedSetter._wayland_supported(
        WallpaperContext(Path("wall.mp4"), DesktopEnvironment(plasma=True), OpsConfig())
    )
    assert not AnimatedSetter._wayland_supported(
        WallpaperContext(Path("wall.mp4"), DesktopEnvironment(noctalia=True), OpsConfig())
    )


def test_plasma_mpvpaper_uses_bottom_layer(tmp_path: Path) -> None:
    setter = AnimatedSetter()
    ctx = WallpaperContext(
        tmp_path / "wall.mp4", DesktopEnvironment(plasma=True), OpsConfig()
    )
    ctx.path.write_bytes(b"video")
    fake = _fake_process(1234)
    with (
        patch("wallpaperctl.set.animated.have", return_value=True),
        patch("wallpaperctl.set.animated.subprocess.Popen", return_value=fake) as popen,
        patch.object(setter, "_stop_previous"),
        patch("wallpaperctl.set.plasma.jeepney_available", return_value=False),
    ):
        assert setter.set_wallpaper(ctx)
    args = popen.call_args.args[0]
    assert args[args.index("--layer") + 1] == "bottom"


def test_x11_uses_xwinwrap_and_mpv(tmp_path: Path) -> None:
    setter = AnimatedSetter()
    ctx = _ctx(tmp_path, wayland=False)
    fake = _fake_process(1234)
    with (
        patch.dict(os.environ, {"DISPLAY": ":0", "WAYLAND_DISPLAY": ""}, clear=False),
        patch("wallpaperctl.set.animated.have", return_value=True),
        patch("wallpaperctl.set.animated.subprocess.Popen", return_value=fake) as popen,
        patch.object(setter, "_stop_previous"),
        patch.object(setter, "_x11_geometry_args", return_value=[["-g", "1920x1080+0+0"]]),
    ):
        assert setter.set_wallpaper(ctx)
    args = popen.call_args.args[0]
    assert args[:2] == ["xwinwrap", "-b"]
    assert "-ni" in args
    assert args[args.index("--") + 1] == "mpv"
    assert "%WID" in args
    assert "--panscan=0" in args
    assert "--background=color" in args


def test_x11_starts_one_wrapper_per_output(tmp_path: Path) -> None:
    setter = AnimatedSetter()
    ctx = _ctx(tmp_path, wayland=False)
    processes = [_fake_process(pid) for pid in (1001, 1002, 1003)]
    with (
        patch.dict(os.environ, {"DISPLAY": ":0", "WAYLAND_DISPLAY": ""}, clear=False),
        patch("wallpaperctl.set.animated.have", return_value=True),
        patch("wallpaperctl.set.animated.subprocess.Popen", side_effect=processes) as popen,
        patch.object(setter, "_stop_previous"),
        patch.object(
            setter,
            "_x11_geometry_args",
            return_value=[["-g", g] for g in (
                "1920x1080+0+0",
                "2560x1080+1920+0",
                "1920x1080+4480+0",
            )],
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
        patch.object(setter, "_socket", Path("/nonexistent/wallpaperctl.sock")),
        patch(
            "wallpaperctl.set.animated.run",
            return_value=type("Result", (), {"returncode": 0, "stdout": "2001\n"})(),
        ),
        patch.object(setter, "_terminate") as terminate,
    ):
        setter._stop_previous()
    assert call(2001) in terminate.call_args_list


def test_cleanup_discovers_untracked_mpvpaper() -> None:
    setter = AnimatedSetter()
    with (
        patch("wallpaperctl.set.animated.have", return_value=True),
        patch.object(setter, "_socket", Path("/nonexistent/wallpaperctl.sock")),
        patch(
            "wallpaperctl.set.animated.run",
            side_effect=[
                type("Result", (), {"returncode": 1, "stdout": ""})(),
                type("Result", (), {"returncode": 0, "stdout": "3001\n3002\n"})(),
            ],
        ),
        patch.object(setter, "_terminate") as terminate,
    ):
        setter._stop_previous()
    assert call(3001) in terminate.call_args_list
    assert call(3002) in terminate.call_args_list
