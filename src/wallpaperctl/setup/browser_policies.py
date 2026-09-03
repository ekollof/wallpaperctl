"""Create managed-policy directories for Chromium-family browsers.

``BrowserThemeColor`` / ``BrowserColorScheme`` policies (theme/browser.py)
must live under /etc, so the directories are created once with privilege
escalation (sudo, doas, or pkexec) and chowned to the invoking user so
later theme applies never need to escalate again.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from wallpaperctl.theme.browser import BROWSER_POLICY_DIRS
from wallpaperctl.util import have, run


def escalation_prefix() -> list[str]:
    for cmd in ("sudo", "doas", "pkexec"):
        if have(cmd):
            return [cmd]
    return []


def browser_policy_status() -> dict:
    dirs = {
        d: {
            "exists": Path(d).is_dir(),
            "writable": os.access(d, os.W_OK),
        }
        for d in BROWSER_POLICY_DIRS
    }
    active = [d for d, v in dirs.items() if v["exists"] and v["writable"]]
    return {"dirs": dirs, "active": active, "ready": bool(active)}


def install_browser_policies(*, yes: bool = False) -> int:
    ready, missing = [], []
    for d in BROWSER_POLICY_DIRS:
        if Path(d).is_dir() and os.access(d, os.W_OK):
            ready.append(d)
        else:
            missing.append(d)

    if ready:
        print(f"already writable: {', '.join(ready)}")
    if not missing:
        print("Browser policy directories ready.")
        return 0

    prefix = escalation_prefix()
    if not prefix:
        print("No privilege escalation helper found (sudo, doas, or pkexec).")
        print("Create these directories manually and chown them to your user:")
        for d in missing:
            print(f"  {d}")
        return 1

    if not yes and sys.stdin.isatty():
        try:
            answer = input(
                f"Create {len(missing)} browser policy director"
                f"{'y' if len(missing) == 1 else 'ies'} with {prefix[0]}? [y/N] "
            ).strip().lower()
        except EOFError:
            answer = "n"
        if answer not in ("y", "yes"):
            print("Cancelled.")
            return 1

    uid = os.getuid() if hasattr(os, "getuid") else None
    gid = os.getgid() if hasattr(os, "getgid") else None
    owner = f"{uid}:{gid}" if uid is not None and gid is not None else None

    for d in missing:
        print(f"creating: {d} (via {prefix[0]})")
        r = run([*prefix, "mkdir", "-p", d], timeout=30)
        if r.returncode != 0:
            print(f"  failed: {(r.stderr or '').strip()}")
            continue
        if owner:
            run([*prefix, "chown", owner, d], timeout=30)

    still_missing = [
        d for d in missing
        if not (Path(d).is_dir() and os.access(d, os.W_OK))
    ]
    if still_missing:
        print(f"Could not create: {', '.join(still_missing)}")
        return 1
    print("Browser policy directories ready — theme applies now tint Brave/Chromium.")
    return 0
