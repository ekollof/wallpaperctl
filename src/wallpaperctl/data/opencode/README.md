# OpenCode wallust theme reloader

Installed by `wallpaperctl setup wallust` (and `setup all`).

| Path | Role |
|------|------|
| `plugins/wallust-hot-reload.ts` | OpenCode TUI plugin that watches `themes/wallust.json` |

OpenCode only refreshes custom themes on SIGUSR2, which interrupts agents.
This plugin polls `themes/wallust.json` and applies a new in-memory theme
(`wallust-hot-<timestamp>`) so a running TUI updates without signals.

Destination: `~/.config/opencode/plugins/wallust-hot-reload.ts`, listed in
`~/.config/opencode/tui.json`. Restart OpenCode once after the first install.
