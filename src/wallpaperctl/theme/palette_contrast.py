"""Contrast-correct the canonical wallust/pywal palette after generation.

wallust's ``check_contrast`` only performs a mild check against the
background (no guaranteed ratio), so mid-tones regularly land too close to
the background for terminal text (shell prompts, opencode muted text,
weechat). This module enforces WCAG ratios on ``~/.cache/wal/colors.json``
and rewrites the same hex values into the other generated files so every
consumer (shell, kitty, starship, weechat, opencode) sees one consistent,
readable palette.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from wallpaperctl.theme.pywalfox import (
    _ensure_contrast,
    _luma,
    load_colors_json,
    save_colors_json,
)
from wallpaperctl.util import have, home, run

log = logging.getLogger("wallpaperctl")

WAL_DIR = home() / ".cache" / "wal"
OPENCODE_SCRIPT = home() / ".config" / "wallust" / "scripts" / "generate-wallust-theme.py"
# Rendered template targets that embed raw palette hexes.
EXTRA_TARGETS = (
    home() / ".config" / "starship.toml",
    home() / ".config" / "kitty" / "current-theme.conf",
    home() / ".config" / "btop" / "themes" / "noctalia.theme",
)

_TOWARD_TEXT_DARK = "#E8EAED"
_TOWARD_TEXT_LIGHT = "#1A1A1A"
_TOWARD_MID_DARK = "#D0D4D8"
_TOWARD_MID_LIGHT = "#333333"


def improve_terminal_contrast(
    data: dict,
    *,
    text_min: float = 4.5,
    dim_min: float = 4.0,
    accent_min: float = 3.0,
) -> tuple[dict, dict[str, str]]:
    """Return (new_data, hex_map) with guaranteed contrast vs the background.

    hex_map maps old lowercase hex -> new uppercase hex for every changed
    color so callers can patch generated files. Untouched: background and
    color0 (surfaces), cursor (follows foreground).
    """
    out = json_copy(data)
    special = out.setdefault("special", {})
    colors = out.setdefault("colors", {})

    def get(key: str) -> str | None:
        val = colors.get(key) or special.get(key)
        if not isinstance(val, str) or not val:
            return None
        return val if val.startswith("#") else f"#{val}"

    bg = get("background") or get("color0") or "#0A0A0A"
    dark = _luma(bg) < 0.5
    toward_text = _TOWARD_TEXT_DARK if dark else _TOWARD_TEXT_LIGHT
    toward_mid = _TOWARD_MID_DARK if dark else _TOWARD_MID_LIGHT

    mapping: dict[str, str] = {}

    def fix(key: str, min_ratio: float, toward: str) -> None:
        old = get(key)
        if not old:
            return
        new = _ensure_contrast(old, bg, min_ratio=min_ratio, toward=toward)
        if new.lower() != old.lower():
            mapping[old.lower()] = new
        if key in colors:
            colors[key] = new
        else:
            special[key] = new

    # Primary text: foreground + color7 (default text) + color15 (emphasized).
    fix("foreground", text_min, toward_text)
    fix("color7", text_min, toward_text)
    fix("color15", text_min, toward_text)
    # color8 = bright black: dim/comments text (shell truncations, opencode
    # muted UI). The most common "invisible text" offender.
    fix("color8", dim_min, toward_mid)
    # ANSI accents must separate from the background but stay colorful;
    # mixing toward a light grey keeps hue while gaining the missing ratio.
    for i in (1, 2, 3, 4, 5, 6, 9, 10, 11, 12, 13, 14):
        fix(f"color{i}", accent_min, toward_mid)
    return out, mapping


def json_copy(data: dict) -> dict:
    import json

    return json.loads(json.dumps(data))


def apply_hex_map(mapping: dict[str, str], paths: list[Path]) -> int:
    """Rewrite occurrences of old hex values in generated text files."""
    if not mapping:
        return 0
    pattern = re.compile(
        "#(" + "|".join(re.escape(h.lstrip("#")) for h in mapping) + ")",
        re.IGNORECASE,
    )
    changed = 0
    for path in paths:
        try:
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            new_text = pattern.sub(
                lambda m: "#" + mapping[f"#{m.group(1)}".lower()].lstrip("#"),
                text,
            )
            if new_text != text:
                path.write_text(new_text, encoding="utf-8")
                changed += 1
        except OSError as e:
            log.debug("hex map skip %s: %s", path, e)
    return changed


def fix_installed_palette(
    *,
    wal_dir: Path | None = None,
    text_min: float = 4.5,
    dim_min: float = 4.0,
    accent_min: float = 3.0,
) -> bool:
    """Contrast-fix colors.json + generated files; regenerate opencode theme."""
    wal = wal_dir or WAL_DIR
    data = load_colors_json(wal / "colors.json")
    if data is None:
        return False
    fixed, mapping = improve_terminal_contrast(
        data, text_min=text_min, dim_min=dim_min, accent_min=accent_min
    )
    if not mapping:
        return True
    if not save_colors_json(fixed, wal / "colors.json"):
        return False

    generated = sorted(
        p for p in wal.glob("colors*") if p.is_file() and p.name != "colors.json"
    )
    changed = apply_hex_map(mapping, [*generated, *EXTRA_TARGETS])
    log.debug(
        "palette contrast: %d colors adjusted, %d files rewritten",
        len(mapping),
        changed,
    )

    # Re-derive themes that build derived colors (mixes) from colors.json.
    if OPENCODE_SCRIPT.is_file():
        run(["python3", str(OPENCODE_SCRIPT)], timeout=15)
    if have("killall"):
        run(["killall", "-SIGUSR1", "kitty"], timeout=5)
    return True
