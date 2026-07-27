"""Read-only migration / cutover checklist (shell → wallpaperctl)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from wallpaperctl import __version__
from wallpaperctl.config import OpsConfig
from wallpaperctl.detect.desktop import detect_desktop
from wallpaperctl.detect.tools import detect_tools
from wallpaperctl.util import home, which


def run_migrate_check(ops: OpsConfig | None = None) -> int:
    """Print PATH/config/tool status for replacing ~/bin wallpaper scripts.

    Always returns 0 (advisory only).
    """
    ops = ops or OpsConfig()
    print(f"wallpaperctl migrate check  (v{__version__})")
    print()

    # --- PATH / which wins ---
    print("=== PATH resolution ===")
    ctl = which("wallpaperctl")
    wall = which("wallpaper")
    print(f"  wallpaperctl → {ctl or '(not found)'}")
    print(f"  wallpaper    → {wall or '(not found)'}")
    if wall and ctl:
        wall_p = Path(wall).resolve()
        ctl_p = Path(ctl).resolve()
        # Entry points are separate scripts; same parent ⇒ same package install
        if wall_p.parent == ctl_p.parent:
            print(f"  ✓ both from package install: {ctl_p.parent}")
        elif wall_p == ctl_p:
            print("  ✓ wallpaper and wallpaperctl resolve to the same path")
        else:
            print("  ! wallpaper and wallpaperctl come from different installs")
            print(f"    wallpaper → {wall_p}")
            print(f"    wallpaperctl → {ctl_p}")
            print("    (legacy shell often lives under ~/bin — check PATH order)")
    legacy_bin = home() / "bin" / "wallpaper"
    if legacy_bin.is_file():
        print(f"  note: legacy script still present: {legacy_bin}")
        path_dirs = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
        # Who wins for bare `wallpaper`?
        if wall:
            wall_resolved = str(Path(wall).resolve())
            legacy_resolved = str(legacy_bin.resolve())
            if wall_resolved == legacy_resolved:
                print(
                    "  ! bare `wallpaper` is still the shell script — "
                    "put package shims before ~/bin on PATH, or call wallpaperctl"
                )
            elif ctl:
                try:
                    wi = path_dirs.index(str(Path(wall).parent))
                    ci = path_dirs.index(str(Path(ctl).parent))
                    if wi < ci and wall_resolved != str(Path(ctl).resolve()):
                        print(
                            "  ! a non-package `wallpaper` appears before "
                            "wallpaperctl on PATH"
                        )
                except ValueError:
                    pass
    print()

    # --- Config / state ---
    print("=== Config & state ===")
    sh = home() / ".config" / "wallpaper" / "config.sh"
    ops_toml = home() / ".config" / "wallpaperctl" / "ops.toml"
    walls = ops.path("wallpaper_dir")
    current = ops.path("current_wallpaper_file")
    for label, path, need in (
        ("API keys config.sh", sh, False),
        ("ops.toml", ops_toml, False),
        ("wallpaper library", walls, True),
        ("last wallpaper file", current, False),
        ("URL log", ops.path("url_log"), False),
        ("hash index", ops.path("hash_cache"), False),
    ):
        if path.is_file() or path.is_dir():
            print(f"  ✓ {label}: {path}")
        elif need:
            print(f"  ! {label} missing: {path}")
        else:
            print(f"  · {label} not present: {path}")
    print()

    # --- Desktop / tools ---
    print("=== Desktop ===")
    de = detect_desktop()
    tools = detect_tools(de, strict=False)
    print(f"  DE: {de.name}")
    if tools.missing_required:
        print("  Missing required for this DE:")
        for m in tools.missing_required:
            print(f"    - {m}")
        print("  → wallpaperctl setup check | wallpaperctl setup install")
    else:
        print("  ✓ required tools for this DE look OK")
    if tools.warnings:
        print("  Warnings:")
        for w in tools.warnings:
            print(f"    - {w}")
    print()

    # --- Shipped data ---
    print("=== Packaged data ===")
    try:
        from wallpaperctl.theme.cinnamon_theme import _template_path

        tpl = _template_path("cinnamon.css.tpl")
        print(f"  cinnamon CSS template: {tpl or 'MISSING'}")
    except Exception as e:
        print(f"  cinnamon template probe failed: {e}", file=sys.stderr)
    wallust_pkg = which("wallust")
    print(f"  wallust binary: {wallust_pkg or '(not on PATH — optional)'}")
    print()

    print("=== Suggested cutover ===")
    print("  1. wallpaperctl setup all     # if not done yet")
    print("  2. wallpaperctl detect && wallpaperctl -R")
    print("  3. Point keybindings/cron at wallpaperctl (or ensure PATH order)")
    print("  4. Remove ~/bin/wallpaper* only after you are happy")
    print()
    print("(This command is read-only and always exits 0.)")
    return 0
