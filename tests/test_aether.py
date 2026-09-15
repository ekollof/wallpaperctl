"""Aether (omarchy theming engine) palette bridge."""

from __future__ import annotations

import json
from unittest.mock import patch

from wallpaperctl.theme import aether as ae


def _payload(colors=None, **extra):
    data = {"mode": "normal", "lightMode": False, "wallpaper": "/tmp/w.jpg"}
    if colors is not False:
        data["colors"] = colors or [f"#{i:02x}{i:02x}{i:02x}" for i in range(16)]
    data.update(extra)
    return json.dumps(data)


def test_parse_envelope_to_pywal_shape():
    out = ae.parse_extract_palette(_payload())
    assert out["special"]["background"] == "#000000"
    assert out["special"]["foreground"] == "#070707"
    assert out["special"]["cursor"] == "#0f0f0f"
    assert out["colors"]["color4"] == "#040404"
    assert len(out["colors"]) == 16


def test_parse_bare_array():
    out = ae.parse_extract_palette(json.dumps([f"#{i:02x}{i:02x}{i:02x}" for i in range(16)]))
    assert out is not None and out["colors"]["color15"] == "#0f0f0f"


def test_parse_rejects_malformed():
    assert ae.parse_extract_palette("not json") is None
    assert ae.parse_extract_palette(_payload(colors=[ "#000000"] * 4)) is None
    assert ae.parse_extract_palette(_payload(colors=["nothex"] * 16)) is None
    assert ae.parse_extract_palette('{"colors": "nope"}') is None


def test_extract_missing_binary_is_soft():
    with (
        patch("wallpaperctl.theme.aether.have", return_value=False),
        patch("wallpaperctl.theme.aether.run") as run_mock,
    ):
        assert ae.extract_palette("/tmp/w.jpg") is None
    run_mock.assert_not_called()


def test_extract_unknown_mode_is_soft():
    with patch("wallpaperctl.theme.aether.have", return_value=True):
        assert ae.extract_palette("/tmp/w.jpg", mode="neon") is None


def test_extract_flags_passthrough():
    captured: list[list[str]] = []

    def fake_run(args, **kwargs):
        captured.append(list(args))
        return type("R", (), {"returncode": 0, "stdout": _payload(), "stderr": ""})()

    with (
        patch("wallpaperctl.theme.aether.have", return_value=True),
        patch("wallpaperctl.theme.aether.run", side_effect=fake_run),
    ):
        assert ae.extract_palette("/tmp/w.jpg") is not None
        assert ae.extract_palette("/tmp/w.jpg", mode="pastel") is not None
        assert ae.extract_palette("/tmp/w.jpg", force_light=True) is not None

    assert captured[0] == ["aether", "--extract-palette", "/tmp/w.jpg", "--json"]
    assert captured[1][4:6] == ["--extract-mode", "pastel"]
    assert "--light-mode" in captured[2]


def test_extract_failure_returns_none():
    with (
        patch("wallpaperctl.theme.aether.have", return_value=True),
        patch("wallpaperctl.theme.aether.run") as run_mock,
    ):
        run_mock.return_value = type(
            "R", (), {"returncode": 1, "stdout": "", "stderr": "boom"}
        )()
        assert ae.extract_palette("/tmp/w.jpg") is None
