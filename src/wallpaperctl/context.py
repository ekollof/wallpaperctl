"""Runtime context shared by setters and theme operations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from wallpaperctl.config import OpsConfig
from wallpaperctl.detect.desktop import DesktopEnvironment


@dataclass
class WallpaperContext:
    path: Path
    de: DesktopEnvironment
    ops: OpsConfig
    photographer_name: str = ""
    photographer_username: str = ""
    provider_name: str = ""
    debug: bool = False

    @property
    def wallpaper_dir(self) -> Path:
        return self.path.parent
