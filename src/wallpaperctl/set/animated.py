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
from wallpaperctl.util import have, run, wm_x11_name

# Shared mpv playback options for both backends: aspect-preserving letterbox
# with an opaque black background (never crop, never show what is underneath),
# plus hardware decode and cheap scaling/shading to keep GPU load low.
_MPV_WALLPAPER_OPTIONS = [
    "--no-audio",
    "--loop-file=inf",
    "--panscan=0",
    "--background=color",
    "--background-color=#000000",
    "--hwdec=auto-safe",
    "--vd-lavc-fast",
    "--scale=bilinear",
    "--dscale=bilinear",
    "--cscale=bilinear",
    "--deband=no",
    "--dither-depth=no",
]
# Cmdline patterns of wallpaperctl-launched players that may outlive their
# pid file (crashed runs, manual restarts).
_STALE_PROCESS_PATTERNS = (
    r"xwinwrap.*mpv.*%WID",
    r"mpvpaper .*--mpv-options",
    r"ffmpeg .*wallpaperctl/animated-live",
    r"feh .*--bg-fill .*animated-live",
)
# Watch players this long for early exits before declaring success.
_STARTUP_GRACE = 2.5
# Wait this long after SIGTERM before escalating to SIGKILL.
_TERM_GRACE = 2.0
# Root-pixmap animator FPS (EXWM/picom transparent-clipping path).
_ROOT_PIXMAP_FPS = 8


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
    # Player stderr/stdout breadcrumbs (crashed starts, codec errors).
    _log_file = _state_dir / "animated.log"

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
        if os.environ.get("DISPLAY"):
            return self._set_x11(ctx)
        debug_set(self.name, "no animated backend available", ctx)
        return False

    def _set_x11(self, ctx: WallpaperContext) -> bool:
        """X11/XLibre animated wallpaper.

        Prefer xwinwrap+mpv (override-redirect below other windows). Fall back
        to ffmpeg+feh root-pixmap updates when xwinwrap/mpv are missing — that
        path is what picom ``transparent-clipping`` can reveal through EXWM.
        """
        self._stop_previous()
        self._set_static_underlay(ctx)
        if have("xwinwrap") and have("mpv"):
            return self._set_xwinwrap(ctx, already_prepared=True)
        if have("ffmpeg") and have("feh"):
            debug_set(self.name, "falling back to root-pixmap animation", ctx)
            return self._set_root_pixmap_animation(ctx)
        debug_set(self.name, "need xwinwrap+mpv or ffmpeg+feh for X11 video", ctx)
        return False

    @staticmethod
    def _virtual_screen_size() -> tuple[int, int]:
        if have("xdpyinfo"):
            r = run(["xdpyinfo"], timeout=5)
            m = re.search(
                r"dimensions:\s+(\d+)x(\d+)\s+pixels", r.stdout or ""
            )
            if m:
                return int(m.group(1)), int(m.group(2))
        if have("xrandr"):
            r = run(["xrandr"], timeout=5)
            m = re.search(r"current\s+(\d+)\s+x\s+(\d+)", r.stdout or "")
            if m:
                return int(m.group(1)), int(m.group(2))
        return 1920, 1080

    def _set_root_pixmap_animation(self, ctx: WallpaperContext) -> bool:
        """Loop video frames onto the X root pixmap (feh) via ffmpeg.

        Fallback when xwinwrap/mpv are unavailable. Also usable under picom
        ``transparent-clipping``, which composites the root pixmap (not
        xwinwrap windows) through transparent clients.
        """
        if not (have("ffmpeg") and have("feh")):
            debug_set(self.name, "ffmpeg/feh required for root-pixmap animation", ctx)
            return False
        frame = self._state_dir / "animated-live.jpg"
        partial = self._state_dir / "animated-live.partial.jpg"
        width, height = self._virtual_screen_size()
        fps = max(1, int(_ROOT_PIXMAP_FPS))
        # Letterbox into the virtual desktop size (multi-monitor span).
        vf = (
            f"fps={fps},"
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black"
        )
        # ffmpeg writes *partial*; we copy to a stable path once size settles
        # so feh never mmaps a half-written JPEG (SIGBUS under EXWM/picom).
        script = f"""
set +e
PARTIAL={partial!s}
FRAME={frame!s}
rm -f "$PARTIAL" "$FRAME"
ffmpeg -hide_banner -loglevel error -nostdin \\
  -re -stream_loop -1 -i {str(ctx.path)!r} \\
  -vf {vf!r} -q:v 5 -update 1 "$PARTIAL" &
FP=$!
trap 'kill "$FP" 2>/dev/null; wait "$FP" 2>/dev/null; exit 0' EXIT INT TERM
for i in $(seq 1 80); do
  [ -s "$PARTIAL" ] && break
  kill -0 "$FP" 2>/dev/null || exit 1
  sleep 0.1
done
LAST=0
while kill -0 "$FP" 2>/dev/null; do
  if [ -s "$PARTIAL" ]; then
    S1=$(stat -c %s "$PARTIAL" 2>/dev/null || echo 0)
    sleep 0.02
    S2=$(stat -c %s "$PARTIAL" 2>/dev/null || echo 0)
    MT=$(stat -c %Y "$PARTIAL" 2>/dev/null || echo 0)
    if [ "$S1" = "$S2" ] && [ "$S1" -gt 1000 ] && [ "$MT" != "$LAST" ]; then
      cp -f "$PARTIAL" "$FRAME" 2>/dev/null || continue
      feh --no-fehbg --bg-fill "$FRAME" >/dev/null 2>&1 || true
      LAST=$MT
    fi
  fi
  sleep 0.08
done
wait "$FP" || true
"""
        try:
            self._state_dir.mkdir(parents=True, exist_ok=True)
            frame.unlink(missing_ok=True)
            with self._log_file.open("w") as log_fh:
                process = subprocess.Popen(
                    ["bash", "-c", script],
                    stdin=subprocess.DEVNULL,
                    stdout=log_fh,
                    stderr=log_fh,
                    start_new_session=True,
                )
                self._pid_file.write_text(f"{process.pid}\n", encoding="utf-8")
                dead = self._wait_for_early_exit([process])
                rc = dead[0].returncode if dead else None
        except OSError as e:
            debug_set(self.name, f"root-pixmap animator start failed: {e}", ctx)
            return False
        if dead:
            self._pid_file.unlink(missing_ok=True)
            debug_set(
                self.name,
                f"root-pixmap animator exited (rc={rc}): {self._log_tail()}",
                ctx,
            )
            return False
        debug_set(
            self.name,
            f"root-pixmap animator started (pid={process.pid}, {width}x{height}@{fps}fps)",
            ctx,
        )
        return True

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
            self._set_static_underlay(ctx)
        layer = "bottom" if ctx.de.plasma else "background"

        mpv_options = " ".join(
            [*_MPV_WALLPAPER_OPTIONS, f"--input-ipc-server={self._socket}"]
        )
        try:
            self._state_dir.mkdir(parents=True, exist_ok=True)
            self._socket.unlink(missing_ok=True)
            with self._log_file.open("w") as log_fh:
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
                    stdout=log_fh,
                    stderr=log_fh,
                    start_new_session=True,
                )
                self._pid_file.write_text(f"{process.pid}\n", encoding="utf-8")
                dead = self._wait_for_early_exit([process])
                rc = dead[0].returncode if dead else None
        except OSError as e:
            debug_set(self.name, f"mpvpaper start failed: {e}", ctx)
            return False
        if dead:
            self._pid_file.unlink(missing_ok=True)
            self._socket.unlink(missing_ok=True)
            debug_set(
                self.name,
                f"mpvpaper exited during startup (rc={rc}): {self._log_tail()}",
                ctx,
            )
            return False
        debug_set(self.name, f"mpvpaper started (pid={process.pid})", ctx)
        return True

    def _set_static_underlay(self, ctx: WallpaperContext) -> bool:
        """Paint the extracted still as the root/DE wallpaper under the video.

        AnimatedSetter short-circuits the setter chain on success, so without
        this the old static wallpaper stays visible in letterbox margins (and
        whenever xwinwrap/mpv fails to cover an output). Plasma Wayland already
        did this; X11/XLibre needs the same.
        """
        img = ctx.image_path
        if img is None or not img.is_file() or img == ctx.path:
            debug_set(self.name, "no still frame for underlay", ctx)
            return False
        if ctx.de.plasma:
            ok = PlasmaSetter().set_wallpaper(ctx)
            debug_set(
                self.name,
                "plasma still underlay ok" if ok else "plasma still underlay failed",
                ctx,
            )
            return ok
        from wallpaperctl.set.fallback import FallbackSetter

        ok = FallbackSetter().set_wallpaper(ctx)
        debug_set(
            self.name,
            f"still underlay {'ok' if ok else 'failed'} ({img.name})",
            ctx,
        )
        return ok

    def _set_xwinwrap(
        self, ctx: WallpaperContext, *, already_prepared: bool = False
    ) -> bool:
        if not already_prepared:
            self._stop_previous()
            self._set_static_underlay(ctx)
        processes: list[subprocess.Popen] = []
        try:
            self._state_dir.mkdir(parents=True, exist_ok=True)
            with self._log_file.open("w") as log_fh:
                for geometry_args in self._x11_geometry_args():
                    # -ov (override-redirect) keeps tiling WMs (qtile, i3, …)
                    # from managing the wrapper as a client. EXWM is excluded:
                    # takase1121 xwinwrap's -ov path finds the fullscreen
                    # workspace frame there and XCreateWindow parents onto the
                    # Emacs inner window (video becomes a "tab", not a root
                    # underlay). Without -ov, -fdt sets TYPE_DESKTOP on a real
                    # root child; EXWM and stacking WMs leave it alone.
                    process = subprocess.Popen(
                        [
                            "xwinwrap",
                            *self._xwinwrap_flags(),
                            "-b",
                            "-ni",
                            "-s",
                            *geometry_args,
                            "-st",
                            "-sp",
                            "-nf",
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
                        stdout=log_fh,
                        stderr=log_fh,
                        start_new_session=True,
                    )
                    processes.append(process)
                    if process.poll() is not None:
                        raise RuntimeError(
                            f"xwinwrap exited with status {process.returncode}"
                        )
                dead = self._wait_for_early_exit(processes)
                if dead:
                    raise RuntimeError(
                        f"xwinwrap/mpv exited during startup "
                        f"(rc={dead[0].returncode}): {self._log_tail()}"
                    )
                self._pid_file.write_text(
                    "".join(f"{process.pid}\n" for process in processes),
                    encoding="utf-8",
                )
        except (OSError, RuntimeError) as e:
            self._pid_file.unlink(missing_ok=True)
            for process in processes:
                self._terminate(process.pid)
            debug_set(self.name, f"xwinwrap failed: {e}", ctx)
            # Still-frame underlay may have succeeded — report video failure
            # but do not undo the root pixmap.
            return False
        debug_set(self.name, f"xwinwrap started for {len(processes)} output(s)", ctx)
        return True

    @staticmethod
    def _xwinwrap_flags() -> list[str]:
        """Extra xwinwrap flags; ["-ov"] unless the WM has known -ov bugs.

        Override-redirect bypasses window management entirely, which is what
        tiling WMs (qtile ignores _NET_WM_WINDOW_TYPE_DESKTOP) need. Unknown
        WM name keeps the historical EXWM-safe behaviour.
        """
        wm = wm_x11_name()
        if not wm or wm.lower() == "exwm":
            return []
        return ["-ov"]

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
    def _wait_for_early_exit(processes: list[subprocess.Popen]) -> list[subprocess.Popen]:
        """Processes that exit within the startup grace window."""
        grace = max(0.0, float(_STARTUP_GRACE))
        deadline = time.monotonic() + grace
        while True:
            dead = [p for p in processes if p.poll() is not None]
            if dead or time.monotonic() >= deadline:
                return dead
            time.sleep(0.1)

    @staticmethod
    def _log_tail(lines: int = 12) -> str:
        try:
            text = AnimatedSetter._log_file.read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            return "(no player log)"
        relevant = [ln for ln in text.splitlines() if ln.strip()]
        return " | ".join(relevant[-lines:]) or "(empty player log)"

    @staticmethod
    def _alive(pid: int) -> bool:
        # waitpid reaps our own exited children (zombies would otherwise look
        # alive to kill(pid, 0)); other pids fall back to signal 0.
        try:
            wpid, _status = os.waitpid(pid, os.WNOHANG)
            return wpid == 0
        except ChildProcessError:
            pass
        except OSError:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False
        return True

    @staticmethod
    def _signal(pid: int, sig: int) -> bool:
        """Deliver *sig* to the process group, falling back to the single pid."""
        for killer in (os.killpg, os.kill):
            try:
                killer(pid, sig)
                return True
            except (ProcessLookupError, PermissionError, OSError):
                continue
        return False

    @classmethod
    def _terminate(cls, pid: int) -> None:
        """SIGTERM the player; escalate to SIGKILL if it survives the grace."""
        if not cls._signal(pid, signal.SIGTERM):
            return
        deadline = time.monotonic() + _TERM_GRACE
        while time.monotonic() < deadline:
            if not cls._alive(pid):
                return
            time.sleep(0.1)
        cls._signal(pid, signal.SIGKILL)
