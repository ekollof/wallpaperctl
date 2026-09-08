"""Terminal *background* opacity so wallpaper shows through empty cells.

Omarchy terminals: Kitty, Ghostty, Foot, Alacritty.

Hyprland ``o.window`` opacity fades glyphs. These keys do not:

* Kitty ``background_opacity``
* Ghostty ``background-opacity``
* Foot ``alpha`` (in the existing ``[colors*]`` section)
* Alacritty ``window.opacity`` with ``transparent_background_colors = false``
  (default: only the default background, not cell/text colors)
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from wallpaperctl.util import home, pgrep_exact, run

log = logging.getLogger("wallpaperctl")

BEGIN = "# wallpaperctl: background-opacity-begin"
END = "# wallpaperctl: background-opacity-end"
FOOT_MARK = "wallpaperctl-background-opacity"
ALACRITTY_MARK = "wallpaperctl-background-opacity"
DEFAULT_OPACITY = 0.85


def clamp_opacity(value: float) -> float:
    try:
        opacity = float(value)
    except (TypeError, ValueError):
        return DEFAULT_OPACITY
    return max(0.20, min(1.0, opacity))


def default_terminal_theme_files() -> list[Path]:
    current = home() / ".local" / "state" / "omarchy" / "current" / "theme"
    return [
        current / "kitty.conf",
        current / "ghostty.conf",
        current / "foot.ini",
        current / "alacritty.toml",
        home() / ".config" / "kitty" / "current-theme.conf",
        home() / ".config" / "alacritty" / "alacritty.toml",
    ]


def apply_terminal_background_opacity(
    opacity: float,
    *,
    files: list[Path] | None = None,
    reload: bool = False,
) -> list[Path]:
    """Upsert or strip opacity. Returns changed paths."""
    opacity = clamp_opacity(opacity)
    solid = opacity >= 0.995
    changed: list[Path] = []
    for path in files if files is not None else default_terminal_theme_files():
        if not path.is_file():
            continue
        kind = _kind_for(path)
        if kind is None:
            continue
        try:
            original = path.read_text(encoding="utf-8")
        except OSError as e:
            log.debug("terminal opacity: cannot read %s: %s", path, e)
            continue
        if kind == "foot":
            updated = _apply_foot(original, None if solid else opacity)
        elif kind == "alacritty":
            updated = _apply_alacritty(original, None if solid else opacity)
        else:
            body = "" if solid else _block_body(kind, opacity)
            updated = _upsert_block(original, body)
        if updated == original:
            continue
        try:
            path.write_text(updated, encoding="utf-8")
        except OSError as e:
            log.debug("terminal opacity: cannot write %s: %s", path, e)
            continue
        changed.append(path)
        log.debug("terminal opacity: %s -> %s", path.name, opacity)
    if reload:
        reload_terminals_for_opacity()
    return changed


def reload_terminals_for_opacity() -> None:
    """Live-apply config. Foot is not in omarchy-restart-terminal."""
    if pgrep_exact("kitty"):
        run(["killall", "-SIGUSR1", "kitty"], timeout=5)
    if pgrep_exact("ghostty"):
        run(["killall", "-SIGUSR2", "ghostty"], timeout=5)
    # Foot: SIGUSR1 selects [colors-dark] (where we put alpha). Not a full
    # reload — omarchy-restart-terminal never signals foot.
    if pgrep_exact("foot"):
        run(["killall", "-SIGUSR1", "foot"], timeout=5)
    alacritty = home() / ".config" / "alacritty" / "alacritty.toml"
    if alacritty.is_file():
        try:
            alacritty.touch()
        except OSError:
            pass


def _kind_for(path: Path) -> str | None:
    name = path.name.lower()
    if name in ("kitty.conf", "current-theme.conf", "colors-kitty.conf"):
        return "kitty"
    if name == "ghostty.conf":
        return "ghostty"
    if name == "foot.ini":
        return "foot"
    if name == "alacritty.toml":
        return "alacritty"
    return None


def _block_body(kind: str, opacity: float) -> str:
    value = f"{opacity:.2f}"
    if kind == "kitty":
        return (
            f"{BEGIN}\n"
            "# Background cells only; text stays opaque.\n"
            f"background_opacity {value}\n"
            f"{END}"
        )
    return (
        f"{BEGIN}\n"
        "# Background cells only; text stays opaque.\n"
        f"background-opacity = {value}\n"
        f"{END}"
    )


_BLOCK_RE = re.compile(
    re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?",
    re.DOTALL,
)


def _upsert_block(text: str, body: str) -> str:
    stripped = _BLOCK_RE.sub("", text).rstrip() + "\n"
    if not body:
        return stripped
    return stripped + "\n" + body.rstrip() + "\n"


_FOOT_SECTIONS = ("colors", "colors-dark", "colors-light")
_FOOT_ALPHA_LINE = re.compile(
    r"(?im)^alpha\s*=\s*[0-9.]+[^\n]*$"
)


def _apply_foot(text: str, opacity: float | None) -> str:
    """Put alpha= in existing [colors*] sections. No duplicate section."""
    stripped = _BLOCK_RE.sub("", text)
    present = [
        name
        for name in _FOOT_SECTIONS
        if re.search(rf"(?im)^\[{re.escape(name)}\]\s*$", stripped)
    ]
    if not present:
        present = ["colors-dark"]
    value = None if opacity is None else f"alpha={opacity:.2f}  # {FOOT_MARK}"
    out = stripped
    for name in present:
        out = _upsert_ini_section_key(out, name, _FOOT_ALPHA_LINE, value)
    if value is not None and not re.search(r"(?im)^\[colors", out):
        out = out.rstrip() + f"\n\n[{present[0]}]\n{value}\n"
    return out if out.endswith("\n") else out + "\n"


def _upsert_ini_section_key(
    text: str,
    section: str,
    key_re: re.Pattern[str],
    replacement: str | None,
) -> str:
    header = f"[{section}]"
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    found_header = False
    while i < len(lines):
        line = lines[i]
        if re.match(rf"^\[{re.escape(section)}\]\s*$", line, re.I):
            found_header = True
            out.append(line)
            i += 1
            inserted = replacement is None
            while i < len(lines) and not lines[i].lstrip().startswith("["):
                if key_re.match(lines[i].strip()):
                    if replacement is not None and not inserted:
                        nl = "\n" if lines[i].endswith("\n") else ""
                        out.append(replacement + nl)
                        inserted = True
                    i += 1
                    continue
                out.append(lines[i])
                i += 1
            if replacement is not None and not inserted:
                out.append(replacement + "\n")
            continue
        out.append(line)
        i += 1
    if replacement is not None and not found_header:
        out.append(f"\n{header}\n{replacement}\n")
    return "".join(out)


def _apply_alacritty(text: str, opacity: float | None) -> str:
    """Theme import + user config: window.opacity, text stays opaque.

    ``transparent_background_colors = false`` (Alacritty default) applies
    opacity only to the default background, not glyphs or colored cells.
    """
    stripped = _BLOCK_RE.sub("", text)
    if opacity is None:
        stripped = _strip_alacritty_opacity(stripped)
        return stripped if stripped.endswith("\n") else stripped + "\n"
    value = f"{opacity:.2f}"
    if "[colors.primary]" in stripped or "general.import" in stripped:
        # Theme file (colors only) or user file (imports theme).
        pass
    stripped = _upsert_toml_window_opacity(stripped, value)
    stripped = _ensure_alacritty_opaque_cells(stripped)
    return stripped if stripped.endswith("\n") else stripped + "\n"


_ALACRITTY_OPACITY_RE = re.compile(
    r"(?m)^[ \t]*opacity\s*=\s*[0-9.]+[^\n]*\n?"
)
_ALACRITTY_TBC_RE = re.compile(
    r"(?m)^[ \t]*transparent_background_colors\s*=\s*(?:true|false)[^\n]*\n?"
)


def _strip_alacritty_opacity(text: str) -> str:
    return _ALACRITTY_OPACITY_RE.sub("", text)


def _upsert_toml_window_opacity(text: str, value: str) -> str:
    line = f"opacity = {value}  # {ALACRITTY_MARK}"
    if re.search(r"(?m)^\[window\]\s*$", text):
        return _upsert_ini_section_key(
            text, "window", _ALACRITTY_OPACITY_RE, line
        )
    return text.rstrip() + f"\n\n[window]\n{line}\n"


def _ensure_alacritty_opaque_cells(text: str) -> str:
    line = f"transparent_background_colors = false  # {ALACRITTY_MARK}"
    if re.search(r"(?m)^\[colors\]\s*$", text):
        return _upsert_ini_section_key(
            text, "colors", _ALACRITTY_TBC_RE, line
        )
    # Theme file uses [colors.primary] not [colors]. Append a colors table.
    if "transparent_background_colors" in text:
        return _ALACRITTY_TBC_RE.sub(line + "\n", text, count=1)
    return text.rstrip() + f"\n\n[colors]\n{line}\n"
