"""Package-manager detection and install helpers."""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass

from wallpaperctl.setup.deps import Dep, DepStatus


@dataclass
class PackageManager:
    id: str  # pacman | apt | dnf | freebsd_pkg | openbsd_pkg
    name: str
    install_cmd: list[str]  # prefix, packages appended


def detect_package_manager() -> PackageManager | None:
    if shutil.which("pacman"):
        # Prefer paru/yay for AUR (wallust-git) when available
        if shutil.which("paru"):
            return PackageManager(
                "pacman",
                "paru (pacman/AUR)",
                ["paru", "-S", "--needed", "--noconfirm"],
            )
        if shutil.which("yay"):
            return PackageManager(
                "pacman",
                "yay (pacman/AUR)",
                ["yay", "-S", "--needed", "--noconfirm"],
            )
        return PackageManager(
            "pacman",
            "pacman",
            ["sudo", "pacman", "-S", "--needed", "--noconfirm"],
        )
    if shutil.which("apt-get"):
        return PackageManager(
            "apt",
            "apt",
            ["sudo", "apt-get", "install", "-y"],
        )
    if shutil.which("dnf"):
        return PackageManager(
            "dnf",
            "dnf",
            ["sudo", "dnf", "install", "-y"],
        )
    if sys.platform.startswith("freebsd") and shutil.which("pkg"):
        return PackageManager(
            "freebsd_pkg",
            "pkg (FreeBSD)",
            ["sudo", "pkg", "install", "-y"],
        )
    if sys.platform.startswith("openbsd") and shutil.which("pkg_add"):
        return PackageManager(
            "openbsd_pkg",
            "pkg_add (OpenBSD)",
            ["doas", "pkg_add"],
        )
    return None


def packages_to_install(
    statuses: list[DepStatus],
    pm: PackageManager,
    *,
    missing_only: bool = True,
    relevant_only: bool = True,
    include_optional: bool = False,
) -> list[tuple[Dep, str]]:
    """Return (dep, package_name) pairs to install."""
    out: list[tuple[Dep, str]] = []
    seen: set[str] = set()
    for st in statuses:
        if relevant_only and not st.relevant:
            continue
        if missing_only and st.present:
            continue
        if not include_optional and st.dep.kind.value == "optional" and not st.required:
            # still allow theme (wallust) as recommended
            if st.dep.id != "wallust":
                continue
        if st.dep.kind.value == "python":
            # python deps come via pip/uv of wallpaperctl itself
            continue
        pkg = st.dep.package_for(pm.id)
        if not pkg:
            continue
        if pkg in seen:
            continue
        seen.add(pkg)
        out.append((st.dep, pkg))
    return out


def install_system_packages(
    pairs: list[tuple[Dep, str]],
    pm: PackageManager,
    *,
    yes: bool = False,
) -> int:
    if not pairs:
        print("Nothing to install via system package manager.")
        return 0
    pkgs = [p for _, p in pairs]
    print(f"Package manager: {pm.name}")
    print("Will install:")
    for dep, pkg in pairs:
        print(f"  - {pkg}  ({dep.id}: {dep.description})")
    if not yes:
        try:
            ans = input("Proceed? [y/N] ").strip().lower()
        except EOFError:
            ans = "n"
        if ans not in ("y", "yes"):
            print("Cancelled.")
            return 1
    cmd = pm.install_cmd + pkgs
    print("+", " ".join(cmd))
    import subprocess

    try:
        proc = subprocess.run(cmd, check=False)
        return proc.returncode
    except FileNotFoundError as e:
        print(f"Failed: {e}", file=sys.stderr)
        return 1


def install_python_extras(*, yes: bool = False) -> int:
    """Ensure wallpaperctl Python deps via the current interpreter."""
    import subprocess
    import sys

    mods = ["PIL", "imagehash", "httpx", "jeepney"]
    missing = []
    for m in mods:
        try:
            __import__("PIL" if m == "PIL" else m)
        except ImportError:
            missing.append(
                {"PIL": "Pillow", "imagehash": "imagehash", "httpx": "httpx", "jeepney": "jeepney"}[
                    m
                ]
            )
    if not missing:
        print("Python packages: all present.")
        return 0
    print("Missing Python packages:", ", ".join(missing))
    print(f"Install into: {sys.executable}")
    if not yes:
        try:
            ans = input("Install with pip? [y/N] ").strip().lower()
        except EOFError:
            ans = "n"
        if ans not in ("y", "yes"):
            print("Cancelled. Or reinstall: pipx install --force wallpaperctl")
            return 1
    cmd = [sys.executable, "-m", "pip", "install", *missing]
    print("+", " ".join(cmd))
    return subprocess.run(cmd, check=False).returncode
