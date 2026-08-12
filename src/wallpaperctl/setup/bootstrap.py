"""Create wallpaperctl config dirs and sample files."""

from __future__ import annotations

from wallpaperctl.util import home

_OPS_TOML = """\
# wallpaperctl operations config
# Defaults: package defaults.toml; this file overrides.
# See: wallpaperctl setup check | wallpaperctl ops list

operations_enabled = true
continue_on_error = true

# Color / wallust (uncomment to override)
# rgb_color_strategy = "warmest"
#   # least_blue | warmest | most_saturated | coolest | brightest | fixed
# wallust_backend = "wal"
# wallust_palette = "kmeans"
# cosmic_theme_mode = "surfaces"       # accent | surfaces | full
# cosmic_accent_softness = 0.42
# cosmic_accent_desaturate = 0.22
# operation_timeout = 30
# wallust_timeout = 10
# openrgb_timeout = 5
# openlinkhub_url = "http://127.0.0.1:27003"
# openlinkhub_timeout = 5.0
# openlinkhub_brightness = 1.0
# max_retries = 3
# retry_delay = 1.0

[enable]
wallust = true
xresources = true
gtk_theme = true
notifications = true
openrgb = true
openlinkhub = true
emacs = true
window_manager = true
nwg_look = true
cinnamon_theme = true
dynamic_icons = false
homeassistant = true
steam_theme = false
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
