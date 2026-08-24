"""Animated wallpaper detection and representative-frame extraction."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from wallpaperctl.config import OpsConfig
from wallpaperctl.util import run

log = logging.getLogger("wallpaperctl")

ANIMATED_SUFFIXES = frozenset({".mp4"})


def is_animated(path: Path) -> bool:
    return path.suffix.lower() in ANIMATED_SUFFIXES


def extract_frame(path: Path, ops: OpsConfig) -> Path | None:
    """Return a cached representative frame for an animated wallpaper.

    Non-animated inputs return None. When ffmpeg cannot decode the video, a
    black placeholder image is generated instead so that image-only consumers
    (static setters, palette tools) always receive a valid image file.
    """
    if not is_animated(path):
        return None

    try:
        stat_result = path.stat()
    except OSError as e:
        log.warning("Could not stat animated wallpaper %s: %s", path, e)
        return None

    seconds = max(0.0, float(ops.animated_frame_seconds))
    key = hashlib.sha256(
        f"{path.resolve()}:{stat_result.st_size}:{stat_result.st_mtime_ns}:{seconds}".encode()
    ).hexdigest()[:24]
    cache_dir = ops.path("animated_cache_dir")
    output = cache_dir / f"{key}.png"
    if output.is_file() and output.stat().st_size > 0:
        return output

    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        log.warning("Could not create animated wallpaper cache: %s", e)
        return None

    temp = cache_dir / f".{key}.tmp.png"
    seek_candidates = [seconds, 0.0] if seconds > 0 else [0.0]
    for seek in seek_candidates:
        result = run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                str(seek),
                "-i",
                str(path),
                "-frames:v",
                "1",
                str(temp),
            ],
            timeout=60,
        )
        if result.returncode == 0 and temp.is_file() and temp.stat().st_size > 0:
            return _commit_temp(temp, output)

    log.warning("Could not extract a frame from %s; using black placeholder", path)
    if _write_black_placeholder(temp, ops):
        return _commit_temp(temp, output)
    _discard(temp)
    return None


def _commit_temp(temp: Path, output: Path) -> Path | None:
    try:
        temp.replace(output)
        return output
    except OSError as e:
        log.warning("Could not cache animated wallpaper frame: %s", e)
        _discard(temp)
        return None


def _write_black_placeholder(target: Path, ops: OpsConfig) -> bool:
    try:
        from PIL import Image

        Image.new("RGB", (ops.target_width, ops.target_height), "black").save(target)
    except Exception as e:
        log.warning("Could not write black placeholder frame: %s", e)
        return False
    return target.is_file() and target.stat().st_size > 0


def _discard(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
