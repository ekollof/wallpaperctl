"""Small JSON interface for the bundled Omarchy wallpaper widget."""

from __future__ import annotations

import random
from pathlib import Path
from urllib.parse import unquote, urlsplit

from PIL import Image

from wallpaperctl.app import apply_wallpaper, load_current_wallpaper, save_current_wallpaper
from wallpaperctl.config import OpsConfig
from wallpaperctl.lock import WallpaperLock
from wallpaperctl.media import is_animated
from wallpaperctl.sources.local import list_animated_files, list_wallpaper_files
from wallpaperctl.util import home

PLUGIN_ID = "io.github.ekollof.wallpaperctl"


def file_identity(path: Path) -> str:
    stat = path.lstat()
    return f"{stat.st_dev}:{stat.st_ino}:{stat.st_size}:{stat.st_mtime_ns}"


def delete_current_wallpaper(ops: OpsConfig, expected: str, identity: str) -> None:
    """Replace then delete only the exact wallpaper the user confirmed."""
    lock = WallpaperLock()
    lock.acquire()
    try:
        current = load_current_wallpaper(ops)
        if str(current) != expected or not identity or file_identity(current) != identity:
            raise ValueError("Wallpaper changed since confirmation; refresh and try again")
        library = ops.path("wallpaper_dir")
        candidates = list_wallpaper_files(library) + list_animated_files(library / "animated")
        candidates = [p for p in candidates if p.resolve() != current.resolve()]
        preferred = [p for p in candidates if is_animated(p) == is_animated(current)]
        if not candidates:
            raise ValueError("No replacement wallpaper in the local library; current file kept")
        replacement = random.choice(preferred or candidates)
        # Theme operations check ~/.wallpaper to reject stale work.
        save_current_wallpaper(replacement, ops)
        try:
            if not apply_wallpaper(replacement, ops, sync=False):
                raise ValueError("Could not apply a replacement wallpaper; current file kept")
        except (Exception, SystemExit):
            save_current_wallpaper(current, ops)
            raise
        if file_identity(current) != identity:
            raise ValueError("Original file changed during replacement; file kept")
        current.unlink()
    finally:
        lock.release()


def wallpaper_status(ops: OpsConfig) -> dict:
    """Read local wallpaper information without fetching or extracting media."""
    result = {
        "path": "",
        "name": "No wallpaper selected",
        "kind": "",
        "size": 0,
        "dimensions": "",
        "preview": "",
        "missing": False,
        "identity": "",
        "library": str(ops.path("wallpaper_dir")),
        "library_url": ops.path("wallpaper_dir").resolve().as_uri(),
    }
    try:
        path = load_current_wallpaper(ops)
    except (SystemExit, OSError):
        return result
    result.update(
        path=str(path), name=path.name, kind="Animated" if is_animated(path) else "Static"
    )
    try:
        result["size"] = path.stat().st_size
        result["identity"] = file_identity(path)
    except OSError:
        result["missing"] = True
        return result
    preview = path
    if is_animated(path):
        preview = home() / ".local/state/omarchy/current/background"
        if not preview.is_file() or is_animated(preview.resolve()):
            return result
    try:
        with Image.open(preview) as image:
            result["dimensions"] = f"{image.width} × {image.height}"
        result["preview"] = preview.resolve().as_uri()
    except (OSError, ValueError):
        pass
    return result


def local_file_url(value: str) -> Path:
    """Decode a Qt file selection, rejecting remote and non-file URLs."""
    url = urlsplit(value)
    if url.scheme != "file" or url.netloc not in ("", "localhost"):
        raise ValueError("Select a local wallpaper file")
    path = Path(unquote(url.path))
    if not path.is_absolute() or not path.is_file():
        raise ValueError("Selected wallpaper file does not exist")
    return path
