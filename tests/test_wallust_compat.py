"""Tests for wallust major-version palette compatibility."""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

import wallpaperctl.wallust_compat as compat
from wallpaperctl.wallust_compat import (
    canonical_config_text,
    normalize_wallust_config_palette,
    resolve_wallust_palette,
    wallust_major_version,
)


def _fake_run(version_output: str, returncode: int = 0):
    def _run(*args, **kwargs):
        return SimpleNamespace(returncode=returncode, stdout=version_output, stderr="")

    return _run


def test_major_version_parses_v4_alpha(monkeypatch):
    monkeypatch.setattr(
        compat, "run", _fake_run("wallust 4.1.0-alpha (a09480b 2026-09-28)\n")
    )
    assert wallust_major_version() == 4


def test_major_version_parses_v3(monkeypatch):
    monkeypatch.setattr(compat, "run", _fake_run("wallust 3.3.0\n"))
    assert wallust_major_version() == 3


def test_major_version_none_when_missing(monkeypatch):
    monkeypatch.setattr(compat, "run", _fake_run("", returncode=1))
    assert wallust_major_version() is None


def test_major_version_none_when_unparseable(monkeypatch):
    monkeypatch.setattr(compat, "run", _fake_run("something unexpected\n"))
    assert wallust_major_version() is None


def test_resolve_auto_v4(monkeypatch):
    monkeypatch.setattr(compat, "wallust_major_version", lambda: 4)
    assert resolve_wallust_palette("auto") == "kmeans"


def test_resolve_auto_v3(monkeypatch):
    monkeypatch.setattr(compat, "wallust_major_version", lambda: 3)
    assert resolve_wallust_palette("auto") == "dark16"


def test_resolve_stale_v3_default_on_v4(monkeypatch):
    # a640e91-era default must keep working after upgrading wallust.
    monkeypatch.setattr(compat, "wallust_major_version", lambda: 4)
    assert resolve_wallust_palette("dark16") == "kmeans"


def test_resolve_stale_v4_default_on_v3(monkeypatch):
    monkeypatch.setattr(compat, "wallust_major_version", lambda: 3)
    assert resolve_wallust_palette("kmeans") == "dark16"


def test_resolve_explicit_valid_passes_through(monkeypatch):
    monkeypatch.setattr(compat, "wallust_major_version", lambda: 4)
    assert resolve_wallust_palette("ansi") == "ansi"


def test_resolve_unknown_version_passes_through(monkeypatch):
    monkeypatch.setattr(compat, "wallust_major_version", lambda: None)
    assert resolve_wallust_palette("dark16") == "dark16"


def test_normalize_rewrites_stale_default_on_v4(monkeypatch):
    monkeypatch.setattr(compat, "wallust_major_version", lambda: 4)
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "wallust.toml"
        p.write_text('backend = "wal"\npalette = "dark16"\n', encoding="utf-8")
        assert normalize_wallust_config_palette(p) is True
        assert 'palette = "kmeans"' in p.read_text(encoding="utf-8")


def test_normalize_leaves_custom_palette_alone(monkeypatch):
    monkeypatch.setattr(compat, "wallust_major_version", lambda: 4)
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "wallust.toml"
        p.write_text('palette = "mycustom"\n', encoding="utf-8")
        assert normalize_wallust_config_palette(p) is False
        assert 'palette = "mycustom"' in p.read_text(encoding="utf-8")


def test_normalize_noop_when_already_valid(monkeypatch):
    monkeypatch.setattr(compat, "wallust_major_version", lambda: 4)
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "wallust.toml"
        p.write_text('palette = "kmeans"\n', encoding="utf-8")
        assert normalize_wallust_config_palette(p) is False


def test_canonical_config_treats_cross_major_defaults_equal():
    a = 'backend = "wal"\npalette = "dark16"\n'
    b = 'backend = "wal"\npalette = "kmeans"\n'
    assert canonical_config_text(a) == canonical_config_text(b)
