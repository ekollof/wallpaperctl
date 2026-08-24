from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from wallpaperctl.config import OpsConfig
from wallpaperctl.media import extract_frame, is_animated


def test_is_animated_only_accepts_mp4() -> None:
    assert is_animated(Path("wall.mp4"))
    assert not is_animated(Path("wall.webm"))
    assert not is_animated(Path("wall.png"))


def test_extract_frame_returns_none_for_still_images(tmp_path: Path) -> None:
    image = tmp_path / "wall.jpg"
    image.write_bytes(b"jpg")
    with patch("wallpaperctl.media.run") as run:
        assert extract_frame(image, OpsConfig()) is None
    run.assert_not_called()


def test_extract_frame_creates_black_placeholder_when_ffmpeg_fails(
    tmp_path: Path,
) -> None:
    video = tmp_path / "wall.mp4"
    video.write_bytes(b"video")
    cache = tmp_path / "cache"
    ops = OpsConfig(animated_cache_dir=str(cache))
    with patch("wallpaperctl.media.run") as run:
        frame = extract_frame(video, ops)
    assert run.call_count == 2
    assert frame is not None
    assert frame.is_file()
    assert frame.stat().st_size > 0


def test_extract_frame_falls_back_to_zero_when_offset_fails(tmp_path: Path) -> None:
    video = tmp_path / "wall.mp4"
    video.write_bytes(b"video")
    cache = tmp_path / "cache"
    ops = OpsConfig(animated_cache_dir=str(cache))

    def fake_run(args, **kwargs):
        output = Path(args[-1])
        if args[args.index("-ss") + 1] == "0.0":
            output.write_bytes(b"png")
            return type("Result", (), {"returncode": 0})()
        return type("Result", (), {"returncode": 1})()

    with patch("wallpaperctl.media.run", side_effect=fake_run):
        frame = extract_frame(video, ops)
    assert frame is not None
    assert frame.is_file()
