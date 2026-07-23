"""Duplicate-detection cache manager (replaces ~/bin/wallpaper-cache).

Manages:
  * ~/.wallpaper_urls   — provider URL / Unsplash ID log
  * ~/.wallpaper_hashes — multi-hash library index
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from wallpaperctl.config import OpsConfig


@dataclass
class CacheStats:
    url_path: Path
    hash_path: Path
    url_entries: int
    hash_entries: int  # non-comment fingerprint lines
    url_exists: bool
    hash_exists: bool

    @property
    def any_exists(self) -> bool:
        return self.url_exists or self.hash_exists


def cache_stats(ops: OpsConfig | None = None) -> CacheStats:
    ops = ops or OpsConfig()
    url_path = ops.path("url_log")
    hash_path = ops.path("hash_cache")
    url_n = _count_data_lines(url_path) if url_path.is_file() else 0
    hash_n = _count_hash_entries(hash_path) if hash_path.is_file() else 0
    return CacheStats(
        url_path=url_path,
        hash_path=hash_path,
        url_entries=url_n,
        hash_entries=hash_n,
        url_exists=url_path.is_file(),
        hash_exists=hash_path.is_file(),
    )


def _count_data_lines(path: Path) -> int:
    try:
        return sum(
            1
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
    except OSError:
        return 0


def _count_hash_entries(path: Path) -> int:
    return _count_data_lines(path)


def _tail_lines(path: Path, n: int) -> list[str]:
    if not path.is_file():
        return []
    try:
        lines = [
            ln
            for ln in path.read_text(encoding="utf-8", errors="replace").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        return lines[-n:]
    except OSError:
        return []


def clear_url_cache(ops: OpsConfig | None = None) -> bool:
    ops = ops or OpsConfig()
    p = ops.path("url_log")
    if p.is_file():
        p.unlink()
        return True
    return False


def clear_hash_cache(ops: OpsConfig | None = None) -> bool:
    ops = ops or OpsConfig()
    p = ops.path("hash_cache")
    if p.is_file():
        p.unlink()
        return True
    return False


def clear_all_caches(ops: OpsConfig | None = None) -> list[str]:
    """Clear URL + hash caches. Returns list of what was removed."""
    ops = ops or OpsConfig()
    cleared: list[str] = []
    if clear_url_cache(ops):
        cleared.append("URL log")
    if clear_hash_cache(ops):
        cleared.append("hash index")
    return cleared


def trim_url_cache(keep: int, ops: OpsConfig | None = None) -> int:
    """Keep only the last *keep* URL entries. Returns remaining count."""
    ops = ops or OpsConfig()
    path = ops.path("url_log")
    if not path.is_file() or keep < 0:
        return 0
    try:
        lines = [
            ln
            for ln in path.read_text(encoding="utf-8", errors="replace").splitlines()
            if ln.strip()
        ]
        kept = lines[-keep:] if keep else []
        if kept:
            path.write_text("\n".join(kept) + "\n", encoding="utf-8")
        else:
            path.unlink(missing_ok=True)
        return len(kept)
    except OSError as e:
        print(f"Failed to trim URL cache: {e}", file=sys.stderr)
        return 0


def show_cache(ops: OpsConfig | None = None, *, full: bool = False, recent: int = 5) -> None:
    stats = cache_stats(ops)
    print("Wallpaper Duplicate Cache Manager")
    print("==================================")
    print()
    print(f"URL log:    {stats.url_path}")
    if stats.url_exists:
        print(f"  entries:  {stats.url_entries}")
    else:
        print("  (not found — created on first remote fetch)")
    print(f"Hash index: {stats.hash_path}")
    if stats.hash_exists:
        print(f"  fingerprints: {stats.hash_entries}")
    else:
        print("  (not found — run: wallpaperctl index)")
    print()

    if stats.url_exists:
        if full:
            print("Full URL cache:")
            print("===============")
            try:
                sys.stdout.write(
                    stats.url_path.read_text(encoding="utf-8", errors="replace")
                )
                if not str(stats.url_path.read_bytes()[-1:]).endswith("\n"):
                    print()
            except OSError as e:
                print(f"(read error: {e})", file=sys.stderr)
        else:
            recent_urls = _tail_lines(stats.url_path, recent)
            if recent_urls:
                print(f"Recent URL entries (last {len(recent_urls)}):")
                for line in recent_urls:
                    print(f"  {line}")
                print()


def run_cache_interactive(ops: OpsConfig | None = None) -> int:
    """Interactive menu (parity with ~/bin/wallpaper-cache, extended for hashes)."""
    ops = ops or OpsConfig()
    stats = cache_stats(ops)

    show_cache(ops, full=False, recent=5)

    if not stats.any_exists:
        print("No cache files found.")
        print("They are created automatically on fetch / index.")
        return 0

    print("Choose an action:")
    print("  1) Clear entire cache (URLs + hash index — force fresh downloads)")
    print("  2) Clear URL log only")
    print("  3) Clear hash index only (re-run: wallpaperctl index)")
    print("  4) Keep only last 10 URL entries (moderate refresh)")
    print("  5) Keep only last 20 URL entries (light refresh)")
    print("  6) View full URL cache")
    print("  7) Show status and exit")
    print("  8) Cancel")
    print()
    try:
        choice = input("Enter choice (1-8): ").strip()
    except EOFError:
        print("No changes made.")
        return 0

    if choice == "1":
        cleared = clear_all_caches(ops)
        if cleared:
            print(f"✓ Cleared: {', '.join(cleared)}. Next fetch will be fully fresh.")
        else:
            print("Nothing to clear.")
    elif choice == "2":
        if clear_url_cache(ops):
            print("✓ URL log cleared.")
        else:
            print("No URL log found.")
    elif choice == "3":
        if clear_hash_cache(ops):
            print("✓ Hash index cleared. Rebuild with: wallpaperctl index")
        else:
            print("No hash index found.")
    elif choice == "4":
        n = trim_url_cache(10, ops)
        print(f"✓ URL cache trimmed to last {n} entries.")
    elif choice == "5":
        n = trim_url_cache(20, ops)
        print(f"✓ URL cache trimmed to last {n} entries.")
    elif choice == "6":
        show_cache(ops, full=True)
    elif choice == "7":
        show_cache(ops, full=False)
    elif choice == "8":
        print("No changes made.")
    else:
        print("Invalid choice. No changes made.")
        return 1
    return 0


def run_cache_command(
    ops: OpsConfig | None = None,
    *,
    action: str | None = None,
    keep: int | None = None,
) -> int:
    """
    Non-interactive cache management.

    action: status | clear | clear-urls | clear-hashes | trim | show | interactive
    """
    ops = ops or OpsConfig()
    act = (action or "interactive").lower().replace("_", "-")

    if act in ("interactive", "menu", ""):
        return run_cache_interactive(ops)

    if act in ("status", "stat", "info"):
        show_cache(ops, full=False)
        return 0

    if act in ("show", "list", "view"):
        show_cache(ops, full=True)
        return 0

    if act in ("clear", "clear-all", "reset"):
        cleared = clear_all_caches(ops)
        if cleared:
            print(f"✓ Cache cleared ({', '.join(cleared)}).")
        else:
            print("No cache files found to clear.")
        return 0

    if act in ("clear-urls", "clear-url"):
        if clear_url_cache(ops):
            print("✓ URL log cleared.")
        else:
            print("No URL log found.")
        return 0

    if act in ("clear-hashes", "clear-hash", "clear-index"):
        if clear_hash_cache(ops):
            print("✓ Hash index cleared.")
        else:
            print("No hash index found.")
        return 0

    if act == "trim":
        n = 10 if keep is None else keep
        remaining = trim_url_cache(n, ops)
        print(f"✓ URL cache trimmed to last {remaining} entries.")
        return 0

    print(f"Unknown cache action: {action}", file=sys.stderr)
    return 1
