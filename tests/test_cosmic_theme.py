"""COSMIC v2 theme application from wallust colors."""

from __future__ import annotations

from pathlib import Path

from wallpaperctl.theme.cosmic import _hex8, apply_cosmic_palette, component_ron


def test_hex8() -> None:
    assert _hex8("#63d0df") == "#63D0DFFF"
    assert _hex8("aabbcc", alpha="80") == "#AABBCC80"


def test_component_ron_is_v2_hex() -> None:
    text = component_ron("#63D0DF")
    assert 'base: "#63D0DFFF"' in text
    assert "red:" not in text  # not v1 float format


def test_apply_writes_v2_accent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("wallpaperctl.theme.cosmic.home", lambda: tmp_path)

    theme = tmp_path / ".config" / "cosmic" / "com.system76.CosmicTheme.Dark" / "v2"
    theme.mkdir(parents=True)
    (theme / "background").write_text(
        '(\n    selected_text: "#111111FF",\n    focus: "#222222FF",\n)\n',
        encoding="utf-8",
    )

    colors = [f"#{i:02x}{i:02x}{i:02x}" for i in range(8, 16)]
    colors[4] = "#63D0DF"

    written = apply_cosmic_palette(colors, dark=True)
    assert written
    accent = theme / "accent"
    assert accent.is_file()
    body = accent.read_text(encoding="utf-8")
    assert "#63D0DFFF" in body
    assert "red:" not in body

    bg = (theme / "background").read_text(encoding="utf-8")
    assert 'selected_text: "#63D0DFFF"' in bg
    assert 'focus: "#63D0DFFF"' in bg
