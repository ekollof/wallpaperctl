from pathlib import Path

from wallpaperctl.config import OpsConfig
from wallpaperctl.context import WallpaperContext
from wallpaperctl.detect.desktop import DesktopEnvironment
from wallpaperctl.set import plasma as plasma_mod
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


def test_animated_overlay_settings_saved_and_restored(tmp_path: Path, monkeypatch):
    setter = PlasmaSetter()
    video = tmp_path / "wall.mp4"
    video.write_bytes(b"video")
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"png")
    still = tmp_path / "wall.jpg"
    still.write_bytes(b"jpg")
    appletsrc = tmp_path / "appletsrc"
    appletsrc.write_text(
        "[Containments][1][Wallpaper][org.kde.image][General]\n"
        "FillMode=6\n"
        "Color=1,2,3\n",
        encoding="utf-8",
    )
    state = tmp_path / "overlay-state"
    monkeypatch.setattr(plasma_mod, "_appletsrc_path", lambda: appletsrc)
    monkeypatch.setattr(plasma_mod, "_ANIMATED_OVERLAY_STATE", state)
    captured: list[str] = []

    def fake_call(**kwargs):
        captured.append(kwargs["body"][0])
        return True, ""

    monkeypatch.setattr(plasma_mod, "dbus_call", fake_call)

    animated_ctx = _ctx(video)
    animated_ctx.static_path = frame
    assert setter._set_desktop(frame, animated_ctx) is True

    saved = state.read_text(encoding="utf-8")
    assert "FillMode=6" in saved
    assert "Color=1,2,3" in saved
    assert "Blur=false" in saved
    animated_js = captured[-1]
    assert 'd.writeConfig("FillMode", 1)' in animated_js
    assert 'd.writeConfig("Color", "#000000")' in animated_js

    static_ctx = _ctx(still)
    assert setter._set_desktop(still, static_ctx) is True

    restore_js = captured[-1]
    assert 'd.writeConfig("FillMode", "6")' in restore_js
    assert 'd.writeConfig("Color", "1,2,3")' in restore_js
    assert 'd.writeConfig("Blur", "false")' in restore_js
    assert not state.exists()


def test_static_apply_without_overlay_state_leaves_settings_untouched(
    tmp_path: Path, monkeypatch
):
    setter = PlasmaSetter()
    still = tmp_path / "wall.jpg"
    still.write_bytes(b"jpg")
    monkeypatch.setattr(
        plasma_mod, "_ANIMATED_OVERLAY_STATE", tmp_path / "missing-state"
    )
    captured: list[str] = []

    def fake_call(**kwargs):
        captured.append(kwargs["body"][0])
        return True, ""

    monkeypatch.setattr(plasma_mod, "dbus_call", fake_call)

    assert setter._set_desktop(still, _ctx(still)) is True
    assert "FillMode" not in captured[-1]
    assert "Color" not in captured[-1]
