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


def log_error(msg: str) -> None:
    log.error(msg)
    err_file = home() / ".wallpaper_errors.log"
    try:
        from datetime import datetime

        line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] ERROR: {msg}\n"
        with err_file.open("a", encoding="utf-8") as f:
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
