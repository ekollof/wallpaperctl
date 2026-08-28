"""Command-line interface — shell-compatible flags + subcommands."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from wallpaperctl import __version__
from wallpaperctl.app import apply_wallpaper, load_current_wallpaper, save_current_wallpaper
from wallpaperctl.config import load_api_config, load_ops_config
from wallpaperctl.detect.desktop import detect_desktop
from wallpaperctl.detect.tools import detect_tools
from wallpaperctl.lock import WallpaperLock
from wallpaperctl.media import is_animated
from wallpaperctl.notify import safe_notify
from wallpaperctl.sources.cache_mgr import clear_all_caches, run_cache_command
from wallpaperctl.sources.fetch import (
    fetch_random_animated_wallpaper,
    fetch_random_wallpaper,
)
from wallpaperctl.sources.local import pick_random_wallpaper
from wallpaperctl.sources.optimize import add_credits
from wallpaperctl.theme.runner import list_ops
from wallpaperctl.util import ensure_debug_logging, have, run


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Subcommand path when first arg is a known command
    subcommands = {
        "set",
        "random",
        "fetch",
        "reload",
        "clear-cache",
        "detect",
        "ops",
        "undup",
        "index",
        "cache",
        "reload-wm",
        "cleanup",
        "verify",
        "setup",
        "migrate",
        "manage",
        "version",
        "help",
    }
    if argv and not argv[0].startswith("-") and argv[0] in subcommands:
        return _subcommand_main(argv)

    # Classic getopt-style: -r -R -C -c -m categories [path]
    return _classic_main(argv)


def _classic_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="wallpaperctl",
        description="Set wallpaper and apply theme operations",
        add_help=True,
    )
    parser.add_argument(
        "-r",
        action="store_true",
        help="Fetch a random wallpaper from Unsplash, Pexels, or Pixabay (1920x1080)",
    )
    parser.add_argument(
        "-R",
        action="store_true",
        help="Reload the current wallpaper from ~/.wallpaper",
    )
    parser.add_argument(
        "-C",
        action="store_true",
        help="Clear wallpaper cache (URLs + perceptual hashes)",
    )
    parser.add_argument(
        "-m",
        action="store_true",
        help="Open Textual wallpaper manager TUI (same as: manage)",
    )
    parser.add_argument(
        "--animated",
        action="store_true",
        help=(
            "Pick a random animated wallpaper from ~/Wallpapers/animated "
            "(with -r: fetch a video from Pexels/Pixabay)"
        ),
    )
    parser.add_argument(
        "-c",
        dest="categories",
        metavar="categories",
        help="Categories (comma-separated), e.g. space,galaxy",
    )
    parser.add_argument(
        "-x",
        dest="exclude",
        metavar="keywords",
        help=(
            "Exclude keywords (comma-separated); skip downloads whose "
            "tags/alt/description match (client-side filter)"
        ),
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="Path to a specific wallpaper file",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"wallpaperctl {__version__}",
    )
    args = parser.parse_args(argv)

    debug = bool(os.environ.get("DEBUG"))
    ensure_debug_logging(debug)
    ops = load_ops_config()

    if args.C:
        cleared = clear_all_caches(ops)
        if cleared:
            print(
                f"✓ Cache cleared ({', '.join(cleared)}). "
                "Next download will fetch fresh wallpapers."
            )
        else:
            print("No cache files found to clear.")
        return 0

    if args.m:
        from wallpaperctl.tui import run_manage_tui

        return run_manage_tui()

    lock = WallpaperLock()
    lock.acquire()
    try:
        return _run_action(
            fetch=args.r,
            reload_=args.R,
            categories=args.categories,
            exclude=args.exclude,
            path=args.path,
            ops=ops,
            debug=debug,
            animated=args.animated,
        )
    finally:
        lock.release()


def _run_action(
    *,
    fetch: bool,
    reload_: bool,
    categories: str | None,
    path: str | None,
    ops,
    debug: bool,
    animated: bool = False,
    exclude: str | None = None,
) -> int:
    photographer_name = ""
    photographer_username = ""
    provider_name = ""
    wallpaper: Path | None = None

    if fetch:
        api = load_api_config(
            categories_override=categories,
            exclude_override=exclude,
        )
        api.require_keys()
        if animated:
            print("Fetching random animated wallpaper from Pexels/Pixabay...")
            result = fetch_random_animated_wallpaper(api, ops)
        else:
            print(
                "Fetching random wallpaper from Unsplash, Pexels, or Pixabay (1920x1080)..."
            )
            result = fetch_random_wallpaper(api, ops)
        what = "animated wallpaper" if animated else "wallpaper"
        if result is None:
            print(
                f"Error: Failed to fetch an {what} after all attempts.",
                file=sys.stderr,
            )
            print(
                f"Falling back to local random wallpaper from "
                f"{ops.path('wallpaper_dir')}...",
                file=sys.stderr,
            )
            safe_notify("Wallpaper Script", "Remote fetch failed, using local wallpaper")
            wallpaper = pick_random_wallpaper(ops, animated_only=animated)
            print(f"Selected local wallpaper: {wallpaper.name}")
        else:
            wallpaper = result.path
            photographer_name = result.photographer_name
            photographer_username = result.photographer_username
            provider_name = result.provider_name
            print(
                f"Downloaded {what}: {wallpaper.name}\n"
                f"  by {photographer_name} from {provider_name}"
            )
            if result.tags:
                print(f"  tags: {result.tags}")
            else:
                print("  tags: (none from provider)")
            safe_notify(
                "Wallpaper Script",
                f"Downloaded {what} by {photographer_name} from {provider_name}",
            )
    elif reload_:
        print("Reloading current wallpaper...")
        wallpaper = load_current_wallpaper(ops)
        # Noctalia fast path
        de = detect_desktop()
        if de.noctalia and have("qs"):
            r = run(
                [
                    "qs",
                    "-c",
                    "noctalia-shell",
                    "ipc",
                    "call",
                    "wallpaper",
                    "set",
                    str(wallpaper),
                    "all",
                ],
                timeout=15,
            )
            if r.returncode == 0:
                print(f"Reloaded wallpaper via Noctalia: {wallpaper.name}")
                save_current_wallpaper(wallpaper, ops)
                ok = apply_wallpaper(
                    wallpaper,
                    ops,
                    debug=debug,
                )
                return 0 if ok else 1
            print(
                "Warning: Noctalia wallpaper reload failed, falling back...",
                file=sys.stderr,
            )
    elif path:
        print(f"Setting specified wallpaper: {path}...")
        wallpaper = Path(path).expanduser()
    else:
        print(f"Picking random wallpaper from {ops.path('wallpaper_dir')}...")
        wallpaper = pick_random_wallpaper(ops, animated_only=animated)
        print(f"Selected wallpaper: {wallpaper.name}")

    assert wallpaper is not None
    if not wallpaper.is_file():
        print(f"Error: File '{wallpaper}' not found!", file=sys.stderr)
        return 1

    if (
        fetch
        and photographer_name
        and photographer_username
        and provider_name
        and not is_animated(wallpaper)
    ):
        if "_credited.jpg" not in wallpaper.name:
            print(f"Attempting to add credits to wallpaper from {provider_name}")
            wallpaper = add_credits(
                wallpaper,
                photographer_name,
                photographer_username,
                provider_name,
            )

    save_current_wallpaper(wallpaper, ops)
    ok = apply_wallpaper(
        wallpaper,
        ops,
        photographer_name=photographer_name,
        photographer_username=photographer_username,
        provider_name=provider_name,
        debug=debug,
    )
    return 0 if ok else 1


def _subcommand_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wallpaperctl")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_set = sub.add_parser("set", help="Set a specific wallpaper")
    p_set.add_argument("path")

    p_random = sub.add_parser("random", help="Pick random local wallpaper")
    p_random.add_argument(
        "--animated",
        action="store_true",
        help="Pick only from ~/Wallpapers/animated",
    )

    p_fetch = sub.add_parser("fetch", help="Fetch remote wallpaper")
    p_fetch.add_argument("-c", "--categories", default=None)
    p_fetch.add_argument(
        "-x",
        "--exclude",
        default=None,
        help="Exclude keywords (comma-separated); client-side tag/alt filter",
    )
    p_fetch.add_argument(
        "--animated",
        action="store_true",
        help="Fetch a video wallpaper from Pexels/Pixabay into ~/Wallpapers/animated",
    )

    sub.add_parser("reload", help="Reload ~/.wallpaper")
    sub.add_parser("clear-cache", help="Clear URL + hash caches (same as: cache clear)")
    p_cache = sub.add_parser(
        "cache",
        help="Manage duplicate-detection caches (replaces wallpaper-cache)",
    )
    p_cache.add_argument(
        "action",
        nargs="?",
        default="interactive",
        choices=[
            "interactive",
            "status",
            "show",
            "clear",
            "clear-urls",
            "clear-hashes",
            "trim",
        ],
        help="Action (default: interactive menu like wallpaper-cache)",
    )
    p_cache.add_argument(
        "--keep",
        type=int,
        default=None,
        help="With trim: number of URL entries to keep (default 10)",
    )
    sub.add_parser("detect", help="Show detected desktop and tools")

    p_ops = sub.add_parser("ops", help="List theme operations")
    p_ops.add_argument("action", nargs="?", default="list", choices=["list"])
    sub.add_parser(
        "index",
        help="(Re)build perceptual hash index for the wallpaper library",
    )
    p_undup = sub.add_parser(
        "undup",
        help="Find near-duplicate images in a directory (wall-undup)",
    )
    p_undup.add_argument(
        "directory",
        nargs="?",
        default=None,
        help="Directory to scan (default: ~/Wallpapers)",
    )
    p_undup.add_argument(
        "--threshold",
        type=int,
        default=None,
        help="Hamming distance threshold (default: from config, currently multi-hash)",
    )
    p_undup.add_argument(
        "--hash-size",
        type=int,
        default=None,
        help="Perceptual hash size (default: 8)",
    )
    p_undup.add_argument(
        "--delete",
        action="store_true",
        help="Prompt to delete duplicates interactively",
    )
    p_undup.add_argument(
        "--confident",
        action="store_true",
        help=(
            "Auto-delete only high-confidence duplicates (≥90%%); "
            "skip weaker matches (implies --delete, never prompts)"
        ),
    )
    p_undup.add_argument(
        "--no-kitty",
        action="store_true",
        help="Disable Kitty graphics side-by-side preview",
    )
    p_rwm = sub.add_parser(
        "reload-wm",
        help="Force Cinnamon WM theme reload (wallpaper-reload-wm)",
    )
    p_rwm.add_argument(
        "--restart",
        "-r",
        action="store_true",
        help="Full Cinnamon restart (most reliable for decorations)",
    )
    p_clean = sub.add_parser(
        "cleanup",
        help="Clean theme backups and stale temp files (cleanup-theme-backups)",
    )
    p_clean.add_argument(
        "--keep-backups",
        type=int,
        default=2,
        help="Number of cinnamon-dynamic backups to keep (default 2)",
    )
    p_clean.add_argument(
        "--cache-days",
        type=int,
        default=7,
        help="Delete ~/.cache/wallpaper files older than N days (default 7)",
    )
    p_verify = sub.add_parser(
        "verify",
        help="Verify dynamic icons / cinnamon theme / wallust colors / omarchy chain",
    )
    p_verify.add_argument(
        "target",
        nargs="?",
        default="all",
        choices=["all", "icons", "cinnamon", "wal", "omarchy"],
        help="What to verify (default: all)",
    )
    sub.add_parser(
        "migrate",
        help="Read-only cutover checklist (shell scripts → wallpaperctl)",
    )
    p_manage = sub.add_parser(
        "manage",
        help="Textual TUI: browse / preview / multi-select / delete / set",
    )
    p_manage.add_argument(
        "directory",
        nargs="?",
        default=None,
        help="Library directory (default: ~/Wallpapers)",
    )
    p_manage.add_argument(
        "--no-kitty",
        action="store_true",
        help="Disable Kitty graphics protocol (use sixel/chafa/blocks)",
    )
    p_manage.add_argument(
        "--video",
        action="store_true",
        help="Manage animated wallpapers (videos) — thumbnails from the "
        "cached extracted frame",
    )
    p_manage.add_argument(
        "--warm-cache",
        action="store_true",
        help="Pre-build Kitty PNG / sixel previews (then open the TUI)",
    )
    p_manage.add_argument(
        "--warm-only",
        action="store_true",
        help="Only warm the preview cache, then exit (no TUI)",
    )
    p_setup = sub.add_parser(
        "setup",
        help="Check/install dependencies and bootstrap config / wallust",
    )
    p_setup.add_argument(
        "action",
        nargs="?",
        default="check",
        choices=[
            "check",
            "install",
            "wallust",
            "wallust-templates",
            "themes",
            "config",
            "omarchy",
            "all",
        ],
        help="check | install | wallust | wallust-templates | themes | config | omarchy | all",
    )
    p_setup.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Non-interactive: assume yes for installs",
    )
    p_setup.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing wallust.toml / ops.toml when bootstrapping",
    )
    p_setup.add_argument(
        "--optional",
        action="store_true",
        help="Include optional packages (openrgb, mako, …) on install",
    )
    p_setup.add_argument(
        "--all-desktops",
        action="store_true",
        help="On check: list deps for every DE, not only the active one",
    )
    sub.add_parser("version", help="Print version")

    args = parser.parse_args(argv)

    debug = bool(os.environ.get("DEBUG"))
    ensure_debug_logging(debug)
    ops = load_ops_config()

    if args.cmd == "version":
        print(f"wallpaperctl {__version__}")
        return 0
    if args.cmd == "detect":
        de = detect_desktop()
        tools = detect_tools(de, strict=False)
        print(f"Desktop: {de.name}")
        print(
            f"  plasma={de.plasma} hyprland={de.hyprland} noctalia={de.noctalia} "
            f"xfce={de.xfce} cinnamon={de.cinnamon} cosmic={de.cosmic} "
            f"awesome={de.awesome} omarchy={de.omarchy}"
        )
        if tools.missing_required:
            print("Missing required:")
            for m in tools.missing_required:
                print(f"  - {m}")
            print("  → wallpaperctl setup check | wallpaperctl setup install")
        if tools.warnings:
            print("Warnings:")
            for w in tools.warnings:
                print(f"  - {w}")
        print("Tools present:")
        for k, v in sorted(tools.present.items()):
            print(f"  {k}: {v}")
        print("(Full audit: wallpaperctl setup check)")
        return 0
    if args.cmd == "ops":
        print("Theme operations (in order):")
        for name in list_ops():
            print(f"  - {name}")
        print("\nWallpaper setters:")
        for name in (
            "omarchy",
            "animated",
            "plasma",
            "cosmic",
            "noctalia",
            "hyprland",
            "xfce",
            "cinnamon",
            "fallback",
        ):
            print(f"  - {name}")
        return 0
    if args.cmd == "clear-cache":
        cleared = clear_all_caches(ops)
        if cleared:
            print(f"✓ Cache cleared ({', '.join(cleared)}).")
        else:
            print("No cache files found.")
        return 0
    if args.cmd == "cache":
        return run_cache_command(ops, action=args.action, keep=args.keep)
    if args.cmd == "index":

        from wallpaperctl.sources.dedup import LibraryIndex

        print(f"Indexing {ops.path('wallpaper_dir')} …")
        idx = LibraryIndex(ops)
        entries = idx.ensure_loaded(progress=True)
        print(f"✓ Index ready: {len(entries)} fingerprints → {ops.path('hash_cache')}")
        return 0
    if args.cmd == "undup":
        from wallpaperctl.sources.undup import run_undup

        return run_undup(
            Path(args.directory) if args.directory else None,
            ops=ops,
            threshold=args.threshold,
            hash_size=args.hash_size,
            delete=args.delete,
            confident=args.confident,
            no_kitty=args.no_kitty,
        )
    if args.cmd == "reload-wm":
        from wallpaperctl.maint.reload_wm import run_reload_wm

        return run_reload_wm(restart=args.restart)
    if args.cmd == "cleanup":
        from wallpaperctl.maint.cleanup import run_cleanup

        return run_cleanup(
            keep_backups=args.keep_backups,
            cache_max_age_days=args.cache_days,
        )
    if args.cmd == "verify":
        from wallpaperctl.maint.verify import run_verify

        return run_verify(args.target, ops=ops)
    if args.cmd == "setup":
        from wallpaperctl.setup import run_setup

        return run_setup(
            args.action,
            yes=args.yes,
            force=args.force,
            optional=args.optional,
            all_desktops=args.all_desktops,
        )
    if args.cmd == "migrate":
        from wallpaperctl.maint.migrate import run_migrate_check

        return run_migrate_check(ops)
    if args.cmd == "manage":
        from wallpaperctl.tui import run_manage_tui

        return run_manage_tui(
            directory=args.directory,
            no_kitty=args.no_kitty,
            warm_cache=args.warm_cache,
            warm_only=args.warm_only,
            videos=args.video,
        )

    lock = WallpaperLock()

    lock.acquire()
    try:
        if args.cmd == "set":
            return _run_action(
                fetch=False,
                reload_=False,
                categories=None,
                path=args.path,
                ops=ops,
                debug=debug,
                animated=False,
            )
        if args.cmd == "random":
            return _run_action(
                fetch=False,
                reload_=False,
                categories=None,
                path=None,
                ops=ops,
                debug=debug,
                animated=args.animated,
            )
        if args.cmd == "fetch":
            return _run_action(
                fetch=True,
                reload_=False,
                categories=args.categories,
                exclude=args.exclude,
                path=None,
                ops=ops,
                debug=debug,
                animated=args.animated,
            )
        if args.cmd == "reload":
            return _run_action(
                fetch=False,
                reload_=True,
                categories=None,
                path=None,
                ops=ops,
                debug=debug,
            )
    finally:
        lock.release()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
