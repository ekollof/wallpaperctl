"""Wallpaper source helpers.

Imports are lazy (PEP 562) so lightweight consumers (e.g. sources.local)
do not require the heavy fetch-stack dependencies (httpx, Pillow).
"""

from __future__ import annotations

from typing import Any

_EXPORTS = {
    "FetchResult": ("wallpaperctl.sources.fetch", "FetchResult"),
    "fetch_random_wallpaper": ("wallpaperctl.sources.fetch", "fetch_random_wallpaper"),
    "pick_random_wallpaper": ("wallpaperctl.sources.local", "pick_random_wallpaper"),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    if name in _EXPORTS:
        import importlib

        module_name, attr = _EXPORTS[name]
        return getattr(importlib.import_module(module_name), attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
