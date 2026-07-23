"""Clean theme backups and stale temp files (cleanup-theme-backups)."""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

from wallpaperctl.util import home


def run_cleanup(*, keep_backups: int = 2, cache_max_age_days: int = 7) -> int:
    print("Cleaning up Cinnamon dynamic theme backups and temporary files...")
    themes = home() / ".themes"
    removed = 0

    # Theme backups: cinnamon-dynamic.backup.*
    backups = sorted(
        themes.glob("cinnamon-dynamic.backup.*") if themes.is_dir() else [],
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
        reverse=True,  # newest first
    )
    if backups:
        print(f"Found {len(backups)} theme backup(s)")
        if len(backups) > keep_backups:
            to_drop = backups[keep_backups:]
            print(
                f"Keeping {keep_backups} most recent, removing {len(to_drop)} old backup(s)"
            )
            for b in to_drop:
                removed += _safe_remove(b)
        else:
            print(f"Only {len(backups)} backup(s) found, keeping all")
    else:
        print("No theme backups found")

    # Temporary CSS under cinnamon-dynamic
    dyn = themes / "cinnamon-dynamic"
    temp_files = list(dyn.rglob("*.tmp")) if dyn.is_dir() else []
    if temp_files:
        print(f"Removing {len(temp_files)} temporary CSS file(s)")
        for t in temp_files:
            removed += _safe_remove(t)
    else:
        print("No temporary CSS files found")

    # Old wallpaper env files in /tmp
    tmp = Path("/tmp")
    cutoff = time.time() - 86400  # 1 day
    env_files = []
    if tmp.is_dir():
        for p in tmp.glob("*cinnamon*env*"):
            try:
                if p.is_file() and p.stat().st_mtime < cutoff:
                    env_files.append(p)
            except OSError:
                continue
    if env_files:
        print(f"Removing {len(env_files)} old wallpaper environment file(s)")
        for p in env_files:
            removed += _safe_remove(p)
    else:
        print("No old environment files found")

    # Optional ~/.cache/wallpaper older than N days
    wall_cache = home() / ".cache" / "wallpaper"
    if wall_cache.is_dir():
        age = time.time() - cache_max_age_days * 86400
        old = []
        for p in wall_cache.rglob("*"):
            try:
                if p.is_file() and p.stat().st_mtime < age:
                    old.append(p)
            except OSError:
                continue
        if old:
            print(
                f"Removing {len(old)} old wallpaper cache file(s) "
                f"(older than {cache_max_age_days} days)"
            )
            for p in old:
                removed += _safe_remove(p)
        else:
            print("No old wallpaper cache files found")

    if dyn.is_dir():
        size = _du_sh(dyn)
        print(f"Current cinnamon-dynamic theme size: {size}")

    print("Cleanup completed!")

    remaining = sorted(themes.glob("cinnamon-dynamic.backup.*")) if themes.is_dir() else []
    if remaining:
        print()
        print("Remaining backups:")
        for b in remaining:
            print(f"  - {b.name} ({_du_sh(b)})")

    return 0


def _safe_remove(path: Path) -> int:
    if not path.exists():
        return 0
    print(f"Removing: {path}")
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
        return 1
    except OSError as e:
        print(f"  Failed: {e}", file=sys.stderr)
        return 0


def _du_sh(path: Path) -> str:
    total = 0
    try:
        if path.is_file():
            total = path.stat().st_size
        else:
            for p in path.rglob("*"):
                if p.is_file():
                    try:
                        total += p.stat().st_size
                    except OSError:
                        pass
    except OSError:
        return "?"
    for unit in ("B", "K", "M", "G"):
        if total < 1024 or unit == "G":
            if unit == "B":
                return f"{total}{unit}"
            return f"{total:.1f}{unit}" if total < 10 else f"{int(total)}{unit}"
        total /= 1024
    return f"{total:.1f}G"
