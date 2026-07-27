"""Textual wallpaper manager TUI."""

from __future__ import annotations

from pathlib import Path


def run_manage_tui(
    *,
    directory: str | None = None,
    no_kitty: bool = False,
    warm_cache: bool = False,
    warm_only: bool = False,
) -> int:
    """Launch the manage TUI. Returns process exit code.

    *warm_cache* / *warm_only*: pre-build Kitty PNG and/or sixel previews under
    ``~/.cache/wallpaperctl/previews`` (also done in the background on TUI start).
    """
    from wallpaperctl.config import load_ops_config

    ops = load_ops_config()
    root = Path(directory).expanduser() if directory else ops.path("wallpaper_dir")
    root = root.expanduser()

    if warm_cache or warm_only:
        code = _warm_cache_cli(root, no_kitty=no_kitty)
        if warm_only or code != 0:
            return code

    try:
        from wallpaperctl.tui.app import ManageApp
    except ImportError as e:
        import sys

        print(
            "Error: Textual is required for the manage TUI.\n"
            "  pip install 'wallpaperctl[tui]'   # or: pip install textual\n"
            f"  ({e})",
            file=sys.stderr,
        )
        return 1

    app = ManageApp(library_root=root, ops=ops, no_kitty=no_kitty)
    app.run()
    return 0


def _warm_cache_cli(root: Path, *, no_kitty: bool = False) -> int:
    """Foreground cache warm with progress on stdout."""
    import sys

    from wallpaperctl.sources.local import list_wallpaper_files
    from wallpaperctl.term_graphics import GraphicsBackend, detect_backend, have_cmd
    from wallpaperctl.tui.preview_cache import warm_preview_cache

    if not root.is_dir():
        print(f"Error: library not found: {root}", file=sys.stderr)
        return 1

    paths = list_wallpaper_files(root)
    if not paths:
        print(f"No wallpapers in {root}")
        return 0

    info = detect_backend(no_kitty=no_kitty)
    warm_kitty = info.backend == GraphicsBackend.KITTY and not no_kitty
    warm_sixel = info.backend == GraphicsBackend.SIXEL
    # Explicit warm: also build sixel if tools exist (handy for --no-kitty later)
    if have_cmd("chafa") or have_cmd("img2sixel"):
        warm_sixel = True
    if not no_kitty:
        warm_kitty = True  # always store PNG thumbs for Kitty sessions

    print(
        f"Warming preview cache for {len(paths)} image(s) in {root}\n"
        f"  backend probe: {info.backend.value} ({info.detail or 'auto'})\n"
        f"  png={warm_kitty}  sixel={warm_sixel}\n"
        f"  cache dir: ~/.cache/wallpaperctl/previews"
    )

    def progress(i: int, n: int, path: Path) -> None:
        if i == 1 or i == n or i % 10 == 0:
            print(f"  [{i}/{n}] {path.name}", flush=True)

    stats = warm_preview_cache(
        paths,
        kitty=warm_kitty,
        sixel=warm_sixel,
        progress=progress,
    )
    print(
        f"Done: png_ok={stats['ok_png']} sixel_ok={stats['ok_sixel']} "
        f"fail={stats['fail']}"
    )
    return 0
