"""Detached daemon spawn must not keep the caller's TTY as stdin."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from unittest.mock import patch

import pytest

from wallpaperctl.util import spawn_detached


def test_spawn_detached_wires_stdio_and_new_session() -> None:
    with patch("wallpaperctl.util.subprocess.Popen") as popen:
        popen.return_value = object()
        assert spawn_detached(["xsettingsd"]) is popen.return_value
    kwargs = popen.call_args.kwargs
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["stdout"] is subprocess.DEVNULL
    assert kwargs["stderr"] is subprocess.DEVNULL
    assert kwargs["start_new_session"] is True
    assert kwargs["close_fds"] is True
    assert popen.call_args.args[0] == ["xsettingsd"]


def test_spawn_detached_returns_none_on_oserror() -> None:
    with patch(
        "wallpaperctl.util.subprocess.Popen",
        side_effect=OSError("boom"),
    ):
        assert spawn_detached(["missing-daemon"]) is None


@pytest.mark.skipif(not os.path.exists("/bin/sleep"), reason="need /bin/sleep")
def test_spawn_detached_child_stdin_is_not_a_tty() -> None:
    """Live check: child must not inherit the interactive terminal."""
    proc = spawn_detached(["/bin/sleep", "30"])
    assert proc is not None
    try:
        time.sleep(0.1)
        assert proc.poll() is None
        stdin = os.readlink(f"/proc/{proc.pid}/fd/0")
        assert "null" in stdin
        # New session: session id == pid for the session leader
        raw = open(f"/proc/{proc.pid}/stat", encoding="utf-8").read()
        rparen = raw.rfind(")")
        fields = raw[rparen + 2 :].split()
        sid = int(fields[3])  # after ')': state ppid pgrp session
        assert sid == proc.pid
    finally:
        try:
            os.kill(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=2)
        except Exception:
            pass
