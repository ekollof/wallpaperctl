"""CDE (Common Desktop Environment) color palette from wallust.

Writes ``~/.dt/palettes/Wallpaperctl.dp`` (8× ``#rrrrggggbbbb``), points the
session ``ColorPalette`` resource at it, merges via ``xrdb``, and optionally
soft-restarts ``dtwm`` so the workspace manager picks up chrome without a
full logout.

**Reload limits (CDE/Motif, not us):** Style Manager itself documents that a
*new* palette takes effect at the next session for full Motif color sets.
``dtstyle`` can live-``XStoreColors`` only on cells it already owns. We:

- Always update the ``.dp`` + session resources (next login / new Motif apps)
- Merge background/foreground into the resource manager (X11 clients now)
- Ensure ``dtwm`` is running; ask it to ``f.restart -noconfirm`` via the
  official ``_DT_WM_REQUEST`` X property (same as Style Manager). **Never
  SIGTERM dtwm** — session manager often will not respawn it.

Already-running Motif apps keep their colors until they restart. Full Motif
palette apply is still “next session” per CDE docs.
"""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path

from wallpaperctl.context import WallpaperContext
from wallpaperctl.theme.base import debug_op
from wallpaperctl.util import have, hex_to_rgb, home, read_wal_colors, run, spawn_detached

log = logging.getLogger("wallpaperctl")

PALETTE_NAME = "Wallpaperctl.dp"
_PALETTE_REL = Path(".dt/palettes") / PALETTE_NAME
_SESSION_CURRENT = Path(".dt/sessions/current/dt.resources")
_SESSION_HOME = Path(".dt/sessions/home/dt.resources")
_DTWM_RELOAD_STAMP = Path(".cache/wallpaperctl/cde-dtwm-reload")
_DTWM_RELOAD_MIN_INTERVAL = 30.0
_DTWM_BIN = Path("/usr/dt/bin/dtwm")
# Official dtwm request protocol (see libDtSvc WmRestart.c / Wsm.h)
_DT_WM_REQUEST = "_DT_WM_REQUEST"
_DTWM_REQ_RESTART = "f.restart"
_DTWM_REQP_NO_CONFIRM = "-noconfirm"

# Map wallust colors[0..15] → CDE palette slots 0..7 (bg / accents).
# Slot 0 is the primary workspace / window background tone.
_SLOT_FROM_WAL = (0, 1, 2, 3, 4, 5, 6, 7)


def hex_to_cde_rgb(hex_color: str) -> str:
    """Convert ``#rrggbb`` to CDE 16-bit palette form ``#rrrrggggbbbb``."""
    r, g, b = hex_to_rgb(hex_color)
    return f"#{r:02x}{r:02x}{g:02x}{g:02x}{b:02x}{b:02x}"


def build_cde_palette_lines(colors: list[str]) -> list[str]:
    """Build 8 CDE palette lines from wallust colors."""
    if len(colors) < 8:
        raise ValueError(f"need at least 8 wallust colors, got {len(colors)}")
    lines: list[str] = []
    for idx in _SLOT_FROM_WAL:
        c = colors[idx] if idx < len(colors) else colors[-1]
        lines.append(hex_to_cde_rgb(c))
    return lines


def write_cde_palette_file(colors: list[str], path: Path | None = None) -> Path:
    dest = path or (home() / _PALETTE_REL)
    dest.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(build_cde_palette_lines(colors)) + "\n"
    dest.write_text(body, encoding="utf-8")
    return dest


def _update_color_palette_line(text: str, palette_name: str = PALETTE_NAME) -> str:
    """Set or insert ``*0*ColorPalette`` / ``*ColorPalette`` lines."""
    lines = text.splitlines()
    out: list[str] = []
    saw_screen = False
    saw_global = False
    for line in lines:
        if re.match(r"^\s*\*0\*ColorPalette\s*:", line):
            out.append(f"*0*ColorPalette:\t{palette_name}")
            saw_screen = True
        elif re.match(r"^\s*\*ColorPalette\s*:", line):
            out.append(f"*ColorPalette:\t{palette_name}")
            saw_global = True
        else:
            out.append(line)
    if not saw_screen:
        out.insert(0, f"*0*ColorPalette:\t{palette_name}")
    if not saw_global:
        # Prefer after ColorUse if present
        inserted = False
        for i, line in enumerate(out):
            if re.match(r"^\s*\*?ColorUse\s*:", line):
                out.insert(i + 1, f"*ColorPalette:\t{palette_name}")
                inserted = True
                break
        if not inserted:
            out.append(f"*ColorPalette:\t{palette_name}")
    return "\n".join(out) + ("\n" if text.endswith("\n") or not text else "\n")


def update_session_resources(
    palette_name: str = PALETTE_NAME,
    *,
    paths: list[Path] | None = None,
) -> list[Path]:
    """Patch ColorPalette in session ``dt.resources`` files."""
    targets = paths or [
        home() / _SESSION_CURRENT,
        home() / _SESSION_HOME,
    ]
    written: list[Path] = []
    for path in targets:
        if not path.is_file():
            continue
        try:
            old = path.read_text(encoding="utf-8", errors="replace")
            new = _update_color_palette_line(old, palette_name)
            if new != old:
                path.write_text(new, encoding="utf-8")
            written.append(path)
        except OSError as e:
            log.warning("Could not update %s: %s", path, e)
    return written


def merge_cde_xrdb(colors: list[str], palette_name: str = PALETTE_NAME) -> bool:
    """Merge ColorPalette + bg/fg into the X resource manager."""
    if not have("xrdb"):
        return False
    bg = colors[0]
    fg = colors[7] if len(colors) > 7 else colors[-1]
    # Also seed Motif-ish globals so new clients look less wrong.
    blob = "\n".join(
        [
            f"*0*ColorPalette:\t{palette_name}",
            f"*ColorPalette:\t{palette_name}",
            f"*background:\t{bg}",
            f"*foreground:\t{fg}",
            f"Dtsession*0*ColorPalette:\t{palette_name}",
            "",
        ]
    )
    r = run(["xrdb", "-merge"], input_text=blob, timeout=10)
    return r.returncode == 0


def _dtwm_reload_allowed() -> bool:
    stamp = home() / _DTWM_RELOAD_STAMP
    try:
        if stamp.is_file():
            age = time.time() - stamp.stat().st_mtime
            if age < _DTWM_RELOAD_MIN_INTERVAL:
                return False
    except OSError:
        pass
    return True


def _mark_dtwm_reload() -> None:
    stamp = home() / _DTWM_RELOAD_STAMP
    try:
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(f"{time.time():.0f}\n", encoding="utf-8")
    except OSError:
        pass


def _dtwm_running() -> bool:
    if not have("pgrep"):
        return False
    return run(["pgrep", "-x", "dtwm"], timeout=3).returncode == 0


def _start_dtwm() -> bool:
    """Start dtwm if missing (e.g. after a bad kill). Prefer official binary."""
    if _dtwm_running():
        return True
    bin_path = _DTWM_BIN if _DTWM_BIN.is_file() else None
    if bin_path is None and have("dtwm"):
        from wallpaperctl.util import which

        w = which("dtwm")
        bin_path = Path(w) if w else None
    if bin_path is None:
        log.warning("dtwm binary not found; cannot start workspace manager")
        return False
    if spawn_detached([str(bin_path)], env=os.environ.copy()) is None:
        log.warning("Failed to start dtwm")
        return False
    for _ in range(40):
        time.sleep(0.15)
        if _dtwm_running():
            time.sleep(0.4)  # let it claim _MOTIF_WM_INFO
            return True
    return _dtwm_running()


def _x11_dtwm_restart_request() -> bool:
    """Ask dtwm to restart via ``_DT_WM_REQUEST`` = ``f.restart -noconfirm``.

    This is what Style Manager / ``_DtWmRestartNoConfirm`` does. Do **not**
    SIGTERM dtwm — dtsession often does not respawn it, leaving no WM.
    """
    try:
        import ctypes
        import ctypes.util
    except ImportError:
        return False

    lib = ctypes.util.find_library("X11")
    if not lib:
        return False
    x11 = ctypes.CDLL(lib)

    Display = ctypes.c_void_p
    Window = ctypes.c_ulong
    Atom = ctypes.c_ulong
    Bool = ctypes.c_int
    Status = ctypes.c_int

    ErrorHandler = ctypes.CFUNCTYPE(ctypes.c_int, Display, ctypes.c_void_p)

    @ErrorHandler
    def _ignore_xerror(_dpy: object, _ev: object) -> int:
        return 0

    x11.XSetErrorHandler(_ignore_xerror)
    x11.XOpenDisplay.restype = Display
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XDefaultRootWindow.restype = Window
    x11.XDefaultRootWindow.argtypes = [Display]
    x11.XInternAtom.restype = Atom
    x11.XInternAtom.argtypes = [Display, ctypes.c_char_p, Bool]
    x11.XGetWindowProperty.restype = Status
    x11.XGetWindowProperty.argtypes = [
        Display,
        Window,
        Atom,
        ctypes.c_long,
        ctypes.c_long,
        Bool,
        Atom,
        ctypes.POINTER(Atom),
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte)),
    ]
    x11.XChangeProperty.restype = ctypes.c_int
    x11.XChangeProperty.argtypes = [
        Display,
        Window,
        Atom,
        Atom,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_int,
    ]
    x11.XFlush.argtypes = [Display]
    x11.XSync.argtypes = [Display, Bool]
    x11.XFree.argtypes = [ctypes.c_void_p]
    x11.XCloseDisplay.argtypes = [Display]
    x11.XGetWindowAttributes.restype = Status
    x11.XGetWindowAttributes.argtypes = [Display, Window, ctypes.c_void_p]

    AnyPropertyType = 0
    PropModeAppend = 2

    dpy = x11.XOpenDisplay(None)
    if not dpy:
        return False
    try:
        root = x11.XDefaultRootWindow(dpy)
        mwm_info = x11.XInternAtom(dpy, b"_MOTIF_WM_INFO", 0)
        actual_type = Atom()
        actual_format = ctypes.c_int()
        nitems = ctypes.c_ulong()
        bytes_after = ctypes.c_ulong()
        prop = ctypes.POINTER(ctypes.c_ubyte)()
        st = x11.XGetWindowProperty(
            dpy,
            root,
            mwm_info,
            0,
            2,
            0,
            AnyPropertyType,
            ctypes.byref(actual_type),
            ctypes.byref(actual_format),
            ctypes.byref(nitems),
            ctypes.byref(bytes_after),
            ctypes.byref(prop),
        )
        if st != 0 or not prop or nitems.value < 2:
            return False
        # format 32 → long-sized cells (8 bytes on LP64)
        arr = ctypes.cast(prop, ctypes.POINTER(ctypes.c_ulong))
        wm_win = int(arr[1])
        x11.XFree(prop)
        if not wm_win:
            return False

        attr_buf = ctypes.create_string_buffer(512)
        if x11.XGetWindowAttributes(dpy, Window(wm_win), attr_buf) == 0:
            x11.XSync(dpy, 0)
            return False
        x11.XSync(dpy, 0)

        req_atom = x11.XInternAtom(dpy, _DT_WM_REQUEST.encode(), 0)
        xa_string = x11.XInternAtom(dpy, b"STRING", 0)
        # C: "f.restart -noconfirm" + NUL (len = strlen+1)
        msg = f"{_DTWM_REQ_RESTART} {_DTWM_REQP_NO_CONFIRM}".encode()
        payload = msg + b"\0"
        buf = ctypes.create_string_buffer(payload)
        x11.XChangeProperty(
            dpy,
            Window(wm_win),
            req_atom,
            xa_string,
            8,
            PropModeAppend,
            buf,
            len(payload),
        )
        x11.XFlush(dpy)
        x11.XSync(dpy, 0)
        return True
    finally:
        x11.XCloseDisplay(dpy)


def soft_restart_dtwm() -> str | None:
    """Restart or ensure dtwm without full logout. Never SIGTERM.

    Uses the official ``_DT_WM_REQUEST`` / ``f.restart -noconfirm`` protocol
    (same as Style Manager). If dtwm is not running, starts ``/usr/dt/bin/dtwm``.
    """
    if not _dtwm_reload_allowed():
        return "dtwm cooldown"

    if not _dtwm_running():
        if _start_dtwm():
            _mark_dtwm_reload()
            return "dtwm started"
        return "dtwm missing (start failed)"

    if _x11_dtwm_restart_request():
        _mark_dtwm_reload()
        # Give dtwm a moment to exec; do not kill if it keeps the same PID
        # (in-place restart via execvp can race).
        time.sleep(0.5)
        if not _dtwm_running():
            # Restart consumed the process and failed to re-exec — recover
            if _start_dtwm():
                return "dtwm restart request + recovered"
            return "dtwm restart request (wm exited)"
        return "dtwm f.restart -noconfirm"

    log.debug("Could not send dtwm f.restart via X11 property")
    return "dtwm restart unavailable"


def apply_cde_palette(
    colors: list[str],
    *,
    restart_dtwm: bool = True,
) -> tuple[bool, str]:
    """Write palette, patch session resources, merge xrdb, optional dtwm bounce."""
    if len(colors) < 8:
        return False, f"need ≥8 colors, got {len(colors)}"
    try:
        pal = write_cde_palette_file(colors)
    except (OSError, ValueError) as e:
        return False, str(e)

    sess = update_session_resources(PALETTE_NAME)
    xrdb_ok = merge_cde_xrdb(colors, PALETTE_NAME)
    parts = [f"palette → {pal.name}"]
    if sess:
        parts.append(f"session files {len(sess)}")
    parts.append("xrdb ok" if xrdb_ok else "xrdb skip/fail")

    if restart_dtwm:
        dtwm = soft_restart_dtwm()
        if dtwm:
            parts.append(dtwm)

    return True, "; ".join(parts)


class CdeThemeOp:
    """Generate CDE Style Manager palette from wallust."""

    name = "cde-theme"

    def enabled(self, ctx: WallpaperContext) -> bool:
        if not getattr(ctx.ops, "enable_cde_theme", True):
            return False
        if getattr(ctx.de, "cde", False):
            return True
        # Live dtwm even if DesktopEnvironment missed it
        return have("pgrep") and run(["pgrep", "-x", "dtwm"], timeout=3).returncode == 0

    def run(self, ctx: WallpaperContext) -> bool:
        colors = read_wal_colors()
        if len(colors) < 8:
            debug_op(self.name, "not enough wal colors (run wallust first)", ctx)
            return True  # soft skip

        restart = bool(getattr(ctx.ops, "cde_restart_dtwm", True))
        ok, detail = apply_cde_palette(colors, restart_dtwm=restart)
        debug_op(self.name, detail, ctx)
        if not ok:
            log.warning("CDE theme: %s", detail)
            return False
        log.debug("CDE theme: %s", detail)
        return True
