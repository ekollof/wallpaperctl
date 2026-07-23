"""Intelligent palette color selection (select-palette-color port)."""

from __future__ import annotations

from pathlib import Path

from wallpaperctl.util import hex_to_rgb, home, read_wal_colors


def select_palette_line(
    strategy: str = "warmest",
    colors_file: Path | None = None,
    *,
    fixed_line: int | None = None,
) -> int:
    if strategy == "fixed" and fixed_line is not None:
        return fixed_line

    colors = read_wal_colors(colors_file or home() / ".cache" / "wal" / "colors")
    if not colors:
        return 12

    # Lines 4-16 in 1-based indexing → indices 3..min(15, len-1)
    start = 3
    end = min(16, len(colors))
    if start >= end:
        return min(12, len(colors))

    best_line = 12
    best_score: float | None = None

    for i in range(start, end):
        try:
            r, g, b = hex_to_rgb(colors[i])
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


def color_at_line(line: int, colors_file: Path | None = None) -> str | None:
    colors = read_wal_colors(colors_file)
    if not colors or line < 1 or line > len(colors):
        return None
    c = colors[line - 1].upper()
    if not c.startswith("#"):
        c = f"#{c}"
    return c
