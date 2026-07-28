"""Push wallust/pywal colors to the Pywalfox Firefox extension.

Pywalfox reads ``~/.cache/wal/colors.json``. Browser chrome often looks muddy
when mid-palette colors sit too close to the background (tab text, icons,
inactive controls). This op optionally boosts contrast in that file, then
runs ``pywalfox update``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from wallpaperctl.context import WallpaperContext
from wallpaperctl.theme.base import debug_op
from wallpaperctl.util import have, hex_to_rgb, home, run

log = logging.getLogger("wallpaperctl")

COLORS_JSON = home() / ".cache" / "wal" / "colors.json"


def _luma(hex_color: str) -> float:
    r, g, b = hex_to_rgb(hex_color)
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


def _contrast_ratio(c1: str, c2: str) -> float:
    """WCAG relative-luminance contrast ratio (approx)."""
    l1, l2 = _luma(c1), _luma(c2)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _mix(c: str, other: str, t: float) -> str:
    t = max(0.0, min(1.0, t))
    r1, g1, b1 = hex_to_rgb(c)
    r2, g2, b2 = hex_to_rgb(other)
    r = max(0, min(255, int(round(r1 + (r2 - r1) * t))))
    g = max(0, min(255, int(round(g1 + (g2 - g1) * t))))
    b = max(0, min(255, int(round(b1 + (b2 - b1) * t))))
    return f"#{r:02X}{g:02X}{b:02X}"


def _ensure_contrast(
    color: str,
    bg: str,
    *,
    min_ratio: float,
    toward: str,
) -> str:
    """Lighten/darken *color* toward *toward* until contrast vs *bg* is enough."""
    c = color if color.startswith("#") else f"#{color}"
    bg = bg if bg.startswith("#") else f"#{bg}"
    toward = toward if toward.startswith("#") else f"#{toward}"
    if _contrast_ratio(c, bg) >= min_ratio:
        return c.upper()
    # Binary-search mix factor
    lo, hi = 0.0, 1.0
    best = c
    for _ in range(12):
        mid = (lo + hi) / 2
        trial = _mix(c, toward, mid)
        if _contrast_ratio(trial, bg) >= min_ratio:
            best = trial
            hi = mid
        else:
            lo = mid
    # Final guarantee
    if _contrast_ratio(best, bg) < min_ratio:
        best = toward
    return best.upper()


def improve_browser_contrast(
    data: dict,
    *,
    text_min: float = 7.0,
    control_min: float = 4.5,
    icon_min: float = 4.5,
) -> dict:
    """Return a copy of colors.json data with better UI contrast for browsers.

    Dark themes (common): raise foreground / bright colors; lift mid accents
    used for icons and inactive controls so they separate from the toolbar.

    Pywalfox maps these into Firefox theme properties (tab text, toolbar icons,
    etc.). Muddy mid-tones on near-black toolbars are the usual failure mode.
    """
    out = json.loads(json.dumps(data))  # deep-ish copy
    special = out.setdefault("special", {})
    colors = out.setdefault("colors", {})

    def get_c(i: int) -> str | None:
        k = f"color{i}"
        if k not in colors:
            return None
        c = colors[k]
        return c if str(c).startswith("#") else f"#{c}"

    def set_c(i: int, val: str) -> None:
        colors[f"color{i}"] = val.upper()

    bg = special.get("background") or get_c(0) or "#0A0A0A"
    if not str(bg).startswith("#"):
        bg = f"#{bg}"
    bg = bg.upper()
    special["background"] = bg
    if get_c(0):
        set_c(0, bg)

    dark = _luma(bg) < 0.5
    # Strong light text for dark toolbars (inactive tabs still readable)
    toward_text = "#E8EAED" if dark else "#1A1A1A"
    # Mid accents: lift toward soft light grey (keeps hue, gains contrast)
    toward_mid = "#D0D4D8" if dark else "#333333"

    # Primary text / cursor — aim high for tab titles
    fg = special.get("foreground") or get_c(7) or toward_text
    if not str(fg).startswith("#"):
        fg = f"#{fg}"
    fg = _ensure_contrast(fg, bg, min_ratio=text_min, toward=toward_text)
    special["foreground"] = fg
    special["cursor"] = fg
    set_c(7, fg)
    # color15: active / emphasized tab text
    c15 = get_c(15) or fg
    set_c(15, _ensure_contrast(c15, bg, min_ratio=text_min, toward=toward_text))

    # Mid palette: icons, accents, inactive UI (must clear the toolbar bg)
    for i in range(1, 7):
        c = get_c(i)
        if not c:
            continue
        set_c(i, _ensure_contrast(c, bg, min_ratio=icon_min, toward=toward_mid))

    # color8 often mirrors bg — slight lift for nested panels
    if get_c(8):
        set_c(
            8,
            _ensure_contrast(get_c(8) or bg, bg, min_ratio=1.2, toward=toward_mid),
        )

    # color9-14: bright variants for controls / highlights
    for i in range(9, 15):
        c = get_c(i)
        if not c:
            continue
        set_c(i, _ensure_contrast(c, bg, min_ratio=control_min, toward=toward_text))

    return out


def load_colors_json(path: Path | None = None) -> dict | None:
    p = path or COLORS_JSON
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log.warning("Failed to read %s: %s", p, e)
        return None


def save_colors_json(data: dict, path: Path | None = None) -> bool:
    p = path or COLORS_JSON
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return True
    except OSError as e:
        log.warning("Failed to write %s: %s", p, e)
        return False


class PywalfoxOp:
    name = "pywalfox"

    def enabled(self, ctx: WallpaperContext) -> bool:
        if not getattr(ctx.ops, "enable_pywalfox", True):
            return False
        return have("pywalfox")

    def run(self, ctx: WallpaperContext) -> bool:
        improve = bool(getattr(ctx.ops, "pywalfox_improve_contrast", True))
        text_min = float(getattr(ctx.ops, "pywalfox_text_contrast", 7.0))
        icon_min = float(getattr(ctx.ops, "pywalfox_icon_contrast", 4.5))
        control_min = float(getattr(ctx.ops, "pywalfox_control_contrast", 4.5))

        data = load_colors_json()
        if data is None:
            debug_op(self.name, f"missing {COLORS_JSON}", ctx)
            return False

        if improve:
            improved = improve_browser_contrast(
                data,
                text_min=text_min,
                control_min=control_min,
                icon_min=icon_min,
            )
            if not save_colors_json(improved):
                return False
            debug_op(self.name, "boosted colors.json contrast for browser UI", ctx)

        # Notify the extension (native host must be installed / Firefox open optional)
        r = run(["pywalfox", "update"], timeout=15)
        if r.returncode != 0:
            # Still ok if Firefox is closed — colors.json is ready for next start
            err = (r.stderr or r.stdout or "").strip()
            debug_op(
                self.name,
                f"pywalfox update returned {r.returncode}"
                + (f": {err[:120]}" if err else " (Firefox may be closed)"),
                ctx,
            )
            # Treat as soft success — file update is what matters for next open
            return True

        debug_op(self.name, "pywalfox update ok", ctx)
        return True
