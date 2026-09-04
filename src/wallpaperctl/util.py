"""Portable helpers (Linux / OpenBSD / FreeBSD)."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

log = logging.getLogger("wallpaperctl")


def home() -> Path:
    return Path.home()


def which(cmd: str) -> str | None:
    return shutil.which(cmd)


def have(cmd: str) -> bool:
    return which(cmd) is not None


def spawn_detached(
    args: Sequence[str],
    *,
    env: dict[str, str] | None = None,
) -> subprocess.Popen[bytes] | None:
    """Start a long-lived helper fully detached from the caller's TTY.

    Daemons like ``xsettingsd`` never exit. If they inherit the interactive
    shell's stdin, zsh/bash can appear hung after wallpaperctl returns even
    when the child is in a new session. Always wire stdio to DEVNULL and
    call ``setsid`` via ``start_new_session``.
    """
    try:
        return subprocess.Popen(
            list(args),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
            env=env,
        )
    except OSError as e:
        log.debug("spawn_detached %s failed: %s", args, e)
        return None


def run(
    args: Sequence[str] | str,
    *,
    check: bool = False,
    capture: bool = True,
    timeout: float | None = 60,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
    cwd: str | Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command; never raise unless check=True."""
    if isinstance(args, str):
        cmd: Sequence[str] | str = args
        shell = True
    else:
        cmd = list(args)
        shell = False
    try:
        return subprocess.run(
            cmd,
            shell=shell,
            check=check,
            capture_output=capture,
            text=True,
            timeout=timeout,
            env=env,
            input=input_text,
            cwd=cwd,
        )
    except FileNotFoundError as e:
        return subprocess.CompletedProcess(
            args=cmd if not shell else [str(cmd)],
            returncode=127,
            stdout="",
            stderr=str(e),
        )
    except subprocess.TimeoutExpired as e:
        return subprocess.CompletedProcess(
            args=cmd if not shell else [str(cmd)],
            returncode=124,
            stdout=(e.stdout or "") if isinstance(e.stdout, str) else "",
            stderr=f"timeout after {timeout}s",
        )


def pgrep_exact(name: str) -> bool:
    """True if a process with exact comm name is running (portable)."""
    # pgrep -x is available on Linux and BSDs
    if have("pgrep"):
        r = run(["pgrep", "-x", name], timeout=5)
        return r.returncode == 0
    # Fallback: scan /proc if present
    proc = Path("/proc")
    if not proc.is_dir():
        return False
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            comm = (entry / "comm").read_text().strip()
        except OSError:
            continue
        if comm == name:
            return True
    return False


def pgrep_full(pattern: str) -> bool:
    """True if any process cmdline matches pattern (pgrep -f)."""
    if have("pgrep"):
        r = run(["pgrep", "-f", pattern], timeout=5)
        return r.returncode == 0
    return False


_WM_NAME_CACHE: dict[str, str] = {}


def wm_x11_name() -> str:
    """Name of the running X11 window manager ("" when unknown).

    Reads WM_NAME off the _NET_SUPPORTING_WM_CHECK client window. Lets
    callers special-case WMs with known quirks (e.g. EXWM vs xwinwrap).
    """
    if "wm" in _WM_NAME_CACHE:
        return _WM_NAME_CACHE["wm"]
    name = ""
    if have("xprop"):
        r = run(
            ["xprop", "-root", "-notype", "_NET_SUPPORTING_WM_CHECK"], timeout=5
        )
        match = re.search(r"window id #\s*(0x[0-9a-fA-F]+)", r.stdout)
        if r.returncode == 0 and match:
            probe = run(
                ["xprop", "-id", match.group(1), "-notype", "_NET_WM_NAME"],
                timeout=5,
            )
            quoted = re.search(r'_NET_WM_NAME[^=]*=\s*"([^"]*)"', probe.stdout)
            if probe.returncode == 0 and quoted:
                name = quoted.group(1)
    _WM_NAME_CACHE["wm"] = name
    log.debug("Detected X11 window manager: %s", name or "(unknown)")
    return name


def reset_wm_name_cache() -> None:
    """Forget cached WM detection (tests, WM switches mid-process)."""
    _WM_NAME_CACHE.clear()


def sanitize_string(s: str) -> str:
    s = s.replace("\n", "").replace("/", "").replace("@", "")
    s = s.replace(" ", "_")
    return re.sub(r"[^a-zA-Z0-9_,_-]", "", s)


def url_encode_spaces(s: str) -> str:
    return s.replace(" ", "%20")


def create_temp_file(prefix: str = "wallpaperctl") -> Path:
    fd, path = tempfile.mkstemp(prefix=f"{prefix}_")
    os.close(fd)
    p = Path(path)
    try:
        p.chmod(0o600)
    except OSError:
        pass
    return p


def ensure_debug_logging(enabled: bool) -> None:
    level = logging.DEBUG if enabled else logging.INFO
    root = logging.getLogger("wallpaperctl")
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        root.addHandler(handler)
    root.setLevel(level)


_QUERY_SECRET_RE = re.compile(r"(?i)([?&](?:key|access_key|api_key|token)=)[^&\s\"']+")


def redact_url_secrets(msg: str) -> str:
    """Mask query-string credentials (Pixabay key, tokens) before logging."""
    return _QUERY_SECRET_RE.sub(r"\1REDACTED", msg)


def log_error(msg: str) -> None:
    msg = redact_url_secrets(msg)
    log.error(msg)
    err_file = home() / ".wallpaper_errors.log"
    try:
        from datetime import datetime

        line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] ERROR: {msg}\n"
        fd = os.open(
            err_file, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600
        )
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"invalid hex color: {hex_color}")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def read_wal_colors(path: Path | None = None) -> list[str]:
    p = path or (home() / ".cache" / "wal" / "colors")
    if not p.is_file():
        return []
    colors: list[str] = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        c = line.strip()
        if not c:
            continue
        if not c.startswith("#"):
            c = f"#{c}"
        colors.append(c)
    return colors


def is_dark_theme_name(name: str) -> bool:
    return bool(re.search(r"(dark|darker|black)", name, re.I))
