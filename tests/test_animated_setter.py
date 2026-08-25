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
        patch("wallpaperctl.set.animated._STARTUP_GRACE", 0),
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
        patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}, clear=False),
        patch("wallpaperctl.set.animated.have", return_value=True),
        patch("wallpaperctl.set.animated.subprocess.Popen", return_value=fake) as popen,
        patch("wallpaperctl.set.animated._STARTUP_GRACE", 0),
        patch.object(setter, "_stop_previous"),
        patch("wallpaperctl.set.plasma.jeepney_available", return_value=False),
    ):
        assert setter.set_wallpaper(ctx)
    args = popen.call_args.args[0]
    assert args[args.index("--layer") + 1] == "bottom"


def test_x11_uses_xwinwrap_and_mpv(tmp_path: Path) -> None:
    setter = AnimatedSetter()
    ctx = _ctx(tmp_path, wayland=False)
    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"jpg")
    ctx.static_path = frame
    fake = _fake_process(1234)
    with (
        patch.dict(os.environ, {"DISPLAY": ":0", "WAYLAND_DISPLAY": ""}, clear=False),
        patch("wallpaperctl.set.animated.have", return_value=True),
        patch("wallpaperctl.set.animated.subprocess.Popen", return_value=fake) as popen,
        patch("wallpaperctl.set.animated._STARTUP_GRACE", 0),
        patch.object(setter, "_stop_previous"),
        patch.object(setter, "_set_static_underlay", return_value=True) as underlay,
        patch.object(setter, "_prefer_root_pixmap_animation", return_value=False),
        patch.object(setter, "_x11_geometry_args", return_value=[["-g", "1920x1080+0+0"]]),
    ):
        assert setter.set_wallpaper(ctx)
    underlay.assert_called_once_with(ctx)
    args = popen.call_args.args[0]
    assert args[0] == "xwinwrap"
    assert "-ni" in args
    assert "-b" in args
    assert args[args.index("--") + 1] == "mpv"
    assert "--wid=%WID" in args
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
        patch("wallpaperctl.set.animated._STARTUP_GRACE", 0),
        patch.object(setter, "_stop_previous"),
        patch.object(setter, "_set_static_underlay", return_value=True),
        patch.object(setter, "_prefer_root_pixmap_animation", return_value=False),
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
    miss = type("Result", (), {"returncode": 1, "stdout": ""})()
    hit = type("Result", (), {"returncode": 0, "stdout": "3001\n3002\n"})()
    with (
        patch("wallpaperctl.set.animated.have", return_value=True),
        patch.object(setter, "_socket", Path("/nonexistent/wallpaperctl.sock")),
        patch(
            "wallpaperctl.set.animated.run",
            # One result per _STALE_PROCESS_PATTERNS entry (xwinwrap, mpvpaper, …)
            side_effect=[miss, hit, miss, miss],
        ),
        patch.object(setter, "_terminate") as terminate,
    ):
        setter._stop_previous()
    assert call(3001) in terminate.call_args_list
    assert call(3002) in terminate.call_args_list


def test_startup_exit_fails_mpvpaper_and_cleans_up(tmp_path: Path) -> None:
    setter = AnimatedSetter()
    ctx = _ctx(tmp_path, wayland=True)
    dead = type("Process", (), {"pid": 1234, "returncode": 3,
                                "poll": lambda self: 1})()
    with (
        patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-1"}, clear=False),
        patch("wallpaperctl.set.animated.have", return_value=True),
        patch("wallpaperctl.set.animated.subprocess.Popen", return_value=dead),
        patch("wallpaperctl.set.animated._STARTUP_GRACE", 0),
        patch.object(setter, "_stop_previous"),
    ):
        assert not setter.set_wallpaper(ctx)


def test_startup_exit_fails_xwinwrap(tmp_path: Path) -> None:
    setter = AnimatedSetter()
    ctx = _ctx(tmp_path, wayland=False)
    dead = type("Process", (), {"pid": 1234, "returncode": 2,
                                "poll": lambda self: 2})()
    with (
        patch.dict(os.environ, {"DISPLAY": ":0"}, clear=False),
        patch("wallpaperctl.set.animated.have", return_value=True),
        patch("wallpaperctl.set.animated.subprocess.Popen", return_value=dead),
        patch.object(setter, "_stop_previous"),
        patch.object(setter, "_set_static_underlay", return_value=True),
        patch.object(setter, "_prefer_root_pixmap_animation", return_value=False),
        patch.object(setter, "_x11_geometry_args", return_value=[["-g", "1920x1080+0+0"]]),
    ):
        assert not setter.set_wallpaper(ctx)


def test_x11_sets_still_underlay_before_video(tmp_path: Path) -> None:
    setter = AnimatedSetter()
    ctx = _ctx(tmp_path, wayland=False)
    frame = tmp_path / "still.jpg"
    frame.write_bytes(b"jpg")
    ctx.static_path = frame
    order: list[str] = []

    def track_underlay(c: WallpaperContext) -> bool:
        order.append("underlay")
        return True

    def track_popen(*_a, **_k):
        order.append("popen")
        return _fake_process(99)

    with (
        patch.dict(os.environ, {"DISPLAY": ":0", "WAYLAND_DISPLAY": ""}, clear=False),
        patch("wallpaperctl.set.animated.have", return_value=True),
        patch("wallpaperctl.set.animated.subprocess.Popen", side_effect=track_popen),
        patch("wallpaperctl.set.animated._STARTUP_GRACE", 0),
        patch.object(setter, "_stop_previous"),
        patch.object(setter, "_set_static_underlay", side_effect=track_underlay),
        patch.object(setter, "_prefer_root_pixmap_animation", return_value=False),
        patch.object(setter, "_x11_geometry_args", return_value=[["-fs"]]),
    ):
        assert setter.set_wallpaper(ctx)
    assert order == ["underlay", "popen"]


def test_exwm_uses_root_pixmap_animator(tmp_path: Path) -> None:
    setter = AnimatedSetter()
    ctx = _ctx(tmp_path, wayland=False)
    frame = tmp_path / "still.jpg"
    frame.write_bytes(b"jpg")
    ctx.static_path = frame
    fake = _fake_process(4242)
    with (
        patch.dict(os.environ, {"DISPLAY": ":0", "WAYLAND_DISPLAY": ""}, clear=False),
        patch("wallpaperctl.set.animated.have", return_value=True),
        patch("wallpaperctl.set.animated.subprocess.Popen", return_value=fake) as popen,
        patch("wallpaperctl.set.animated._STARTUP_GRACE", 0),
        patch.object(setter, "_stop_previous"),
        patch.object(setter, "_set_static_underlay", return_value=True),
        patch.object(setter, "_prefer_root_pixmap_animation", return_value=True),
        patch.object(setter, "_virtual_screen_size", return_value=(1920, 1080)),
    ):
        assert setter.set_wallpaper(ctx)
    args = popen.call_args.args[0]
    assert args[:2] == ["bash", "-c"]
    script = args[2]
    assert "ffmpeg" in script
    assert "feh --no-fehbg --bg-fill" in script
    assert "animated-live.jpg" in script
    assert "animated-live.partial.jpg" in script


def test_terminate_escalates_to_sigkill(monkeypatch) -> None:
    import signal as signal_mod

    from wallpaperctl.set import animated as anim

    sent: list[tuple[int, int]] = []
    monkeypatch.setattr(
        anim.AnimatedSetter,
        "_signal",
        classmethod(lambda cls, pid, sig: sent.append((pid, sig)) or True),
    )
    monkeypatch.setattr(
        anim.AnimatedSetter, "_alive", classmethod(lambda cls, pid: True)
    )
    monkeypatch.setattr(anim, "_TERM_GRACE", 0.05)
    AnimatedSetter._terminate(4242)
    assert (4242, signal_mod.SIGTERM) in sent
    assert (4242, signal_mod.SIGKILL) in sent


def test_terminate_skips_kill_when_term_works(monkeypatch) -> None:
    import signal as signal_mod

    from wallpaperctl.set import animated as anim

    sent: list[tuple[int, int]] = []
    monkeypatch.setattr(
        anim.AnimatedSetter,
        "_signal",
        classmethod(lambda cls, pid, sig: sent.append((pid, sig)) or True),
    )
    monkeypatch.setattr(
        anim.AnimatedSetter, "_alive", classmethod(lambda cls, pid: False)
    )
    monkeypatch.setattr(anim, "_TERM_GRACE", 5.0)
    AnimatedSetter._terminate(5151)
    assert sent == [(5151, signal_mod.SIGTERM)]


def test_log_tail_missing_file() -> None:
    from wallpaperctl.set.animated import AnimatedSetter as A

    with patch.object(A, "_log_file", Path("/nonexistent/animated.log")):
        assert A._log_tail() == "(no player log)"
