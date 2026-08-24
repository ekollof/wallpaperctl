"""Intelligent palette color selection (select-palette-color port)."""

from __future__ import annotations

from pathlib import Path

from wallpaperctl.util import hex_to_rgb, home, read_wal_colors


def _palette(
    colors_file: Path | None, colors: list[str] | None
) -> list[str]:
    """In-memory palette if given, else read the wal colors file."""
    if colors is not None:
        return colors
    return read_wal_colors(colors_file or home() / ".cache" / "wal" / "colors")


def select_palette_line(
    strategy: str = "warmest",
    colors_file: Path | None = None,
    *,
    fixed_line: int | None = None,
    colors: list[str] | None = None,
) -> int:
    if strategy == "fixed" and fixed_line is not None:
        return fixed_line

    palette = _palette(colors_file, colors)
    if not palette:
        return 12

    # Lines 4-16 in 1-based indexing → indices 3..min(15, len-1)
    start = 3
    end = min(16, len(palette))
    if start >= end:
        return min(12, len(palette))

    best_line = 12
    best_score: float | None = None

    for i in range(start, end):
        try:
            r, g, b = hex_to_rgb(palette[i])
        except ValueError:
            continue
        line = i + 1  # 1-based
        if strategy == "least_blue":
            score = b - ((r + g) / 2)
            better = best_score is None or score < best_score
        elif strategy == "warmest":
            score = r - b + (r - g) / 2
            better = best_score is None or score > best_score
        elif strategy == "most_saturated":
            score = float(max(r, g, b) - min(r, g, b))
            better = best_score is None or score > best_score
        elif strategy == "coolest":
            score = r - b + (r - g) / 2
            better = best_score is None or score < best_score
        elif strategy == "brightest":
            score = (r + g + b) / 3
            better = best_score is None or score > best_score
        else:
            return 12
        if better:
            best_score = score
            best_line = line

    return best_line


def color_at_line(
    line: int,
    colors_file: Path | None = None,
    *,
    colors: list[str] | None = None,
) -> str | None:
    palette = _palette(colors_file, colors)
    if not palette or line < 1 or line > len(palette):
        return None
    c = palette[line - 1].upper()
    if not c.startswith("#"):
        c = f"#{c}"
    return c


def pick_theme_color(
    strategy: str,
    *,
    fixed_line: int,
    colors_file: Path | None = None,
    colors: list[str] | None = None,
) -> tuple[str | None, int]:
    """Resolve a wallust palette color the same way OpenRGB / HA / OpenLinkHub do.

    Returns ``(hex_color_or_None, 1-based palette line)``.
    """
    if strategy == "fixed":
        line = fixed_line
    else:
        line = select_palette_line(strategy, colors_file, colors=colors)
    return color_at_line(line, colors_file, colors=colors), line
