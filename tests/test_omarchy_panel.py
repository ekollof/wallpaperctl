from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from PIL import Image

from wallpaperctl.cli import main
from wallpaperctl.config import OpsConfig
from wallpaperctl.omarchy_panel import PLUGIN_ID, local_file_url, wallpaper_status
from wallpaperctl.setup.omarchy_bootstrap import install_wallpaper_widget


def test_status_empty_and_missing(tmp_path):
    ops = OpsConfig(current_wallpaper_file=str(tmp_path / "current"))
    assert wallpaper_status(ops)["path"] == ""
    (tmp_path / "current").write_text(str(tmp_path / "missing.png"))
    assert wallpaper_status(ops)["missing"] is True


def test_status_preserves_untrusted_filename_without_markup(tmp_path):
    image = tmp_path / "<b>wallpaper & snow 雪</b>.png".replace("/", "_")
    Image.new("RGB", (160, 90)).save(image)
    current = tmp_path / "current"
    current.write_text(str(image))
    ops = OpsConfig(current_wallpaper_file=str(current))
    status = wallpaper_status(ops)
    assert status["name"] == image.name
    assert status["dimensions"] == "160 × 90"
    assert status["kind"] == "Static"
    assert status["preview"] == image.as_uri()
    assert local_file_url(status["preview"]) == image


def test_video_status_does_not_decode_or_fetch(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    current = tmp_path / "current"
    current.write_text(str(video))
    status = wallpaper_status(OpsConfig(current_wallpaper_file=str(current)))
    assert status["kind"] == "Animated"
    assert status["preview"] == ""


@pytest.mark.parametrize(
    "url",
    [
        "https://example.org/image.png",
        "file://remote/image.png",
        "file:relative",
        "file:///missing.png",
    ],
)
def test_picker_rejects_nonlocal_or_missing_file(url):
    with pytest.raises(ValueError):
        local_file_url(url)


def test_panel_cli_status_is_json(tmp_path, capsys):
    with patch(
        "wallpaperctl.cli.load_ops_config",
        return_value=OpsConfig(current_wallpaper_file=str(tmp_path / "none")),
    ):
        assert main(["omarchy-panel", "status"]) == 0
    assert json.loads(capsys.readouterr().out)["path"] == ""


def test_picker_passes_path_as_one_argument(tmp_path):
    image = tmp_path / "a $(touch nope) # 雪.png"
    image.touch()
    from wallpaperctl import cli

    with patch.object(cli, "_run_action", return_value=0) as action:
        assert main(["omarchy-panel", "set", image.as_uri()]) == 0
    assert action.call_args.kwargs["path"] == str(image)
    assert action.call_args.kwargs["sync"] is False


def test_widget_install_is_idempotent_and_preserves_other_files(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    with (
        patch("wallpaperctl.setup.omarchy_bootstrap.run_omarchy") as omarchy,
        patch("wallpaperctl.setup.omarchy_bootstrap.is_omarchy_shell_running", return_value=False),
    ):
        omarchy.return_value.returncode = 0
        assert install_wallpaper_widget()
        target = tmp_path / ".config/omarchy/plugins" / PLUGIN_ID
        custom = target / "notes.txt"
        custom.write_text("keep")
        before = (target / "BarWidget.qml").stat().st_mtime_ns
        assert install_wallpaper_widget()
        assert (target / "BarWidget.qml").stat().st_mtime_ns == before
        assert custom.read_text() == "keep"
        assert omarchy.call_args.args[0] == ["bar", "put", PLUGIN_ID, "--section", "right"]
        manifest = json.loads((target / "manifest.json").read_text())
        assert set(manifest["kinds"]) == {"bar-widget", "service"}
        for file in manifest["entryPoints"].values():
            assert (target / file).is_file()


def test_widget_install_validation_failure_is_soft(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    with patch("wallpaperctl.setup.omarchy_bootstrap.run_omarchy") as omarchy:
        omarchy.return_value.returncode = 1
        omarchy.return_value.stderr = "unsupported"
        assert not install_wallpaper_widget()
        assert omarchy.call_count == 1


def _delete_fixture(tmp_path):
    from wallpaperctl.omarchy_panel import file_identity

    library = tmp_path / "library"
    library.mkdir()
    current = library / "current.png"
    Image.new("RGB", (10, 10)).save(current)
    record = tmp_path / "current"
    record.write_text(str(current))
    ops = OpsConfig(current_wallpaper_file=str(record), wallpaper_dir=str(library))
    return ops, current, record, file_identity(current)


def test_delete_applies_replacement_before_unlink(tmp_path):
    from wallpaperctl.omarchy_panel import delete_current_wallpaper

    ops, current, record, identity = _delete_fixture(tmp_path)
    replacement = current.with_name("replacement.png")
    Image.new("RGB", (10, 10)).save(replacement)

    def apply(path, ops, sync):
        assert current.exists()
        assert path == replacement
        assert record.read_text().strip() == str(replacement)
        assert not sync
        return True

    with patch("wallpaperctl.omarchy_panel.apply_wallpaper", side_effect=apply):
        delete_current_wallpaper(ops, str(current), identity)
    assert not current.exists()
    assert replacement.exists()
    assert record.read_text().strip() == str(replacement)


@pytest.mark.parametrize("failure", ["no_replacement", "apply_fails", "stale_path", "stale_file"])
def test_delete_keeps_file_when_preconditions_fail(tmp_path, failure):
    from wallpaperctl.omarchy_panel import delete_current_wallpaper

    ops, current, record, identity = _delete_fixture(tmp_path)
    if failure != "no_replacement":
        Image.new("RGB", (10, 10)).save(current.with_name("replacement.png"))
    if failure == "stale_file":
        current.write_bytes(b"changed since confirmation")
    expected = str(current) if failure != "stale_path" else str(current.with_name("other.png"))
    with patch("wallpaperctl.omarchy_panel.apply_wallpaper", return_value=False) as apply:
        with pytest.raises(ValueError):
            delete_current_wallpaper(ops, expected, identity)
    assert current.exists()
    assert record.read_text().strip() == str(current)
    if failure != "apply_fails":
        apply.assert_not_called()


def test_delete_does_not_follow_alias_as_replacement(tmp_path):
    from wallpaperctl.omarchy_panel import delete_current_wallpaper

    ops, current, record, identity = _delete_fixture(tmp_path)
    current.with_name("alias.png").symlink_to(current)
    with pytest.raises(ValueError, match="No replacement"):
        delete_current_wallpaper(ops, str(current), identity)
    assert current.exists()


def test_delete_rechecks_identity_after_applying(tmp_path):
    from wallpaperctl.omarchy_panel import delete_current_wallpaper

    ops, current, record, identity = _delete_fixture(tmp_path)
    Image.new("RGB", (10, 10)).save(current.with_name("replacement.png"))

    def apply(*args, **kwargs):
        current.write_bytes(b"new file contents")
        return True

    with patch("wallpaperctl.omarchy_panel.apply_wallpaper", side_effect=apply):
        with pytest.raises(ValueError, match="Original file changed"):
            delete_current_wallpaper(ops, str(current), identity)
    assert current.read_bytes() == b"new file contents"
