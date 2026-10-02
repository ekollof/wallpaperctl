"""wallust version compatibility (palette names differ per major version).

wallust 3.x palettes are the ``*16`` family (``dark16``, ...); ``kmeans``
there is a backend value, not a palette, so commit a640e91 switched the
default to ``dark16``. wallust 4.x renamed the palette set to
``salience`` / ``ansi`` / ``kmeans`` and rejects ``dark16`` — both on the
CLI and when parsing ``wallust.toml``. Detect the installed major version
and resolve an effective palette instead of hardcoding one name.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from wallpaperctl.util import run

log = logging.getLogger("wallpaperctl")

_VERSION_RE = re.compile(r"^wallust\s+(\d+)\.", re.IGNORECASE)

#: Default palette per wallust major version.
WALLUST_DEFAULT_PALETTE = {3: "dark16", 4: "kmeans"}

#: Palettes known-valid per major (from ``wallust run --help``).
WALLUST_VALID_PALETTES = {
    3: {"dark16"},
    4: {"salience", "ansi", "kmeans"},
}

#: Palettes that only ever meant "the other major's default" (i.e. values
#: wallpaperctl itself used as defaults). These are safe to translate when
#: the installed wallust disagrees; anything else passes through untouched
#: so explicit user choices are never silently rewritten.
_CROSS_MAJOR_DEFAULTS = {"dark16", "kmeans"}


def wallust_major_version() -> int | None:
    """Return the installed wallust major version, or None if unknown."""
    try:
        r = run(["wallust", "--version"], timeout=10)
    except Exception:
        return None
    if r.returncode != 0:
        return None
    out = (r.stdout or "") + (r.stderr or "")
    m = _VERSION_RE.search(out.strip())
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def resolve_wallust_palette(requested: str | None) -> str:
    """Map a configured palette to one the installed wallust accepts.

    ``"auto"`` (the default) means the per-major default. A value that is
    the other major's default (e.g. ``dark16`` on wallust 4) is translated
    to this major's default so upgrades/downgrades keep working. Explicit
    values valid for the installed major — and anything when the version
    is unknown — pass through unchanged.
    """
    if not requested or requested == "auto":
        major = wallust_major_version()
        return WALLUST_DEFAULT_PALETTE.get(major or 0, "kmeans")
    major = wallust_major_version()
    if major is None:
        return requested
    valid = WALLUST_VALID_PALETTES.get(major)
    if valid is not None and requested in valid:
        return requested
    if requested in _CROSS_MAJOR_DEFAULTS:
        default = WALLUST_DEFAULT_PALETTE.get(major)
        if default is not None:
            log.info(
                "wallust v%d does not accept palette %r; using %r",
                major,
                requested,
                default,
            )
            return default
    return requested


def canonical_config_text(text: str) -> str:
    """Canonicalize the top-level palette line for config comparison.

    Lets variant checks treat ``dark16``/``kmeans`` (wallpaperctl's own
    per-major defaults) as equal, so a version-normalized install still
    compares as the packaged variant instead of flapping reinstalls.
    """
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("palette") and "=" in stripped:
            key, _, value = stripped.partition("=")
            if key.strip() == "palette" and value.strip().strip("\"'") in _CROSS_MAJOR_DEFAULTS:
                line = line.replace(value.strip(), '"PALETTE"')
        out.append(line)
    return "".join(out)


def normalize_wallust_config_palette(path: str | Path) -> bool:
    """Rewrite a stale cross-major default palette in a wallust.toml.

    Only touches the top-level ``palette = "..."`` line, and only when its
    value is wallpaperctl's default for the *other* major (never user
    customs). Returns True when the file was changed. Never raises —
    callers treat config normalization as best-effort.
    """
    try:
        major = wallust_major_version()
        if major is None:
            return False
        valid = WALLUST_VALID_PALETTES.get(major)
        default = WALLUST_DEFAULT_PALETTE.get(major)
        if valid is None or default is None:
            return False
        p = Path(path)
        text = p.read_text(encoding="utf-8")
        changed = False
        out: list[str] = []
        for line in text.splitlines(keepends=True):
            stripped = line.strip()
            if stripped.startswith("palette") and "=" in stripped:
                key, _, value = stripped.partition("=")
                if key.strip() == "palette":
                    current = value.strip().strip("\"'")
                    if current not in valid and current in _CROSS_MAJOR_DEFAULTS:
                        line = line.replace(value.strip(), f'"{default}"')
                        changed = True
            out.append(line)
        if changed:
            p.write_text("".join(out), encoding="utf-8")
            log.info("normalized %s palette to %r for wallust v%d", p, default, major)
        return changed
    except Exception:
        return False
