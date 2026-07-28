"""COSMIC wallpaper config + greeter state sync."""

from __future__ import annotations

from pathlib import Path

from wallpaperctl.set.cosmic import (
    discover_cosmic_outputs,
    sync_cosmic_wallpaper,
    write_cosmic_background_config,
    write_cosmic_background_state,
)


def test_write_config_and_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("wallpaperctl.set.cosmic.home", lambda: tmp_path)
    monkeypatch.setattr(
        "wallpaperctl.set.cosmic.discover_cosmic_outputs", lambda: []
    )
    img = tmp_path / "Wallpapers" / "a.jpg"
    img.parent.mkdir(parents=True)
    img.write_bytes(b"fake")

    cfg = write_cosmic_background_config(img)
    assert cfg.is_file()
    text = cfg.read_text(encoding="utf-8")
    assert "a.jpg" in text
    assert 'output: "all"' in text

    same = tmp_path / ".config/cosmic/com.system76.CosmicBackground/v1/same-on-all"
    assert same.read_text(encoding="utf-8").strip() == "true"

    st = write_cosmic_background_state(img)
    assert st is not None and st.is_file()
    body = st.read_text(encoding="utf-8")
    assert "a.jpg" in body
    assert '("all", Path(' in body


def test_state_rewrites_all_known_outputs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("wallpaperctl.set.cosmic.home", lambda: tmp_path)
    img = tmp_path / "w.jpg"
    img.write_bytes(b"x")
    state_dir = tmp_path / ".local/state/cosmic/com.system76.CosmicBackground/v1"
    state_dir.mkdir(parents=True)
    (state_dir / "wallpapers").write_text(
        "[\n"
        '    ("DP-1", Path("/old/one.jpg")),\n'
        '    ("eDP-1", Path("/old/two.jpg")),\n'
        "]\n",
        encoding="utf-8",
    )
    # Also expose a live output not yet in state
    monkeypatch.setattr(
        "wallpaperctl.set.cosmic.discover_cosmic_outputs",
        lambda: ["DP-1", "DP-7", "eDP-1"],
    )
    write_cosmic_background_state(img)
    out = (state_dir / "wallpapers").read_text(encoding="utf-8")
    assert out.count("w.jpg") == 3
    assert "/old/" not in out
    assert "DP-7" in out
    assert "eDP-1" in out


def test_discover_outputs_from_ron_and_state(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("wallpaperctl.set.cosmic.home", lambda: tmp_path)
    monkeypatch.setattr("wallpaperctl.set.cosmic.have", lambda _c: False)
    ron = tmp_path / ".local/state/cosmic-comp/outputs.ron"
    ron.parent.mkdir(parents=True)
    ron.write_text(
        'connector: "DP-10",\nconnector: "eDP-1",\n',
        encoding="utf-8",
    )
    state_dir = tmp_path / ".local/state/cosmic/com.system76.CosmicBackground/v1"
    state_dir.mkdir(parents=True)
    (state_dir / "wallpapers").write_text(
        '[("DP-8", Path("/x.jpg")),]\n',
        encoding="utf-8",
    )
    names = discover_cosmic_outputs()
    assert names == ["DP-10", "DP-8", "eDP-1"]


def test_sync_ok(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("wallpaperctl.set.cosmic.home", lambda: tmp_path)
    monkeypatch.setattr(
        "wallpaperctl.set.cosmic.discover_cosmic_outputs", lambda: ["eDP-1"]
    )
    monkeypatch.setattr(
        "wallpaperctl.set.cosmic.reload_cosmic_greeter", lambda **_k: None
    )
    img = tmp_path / "pic.png"
    img.write_bytes(b"png")
    ok, detail = sync_cosmic_wallpaper(img, reload_greeter=False)
    assert ok
    assert "pic.png" in detail


def test_write_watched_is_in_place(tmp_path: Path) -> None:
    from wallpaperctl.set.cosmic import _write_watched

    p = tmp_path / "wallpapers"
    _write_watched(p, "first\n")
    ino1 = p.stat().st_ino
    _write_watched(p, "second\n")
    ino2 = p.stat().st_ino
    assert ino1 == ino2
    assert p.read_text() == "second\n"
