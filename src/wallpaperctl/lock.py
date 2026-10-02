"""PID-based exclusive locks (mkdir lockdir, same idea as the shell tool)."""

from __future__ import annotations

import atexit
import os
import signal
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path


class WallpaperLock:
    """Exclusive mkdir lock with stale-owner recovery.

    The default ``name="wallpaper"`` preserves the historic
    ``wallpaper-<uid>.lock`` path. Background theme workers serialize on a
    separate ``name="wallpaper-theme"`` lock so overlapping theme runs can
    neither interleave file writes nor let a stale palette overwrite a newer
    wallpaper's theme.
    """

    def __init__(self, name: str = "wallpaper") -> None:
        uid = os.getuid() if hasattr(os, "getuid") else os.getpid()
        base = Path(tempfile.gettempdir())
        self.lockdir = base / f"{name}-{uid}.lock"
        self._held = False

    def acquire(self) -> None:
        if self._attempt():
            return
        if self._live_owner():
            print(
                "Another wallpaper process is already running "
                f"(PID {self._owner_pid()}).",
                file=sys.stderr,
            )
            raise SystemExit(1)
        print(f"Failed to acquire wallpaper lock ({self.lockdir}).", file=sys.stderr)
        raise SystemExit(1)

    def acquire_waiting(
        self,
        timeout: float = 300.0,
        poll: float = 0.25,
        abort_if: Callable[[], bool] | None = None,
    ) -> bool:
        """Wait up to ``timeout`` seconds for the lock. Returns held or not.

        Never raises for contention: True means the lock is held by us,
        False means the wait timed out (caller runs anyway with a warning, or
        skips). When ``abort_if`` reports True (a newer wallpaper superseded
        this run) the wait stops early with False so stale workers collapse
        instead of piling up behind the active theme run.
        """
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            if self._attempt():
                return True
            if abort_if is not None:
                try:
                    if abort_if():
                        return False
                except Exception:
                    pass
            if time.monotonic() >= deadline:
                return False
            time.sleep(max(0.01, poll))

    def release(self) -> None:
        if self._held:
            self._rm_lockdir()
            self._held = False

    def _attempt(self) -> bool:
        """Single non-blocking acquisition try (steals provably stale locks)."""
        if self._try_mkdir():
            self._held = True
            self._write_pid()
            self._install_cleanup()
            return True
        if self._live_owner():
            return False
        # Stale lock
        self._rm_lockdir()
        if self._try_mkdir():
            self._held = True
            self._write_pid()
            self._install_cleanup()
            return True
        return False

    def _owner_pid(self) -> int:
        pid_file = self.lockdir / "pid"
        if not pid_file.is_file():
            return 0
        try:
            return int(pid_file.read_text().strip())
        except (ValueError, OSError):
            return 0

    def _live_owner(self) -> bool:
        owner = self._owner_pid()
        return bool(owner) and self._pid_alive(owner) and self._pid_is_ours(owner)

    def _try_mkdir(self) -> bool:
        try:
            self.lockdir.mkdir(mode=0o700)
            return True
        except FileExistsError:
            return False
        except OSError:
            return False

    def _write_pid(self) -> None:
        try:
            (self.lockdir / "pid").write_text(str(os.getpid()), encoding="utf-8")
        except OSError:
            pass

    def _rm_lockdir(self) -> None:
        # Never follow a symlinked lockdir: unlinking children would tear
        # into whatever directory an attacker pointed the symlink at.
        try:
            if self.lockdir.is_symlink() or not self.lockdir.is_dir():
                return
        except OSError:
            return
        try:
            for child in self.lockdir.iterdir():
                child.unlink(missing_ok=True)  # type: ignore[arg-type]
            self.lockdir.rmdir()
        except OSError:
            import shutil

            shutil.rmtree(self.lockdir, ignore_errors=True)

    def _install_cleanup(self) -> None:
        atexit.register(self.release)

        def _handler(signum: int, frame: object) -> None:
            self.release()
            raise SystemExit(128 + signum)

        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            try:
                signal.signal(sig, _handler)
            except (ValueError, OSError):
                pass

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True  # exists but not ours
        except OSError:
            return False

    @staticmethod
    def _pid_is_ours(pid: int) -> bool:
        """True when pid runs a wallpaperctl entry point.

        Covers the ``wallpaperctl``/``wallpaper`` scripts as well as
        ``python -m wallpaperctl`` (detached background theme workers).

        Guards against a planted pid file blocking runs forever (shared
        /tmp). Only Linux exposes /proc; elsewhere trust the pid file.
        """
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                parts = f.read().split(b"\x00")
        except (OSError, ValueError):
            return True
        if not parts or not parts[0]:
            return True
        exe = parts[0].decode("utf-8", errors="replace").rsplit("/", 1)[-1]
        if exe in ("wallpaperctl", "wallpaper"):
            return True
        if exe.startswith("python"):
            rest = [p.decode("utf-8", errors="replace") for p in parts[1:]]
            if "wallpaperctl" in rest:
                return True
        return False
