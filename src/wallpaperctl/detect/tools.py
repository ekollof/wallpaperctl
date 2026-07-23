"""Optional / required tool detection."""

from __future__ import annotations

from dataclasses import dataclass, field

from wallpaperctl.detect.desktop import DesktopEnvironment
from wallpaperctl.util import have


@dataclass
class ToolReport:
    missing_required: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    present: dict[str, bool] = field(default_factory=dict)


def detect_tools(de: DesktopEnvironment, *, strict: bool = False) -> ToolReport:
    report = ToolReport()

    # Pillow is a package dependency — image ops never need ImageMagick.
    try:
        import PIL  # noqa: F401

        report.present["pillow"] = True
    except ImportError:
        report.present["pillow"] = False
        report.missing_required.append("Pillow (pip package)")

    try:
        import imagehash  # noqa: F401

        report.present["imagehash"] = True
    except ImportError:
        report.present["imagehash"] = False
        report.warnings.append("imagehash not found: perceptual dedup disabled")

    try:
        import jeepney  # noqa: F401

        report.present["jeepney"] = True
    except ImportError:
        report.present["jeepney"] = False
        report.warnings.append("jeepney not found: desktop notifications disabled")

    if de.plasma:
        if not have("dbus-send"):
            report.missing_required.append("dbus-send (required for Plasma wallpapers)")
    elif de.hyprland and not de.noctalia:
        if not have("hyprctl"):
            report.missing_required.append("hyprctl")
    elif de.noctalia:
        if not have("qs"):
            report.missing_required.append("qs (Noctalia)")
    elif de.xfce:
        if not have("xfconf-query"):
            report.missing_required.append("xfconf-query")
    elif de.cinnamon:
        if not have("gsettings"):
            report.missing_required.append("gsettings")
    else:
        setters = ["feh", "nitrogen", "hsetroot", "xwallpaper", "xsetbg"]
        if not any(have(s) for s in setters):
            report.missing_required.append(
                "wallpaper setter (feh|nitrogen|hsetroot|xwallpaper|xsetbg)"
            )

    soft = {
        "wallust": "color scheme won't be updated",
        "openrgb": "RGB lighting skipped",
        "nwg-look": "GTK/xsettingsd reload skipped",
        "dunst": "dunst notifications skipped",
        "mako": "mako notifications skipped",
        "waybar": "waybar reload skipped",
        "xrdb": "Xresources merge skipped",
    }
    for cmd, msg in soft.items():
        ok = have(cmd)
        report.present[cmd] = ok
        if not ok:
            report.warnings.append(f"{cmd} not found: {msg}")

    if strict and report.missing_required:
        raise SystemExit(
            "Error: missing required tools:\n  - "
            + "\n  - ".join(report.missing_required)
        )
    return report
