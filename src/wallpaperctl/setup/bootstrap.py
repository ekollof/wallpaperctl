"""Create wallpaperctl config dirs and sample files."""

from __future__ import annotations

from pathlib import Path

from wallpaperctl.util import home

_OPS_TOML = """\
# wallpaperctl operations config
# See: wallpaperctl setup check

# rgb_color_strategy = "warmest"   # or least_blue, most_saturated, fixed
# wallust_backend = "wal"
# wallust_palette = "kmeans"

[enable]
wallust = true
gtk_theme = true
openrgb = true
homeassistant = true
dynamic_icons = false
# notifications = true
# nwg_look = true
"""

_API_HINT = """\
# Wallpaper fetch API keys (used by wallpaperctl -r)
# chmod 600 this file
#
# export UNSPLASH_ACCESS_KEY="..."
# export PEXELS_API_KEY="..."
# export PIXABAY_API_KEY="..."
# export CATEGORIES="nature,landscape,architecture"
"""


def bootstrap_config(*, force: bool = False) -> int:
    cfg_dir = home() / ".config" / "wallpaperctl"
    wall_cfg = home() / ".config" / "wallpaper"
    walls = home() / "Wallpapers"
    wal = home() / ".cache" / "wal"

    for d in (cfg_dir, wall_cfg, walls, wal):
        d.mkdir(parents=True, exist_ok=True)
        print(f"dir: {d}")

    ops = cfg_dir / "ops.toml"
    if not ops.is_file() or force:
        ops.write_text(_OPS_TOML, encoding="utf-8")
        print(f"wrote: {ops}")
    else:
        print(f"exists: {ops}")

    api = wall_cfg / "config.sh"
    if not api.is_file():
        api.write_text(_API_HINT, encoding="utf-8")
        try:
            api.chmod(0o600)
        except OSError:
            pass
        print(f"wrote: {api}  (add API keys for wallpaperctl -r)")
    else:
        print(f"exists: {api}")

    print()
    print("Next:")
    print("  wallpaperctl setup check")
    print("  wallpaperctl setup install     # system packages for this DE")
    print("  wallpaperctl setup wallust     # minimal wallust if needed")
    print("  wallpaperctl detect")
    return 0
