"""Aether (omarchy's theming engine) palette bridge.

Aether ships with omarchy and owns the color science: median-cut wallpaper
extraction (8 modes), OKLab adjustments, WCAG grading. On omarchy it applies
themes itself through its managed ``~/.config/omarchy/themes/aether`` theme
and a full ``omarchy theme set`` — which reloads Hyprland and restarts the
session flow. Wallpaper changes must not do that (motion wallpaper,
autorotation), so wallpaperctl uses Aether's read-only headless extraction
for the palette and keeps the fast dynamic-theme retint:

    wallpaperctl: fetch/pick/dedup, motion video, dynamic theme plumbing
    aether:       wallpaper -> 16-color ANSI palette

Falls back to the wallust palette whenever aether is missing or fails.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from wallpaperctl.util import have, run

log = logging.getLogger("wallpaperctl")

EXTRACT_MODES = (
    "normal",
    "monochromatic",
    "analogous",
    "pastel",
    "material",
    "colorful",
    "muted",
    "bright",
)

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def parse_extract_palette(payload: str | bytes) -> dict | None:
    """Parse ``aether --extract-palette --json`` output into a pywal palette.

    Accepts the documented envelope ({"colors": [...], ...}) or a bare
    16-entry array. ANSI semantics: index 0 = background, 7 = foreground,
    15 = brightest (cursor). Returns None on any malformed payload.
    """
    try:
        data = json.loads(payload)
    except (ValueError, TypeError):
        return None
    colors = data.get("colors") if isinstance(data, dict) else data
    if not isinstance(colors, list) or len(colors) < 16:
        return None
    hexes = [str(c).strip() for c in colors[:16]]
    if not all(_HEX_RE.match(c) for c in hexes):
        return None
    return {
        "special": {
            "background": hexes[0],
            "foreground": hexes[7],
            "cursor": hexes[15],
        },
        "colors": {f"color{i}": hexes[i] for i in range(16)},
    }


def extract_palette(
    image: Path,
    *,
    mode: str = "normal",
    force_light: bool = False,
) -> dict | None:
    """16-color palette from *image* via aether, shaped like pywal's colors.json.

    Read-only: never activates a theme or writes app configs. Returns None
    when aether is missing, the mode is unknown, or extraction fails —
    callers fall back to the wallust palette.
    """
    if mode not in EXTRACT_MODES:
        log.debug("aether: unknown extract mode %s", mode)
        return None
    if not have("aether"):
        return None
    args = ["aether", "--extract-palette", str(image), "--json"]
    if mode != "normal":
        args += ["--extract-mode", mode]
    if force_light:
        args.append("--light-mode")
    r = run(args, timeout=30)
    if r.returncode != 0:
        log.debug(
            "aether extract failed: %s", (r.stderr or r.stdout or "").strip()[:200]
        )
        return None
    return parse_extract_palette(r.stdout or "")
