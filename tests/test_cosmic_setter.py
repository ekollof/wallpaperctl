"""COSMIC wallpaper config + greeter state sync."""

from __future__ import annotations

from pathlib import Path

from wallpaperctl.set.cosmic import (
    sync_cosmic_wallpaper,
    write_cosmic_background_config,
    write_cosmic_background_state,
)


def test_write_config_and_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("wallpaperctl.set.cosmic.home", lambda: tmp_path)
    img = tmp_path / "Wallpapers" / "a.jpg"
    img.parent.mkdir(parents=True)
    img.write_bytes(b"fake")

    cfg = write_cosmic_background_config(img)
    assert cfg.is_file()
    text = cfg.read_text(encoding="utf-8")
    assert "a.jpg" in text
    assert "output: \"all\"" in text

    same = tmp_path / ".config/cosmic/com.system76.CosmicBackground/v1/same-on-all"
    assert same.read_text(encoding="utf-8").strip() == "true"

    st = write_cosmic_background_state(img)
    assert st is not None and st.is_file()
    assert "a.jpg" in st.read_text(encoding="utf-8")


def test_state_updates_all_outputs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("wallpaperctl.set.cosmic.home", lambda: tmp_path)
    img = tmp_path / "w.jpg"
    img.write_bytes(b"x")
    state_dir = tmp_path / ".local/state/cosmic/com.system76.CosmicBackground/v1"
    state_dir.mkdir(parents=True)
    (state_dir / "wallpapers").write_text(
        '[\n'
        '    ("DP-1", Path("/old/one.jpg")),\n'
        '    ("eDP-1", Path("/old/two.jpg")),\n'
        "]\n",
        encoding="utf-8",
    )
    write_cosmic_background_state(img)
    out = (state_dir / "wallpapers").read_text(encoding="utf-8")
    assert out.count("w.jpg") == 2
    assert "/old/" not in out


def test_sync_ok(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("wallpaperctl.set.cosmic.home", lambda: tmp_path)
    img = tmp_path / "pic.png"
    img.write_bytes(b"png")
    ok, detail = sync_cosmic_wallpaper(img)
    assert ok
    assert "pic.png" in detail
