"""Theme serialization: named locks, waiting acquire, superseded-run abort."""

from __future__ import annotations

import io
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from wallpaperctl.config import OpsConfig
from wallpaperctl.context import WallpaperContext
from wallpaperctl.detect.desktop import DesktopEnvironment
from wallpaperctl.lock import WallpaperLock
from wallpaperctl.theme import runner as theme_runner


def _use_tmp_locks(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))


def test_named_lock_paths_differ(tmp_path) -> None:
    default = WallpaperLock()
    theme = WallpaperLock(name="wallpaper-theme")
    assert default.lockdir != theme.lockdir
    assert default.lockdir.name.startswith("wallpaper-")
    assert theme.lockdir.name.startswith("wallpaper-theme-")


def test_acquire_waiting_immediate_success(tmp_path, monkeypatch) -> None:
    _use_tmp_locks(monkeypatch, tmp_path)
    lock = WallpaperLock(name="test-wait")
    try:
        assert lock.acquire_waiting(timeout=5.0) is True
    finally:
        lock.release()
    assert not lock.lockdir.exists()


def test_acquire_waiting_times_out_on_live_owner(tmp_path, monkeypatch) -> None:
    _use_tmp_locks(monkeypatch, tmp_path)
    lock = WallpaperLock(name="test-busy")
    with patch.object(WallpaperLock, "_attempt", return_value=False):
        start = time.monotonic()
        assert lock.acquire_waiting(timeout=0.05, poll=0.01) is False
        assert time.monotonic() - start < 5.0


def test_acquire_waiting_abort_stops_early(tmp_path, monkeypatch) -> None:
    _use_tmp_locks(monkeypatch, tmp_path)
    lock = WallpaperLock(name="test-abort")
    calls = 0

    def _abort() -> bool:
        nonlocal calls
        calls += 1
        return True

    with patch.object(WallpaperLock, "_attempt", return_value=False):
        start = time.monotonic()
        assert lock.acquire_waiting(timeout=60.0, poll=0.01, abort_if=_abort) is False
        assert time.monotonic() - start < 5.0
    assert calls >= 1


def test_acquire_waiting_retries_until_free(tmp_path, monkeypatch) -> None:
    _use_tmp_locks(monkeypatch, tmp_path)
    lock = WallpaperLock(name="test-retry")
    with patch.object(
        WallpaperLock, "_attempt", side_effect=[False, False, True]
    ) as attempt:
        assert lock.acquire_waiting(timeout=5.0, poll=0.01) is True
        assert attempt.call_count == 3
    lock.release()


def test_pid_is_ours_detects_python_m_worker(monkeypatch) -> None:
    cmd = b"/tmp/wct-test/bin/python\x00-m\x00wallpaperctl\x00__theme__\x00/x\x00"
    monkeypatch.setattr("builtins.open", lambda *a, **k: io.BytesIO(cmd))
    assert WallpaperLock._pid_is_ours(99999) is True


def test_pid_is_ours_detects_entry_script(monkeypatch) -> None:
    cmd = b"/home/u/.local/bin/wallpaperctl\x00set\x00x.jpg\x00"
    monkeypatch.setattr("builtins.open", lambda *a, **k: io.BytesIO(cmd))
    assert WallpaperLock._pid_is_ours(99999) is True


def test_pid_is_ours_rejects_unrelated_python(monkeypatch) -> None:
    cmd = b"/usr/bin/python\x00-m\x00pytest\x00tests/test_x.py\x00"
    monkeypatch.setattr("builtins.open", lambda *a, **k: io.BytesIO(cmd))
    assert WallpaperLock._pid_is_ours(99999) is False


class _FakeOp:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls = 0

    def enabled(self, ctx) -> bool:
        return True

    def run(self, ctx) -> bool:
        self.calls += 1
        return True


def _ctx(tmp_path: Path) -> WallpaperContext:
    ops = OpsConfig()
    ops.max_retries = 1
    ops.retry_delay = 0.0
    img = tmp_path / "w.jpg"
    img.write_bytes(b"x")
    return WallpaperContext(path=img, de=DesktopEnvironment(), ops=ops)


def test_runner_aborts_before_any_op(tmp_path) -> None:
    ops = [_FakeOp("a"), _FakeOp("b")]
    ctx = _ctx(tmp_path)
    with (
        patch.object(theme_runner, "THEME_OPS", ops),
        patch.object(theme_runner.time, "sleep", lambda s: None),
    ):
        failed, total = theme_runner.run_theme_ops(ctx, abort_if=lambda: True)
    assert (failed, total) == (0, 0)
    assert all(op.calls == 0 for op in ops)


def test_runner_aborts_between_ops(tmp_path) -> None:
    ops = [_FakeOp("a"), _FakeOp("b"), _FakeOp("c")]
    ctx = _ctx(tmp_path)
    states = [False, True]  # run first op, then abort

    with (
        patch.object(theme_runner, "THEME_OPS", ops),
        patch.object(theme_runner.time, "sleep", lambda s: None),
    ):
        failed, total = theme_runner.run_theme_ops(
            ctx, abort_if=lambda: states.pop(0) if states else True
        )
    assert (failed, total) == (0, 1)
    assert ops[0].calls == 1
    assert ops[1].calls == 0
    assert ops[2].calls == 0


def test_runner_abort_check_exception_is_soft(tmp_path) -> None:
    ops = [_FakeOp("a")]
    ctx = _ctx(tmp_path)

    def _boom() -> bool:
        raise RuntimeError("boom")

    with (
        patch.object(theme_runner, "THEME_OPS", ops),
        patch.object(theme_runner.time, "sleep", lambda s: None),
    ):
        failed, total = theme_runner.run_theme_ops(ctx, abort_if=_boom)
    assert (failed, total) == (0, 1)
    assert ops[0].calls == 1


def test_acquire_release_roundtrip_default_lock_untouched(
    tmp_path, monkeypatch
) -> None:
    """Waiting API must not alter the classic main-lock behavior."""
    _use_tmp_locks(monkeypatch, tmp_path)
    lock = WallpaperLock()
    lock.acquire()
    assert lock.lockdir.is_dir()
    lock.release()
    assert not lock.lockdir.exists()
    uid = os.getuid() if hasattr(os, "getuid") else os.getpid()
    assert lock.lockdir.name == f"wallpaper-{uid}.lock"
