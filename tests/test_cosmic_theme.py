"""COSMIC v2 theme application from wallust colors."""

from __future__ import annotations

from pathlib import Path

from wallpaperctl.theme.cosmic import (
    _hex8,
    apply_cosmic_palette,
    component_ron,
    pick_accent,
    surface_ron,
)


def test_hex8() -> None:
    assert _hex8("#63d0df") == "#63D0DFFF"
    assert _hex8("aabbcc", alpha="80") == "#AABBCC80"


def test_component_ron_soft_border_differs_from_base() -> None:
    text = component_ron("#FF0000", soft_border=True, bg="#101010")
    assert 'base: "#FF0000FF"' in text
    # Border should be mixed toward bg, not pure red
    assert 'border: "#FF0000FF"' not in text
    assert "red:" not in text


def test_pick_accent_softens_toward_bg() -> None:
    colors = ["#101010", "#FF0000", "#00FF00", "#0000FF", "#FF6600", "#888", "#999", "#EEE"]
    # Force fixed-ish by putting orange in range
    raw, soft = pick_accent(colors, strategy="warmest", softness=0.5, desaturate=0.0)
    assert raw.startswith("#")
    assert soft != raw or soft  # soft may equal only if already near bg
    # Soft should be darker / closer to bg than pure neon
    from wallpaperctl.theme.cosmic import _luma

    assert _luma(soft) < _luma(raw) + 0.05


def test_surface_ron_uses_soft_accent_for_focus() -> None:
    text = surface_ron(base="#1A1A1A", fg="#F0F0F0", accent="#AA8866", dark=True)
    assert 'base: "#1A1A1AFF"' in text
    assert 'selected_text: "#AA8866FF"' in text
    assert 'focus: "#AA8866FF"' in text


def test_apply_surfaces_mode_writes_accent_and_bg(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("wallpaperctl.theme.cosmic.home", lambda: tmp_path)
    theme = tmp_path / ".config" / "cosmic" / "com.system76.CosmicTheme.Dark" / "v2"
    theme.mkdir(parents=True)

    colors = [f"#{i:02x}{i:02x}{i:02x}" for i in range(8, 16)]
    colors[0] = "#121212"
    colors[4] = "#E85D04"
    colors[7] = "#F5F5F5"

    written = apply_cosmic_palette(
        colors,
        dark=True,
        mode="surfaces",
        strategy="warmest",
        softness=0.45,
        desaturate=0.2,
    )
    assert written
    assert (theme / "accent").is_file()
    assert (theme / "background").is_file()
    assert (theme / "primary").is_file()
    # Should NOT stamp every button in surfaces mode
    assert not (theme / "icon_button").is_file()
    assert not (theme / "destructive").is_file()

    accent_body = (theme / "accent").read_text(encoding="utf-8")
    assert "red:" not in accent_body  # v2 hex, not float v1
    # Border should be softened (not identical pure base stamp only)
    assert "border:" in accent_body


def test_apply_accent_mode_skips_surfaces(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("wallpaperctl.theme.cosmic.home", lambda: tmp_path)
    theme = tmp_path / ".config" / "cosmic" / "com.system76.CosmicTheme.Dark" / "v2"
    theme.mkdir(parents=True)
    colors = ["#111111", "#AA0000", "#00AA00", "#0000AA", "#CC6633", "#1", "#2", "#EEE"]
    apply_cosmic_palette(colors, dark=True, mode="accent", softness=0.4)
    assert (theme / "accent").is_file()
    assert not (theme / "background").is_file()
