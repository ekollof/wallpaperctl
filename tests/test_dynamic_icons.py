"""Dynamic icon theme generation."""

from __future__ import annotations

from pathlib import Path

from wallpaperctl.theme.dynamic_icons import _write_icons


def test_write_icons_shell_parity_status_set(tmp_path: Path) -> None:
    for size in (16, 22, 24, 32, 48, "scalable"):
        for ctx in ("actions", "apps", "devices", "places", "status"):
            (tmp_path / str(size) / ctx).mkdir(parents=True)

    _write_icons(tmp_path, fg="eeeeee", accent="4488ff", red="ff0000", green="00aa00")

    expected_status = [
        "battery-full-symbolic.svg",
        "battery-good-symbolic.svg",
        "battery-low-symbolic.svg",
        "battery-caution-symbolic.svg",
        "bluetooth-active-symbolic.svg",
        "notification-symbolic.svg",
        "network-wireless-offline-symbolic.svg",
        "audio-volume-muted-symbolic.svg",
        "user-available-symbolic.svg",
        "view-app-grid-symbolic.svg",
    ]
    for name in expected_status:
        assert (tmp_path / "24" / "status" / name).is_file(), name
        assert (tmp_path / "scalable" / "status" / name).is_file(), f"scalable {name}"

    assert (tmp_path / "scalable" / "places" / "folder.svg").is_file()
