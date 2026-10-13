"""Terminal background opacity: wallpaper shows through; text stays opaque."""

from __future__ import annotations

from pathlib import Path

from wallpaperctl.theme.terminal_opacity import (
    BEGIN,
    END,
    apply_terminal_background_opacity,
    clamp_opacity,
)


def test_clamp_opacity():
    assert clamp_opacity(0.75) == 0.75
    assert clamp_opacity(0.0) == 0.20
    assert clamp_opacity(2) == 1.0
    assert clamp_opacity("nope") == 0.85  # type: ignore[arg-type]


def test_kitty_upsert_and_idempotent(tmp_path: Path):
    path = tmp_path / "kitty.conf"
    path.write_text("background #111111\nforeground #eeeeee\n", encoding="utf-8")
    changed = apply_terminal_background_opacity(0.75, files=[path])
    assert changed == [path]
    text = path.read_text(encoding="utf-8")
    assert "background_opacity 0.75" in text
    assert text.count(BEGIN) == 1
    assert apply_terminal_background_opacity(0.75, files=[path]) == []
    apply_terminal_background_opacity(0.6, files=[path])
    text = path.read_text(encoding="utf-8")
    assert "background_opacity 0.60" in text
    assert "background_opacity 0.75" not in text
    assert text.count(BEGIN) == 1


def test_ghostty_block(tmp_path: Path):
    ghostty = tmp_path / "ghostty.conf"
    ghostty.write_text("background = #111111\n", encoding="utf-8")
    apply_terminal_background_opacity(0.8, files=[ghostty])
    assert "background-opacity = 0.80" in ghostty.read_text(encoding="utf-8")


def test_foot_alpha_in_existing_section(tmp_path: Path):
    foot = tmp_path / "foot.ini"
    foot.write_text(
        "[colors-dark]\nbackground=111111\nforeground=eeeeee\n",
        encoding="utf-8",
    )
    apply_terminal_background_opacity(0.8, files=[foot])
    text = foot.read_text(encoding="utf-8")
    assert text.count("[colors-dark]") == 1
    assert "alpha=0.80" in text
    assert "background=111111" in text
    # old trailing duplicate-section block is not used
    assert BEGIN not in text
    apply_terminal_background_opacity(0.65, files=[foot])
    text = foot.read_text(encoding="utf-8")
    assert text.count("alpha=") == 1
    assert "alpha=0.65" in text


def test_foot_strips_legacy_duplicate_section(tmp_path: Path):
    foot = tmp_path / "foot.ini"
    foot.write_text(
        "[colors-dark]\nbackground=111111\n\n"
        f"{BEGIN}\n[colors-dark]\nalpha=0.75\n[colors]\nalpha=0.75\n{END}\n",
        encoding="utf-8",
    )
    apply_terminal_background_opacity(0.75, files=[foot])
    text = foot.read_text(encoding="utf-8")
    assert text.count("[colors-dark]") == 1
    assert "[colors]\n" not in text
    assert "alpha=0.75" in text
    assert "background=111111" in text


def test_alacritty_theme_and_user_window(tmp_path: Path):
    theme = tmp_path / "alacritty.toml"
    theme.write_text("[colors.primary]\nbackground = '#000000'\n", encoding="utf-8")
    other = tmp_path / "cfg"
    other.mkdir()
    user_cfg = other / "alacritty.toml"
    user_cfg.write_text(
        'general.import = ["theme.toml"]\n\n[window]\npadding.x = 14\n',
        encoding="utf-8",
    )
    apply_terminal_background_opacity(0.75, files=[theme, user_cfg])
    theme_text = theme.read_text(encoding="utf-8")
    assert "opacity = 0.75" in theme_text
    assert "transparent_background_colors = false" in theme_text
    user_text = user_cfg.read_text(encoding="utf-8")
    assert "opacity = 0.75" in user_text
    assert "padding.x = 14" in user_text


def test_opacity_one_strips_block(tmp_path: Path):
    path = tmp_path / "kitty.conf"
    path.write_text("background #111\n", encoding="utf-8")
    apply_terminal_background_opacity(0.7, files=[path])
    apply_terminal_background_opacity(1.0, files=[path])
    text = path.read_text(encoding="utf-8")
    assert BEGIN not in text
    assert "background_opacity" not in text
    assert "background #111" in text


def test_missing_file_is_noop(tmp_path: Path):
    assert apply_terminal_background_opacity(0.5, files=[tmp_path / "nope.conf"]) == []


def test_unset_removes_owned_settings_preserves_native_opacity(tmp_path: Path):
    for name, native in (
        ("kitty.conf", "background_opacity 0.65\n"),
        ("ghostty.conf", "background-opacity = 0.65\n"),
        ("foot.ini", "[colors-dark]\nalpha=0.65\n"),
        ("alacritty.toml", "[window]\nopacity = 0.65\n"),
    ):
        path = tmp_path / name
        original = "# omarchy-glass begin\n" + native + "# omarchy-glass end\n"
        path.write_text(
            original + f"{BEGIN}\nbackground_opacity 0.85\n{END}\n"
            + "alpha=0.85  # wallpaperctl-background-opacity\n"
            + "opacity = 0.85  # wallpaperctl-background-opacity\n"
            + "transparent_background_colors = false  # wallpaperctl-background-opacity\n"
        )
        assert apply_terminal_background_opacity(None, files=[path]) == [path]
        assert path.read_text() == original
        assert apply_terminal_background_opacity(None, files=[path]) == []


def test_default_opacity_is_unmanaged():
    from wallpaperctl.config import OpsConfig

    assert OpsConfig().terminal_background_opacity is None
