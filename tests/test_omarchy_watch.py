from __future__ import annotations

import json
from unittest.mock import patch

from wallpaperctl.omarchy_watch import (
    is_layout_event,
    monitor_layout_fingerprint,
    rebind_motion_wallpaper,
    restore_monitor_transforms,
    snapshot_monitor_transforms,
    suppress_layout_rebind,
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


def test_snapshot_monitor_transforms():
    payload = (
        '[{"name":"eDP-1","transform":1,"width":1600,"height":2560},'
        '{"name":"HDMI-A-1","transform":0,"width":1920,"height":1080}]'
    )
    assert snapshot_monitor_transforms(payload) == [("eDP-1", 1), ("HDMI-A-1", 0)]


def test_restore_skips_matching_transform():
    with (
        patch(
            "wallpaperctl.omarchy_watch.snapshot_monitor_transforms",
            return_value=[("eDP-1", 3)],
        ),
        patch("wallpaperctl.omarchy_watch.run") as run_mock,
    ):
        assert restore_monitor_transforms([("eDP-1", 3)])
    run_mock.assert_not_called()
    calls = {"n": 0}

    def fake_snap(**kwargs):
        calls["n"] += 1
        return [("eDP-1", 0)] if calls["n"] == 1 else [("eDP-1", 3)]

    with (
        patch(
            "wallpaperctl.omarchy_watch.snapshot_monitor_transforms",
            side_effect=fake_snap,
        ),
        patch("wallpaperctl.omarchy_watch._touch_device_names", return_value=[]),
        patch("wallpaperctl.omarchy_watch.run") as run_mock,
        patch("wallpaperctl.omarchy_watch.time.sleep", lambda s: None),
    ):
        run_mock.return_value.returncode = 0
        run_mock.return_value.stdout = "ok"
        assert restore_monitor_transforms([("eDP-1", 3)])
    expr = run_mock.call_args[0][0][2]
    assert "eDP-1" in expr and "transform = 3" in expr


def test_suppress_blocks_rebind(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(
        "wallpaperctl.omarchy_watch._WATCH_DIR", tmp_path / "cache"
    )
    monkeypatch.setattr(
        "wallpaperctl.omarchy_watch._SUPPRESS_FILE",
        tmp_path / "cache" / "omarchy-motion-suppress",
    )
    state = tmp_path / ".local" / "state" / "motion-wallpaper"
    state.mkdir(parents=True)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"v")
    (state / "state.json").write_text(
        json.dumps({"enabled": True, "videoPath": str(video)}),
        encoding="utf-8",
    )
    suppress_layout_rebind(30)
    with (
        patch("wallpaperctl.omarchy_watch.motion_wallpaper_stop") as stop,
        patch("wallpaperctl.omarchy_watch.motion_wallpaper_play") as play,
    ):
        assert not rebind_motion_wallpaper()
        stop.assert_not_called()
        assert rebind_motion_wallpaper(force=True)
        play.assert_called_once()


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
