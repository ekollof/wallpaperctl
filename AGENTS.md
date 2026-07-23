# Agent Instructions

All coding agents working in this repository **must** read and follow this file
before making changes.

**After any context compaction** (conversation summary, truncated history, or
handoff): **re-read this entire `AGENTS.md` before writing code.** Compaction
drops detail — these rules are authoritative, not the summary.

---

## Project Overview

**wallpaperctl** is a Python CLI that replaces a modular POSIX-shell wallpaper
system (`~/bin/wallpaper` + `wallpaper.d`). It:

1. Picks or fetches wallpapers (local library / Unsplash / Pexels / Pixabay)
2. Sets the desktop background for the active DE/compositor
3. Runs ordered theme operations (wallust palette, GTK, notifications, OpenRGB, …)

**Platforms:** Linux, OpenBSD, FreeBSD.  
**Layout:** `src/wallpaperctl/` (src layout), tests under `tests/`, packaging via
`pyproject.toml` (hatchling). Entry points: `wallpaperctl`, `wallpaper`.

This project is **AI-assisted** (see README). Human author: Emiel Kollof.

---

## Hard Rules

1. **No dependency on the old shell scripts.** Never call or shell out to
   `~/bin/wallpaper`, `~/bin/wallpaper.d/*`, `wallpaper-cache`,
   `wallpaper-reload-wm`, etc. Reimplement behaviour in-package.
2. **Never embed API keys** or tokens. Secrets live only in the user's
   `~/.config/wallpaper/config.sh` (or env / optional local config). Do not
   commit credentials or copy them into the tree.
3. **Do not require ImageMagick** for image work. Use **Pillow** (and
   imagehash for perceptual hashes).
4. **Notifications** use session D-Bus via **jeepney** — not `notify-send` /
   `dbus-send` for Notify.
5. Prefer **soft failures**: missing optional tools skip ops with a warning;
   only hard-fail when the primary wallpaper path cannot proceed.
6. Keep **CLI parity** with the shell flags (`-r`, `-R`, `-C`, `-c`, path) plus
   subcommands. Do not break the classic flag path without a strong reason.
7. **BSD-friendly**: avoid GNU-only assumptions; use portable process checks
   and pure Python where possible.

---

## Package Map

```
src/wallpaperctl/
  cli.py, app.py, config.py, context.py, lock.py, notify.py, util.py
  detect/       # DE + tool detection
  sources/      # fetch, local pick, dedup, optimize/credits, undup, cache_mgr
  set/          # wallpaper setters (plasma, hyprland, noctalia, xfce, cinnamon, fallback)
  theme/        # ordered theme ops (wallust, gtk, openrgb, …)
  maint/        # reload-wm, cleanup, verify
  assets/       # notification icons
  defaults.toml
tests/
```

- **Setters** run before **theme ops** (`set/runner.py` then `theme/runner.py`).
- Dedup: multi-hash (dHash + pHash + aHash) against full `~/Wallpapers` index
  (`sources/dedup.py`). Undup CLI lives in `sources/undup.py`.
- Config: `load_api_config` / `load_ops_config` in `config.py`; defaults in
  `defaults.toml`, user overrides in `~/.config/wallpaperctl/ops.toml`.

---

## User State (outside the repo)

| Path | Role |
|------|------|
| `~/.config/wallpaper/config.sh` | API keys + default categories |
| `~/.config/wallpaperctl/ops.toml` | Optional ops toggles |
| `~/Wallpapers/` | Library + downloads |
| `~/.wallpaper` | Last wallpaper path |
| `~/.wallpaper_urls` | URL/ID dedup log |
| `~/.wallpaper_hashes` | Multi-hash fingerprint index |
| `~/.cache/wal/` | wallust/pywal colors |

Do not write secrets into the package; do not delete the user's library unless
the user explicitly runs a delete/undup path.

---

## Development Commands

```bash
cd ~/devel/wallpaperctl
# install / refresh
uv pip install -e ".[dev]"   # or: pip install -e ".[dev]"

uv run pytest                # or: .venv/bin/pytest -q
uv run wallpaperctl detect
uv run ruff check src tests  # if ruff installed via [dev]
```

After behavioural changes: run **pytest**. For integration smoke tests on a
desktop session: `wallpaperctl detect`, `wallpaperctl -R` (reload), prefer
non-destructive commands unless the user asks to fetch/change wallpaper.

---

## Coding Conventions

- Python **3.10+**, type hints preferred, `from __future__ import annotations`.
- Logging via `logging.getLogger("wallpaperctl")`; `DEBUG=1` enables debug.
- Subprocess helpers: `wallpaperctl.util.run` / `have` / `pgrep_*` — avoid ad-hoc
  shell pipelines for core paths.
- Theme ops and setters: implement as small classes with `enabled`/`run` or
  `applies`/`set_wallpaper`, registered in the respective runners.
- Keep new deps minimal; justify anything beyond httpx, Pillow, imagehash, jeepney.

---

## What Not To Do

- Do not reintroduce ImageMagick, `curl` (for fetch), or `notify-send` as
  required tools.
- Do not add a legacy shell-ops bridge back to `~/bin/wallpaper.d`.
- Do not expand scope into unrelated desktop config (portals, kwallet, etc.)
  unless the user asks.
- Do not force-push or amend published history without explicit user request.

---

## Related Legacy (reference only)

Historical behaviour may be understood by reading (not calling):

- `~/bin/wallpaper`, `~/bin/wallpaper.d/`
- `~/devel/wall-undup`

When porting behaviour, match intent; improve fragility (locks, pure Python,
multi-hash dedup) rather than copying shell bugs.
