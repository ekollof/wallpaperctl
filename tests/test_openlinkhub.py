"""OpenLinkHub theme op tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx

from wallpaperctl.config import OpsConfig
from wallpaperctl.context import WallpaperContext
from wallpaperctl.detect.desktop import DesktopEnvironment
from wallpaperctl.theme.openlinkhub import OpenlinkhubOp


def _ctx(tmp_path: Path, **ops_kw) -> WallpaperContext:
    ops = OpsConfig()
    for k, v in ops_kw.items():
        setattr(ops, k, v)
    img = tmp_path / "w.jpg"
    img.write_bytes(b"x")
    return WallpaperContext(path=img, de=DesktopEnvironment(), ops=ops)


def test_enabled_flag(tmp_path: Path) -> None:
    op = OpenlinkhubOp()
    assert op.enabled(_ctx(tmp_path, enable_openlinkhub=True))
    assert not op.enabled(_ctx(tmp_path, enable_openlinkhub=False))


def test_skips_when_daemon_down(tmp_path: Path) -> None:
    op = OpenlinkhubOp()
    ctx = _ctx(tmp_path, openlinkhub_url="http://127.0.0.1:9")
    with patch.object(op, "_is_running", return_value=False):
        assert op.run(ctx) is True


def test_posts_color_all_when_running(tmp_path: Path) -> None:
    op = OpenlinkhubOp()
    ctx = _ctx(
        tmp_path,
        rgb_color_strategy="fixed",
        openrgb_color_line_standalone=4,
        openlinkhub_url="http://127.0.0.1:27003",
        openlinkhub_brightness=0.8,
    )
    posted: dict = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"code": 200, "status": 1, "message": "ok"}

        text = "ok"

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url):
            r = FakeResponse()
            return r

        def post(self, url, json=None):
            posted["url"] = url
            posted["json"] = json
            return FakeResponse()

    with (
        patch("wallpaperctl.theme.openlinkhub.httpx.Client", FakeClient),
        patch(
            "wallpaperctl.theme.openlinkhub.pick_theme_color",
            return_value=("#FF6432", 4),
        ),
    ):
        assert op.run(ctx) is True

    assert posted["url"] == "http://127.0.0.1:27003/api/color/all"
    assert posted["json"] == {
        "color": {"red": 255, "green": 100, "blue": 50, "brightness": 0.8}
    }


def test_returns_false_on_http_error(tmp_path: Path) -> None:
    op = OpenlinkhubOp()
    ctx = _ctx(tmp_path)

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url):
            r = MagicMock()
            r.status_code = 200
            return r

        def post(self, url, json=None):
            raise httpx.ConnectError("boom")

    with (
        patch("wallpaperctl.theme.openlinkhub.httpx.Client", FakeClient),
        patch(
            "wallpaperctl.theme.openlinkhub.pick_theme_color",
            return_value=("#AABBCC", 5),
        ),
    ):
        assert op.run(ctx) is False


def test_is_running_true_on_200() -> None:
    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url):
            r = MagicMock()
            r.status_code = 200
            return r

    with patch("wallpaperctl.theme.openlinkhub.httpx.Client", FakeClient):
        assert OpenlinkhubOp._is_running("http://127.0.0.1:27003", 2.0, MagicMock())


def test_is_running_false_on_connect_error() -> None:
    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url):
            raise httpx.ConnectError("nope")

    with patch("wallpaperctl.theme.openlinkhub.httpx.Client", FakeClient):
        assert not OpenlinkhubOp._is_running("http://127.0.0.1:9", 1.0, MagicMock())


def test_runner_lists_openlinkhub() -> None:
    from wallpaperctl.theme.runner import list_ops

    assert "openlinkhub" in list_ops()
