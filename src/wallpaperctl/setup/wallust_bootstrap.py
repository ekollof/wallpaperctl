"""Bootstrap wallust config from vendored templates/hooks (shipped with wallpaperctl)."""

from __future__ import annotations

import shutil
from importlib import resources
from pathlib import Path

from wallpaperctl.util import have, home, run


def wallust_config_dir() -> Path:
    return home() / ".config" / "wallust"


def wallust_status() -> dict:
    cfg = wallust_config_dir() / "wallust.toml"
    return {
        "binary": have("wallust"),
        "config_dir": str(wallust_config_dir()),
        "config_exists": cfg.is_file(),
        "config_path": str(cfg),
        "templates_dir": str(wallust_config_dir() / "templates"),
        "scripts_dir": str(wallust_config_dir() / "scripts"),
        "wal_cache": str(home() / ".cache" / "wal"),
        "wal_colors": (home() / ".cache" / "wal" / "colors").is_file(),
    }


def _packaged_wallust_root() -> Path | None:
    """Return filesystem path to packaged data/wallust (editable or wheel)."""
    # Source tree / editable install
    here = Path(__file__).resolve().parent.parent / "data" / "wallust"
    if (here / "wallust.toml").is_file():
        return here
    try:
        root = resources.files("wallpaperctl").joinpath("data").joinpath("wallust")
        # importlib.resources Traversable
        if hasattr(root, "is_dir") and root.is_dir():  # type: ignore[attr-defined]
            with resources.as_file(root) as p:
                if (p / "wallust.toml").is_file():
                    return Path(p)
    except Exception:
        pass
    return None


def bootstrap_wallust(
    *,
    force: bool = False,
    yes: bool = False,
    templates_only: bool = False,
) -> int:
    """
    Install vendored wallust.toml + templates + hook scripts into ~/.config/wallust.

    By default does not overwrite an existing wallust.toml (unless force).
    Missing templates/scripts are always filled in; with force, templates are
    refreshed from the package as well.
    """
    st = wallust_status()
    if not st["binary"]:
        print("wallust binary not found. Install it first:")
        print("  Arch/CachyOS:  paru -S wallust-git   # or pacman -S wallust")
        print("  cargo:         cargo install wallust")
        print("  Then re-run:   wallpaperctl setup wallust")
        return 1

    pkg = _packaged_wallust_root()
    if pkg is None:
        print("Packaged wallust data not found in wallpaperctl install.")
        return 1

    cfg_dir = wallust_config_dir()
    tpl_dir = cfg_dir / "templates"
    scripts_dir = cfg_dir / "scripts"
    cfg = cfg_dir / "wallust.toml"
    wal = home() / ".cache" / "wal"

    print(f"wallust:  {shutil.which('wallust')}")
    print(f"package:  {pkg}")
    print(f"target:   {cfg_dir}")

    cfg_dir.mkdir(parents=True, exist_ok=True)
    wal.mkdir(parents=True, exist_ok=True)

    # --- wallust.toml ---
    if not templates_only:
        if cfg.is_file() and not force:
            print(f"exists:  {cfg} (use --force to replace; templates still filled)")
        else:
            if cfg.is_file() and force:
                if not yes:
                    try:
                        ans = input(f"Overwrite {cfg}? [y/N] ").strip().lower()
                    except EOFError:
                        ans = "n"
                    if ans not in ("y", "yes"):
                        print("Cancelled config overwrite; installing templates only.")
                        templates_only = True
                    else:
                        backup = cfg.with_suffix(".toml.bak-wallpaperctl")
                        shutil.copy2(cfg, backup)
                        print(f"backup:  {backup}")
            if not templates_only:
                shutil.copy2(pkg / "wallust.toml", cfg)
                print(f"wrote:   {cfg}")

    # --- templates ---
    src_tpl = pkg / "templates"
    n_tpl = _copy_tree(src_tpl, tpl_dir, overwrite=force)
    print(f"templates: {n_tpl} file(s) → {tpl_dir}")

    # --- scripts (hooks) ---
    src_scripts = pkg / "scripts"
    if src_scripts.is_dir():
        n_sc = _copy_tree(src_scripts, scripts_dir, overwrite=force, mode_exec=True)
        print(f"scripts:   {n_sc} file(s) → {scripts_dir}")
        print("  hooks reference: python3 ~/.config/wallust/scripts/…")

    print()
    print("wallpaperctl runs: wallust run --backend wal --palette kmeans <image>")
    print("(your wallust.toml backend/palette defaults apply when using wallust CLI directly)")
    return 0


def _copy_tree(
    src: Path,
    dest: Path,
    *,
    overwrite: bool,
    mode_exec: bool = False,
) -> int:
    if not src.is_dir():
        return 0
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    for path in sorted(src.rglob("*")):
        if not path.is_file():
            continue
        if path.name.endswith(".pyc") or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(src)
        target = dest / rel
        if target.is_file() and not overwrite:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        if mode_exec:
            try:
                target.chmod(target.stat().st_mode | 0o111)
            except OSError:
                pass
        count += 1
    return count


def smoke_test_wallust(image: Path | None = None) -> int:
    """Run wallust once if an image is available."""
    if not have("wallust"):
        print("wallust not installed.")
        return 1
    img = image
    if img is None:
        cur = home() / ".wallpaper"
        if cur.is_file():
            p = Path(cur.read_text(encoding="utf-8").strip())
            if p.is_file():
                img = p
    if img is None or not img.is_file():
        print("No image for smoke test (set a wallpaper first or pass a path).")
        return 0
    print(f"Smoke test: wallust run {img}")
    r = run(
        ["wallust", "run", "--backend", "wal", "--palette", "kmeans", str(img)],
        timeout=60,
    )
    if r.returncode != 0:
        print(r.stderr or r.stdout)
        return r.returncode
    colors = home() / ".cache" / "wal" / "colors"
    if colors.is_file():
        print(f"OK — wrote {colors}")
        return 0
    print("wallust exited 0 but ~/.cache/wal/colors missing — check templates.")
    return 1
