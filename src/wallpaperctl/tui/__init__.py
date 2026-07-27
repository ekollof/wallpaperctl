"""Textual wallpaper manager TUI."""

from __future__ import annotations


def run_manage_tui(
    *,
    directory: str | None = None,
    no_kitty: bool = False,
) -> int:
    """Launch the manage TUI. Returns process exit code."""
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

    from pathlib import Path

    from wallpaperctl.config import load_ops_config

    ops = load_ops_config()
    root = Path(directory).expanduser() if directory else ops.path("wallpaper_dir")
    app = ManageApp(library_root=root, ops=ops, no_kitty=no_kitty)
    app.run()
    return 0
