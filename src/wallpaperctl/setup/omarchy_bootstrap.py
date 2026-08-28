"""wallpaperctl setup omarchy — prerequisites + persistent Dynamic Wallpapers theme."""

from __future__ import annotations

import json
from pathlib import Path

from wallpaperctl.omarchy import (
    THEME_DISPLAY,
    THEME_SLUG,
    current_theme_name,
    is_omarchy_shell_running,
    omarchy_available,
    run_omarchy,
    user_theme_dir,
)
from wallpaperctl.setup.deps import DEPS
from wallpaperctl.setup.packages import (
    detect_package_manager,
    install_system_packages,
)
from wallpaperctl.setup.wallust_bootstrap import bootstrap_wallust, wallust_status
from wallpaperctl.theme.omarchy import ensure_theme_skeleton
from wallpaperctl.util import have, home

MOTION_PLUGIN_REPO = "https://github.com/28allday/Motion-Wallpaper-Omarchy.git"
MOTION_PLUGIN_FRAGMENT = "motion-wallpaper"


def _ask(prompt: str, *, yes: bool) -> bool:
    if yes:
        return True
    try:
        ans = input(f"{prompt} [y/N] ").strip().lower()
    except EOFError:
        return False
    return ans in ("y", "yes")


def motion_plugin_status() -> dict:
    """Installed/enabled state of the omarchy-shell Motion Wallpaper plugin.

    Animated wallpapers under the dynamic theme are played through this
    third-party plugin (nosignal.motion-wallpaper); without it the setter
    falls back to mpvpaper. ``available`` is False when omarchy's plugin
    management itself is unavailable (very old omarchy).
    """
    r = run_omarchy(["plugin", "list", "--json"], timeout=15)
    stdout = r.stdout if isinstance(r.stdout, str) else ""
    if r.returncode != 0:
        return {"available": False, "installed": False, "enabled": False, "id": None}
    try:
        data = json.loads(stdout or "[]")
    except (json.JSONDecodeError, TypeError):
        return {"available": False, "installed": False, "enabled": False, "id": None}
    plugins = data if isinstance(data, list) else data.get("plugins", [])
    for entry in plugins:
        if not isinstance(entry, dict):
            continue
        if MOTION_PLUGIN_FRAGMENT in str(entry.get("id", "")).lower():
            return {
                "available": True,
                "installed": True,
                "enabled": bool(entry.get("enabled")),
                "id": entry.get("id"),
            }
    return {"available": True, "installed": False, "enabled": False, "id": None}


def _ensure_motion_plugin(*, yes: bool) -> bool:
    """Make sure the Motion Wallpaper plugin is installed and enabled."""
    motion = motion_plugin_status()
    if not motion["available"]:
        print("Note: omarchy plugin management unavailable; cannot verify the")
        print("  Motion Wallpaper plugin (animated wallpapers fall back to mpvpaper).")
        return False
    if motion["installed"] and motion["enabled"]:
        print(f"Motion Wallpaper plugin: enabled ({motion['id']})")
        return True
    if motion["installed"]:
        print(f"Motion Wallpaper plugin installed but disabled ({motion['id']}).")
        if _ask("Enable it now?", yes=yes):
            r = run_omarchy(["plugin", "enable", str(motion["id"])], timeout=30)
            if r.returncode == 0:
                print("✓ Motion Wallpaper plugin enabled.")
                return True
            print("Warning: enabling failed; animated wallpapers fall back to mpvpaper.")
        return False

    print("Animated wallpapers need the omarchy-shell Motion Wallpaper plugin:")
    print(f"  {MOTION_PLUGIN_REPO}")
    if _ask("Install and enable it now?", yes=yes):
        args = ["plugin", "add", MOTION_PLUGIN_REPO, "--enable"]
        if yes:
            args.append("--yes")
        r = run_omarchy(args, timeout=120)
        if r.returncode == 0:
            print("✓ Motion Wallpaper plugin installed and enabled.")
            return True
        print("Warning: plugin install failed; animated wallpapers fall back to mpvpaper.")
        print(f"  Manual: omarchy plugin add {MOTION_PLUGIN_REPO} --enable")
    else:
        print("Skipped. Install later with:")
        print(f"  omarchy plugin add {MOTION_PLUGIN_REPO} --enable")
    return False


def omarchy_status() -> dict:
    theme_dir = user_theme_dir()
    return {
        "binary": have("omarchy"),
        "config_dir": (home() / ".config" / "omarchy").is_dir(),
        "shell_running": is_omarchy_shell_running(),
        "current_theme": current_theme_name(),
        "theme_dir": str(theme_dir),
        "theme_installed": (theme_dir / "colors.toml").is_file(),
        "motion_plugin": motion_plugin_status(),
        "wallust": wallust_status(),
    }


def _install_wallust(*, yes: bool) -> bool:
    """Best-effort wallust install via the detected system package manager.

    Prefers the AUR build (wallust-git) on Arch-like systems and falls back to
    the stable repo package, mirroring setup install's catalog behaviour.
    """
    pm = detect_package_manager()
    if not pm:
        print("No supported package manager detected; install wallust manually:")
        print("  AUR helper:  paru -S wallust-git")
        print("  cargo:       cargo install wallust")
        return False

    dep = next(d for d in DEPS if d.id == "wallust")
    candidates: list[str] = []
    catalog_pkg = dep.package_for(pm.id)
    if catalog_pkg:
        candidates.append(catalog_pkg)
    if pm.id == "pacman" and "wallust" not in candidates:
        candidates.append("wallust")

    last_rc = 1
    for pkg in candidates:
        print(f"Trying: {pm.name}: {pkg}")
        last_rc = install_system_packages([(dep, pkg)], pm, yes=yes)
        if last_rc == 0 and have("wallust"):
            return True
        if pm.id == "pacman":
            print("If that failed: wallust is AUR-only on Arch (no repo package). Try:")
            print("  paru -S wallust-git      # or yay -S wallust-git")
            print("  cargo install wallust")
    return False


def _install_omarchy_hooks() -> int:
    """Install wallpaperctl theme-set hooks (starship follows Omarchy themes)."""
    import shutil

    from wallpaperctl.util import run

    pkg = Path(__file__).resolve().parent.parent / "data" / "omarchy" / "hooks"
    if not pkg.is_dir():
        print("Packaged omarchy hooks not found in wallpaperctl install.")
        return 1

    dest_root = home() / ".config" / "omarchy" / "hooks"
    dest_root.mkdir(parents=True, exist_ok=True)
    for src in sorted(pkg.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(pkg)
        dest = dest_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.is_file() or src.read_bytes() != dest.read_bytes():
            shutil.copy2(src, dest)
            print(f"hook:    {dest}")
        dest.chmod(dest.stat().st_mode | 0o111)

    # sync once now so the prompt matches the active theme immediately
    for hook in sorted((dest_root / "theme-set.d").glob("wallpaperctl-*")):
        run([str(hook)], timeout=30)
    return 0


def bootstrap_omarchy(*, yes: bool = False, force: bool = False) -> int:
    """Set up the Omarchy integration: wallust + one persistent theme, activated."""
    print("wallpaperctl setup omarchy")
    print("=" * 40)

    if not omarchy_available():
        print("Error: Omarchy was not detected on this system.")
        print("  Expected the `omarchy` binary or ~/.config/omarchy.")
        print("  This integration only applies to Omarchy installations.")
        return 1

    if not is_omarchy_shell_running():
        print("Note: omarchy-shell is not running; the shell will pick up the")
        print("  theme on next login (configs are still applied).")

    status = omarchy_status()
    print(f"omarchy:     {'yes' if status['binary'] else 'config only'}")
    print(f"shell:       {'running' if status['shell_running'] else 'not running'}")
    print(f"theme dir:   {status['theme_dir']}")

    if not have("wallust"):
        print()
        print("wallust is required to palettize wallpapers for the theme.")
        if not _install_wallust(yes=yes):
            print("Error: wallust is still missing; aborting (install it and re-run).")
            return 1

    print()
    _ensure_motion_plugin(yes=yes)

    print()
    _install_omarchy_hooks()

    print()
    rc = bootstrap_wallust(force=force, yes=yes, skip_opencode=True)
    if rc != 0:
        print("Warning: wallust bootstrap reported issues; continuing.")

    # Palette-only wallust config: ALL app theming belongs to Omarchy. The
    # full wallust template set would fight it — its opencode hook flips
    # tui.json back to theme "wallust" on every wallpaper change, and the
    # kitty/btop templates overwrite omarchy-managed configs.
    from wallpaperctl.setup.wallust_bootstrap import install_omarchy_wallust_config

    print()
    install_omarchy_wallust_config()
    for stale in (
        home() / ".config" / "opencode" / "themes" / "wallust.json",
        home() / ".config" / "kitty" / "current-theme.conf",
        home() / ".config" / "btop" / "themes" / "noctalia.theme",
    ):
        if stale.is_file():
            try:
                stale.unlink()
                print(f"removed: {stale}  (wallust-rendered; omarchy owns this)")
            except OSError:
                pass

    # Omarchy owns opencode theming (theme "omarchy" + its own TUI plugin);
    # wallpaperctl's wallust hot-reload plugin would fight it over tui.json.
    from wallpaperctl.setup.opencode_bootstrap import remove_opencode_plugin

    print()
    if remove_opencode_plugin():
        print("  (omarchy's opencode theme integration stays active)")
    else:
        print("opencode: no wallpaperctl plugin found (omarchy theming active).")

    print()
    created = ensure_theme_skeleton(
        user_theme_dir(),
        accent_strategy="warmest",
    )
    if created:
        print(f"theme:      created '{THEME_DISPLAY}' ({THEME_SLUG})")
    else:
        print(f"theme:      '{THEME_DISPLAY}' already exists (colors.toml kept)")

    print()
    print(f"Activating theme via: omarchy theme set {THEME_SLUG}")
    r = run_omarchy(["theme", "set", THEME_SLUG], timeout=120)
    if r.returncode != 0:
        print(f"Error: omarchy theme set failed: {(r.stderr or r.stdout or '')[:300]}")
        print(f"  Manual: omarchy theme set \"{THEME_DISPLAY}\"")
        return 1
    print(f"✓ '{THEME_DISPLAY}' is now the active Omarchy theme.")

    # Warm the theme picker cache so the new theme shows up in the switcher
    # (the picker lists themes from its preview cache).
    run_omarchy(["theme", "switcher", "--preload"], timeout=60)
    print()
    print("wallpaperctl now drives wallpapers and colors whenever this theme is")
    print("active: each wallpaper change rewrites colors.toml and refreshes the")
    print("theme through omarchy tooling (terminals, bar, btop, browser, …).")
    print()
    print("Try it: wallpaperctl random")
    return 0


def seed_backgrounds_from_current(theme_dir: Path | None = None) -> None:
    """Convenience wrapper used by setup when a wallpaper already exists."""
    from wallpaperctl.theme.omarchy import sync_theme_media

    theme_dir = theme_dir or user_theme_dir()
    current = home() / ".wallpaper"
    if not current.is_file():
        return
    try:
        wallpaper = Path(current.read_text(encoding="utf-8").strip())
        if wallpaper.is_file():
            sync_theme_media(theme_dir, wallpaper)
    except OSError:
        pass
