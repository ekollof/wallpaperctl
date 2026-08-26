# Vendored wallust pack

Shipped with wallpaperctl for `wallpaperctl setup wallust`.

| Path | Contents |
|------|----------|
| `wallust.toml` | Sample config (templates + hooks) |
| `templates/` | Color templates (kitty, waybar, gtk, hypr, …) |
| `scripts/` | Hook helpers referenced from `[hooks]` |

Install into the user tree:

```bash
wallpaperctl setup wallust              # toml if missing + fill templates, refresh scripts
wallpaperctl setup wallust --force      # replace toml (backs up first) + refresh templates
wallpaperctl setup wallust-templates    # templates/scripts only
wallpaperctl setup wallust-templates --force   # also overwrite modified templates
```

Scripts are package-owned code and are always refreshed on every bootstrap run
(a differing previous version is kept as `*.bak-wallpaperctl`). Templates are
user-editable: missing ones are filled in; changed ones are only overwritten
with `--force`. `wallpaperctl setup check` reports when installed files differ
from the packaged versions.

Hooks expect scripts under `~/.config/wallust/scripts/` after install.

`setup wallust` also installs the OpenCode TUI plugin
`~/.config/opencode/plugins/wallust-hot-reload.ts` and registers it in
`tui.json`. That watches `themes/wallust.json` so a running OpenCode session
picks up palette changes without SIGUSR2 (which interrupts agents). Restart
OpenCode once after the first install.
