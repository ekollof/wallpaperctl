"""Apply wallust palette to System76 COSMIC desktop theme (v2 hex format).

Aesthetic goals (not a full neon recolor):
  * Pick accent via palette strategy, then soften toward wallpaper bg
  * Write **accent** / **accent_button** only by default (+ soft surface tints)
  * Derive dark/light surfaces from color0/color7 so greys match the wallpaper
  * Leave semantic success/warning/destructive alone unless mode=full
  * Soft window-chrome borders (mixed toward bg) so focus rings are not neon

COSMIC reads ``CosmicTheme.{Dark,Light}/v2/*`` as 8-digit hex RON
(``"#RRGGBBAA"``).
"""

from __future__ import annotations

import logging
from pathlib import Path

from wallpaperctl.context import WallpaperContext
from wallpaperctl.theme.base import debug_op
from wallpaperctl.theme.palette import color_at_line, select_palette_line
from wallpaperctl.util import hex_to_rgb, home, read_wal_colors

log = logging.getLogger("wallpaperctl")

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

# Modes: accent = chrome only; surfaces = accent + bg/primary/secondary;
# full = also recolor semantic + generic buttons (old aggressive behavior).
_VALID_MODES = frozenset({"accent", "surfaces", "full"})


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
    t = max(0.0, min(1.0, t))
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


def _desaturate(c: str, t: float = 0.25) -> str:
    """Pull *c* toward its luma grey by *t* (reduces neon)."""
    r, g, b = hex_to_rgb(c)
    grey = int(round(0.299 * r + 0.587 * g + 0.114 * b))
    ghex = f"#{grey:02X}{grey:02X}{grey:02X}"
    return _mix(c, ghex, t)


def _luma(c: str) -> float:
    r, g, b = hex_to_rgb(c)
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


def _on_color(c: str) -> str:
    return "#000000" if _luma(c) > 0.55 else "#FFFFFF"


def _ensure_hash(c: str) -> str:
    c = c.strip()
    if not c.startswith("#"):
        c = f"#{c}"
    return c.upper() if len(c.lstrip("#")) in (6, 8) else c


def pick_accent(
    colors: list[str],
    *,
    strategy: str = "warmest",
    softness: float = 0.4,
    desaturate: float = 0.2,
) -> tuple[str, str]:
    """Return (raw_accent, soft_accent) for chrome.

    *softness* mixes accent toward wallpaper bg (color0).
    *desaturate* tames neon after softening.
    """
    bg = _ensure_hash(colors[0]) if colors else "#1B1B1B"
    # Prefer palette strategy over fixed color4
    line = select_palette_line(strategy)
    raw = color_at_line(line)
    if not raw:
        raw = colors[4] if len(colors) > 4 else (colors[1] if len(colors) > 1 else "#888888")
    raw = _ensure_hash(raw)
    # Soft chrome: pull toward bg so window borders aren't neon stickers
    soft = _mix(raw, bg, max(0.0, min(0.85, softness)))
    soft = _desaturate(soft, max(0.0, min(0.8, desaturate)))
    # Keep a minimum separation from bg so accent is still visible
    if abs(_luma(soft) - _luma(bg)) < 0.08:
        soft = _lighten(soft, 0.15) if _luma(bg) < 0.5 else _darken(soft, 0.15)
    return raw, soft


def component_ron(
    base: str,
    *,
    hover: str | None = None,
    pressed: str | None = None,
    selected: str | None = None,
    divider: str | None = None,
    on: str | None = None,
    border: str | None = None,
    soft_border: bool = True,
    bg: str | None = None,
) -> str:
    """Serialize a COSMIC v2 Component as RON."""
    base8 = _hex8(base)
    hover8 = _hex8(hover or _lighten(base, 0.1))
    pressed8 = _hex8(pressed or _darken(base, 0.28))
    selected8 = _hex8(selected or hover or _lighten(base, 0.1))
    on8 = _hex8(on or _on_color(base))
    # Soft border: mix accent toward bg so active window chrome is subtle
    if border is not None:
        border8 = _hex8(border)
    elif soft_border and bg is not None:
        border8 = _hex8(_mix(base, bg, 0.45))
    else:
        border8 = base8
    div = divider or ("#000000" if _luma(base) > 0.4 else "#FFFFFF")
    vals = {
        "base": base8,
        "hover": hover8,
        "pressed": pressed8,
        "selected": selected8,
        "selected_text": base8,
        "focus": base8,
        "divider": _hex8(div, alpha="FF" if divider else "33"),
        "on": on8,
        "disabled": base8,
        "on_disabled": _hex8(_darken(on or _on_color(base), 0.5), alpha="80"),
        "border": border8,
        "disabled_border": _hex8(base, alpha="80"),
    }
    lines = ["("]
    for k in _COMPONENT_KEYS:
        lines.append(f'    {k}: "{vals[k]}",')
    lines.append(")")
    return "\n".join(lines) + "\n"


def surface_ron(
    *,
    base: str,
    fg: str,
    accent: str,
    component_lift: float = 0.06,
    dark: bool = True,
) -> str:
    """Container surface (background / primary / secondary) for COSMIC v2."""
    base = _ensure_hash(base)
    fg = _ensure_hash(fg)
    accent = _ensure_hash(accent)
    if dark:
        comp = _lighten(base, component_lift)
        hover = _lighten(comp, 0.08)
        pressed = _lighten(comp, 0.14)
        divider = _lighten(base, 0.18)
        border = _lighten(base, 0.35)
        small_a = "40"
    else:
        comp = _darken(base, component_lift)
        hover = _darken(comp, 0.06)
        pressed = _darken(comp, 0.12)
        divider = _darken(base, 0.12)
        border = _darken(base, 0.25)
        small_a = "40"

    # Focus/selection use soft accent, not full neon
    focus = accent
    on_fg = fg if abs(_luma(fg) - _luma(base)) > 0.25 else _on_color(base)

    return f"""(
    base: "{_hex8(base)}",
    component: (
        base: "{_hex8(comp)}",
        hover: "{_hex8(hover)}",
        pressed: "{_hex8(pressed)}",
        selected: "{_hex8(hover)}",
        selected_text: "{_hex8(focus)}",
        focus: "{_hex8(focus)}",
        divider: "{_hex8("#FFFFFF" if dark else "#000000", alpha="33")}",
        on: "{_hex8(on_fg)}",
        disabled: "{_hex8(comp, alpha="80")}",
        on_disabled: "{_hex8(on_fg, alpha="A6")}",
        border: "{_hex8(border)}",
        disabled_border: "{_hex8(border, alpha="80")}",
    ),
    divider: "{_hex8(divider)}",
    on: "{_hex8(on_fg)}",
    small_widget: "{_hex8(comp, alpha=small_a)}",
)
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def apply_cosmic_palette(
    colors: list[str],
    *,
    dark: bool = True,
    mode: str = "surfaces",
    strategy: str = "warmest",
    softness: float = 0.42,
    desaturate: float = 0.22,
) -> list[Path]:
    """Write COSMIC v2 theme files from a wallust/pywal color list.

    Returns paths written.
    """
    if len(colors) < 8:
        return []

    mode = mode if mode in _VALID_MODES else "surfaces"
    bg = _ensure_hash(colors[0])
    fg = _ensure_hash(colors[7] if len(colors) > 7 else "#F5F5F5")

    # Ensure bg is on the right side of mid-luma for the theme variant
    if dark and _luma(bg) > 0.45:
        bg = _darken(bg, 0.55)
    if not dark and _luma(bg) < 0.55:
        bg = _lighten(bg, 0.55)

    raw_accent, soft_accent = pick_accent(
        colors, strategy=strategy, softness=softness, desaturate=desaturate
    )
    # For light themes, soft_accent may need a bit more weight
    if not dark:
        soft_accent = _mix(raw_accent, bg, max(0.15, softness * 0.5))
        soft_accent = _desaturate(soft_accent, desaturate * 0.5)

    theme = "CosmicTheme.Dark" if dark else "CosmicTheme.Light"
    base_dir = home() / ".config" / "cosmic" / f"com.system76.{theme}"
    written: list[Path] = []

    for ver in ("v2", "v1"):
        root = base_dir / ver
        if ver == "v2":
            root.mkdir(parents=True, exist_ok=True)
        elif not root.is_dir():
            continue

        # --- accent chrome (always) ---
        accent_files = ("accent", "accent_button")
        for name in accent_files:
            path = root / name
            if ver == "v1":
                if name == "accent" or path.is_file():
                    _write(path, _component_v1_float(soft_accent))
                    written.append(path)
            else:
                _write(
                    path,
                    component_ron(
                        soft_accent,
                        hover=_lighten(soft_accent, 0.08),
                        pressed=_darken(soft_accent, 0.22),
                        soft_border=True,
                        bg=bg,
                    ),
                )
                written.append(path)

        if ver != "v2":
            continue

        # --- surfaces from wallpaper bg ---
        if mode in ("surfaces", "full"):
            surfaces = {
                "background": (bg, 0.07),
                "primary": (_lighten(bg, 0.035) if dark else _darken(bg, 0.04), 0.06),
                "secondary": (_lighten(bg, 0.07) if dark else _darken(bg, 0.08), 0.05),
            }
            for name, (surf_base, lift) in surfaces.items():
                path = root / name
                _write(
                    path,
                    surface_ron(
                        base=surf_base,
                        fg=fg,
                        accent=soft_accent,
                        component_lift=lift,
                        dark=dark,
                    ),
                )
                written.append(path)

            # Transparent variants: same bases with alpha-ish small_widget already set
            for name, src in (
                ("transparent_background", "background"),
                ("transparent_primary", "primary"),
                ("transparent_secondary", "secondary"),
            ):
                src_path = root / src
                if src_path.is_file():
                    text = src_path.read_text(encoding="utf-8")
                    # slight extra transparency cue on small_widget only (already alpha)
                    dst = root / name
                    _write(dst, text)
                    written.append(dst)

        # --- full mode: optional semantic / generic buttons ---
        if mode == "full":
            destructive = _ensure_hash(colors[1] if len(colors) > 1 else "#C01C28")
            success = _ensure_hash(colors[2] if len(colors) > 2 else "#26A269")
            warning = _ensure_hash(colors[3] if len(colors) > 3 else "#E5A50A")
            for name, color in (
                ("destructive", destructive),
                ("destructive_button", destructive),
                ("success", success),
                ("warning", warning),
                ("warning_button", warning),
                ("text_button", soft_accent),
                ("link_button", soft_accent),
                ("icon_button", soft_accent),
                ("button", soft_accent),
            ):
                path = root / name
                _write(
                    path,
                    component_ron(color, soft_border=True, bg=bg),
                )
                written.append(path)

    # Builder (settings live copy)
    builder = home() / ".config" / "cosmic" / f"com.system76.{theme}.Builder" / "v2"
    if builder.is_dir():
        for name in ("accent", "accent_button"):
            p = builder / name
            _write(
                p,
                component_ron(soft_accent, soft_border=True, bg=bg),
            )
            written.append(p)

    log.debug(
        "COSMIC %s mode=%s accent raw=%s soft=%s",
        theme,
        mode,
        raw_accent,
        soft_accent,
    )
    return written


def _component_v1_float(base: str) -> str:
    """Legacy v1 float-component accent (compat only)."""
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
        if getattr(ctx.de, "cosmic", False):
            return True
        dark = home() / ".config" / "cosmic" / "com.system76.CosmicTheme.Dark"
        return dark.is_dir()

    def run(self, ctx: WallpaperContext) -> bool:
        # Keep greeter/lock wallpaper state in sync with the session image.
        # (cosmic-greeter reads BgState, not only CosmicBackground config.)
        try:
            from wallpaperctl.set.cosmic import sync_cosmic_wallpaper

            ok_bg, bg_detail = sync_cosmic_wallpaper(ctx.path)
            debug_op(self.name, f"lock/session wallpaper: {bg_detail}", ctx)
            if not ok_bg:
                log.warning("COSMIC wallpaper sync: %s", bg_detail)
        except Exception as e:
            log.warning("COSMIC wallpaper sync failed: %s", e)

        colors = read_wal_colors()
        if len(colors) < 8:
            debug_op(self.name, "not enough wal colors (run wallust first)", ctx)
            # Wallpaper state may still have been updated
            return True

        mode = str(getattr(ctx.ops, "cosmic_theme_mode", "surfaces") or "surfaces")
        strategy = str(
            getattr(ctx.ops, "cosmic_accent_strategy", None)
            or getattr(ctx.ops, "rgb_color_strategy", "warmest")
            or "warmest"
        )
        softness = float(getattr(ctx.ops, "cosmic_accent_softness", 0.42))
        desat = float(getattr(ctx.ops, "cosmic_accent_desaturate", 0.22))

        kwargs = dict(
            mode=mode,
            strategy=strategy,
            softness=softness,
            desaturate=desat,
        )
        written = apply_cosmic_palette(colors, dark=True, **kwargs)
        light_v2 = (
            home() / ".config" / "cosmic" / "com.system76.CosmicTheme.Light" / "v2"
        )
        if light_v2.is_dir():
            written.extend(apply_cosmic_palette(colors, dark=False, **kwargs))

        if not written:
            debug_op(self.name, "no cosmic theme files written", ctx)
            return True  # wallpaper sync may still have succeeded

        raw, soft = pick_accent(
            colors, strategy=strategy, softness=softness, desaturate=desat
        )
        debug_op(
            self.name,
            f"mode={mode} strategy={strategy} soft={softness} "
            f"accent {raw} → {soft} ({len(written)} files)",
            ctx,
        )
        log.info(
            "COSMIC theme updated (mode=%s, soft accent %s, %s files) + lock wallpaper",
            mode,
            soft,
            len(written),
        )
        return True
