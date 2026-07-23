from wallpaperctl.detect.desktop import DesktopEnvironment, detect_desktop
from wallpaperctl.util import sanitize_string, hex_to_rgb


def test_sanitize():
    assert sanitize_string("Foo Bar/@!") == "Foo_Bar"


def test_hex_to_rgb():
    assert hex_to_rgb("#ff0080") == (255, 0, 128)
    assert hex_to_rgb("00ff00") == (0, 255, 0)


def test_detect_desktop_returns_object():
    de = detect_desktop()
    assert isinstance(de, DesktopEnvironment)
    assert isinstance(de.name, str)


def test_palette_select():
    from wallpaperctl.theme.palette import select_palette_line
    # no colors file → fallback 12
    line = select_palette_line("warmest", colors_file=__import__("pathlib").Path("/nonexistent"))
    assert line == 12
