"""Local wallpaper library selection."""

from __future__ import annotations

from pathlib import Path

import pytest

from wallpaperctl.config import OpsConfig
from wallpaperctl.sources.local import list_wallpaper_files, pick_random_wallpaper


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


def test_list_wallpaper_files_recursive(tmp_path: Path) -> None:
    top = _touch(tmp_path / "a.jpg")
    nested = _touch(tmp_path / "subdir" / "deep" / "b.png")
    _touch(tmp_path / "readme.txt")
    _touch(tmp_path / ".hidden.jpg")
    _touch(tmp_path / "subdir" / ".secret" / "c.webp")

    found = {p.resolve() for p in list_wallpaper_files(tmp_path)}
    assert top.resolve() in found
    assert nested.resolve() in found
    assert all(p.suffix.lower() in {".jpg", ".png"} for p in found)
    assert len(found) == 2


def test_pick_random_wallpaper_from_nested(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _touch(tmp_path / "nested" / "wall.jpeg")
    ops = OpsConfig()
    ops.wallpaper_dir = str(tmp_path)
    monkeypatch.setattr("wallpaperctl.sources.local.random.choice", lambda xs: xs[0])
    picked = pick_random_wallpaper(ops)
    assert picked.name == "wall.jpeg"
    assert "nested" in picked.parts


def test_animated_only_picks_from_animated_directory(tmp_path: Path) -> None:
    _touch(tmp_path / "still.jpg")
    video = _touch(tmp_path / "animated" / "motion.mp4")
    ops = OpsConfig()
    ops.wallpaper_dir = str(tmp_path)
    assert video not in list_wallpaper_files(tmp_path)
    assert pick_random_wallpaper(ops, animated_only=True) == video


def test_animated_selection_ignores_still_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for index in range(20):
        _touch(tmp_path / f"still-{index}.jpg")
    video = _touch(tmp_path / "animated" / "motion.mp4")
    ops = OpsConfig()
    ops.wallpaper_dir = str(tmp_path)
    monkeypatch.setattr("wallpaperctl.sources.local.random.choice", lambda choices: choices[0])
    assert pick_random_wallpaper(ops, animated_only=True) == video


def test_animated_only_errors_when_directory_empty(tmp_path: Path) -> None:
    _touch(tmp_path / "still.jpg")
    ops = OpsConfig()
    ops.wallpaper_dir = str(tmp_path)
    with pytest.raises(SystemExit, match="No animated wallpapers"):
        pick_random_wallpaper(ops, animated_only=True)


def test_pick_random_wallpaper_empty(tmp_path: Path) -> None:
    ops = OpsConfig()
    ops.wallpaper_dir = str(tmp_path)
    with pytest.raises(SystemExit, match="No wallpapers"):
        pick_random_wallpaper(ops)


def test_pick_random_wallpaper_missing_dir(tmp_path: Path) -> None:
    ops = OpsConfig()
    ops.wallpaper_dir = str(tmp_path / "nope")
    with pytest.raises(SystemExit, match="not found"):
        pick_random_wallpaper(ops)
