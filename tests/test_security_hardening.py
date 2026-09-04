"""Tests for security hardening: log redaction, lock guards, undup containment."""

from __future__ import annotations

import os
import stat
import sys

import pytest

from wallpaperctl.lock import WallpaperLock
from wallpaperctl.sources.undup import _contained
from wallpaperctl.util import log_error, redact_url_secrets


def test_redact_url_secrets_pixabay_key():
    url = 'Pixabay fetch failed: https://pixabay.com/api/?key=SECRET123&q=nature&w=1920'
    out = redact_url_secrets(url)
    assert "SECRET123" not in out
    assert "key=REDACTED" in out
    assert "q=nature" in out


def test_redact_url_secrets_other_params():
    assert redact_url_secrets("https://x/?access_key=abc&token=def") == (
        "https://x/?access_key=REDACTED&token=REDACTED"
    )
    # No secrets: untouched
    plain = "https://x/?q=foo&bar=1"
    assert redact_url_secrets(plain) == plain


def test_log_error_redacts_and_sets_mode(tmp_path, monkeypatch):
    logfile = tmp_path / ".wallpaper_errors.log"
    monkeypatch.setattr("wallpaperctl.util.home", lambda: tmp_path)
    log_error("Pixabay fetch failed: https://pixabay.com/api/?key=TOK9&q=x")
    data = logfile.read_text()
    assert "TOK9" not in data
    assert "key=REDACTED" in data
    mode = stat.S_IMODE(logfile.stat().st_mode)
    assert mode == 0o600


def test_lock_rm_lockdir_refuses_symlink(tmp_path):
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "keep.txt").write_text("x")
    lock = WallpaperLock()
    lock.lockdir = tmp_path / "wallpaper-lock"
    lock.lockdir.symlink_to(victim)
    lock._rm_lockdir()
    # Symlink untouched, victim contents intact
    assert lock.lockdir.is_symlink()
    assert (victim / "keep.txt").is_file()


@pytest.mark.skipif(sys.platform != "linux", reason="/proc only on Linux")
def test_pid_is_ours_rejects_non_wallpaper_pid():
    # Current process runs pytest, not wallpaperctl
    assert WallpaperLock._pid_is_ours(os.getpid()) is False


def test_pid_is_ours_missing_proc_defaults_true(tmp_path, monkeypatch):
    # No /proc readable path -> trust the pid file (BSD behaviour)
    monkeypatch.setattr(
        "builtins.open", lambda *a, **k: (_ for _ in ()).throw(OSError)
    )
    assert WallpaperLock._pid_is_ours(12345) is True


def test_contained(tmp_path):
    inside = tmp_path / "a.jpg"
    inside.write_text("x")
    assert _contained(inside, tmp_path)
    outside = tmp_path.parent / "elsewhere.jpg"
    outside.write_text("x")
    assert not _contained(outside, tmp_path)
