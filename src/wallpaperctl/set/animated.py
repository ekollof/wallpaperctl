"""Animated wallpaper playback for X11 and wlroots Wayland."""

from __future__ import annotations

import os
import re
import signal
import stat
import subprocess
import time
from pathlib import Path

from wallpaperctl.context import WallpaperContext
from wallpaperctl.set.base import debug_set
from wallpaperctl.set.plasma import PlasmaSetter
from wallpaperctl.util import have, run

# Shared mpv playback options for both backends: aspect-preserving letterbox
# with an opaque black background (never crop, never show what is underneath).
_MPV_WALLPAPER_OPTIONS = [
    "--no-audio",
    "--loop-file=inf",
    "--panscan=0",
    "--background=color",
    "--background-color=#000000",
]
# Cmdline patterns of wallpaperctl-launched players that may outlive their
# pid file (crashed runs, manual restarts).
_STALE_PROCESS_PATTERNS = (r"xwinwrap.*mpv.*%WID", r"mpvpaper .*--mpv-options")


def _is_socket(path: Path) -> bool:
    try:
        return stat.S_ISSOCK(path.stat().st_mode)
    except OSError:
        return False


class AnimatedSetter:
    name = "animated"
    _state_dir = Path("~/.cache/wallpaperctl").expanduser()
    _pid_file = _state_dir / "animated.pid"
    _socket = _state_dir / "animated.sock"

    def applies(self, ctx: WallpaperContext) -> bool:
        return ctx.is_animated

    @classmethod
    def stop_active(cls) -> None:
        """Stop any running animated playback (used before static setters)."""
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
            # mpvpaper leaves aspect-ratio margins transparent; refresh the
            # Plasma image underneath (aspect-fit + black) before playback.
            PlasmaSetter().set_wallpaper(ctx)
        layer = "bottom" if ctx.de.plasma else "background"
        mpv_options = " ".join(
            [*_MPV_WALLPAPER_OPTIONS, f"--input-ipc-server={self._socket}"]
        )
        try:
            self._state_dir.mkdir(parents=True, exist_ok=True)
            self._socket.unlink(missing_ok=True)
            process = subprocess.Popen(
                [
                    "mpvpaper",
                    "--layer",
                    layer,
                    "--mpv-options",
                    mpv_options,
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
        processes: list[subprocess.Popen] = []
        try:
            self._state_dir.mkdir(parents=True, exist_ok=True)
            for geometry_args in self._x11_geometry_args():
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
                        *_MPV_WALLPAPER_OPTIONS,
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
        except (OSError, RuntimeError) as e:
            self._pid_file.unlink(missing_ok=True)
            for process in processes:
                self._terminate(process.pid)
            debug_set(self.name, f"xwinwrap failed: {e}", ctx)
            return False
        debug_set(self.name, f"xwinwrap started for {len(processes)} output(s)", ctx)
        return True

    @staticmethod
    def _x11_geometry_args() -> list[list[str]]:
        """Per-output xwinwrap geometry fragments; [["-fs"]] when unknown."""
        if not have("xrandr"):
            return [["-fs"]]
        result = run(["xrandr", "--query"], timeout=10)
        geometries = re.findall(
            r"^\S+ connected(?: primary)?\s+(\d+x\d+\+-?\d+\+-?\d+)",
            result.stdout or "",
            re.MULTILINE,
        )
        return [["-g", geometry] for geometry in geometries] or [["-fs"]]

    def _stop_previous(self) -> None:
        if have("socat") and _is_socket(self._socket):
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
            for pattern in _STALE_PROCESS_PATTERNS:
                result = run(["pgrep", "-f", pattern], timeout=5)
                if result.returncode == 0:
                    pids.update(
                        int(line) for line in result.stdout.split() if line.isdigit()
                    )
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
