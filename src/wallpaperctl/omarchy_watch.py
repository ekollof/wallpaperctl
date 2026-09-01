"""Rebind Omarchy motion wallpaper after Hyprland monitor layout changes.

The third-party motion-wallpaper plugin does not restart its decoder when a
screen is rotated (Hyprland recreates the output). Patching the plugin would
be lost on ``omarchy plugin update``, so wallpaperctl owns a small watcher
instead: on monitor add/remove/reload it stop+plays the clip from the
plugin's state file, which recreates the video surfaces through official IPC.
"""

from __future__ import annotations

import logging
import os
import select
import socket
import stat
import sys
import time
from pathlib import Path

from wallpaperctl.omarchy import (
    motion_state_file,
    motion_wallpaper_play,
    motion_wallpaper_stop,
)
from wallpaperctl.util import run, spawn_detached

log = logging.getLogger("wallpaperctl")

_WATCH_DIR = Path("~/.cache/wallpaperctl").expanduser()
_PID_FILE = _WATCH_DIR / "omarchy-motion-watch.pid"
_LAYOUT_EVENTS = frozenset(
    {
        "monitoradded",
        "monitoraddedv2",
        "monitorremoved",
        "monitorremovedv2",
        "configreloaded",
    }
)
_DEBOUNCE_S = 0.35
_RECONNECT_S = 1.0
_POLL_S = 0.4


def is_layout_event(line: str) -> bool:
    name = (line or "").split(">>", 1)[0].strip()
    return name in _LAYOUT_EVENTS


def monitor_layout_fingerprint(payload: str | None = None) -> str:
    """Stable id of connected outputs: name, size, transform, scale, position.

    Hyprland does **not** emit monitoradded/removed on an in-place rotate
    (transform). Polling ``hyprctl -j monitors`` is what actually sees it.
    """
    text = payload
    if text is None:
        r = run(["hyprctl", "-j", "monitors"], timeout=2)
        if r.returncode != 0:
            return ""
        text = r.stdout or ""
    try:
        import json

        mons = json.loads(text)
    except (ValueError, TypeError):
        return ""
    if not isinstance(mons, list):
        return ""
    parts: list[str] = []
    for mon in mons:
        if not isinstance(mon, dict):
            continue
        parts.append(
            f"{mon.get('name')}:"
            f"{mon.get('width')}x{mon.get('height')}:"
            f"t{mon.get('transform')}:"
            f"s{mon.get('scale')}:"
            f"{mon.get('x')},{mon.get('y')}"
        )
    return "|".join(sorted(parts))


def hyprland_socket2_path() -> Path | None:
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "").strip()
    if sig:
        path = Path(runtime) / "hypr" / sig / ".socket2.sock"
        return path if _is_socket(path) else None
    hypr = Path(runtime) / "hypr"
    if not hypr.is_dir():
        return None
    try:
        entries = sorted(hypr.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return None
    for entry in entries:
        sock = entry / ".socket2.sock"
        if _is_socket(sock):
            return sock
    return None


def _is_socket(path: Path) -> bool:
    try:
        return stat.S_ISSOCK(path.stat().st_mode)
    except OSError:
        return False


def rebind_motion_wallpaper() -> bool:
    """Stop+play the persisted clip so surfaces are recreated after a rotate."""
    path = motion_state_file()
    try:
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    if not isinstance(data, dict):
        return False
    enabled = data.get("enabled")
    if not (enabled is True or str(enabled).lower() == "true"):
        return False
    video = Path(str(data.get("videoPath") or "")).expanduser()
    if not video.is_file():
        return False
    motion_wallpaper_stop()
    # Give the plugin a beat to destroy surfaces before play recreates them.
    time.sleep(0.12)
    return motion_wallpaper_play(video)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _read_pid() -> int | None:
    try:
        text = _PID_FILE.read_text(encoding="utf-8").strip()
        pid = int(text)
    except (OSError, ValueError):
        return None
    return pid if _pid_alive(pid) else None


def watch_running() -> bool:
    return _read_pid() is not None


def stop_watch() -> None:
    pid = _read_pid()
    if pid is not None:
        try:
            os.kill(pid, 15)
        except OSError:
            pass
    try:
        _PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def _watch_argv() -> list[str]:
    """Prefer the running wallpaperctl entry so we don't pick an older pipx."""
    argv0 = Path(sys.argv[0]).name
    if argv0 in ("wallpaperctl", "wallpaper"):
        return [sys.argv[0], "omarchy-watch", "--foreground"]
    return [sys.executable, "-m", "wallpaperctl", "omarchy-watch", "--foreground"]


def ensure_watch_running() -> None:
    """Start the watcher in the background if it is not already up."""
    if watch_running():
        return
    cmd = _watch_argv()
    _WATCH_DIR.mkdir(parents=True, exist_ok=True)
    proc = spawn_detached(cmd)
    if proc is None:
        log.debug("omarchy-watch: failed to spawn")
        return
    try:
        _PID_FILE.write_text(f"{proc.pid}\n", encoding="utf-8")
    except OSError as e:
        log.debug("omarchy-watch: could not write pid file: %s", e)


def _write_own_pid() -> None:
    _WATCH_DIR.mkdir(parents=True, exist_ok=True)
    _PID_FILE.write_text(f"{os.getpid()}\n", encoding="utf-8")


def watch_loop(*, once_socket: Path | None = None) -> int:
    """Block, reading Hyprland events until the socket goes away (then retry)."""
    _write_own_pid()
    pending_until = 0.0
    last_fp = monitor_layout_fingerprint()
    while True:
        sock_path = once_socket or hyprland_socket2_path()
        if sock_path is None:
            time.sleep(_RECONNECT_S)
            if once_socket is not None:
                return 1
            continue
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(None)
            sock.connect(str(sock_path))
        except OSError:
            time.sleep(_RECONNECT_S)
            if once_socket is not None:
                return 1
            continue
        try:
            with sock, sock.makefile("r", encoding="utf-8", errors="replace") as stream:
                while True:
                    now = time.monotonic()
                    timeout = _POLL_S
                    if pending_until:
                        timeout = min(timeout, max(0.0, pending_until - now))
                    ready, _, _ = select.select([sock], [], [], timeout)
                    fp = monitor_layout_fingerprint()
                    if fp and fp != last_fp:
                        last_fp = fp
                        pending_until = time.monotonic() + _DEBOUNCE_S
                    if pending_until and time.monotonic() >= pending_until:
                        pending_until = 0.0
                        try:
                            rebind_motion_wallpaper()
                        except Exception as e:  # noqa: BLE001 — watcher must not die
                            log.debug("omarchy-watch rebind failed: %s", e)
                    if not ready:
                        continue
                    line = stream.readline()
                    if line == "":
                        break
                    if is_layout_event(line):
                        pending_until = time.monotonic() + _DEBOUNCE_S
        finally:
            try:
                sock.close()
            except OSError:
                pass
        if once_socket is not None:
            return 0
        time.sleep(_RECONNECT_S)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    foreground = "--foreground" in args
    if foreground:
        return watch_loop()
    ensure_watch_running()
    return 0
