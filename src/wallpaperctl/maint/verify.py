"""Verify theme/icon installation (verify-dynamic-icons + cinnamon extras)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from wallpaperctl.config import OpsConfig
from wallpaperctl.util import have, home, run


def run_verify(what: str = "all", *, ops: OpsConfig | None = None) -> int:
    ops = ops or OpsConfig()
    what = (what or "all").lower()
    ok = True

    if what in ("all", "icons", "icon"):
        if not _verify_icons(ops):
            ok = False
    if what in ("all", "cinnamon", "theme"):
        if not _verify_cinnamon(ops):
            ok = False
    if what in ("all", "wal", "colors", "wallust"):
        if not _verify_wal():
            ok = False
    if what in ("all", "omarchy"):
        if not _verify_omarchy(ops):
            ok = False

    if what not in (
        "all",
        "icons",
        "icon",
        "cinnamon",
        "theme",
        "wal",
        "colors",
        "wallust",
        "omarchy",
    ):
        print(f"Unknown verify target: {what}", file=sys.stderr)
        print("Use: icons | cinnamon | wal | omarchy | all", file=sys.stderr)
        return 1

    return 0 if ok else 1


def _verify_icons(ops: OpsConfig) -> bool:
    print("=== Dynamic Icon Theme Verification ===")
    print()
    theme_name = ops.dynamic_icon_theme_name or "wallust-dynamic-icons"
    theme_dir = home() / ".local" / "share" / "icons" / theme_name

    ok = True
    if theme_dir.is_dir():
        print("✓ Dynamic icon theme directory exists")
        print(f"  Location: {theme_dir}")
    else:
        print("✗ Dynamic icon theme directory missing")
        print(f"  Expected: {theme_dir}")
        print("  Enable with enable_dynamic_icons and re-run wallpaperctl on Cinnamon")
        return False

    print()
    print("Icon theme structure:")
    for child in sorted(theme_dir.iterdir()):
        print(f"  {child.name}")

    svgs = list(theme_dir.rglob("*.svg"))
    print()
    print(f"Total icons created: {len(svgs)}")

    places = list(theme_dir.glob("*/places/*.svg"))[:5]
    print()
    print("Folder icons (should override Mint-Y green):")
    for p in places:
        print(f"  {p.relative_to(theme_dir)}")
    if not places:
        print("  (none found)")

    print()
    print("Sample folder icon color:")
    folder = theme_dir / "24" / "places" / "folder.svg"
    if folder.is_file():
        text = folder.read_text(encoding="utf-8", errors="replace")
        m = re.search(r'fill="(#[^"]+)"', text)
        print(f"  {m.group(1) if m else '(no fill found)'}")
    else:
        print("  Folder icon not found")
        ok = False

    print()
    print("Current icon theme setting:")
    gtk = _gget("org.gnome.desktop.interface", "icon-theme")
    cin = _gget("org.cinnamon.desktop.interface", "icon-theme")
    print(f"  GTK: {gtk or '(unavailable)'}")
    print(f"  Cinnamon: {cin or '(unavailable)'}")

    index = theme_dir / "index.theme"
    print()
    print("Icon theme inheritance:")
    if index.is_file():
        for line in index.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("Inherits="):
                print(f"  {line}")
    else:
        print("  (no index.theme)")
        ok = False

    print()
    if gtk == theme_name or cin == theme_name:
        print("✓ Dynamic icon theme is active!")
        print("  Folder icons should match your wallpaper accent color")
    else:
        print("! Dynamic icon theme not active")
        print(
            f"  Run: gsettings set org.gnome.desktop.interface icon-theme '{theme_name}'"
        )
        ok = False

    print()
    print("To manually test:")
    print("  1. Open file manager (nautilus or nemo)")
    print("  2. Check if folder icons match your wallpaper colors")
    print("  3. Check panel status icons for color coordination")
    return ok


def _verify_cinnamon(ops: OpsConfig) -> bool:
    print()
    print("=== Cinnamon Dynamic Theme Verification ===")
    print()
    ok = True
    theme_dir = home() / ".themes" / "cinnamon-dynamic"
    css = theme_dir / "cinnamon" / "cinnamon.css"
    gtk_css = theme_dir / "gtk-3.0" / "gtk.css"

    if theme_dir.is_dir():
        print("✓ cinnamon-dynamic theme directory exists")
        print(f"  Location: {theme_dir}")
    else:
        print("✗ cinnamon-dynamic theme missing")
        print("  Run wallpaperctl on Cinnamon to generate it")
        return False

    for label, path in (("cinnamon.css", css), ("gtk.css", gtk_css)):
        if path.is_file():
            print(f"✓ {label} present ({path.stat().st_size} bytes)")
        else:
            print(f"✗ {label} missing: {path}")
            ok = False

    print()
    print("gsettings themes:")
    for schema, key, label in (
        ("org.cinnamon.theme", "name", "Cinnamon shell"),
        ("org.cinnamon.desktop.wm.preferences", "theme", "WM"),
        ("org.cinnamon.desktop.interface", "gtk-theme", "GTK (Cinnamon)"),
        ("org.gnome.desktop.interface", "gtk-theme", "GTK (GNOME)"),
    ):
        val = _gget(schema, key)
        mark = "✓" if val == "cinnamon-dynamic" else "!"
        print(f"  {mark} {label}: {val or '(unavailable)'}")

    backups = list((home() / ".themes").glob("cinnamon-dynamic.backup.*"))
    print()
    print(f"Theme backups: {len(backups)}")
    for b in sorted(backups)[:5]:
        print(f"  - {b.name}")
    if len(backups) > 5:
        print(f"  … and {len(backups) - 5} more (wallpaperctl cleanup)")
    return ok


def _verify_wal() -> bool:
    print()
    print("=== Wallust / pywal colors ===")
    print()
    colors = home() / ".cache" / "wal" / "colors"
    if not colors.is_file():
        print("✗ ~/.cache/wal/colors missing (run wallpaperctl with wallust enabled)")
        return False
    lines = [
        ln.strip()
        for ln in colors.read_text(encoding="utf-8", errors="replace").splitlines()
        if ln.strip()
    ]
    print(f"✓ colors file present ({len(lines)} entries)")
    for i, c in enumerate(lines[:8]):
        print(f"  color{i}: {c}")
    if len(lines) > 8:
        print(f"  … +{len(lines) - 8} more")

    xres = home() / ".cache" / "wal" / "colors.Xresources"
    print(f"{'✓' if xres.is_file() else '!'} colors.Xresources: "
          f"{'present' if xres.is_file() else 'missing'}")
    return True


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _verify_omarchy(ops: OpsConfig) -> bool:
    """Verify the Omarchy dynamic-theme hand-off chain, stage by stage."""
    from wallpaperctl.omarchy import (
        THEME_SLUG,
        current_theme_name,
        is_omarchy_shell_running,
        omarchy_available,
        user_theme_dir,
    )
    from wallpaperctl.theme.omarchy import build_colors_mapping
    from wallpaperctl.theme.pywalfox import load_colors_json

    print()
    print("=== Omarchy dynamic theme chain ===")
    print()
    if not omarchy_available():
        print("✗ omarchy not present on this system")
        return False

    ok = True
    slug = ops.omarchy_theme_slug or THEME_SLUG
    theme = current_theme_name()
    mark = "✓" if theme == slug else "✗"
    print(f"{mark} active theme: {theme or '(none)'}")
    if theme != slug:
        print(f"  → wallpaperctl only retints while '{slug}' is active")
        print(f"    (switch back: omarchy theme set {slug})")
        return False
    print(f"{'✓' if is_omarchy_shell_running() else '!'} omarchy-shell: "
          f"{'running' if is_omarchy_shell_running() else 'NOT running'}")

    # 1. wallust palette vs current wallpaper
    wallpaper = home() / ".wallpaper"
    colors_json = home() / ".cache" / "wal" / "colors.json"
    stale = (
        wallpaper.is_file()
        and colors_json.is_file()
        and _mtime(colors_json) + 2 < _mtime(wallpaper)
    )
    if stale:
        print("✗ wallust palette: OLDER than current wallpaper — wallust failed")
        print(f"  → check: wallust run --backend wal --palette kmeans {wallpaper}")
        ok = False
    else:
        print("✓ wallust palette: current")

    # 2. colors.toml derived from the palette
    theme_dir = user_theme_dir(slug)
    colors_toml = theme_dir / "colors.toml"
    colors = load_colors_json() or {}
    if colors_json.is_file() and colors:
        expected = build_colors_mapping(colors)
        accent = expected.get("accent", "")
        text = colors_toml.read_text(encoding="utf-8") if colors_toml.is_file() else ""
        mark = "✓" if f'accent = "{accent.lower()}' in text.lower() else "✗"
        current = "missing"
        if "accent = " in text:
            current = text.split("accent = ")[1].splitlines()[0]
        print(f"{mark} colors.toml accent: {current}")
        if mark == "✗":
            print(f"  → expected accent {accent}; re-run: wallpaperctl -R")
            ok = False
    else:
        print("✗ colors.toml missing")
        ok = False

    # 3. staged + live opencode theme
    staged = home() / ".local" / "state" / "omarchy" / "current" / "theme" / "opencode.json"
    live = home() / ".config" / "opencode" / "themes" / "omarchy.json"
    for label, path in (("staged", staged), ("live", live)):
        if not path.is_file():
            print(f"✗ opencode theme ({label}): missing — {path}")
            ok = False
            continue
        fresh = not colors_toml.is_file() or _mtime(path) + 2 >= _mtime(colors_toml)
        print(f"{'✓' if fresh else '!'} opencode theme ({label}): "
              f"{'fresh' if fresh else 'OLDER than colors.toml'}")
        if not fresh and label == "live":
            print("  → omarchy theme refresh did not sync opencode; try: omarchy theme refresh")
            ok = False

    # 4. opencode registration + leftovers
    tui_path = home() / ".config" / "opencode" / "tui.json"
    if tui_path.is_file():
        try:
            tui = json.loads(tui_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            tui = {}
        sel = tui.get("theme")
        mark = "✓" if sel == "omarchy" else "!"
        print(f"{mark} tui.json theme: {sel or '(none)'}")
        if sel != "omarchy":
            print("  → fix: wallpaperctl setup omarchy (or omarchy theme refresh)")
            ok = False
        plugins = tui.get("plugin") or []
        leftover = [p for p in plugins if "wallust-hot-reload" in str(p)]
        if leftover:
            print("✗ tui.json still lists the wallust hot-reload plugin")
            ok = False
    wallust_theme = home() / ".config" / "opencode" / "themes" / "wallust.json"
    if wallust_theme.exists():
        print("✗ themes/wallust.json still present (stale wallust theming)")
        print("  → fix: wallpaperctl setup omarchy")
        ok = False
    else:
        print("✓ no wallust opencode leftovers")

    # 5. guidance for sessions
    print()
    print("Live opencode sessions retint only when they were started with theme")
    print("'omarchy' (omarchy's owned() gate). Sessions started before the last")
    print("tui.json fix keep 'wallust' selected and are ignored — restart them once.")
    return ok


def _gget(schema: str, key: str) -> str:
    if not have("gsettings"):
        return ""
    r = run(["gsettings", "get", schema, key], timeout=5)
    if r.returncode != 0:
        return ""
    return r.stdout.strip().strip("'")
