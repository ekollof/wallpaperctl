# Wallpaperctl for Omarchy

Bundled bar widget for [wallpaperctl](https://github.com/ekollof/wallpaperctl).
Installed and updated by `wallpaperctl setup omarchy` (also `setup all` on
Omarchy). Requires wallpaperctl on PATH and the Omarchy Quattro shell's
`qs.Ui`, `qs.Commons`, Quickshell.Io, and QtQuick.Dialogs modules.

Left or right click the image icon to open wallpaper information and controls:

- Preview, file name, path, image dimensions and file size.
- **Randomize** uses the two preferences below.
- **Choose wallpaper…** opens a local file selection dialog; cancellation
  leaves the wallpaper untouched. Selecting a file applies it directly.
- **Animated** chooses video versus static image for the next random wallpaper.
- **Fetch remotely** chooses configured remote providers versus the local library.

Preferences live inline on this widget's `shell.json` entry (`animated` and
`remote`, both false by default). Manual file selection overrides the type
preference. Remote fetching uses wallpaperctl's existing provider configuration
and local fallback; the plugin never reads API keys. Status refreshes every ten
seconds using local files only. Network requests happen only after Randomize
with Fetch remotely enabled. Video dimensions describe the cached still preview.
Actions run in the singleton service, survive closing the panel, and block
repeated actions across monitors. Errors are shown in the panel.

Escape, outside click, or Close dismisses the panel. Arrow keys and Tab move
between controls; Enter/Space activates the selected control. The icon and
anchored popup support horizontal and vertical bars. Service integration
requires the built-in Omarchy bar; an unavailable service is shown explicitly.

To move, disable, or remove:

```sh
omarchy bar move io.github.ekollof.wallpaperctl --section left
omarchy plugin disable io.github.ekollof.wallpaperctl
omarchy plugin remove io.github.ekollof.wallpaperctl
```

Setup reinstalls/enables this bundled widget when run again. User preferences
and existing placement are preserved. No separate plugin repository or automatic
plugin updater is required. Test using `./tests/run`; Python regression tests
live in the wallpaperctl repository. `demo/fixtures/example.json` is fictional
status data, not live wallpaper information. No screenshot evidence is implied
by the fixture. The widget was adapted from Omarchy's installed Clock/Panel,
KeyboardPanel, WidgetButton, Button, Toggle and scoped PluginShellApi contracts.
