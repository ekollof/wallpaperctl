"""Verify theme/icon installation (verify-dynamic-icons + cinnamon extras)."""

from __future__ import annotations

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

    if what not in (
        "all",
        "icons",
        "icon",
        "cinnamon",
        "theme",
        "wal",
        "colors",
        "wallust",
    ):
        print(f"Unknown verify target: {what}", file=sys.stderr)
        print("Use: icons | cinnamon | wal | all", file=sys.stderr)
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


def _gget(schema: str, key: str) -> str:
    if not have("gsettings"):
        return ""
    r = run(["gsettings", "get", schema, key], timeout=5)
    if r.returncode != 0:
        return ""
    return r.stdout.strip().strip("'")
