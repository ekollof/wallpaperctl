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


def _openlinkhub_reachable(url: str = "http://127.0.0.1:27003") -> bool:
    """True if OpenLinkHub's local REST API answers on the default port."""
    try:
        import httpx
    except ImportError:
        return False
    try:
        with httpx.Client(timeout=1.0) as client:
            resp = client.get(f"{url.rstrip('/')}/api/")
        return resp.status_code == 200
    except Exception:
        return False


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
        if not report.present.get("jeepney"):
            report.missing_required.append(
                "jeepney (session D-Bus client for Plasma wallpapers)"
            )
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

    # OpenLinkHub is a local HTTP daemon, not a CLI tool
    olh_ok = _openlinkhub_reachable()
    report.present["openlinkhub"] = olh_ok
    if not olh_ok:
        report.warnings.append(
            "openlinkhub not reachable at http://127.0.0.1:27003: Corsair RGB via OpenLinkHub skipped"
        )

    if strict and report.missing_required:
        raise SystemExit(
            "Error: missing required tools:\n  - "
            + "\n  - ".join(report.missing_required)
        )
    return report
