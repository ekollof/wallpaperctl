from __future__ import annotations

import json
from unittest.mock import patch

from wallpaperctl.omarchy_watch import (
    is_layout_event,
    monitor_layout_fingerprint,
    rebind_motion_wallpaper,
)


def test_fingerprint_changes_on_transform():
    landscape = '[{"name":"eDP-1","width":2560,"height":1600,"transform":0,"scale":1,"x":0,"y":0}]'
    portrait = '[{"name":"eDP-1","width":1600,"height":2560,"transform":1,"scale":1,"x":0,"y":0}]'
    a = monitor_layout_fingerprint(landscape)
    b = monitor_layout_fingerprint(portrait)
    assert "eDP-1" in a
    assert a != b
    assert "t0" in a
    assert "t1" in b


def test_layout_event_prefixes():
    assert is_layout_event("monitoradded>>eDP-1")
    assert is_layout_event("monitoraddedv2>>eDP-1,desc")
    assert is_layout_event("monitorremoved>>HDMI-A-1")
    assert is_layout_event("configreloaded>>")
    assert not is_layout_event("activewindow>>kitty")
    assert not is_layout_event("fullscreen>>1")


def test_rebind_stop_then_play(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    state = tmp_path / ".local" / "state" / "motion-wallpaper"
    state.mkdir(parents=True)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"v")
    (state / "state.json").write_text(
        json.dumps({"enabled": True, "videoPath": str(video)}),
        encoding="utf-8",
    )
    with (
        patch("wallpaperctl.omarchy_watch.motion_wallpaper_stop") as stop,
        patch("wallpaperctl.omarchy_watch.motion_wallpaper_play", return_value=True) as play,
        patch("wallpaperctl.omarchy_watch.time.sleep", lambda s: None),
    ):
        assert rebind_motion_wallpaper()
    stop.assert_called_once()
    play.assert_called_once()
    assert play.call_args[0][0] == video


def test_rebind_skips_when_stopped(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    state = tmp_path / ".local" / "state" / "motion-wallpaper"
    state.mkdir(parents=True)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"v")
    (state / "state.json").write_text(
        json.dumps({"enabled": False, "videoPath": str(video)}),
        encoding="utf-8",
    )
    with (
        patch("wallpaperctl.omarchy_watch.motion_wallpaper_stop") as stop,
        patch("wallpaperctl.omarchy_watch.motion_wallpaper_play") as play,
    ):
        assert not rebind_motion_wallpaper()
    stop.assert_not_called()
    play.assert_not_called()
