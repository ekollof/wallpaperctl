"""COSMIC desktop wallpaper via CosmicBackground config + state.

``cosmic-bg`` (session) reads config ``v1/all``. ``cosmic-greeter`` (lock)
reads state ``v1/wallpapers`` and matches **exact** Wayland output names.

## Why lock wallpaper is hard

1. **Inotify:** ``cosmic-config`` ignores ``RenameMode::Both`` (temp+rename).
   We write state **in place** so greeter sees ``MODIFY``.

2. **Greeter bug after unlock:** On unlock, greeter drops ``surface_names``
   but keeps ``surface_images``. A later ``BackgroundState`` (from our
   state write) does ``surface_images.clear()`` then ``update_wallpapers``,
   which needs ``surface_names`` → no-op. Next lock never repopulates
   images → **embedded default nebula forever**.

3. **No D-Bus reload** for session greeter. The only reliable refresh when
   unlocked is a **rate-limited** soft restart (``cosmic-session`` respawns
   greeter). We never kill while the session is locked, and we throttle
   restarts so session backoff does not explode.
"""

from __future__ import annotations

import logging
import os
import re
import signal
import time
from pathlib import Path

from wallpaperctl.context import WallpaperContext
from wallpaperctl.set.base import debug_set
from wallpaperctl.util import have, home, run

log = logging.getLogger("wallpaperctl")

_CONFIG_DIR = "com.system76.CosmicBackground"
_STATE_REL = Path(".local/state/cosmic") / _CONFIG_DIR / "v1"
_CONFIG_REL = Path(".config/cosmic") / _CONFIG_DIR / "v1"
_OUTPUTS_RON = Path(".local/state/cosmic-comp/outputs.ron")
# Rate-limit greeter restarts. cosmic-session uses exponential backoff on
# rapid greeter deaths; stay well above that thrash window.
_GREETER_RELOAD_MIN_INTERVAL = 90.0
_RELOAD_STAMP = Path(".cache/wallpaperctl/cosmic-greeter-reload")

_CONN_RE = re.compile(r'connector:\s*"([^"]+)"')
_STATE_OUT_RE = re.compile(r'\(\s*"([^"]+)"\s*,')
_RANDR_OUT_RE = re.compile(r"^(\S+)\s+\(enabled\)\s*$", re.MULTILINE)


def _ron_path(path: Path) -> str:
    s = str(path.resolve())
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _write_watched(path: Path, text: str) -> None:
    """In-place write so cosmic-config notify sees data changes (not rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    with open(path, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def discover_cosmic_outputs() -> list[str]:
    """Union of live outputs, cosmic-comp history, and existing state keys."""
    names: set[str] = set()

    if have("cosmic-randr"):
        r = run(["cosmic-randr", "list"], timeout=5)
        if r.returncode == 0 and r.stdout:
            names.update(_RANDR_OUT_RE.findall(r.stdout))
            for line in r.stdout.splitlines():
                line = line.strip()
                if " (enabled)" in line:
                    names.add(line.split(" (enabled)", 1)[0].strip())

    if have("wlr-randr"):
        r = run(["wlr-randr"], timeout=5)
        if r.returncode == 0 and r.stdout:
            for line in r.stdout.splitlines():
                if not line or line[0].isspace():
                    continue
                tok = line.split()[0]
                if tok and not tok.startswith('"'):
                    names.add(tok)

    ron = home() / _OUTPUTS_RON
    if ron.is_file():
        try:
            names.update(_CONN_RE.findall(ron.read_text(encoding="utf-8", errors="replace")))
        except OSError as e:
            log.debug("Could not read cosmic-comp outputs: %s", e)

    state_file = home() / _STATE_REL / "wallpapers"
    if state_file.is_file():
        try:
            names.update(
                _STATE_OUT_RE.findall(
                    state_file.read_text(encoding="utf-8", errors="replace")
                )
            )
        except OSError:
            pass

    return sorted(n for n in names if n and n != "all")


def write_cosmic_background_config(wallpaper: Path) -> Path:
    cfg = home() / _CONFIG_REL
    cfg.mkdir(parents=True, exist_ok=True)
    rp = _ron_path(wallpaper)
    _write_watched(
        cfg / "all",
        "\n".join(
            [
                "(",
                '    output: "all",',
                f'    source: Path("{rp}"),',
                "    filter_by_theme: true,",
                "    rotation_frequency: 300,",
                "    filter_method: Lanczos,",
                "    scaling_mode: Zoom,",
                "    sampling_method: Alphanumeric,",
                ")",
                "",
            ]
        ),
    )
    _write_watched(cfg / "same-on-all", "true\n")
    return cfg / "all"


def write_cosmic_background_state(wallpaper: Path) -> Path | None:
    state_dir = home() / _STATE_REL
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / "wallpapers"
    rp = _ron_path(wallpaper)

    outputs = discover_cosmic_outputs()
    if not outputs:
        outputs = ["all"]

    lines = ["["]
    for name in outputs:
        safe = name.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'    ("{safe}", Path("{rp}")),')
    lines.append("]")
    lines.append("")
    try:
        _write_watched(state_file, "\n".join(lines))
    except OSError as e:
        log.warning("Could not write cosmic-bg state: %s", e)
        return None
    log.debug(
        "Wrote cosmic-bg state for %d output(s): %s",
        len(outputs),
        ", ".join(outputs[:12]) + ("…" if len(outputs) > 12 else ""),
    )
    return state_file


def _session_locked() -> bool:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    session = os.environ.get("XDG_SESSION_ID")
    if not runtime or not session:
        return False
    return Path(runtime, f"cosmic-greeter-{session}.lock").is_file()


def _pids_exact(name: str) -> list[int]:
    if not have("pgrep"):
        return []
    r = run(["pgrep", "-x", name], timeout=5)
    if r.returncode != 0 or not r.stdout.strip():
        return []
    return [int(x) for x in r.stdout.split() if x.isdigit()]


def _greeter_reload_allowed() -> bool:
    stamp = home() / _RELOAD_STAMP
    try:
        if stamp.is_file():
            age = time.time() - stamp.stat().st_mtime
            if age < _GREETER_RELOAD_MIN_INTERVAL:
                log.debug(
                    "Skip greeter reload (%.0fs < %.0fs cooldown)",
                    age,
                    _GREETER_RELOAD_MIN_INTERVAL,
                )
                return False
    except OSError:
        pass
    return True


def _mark_greeter_reload() -> None:
    stamp = home() / _RELOAD_STAMP
    try:
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(f"{time.time():.0f}\n", encoding="utf-8")
    except OSError as e:
        log.debug("Could not write greeter reload stamp: %s", e)


def reload_cosmic_greeter(*, force: bool = False) -> str | None:
    """Rate-limited soft-restart of session greeter so lock images reload.

    Required after unlock: greeter clears surface_names; a state-file notify
    then clears surface_images with no way to repopulate until process restart.
    """
    if _session_locked():
        log.debug("Session locked — not restarting greeter")
        return "locked (state written; applies after unlock/reload)"
    if not force and not _greeter_reload_allowed():
        return "cooldown"

    pids = _pids_exact("cosmic-greeter")
    if not pids:
        # Greeter may be in cosmic-session backoff sleep; do not spam kills.
        log.debug("No cosmic-greeter process (session may be restarting it)")
        return "greeter not running"

    sent = 0
    uid = os.getuid()
    old = set(pids)
    for pid in pids:
        try:
            if os.stat(f"/proc/{pid}").st_uid != uid:
                continue
            age = time.time() - os.stat(f"/proc/{pid}").st_mtime
            if age < 5.0:
                log.debug("Greeter pid %s too young (%.1fs), skip", pid, age)
                continue
            os.kill(pid, signal.SIGTERM)
            sent += 1
        except (ProcessLookupError, PermissionError, FileNotFoundError) as e:
            log.debug("Could not signal greeter %s: %s", pid, e)

    if not sent:
        return None

    _mark_greeter_reload()
    # Wait briefly for respawn so the next wallpaperctl run does not pile on.
    deadline = time.time() + 15.0
    while time.time() < deadline:
        time.sleep(0.4)
        now = set(_pids_exact("cosmic-greeter"))
        if now and now != old:
            log.debug("cosmic-greeter respawned: %s", now)
            return f"greeter reload ({sent})"
    log.debug("cosmic-greeter not seen after SIGTERM (session backoff?)")
    return f"greeter reload ({sent}, waiting on session)"


def sync_cosmic_wallpaper(
    wallpaper: Path, *, reload_greeter: bool = True
) -> tuple[bool, str]:
    """Write config + state; optionally rate-limit-restart greeter when unlocked."""
    if not wallpaper.is_file():
        return False, f"not a file: {wallpaper}"
    try:
        write_cosmic_background_config(wallpaper)
        st = write_cosmic_background_state(wallpaper)
        detail = (
            f"config+state → {wallpaper.name}"
            if st is not None
            else f"config only → {wallpaper.name}"
        )
        if reload_greeter:
            # Brief pause so inotify/BackgroundState is processed before we
            # replace the process (avoids racing a dying greeter).
            time.sleep(0.15)
            g = reload_cosmic_greeter()
            if g:
                detail = f"{detail}; {g}"
        return True, detail
    except OSError as e:
        return False, str(e)


class CosmicSetter:
    """Apply wallpaper for System76 COSMIC (session + lock/greeter state)."""

    name = "cosmic"

    def applies(self, ctx: WallpaperContext) -> bool:
        if getattr(ctx.de, "cosmic", False):
            return True
        return (home() / ".config/cosmic" / _CONFIG_DIR).is_dir()

    def set_wallpaper(self, ctx: WallpaperContext) -> bool:
        path = ctx.path.resolve()
        # Theme op will call sync again; only reload greeter once at end of
        # theme when that op is enabled.
        theme_next = bool(getattr(ctx.ops, "enable_cosmic_theme", True))
        ok, detail = sync_cosmic_wallpaper(path, reload_greeter=not theme_next)
        if ok:
            debug_set(self.name, detail, ctx)
        else:
            debug_set(self.name, f"failed: {detail}", ctx)
        return ok
