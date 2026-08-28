"""manage TUI video mode: scan, thumbnails via extracted frames."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from wallpaperctl.config import OpsConfig
from wallpaperctl.tui.library import scan_library


def _make_library(tmp_path: Path) -> tuple[Path, Path, Path]:
    img = tmp_path / "photo.jpg"
    img.write_bytes(b"\xff\xd8fakejpg")
    vid = tmp_path / "animated" / "clip.mp4"
    vid.parent.mkdir(parents=True)
    vid.write_bytes(b"\x00\x00fake.mp4")
    return tmp_path, img, vid


def test_scan_library_images_excludes_videos(tmp_path: Path) -> None:
    root, img, vid = _make_library(tmp_path)
    items = scan_library(root)
    assert [i.path for i in items] == [img]
    assert not any(i.is_video for i in items)


def test_scan_library_videos_excludes_images(tmp_path: Path) -> None:
    root, img, vid = _make_library(tmp_path)
    items = scan_library(root, videos=True)
    assert [i.path for i in items] == [vid]
    assert all(i.is_video for i in items)


def test_scan_library_video_dims_from_frame(tmp_path: Path) -> None:
    """Dims come from the cached extracted frame (placeholder PNG is valid)."""
    root, _img, vid = _make_library(tmp_path)
    ops = OpsConfig()
    items = scan_library(root, with_dimensions=True, videos=True, ops=ops)
    assert len(items) == 1
    # extract_frame writes a black placeholder (target size) when ffmpeg
    # cannot decode the fake video — dims reflect that frame.
    from wallpaperctl.media import extract_frame

    frame = extract_frame(vid, ops)
    assert frame is not None
    assert (items[0].width, items[0].height) != (0, 0)


def test_preview_path_uses_frame_for_videos(tmp_path: Path) -> None:
    from wallpaperctl.tui.app import ManageApp

    root, _img, vid = _make_library(tmp_path)
    app = ManageApp(library_root=root, ops=OpsConfig(), videos=True)
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"png")

    item = next(iter(scan_library(root, videos=True)))
    with patch("wallpaperctl.tui.library.video_frame", return_value=frame):
        assert app._preview_path_for(item) == frame


def test_preview_path_image_passthrough(tmp_path: Path) -> None:
    from wallpaperctl.tui.app import ManageApp

    root, img, _vid = _make_library(tmp_path)
    app = ManageApp(library_root=root, ops=OpsConfig())
    item = next(iter(scan_library(root)))
    assert app._preview_path_for(item) == img


def test_video_mode_survives_delete(tmp_path: Path) -> None:
    """Regression: deleting in --video mode must not flip back to images."""
    from wallpaperctl.tui.app import ManageApp

    root, _img, vid = _make_library(tmp_path)
    vid2 = tmp_path / "animated" / "clip2.mp4"
    vid2.write_bytes(b"\x00\x00fake2.mp4")
    ops = OpsConfig()

    app = ManageApp(library_root=root, ops=ops, videos=True)

    async def _run() -> None:
        async with app.run_test() as pilot:
            await pilot.pause()
            # mark both videos and batch-delete them
            app.action_mark_all()
            assert len(app._marked) == 2
            app.action_delete()
            await pilot.pause()
            await pilot.press("y")  # confirm
            await pilot.pause()
            await pilot.pause()

    import asyncio

    asyncio.run(_run())

    assert not vid.exists() and not vid2.exists()
    # library still in video mode: zero items, but the mode flag held
    assert app.videos is True
    assert all(i.is_video for i in app._all)
