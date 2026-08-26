"""Contrast guarantees for the wallust-generated opencode theme."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "wallpaperctl"
    / "data"
    / "wallust"
    / "scripts"
    / "generate-wallust-theme.py"
)


@pytest.fixture
def mod() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_wallust_theme", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_contrast_ratio_extremes(mod: ModuleType) -> None:
    assert mod.contrast_ratio("#000000", "#ffffff") == pytest.approx(21, abs=0.1)
    assert mod.contrast_ratio("#1b2226", "#1b2226") == pytest.approx(1, abs=0.01)


def test_ensure_contrast_fixes_invisible_muted_color(mod: ModuleType) -> None:
    # Regression: wallust color8 (#20272B) on the panel (#1b2226) is ~1.07:1.
    muted = mod.ensure_contrast("#20272B", "#1b2226", 4.5, "lighten")
    assert mod.contrast_ratio(muted, "#1b2226") >= 4.5


def test_ensure_contrast_keeps_already_legible_color(mod: ModuleType) -> None:
    assert mod.ensure_contrast("#20272B", "#cfcfcf", 4.5, "darken") == "#20272B"


def test_generated_theme_muted_text_is_legible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mod: ModuleType
) -> None:
    # Simulate the reported failure: color8 nearly identical to the background.
    colors = {
        "special": {
            "background": "#080F14",
            "foreground": "#C7D2B1",
            "cursor": "#C7D2B1",
        },
        "colors": {
            **{f"color{i}": "#45885D" for i in range(16)},
            "color8": "#20272B",
        },
    }
    wal = tmp_path / "colors.json"
    wal.write_text(json.dumps(colors))
    output = tmp_path / "themes" / "wallust.json"
    monkeypatch.setattr(mod, "WAL_COLORS_PATH", wal)
    monkeypatch.setattr(mod, "THEME_OUTPUT_PATH", output)

    mod.generate_theme()

    theme = json.loads(output.read_text())
    defs = theme["defs"]
    assert mod.contrast_ratio(defs["wal_text_muted_dark"], defs["wal_panel_dark"]) >= 4.5
    assert mod.contrast_ratio(defs["wal_comment_dark"], defs["wal_bg"]) >= 4.5
    assert mod.contrast_ratio(defs["wal_text_muted_light"], defs["wal_panel_light"]) >= 4.5
    assert theme["theme"]["textMuted"]["dark"] == "wal_text_muted_dark"
    assert theme["theme"]["syntaxComment"]["dark"] == "wal_comment_dark"
    assert theme["theme"]["diffContext"]["dark"] == "wal_comment_dark"


def test_write_json_is_atomic(tmp_path: Path, mod: ModuleType) -> None:
    dest = tmp_path / "out.json"
    mod._write_json(dest, {"ok": True})
    assert json.loads(dest.read_text()) == {"ok": True}
    assert not (tmp_path / ".out.json.tmp").exists()


def test_set_tui_theme_registers_plugin_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mod: ModuleType
) -> None:
    tui_path = tmp_path / "tui.json"
    plugin = tmp_path / "plugins" / "wallust-hot-reload.ts"
    plugin.parent.mkdir()
    plugin.write_text("// plugin\n")
    tui_path.write_text(json.dumps({"scroll_speed": 2, "plugin": ["keep.me"]}))
    monkeypatch.setattr(mod, "TUI_PATH", tui_path)
    monkeypatch.setattr(mod, "OPENCODE_PLUGIN_PATH", plugin)

    mod.set_tui_theme()

    tui = json.loads(tui_path.read_text())
    assert tui["theme"] == "wallust"
    assert tui["scroll_speed"] == 2
    assert tui["plugin"] == ["keep.me", mod.OPENCODE_PLUGIN_SPEC]


def test_set_tui_theme_skips_plugin_when_file_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mod: ModuleType
) -> None:
    tui_path = tmp_path / "tui.json"
    monkeypatch.setattr(mod, "TUI_PATH", tui_path)
    monkeypatch.setattr(mod, "OPENCODE_PLUGIN_PATH", tmp_path / "missing.ts")

    mod.set_tui_theme()

    tui = json.loads(tui_path.read_text())
    assert tui["theme"] == "wallust"
    assert "plugin" not in tui
