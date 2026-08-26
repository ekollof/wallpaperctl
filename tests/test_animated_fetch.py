"""Animated wallpaper fetch: providers, orchestration, CLI wiring."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from wallpaperctl.config import ApiConfig, OpsConfig
from wallpaperctl.sources import fetch as fetch_mod
from wallpaperctl.sources import providers
from wallpaperctl.sources.fetch import FetchResult, fetch_random_animated_wallpaper

# ── Provider helpers ─────────────────────────────────────────────────────


def _video(seconds=10, **tiers):
    return {"duration": seconds, "videos": {k: dict(v) for k, v in tiers.items()}}


def test_prefer_short_filters_long_videos():
    videos = [{"duration": 300}, {"duration": 30}, {"duration": 0}]
    assert providers._prefer_short(videos) == [{"duration": 30}]
    # nothing short → keep everything
    assert providers._prefer_short([{"duration": 999}]) == [{"duration": 999}]


def test_pixabay_tier_prefers_large_landscape():
    hit = _video(
        large={"url": "https://x/l.mp4", "width": 1920, "height": 1080},
        small={"url": "https://x/s.mp4", "width": 960, "height": 540},
    )
    tier = providers._pixabay_tier(hit)
    assert tier == {
        "url": "https://x/l.mp4",
        "width": 1920,
        "height": 1080,
    }
    # portrait-only tiers are rejected
    assert providers._pixabay_tier(
        _video(large={"url": "https://x/p.mp4", "width": 540, "height": 960})
    ) is None


def test_fetch_pexels_video_picks_1080p(monkeypatch: pytest.MonkeyPatch):
    files = [
        {"file_type": "video/mp4", "link": "https://cdn/4k.mp4", "width": 3840, "height": 2160},
        {"file_type": "video/mp4", "link": "https://cdn/fhd.mp4", "width": 1920, "height": 1080},
        {"file_type": "video/mp4", "link": "https://cdn/sd.mp4", "width": 640, "height": 360},
        {"file_type": "video/webm", "link": "https://cdn/x.webm", "width": 1920, "height": 1080},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.pexels.com"
        assert request.url.path.startswith("/v1/videos/")
        return httpx.Response(
            200,
            json={
                "videos": [
                    {
                        "duration": 15,
                        "user": {"name": "Ada"},
                        "video_files": files,
                    }
                ]
            },
        )

    monkeypatch.setattr(providers, "_client", lambda: _make_client(handler))
    result = providers.fetch_pexels_video(ApiConfig(pexels_api_key="k", categories="nature"))
    assert result is not None
    assert result.video_url == "https://cdn/fhd.mp4"
    assert result.provider_name == "Pexels"
    assert result.photographer_name == "Ada"


def test_fetch_pixabay_video(monkeypatch: pytest.MonkeyPatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "pixabay.com"
        assert request.url.path == "/api/videos/"
        return httpx.Response(
            200,
            json={
                "totalHits": 1,
                "hits": [
                    {
                        "duration": 12,
                        "user": "Bob",
                        "videos": {
                            "large": {
                                "url": "https://cdn.pixabay/l.mp4",
                                "width": 1280,
                                "height": 720,
                            },
                        },
                    }
                ],
            },
        )

    monkeypatch.setattr(providers, "_client", lambda: _make_client(handler))
    result = providers.fetch_pixabay_video(ApiConfig(pixabay_api_key="k", categories="nature"))
    assert result is not None
    assert result.video_url == "https://cdn.pixabay/l.mp4"
    assert result.provider_name == "Pixabay"


def _make_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_pick_video_provider_covers_all():
    seen: set[str] = set()
    tried: set[str] = set()
    for _ in range(50):
        pick = providers.pick_video_provider(tried)
        seen.add(pick)
        if len(seen) == 2:
            break
        tried.add(pick)
    assert seen == {"pexels", "pixabay"}


# ── Orchestration ────────────────────────────────────────────────────────


@pytest.fixture
def ops(tmp_path: Path) -> OpsConfig:
    ops = OpsConfig()
    ops.wallpaper_dir = str(tmp_path / "Wallpapers")
    ops.url_log = str(tmp_path / "urls.log")
    return ops


def _fake_download_succeeds(content: bytes):
    def _download(url, dest, provider, *, timeout=30.0):
        dest.write_bytes(content)
        return True

    return _download


def test_fetch_animated_downloads_into_animated_dir(
    tmp_path: Path, ops: OpsConfig, monkeypatch: pytest.MonkeyPatch
):
    calls: list[str] = []

    def fake_fetch(name, api):
        calls.append(name)
        return providers.VideoResult(
            video_url="https://cdn/new-video.mp4",
            width=1920,
            height=1080,
            photographer_name="Ada",
            photographer_username="ada",
            provider_name="Pexels",
        )

    monkeypatch.setattr(fetch_mod.providers, "fetch_video_from_provider", fake_fetch)
    monkeypatch.setattr(
        fetch_mod, "_download", _fake_download_succeeds(b"x" * 200_000)
    )
    monkeypatch.setattr(fetch_mod.media, "extract_frame", lambda path, ops: None)

    result = fetch_random_animated_wallpaper(ApiConfig(categories="nature"), ops)
    assert isinstance(result, FetchResult)
    assert result.path.parent.name == "animated"
    assert result.path.suffix == ".mp4"
    assert result.path.stat().st_size == 200_000
    assert calls == ["pexels"]
    # URL logged for dedup
    log_text = Path(ops.url_log).read_text(encoding="utf-8")
    assert "new-video.mp4" in log_text


def test_fetch_animated_skips_duplicate_urls(
    tmp_path: Path, ops: OpsConfig, monkeypatch: pytest.MonkeyPatch
):
    state = {"n": 0}

    def fake_fetch(name, api):
        state["n"] += 1
        url = "https://cdn/same-video.mp4" if state["n"] == 1 else "https://cdn/other.mp4"
        return providers.VideoResult(
            video_url=url,
            width=1920,
            height=1080,
            photographer_name="Ada",
            photographer_username="ada",
            provider_name="Pexels",
        )

    monkeypatch.setattr(fetch_mod.providers, "fetch_video_from_provider", fake_fetch)
    monkeypatch.setattr(
        fetch_mod, "_download", _fake_download_succeeds(b"x" * 200_000)
    )
    monkeypatch.setattr(fetch_mod.media, "extract_frame", lambda path, ops: None)

    first = fetch_random_animated_wallpaper(ApiConfig(categories="nature"), ops)
    assert first is not None
    second = fetch_random_animated_wallpaper(ApiConfig(categories="nature"), ops)
    assert second is not None
    assert first.path != second.path
    assert state["n"] >= 2


def test_fetch_animated_rejects_truncated_download(
    tmp_path: Path, ops: OpsConfig, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        fetch_mod.providers,
        "fetch_video_from_provider",
        lambda name, api: providers.VideoResult(
            video_url="https://cdn/tiny.mp4",
            width=1920,
            height=1080,
            photographer_name="A",
            photographer_username="a",
            provider_name="Pixabay",
        ),
    )
    monkeypatch.setattr(fetch_mod, "_download", _fake_download_succeeds(b"tiny"))
    monkeypatch.setattr(ops, "fetch_max_attempts", 2, raising=False)

    assert (
        fetch_random_animated_wallpaper(ApiConfig(categories="nature"), ops) is None
    )


def test_media_recognizes_more_containers():
    from wallpaperctl.media import is_animated

    assert is_animated(Path("a.mp4"))
    assert is_animated(Path("b.webm"))
    assert is_animated(Path("c.mov"))
    assert not is_animated(Path("d.jpg"))


# ── CLI wiring ───────────────────────────────────────────────────────────


def test_cli_routes_r_animated_to_video_fetch(
    tmp_path: Path, ops: OpsConfig, monkeypatch: pytest.MonkeyPatch
):
    import wallpaperctl.cli as cli

    hits = {"animated": 0, "static": 0}

    def fake_animated(api, ops_):
        hits["animated"] += 1
        video = tmp_path / "v.mp4"
        video.write_bytes(b"x" * 200_000)
        return FetchResult(path=video, photographer_name="A",
                           photographer_username="a", provider_name="Pexels")

    def fake_static(api, ops_):
        hits["static"] += 1
        return None

    monkeypatch.setattr(cli, "load_ops_config", lambda: ops)
    monkeypatch.setattr(
        cli,
        "load_api_config",
        lambda categories_override=None, exclude_override=None: ApiConfig(
            unsplash_access_key="x", pexels_api_key="x", pixabay_api_key="x"
        ),
    )
    monkeypatch.setattr(cli, "fetch_random_animated_wallpaper", fake_animated)
    monkeypatch.setattr(cli, "fetch_random_wallpaper", fake_static)
    monkeypatch.setattr(cli, "save_current_wallpaper", lambda *a, **k: None)
    monkeypatch.setattr(cli, "apply_wallpaper", lambda *a, **k: True)
    monkeypatch.setattr(cli, "safe_notify", lambda *a, **k: None)
    monkeypatch.setattr(cli, "pick_random_wallpaper", lambda *a, **k: tmp_path / "local.jpg")

    rc = cli._run_action(
        fetch=True, reload_=False, categories=None, path=None,
        ops=ops, debug=False, animated=True,
    )
    assert rc == 0
    assert hits == {"animated": 1, "static": 0}
