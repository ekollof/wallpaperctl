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
    """Extract a cached representative frame from an animated wallpaper."""
    if not is_animated(path):
        return path

    try:
        stat = path.stat()
    except OSError as e:
        log.warning("Could not stat animated wallpaper %s: %s", path, e)
        return None

    seconds = max(0.0, float(ops.animated_frame_seconds))
    key = hashlib.sha256(
        f"{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}:{seconds}".encode()
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
    for seek in (seconds, 0.0) if seconds else (0.0,):
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
            try:
                temp.replace(output)
                return output
            except OSError as e:
                log.warning("Could not cache animated wallpaper frame: %s", e)
                return None

    try:
        temp.unlink(missing_ok=True)
    except OSError:
        pass
    log.warning("Could not extract a frame from animated wallpaper %s", path)
    return None
