"""COSMIC desktop wallpaper via CosmicBackground config + state.

``cosmic-bg`` and ``cosmic-greeter`` (lock/login) both care about background
settings. Wallust only wrote the *config* entry ``v1/all``; the greeter and
multi-monitor layout use *state* at
``~/.local/state/cosmic/com.system76.CosmicBackground/v1/wallpapers``.
Without updating state, the lock screen keeps stale per-output images.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from wallpaperctl.context import WallpaperContext
from wallpaperctl.set.base import debug_set
from wallpaperctl.util import home

log = logging.getLogger("wallpaperctl")

_CONFIG_DIR = "com.system76.CosmicBackground"
_STATE_REL = Path(".local/state/cosmic") / _CONFIG_DIR / "v1"
_CONFIG_REL = Path(".config/cosmic") / _CONFIG_DIR / "v1"


def _ron_path(path: Path) -> str:
    """Escape a filesystem path for RON Path(\"…\")."""
    s = str(path.resolve())
    return s.replace("\\", "\\\\").replace('"', '\\"')


def write_cosmic_background_config(wallpaper: Path) -> Path:
    """Write CosmicBackground config (``all`` + ``same-on-all``)."""
    cfg = home() / _CONFIG_REL
    cfg.mkdir(parents=True, exist_ok=True)
    rp = _ron_path(wallpaper)
    (cfg / "all").write_text(
        "\n".join(
            [
                "(",
                '    output: "all",',
                f'    source: Path("{rp}"),',
                "    filter_by_theme: true,",
                "    rotation_frequency: 300,",
                "    filter_method: Lanczos,",
                "    scaling_mode: Zoom,",
                "    sampling_method: Alphanumeric,",
                ")",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (cfg / "same-on-all").write_text("true\n", encoding="utf-8")
    return cfg / "all"


def write_cosmic_background_state(wallpaper: Path) -> Path | None:
    """Update CosmicBackground *state* wallpapers list (greeter + multi-head).

    Replaces every ``Path("…")`` with the new wallpaper so all outputs match
    when same-on-all is intended. If no state file exists yet, creates a
    single-entry list for ``all``.
    """
    state_dir = home() / _STATE_REL
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / "wallpapers"
    rp = _ron_path(wallpaper)

    if state_file.is_file():
        try:
            text = state_file.read_text(encoding="utf-8")
        except OSError as e:
            log.warning("Could not read cosmic-bg state: %s", e)
            return None
        new_text, n = re.subn(
            r'Path\("(?:[^"\\]|\\.)*"\)',
            f'Path("{rp}")',
            text,
        )
        if n == 0:
            # Unexpected format — rewrite as single-source list
            new_text = f'[\n    ("all", Path("{rp}")),\n]\n'
        try:
            state_file.write_text(new_text, encoding="utf-8")
        except OSError as e:
            log.warning("Could not write cosmic-bg state: %s", e)
            return None
        log.debug("Updated %s Path entries in cosmic-bg state", max(n, 1))
    else:
        state_file.write_text(
            f'[\n    ("all", Path("{rp}")),\n]\n',
            encoding="utf-8",
        )
    return state_file


def sync_cosmic_wallpaper(wallpaper: Path) -> tuple[bool, str]:
    """Write config + state for *wallpaper*. Returns (ok, detail)."""
    if not wallpaper.is_file():
        return False, f"not a file: {wallpaper}"
    try:
        write_cosmic_background_config(wallpaper)
        st = write_cosmic_background_state(wallpaper)
        detail = f"config+state → {wallpaper.name}"
        if st is None:
            detail = f"config only → {wallpaper.name}"
        return True, detail
    except OSError as e:
        return False, str(e)


class CosmicSetter:
    """Apply wallpaper for System76 COSMIC (session + lock/greeter state)."""

    name = "cosmic"

    def applies(self, ctx: WallpaperContext) -> bool:
        if getattr(ctx.de, "cosmic", False):
            return True
        # Config present even if detection missed
        return (home() / ".config/cosmic" / _CONFIG_DIR).is_dir()

    def set_wallpaper(self, ctx: WallpaperContext) -> bool:
        path = ctx.path.resolve()
        ok, detail = sync_cosmic_wallpaper(path)
        if ok:
            debug_set(self.name, detail, ctx)
        else:
            debug_set(self.name, f"failed: {detail}", ctx)
        return ok
