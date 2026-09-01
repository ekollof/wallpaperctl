"""wallpaperctl setup — audit, install deps, bootstrap config/wallust."""

from __future__ import annotations

import sys

from wallpaperctl.detect.desktop import detect_desktop
from wallpaperctl.setup.bootstrap import bootstrap_config
from wallpaperctl.setup.deps import (
    Kind,
    animated_backend_hint,
    classify_deps,
    de_profile,
)
from wallpaperctl.setup.omarchy_bootstrap import bootstrap_omarchy, omarchy_status
from wallpaperctl.setup.opencode_bootstrap import opencode_status
from wallpaperctl.setup.packages import (
    detect_package_manager,
    install_python_extras,
    install_system_packages,
    packages_to_install,
)
from wallpaperctl.setup.themes_bootstrap import bootstrap_themes, themes_status
from wallpaperctl.setup.wallust_bootstrap import (
    bootstrap_wallust,
    smoke_test_wallust,
    wallust_status,
)


def run_setup(
    action: str = "check",
    *,
    yes: bool = False,
    force: bool = False,
    optional: bool = False,
    all_desktops: bool = False,
) -> int:
    action = (action or "check").lower()
    de = detect_desktop()
    profile = de_profile(de)

    if action in ("check", "status", "deps"):
        return cmd_check(de, profile, optional=optional, all_desktops=all_desktops)
    if action in ("install", "deps-install"):
        return cmd_install(de, profile, yes=yes, optional=optional)
    if action == "wallust":
        rc = bootstrap_wallust(force=force, yes=yes)
        if rc == 0:
            smoke_test_wallust()
        return rc
    if action == "wallust-templates":
        # Install/update templates+scripts only; never touch wallust.toml
        return bootstrap_wallust(force=force, yes=yes, templates_only=True)
    if action in ("config", "bootstrap"):
        return bootstrap_config(force=force)
    if action == "omarchy":
        return bootstrap_omarchy(yes=yes, force=force)
    if action in ("themes", "gtk-themes", "flatcolor"):
        return bootstrap_themes(force=force, yes=yes)
    if action in ("all", "init"):
        print("=== 1/5 config directories ===")
        bootstrap_config(force=force)
        if de.omarchy:
            print("\n=== 2/5 FlatColor GTK themes ===")
            print("Skipped: Omarchy owns GTK (Adwaita via omarchy-theme-set-gnome).")
        else:
            print("\n=== 2/5 FlatColor GTK themes ===")
            bootstrap_themes(force=force, yes=yes)
        print("\n=== 3/5 dependency check ===")
        cmd_check(de, profile, optional=optional)
        print("\n=== 4/5 install missing packages ===")
        cmd_install(de, profile, yes=yes, optional=optional)
        if de.omarchy:
            print("\n=== 5/5 omarchy (wallust palette-only + Dynamic Wallpapers) ===")
            rc = bootstrap_omarchy(yes=yes, force=force)
            print()
            print("Done. Try: wallpaperctl detect && wallpaperctl random")
            return rc
        print("\n=== 5/5 wallust ===")
        bootstrap_wallust(force=force, yes=yes)
        smoke_test_wallust()
        print("\nDone. Try: wallpaperctl detect && wallpaperctl -R")
        return 0

    print(f"Unknown setup action: {action}", file=sys.stderr)
    print(
        "Use: check | install | wallust | themes | config | omarchy | all",
        file=sys.stderr,
    )
    return 1


def cmd_check(
    de,
    profile: str,
    *,
    optional: bool = False,
    all_desktops: bool = False,
) -> int:
    print("wallpaperctl setup check")
    print("=" * 40)
    print(f"Desktop:  {de.name}  (profile={profile})")
    print(
        f"  plasma={de.plasma} hyprland={de.hyprland} omarchy={de.omarchy} "
        f"noctalia={de.noctalia} xfce={de.xfce} cinnamon={de.cinnamon}"
    )
    pm = detect_package_manager()
    print(f"Packages: {pm.name if pm else 'none detected (manual install)'}")
    print()

    statuses = classify_deps(de, include_optional=True)
    missing_req: list[str] = []
    missing_rec: list[str] = []

    def show(title: str, pred) -> None:
        rows = [s for s in statuses if pred(s)]
        if not rows:
            return
        print(title)
        for s in rows:
            if not s.relevant and not all_desktops:
                continue
            mark = "✓" if s.present else ("✗" if s.required else "·")
            tag = ""
            if s.required and not s.present:
                tag = " [REQUIRED]"
                missing_req.append(s.dep.id)
            elif not s.present and s.relevant:
                missing_rec.append(s.dep.id)
            pkg = ""
            if pm and not s.present:
                p = s.dep.package_for(pm.id)
                if p:
                    pkg = f"  → {p}"
            note = f"  ({s.dep.notes})" if s.dep.notes and not s.present else ""
            print(f"  {mark} {s.dep.id:16} {s.dep.description}{tag}{pkg}{note}")
        print()

    show("Python (bundled with wallpaperctl):", lambda s: s.dep.kind == Kind.PYTHON)
    show("Core / theme:", lambda s: s.dep.kind in (Kind.CORE, Kind.THEME))
    show(f"Desktop ({profile}):", lambda s: s.dep.kind == Kind.DE)
    show("Animated wallpapers:", lambda s: s.dep.kind == Kind.ANIMATED)
    show("Optional:", lambda s: s.dep.kind == Kind.OPTIONAL)

    hint = animated_backend_hint(de, statuses)
    print("Animated playback backend for this session:")
    print(f"  {hint or 'none available (pick static images or install above)'}")
    print()

    ws = wallust_status()
    print("Wallust:")
    print(f"  binary:  {'yes' if ws['binary'] else 'NO'}")
    print(f"  config:  {ws['config_path']} ({'yes' if ws['config_exists'] else 'missing'})")
    if ws.get("omarchy_config"):
        print("  mode:    omarchy palette-only (app theming via omarchy)")
    print(f"  wal cache colors: {'yes' if ws['wal_colors'] else 'missing'}")
    stale_n = len(ws["stale_templates"]) + len(ws["stale_scripts"])
    if stale_n:
        print(
            f"  vendored files outdated: {len(ws['stale_templates'])} template(s), "
            f"{len(ws['stale_scripts'])} script(s)"
        )
        print("  Fix: wallpaperctl setup wallust-templates --force")
    else:
        print("  vendored templates/scripts: up to date")
    ost = omarchy_status()
    oc = opencode_status()
    print("OpenCode (wallust theme reload):")
    if ost["binary"] or ost["theme_installed"]:
        print("  managed by Omarchy (omarchy theme integration; wallust plugin suppressed)")
    else:
        print(
            f"  plugin:  {'yes' if oc['plugin_installed'] else 'NO — wallpaperctl setup wallust'}"
            f"{' (outdated)' if oc['plugin_stale'] else ''}"
        )
        print(
            f"  tui.json plugin: "
            f"{'yes' if oc['plugin_listed'] else 'NO — wallpaperctl setup wallust'}"
        )
    ts = themes_status()
    print("GTK themes (FlatColor):")
    if de.omarchy:
        print("  skipped (Omarchy uses Adwaita; wallpaperctl setup themes is a no-op here)")
    else:
        print(f"  FlatColor:      {'yes' if ts['flatcolor'] else 'NO — wallpaperctl setup themes'}")
        print(f"  FlatColor-dark: {'yes' if ts['flatcolor_dark'] else 'NO'}")
    print()

    print("Omarchy:")
    print(f"  binary:        {'yes' if ost['binary'] else 'no'}")
    print(f"  omarchy-shell: {'running' if ost['shell_running'] else 'not running'}")
    print(f"  current theme: {ost['current_theme'] or '(none)'}")
    if ost["theme_installed"]:
        print(f"  dynamic theme: installed ({ost['theme_dir']})")
    else:
        print("  dynamic theme: NO — wallpaperctl setup omarchy")
    motion = ost.get("motion_plugin") or {}
    if not motion.get("available", True):
        print("  motion plugin: unknown (omarchy plugin management unavailable)")
    elif motion.get("installed"):
        state = "enabled" if motion.get("enabled") else "installed but DISABLED"
        print(f"  motion plugin: {state} ({motion.get('id')})")
    else:
        print("  motion plugin: NO — animated wallpapers fall back to mpvpaper")
    print()

    if missing_req:
        print("Missing REQUIRED for this desktop:")
        for m in missing_req:
            print(f"  - {m}")
        print("  Fix: wallpaperctl setup install")
    elif missing_rec:
        print("Recommended missing (optional/theme):", ", ".join(missing_rec))
        print("  Fix: wallpaperctl setup install --optional")
    else:
        print("All relevant dependencies look good.")

    if profile == "xfce":
        from wallpaperctl.util import pgrep_exact

        if not pgrep_exact("xfsettingsd"):
            print()
            print("Note: xfsettingsd is not running — XFCE Appearance will not apply.")
            print("  Start: xfsettingsd --replace --daemon")
            print("  (and do not run standalone xsettingsd at the same time)")

    return 1 if missing_req else 0


def cmd_install(de, profile: str, *, yes: bool = False, optional: bool = False) -> int:
    print("wallpaperctl setup install")
    print("=" * 40)
    # Python first
    rc_py = install_python_extras(yes=yes)
    statuses = classify_deps(de, include_optional=True)
    pm = detect_package_manager()
    if not pm:
        print("No supported system package manager detected.")
        print("Install missing tools manually (see: wallpaperctl setup check).")
        return rc_py

    pairs = packages_to_install(
        statuses,
        pm,
        missing_only=True,
        relevant_only=True,
        include_optional=optional,
    )
    # Always offer wallust if missing
    if not any(d.id == "wallust" for d, _ in pairs):
        for s in statuses:
            if s.dep.id == "wallust" and not s.present:
                pkg = s.dep.package_for(pm.id)
                if pkg:
                    pairs.append((s.dep, pkg))

    # pacman: if wallust-git fails, point at the AUR helper / cargo paths
    rc = install_system_packages(pairs, pm, yes=yes)
    if rc != 0 and any(d.id == "wallust" for d, _ in pairs) and pm.id == "pacman":
        print("wallust is AUR-only on Arch (no repo package). Try:")
        print("  paru -S wallust-git      # or yay -S wallust-git")
        print("  cargo install wallust")
    return rc if rc else rc_py
