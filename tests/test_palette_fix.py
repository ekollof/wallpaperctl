from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from wallpaperctl.config import OpsConfig
from wallpaperctl.context import WallpaperContext
from wallpaperctl.detect.desktop import DesktopEnvironment
from wallpaperctl.theme.palette_contrast import (
    apply_hex_map,
    fix_installed_palette,
    improve_terminal_contrast,
)
from wallpaperctl.theme.pywalfox import _contrast_ratio, _luma

DARK_BG = "#2b2b33"
LIGHT_BG = "#e8e6e3"


def _palette(bg: str, fg: str, accent: str, dim: str) -> dict:
    return {
        "special": {"background": bg, "foreground": fg, "cursor": fg},
        "colors": {
            **{f"color{i}": accent for i in range(0, 16)},
            "color7": fg,
            "color8": dim,
            "color15": fg,
        },
    }


def test_dark_bg_lifts_text_and_accents() -> None:
    data = _palette(DARK_BG, "#5a5464", "#4a3b55", "#34303c")
    fixed, mapping = improve_terminal_contrast(data)
    bg = DARK_BG
    assert _contrast_ratio(fixed["special"]["foreground"], bg) >= 4.5
    assert _contrast_ratio(fixed["colors"]["color8"], bg) >= 4.0
    for i in (1, 2, 3, 4, 5, 6, 9, 10, 11, 12, 13, 14):
        assert _contrast_ratio(fixed["colors"][f"color{i}"], bg) >= 3.0, i
    # Surfaces untouched, hue roughly kept (accent still purple-ish).
    assert fixed["special"]["background"] == DARK_BG
    assert fixed["colors"]["color0"] == data["colors"]["color0"]
    assert fixed["colors"]["color4"][1] >= data["colors"]["color4"][1]
    # Mapping only contains changed colors, lowercase keys.
    assert set(mapping) <= {h.lower() for h in (
        "#5a5464", "#4a3b55", "#34303c",
    )}
    assert all(v.startswith("#") for v in mapping.values())


def test_light_bg_darkens_text() -> None:
    data = _palette(LIGHT_BG, "#9a94a4", "#8a7b95", "#c5c1cb")
    fixed, _ = improve_terminal_contrast(data)
    assert _contrast_ratio(fixed["special"]["foreground"], LIGHT_BG) >= 4.5
    assert _luma(fixed["special"]["foreground"]) < _luma(LIGHT_BG)
    assert _contrast_ratio(fixed["colors"]["color1"], LIGHT_BG) >= 3.0


def test_already_readable_palette_is_untouched() -> None:
    data = _palette(DARK_BG, "#f2f2f2", "#d75f5f", "#8a8a95")
    for i in (1, 2, 3, 4, 5, 6, 9, 10, 11, 12, 13, 14):
        data["colors"][f"color{i}"] = "#d75f5f"
    _, mapping = improve_terminal_contrast(data)
    assert mapping == {}


def test_apply_hex_map_rewrites_generated_files(tmp_path: Path) -> None:
    target = tmp_path / "colors.sh"
    target.write_text("foreground='#5A5464'\ncolor1=#5a5464\n", encoding="utf-8")
    apply_hex_map({"#5a5464": "#B9B3C3"}, [target])
    text = target.read_text(encoding="utf-8")
    assert "#B9B3C3" in text
    assert "5a5464" not in text.lower().replace("#b9b3c3", "")


def test_fix_installed_palette_updates_cache(tmp_path: Path) -> None:
    wal = tmp_path / "wal"
    wal.mkdir()
    payload = _palette(DARK_BG, "#5a5464", "#4a3b55", "#34303c")
    (wal / "colors.json").write_text(json.dumps(payload), encoding="utf-8")
    (wal / "colors.sh").write_text(
        f"background='{DARK_BG}'\nforeground='#5a5464'\n", encoding="utf-8"
    )
    # never signal real processes from tests (opencode script / kitty reload)
    with (
        patch("wallpaperctl.omarchy.omarchy_available", return_value=True),
        patch("wallpaperctl.theme.palette_contrast.run"),
    ):
        ok = fix_installed_palette(wal_dir=wal)
    assert ok
    fixed = json.loads((wal / "colors.json").read_text(encoding="utf-8"))
    assert _contrast_ratio(fixed["special"]["foreground"], DARK_BG) >= 4.5
    assert "#5a5464" not in (wal / "colors.sh").read_text(encoding="utf-8").lower()


def test_fix_skips_opencode_and_kitty_on_omarchy(tmp_path: Path) -> None:
    wal = tmp_path / "wal"
    wal.mkdir()
    payload = _palette(DARK_BG, "#5a5464", "#4a3b55", "#34303c")
    (wal / "colors.json").write_text(json.dumps(payload), encoding="utf-8")

    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append(list(args))
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    with (
        patch("wallpaperctl.omarchy.omarchy_available", return_value=True),
        patch("wallpaperctl.theme.palette_contrast.run", side_effect=fake_run),
    ):
        ok = fix_installed_palette(wal_dir=wal)

    assert ok
    assert calls == [], f"expected no subprocess on omarchy, got {calls}"


def test_fix_regen_opencode_and_kitty_off_omarchy(tmp_path: Path) -> None:
    wal = tmp_path / "wal"
    wal.mkdir()
    payload = _palette(DARK_BG, "#5a5464", "#4a3b55", "#34303c")
    (wal / "colors.json").write_text(json.dumps(payload), encoding="utf-8")

    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append(list(args))
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    with (
        patch("wallpaperctl.omarchy.omarchy_available", return_value=False),
        patch(
            "wallpaperctl.theme.palette_contrast.OPENCODE_SCRIPT",
            tmp_path / "generate-wallust-theme.py",
        ),
        patch("wallpaperctl.theme.palette_contrast.run", side_effect=fake_run),
        patch("wallpaperctl.theme.palette_contrast.have", return_value=True),
    ):
        (tmp_path / "generate-wallust-theme.py").write_text("pass", encoding="utf-8")
        assert fix_installed_palette(wal_dir=wal)

    flat = [" ".join(map(str, c)) for c in calls]
    assert any("generate-wallust-theme.py" in c for c in flat)
    assert any("SIGUSR1" in c for c in flat)


def _ctx(tmp_path: Path) -> WallpaperContext:
    video = tmp_path / "wall.jpg"
    video.write_bytes(b"img")
    return WallpaperContext(video, DesktopEnvironment(awesome=True), OpsConfig())


def test_wallust_op_applies_contrast_fix(tmp_path: Path) -> None:
    from wallpaperctl.theme.wallust import WallustOp

    ctx = _ctx(tmp_path)
    ctx.ops.wallust_fix_contrast = True
    ok_result = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
    with (
        patch("wallpaperctl.theme.wallust.have", return_value=True),
        patch("wallpaperctl.theme.wallust.run", return_value=ok_result),
        patch(
            "wallpaperctl.theme.wallust.fix_installed_palette",
            return_value=True,
        ) as fix,
    ):
        assert WallustOp().run(ctx)
    fix.assert_called_once()


def test_wallust_op_contrast_fix_can_be_disabled(tmp_path: Path) -> None:
    from wallpaperctl.theme.wallust import WallustOp

    ctx = _ctx(tmp_path)
    ctx.ops.wallust_fix_contrast = False
    ok_result = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
    with (
        patch("wallpaperctl.theme.wallust.have", return_value=True),
        patch("wallpaperctl.theme.wallust.run", return_value=ok_result),
        patch(
            "wallpaperctl.theme.wallust.fix_installed_palette", return_value=True
        ) as fix,
    ):
        assert WallustOp().run(ctx)
    fix.assert_not_called()
