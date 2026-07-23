"""Install vendored FlatColor / FlatColor-dark GTK themes."""

from __future__ import annotations

import shutil
from importlib import resources
from pathlib import Path

from wallpaperctl.util import home


def _packaged_themes_root() -> Path | None:
    here = Path(__file__).resolve().parent.parent / "data" / "themes"
    if (here / "FlatColor" / "index.theme").is_file():
        return here
    try:
        root = resources.files("wallpaperctl").joinpath("data").joinpath("themes")
        with resources.as_file(root) as p:
            if (Path(p) / "FlatColor" / "index.theme").is_file():
                return Path(p)
    except Exception:
        pass
    return None


def themes_status() -> dict:
    base = home() / ".local" / "share" / "themes"
    fc = base / "FlatColor"
    fcd = base / "FlatColor-dark"
    return {
        "install_dir": str(base),
        "flatcolor": fc.is_dir(),
        "flatcolor_dark": fcd.exists(),
        "flatcolor_path": str(fc),
        "flatcolor_dark_path": str(fcd),
    }


def bootstrap_themes(*, force: bool = False, yes: bool = False) -> int:
    """
    Copy packaged FlatColor into ~/.local/share/themes and link FlatColor-dark.
    """
    pkg = _packaged_themes_root()
    if pkg is None:
        print("Packaged themes not found in wallpaperctl install.")
        return 1

    dest_root = home() / ".local" / "share" / "themes"
    dest_root.mkdir(parents=True, exist_ok=True)
    src = pkg / "FlatColor"
    dest = dest_root / "FlatColor"
    dark = dest_root / "FlatColor-dark"

    print(f"package: {src}")
    print(f"target:  {dest}")

    if dest.is_dir() and not force:
        print(f"exists:  {dest} (use --force to replace)")
    else:
        do_copy = True
        if dest.exists() and force:
            if not yes:
                try:
                    ans = input(f"Replace {dest}? [y/N] ").strip().lower()
                except EOFError:
                    ans = "n"
                if ans not in ("y", "yes"):
                    print("Cancelled.")
                    do_copy = False
        if do_copy:
            if dest.exists():
                if dest.is_dir() and not dest.is_symlink():
                    shutil.rmtree(dest)
                else:
                    dest.unlink(missing_ok=True)
            shutil.copytree(src, dest, symlinks=True)
            print(f"wrote:   {dest}")

    # FlatColor-dark → FlatColor
    if dark.is_symlink() or not dark.exists():
        if dark.is_symlink() or dark.exists():
            dark.unlink()
        dark.symlink_to("FlatColor")
        print(f"link:    {dark} → FlatColor")
    elif dark.is_dir() and force:
        shutil.rmtree(dark)
        dark.symlink_to("FlatColor")
        print(f"link:    {dark} → FlatColor (replaced directory)")
    else:
        print(f"exists:  {dark} (not a symlink; leave alone or --force)")

    print()
    print("Wallust will recolor FlatColor via templates:")
    print("  ~/.local/share/themes/FlatColor/gtk-2.0/gtkrc")
    print("  ~/.local/share/themes/FlatColor/gtk-3.0/gtk.css")
    print("  ~/.local/share/themes/FlatColor/gtk-3.20/gtk.css")
    print("Select theme: FlatColor or FlatColor-dark in Appearance / gsettings.")
    return 0
