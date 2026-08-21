"""Animated wallpaper playback for X11 and wlroots Wayland."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import time
from pathlib import Path

from wallpaperctl.context import WallpaperContext
from wallpaperctl.set.base import debug_set
from wallpaperctl.util import have, run


class AnimatedSetter:
    name = "animated"
    _state_dir = Path("~/.cache/wallpaperctl").expanduser()
    _pid_file = _state_dir / "animated.pid"
    _socket = _state_dir / "animated.sock"

    def applies(self, ctx: WallpaperContext) -> bool:
        return ctx.is_animated

    @classmethod
    def stop_active(cls) -> None:
        cls()._stop_previous()

    def set_wallpaper(self, ctx: WallpaperContext) -> bool:
        if not ctx.path.is_file():
            return False
        if os.environ.get("WAYLAND_DISPLAY") and self._wayland_supported(ctx):
            return self._set_mpvpaper(ctx)
        if os.environ.get("DISPLAY") and have("xwinwrap") and have("mpv"):
            return self._set_xwinwrap(ctx)
        debug_set(self.name, "no animated backend available", ctx)
        return False

    @staticmethod
    def _wayland_supported(ctx: WallpaperContext) -> bool:
        # KWin supports the layer-shell protocol used by mpvpaper. Noctalia and
        # COSMIC own their wallpaper surfaces, so avoid competing with them.
        return not (ctx.de.cosmic or ctx.de.noctalia)

    def _set_mpvpaper(self, ctx: WallpaperContext) -> bool:
        if not have("mpvpaper") or not have("mpv"):
            debug_set(self.name, "mpvpaper or mpv not found", ctx)
            return False
        self._stop_previous()
        if ctx.de.plasma:
            # mpvpaper may leave aspect-ratio margins transparent; replace any
            # previous Plasma image before starting the animated layer.
            from wallpaperctl.set.plasma import PlasmaSetter

            PlasmaSetter().set_wallpaper(ctx)
        layer = "bottom" if ctx.de.plasma else "background"
        try:
            self._state_dir.mkdir(parents=True, exist_ok=True)
            self._socket.unlink(missing_ok=True)
            process = subprocess.Popen(
                [
                    "mpvpaper",
                    "--layer",
                    layer,
                    "--mpv-options",
                    f"no-audio loop panscan=0 background=color "
                    f"background-color=#000000 input-ipc-server={self._socket}",
                    "ALL",
                    str(ctx.path),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            self._pid_file.write_text(f"{process.pid}\n", encoding="utf-8")
        except OSError as e:
            debug_set(self.name, f"mpvpaper start failed: {e}", ctx)
            return False
        time.sleep(0.2)
        if process.poll() is not None:
            self._pid_file.unlink(missing_ok=True)
            debug_set(self.name, f"mpvpaper exited with status {process.returncode}", ctx)
            return False
        debug_set(self.name, f"mpvpaper started (pid={process.pid})", ctx)
        return True

    def _set_xwinwrap(self, ctx: WallpaperContext) -> bool:
        self._stop_previous()
        geometries = self._x11_geometries()
        processes: list[subprocess.Popen] = []
        try:
            self._state_dir.mkdir(parents=True, exist_ok=True)
            for geometry in geometries:
                geometry_args = ["-g", geometry] if geometry != "-fs" else ["-fs"]
                process = subprocess.Popen(
                    [
                        "xwinwrap",
                        "-b",
                        "-ni",
                        "-s",
                        *geometry_args,
                        "-st",
                        "-sp",
                        "-nf",
                        "-ov",
                        "-fdt",
                        "--",
                        "mpv",
                        "-wid",
                        "%WID",
                        "--really-quiet",
                        "--framedrop=vo",
                        "--no-audio",
                        "--panscan=0",
                        "--background=color",
                        "--background-color=#000000",
                        "--loop-file=inf",
                        str(ctx.path),
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                processes.append(process)
                time.sleep(0.2)
                if process.poll() is not None:
                    raise RuntimeError(f"xwinwrap exited with status {process.returncode}")
            self._pid_file.write_text(
                "".join(f"{process.pid}\n" for process in processes),
                encoding="utf-8",
            )
        except OSError as e:
            debug_set(self.name, f"xwinwrap start failed: {e}", ctx)
            for process in processes:
                self._terminate(process.pid)
            return False
        except RuntimeError as e:
            self._pid_file.unlink(missing_ok=True)
            for process in processes:
                self._terminate(process.pid)
            debug_set(self.name, str(e), ctx)
            return False
        debug_set(self.name, f"xwinwrap started for {len(processes)} output(s)", ctx)
        return True

    @staticmethod
    def _x11_geometries() -> list[str]:
        if not have("xrandr"):
            return ["-fs"]
        result = run(["xrandr", "--query"], timeout=10)
        geometries = re.findall(
            r"^\S+ connected(?: primary)?\s+(\d+x\d+\+-?\d+\+-?\d+)",
            result.stdout or "",
            re.MULTILINE,
        )
        return geometries or ["-fs"]

    def _stop_previous(self) -> None:
        if have("socat") and self._socket.is_socket():
            run(["socat", "-", str(self._socket)], input_text="quit\n", timeout=2)
        pids: set[int] = set()
        try:
            pids.update(
                int(line)
                for line in self._pid_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
        except (OSError, ValueError):
            pass
        if have("pgrep"):
            for pattern in (r"xwinwrap.*mpv.*%WID", r"mpvpaper .*--mpv-options"):
                result = run(["pgrep", "-f", pattern], timeout=5)
                if result.returncode == 0:
                    pids.update(int(line) for line in result.stdout.split() if line.isdigit())
        for pid in pids:
            self._terminate(pid)
        try:
            self._pid_file.unlink(missing_ok=True)
            self._socket.unlink(missing_ok=True)
        except OSError:
            pass

    @staticmethod
    def _terminate(pid: int) -> None:
        try:
            os.killpg(pid, signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass
