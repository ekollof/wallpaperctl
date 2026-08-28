"""Install the OpenCode wallust theme hot-reload plugin."""

from __future__ import annotations

import json
import shutil
from importlib import resources
from pathlib import Path

from wallpaperctl.util import home


def _files_differ(a: Path, b: Path) -> bool:
    try:
        if a.stat().st_size != b.stat().st_size:
            return True
        with a.open("rb") as fa, b.open("rb") as fb:
            return fa.read() != fb.read()
    except OSError:
        return True

PLUGIN_SPEC = "./plugins/wallust-hot-reload.ts"
PLUGIN_NAME = "wallust-hot-reload.ts"


def opencode_config_dir() -> Path:
    return home() / ".config" / "opencode"


def _packaged_plugin() -> Path | None:
    here = Path(__file__).resolve().parent.parent / "data" / "opencode" / "plugins" / PLUGIN_NAME
    if here.is_file():
        return here
    try:
        root = (
            resources.files("wallpaperctl")
            .joinpath("data")
            .joinpath("opencode")
            .joinpath("plugins")
            .joinpath(PLUGIN_NAME)
        )
        with resources.as_file(root) as p:
            if Path(p).is_file():
                return Path(p)
    except Exception:
        pass
    return None


def _plugin_listed(tui: dict) -> bool:
    plugins = tui.get("plugin")
    if not isinstance(plugins, list):
        return False
    for entry in plugins:
        if entry == PLUGIN_SPEC:
            return True
        if isinstance(entry, list) and entry and entry[0] == PLUGIN_SPEC:
            return True
    return False


def _ensure_plugin_spec(tui: dict) -> bool:
    plugins = tui.get("plugin")
    if not isinstance(plugins, list):
        tui["plugin"] = [PLUGIN_SPEC]
        return True
    if _plugin_listed(tui):
        return False
    plugins.append(PLUGIN_SPEC)
    return True


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    tmp.replace(path)


def opencode_status() -> dict:
    cfg = opencode_config_dir()
    plugin = cfg / "plugins" / PLUGIN_NAME
    tui = cfg / "tui.json"
    listed = False
    if tui.is_file():
        try:
            data = json.loads(tui.read_text(encoding="utf-8"))
            listed = isinstance(data, dict) and _plugin_listed(data)
        except (json.JSONDecodeError, OSError):
            listed = False
    pkg = _packaged_plugin()
    stale = bool(pkg and plugin.is_file() and _files_differ(pkg, plugin))
    return {
        "config_dir": str(cfg),
        "plugin_path": str(plugin),
        "plugin_installed": plugin.is_file(),
        "plugin_stale": stale,
        "tui_path": str(tui),
        "tui_exists": tui.is_file(),
        "plugin_listed": listed,
    }


def bootstrap_opencode(*, force: bool = False) -> int:  # noqa: ARG001
    """Copy the TUI plugin and register it in ~/.config/opencode/tui.json.

    OpenCode reloads custom themes on SIGUSR2, which interrupts agents.
    The plugin watches themes/wallust.json instead.
    """
    pkg = _packaged_plugin()
    if pkg is None:
        print("Packaged OpenCode plugin not found in wallpaperctl install.")
        return 1

    cfg = opencode_config_dir()
    dest = cfg / "plugins" / PLUGIN_NAME
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.is_file() and not _files_differ(pkg, dest):
        print(f"opencode plugin: up to date → {dest}")
    else:
        if dest.is_file():
            bak = Path(str(dest) + ".bak-wallpaperctl")
            shutil.copy2(dest, bak)
            print(f"backup:  {bak}")
        shutil.copy2(pkg, dest)
        print(f"wrote:   {dest}")

    tui_path = cfg / "tui.json"
    tui: dict = {}
    if tui_path.is_file():
        try:
            loaded = json.loads(tui_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                tui = loaded
        except (json.JSONDecodeError, OSError):
            tui = {}

    tui["$schema"] = "https://opencode.ai/tui.json"
    tui["theme"] = "wallust"
    added = _ensure_plugin_spec(tui)
    _write_json(tui_path, tui)
    if added:
        print(f"wrote:   {tui_path}  (theme=wallust, plugin={PLUGIN_SPEC})")
    else:
        print(f"opencode tui: {tui_path}  (theme=wallust, plugin listed)")

    print("  Restart OpenCode once so the wallust theme reloader loads.")
    return 0


def remove_opencode_plugin() -> bool:
    """Remove the wallpaperctl opencode plugin + tui.json registration.

    Used by the Omarchy setup: omarchy owns opencode theming there
    (theme "omarchy" + its own TUI plugin), and the wallust hot-reload
    plugin would fight it over the ``theme`` key.
    """
    cfg = opencode_config_dir()
    plugin = cfg / "plugins" / PLUGIN_NAME
    removed = False

    if plugin.is_file():
        try:
            plugin.unlink()
            print(f"removed: {plugin}")
            removed = True
        except OSError as e:
            print(f"Warning: could not remove {plugin}: {e}")

    tui_path = cfg / "tui.json"
    if tui_path.is_file():
        try:
            tui = json.loads(tui_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            tui = None
        if isinstance(tui, dict) and (_plugin_listed(tui) or tui.get("theme") == "wallust"):
            if isinstance(tui.get("plugin"), list):
                tui["plugin"] = [
                    p
                    for p in tui["plugin"]
                    if p != PLUGIN_SPEC
                    and not (isinstance(p, list) and p and p[0] == PLUGIN_SPEC)
                ]
            if tui.get("theme") == "wallust":
                # our own marker; omarchy owns theming in this context
                tui["theme"] = "omarchy"
            _write_json(tui_path, tui)
            print(f"updated: {tui_path}  (wallust plugin entry removed)")
            removed = True
    return removed
