"""KDE Plasma wallpaper via native session D-Bus + lockscreen config."""

from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path

from wallpaperctl.context import WallpaperContext
from wallpaperctl.dbus_session import call as dbus_call
from wallpaperctl.dbus_session import jeepney_available
from wallpaperctl.set.base import debug_set
from wallpaperctl.util import have, run

log = logging.getLogger("wallpaperctl")

PLASMA_BUS = "org.kde.plasmashell"
PLASMA_PATH = "/PlasmaShell"
PLASMA_IFACE = "org.kde.PlasmaShell"
WALLPAPER_PLUGIN = "org.kde.image"

# Animated wallpapers render with aspect-fit + black background on top of the
# org.kde.image plugin. These settings must not leak into later static
# wallpapers, so the previous values are saved once and restored on the next
# static apply.
_ANIMATED_OVERLAY_KEYS = ("FillMode", "Color", "Blur")
_ANIMATED_OVERLAY_DEFAULTS = {"FillMode": "2", "Color": "#ffffff", "Blur": "false"}
_ANIMATED_OVERLAY_STATE = Path("~/.cache/wallpaperctl/plasma-image-overlay").expanduser()
_IMAGE_SECTION_RE = re.compile(
    r"^\[Containments\]\[\d+\]\[Wallpaper\]\[org\.kde\.image\]\[General\]\s*$"
)


def _appletsrc_path() -> Path:
    return Path.home() / ".config" / "plasma-org.kde.plasma.desktop-appletsrc"


def _current_image_settings(cfg: Path) -> dict[str, str]:
    """First value per key under any containment's org.kde.image group."""
    values: dict[str, str] = {}
    try:
        lines = cfg.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return values
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("["):
            in_section = bool(_IMAGE_SECTION_RE.match(stripped))
            continue
        if in_section and "=" in stripped:
            key, _, value = stripped.partition("=")
            values.setdefault(key.strip(), value.strip())
    return values


def _save_animated_overlay_settings() -> None:
    """Remember pre-animated org.kde.image settings (once per animated run)."""
    if _ANIMATED_OVERLAY_STATE.exists():
        return
    current = _current_image_settings(_appletsrc_path())
    lines = [
        f"{key}={current.get(key, _ANIMATED_OVERLAY_DEFAULTS[key])}"
        for key in _ANIMATED_OVERLAY_KEYS
    ]
    try:
        _ANIMATED_OVERLAY_STATE.parent.mkdir(parents=True, exist_ok=True)
        _ANIMATED_OVERLAY_STATE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as e:
        log.debug("Could not save Plasma overlay settings: %s", e)


def _restore_animated_overlay_js() -> str:
    """JS restoring pre-animated settings; empty when nothing was saved."""
    try:
        text = _ANIMATED_OVERLAY_STATE.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    saved = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
    if not any(key in saved for key in _ANIMATED_OVERLAY_KEYS):
        return ""
    js = "".join(
        f'\n    d.writeConfig("{key}", "{saved[key]}");'
        for key in _ANIMATED_OVERLAY_KEYS
        if key in saved
    )
    try:
        _ANIMATED_OVERLAY_STATE.unlink(missing_ok=True)
    except OSError as e:
        log.debug("Could not clear Plasma overlay state: %s", e)
    return js


class PlasmaSetter:
    name = "plasma"

    def applies(self, ctx: WallpaperContext) -> bool:
        return ctx.de.plasma

    def set_wallpaper(self, ctx: WallpaperContext) -> bool:
        path = ctx.image_path.resolve()
        if not path.is_file():
            debug_set(self.name, f"file not found: {path}", ctx)
            return False
        if not jeepney_available():
            debug_set(self.name, "jeepney not available for Plasma D-Bus", ctx)
            return False

        ok = self._set_desktop(path, ctx)
        lock_ok = self._set_lockscreen(path, ctx)
        if not lock_ok:
            debug_set(self.name, "lockscreen wallpaper update failed", ctx)
        if ok and self._is_screen_locked():
            debug_set(
                self.name,
                "screen is locked — lockscreen wallpaper may not show until unlock",
                ctx,
            )
            log.info(
                "Plasma screen locked: lockscreen wallpaper updated but may not "
                "be visible until unlock"
            )
        return ok

    @staticmethod
    def _is_screen_locked() -> bool:
        """True if the session screensaver reports active (best-effort)."""
        for bus, path, iface in (
            ("org.freedesktop.ScreenSaver", "/ScreenSaver", "org.freedesktop.ScreenSaver"),
            ("org.kde.screensaver", "/ScreenSaver", "org.freedesktop.ScreenSaver"),
        ):
            ok, body = dbus_call(
                bus_name=bus,
                path=path,
                interface=iface,
                method="GetActive",
                signature="",
                body=(),
                timeout=1.0,
            )
            if ok and body:
                try:
                    return bool(body[0])
                except (IndexError, TypeError):
                    pass
        return False

    def _set_desktop(self, path: Path, ctx: WallpaperContext) -> bool:
        uri = path.as_uri()
        uri_js = uri.replace("\\", "\\\\").replace('"', '\\"')
        plugin = WALLPAPER_PLUGIN
        if ctx.is_animated:
            _save_animated_overlay_settings()
            overlay_js = (
                '\n    d.writeConfig("FillMode", 1);'
                '\n    d.writeConfig("Color", "#000000");'
                "\n    d.writeConfig(\"Blur\", false);"
            )
        else:
            overlay_js = _restore_animated_overlay_js()
        js = f"""
var allDesktops = desktops();
for (i = 0; i < allDesktops.length; i++) {{
    d = allDesktops[i];
    d.wallpaperPlugin = "{plugin}";
    d.currentConfigGroup = Array("Wallpaper", "{plugin}", "General");
    d.writeConfig("Image", "{uri_js}");
    d.writeConfig("PreviewImage", "{uri_js}");{overlay_js}
}}
"""
        ok, err = dbus_call(
            bus_name=PLASMA_BUS,
            path=PLASMA_PATH,
            interface=PLASMA_IFACE,
            method="evaluateScript",
            signature="s",
            body=(js,),
            timeout=15.0,
        )
        if ok:
            debug_set(self.name, "desktop wallpaper set via D-Bus", ctx)
            return True
        debug_set(self.name, f"evaluateScript failed: {err}", ctx)
        return False

    def _set_lockscreen(self, path: Path, ctx: WallpaperContext) -> bool:
        """
        Plasma 6 reads lock-screen wallpaper from kscreenlockerrc.

        Prefer kwriteconfig6 --notify so KConfig clients re-read the file.
        Image should be a file:// URI (same as desktop containments).
        """
        uri = path.as_uri()
        cfg = Path.home() / ".config" / "kscreenlockerrc"

        if have("kwriteconfig6"):
            if self._lockscreen_kwriteconfig(cfg, uri, ctx):
                return True
            debug_set(self.name, "kwriteconfig6 failed; falling back to file edit", ctx)

        return self._lockscreen_file_edit(cfg, path, uri, ctx)

    def _lockscreen_kwriteconfig(
        self, cfg: Path, uri: str, ctx: WallpaperContext
    ) -> bool:
        cfg.parent.mkdir(parents=True, exist_ok=True)
        groups = [
            "--group",
            "Greeter",
            "--group",
            "Wallpaper",
            "--group",
            WALLPAPER_PLUGIN,
            "--group",
            "General",
        ]
        base = ["kwriteconfig6", "--file", str(cfg), "--notify"]

        cmds = [
            base
            + ["--group", "Greeter", "--key", "WallpaperPlugin", WALLPAPER_PLUGIN],
            base + groups + ["--key", "Image", uri],
            base + groups + ["--key", "PreviewImage", uri],
        ]
        all_ok = True
        for cmd in cmds:
            r = run(cmd, timeout=10)
            if r.returncode != 0:
                debug_set(
                    self.name,
                    f"kwriteconfig6 failed ({r.returncode}): {r.stderr.strip()}",
                    ctx,
                )
                all_ok = False
        if all_ok:
            debug_set(self.name, f"lockscreen wallpaper set via kwriteconfig6: {uri}", ctx)
            # Verify
            try:
                text = cfg.read_text(encoding="utf-8", errors="replace")
                if uri not in text and str(Path(uri).as_posix()) not in text:
                    # also accept path without scheme if kwrite stripped it
                    path_part = uri.removeprefix("file://")
                    if path_part not in text:
                        debug_set(self.name, "kscreenlockerrc missing Image after write", ctx)
                        return False
            except OSError:
                pass
        return all_ok

    def _lockscreen_file_edit(
        self, cfg: Path, path: Path, uri: str, ctx: WallpaperContext
    ) -> bool:
        plugin = WALLPAPER_PLUGIN
        section = f"[Greeter][Wallpaper][{plugin}][General]"
        try:
            cfg.parent.mkdir(parents=True, exist_ok=True)
            if not cfg.is_file():
                cfg.write_text(
                    "\n".join(
                        [
                            "[Greeter]",
                            f"WallpaperPlugin={plugin}",
                            "",
                            section,
                            f"Image={uri}",
                            f"PreviewImage={uri}",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
                debug_set(self.name, "created lockscreen config", ctx)
                return True

            lines = cfg.read_text(encoding="utf-8", errors="replace").splitlines()
            out: list[str] = []
            greeter_found = False
            wallpaper_plugin_set = False
            section_found = False
            image_set = False
            preview_set = False
            in_image_section = False

            section_re = re.compile(
                rf"^\[Greeter\]\[Wallpaper\]\[{re.escape(plugin)}\]\[General\]\s*$"
            )

            for line in lines:
                stripped = line.strip()

                if stripped == "[Greeter]":
                    greeter_found = True
                    out.append(line)
                    continue

                if greeter_found and not wallpaper_plugin_set:
                    if stripped.startswith("WallpaperPlugin="):
                        out.append(f"WallpaperPlugin={plugin}")
                        wallpaper_plugin_set = True
                        greeter_found = False
                        continue
                    if stripped.startswith("["):
                        # left [Greeter] without WallpaperPlugin
                        out.append(f"WallpaperPlugin={plugin}")
                        wallpaper_plugin_set = True
                        greeter_found = False
                    # else still in [Greeter]

                if section_re.match(stripped):
                    in_image_section = True
                    section_found = True
                    out.append(line)
                    continue

                if in_image_section:
                    if stripped.startswith("Image="):
                        out.append(f"Image={uri}")
                        image_set = True
                        continue
                    if stripped.startswith("PreviewImage="):
                        out.append(f"PreviewImage={uri}")
                        preview_set = True
                        continue
                    if stripped.startswith("["):
                        # leaving section — pad missing keys
                        if not image_set:
                            out.append(f"Image={uri}")
                            image_set = True
                        if not preview_set:
                            out.append(f"PreviewImage={uri}")
                            preview_set = True
                        in_image_section = False
                        out.append(line)
                        continue
                    out.append(line)
                    continue

                out.append(line)

            if greeter_found and not wallpaper_plugin_set:
                out.append(f"WallpaperPlugin={plugin}")
                wallpaper_plugin_set = True

            if in_image_section:
                if not image_set:
                    out.append(f"Image={uri}")
                    image_set = True
                if not preview_set:
                    out.append(f"PreviewImage={uri}")
                    preview_set = True

            if not greeter_found and not wallpaper_plugin_set:
                # No bare [Greeter] section — WallpaperPlugin still useful
                out.insert(0, f"WallpaperPlugin={plugin}")
                out.insert(0, "[Greeter]")
                wallpaper_plugin_set = True

            if not section_found:
                out.append("")
                out.append(section)
                out.append(f"Image={uri}")
                out.append(f"PreviewImage={uri}")

            fd, tmp = tempfile.mkstemp(prefix="kscreenlocker_", dir=str(cfg.parent))
            os.close(fd)
            tmp_path = Path(tmp)
            try:
                tmp_path.write_text("\n".join(out) + "\n", encoding="utf-8")
                tmp_path.chmod(0o600)
                tmp_path.replace(cfg)
            except OSError:
                tmp_path.unlink(missing_ok=True)
                raise

            debug_set(self.name, f"updated lockscreen wallpaper (file edit): {uri}", ctx)
            return True
        except OSError as e:
            debug_set(self.name, f"lockscreen update failed: {e}", ctx)
            return False
