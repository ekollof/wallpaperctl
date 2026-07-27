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

From the public GitHub repository:

### pipx (recommended for CLI tools)

```bash
pipx install git+https://github.com/ekollof/wallpaperctl.git
```

### uv

```bash
uv tool install git+https://github.com/ekollof/wallpaperctl.git
```

### venv / pip (development checkout)

```bash
git clone https://github.com/ekollof/wallpaperctl.git
cd wallpaperctl
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
# or: uv sync --all-extras
```

Entry points: `wallpaperctl` and `wallpaper` (compat alias).

## CLI (shell-compatible)

```text
wallpaperctl [-r] [-R] [-C] [-m] [-c categories] [<path_to_wallpaper>]

  -r  Fetch a random wallpaper (Unsplash / Pexels / Pixabay, ~1920x1080)
  -R  Reload the current wallpaper from ~/.wallpaper
  -C  Clear URL + perceptual-hash caches
  -m  Open wallpaper manager TUI (preview / tag / delete / set)
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
wallpaperctl setup check          # dependency audit for this desktop
wallpaperctl setup install        # offer to install missing packages
wallpaperctl setup wallust        # install shipped wallust.toml + templates + hooks
wallpaperctl setup wallust-templates  # templates/scripts only (keep your toml)
wallpaperctl setup wallust --force    # overwrite existing wallust.toml (backs up first)
wallpaperctl setup themes         # install FlatColor / FlatColor-dark GTK themes
wallpaperctl setup config         # create dirs + sample ops.toml / config.sh
wallpaperctl setup all            # config + themes + check + install + wallust
wallpaperctl migrate              # cutover checklist (PATH, config, tools)
wallpaperctl manage [dir]         # Textual TUI manager (same as -m)
wallpaperctl -m                   # shortcut for manage
```

### Wallpaper manager TUI (`-m` / `manage`)

Interactive library browser built with [Textual](https://textual.textualize.io/):

| Key | Action |
|-----|--------|
| `/` | Focus search (name + tags) |
| `s` / Enter | Set wallpaper + run theme ops |
| `t` | Add tag |
| `u` | Remove tag |
| `d` | Delete file (confirm) |
| `f` | Filter by tag |
| `c` | Clear search/tag filters |
| `r` | Rescan library |
| `q` | Quit |

**Preview backends** (auto-detected, best first):

1. **Kitty graphics protocol** — true inline image via Textual’s post-frame hook  
   (Kitty, Ghostty, WezTerm, …)
2. **Sixel** — same post-frame path via `chafa --format=sixels` or `img2sixel`
3. **Chafa** symbol/ANSI art (rendered with Rich `Text.from_ansi`)
4. **Unicode half-blocks** via Pillow (always available)

Protocol backends leave the preview pane blank in Textual’s cell buffer, then
paint the image *after* each frame so escapes are not mangled as text.

Tags are stored in `~/.config/wallpaperctl/tags.json` (not in the image files).
Optional: install `chafa` for sixel/ANSI quality.


Shipped data under `src/wallpaperctl/data/`:

- **`wallust/`** — `wallust.toml`, templates, hook scripts  
- **`themes/FlatColor`** (+ `FlatColor-dark` → symlink) — wallust-driven GTK theme  
- **`cinnamon/`** — dynamic Cinnamon CSS/GTK templates (theme op)

No secrets; safe to distribute. Themes install to `~/.local/share/themes/`.




Environment:

| Variable | Effect |
|----------|--------|
| `DEBUG=1` | Verbose debug logging |
| `MINIMAL_MODE=1` | Disable optional theme ops |
| `WALLPAPERCTL_CONFIG` | Override ops config path |

## Configuration

### API keys (remote fetch: `wallpaperctl -r`)

**Automatic download is optional.** Local pick (`wallpaperctl` with no flags),
a path, or `wallpaperctl -R` need **no** API keys.

For **`wallpaperctl -r` / `fetch`**, you must register on each stock site and
create your own free API credentials. wallpaperctl does **not** ship keys; it
only reads yours from disk or the environment.

| Provider | Where to register / get a key |
|----------|--------------------------------|
| [Unsplash](https://unsplash.com/developers) | Developers → create an app → **Access Key** |
| [Pexels](https://www.pexels.com/api/) | API → sign up → **API key** |
| [Pixabay](https://pixabay.com/api/docs/) | Account → API → **API key** |

Respect each site’s terms of use, rate limits, and attribution rules (the
tool can overlay photographer credits when metadata is available).

Put keys in **`~/.config/wallpaper/config.sh`** (not in the package; `chmod 600`):

```sh
export UNSPLASH_ACCESS_KEY="your-unsplash-access-key"
export PEXELS_API_KEY="your-pexels-api-key"
export PIXABAY_API_KEY="your-pixabay-api-key"
export CATEGORIES="nature,landscape,architecture"  # optional default for -r
```

Or set the same variables in the environment. Optional pure-Python config:
`~/.config/wallpaperctl/config.toml` (`[api]` keys). Never commit real keys.

### Operations config

`~/.config/wallpaperctl/ops.toml` (optional). Defaults live in
`src/wallpaperctl/defaults.toml`. Environment detection still applies
Plasma/Hyprland/XFCE/Cinnamon overrides at runtime.

### Home Assistant

Optional: `~/.config/hass.cfg` (`[auth]` with `server=`, `token=`, `lamp=`).

## Desktop environments

| Environment | Wallpaper setter |
|-------------|------------------|
| KDE Plasma | Session D-Bus `evaluateScript` via **jeepney** (+ lockscreen `kscreenlockerrc` file edit) |
| Hyprland | `hyprctl hyprpaper` (skipped when Noctalia is active) |
| Noctalia | `qs -c noctalia-shell ipc call wallpaper set … all` |
| XFCE | `xfconf-query` for **connected** outputs (xrandr) + existing keys; creates missing multihead/dock props |
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
- Session D-Bus: **jeepney** (Plasma wallpaper, notifications, portal/kded hooks — no `dbus-send`/`notify-send`)
- DE tools only where the DE has no bus API: `hyprctl`, `qs`, `xfconf-query`, `gsettings`
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

### Same machine (cut over from `~/bin`)

1. Install the package (pipx/uv tool or editable checkout).
2. Keep **`~/.config/wallpaper/config.sh`** as-is (API keys + default categories).
3. Optionally create ops toggles: `wallpaperctl setup config` →  
   `~/.config/wallpaperctl/ops.toml`.
4. Bootstrap DE data if needed:
   ```bash
   wallpaperctl setup check
   wallpaperctl setup wallust      # templates + wallust.toml
   wallpaperctl setup themes       # FlatColor GTK themes
   # or: wallpaperctl setup all
   wallpaperctl migrate            # PATH / config / tools checklist
   ```
5. Smoke-test **without** removing shell tools yet:
   ```bash
   wallpaperctl detect
   wallpaperctl migrate
   wallpaperctl -R                 # reload last wallpaper
   which -a wallpaper wallpaperctl # see PATH order
   ```
6. Point bindings / cron / Hyprland `exec` / keyboard shortcuts at **`wallpaperctl`**
   (or the `wallpaper` entry point this package installs — ensure it wins on `PATH`
   over `~/bin/wallpaper` if both exist).
7. When stable, remove or rename the old scripts (`~/bin/wallpaper`,
   `wallpaper.d`, `wallpaper-cache`, `wallpaper-reload-wm`, …).

**State files are shared** with the shell tool (`~/.wallpaper`, `~/Wallpapers`,
URL/hash caches). You do not need to re-download the library.

### New machine (portable install)

```bash
pipx install git+https://github.com/ekollof/wallpaperctl.git
# or: uv tool install git+https://github.com/ekollof/wallpaperctl.git

wallpaperctl setup all             # dirs, sample configs, themes, deps, wallust
# edit ~/.config/wallpaper/config.sh  # only if you want remote fetch (-r)
wallpaperctl detect
wallpaperctl                       # random local from ~/Wallpapers
```

No need to copy `~/bin` wallpaper scripts. System packages for your DE can be
offered via `wallpaperctl setup install`.

### Behaviour notes vs shell

| Topic | wallpaperctl |
|-------|----------------|
| Local library | Recursive under `~/Wallpapers` (image extensions) |
| Dedup | Multi-hash index (`dHash`+`pHash`+`aHash`) of full library |
| Credits / resize | Pillow only (no ImageMagick) |
| D-Bus (Plasma, notify) | jeepney (no `dbus-send` / `notify-send` required) |
| Cinnamon dynamic theme | Full CSS templates; does **not** force GTK to `cinnamon-dynamic` |
| Cinnamon decorations | Optional full restart: `RESTART_CINNAMON_AFTER_THEME=1` or `reload-wm --restart` |
| Failed wallpaper set | Non-zero exit (theme ops skipped) |
| starttree | Removed (unused) |

### Coexistence

Until cutover, both tools may be on `PATH`. Prefer calling `wallpaperctl`
explicitly, or put the pipx/uv shims **before** `~/bin` in `PATH`.

## Development

```bash
git clone https://github.com/ekollof/wallpaperctl.git
cd wallpaperctl
uv sync --all-extras
uv run wallpaperctl detect
uv run pytest
```

Agent-oriented project notes for automated coding tools live in [`AGENTS.md`](AGENTS.md).

## License

MIT — Copyright (c) Emiel Kollof and contributors.
