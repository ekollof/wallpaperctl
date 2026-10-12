"""Small JSON interface for the bundled Omarchy wallpaper widget."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlsplit

from PIL import Image

from wallpaperctl.app import load_current_wallpaper
from wallpaperctl.config import OpsConfig
from wallpaperctl.media import is_animated
from wallpaperctl.util import home

PLUGIN_ID = "io.github.ekollof.wallpaperctl"


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
