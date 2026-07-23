"""PID-based exclusive lock (mkdir lockdir, same idea as the shell tool)."""

from __future__ import annotations

import atexit
import os
import signal
import sys
import tempfile
from pathlib import Path


class WallpaperLock:
    def __init__(self) -> None:
        uid = os.getuid() if hasattr(os, "getuid") else os.getpid()
        base = Path(tempfile.gettempdir())
        self.lockdir = base / f"wallpaper-{uid}.lock"
        self._held = False

    def acquire(self) -> None:
        if self._try_mkdir():
            self._held = True
            self._write_pid()
            self._install_cleanup()
            return

        pid_file = self.lockdir / "pid"
        if pid_file.is_file():
            try:
                owner = int(pid_file.read_text().strip())
            except (ValueError, OSError):
                owner = 0
            if owner and self._pid_alive(owner):
                print(
                    f"Another wallpaper process is already running (PID {owner}).",
                    file=sys.stderr,
                )
                raise SystemExit(1)

        # Stale lock
        self._rm_lockdir()
        if self._try_mkdir():
            self._held = True
            self._write_pid()
            self._install_cleanup()
            return

        print(f"Failed to acquire wallpaper lock ({self.lockdir}).", file=sys.stderr)
        raise SystemExit(1)

    def release(self) -> None:
        if self._held:
            self._rm_lockdir()
            self._held = False

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
