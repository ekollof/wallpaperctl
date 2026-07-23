#!/usr/bin/env python3
"""Ensure Kitty ANSI colors stay readable for remote TUIs (htop, etc.).

Wallust's wallpaper palette often puts mid/dark tones in color1–6 / color9–14.
htop maps CPU% to ANSI green (color2 / bright color10). If those are muddy,
remote htop is unreadable even though the local UI looks fine.

This rewrites the active kitty theme in place after wallust generates it.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

THEME = Path.home() / ".config/kitty/current-theme.conf"
# Follow symlink (themes/noctalia.conf)
THEME = THEME.resolve() if THEME.exists() else Path.home() / ".config/kitty/themes/noctalia.conf"

# Small terminal UI (htop CPU%, git, ls) needs more than WCAG "UI component" 3:1.
MIN_CONTRAST = 5.5
# How hard to push toward white each step when lifting a color.
LIFT = 0.22

# Slots that must stay bright (remote apps: htop, ls --color, git, etc.)
# color2 / color10 = ANSI green — htop CPU% column.
BRIGHT_SLOTS = {
    "color1",
    "color2",
    "color3",
    "color4",
    "color5",
    "color6",
    "color7",
    "color9",
    "color10",
    "color11",
    "color12",
    "color13",
    "color14",
    "color15",
    "foreground",
    "url_color",
    "active_border_color",
}

# Prefer these brighter palette slots when a primary ANSI color is still dull
# after lifting (wallust often puts the vivid cyan/green in color6/14).
GREEN_FALLBACKS = ("color6", "color14", "color4", "color12")


def parse_hex(h: str) -> tuple[int, int, int]:
    h = h.strip().lstrip("#")
    if len(h) != 6:
        raise ValueError(h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def to_hex(r: float, g: float, b: float) -> str:
    return f"#{int(round(max(0, min(255, r)))):02x}{int(round(max(0, min(255, g)))):02x}{int(round(max(0, min(255, b)))):02x}"


def lin(c: float) -> float:
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rel_lum(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    L1, L2 = rel_lum(a), rel_lum(b)
    hi, lo = max(L1, L2), min(L1, L2)
    return (hi + 0.05) / (lo + 0.05)


def lighten_toward_white(rgb: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    r, g, b = rgb
    return (
        int(r + (255 - r) * amount),
        int(g + (255 - g) * amount),
        int(b + (255 - b) * amount),
    )


def ensure_contrast(fg: tuple[int, int, int], bg: tuple[int, int, int]) -> tuple[int, int, int]:
    out = fg
    for _ in range(24):
        if contrast(out, bg) >= MIN_CONTRAST and rel_lum(out) > rel_lum(bg) + 0.04:
            return out
        out = lighten_toward_white(out, LIFT)
    return out


def main() -> int:
    path = THEME
    if not path.is_file():
        print(f"no theme at {path}", file=sys.stderr)
        return 1

    text = path.read_text()
    # key -> hex
    kv: dict[str, str] = {}
    for m in re.finditer(r"^(?P<k>[a-z0-9_]+)\s+(?P<v>#[0-9A-Fa-f]{6})\s*$", text, re.M):
        kv[m.group("k")] = m.group("v")

    bg_hex = kv.get("background") or kv.get("color0")
    if not bg_hex:
        print("no background in theme", file=sys.stderr)
        return 1
    bg = parse_hex(bg_hex)

    def set_key(key: str, new: str) -> None:
        nonlocal text, changed
        old = kv.get(key)
        if not old or old.lower() == new.lower():
            return
        text, n = re.subn(
            rf"^{re.escape(key)}\s+{re.escape(old)}\s*$",
            f"{key} {new}",
            text,
            count=1,
            flags=re.M | re.I,
        )
        if n:
            kv[key] = new
            changed += 1
            print(f"{key}: {old} -> {new}  (contrast {contrast(parse_hex(new), bg):.2f})")

    changed = 0
    for key in BRIGHT_SLOTS:
        if key not in kv:
            continue
        old = kv[key]
        new_rgb = ensure_contrast(parse_hex(old), bg)
        set_key(key, to_hex(*new_rgb))

    # If green is still the dullest accent, promote a vivid fallback (htop CPU%).
    def best_green() -> str | None:
        candidates = []
        for k in ("color2", "color10", *GREEN_FALLBACKS):
            if k in kv:
                candidates.append(kv[k])
        if not candidates:
            return None
        # Highest luminance among candidates that already clear contrast
        ranked = sorted(candidates, key=lambda h: rel_lum(parse_hex(h)), reverse=True)
        return ranked[0]

    green = best_green()
    if green:
        for k in ("color2", "color10"):
            if k in kv and rel_lum(parse_hex(kv[k])) + 0.02 < rel_lum(parse_hex(green)):
                set_key(k, green)


    # htop PROCESS_SHADOW = bold Magenta (ColorPairGrayBlack) → color5 / color13.
    # For CPU% < 0.05 htop uses this "gray" hack. Magenta must stay LIGHT.
    shadow_target = "#a8d4c4"
    for k in ("color5", "color13"):
        if k in kv:
            # Never let wallust leave a dark magenta here
            if contrast(parse_hex(kv[k]), bg) < 7.0 or rel_lum(parse_hex(kv[k])) < 0.35:
                set_key(k, shadow_target)

    # Vivid green for real COLOR_GREEN uses (meters, threads, non-shadow)
    for k in ("color2", "color10"):
        if k in kv and rel_lum(parse_hex(kv[k])) < 0.45:
            set_key(k, to_hex(*ensure_contrast(lighten_toward_white(parse_hex(kv[k]), 0.35), bg)))

    # Keep bright-green pair in sync
    if "color2" in kv and "color10" in kv and kv["color10"].lower() != kv["color2"].lower():
        set_key("color10", kv["color2"])

    path.write_text(text)
    print(f"updated {path} ({changed} colors lifted)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
