"""KDE Plasma wallpaper via dbus-send evaluateScript + lockscreen config."""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path

from wallpaperctl.context import WallpaperContext
from wallpaperctl.set.base import debug_set
from wallpaperctl.util import have, run

log = logging.getLogger("wallpaperctl")


class PlasmaSetter:
    name = "plasma"

    def applies(self, ctx: WallpaperContext) -> bool:
        return ctx.de.plasma

    def set_wallpaper(self, ctx: WallpaperContext) -> bool:
        path = ctx.path.resolve()
        if not path.is_file():
            debug_set(self.name, f"file not found: {path}", ctx)
            return False
        if not have("dbus-send"):
            debug_set(self.name, "dbus-send not found", ctx)
            return False

        ok = self._set_desktop(path, ctx)
        self._set_lockscreen(path, ctx)
        return ok

    def _set_desktop(self, path: Path, ctx: WallpaperContext) -> bool:
        plugin = "org.kde.image"
        # file:// URI
        uri = path.as_uri()
        js = f"""
var allDesktops = desktops();
print (allDesktops);
for (i=0;i<allDesktops.length;i++) {{
    d = allDesktops[i];
    d.wallpaperPlugin = "{plugin}";
    d.currentConfigGroup = Array("Wallpaper", "{plugin}", "General");
    d.writeConfig("Image", "{uri}")
}}
"""
        r = run(
            [
                "dbus-send",
                "--session",
                "--dest=org.kde.plasmashell",
                "--type=method_call",
                "/PlasmaShell",
                "org.kde.PlasmaShell.evaluateScript",
                f"string:{js}",
            ],
            timeout=15,
        )
        if r.returncode == 0:
            debug_set(self.name, "desktop wallpaper set", ctx)
            return True
        debug_set(self.name, f"dbus failed: {r.stderr}", ctx)
        return False

    def _set_lockscreen(self, path: Path, ctx: WallpaperContext) -> None:
        plugin = "org.kde.image"
        cfg = Path.home() / ".config" / "kscreenlockerrc"
        section = f"[Greeter][Wallpaper][{plugin}][General]"
        try:
            cfg.parent.mkdir(parents=True, exist_ok=True)
            if not cfg.is_file():
                cfg.write_text(f"{section}\nImage={path}\n", encoding="utf-8")
                debug_set(self.name, "created lockscreen config", ctx)
                return

            lines = cfg.read_text(encoding="utf-8", errors="replace").splitlines()
            out: list[str] = []
            in_section = False
            section_found = False
            image_written = False
            for line in lines:
                if line.strip() == section or re.match(
                    rf"^\[Greeter\]\[Wallpaper\]\[{re.escape(plugin)}\]\[General\]",
                    line,
                ):
                    in_section = True
                    section_found = True
                    out.append(line)
                    continue
                if in_section and line.startswith("Image="):
                    out.append(f"Image={path}")
                    image_written = True
                    in_section = False
                    continue
                if in_section and line.startswith("["):
                    if not image_written:
                        out.append(f"Image={path}")
                        image_written = True
                    in_section = False
                out.append(line)
            if not section_found:
                out.append("")
                out.append(section)
                out.append(f"Image={path}")
            elif section_found and not image_written:
                out.append(f"Image={path}")

            fd, tmp = tempfile.mkstemp(prefix="kscreenlocker_")
            import os

            os.close(fd)
            Path(tmp).write_text("\n".join(out) + "\n", encoding="utf-8")
            Path(tmp).replace(cfg)
            debug_set(self.name, "updated lockscreen wallpaper", ctx)
        except OSError as e:
            debug_set(self.name, f"lockscreen update failed: {e}", ctx)
