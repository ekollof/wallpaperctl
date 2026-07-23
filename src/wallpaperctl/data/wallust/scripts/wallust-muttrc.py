#!/usr/bin/env python3
"""
Generate ~/.cache/wal/colors.muttrc with xterm-256 color indices
derived from the current wallust palette (reads ~/.cache/wal/colors.json).

Called by wallust as a post-hook, or run manually after wallust.

Roles are assigned by sorting palette colors by perceived brightness/saturation
so that visually distinct colors get the most important slots, rather than
blindly using color0-color15 indices which vary wildly between palettes.

Contrast is enforced: if the palette is too washed-out (e.g. all greys), colors
are clamped to safe xterm-256 grey-ramp values so text is always readable.
"""

import json
import sys
import os


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def rgb_to_hsl(r, g, b):
    r, g, b = r / 255, g / 255, b / 255
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2
    if mx == mn:
        h = s = 0.0
    else:
        d = mx - mn
        s = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
        if mx == r:
            h = (g - b) / d + (6 if g < b else 0)
        elif mx == g:
            h = (b - r) / d + 2
        else:
            h = (r - g) / d + 4
        h /= 6
    return h, s, l


def xterm256_rgb(idx):
    if idx < 16:
        system = [
            (0, 0, 0),
            (128, 0, 0),
            (0, 128, 0),
            (128, 128, 0),
            (0, 0, 128),
            (128, 0, 128),
            (0, 128, 128),
            (192, 192, 192),
            (128, 128, 128),
            (255, 0, 0),
            (0, 255, 0),
            (255, 255, 0),
            (0, 0, 255),
            (255, 0, 255),
            (0, 255, 255),
            (255, 255, 255),
        ]
        return system[idx]
    if idx >= 232:
        v = 8 + 10 * (idx - 232)
        return (v, v, v)
    idx -= 16
    b = idx % 6
    g = (idx // 6) % 6
    r = idx // 36

    def cv(i):
        return 0 if i == 0 else 55 + 40 * i

    return (cv(r), cv(g), cv(b))


def xterm_lightness(idx):
    r, g, b = xterm256_rgb(idx)
    _, _, l = rgb_to_hsl(r, g, b)
    return l


def dist(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b))


def nearest_xterm256(hex_color):
    rgb = hex_to_rgb(hex_color)
    candidates = list(range(16, 256))
    candidates.sort(key=lambda i: dist(rgb, xterm256_rgb(i)))
    return candidates


def deduplicate(assignments):
    """
    Each entry is (role_name, ranked_candidates).
    Returns dict role_name -> xterm_idx with no duplicates.
    """
    taken = set()
    result = {}
    for role, ranked in assignments:
        for candidate in ranked:
            if candidate not in taken:
                taken.add(candidate)
                result[role] = candidate
                break
    return result


def lightness_of(h):
    r, g, b = hex_to_rgb(h)
    _, _, l = rgb_to_hsl(r, g, b)
    return l


# Minimum lightness difference required between a fg and bg color pair.
MIN_CONTRAST = 0.30


def contrast_ranked_candidates(fg_idx, bg_idx):
    """
    Return a ranked list of xterm-256 indices (16-255) that:
      1. Have sufficient contrast against bg_idx (lightness diff >= MIN_CONTRAST)
      2. Are ordered by closeness to fg_idx in colour (cube colours first,
         then grey ramp), so deduplication can pick the best available slot.

    If fg_idx already has sufficient contrast it is placed first.
    """
    fg_l = xterm_lightness(fg_idx)
    bg_l = xterm_lightness(bg_idx)

    if bg_l <= 0.5:
        target_l = bg_l + MIN_CONTRAST
    else:
        target_l = bg_l - MIN_CONTRAST
    target_l = max(0.05, min(0.95, target_l))

    fg_rgb = xterm256_rgb(fg_idx)

    def score(i):
        l = xterm_lightness(i)
        if abs(l - bg_l) < MIN_CONTRAST:
            return float("inf")
        color_dist = dist(fg_rgb, xterm256_rgb(i))
        lightness_penalty = abs(l - target_l) * 10000
        return color_dist + lightness_penalty

    # Cube colours first (preserve hue), then grey ramp
    cube = sorted(range(16, 232), key=score)
    grey = sorted(range(232, 256), key=score)
    ranked = cube + grey

    # If original already contrasts, put it at the front
    if abs(fg_l - bg_l) >= MIN_CONTRAST:
        ranked = [fg_idx] + [i for i in ranked if i != fg_idx]

    return ranked


def ensure_contrast(fg_idx, bg_idx):
    """
    Return the best single index for fg_idx that has sufficient contrast
    against bg_idx.  Kept for use outside deduplicate (e.g. status bar).
    """
    ranked = contrast_ranked_candidates(fg_idx, bg_idx)
    return ranked[0]


def main():
    json_path = os.path.expanduser("~/.cache/wal/colors.json")
    out_path = os.path.expanduser("~/.cache/wal/colors.muttrc")

    try:
        with open(json_path) as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: {json_path} not found. Run wallust first.", file=sys.stderr)
        sys.exit(1)

    colors = data["colors"]
    hex_list = [colors[f"color{i}"] for i in range(16)]

    # Use special.background for contrast calculations — this is the actual
    # terminal background color set by wallust/kitty, not color0.
    special_bg_hex = data.get("special", {}).get("background", "#1a1a1a")
    special_bg_light_val = lightness_of(special_bg_hex)

    def lightness(h):
        r, g, b = hex_to_rgb(h)
        _, _, l = rgb_to_hsl(r, g, b)
        return l

    def saturation(h):
        r, g, b = hex_to_rgb(h)
        _, s, _ = rgb_to_hsl(r, g, b)
        return s

    sorted_by_light = sorted(range(16), key=lambda i: lightness(hex_list[i]))
    sorted_by_sat = sorted(
        range(16), key=lambda i: saturation(hex_list[i]), reverse=True
    )

    # bg: always "default" — lets the terminal background (set by wallust/kitty)
    # show through. We only need a bg xterm index for bg_mid (status bar).
    # For contrast calculations we use special.background lightness.

    # bg_mid: least-saturated color that is noticeably lighter than special bg
    # (for status bar — avoid saturated or near-bg choices)
    neutral_candidates = sorted(
        [i for i in range(16) if lightness(hex_list[i]) > special_bg_light_val + 0.15],
        key=lambda i: saturation(hex_list[i]),
    )
    bg_mid_idx = neutral_candidates[0] if neutral_candidates else sorted_by_light[2]

    fg_dim_idx = sorted_by_light[7]
    fg_normal_idx = sorted_by_light[10]
    fg_bright_idx = sorted_by_light[15]
    accent1_idx = sorted_by_sat[0]
    accent2_idx = sorted_by_sat[1]
    accent3_idx = sorted_by_sat[2]
    accent4_idx = sorted_by_sat[3]

    def warmth(h):
        r, g, b = hex_to_rgb(h)
        return r - (g + b) / 2

    warm_idx = max(range(16), key=lambda i: warmth(hex_list[i]))

    # Use special.background lightness as reference for contrast enforcement.
    # We pass a synthetic "bg index" that approximates special.background.
    bg_ref = min(
        range(232, 256), key=lambda i: abs(xterm_lightness(i) - special_bg_light_val)
    )

    # bg_mid uses plain nearest-xterm ranking (it is a background, not a fg).
    # All fg roles use contrast-safe ranked lists so that deduplicate() can
    # assign distinct indices that are *already* guaranteed to contrast — this
    # avoids the grey-palette collapse where a post-hoc ensure_contrast() maps
    # every accent to the same fallback index.
    bg_mid_candidates = nearest_xterm256(hex_list[bg_mid_idx])

    roles = [
        ("bg_mid", bg_mid_candidates),
        (
            "fg_dim",
            contrast_ranked_candidates(
                nearest_xterm256(hex_list[fg_dim_idx])[0], bg_ref
            ),
        ),
        (
            "fg_normal",
            contrast_ranked_candidates(
                nearest_xterm256(hex_list[fg_normal_idx])[0], bg_ref
            ),
        ),
        (
            "fg_bright",
            contrast_ranked_candidates(
                nearest_xterm256(hex_list[fg_bright_idx])[0], bg_ref
            ),
        ),
        (
            "accent1",
            contrast_ranked_candidates(
                nearest_xterm256(hex_list[accent1_idx])[0], bg_ref
            ),
        ),
        (
            "accent2",
            contrast_ranked_candidates(
                nearest_xterm256(hex_list[accent2_idx])[0], bg_ref
            ),
        ),
        (
            "accent3",
            contrast_ranked_candidates(
                nearest_xterm256(hex_list[accent3_idx])[0], bg_ref
            ),
        ),
        (
            "accent4",
            contrast_ranked_candidates(
                nearest_xterm256(hex_list[accent4_idx])[0], bg_ref
            ),
        ),
        (
            "warm",
            contrast_ranked_candidates(nearest_xterm256(hex_list[warm_idx])[0], bg_ref),
        ),
    ]

    c = deduplicate(roles)

    bg_mid = c["bg_mid"]
    fg_dim = c["fg_dim"]
    fg_normal = c["fg_normal"]
    fg_bright = c["fg_bright"]
    accent1 = c["accent1"]
    accent2 = c["accent2"]
    accent3 = c["accent3"]
    accent4 = c["accent4"]
    warm = c["warm"]

    # bg_mid must not be near-white (would clash with fg on status bar)
    if xterm_lightness(bg_mid) > 0.55:
        bg_mid = 240  # xterm grey ramp: rgb(88,88,88)

    # Enforce contrast for status bar fg against bg_mid (separate from main dedup)
    fg_bright_status = ensure_contrast(fg_bright, bg_mid)

    template = f"""\
# Generated by wallust-muttrc.py
# xterm-256 color indices derived from current wallust palette.
# Regenerate by running: ~/.config/wallust/scripts/wallust-muttrc.py
#
# Role assignments (palette hex -> xterm index):
#   special.bg={special_bg_hex}(default)  bg_mid={hex_list[bg_mid_idx]}->{bg_mid}
#   fg_dim={hex_list[fg_dim_idx]}->{fg_dim}  fg_normal={hex_list[fg_normal_idx]}->{fg_normal}  fg_bright={hex_list[fg_bright_idx]}->{fg_bright}
#   accent1(flagged)={hex_list[accent1_idx]}->{accent1}  accent2(unread)={hex_list[accent2_idx]}->{accent2}
#   accent3(search/quote)={hex_list[accent3_idx]}->{accent3}  accent4(attach/tree)={hex_list[accent4_idx]}->{accent4}
#   warm(bold/error)={hex_list[warm_idx]}->{warm}

# Clear pattern-based color lists before re-applying so that re-sourcing this
# file (e.g. via timeout-hook) replaces old palette entries instead of
# appending to them (NeoMutt evaluates list colors front-to-back; old entries
# would otherwise shadow the new ones).
# Only these objects support patterns (and thus accumulate): body, header,
# index, index_author, index_flags, index_label, index_number, index_subject,
# index_tags, status.  All others (quoted*, sidebar_*, normal, etc.) are simple
# and overwrite directly - no uncolor needed.
uncolor body *
uncolor header *
uncolor index *
uncolor index_author *
uncolor index_flags *
uncolor index_label *
uncolor index_number *
uncolor index_subject *
uncolor index_tags *

# Simple colors (overwrite directly)
color normal        color{fg_dim}          default
color indicator     color{fg_bright_status} color{bg_mid}
color markers       color{warm}            default
color error         color{warm}            default
color tilde         color{fg_dim}          default
color attachment    color{accent4}         default
color search        color{accent3}         default
color status        color{fg_bright_status} color{bg_mid}
color tree          color{accent4}         default
color quoted        color{accent3}         default
color quoted1       color{accent3}         default
color quoted2       color{accent4}         default
color quoted3       color{fg_dim}          default
color quoted4       color{warm}            default
color signature     color{fg_dim}          default
color underline     color{fg_normal}       default
color message       color{accent3}         default
color sidebar_highlight  color{fg_bright_status} color{bg_mid}
color sidebar_flagged    color{accent1}    default
color sidebar_new        color{accent2}    default
color sidebar_divider    color{fg_dim}     default

# Pattern-based colors (need uncolor before re-sourcing)
color body          color{fg_normal} default ".*"
color header        color{fg_dim}    default "."
color header        color{fg_bright} default "^(From|Subject):"
color index         color{fg_normal} default "~A"
color index         color{accent2}   default "~N"
color index         color{accent1}   default "~F"
color index         color{fg_bright} default "~v~(!~N)"
color index         color{accent2}   default "~v~(~N)"
color index         color{accent3}   default "~p!~F"
color index         color{accent1}   default "~N~p"
color index         color{fg_bright} default "~T"
color index         color{fg_dim}    default "~D"
color index_author  color{fg_normal} default ".*"
color index_flags   color{accent1}   default ".*"
color index_label   color{accent4}   default ".*"
color index_number  color{fg_dim}    default ".*"
color index_subject color{fg_normal} default ".*"
color index_tags    color{accent2}   default ".*"
"""

    with open(out_path, "w") as f:
        f.write(template)

    print(f"Written: {out_path}")


if __name__ == "__main__":
    main()
