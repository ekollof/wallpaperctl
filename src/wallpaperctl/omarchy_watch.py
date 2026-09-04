"""Rebind Omarchy motion wallpaper after Hyprland monitor layout changes.

The third-party motion-wallpaper plugin does not restart its decoder when a
screen is rotated (Hyprland recreates the output). Patching the plugin would
be lost on ``omarchy plugin update``, so wallpaperctl owns a small watcher
instead: on monitor add/remove/reload it stop+plays the clip from the
plugin's state file, which recreates the video surfaces through official IPC.

At session start the same stop+play is re-issued once: the plugin maps its
video surface before the shell's static background surface, which then
stacks on top and hides the playing clip behind a frozen frame.
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
    theme_wants_motion,
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
_STARTUP_ATTEMPTS = 8
_STARTUP_RETRY_S = 1.5


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


_SUPPRESS_FILE = _WATCH_DIR / "omarchy-motion-suppress"


def suppress_layout_rebind(seconds: float = 8.0) -> None:
    """Ignore layout changes for a bit (theme refresh reloads Hyprland)."""
    _WATCH_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _SUPPRESS_FILE.write_text(str(time.time() + max(0.0, seconds)), encoding="utf-8")
    except OSError:
        pass


def _rebind_suppressed() -> bool:
    try:
        until = float(_SUPPRESS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return time.time() < until


def snapshot_monitor_transforms(payload: str | None = None) -> list[tuple[str, int]]:
    """[(connector, transform), ...] from hyprctl JSON or an injected payload."""
    text = payload
    if text is None:
        r = run(["hyprctl", "-j", "monitors"], timeout=2)
        if r.returncode != 0:
            return []
        text = r.stdout or ""
    try:
        import json

        mons = json.loads(text)
    except (ValueError, TypeError):
        return []
    if not isinstance(mons, list):
        return []
    out: list[tuple[str, int]] = []
    for mon in mons:
        if not isinstance(mon, dict):
            continue
        name = str(mon.get("name") or "").strip()
        if not name or name.startswith("."):
            continue
        try:
            transform = int(mon.get("transform") or 0)
        except (TypeError, ValueError):
            transform = 0
        out.append((name, transform))
    return out


def _hypr_eval(expr: str) -> bool:
    r = run(["hyprctl", "eval", expr], timeout=5)
    if r.returncode != 0 or "ok" not in (r.stdout or "").lower():
        log.debug("hyprctl eval failed %s: %s", expr, (r.stderr or r.stdout or "")[:160])
        return False
    return True


def _touch_device_names() -> list[str]:
    r = run(["hyprctl", "-j", "devices"], timeout=2)
    if r.returncode != 0:
        return []
    try:
        import json

        data = json.loads(r.stdout or "{}")
    except (ValueError, TypeError):
        return []
    names: list[str] = []
    for item in data.get("touch") or []:
        if isinstance(item, dict) and item.get("name"):
            names.append(str(item["name"]))
    return names


def restore_monitor_transforms(snapshot: list[tuple[str, int]]) -> bool:
    """Re-apply runtime transforms after ``hyprctl reload`` stomps monitors.lua.

    Uses the same ``hyprctl eval hl.monitor({...})`` path as the machine's
    autorotate daemon. Retries briefly because Hyprland can finish applying
    the reloaded config *after* ``hyprctl reload`` returns.
    """
    if not snapshot:
        return True
    deadline = time.monotonic() + 1.6
    last_ok = False
    while True:
        current = {name: t for name, t in snapshot_monitor_transforms()}
        pending = [(n, t) for n, t in snapshot if current.get(n) != t]
        if not pending:
            return True
        if time.monotonic() >= deadline:
            return last_ok
        for name, transform in pending:
            escaped_name = name.replace("\\", "\\\\").replace('"', '\\"')
            last_ok = _hypr_eval(
                f'hl.monitor({{ output = "{escaped_name}", transform = {transform} }})'
            )
            # Touch digitizer transform must match the panel (autorotate.py).
            for touch in _touch_device_names():
                escaped = touch.replace("\\", "\\\\").replace('"', '\\"')
                _hypr_eval(
                    f'hl.device({{ name = "{escaped}", transform = {transform} }})'
                )
        time.sleep(0.12)


def _state_playback_clip() -> Path | None:
    """Video path from the plugin's state file when playback should be active."""
    try:
        import json

        data = json.loads(motion_state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    enabled = data.get("enabled")
    if not (enabled is True or str(enabled).lower() == "true"):
        return None
    video = Path(str(data.get("videoPath") or "")).expanduser()
    return video if video.is_file() else None


def rebind_motion_wallpaper(*, force: bool = False) -> bool:
    """Stop+play the persisted clip so surfaces are recreated after a rotate."""
    if not force and _rebind_suppressed():
        return False
    # Do not resurrect a clip after `omarchy theme set` switched to a
    # still-only theme (hyprctl reload would otherwise rebind from state.json).
    if not force and not theme_wants_motion():
        return False
    video = _state_playback_clip()
    if video is None:
        return False
    motion_wallpaper_stop()
    # Give the plugin a beat to destroy surfaces before play recreates them.
    time.sleep(0.12)
    return motion_wallpaper_play(video)


def startup_rebind(*, attempts: int = _STARTUP_ATTEMPTS) -> bool:
    """Re-issue stop+play once at session start.

    The plugin resumes playback at shell startup by mapping its video surface
    before the static background surface does, leaving the frozen still frame
    stacked on top of the playing video. Re-issuing play remaps the video
    surface above it. Retried while omarchy-shell IPC is still coming up.
    """
    if _state_playback_clip() is None or not theme_wants_motion():
        return False
    for _ in range(max(1, attempts)):
        try:
            if rebind_motion_wallpaper():
                return True
        except Exception as e:  # noqa: BLE001 — watcher must not die
            log.debug("omarchy-watch startup rebind failed: %s", e)
        time.sleep(_STARTUP_RETRY_S)
    return False


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


def watch_loop(
    *, once_socket: Path | None = None, startup: bool = True
) -> int:
    """Block, reading Hyprland events until the socket goes away (then retry)."""
    _write_own_pid()
    if startup and once_socket is None:
        try:
            startup_rebind()
        except Exception as e:  # noqa: BLE001 — watcher must not die
            log.debug("omarchy-watch startup rebind crashed: %s", e)
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
