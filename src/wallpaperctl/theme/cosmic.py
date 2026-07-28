"""Apply wallust palette to System76 COSMIC desktop theme (v2 hex format).

COSMIC ≥ epoch-1 reads ``CosmicTheme.{Dark,Light}/v2/*`` with 8-digit hex
colors (``"#RRGGBBAA"``). Older wallust templates only wrote **v1** float
RGB accents, which COSMIC no longer applies — this op writes v2.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from wallpaperctl.context import WallpaperContext
from wallpaperctl.theme.base import debug_op
from wallpaperctl.util import hex_to_rgb, home, read_wal_colors

log = logging.getLogger("wallpaperctl")

# Simple component (accent, buttons, warning, …)
_COMPONENT_KEYS = (
    "base",
    "hover",
    "pressed",
    "selected",
    "selected_text",
    "focus",
    "divider",
    "on",
    "disabled",
    "on_disabled",
    "border",
    "disabled_border",
)

# Nested surface files that should pick up accent for focus / selected_text
_SURFACE_FILES = (
    "background",
    "primary",
    "secondary",
    "transparent_background",
    "transparent_primary",
    "transparent_secondary",
)


def _hex8(color: str, *, alpha: str = "FF") -> str:
    h = color.lstrip("#")
    if len(h) == 8:
        return f"#{h.upper()}"
    if len(h) != 6:
        raise ValueError(f"bad color {color!r}")
    return f"#{h.upper()}{alpha.upper()}"


def _clamp_byte(n: float) -> int:
    return max(0, min(255, int(round(n))))


def _mix(c: str, other: str, t: float) -> str:
    """Linear blend *c* toward *other* by *t* (0..1) → #RRGGBB."""
    r1, g1, b1 = hex_to_rgb(c)
    r2, g2, b2 = hex_to_rgb(other)
    r = _clamp_byte(r1 + (r2 - r1) * t)
    g = _clamp_byte(g1 + (g2 - g1) * t)
    b = _clamp_byte(b1 + (b2 - b1) * t)
    return f"#{r:02X}{g:02X}{b:02X}"


def _darken(c: str, t: float = 0.4) -> str:
    return _mix(c, "#000000", t)


def _lighten(c: str, t: float = 0.15) -> str:
    return _mix(c, "#FFFFFF", t)


def _luma(c: str) -> float:
    r, g, b = hex_to_rgb(c)
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


def _on_color(c: str) -> str:
    """Contrasting black/white for text on *c*."""
    return "#000000" if _luma(c) > 0.55 else "#FFFFFF"


def component_ron(
    base: str,
    *,
    hover: str | None = None,
    pressed: str | None = None,
    selected: str | None = None,
    divider: str = "#000000",
    on: str | None = None,
) -> str:
    """Serialize a COSMIC v2 Component as RON."""
    base8 = _hex8(base)
    hover8 = _hex8(hover or _lighten(base, 0.12))
    pressed8 = _hex8(pressed or _darken(base, 0.4))
    selected8 = _hex8(selected or hover or _lighten(base, 0.12))
    on8 = _hex8(on or _on_color(base))
    disabled8 = base8  # full alpha; COSMIC also has disabled_border
    on_dis8 = _hex8(_darken(on or _on_color(base), 0.5), alpha="80")
    border8 = base8
    dis_border8 = _hex8(base, alpha="80")
    vals = {
        "base": base8,
        "hover": hover8,
        "pressed": pressed8,
        "selected": selected8,
        "selected_text": base8,
        "focus": base8,
        "divider": _hex8(divider),
        "on": on8,
        "disabled": disabled8,
        "on_disabled": on_dis8,
        "border": border8,
        "disabled_border": dis_border8,
    }
    lines = ["("]
    for k in _COMPONENT_KEYS:
        lines.append(f'    {k}: "{vals[k]}",')
    lines.append(")")
    return "\n".join(lines) + "\n"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _patch_surface_accent(path: Path, accent: str) -> bool:
    """Update focus / selected_text hex fields in a surface RON file."""
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    accent8 = _hex8(accent)
    new, n = re.subn(
        r'(selected_text|focus):\s*"#[0-9A-Fa-f]{8}"',
        rf'\1: "{accent8}"',
        text,
    )
    if n:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def apply_cosmic_palette(colors: list[str], *, dark: bool = True) -> list[Path]:
    """Write COSMIC v2 theme files from a wallust/pywal color list.

    Returns paths written.
    """
    if len(colors) < 8:
        return []

    # wallust slots: 0 bg, 1–6 accents, 7 fg (common layout)
    accent = colors[4] if len(colors) > 4 else colors[1]
    destructive = colors[1]
    success = colors[2]
    warning = colors[3]
    # link / text buttons use a cooler accent if available
    link = colors[6] if len(colors) > 6 else accent

    theme = "CosmicTheme.Dark" if dark else "CosmicTheme.Light"
    base = home() / ".config" / "cosmic" / f"com.system76.{theme}"
    written: list[Path] = []

    # Prefer v2; also mirror to v1 for older builds
    for ver in ("v2", "v1"):
        root = base / ver
        if ver == "v1" and not root.is_dir() and (base / "v2").is_dir():
            # Only create v1 if it already existed (legacy)
            continue
        if ver == "v2":
            root.mkdir(parents=True, exist_ok=True)

        if not root.is_dir() and ver == "v1":
            continue

        simple = {
            "accent": accent,
            "accent_button": accent,
            "button": accent if dark else _darken(accent, 0.1),
            "destructive": destructive,
            "destructive_button": destructive,
            "success": success,
            "warning": warning,
            "warning_button": warning,
            "text_button": link,
            "link_button": link,
            "icon_button": accent,
        }
        for name, color in simple.items():
            path = root / name
            if ver == "v2" or path.is_file() or name in ("accent", "accent_button"):
                if ver == "v1":
                    # v1 uses float RGB — leave existing pure-Python v2 as source of truth;
                    # still write accent for tools that read v1
                    if name not in ("accent", "accent_button"):
                        continue
                    _write(path, _component_v1_float(color))
                else:
                    _write(path, component_ron(color))
                written.append(path)

        if ver == "v2":
            for surface in _SURFACE_FILES:
                if _patch_surface_accent(root / surface, accent):
                    written.append(root / surface)

    # Builder theme (live-edit copy COSMIC settings uses)
    builder = home() / ".config" / "cosmic" / f"com.system76.{theme}.Builder" / "v2"
    if builder.is_dir():
        for name in ("accent", "accent_button"):
            p = builder / name
            _write(p, component_ron(accent))
            written.append(p)

    return written


def _component_v1_float(base: str) -> str:
    """Legacy v1 float-component accent (kept for compatibility)."""
    r, g, b = hex_to_rgb(base)
    br, bg, bb = r / 255.0, g / 255.0, b / 255.0
    hr = min(1.0, br + 0.05)
    hg = min(1.0, bg + 0.05)
    hb = min(1.0, bb + 0.05)
    on = 0.0 if (0.299 * br + 0.587 * bg + 0.114 * bb) > 0.5 else 1.0
    return f"""(
    base: (
        red: {br:.4f},
        green: {bg:.4f},
        blue: {bb:.4f},
        alpha: 1.0,
    ),
    hover: (
        red: {hr:.4f},
        green: {hg:.4f},
        blue: {hb:.4f},
        alpha: 1.0,
    ),
    pressed: (
        red: {br * 0.6:.4f},
        green: {bg * 0.6:.4f},
        blue: {bb * 0.6:.4f},
        alpha: 1.0,
    ),
    selected: (
        red: {hr:.4f},
        green: {hg:.4f},
        blue: {hb:.4f},
        alpha: 1.0,
    ),
    selected_text: (
        red: {br:.4f},
        green: {bg:.4f},
        blue: {bb:.4f},
        alpha: 1.0,
    ),
    focus: (
        red: {br:.4f},
        green: {bg:.4f},
        blue: {bb:.4f},
        alpha: 1.0,
    ),
    divider: (
        red: 0.0,
        green: 0.0,
        blue: 0.0,
        alpha: 1.0,
    ),
    on: (
        red: {on},
        green: {on},
        blue: {on},
        alpha: 1.0,
    ),
    disabled: (
        red: {br:.4f},
        green: {bg:.4f},
        blue: {bb:.4f},
        alpha: 1.0,
    ),
    on_disabled: (
        red: {br * 0.5:.4f},
        green: {bg * 0.5:.4f},
        blue: {bb * 0.5:.4f},
        alpha: 1.0,
    ),
    border: (
        red: {br:.4f},
        green: {bg:.4f},
        blue: {bb:.4f},
        alpha: 1.0,
    ),
    disabled_border: (
        red: {br:.4f},
        green: {bg:.4f},
        blue: {bb:.4f},
        alpha: 0.5,
    ),
)
"""


class CosmicThemeOp:
    name = "cosmic-theme"

    def enabled(self, ctx: WallpaperContext) -> bool:
        if not getattr(ctx.ops, "enable_cosmic_theme", True):
            return False
        # Run when COSMIC session is active or theme dirs exist (headless apply)
        if getattr(ctx.de, "cosmic", False):
            return True
        dark = home() / ".config" / "cosmic" / "com.system76.CosmicTheme.Dark"
        return dark.is_dir()

    def run(self, ctx: WallpaperContext) -> bool:
        colors = read_wal_colors()
        if len(colors) < 8:
            debug_op(self.name, "not enough wal colors (run wallust first)", ctx)
            return False

        written = apply_cosmic_palette(colors, dark=True)
        # Light theme if user has v2 light components
        light_v2 = (
            home()
            / ".config"
            / "cosmic"
            / "com.system76.CosmicTheme.Light"
            / "v2"
        )
        if light_v2.is_dir():
            written.extend(apply_cosmic_palette(colors, dark=False))

        if not written:
            debug_op(self.name, "no cosmic theme files written", ctx)
            return False

        debug_op(
            self.name,
            f"wrote {len(written)} COSMIC theme file(s) (v2 hex accent)",
            ctx,
        )
        log.info("COSMIC theme updated from wallpaper palette (%s files)", len(written))
        return True
