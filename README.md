# wallpaperctl

Cross-platform wallpaper + theme controller for **Linux**, **OpenBSD**, and **FreeBSD**.

Python rewrite of a modular POSIX shell wallpaper system (`wallpaper` + `wallpaper.d`).
It fetches or picks wallpapers, sets them for the active desktop environment, and runs
theme operations (wallust palette, GTK, notifications, OpenRGB, Home Assistant, etc.).

**Author:** Emiel Kollof \<emiel@kollof.nl\>

### AI-assisted development

This project is **AI-assisted**. Substantial design and implementation work was
done with AI coding agents (including Grok / xAI tooling), under human direction
and review by the author. Treat the code as collaboratively authored: review
diffs, run tests, and verify on your desktop before relying on it in production
workflows.

## Install

### pipx (recommended for CLI tools)

```bash
pipx install ~/devel/wallpaperctl
# or from a git checkout:
pipx install .
```

### uv

```bash
uv tool install ~/devel/wallpaperctl
# or editable for development:
uv tool install --editable ~/devel/wallpaperctl
```

### venv / pip

```bash
cd ~/devel/wallpaperctl
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Entry points: `wallpaperctl` and `wallpaper` (compat alias).

## CLI (shell-compatible)

```text
wallpaperctl [-r] [-R] [-C] [-c categories] [<path_to_wallpaper>]

  -r  Fetch a random wallpaper (Unsplash / Pexels / Pixabay, ~1920x1080)
  -R  Reload the current wallpaper from ~/.wallpaper
  -C  Clear URL + perceptual-hash caches
  -c  Categories (comma-separated), e.g. space,galaxy
  (no args)  Pick a random file from ~/Wallpapers
  <path>     Set a specific image
```

Extra subcommands (optional; classic flags still work as the default path):

```bash
wallpaperctl set /path/to/image.jpg
wallpaperctl random
wallpaperctl fetch -c nature,landscape
wallpaperctl reload
wallpaperctl clear-cache
wallpaperctl detect          # show detected DE/tools
wallpaperctl ops list        # list theme/wallpaper operations
wallpaperctl index           # rebuild perceptual hash index for ~/Wallpapers
wallpaperctl undup [dir]     # find near-duplicates (wall-undup; optional --delete)
wallpaperctl cache           # interactive cache manager (replaces wallpaper-cache)
wallpaperctl cache status    # show URL log + hash index stats
wallpaperctl cache clear     # clear both caches
wallpaperctl cache trim --keep 10
wallpaperctl reload-wm           # Cinnamon WM theme hot-reload
wallpaperctl reload-wm --restart # full Cinnamon restart
wallpaperctl cleanup             # prune theme backups / stale temps
wallpaperctl verify              # icons + cinnamon + wallust colors
wallpaperctl verify icons
```




Environment:

| Variable | Effect |
|----------|--------|
| `DEBUG=1` | Verbose debug logging |
| `MINIMAL_MODE=1` | Disable optional theme ops |
| `WALLPAPERCTL_CONFIG` | Override ops config path |

## Configuration

### API keys (fetch)

Same path as the shell tool — **not** shipped in the package:

`~/.config/wallpaper/config.sh`

```sh
export UNSPLASH_ACCESS_KEY="..."
export PEXELS_API_KEY="..."
export PIXABAY_API_KEY="..."
export CATEGORIES="nature,landscape,architecture"  # optional default
```

Permissions should be `600`. Values can also live in a TOML/YAML-free
`~/.config/wallpaperctl/config.toml` if you prefer pure Python config
(keys override / supplement `config.sh`).

### Operations config

`~/.config/wallpaperctl/ops.toml` (optional). Defaults live in
`src/wallpaperctl/defaults.toml`. Environment detection still applies
Plasma/Hyprland/XFCE/Cinnamon overrides at runtime.

### Home Assistant

Optional: `~/.config/hass.cfg` (`[auth]` with `server=`, `token=`, `lamp=`).

## Desktop environments

| Environment | Wallpaper setter |
|-------------|------------------|
| KDE Plasma | `dbus-send` PlasmaShell script (+ lockscreen `kscreenlockerrc`) |
| Hyprland | `hyprctl hyprpaper` (skipped when Noctalia is active) |
| Noctalia | `qs -c noctalia-shell ipc call wallpaper set … all` |
| XFCE | `xfconf-query` per monitor/workspace |
| Cinnamon | `gsettings` picture-uri + options |
| Fallback X11 | `feh` → `nitrogen` → `hsetroot` → `xwallpaper` → `xsetbg` |

## Theme operations (order)

1. wallust  
2. xresources (`xrdb -merge`)  
3. nwg-look  
4. notifications (dunst / mako + waybar)  
5. openrgb  
6. emacs (`emacs-daemon`)  
7. window-manager signals (`xsetroot`, xsettingsd, awesome)  
8. gtk-theme  
9. cinnamon-theme (dynamic CSS/WM theme)  
10. dynamic-icons  
11. homeassistant  
12. steam-theme (stub / disabled, same as shell)

Wallpaper setters run **before** theme ops.

## External tools

Required for full functionality (soft-deps skip when missing):

- Image: **Pillow** (bundled dependency) for resize, credits, aspect checks, validation
- Fetch: network (httpx; no curl/ImageMagick required)
- Notifications: session D-Bus via **jeepney** (no `notify-send`)
- DE tools as applicable: `dbus-send`, `hyprctl`, `qs`, `xfconf-query`, `gsettings`
- Theme: `wallust`, `xrdb`, `nwg-look`, `dunst`/`mako`, `openrgb`, …
- Fallback setters: `feh`, `nitrogen`, …

## State files

| Path | Purpose |
|------|---------|
| `~/.wallpaper` | Last set path |
| `~/Wallpapers/` | Local library + downloaded images |
| `~/.wallpaper_urls` | URL/ID dedup log |
| `~/.wallpaper_hashes` | Multi-hash library index (dHash+pHash+aHash, v2) |

| `~/.wallpaper_errors.log` | Error log |
| `~/.cache/wal/` | wallust/pywal colors |

## Migration from the shell scripts

`wallpaperctl` is fully self-contained — it does **not** call or depend on
`~/bin/wallpaper` or `~/bin/wallpaper.d/`.

1. Install with pipx/uv.  
2. Keep `~/.config/wallpaper/config.sh` as-is (API keys only).  
3. Optionally put ops toggles in `~/.config/wallpaperctl/ops.toml`.  
4. Point bindings / cron / hyprland exec from `wallpaper` to `wallpaperctl` (or
   use the `wallpaper` entry point installed by this package).  
5. Once happy, you can remove the old shell scripts.

## Development

```bash
cd ~/devel/wallpaperctl
uv sync --all-extras
uv run wallpaperctl detect
uv run pytest
```

Agent-oriented project notes for automated coding tools live in [`AGENTS.md`](AGENTS.md).

## License

MIT — Copyright (c) Emiel Kollof and contributors.
