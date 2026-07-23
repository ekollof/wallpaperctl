from pathlib import Path

from wallpaperctl.config import OpsConfig
from wallpaperctl.context import WallpaperContext
from wallpaperctl.detect.desktop import DesktopEnvironment
from wallpaperctl.set.plasma import PlasmaSetter


def _ctx(path: Path) -> WallpaperContext:
    return WallpaperContext(
        path=path,
        de=DesktopEnvironment(plasma=True),
        ops=OpsConfig(),
        debug=True,
    )


def test_lockscreen_file_edit_creates_and_updates(tmp_path: Path, monkeypatch):
    setter = PlasmaSetter()
    img = tmp_path / "wall.jpg"
    img.write_bytes(b"fake")
    cfg = tmp_path / "kscreenlockerrc"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    # Point config at tmp by patching method internals via home()
    # _lockscreen_file_edit takes cfg path explicitly
    uri = img.as_uri()
    ctx = _ctx(img)

    assert setter._lockscreen_file_edit(cfg, img, uri, ctx) is True
    text = cfg.read_text(encoding="utf-8")
    assert "WallpaperPlugin=org.kde.image" in text
    assert f"Image={uri}" in text
    assert f"PreviewImage={uri}" in text

    img2 = tmp_path / "wall2.jpg"
    img2.write_bytes(b"fake2")
    uri2 = img2.as_uri()
    assert setter._lockscreen_file_edit(cfg, img2, uri2, ctx) is True
    text2 = cfg.read_text(encoding="utf-8")
    assert f"Image={uri2}" in text2
    assert f"PreviewImage={uri2}" in text2
    # Count Image= keys only (PreviewImage= also contains the substring "Image=")
    image_keys = [
        ln for ln in text2.splitlines() if ln.startswith("Image=")
    ]
    assert len(image_keys) == 1
    assert uri not in text2  # old uri gone
