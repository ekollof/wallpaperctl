# Vendored GTK themes

| Theme | Notes |
|-------|--------|
| `FlatColor` | Base theme; wallust templates rewrite `gtk-2.0/gtkrc`, `gtk-3.0/gtk.css`, `gtk-3.20/gtk.css` |
| `FlatColor-dark` | Symlink → `FlatColor` (same files; name used for dark preference) |

Install:

```bash
wallpaperctl setup themes
# or: wallpaperctl setup all
```

Installed to `~/.local/share/themes/` so gsettings / XFCE / nwg-look can find them.
