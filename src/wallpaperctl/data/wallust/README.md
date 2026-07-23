# Vendored wallust pack

Shipped with wallpaperctl for `wallpaperctl setup wallust`.

| Path | Contents |
|------|----------|
| `wallust.toml` | Sample config (templates + hooks) |
| `templates/` | Color templates (kitty, waybar, gtk, hypr, …) |
| `scripts/` | Hook helpers referenced from `[hooks]` |

Install into the user tree:

```bash
wallpaperctl setup wallust              # toml if missing + fill templates/scripts
wallpaperctl setup wallust --force      # replace toml (backs up first)
wallpaperctl setup wallust-templates    # templates/scripts only
```

Hooks expect scripts under `~/.config/wallust/scripts/` after install.
