"""GTK theme reload + dark preference (Plasma portal / xsettingsd)."""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

from wallpaperctl.context import WallpaperContext
from wallpaperctl.theme.base import debug_op
from wallpaperctl.util import have, home, is_dark_theme_name, pgrep_exact, pgrep_full, run


class GtkThemeOp:
    name = "gtk-theme"

    def enabled(self, ctx: WallpaperContext) -> bool:
        return ctx.ops.enable_gtk_theme

    def run(self, ctx: WallpaperContext) -> bool:
        if ctx.de.xfce:
            return self._xfce(ctx)
        if not have("gsettings"):
            debug_op(self.name, "gsettings not found", ctx)
            return True

        if ctx.de.plasma:
            current = self._gget("org.gnome.desktop.interface", "gtk-theme")
            color_scheme = self._gget("org.gnome.desktop.interface", "color-scheme")
            target = ctx.ops.gtk_theme_plasma or current
            if color_scheme == "prefer-dark" and not is_dark_theme_name(target):
                dark = self._dark_variant(target)
                if dark:
                    target = dark
            self._gset("org.gnome.desktop.interface", "gtk-theme", target)
            self._gset("org.gnome.desktop.interface", "color-scheme", "prefer-dark")
        elif ctx.de.cinnamon:
            dyn = home() / ".themes" / "cinnamon-dynamic" / "gtk-3.0" / "gtk.css"
            if dyn.is_file():
                self._gset("org.cinnamon.desktop.interface", "gtk-theme", "cinnamon-dynamic")
                self._gset("org.gnome.desktop.interface", "gtk-theme", "cinnamon-dynamic")
            else:
                current = self._gget("org.cinnamon.desktop.interface", "gtk-theme")
                if current:
                    self._gset("org.gnome.desktop.interface", "gtk-theme", current)
                else:
                    t = ctx.ops.gtk_theme_cinnamon
                    self._gset("org.cinnamon.desktop.interface", "gtk-theme", t)
                    self._gset("org.gnome.desktop.interface", "gtk-theme", t)
        else:
            current = self._gget("org.gnome.desktop.interface", "gtk-theme")
            if current.endswith("-dark"):
                target = current
            else:
                target = ctx.ops.gtk_theme_standalone
            self._gset("org.gnome.desktop.interface", "gtk-theme", target)
            self._gset("org.gnome.desktop.interface", "color-scheme", "prefer-dark")

        return self._reload_gtk(ctx)

    def _xfce(self, ctx: WallpaperContext) -> bool:
        if not have("xfconf-query"):
            return True
        current_r = run(
            ["xfconf-query", "-c", "xsettings", "-p", "/Net/ThemeName"],
            timeout=5,
        )
        current = current_r.stdout.strip() if current_r.returncode == 0 else "Greybird"
        target = ctx.ops.gtk_theme_xfce or current
        run(
            ["xfconf-query", "-c", "xsettings", "-p", "/Net/ThemeName", "-s", target],
            timeout=5,
        )
        if pgrep_exact("xfsettingsd"):
            run(["pkill", "-HUP", "xfsettingsd"], timeout=5)
        return True

    def _reload_gtk(self, ctx: WallpaperContext) -> bool:
        current = self._gget("org.gnome.desktop.interface", "gtk-theme") or "Default"
        self._gset("org.gnome.desktop.interface", "color-scheme", "prefer-dark")
        self._ensure_settings_ini(current)
        self._ensure_gtk_theme_env(ctx)
        self._reload_kde_gtkconfig()
        self._ensure_portal()
        self._emit_portal_signal()
        self._update_xsettingsd(current)

        self._gset("org.gnome.desktop.interface", "gtk-theme", "")
        self._gset("org.gnome.desktop.interface", "gtk-theme", current)
        debug_op(self.name, "GTK reloaded with dark preference", ctx)
        return True

    def _ensure_settings_ini(self, theme_name: str) -> None:
        for ini in (
            home() / ".config" / "gtk-3.0" / "settings.ini",
            home() / ".config" / "gtk-4.0" / "settings.ini",
        ):
            if not ini.is_file():
                continue
            try:
                text = ini.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            lines = text.splitlines()
            out: list[str] = []
            has_dark = False
            has_theme = False
            for line in lines:
                if line.startswith("gtk-application-prefer-dark-theme="):
                    out.append("gtk-application-prefer-dark-theme=1")
                    has_dark = True
                elif line.startswith("gtk-theme-name="):
                    cur = line.split("=", 1)[1]
                    if theme_name and not is_dark_theme_name(cur):
                        out.append(f"gtk-theme-name={theme_name}")
                    else:
                        out.append(line)
                    has_theme = True
                else:
                    out.append(line)
            if not has_dark:
                if any(l.startswith("[Settings]") for l in out):
                    new = []
                    for l in out:
                        new.append(l)
                        if l.startswith("[Settings]") and not has_dark:
                            new.append("gtk-application-prefer-dark-theme=1")
                            has_dark = True
                    out = new
                else:
                    out = ["[Settings]", "gtk-application-prefer-dark-theme=1"] + out
            try:
                ini.write_text("\n".join(out) + "\n", encoding="utf-8")
            except OSError:
                pass

    def _ensure_gtk_theme_env(self, ctx: WallpaperContext) -> None:
        env_file = home() / ".config" / "environment.d" / "gtk-theme.conf"
        if not env_file.is_file():
            return
        try:
            text = env_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        m = re.search(r"^GTK_THEME=(.*)$", text, re.M)
        if not m:
            return
        current = m.group(1).strip().strip('"')
        base = current.split(":")[0]
        variant = current.split(":")[1] if ":" in current else ""

        if not ctx.de.cinnamon and re.search(r"^cinnamon", base, re.I):
            if ctx.de.plasma:
                replacement = "Breeze-Dark"
            else:
                replacement = ctx.ops.gtk_theme_standalone
            if variant and not is_dark_theme_name(replacement):
                replacement = f"{replacement}:{variant}"
            new = re.sub(r"^GTK_THEME=.*$", f"GTK_THEME={replacement}", text, flags=re.M)
            env_file.write_text(new, encoding="utf-8")
            return

        if is_dark_theme_name(base):
            return
        dark = self._dark_variant(base)
        if dark:
            if variant and not is_dark_theme_name(dark):
                dark = f"{dark}:{variant}"
            new = re.sub(r"^GTK_THEME=.*$", f"GTK_THEME={dark}", text, flags=re.M)
            env_file.write_text(new, encoding="utf-8")

    def _reload_kde_gtkconfig(self) -> None:
        for bus, proc in (("org.kde.kded6", "kded6"), ("org.kde.kded5", "kded5")):
            if not pgrep_exact(proc):
                continue
            if not have("qdbus"):
                break
            run(["qdbus", bus, "/kded", "unloadModule", "gtkconfig"], timeout=5)
            run(["qdbus", bus, "/kded", "loadModule", "gtkconfig"], timeout=5)
            break

    def _ensure_portal(self) -> None:
        if pgrep_full("xdg-desktop-portal"):
            return
        for unit in (
            "xdg-desktop-portal-kde",
            "xdg-desktop-portal-gnome",
            "xdg-desktop-portal",
        ):
            r = run(["systemctl", "--user", "start", unit], timeout=10)
            if r.returncode == 0:
                time.sleep(0.5)
                return

    def _emit_portal_signal(self) -> None:
        if not have("dbus-send"):
            return
        run(
            [
                "dbus-send",
                "--session",
                "--type=signal",
                "/org/freedesktop/portal/desktop",
                "org.freedesktop.portal.Settings.SettingChanged",
                "string:org.freedesktop.appearance",
                "string:color-scheme",
                "variant:uint32:1",
            ],
            timeout=5,
        )

    def _update_xsettingsd(self, theme: str) -> None:
        conf = home() / ".config" / "xsettingsd" / "xsettingsd.conf"
        if not conf.is_file():
            return
        try:
            lines = [
                l
                for l in conf.read_text(encoding="utf-8", errors="replace").splitlines()
                if "Gtk/ApplicationPreferDarkTheme" not in l and "Net/ThemeName" not in l
            ]
            x_theme = theme
            if not is_dark_theme_name(theme):
                dark = self._dark_variant(theme)
                if dark:
                    x_theme = dark
            new = [
                "Gtk/ApplicationPreferDarkTheme 1",
                f'Net/ThemeName "{x_theme}"',
                *lines,
            ]
            conf.write_text("\n".join(new) + "\n", encoding="utf-8")
            r = run(["pkill", "-HUP", "xsettingsd"], timeout=5)
            if r.returncode != 0 and have("xsettingsd"):
                run(["pkill", "xsettingsd"], timeout=5)
                time.sleep(0.1)
                subprocess.Popen(
                    ["xsettingsd"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
        except OSError:
            pass

    @staticmethod
    def _theme_exists(theme: str) -> bool:
        for base in (
            home() / ".themes",
            Path("/usr/share/themes"),
            home() / ".local" / "share" / "themes",
        ):
            if (base / theme).is_dir():
                return True
        return False

    def _dark_variant(self, theme: str) -> str:
        if theme == "Breeze":
            return "Breeze-Dark"
        if theme == "Adwaita":
            return "Adwaita-dark"
        for suffix in ("-Dark", "-dark"):
            cand = f"{theme}{suffix}"
            if self._theme_exists(cand):
                return cand
        return ""

    @staticmethod
    def _gget(schema: str, key: str) -> str:
        r = run(["gsettings", "get", schema, key], timeout=5)
        if r.returncode != 0:
            return ""
        return r.stdout.strip().strip("'")

    @staticmethod
    def _gset(schema: str, key: str, value: str) -> None:
        run(["gsettings", "set", schema, key, value], timeout=5)
