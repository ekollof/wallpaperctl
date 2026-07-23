"""Configuration loading (API keys + ops toggles).

Secrets stay in ~/.config/wallpaper/config.sh (or env / wallpaperctl TOML).
Never embed API keys in the package.
"""

from __future__ import annotations

import logging
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from wallpaperctl.util import home

log = logging.getLogger("wallpaperctl")


@dataclass
class ApiConfig:
    unsplash_access_key: str = ""
    pexels_api_key: str = ""
    pixabay_api_key: str = ""
    categories: str = "nature,landscape,architecture"

    def require_keys(self) -> None:
        missing = [
            name
            for name, val in (
                ("UNSPLASH_ACCESS_KEY", self.unsplash_access_key),
                ("PEXELS_API_KEY", self.pexels_api_key),
                ("PIXABAY_API_KEY", self.pixabay_api_key),
            )
            if not val
        ]
        if missing:
            path = home() / ".config" / "wallpaper" / "config.sh"
            raise SystemExit(
                f"Error: Missing API keys: {', '.join(missing)}\n"
                f"Create {path} with UNSPLASH_ACCESS_KEY, PEXELS_API_KEY, PIXABAY_API_KEY"
            )


@dataclass
class OpsConfig:
    operations_enabled: bool = True
    continue_on_error: bool = True
    debug_operations: bool = False

    enable_wallust: bool = True
    enable_xresources: bool = True
    enable_gtk_theme: bool = True
    enable_notifications: bool = True
    enable_openrgb: bool = True
    enable_emacs: bool = True
    enable_window_manager: bool = True
    enable_nwg_look: bool = True
    enable_cinnamon_theme: bool = True
    enable_dynamic_icons: bool = False
    enable_homeassistant: bool = True
    enable_steam_theme: bool = False
    enable_starttree: bool = True

    wallust_backend: str = "wal"
    wallust_palette: str = "kmeans"
    gtk_theme_plasma: str = "Breeze"
    gtk_theme_xfce: str = "FlatColor-dark"
    gtk_theme_cinnamon: str = "Mint-Y"
    gtk_theme_standalone: str = "FlatColor-dark"
    dynamic_icon_theme_name: str = "wallust-dynamic-icons"

    rgb_color_strategy: str = "warmest"
    openrgb_color_line_plasma: int = 3
    openrgb_color_line_standalone: int = 5

    emacs_theme: str = "ewal-doom-one"
    wallpaper_scaling_cinnamon: str = "scaled"
    wallpaper_scaling_gnome: str = "scaled"

    operation_timeout: int = 30
    wallust_timeout: int = 10
    openrgb_timeout: int = 5
    max_retries: int = 3
    retry_delay: float = 1.0

    # Paths

    wallpaper_dir: str = "~/Wallpapers"
    current_wallpaper_file: str = "~/.wallpaper"
    url_log: str = "~/.wallpaper_urls"
    hash_cache: str = "~/.wallpaper_hashes"
    # Hamming distance on 64-bit hashes (hash_size=8). Higher = catch more near-dups.
    # Old default was 10 and only checked a tiny cache; 14 + multi-hash consensus is
    # much better at credits/crops from different providers.
    perceptual_hash_threshold: int = 14
    hash_size: int = 8
    hash_consensus_slack: int = 4  # second-chance window for multi-algorithm votes
    target_width: int = 1920
    target_height: int = 1080
    aspect_min: float = 1.5
    aspect_max: float = 1.9
    fetch_max_attempts: int = 5

    extra: dict = field(default_factory=dict)

    def path(self, key: str) -> Path:
        raw = getattr(self, key)
        return Path(os.path.expanduser(raw))

    def apply_env_overrides(
        self,
        *,
        is_plasma: bool,
        is_hyprland: bool,
        is_xfce: bool,
        is_cinnamon: bool,
    ) -> None:
        """Apply DE-specific enable/disable overrides."""
        if is_plasma:
            self.enable_xresources = False
            self.enable_notifications = False
            self.enable_window_manager = False
            self.enable_nwg_look = False
        if is_hyprland:
            self.enable_xresources = False
            self.enable_window_manager = False
        if is_xfce:
            self.enable_notifications = False
            self.enable_nwg_look = False
            self.gtk_theme_standalone = self.gtk_theme_xfce
        if is_cinnamon:
            self.enable_notifications = False
            self.enable_nwg_look = False
            self.gtk_theme_standalone = self.gtk_theme_cinnamon
            self.enable_cinnamon_theme = True
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            self.enable_gtk_theme = False
            self.enable_notifications = False
            self.enable_window_manager = False
            self.enable_nwg_look = False
            self.enable_openrgb = False
        if os.environ.get("MINIMAL_MODE") == "1":
            self.enable_openrgb = False
            self.enable_emacs = False
            self.enable_nwg_look = False


def _parse_sh_exports(path: Path) -> dict[str, str]:
    """Parse KEY=value / export KEY=value from a shell config (no eval)."""
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    # Fix world-writable perms like the shell tool
    try:
        mode = path.stat().st_mode & 0o777
        if mode & 0o077:
            path.chmod(0o600)
            log.warning("Fixed permissions on %s to 600", path)
    except OSError:
        pass

    export_re = re.compile(
        r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$"
    )
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = export_re.match(line)
        if not m:
            continue
        key, raw = m.group(1), m.group(2).strip()
        # Strip matching quotes
        if (raw.startswith('"') and raw.endswith('"')) or (
            raw.startswith("'") and raw.endswith("'")
        ):
            raw = raw[1:-1]
        result[key] = raw
    return result


def load_api_config(categories_override: str | None = None) -> ApiConfig:
    cfg = ApiConfig()

    # Env first
    cfg.unsplash_access_key = os.environ.get("UNSPLASH_ACCESS_KEY", "")
    cfg.pexels_api_key = os.environ.get("PEXELS_API_KEY", "")
    cfg.pixabay_api_key = os.environ.get("PIXABAY_API_KEY", "")
    if os.environ.get("CATEGORIES"):
        cfg.categories = os.environ["CATEGORIES"]

    sh_path = home() / ".config" / "wallpaper" / "config.sh"
    if sh_path.is_file():
        values = _parse_sh_exports(sh_path)
        cfg.unsplash_access_key = values.get("UNSPLASH_ACCESS_KEY", cfg.unsplash_access_key)
        cfg.pexels_api_key = values.get("PEXELS_API_KEY", cfg.pexels_api_key)
        cfg.pixabay_api_key = values.get("PIXABAY_API_KEY", cfg.pixabay_api_key)
        if "CATEGORIES" in values and not categories_override:
            cfg.categories = values["CATEGORIES"]
        log.debug("Loaded API config from %s", sh_path)
    else:
        # Optional pure-Python config
        toml_path = home() / ".config" / "wallpaperctl" / "config.toml"
        if toml_path.is_file():
            data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
            api = data.get("api", data)
            cfg.unsplash_access_key = api.get("unsplash_access_key", cfg.unsplash_access_key)
            cfg.pexels_api_key = api.get("pexels_api_key", cfg.pexels_api_key)
            cfg.pixabay_api_key = api.get("pixabay_api_key", cfg.pixabay_api_key)
            if "categories" in api and not categories_override:
                cfg.categories = api["categories"]

    if categories_override:
        cfg.categories = categories_override

    return cfg


def load_ops_config() -> OpsConfig:
    cfg = OpsConfig()
    # Package defaults first, then user overrides
    sources: list[tuple[str, str]] = []
    defaults = Path(__file__).with_name("defaults.toml")
    if defaults.is_file():
        sources.append((str(defaults), defaults.read_text(encoding="utf-8")))
    else:
        try:
            from importlib.resources import files

            text = files("wallpaperctl").joinpath("defaults.toml").read_text(encoding="utf-8")
            sources.append(("package:defaults.toml", text))
        except Exception:
            pass

    override = os.environ.get("WALLPAPERCTL_CONFIG")
    user_paths: list[Path] = []
    if override:
        user_paths.append(Path(os.path.expanduser(override)))
    user_paths.append(home() / ".config" / "wallpaperctl" / "ops.toml")
    for path in user_paths:
        if path.is_file():
            sources.append((str(path), path.read_text(encoding="utf-8")))

    for label, text in sources:
        try:
            data = tomllib.loads(text)
        except Exception as e:
            log.warning("Failed to parse %s: %s", label, e)
            continue
        _apply_toml(cfg, data)
        log.debug("Loaded ops config from %s", label)

    return cfg



def _apply_toml(cfg: OpsConfig, data: dict) -> None:
    # Top-level + [ops]
    for section in (data, data.get("ops") or {}):
        if not isinstance(section, dict):
            continue
        for key, val in section.items():
            if key == "enable" or isinstance(val, dict):
                continue
            attr = key
            if hasattr(cfg, attr):
                setattr(cfg, attr, val)

    # [enable] wallust = true  → enable_wallust
    enable = data.get("enable") or {}
    if isinstance(enable, dict):
        for key, val in enable.items():
            attr = key if key.startswith("enable_") else f"enable_{key}"
            if hasattr(cfg, attr):
                setattr(cfg, attr, bool(val))
