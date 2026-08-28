"""Omarchy integration: helpers, setter, theme op, setup bootstrap."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from wallpaperctl.config import OpsConfig
from wallpaperctl.context import WallpaperContext
from wallpaperctl.detect.desktop import DesktopEnvironment
from wallpaperctl.omarchy import (
    THEME_SLUG,
    current_theme_name,
    is_dynamic_theme_active,
)
from wallpaperctl.set.omarchy import OmarchySetter
from wallpaperctl.setup import omarchy_bootstrap as ob
from wallpaperctl.theme import omarchy as tom
from wallpaperctl.theme.omarchy import (
    OmarchyThemeOp,
    build_colors_mapping,
    ensure_theme_skeleton,
    render_colors_toml,
    sync_theme_media,
)


@pytest.fixture(autouse=True)
def _no_real_process_signals(monkeypatch):
    """Never let tests signal real processes (kitty/opencode) or run wallust.

    Individual tests may re-patch these; the stub only guarantees that an
    un-mocked code path cannot SIGUSR2/SIGUSR1 the developer's live session.
    """
    rc0 = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
    monkeypatch.setattr("wallpaperctl.theme.omarchy.run", lambda *a, **k: rc0)
    monkeypatch.setattr(
        "wallpaperctl.theme.omarchy.have", lambda cmd: cmd in ("pkill", "wallust")
    )

# ── helpers / state ──────────────────────────────────────────────────────


def _fake_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def _theme_state(tmp_path: Path, slug: str | None) -> Path:
    state = tmp_path / ".local" / "state" / "omarchy" / "current"
    state.mkdir(parents=True, exist_ok=True)
    if slug is not None:
        (state / "theme.name").write_text(slug + "\n", encoding="utf-8")
    return state


def test_current_theme_name_reads_state(monkeypatch, tmp_path):
    _fake_home(monkeypatch, tmp_path)
    assert current_theme_name() is None
    _theme_state(tmp_path, "tokyo-night")
    assert current_theme_name() == "tokyo-night"


def test_dynamic_theme_active_gate(monkeypatch, tmp_path):
    _fake_home(monkeypatch, tmp_path)
    assert not is_dynamic_theme_active()
    _theme_state(tmp_path, THEME_SLUG)
    assert is_dynamic_theme_active()
    _theme_state(tmp_path, "andrath-terminal")
    assert not is_dynamic_theme_active()


# ── palette mapping ──────────────────────────────────────────────────────


def _palette(bright: bool = False) -> dict:
    base = {
        "special": {"background": "#101315", "foreground": "#cacccc", "cursor": "#a5aeb4"},
        "colors": {
            "color0": "#101315",
            "color1": "#de6145",
            "color2": "#8ec07c",
            "color3": "#d8a657",
            "color4": "#7daea3",
            "color5": "#d3869b",
            "color6": "#89b482",
            "color7": "#cacccc",
            "color8": "#4b4e55",
            "color9": "#e78a4e",
            "color10": "#a9b665",
            "color11": "#d8a657",
            "color12": "#7daea3",
            "color13": "#d3869b",
            "color14": "#89b482",
            "color15": "#a5aeb4",
        },
    }
    if bright:
        base["special"]["background"] = "#f4f0ec"
    return base


def test_mapping_has_required_keys():
    m = build_colors_mapping(_palette())
    for key in ("mode", "accent", "background", "foreground", "color0", "color15"):
        assert key in m
    # accent has no omarchy-side derivation — must always be present and hex
    assert m["accent"].startswith("#") and len(m["accent"]) == 7


def test_mapping_values_charset_safe():
    # omarchy-theme-color rejects keys/values outside its whitelist; make sure
    # everything we emit passes that filter.
    import re

    key_re = re.compile(r"^[A-Za-z0-9_-]+$")
    value_re = re.compile(r"^[A-Za-z0-9#(),._+/% -]*$")
    m = build_colors_mapping(_palette())
    for key, value in m.items():
        assert key_re.match(key), key
        assert value_re.match(value), (key, value)


def test_mapping_mode_from_background_luminance():
    assert build_colors_mapping(_palette())["mode"] == "dark"
    assert build_colors_mapping(_palette(bright=True))["mode"] == "light"


def test_render_colors_toml_roundtrip():
    import tomllib

    text = render_colors_toml(build_colors_mapping(_palette()))
    data = tomllib.loads(text)
    assert data["mode"] == "dark"
    assert data["hyprland_active_border"].endswith("45deg")
    assert data["color7"] == "#cacccc"


def test_write_colors_toml_atomic(tmp_path):
    target = tom.write_colors_toml(tmp_path, {"accent": "#ff0000"})
    assert target.is_file()
    assert not target.with_suffix(".toml.tmp").exists()
    assert 'accent = "#ff0000"' in target.read_text(encoding="utf-8")


# ── theme media sync ─────────────────────────────────────────────────────


def _png(tmp_path: Path, name: str = "wall.png") -> Path:
    from PIL import Image

    img = tmp_path / name
    Image.new("RGB", (8, 8), (200, 30, 30)).save(img, format="PNG")
    return img


def test_sync_static_clears_old_video(tmp_path):
    img = _png(tmp_path, "wall.jpg")
    theme = tmp_path / "theme"
    theme.mkdir()
    (theme / "wallpaper-video.mp4").write_bytes(b"old")

    assert sync_theme_media(theme, img, video_path=None)
    assert (theme / "backgrounds" / "wall.jpg").is_file()
    assert not list(theme.glob("wallpaper-video.*"))
    assert (theme / "preview.png").is_file()


def test_sync_animated_stages_video(tmp_path):
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"frame")
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"video")
    theme = tmp_path / "theme"
    theme.mkdir()

    assert sync_theme_media(theme, img, video_path=video)
    assert (theme / "wallpaper-video.mp4").is_file()
    assert (theme / "backgrounds" / "frame.jpg").is_file()


def test_sync_unsupported_video_codec_not_staged(tmp_path):
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"frame")
    video = tmp_path / "clip.avi"
    video.write_bytes(b"video")
    theme = tmp_path / "theme"
    theme.mkdir()

    assert sync_theme_media(theme, img, video_path=video)
    assert not list(theme.glob("wallpaper-video.*"))


def test_sync_replaces_previous_background(tmp_path):
    old = tmp_path / "old.jpg"
    old.write_bytes(b"old")
    new = tmp_path / "new.jpg"
    new.write_bytes(b"new")
    theme = tmp_path / "theme"
    sync_theme_media(theme, old)
    sync_theme_media(theme, new)
    backgrounds = list((theme / "backgrounds").iterdir())
    assert [p.name for p in backgrounds] == ["new.jpg"]


# ── setter ───────────────────────────────────────────────────────────────


def _ctx(tmp_path: Path, *, omarchy: bool = True, animated: bool = False) -> WallpaperContext:
    img = tmp_path / "w.jpg"
    img.write_bytes(b"x")
    return WallpaperContext(
        path=img,
        de=DesktopEnvironment(hyprland=True, omarchy=omarchy),
        ops=OpsConfig(),
    )


def test_setter_applies_only_on_omarchy(tmp_path):
    s = OmarchySetter()
    assert s.applies(_ctx(tmp_path, omarchy=True))
    assert not s.applies(_ctx(tmp_path, omarchy=False))


def test_setter_static_runs_bg_set(tmp_path):
    with patch("wallpaperctl.set.omarchy.run_omarchy") as run_mock, patch(
        "wallpaperctl.set.omarchy.motion_wallpaper_stop", return_value=True
    ):
        run_mock.return_code = 0
        run_mock.return_value.returncode = 0
        assert OmarchySetter().set_wallpaper(_ctx(tmp_path))
        args = run_mock.call_args[0][0]
        assert args[:3] == ["theme", "bg", "set"]
        assert args[3].endswith("w.jpg")


def test_setter_static_failure_returns_false(tmp_path):
    with patch("wallpaperctl.set.omarchy.run_omarchy") as run_mock, patch(
        "wallpaperctl.set.omarchy.motion_wallpaper_stop", return_value=True
    ):
        run_mock.return_value.returncode = 1
        assert not OmarchySetter().set_wallpaper(_ctx(tmp_path))


def test_setter_animated_uses_motion_wallpaper(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"v")
    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"f")
    ctx = WallpaperContext(
        path=video,
        de=DesktopEnvironment(hyprland=True, omarchy=True),
        ops=OpsConfig(),
        static_path=frame,
    )
    assert ctx.is_animated

    with (
        patch("wallpaperctl.set.omarchy.run_omarchy") as run_mock,
        patch("wallpaperctl.set.omarchy.motion_wallpaper_play", return_value=True) as play,
    ):
        run_mock.return_value.returncode = 0
        assert OmarchySetter().set_wallpaper(ctx)
        play.assert_called_once()
        # video passed to play, still passed to bg set
        assert play.call_args[0][0] == video
        assert run_mock.call_args[0][0][2] == "set"


def test_setter_animated_failure_falls_back(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"v")
    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"f")
    ctx = WallpaperContext(
        path=video,
        de=DesktopEnvironment(hyprland=True, omarchy=True),
        ops=OpsConfig(),
        static_path=frame,
    )

    with patch("wallpaperctl.set.omarchy.run_omarchy") as run_mock, patch(
        "wallpaperctl.set.omarchy.motion_wallpaper_play", return_value=False
    ):
        run_mock.return_value.returncode = 0
        assert not OmarchySetter().set_wallpaper(ctx)


# ── theme op gating + run ────────────────────────────────────────────────


def test_op_disabled_when_other_theme_active(monkeypatch, tmp_path):
    _fake_home(monkeypatch, tmp_path)
    _theme_state(tmp_path, "andrath-terminal")
    op = OmarchyThemeOp()
    ctx = _ctx(tmp_path)
    assert not op.enabled(ctx)


def test_op_enabled_when_dynamic_active(monkeypatch, tmp_path):
    _fake_home(monkeypatch, tmp_path)
    _theme_state(tmp_path, THEME_SLUG)
    (tmp_path / ".config" / "omarchy").mkdir(parents=True)
    with patch("wallpaperctl.omarchy.have", return_value=True):
        assert OmarchyThemeOp().enabled(_ctx(tmp_path))


def test_op_disabled_via_config(monkeypatch, tmp_path):
    _fake_home(monkeypatch, tmp_path)
    _theme_state(tmp_path, THEME_SLUG)
    ctx = _ctx(tmp_path)
    ctx.ops.enable_omarchy = False
    assert not OmarchyThemeOp().enabled(ctx)


def test_op_run_writes_colors_and_refreshes(monkeypatch, tmp_path):
    _fake_home(monkeypatch, tmp_path)
    _theme_state(tmp_path, THEME_SLUG)
    wal = tmp_path / ".cache" / "wal"
    wal.mkdir(parents=True)
    (wal / "colors.json").write_text(json.dumps(_palette()), encoding="utf-8")

    runs: list[list[str]] = []

    def fake_run_omarchy(args, **kwargs):
        runs.append(args)
        result = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        return result

    with (
        patch("wallpaperctl.theme.omarchy.load_colors_json", return_value=_palette()),
        patch("wallpaperctl.theme.omarchy.run_omarchy", side_effect=fake_run_omarchy),
        patch("wallpaperctl.theme.omarchy.omarchy_available", return_value=True),
    ):
        op = OmarchyThemeOp()
        ctx = _ctx(tmp_path)
        assert op.run(ctx)

    theme_dir = tmp_path / ".config" / "omarchy" / "themes" / THEME_SLUG
    assert (theme_dir / "colors.toml").is_file()
    assert (theme_dir / "backgrounds" / "w.jpg").is_file()
    assert runs == [["theme", "refresh"]]


def test_op_run_falls_back_to_theme_set(monkeypatch, tmp_path):
    _fake_home(monkeypatch, tmp_path)
    _theme_state(tmp_path, THEME_SLUG)

    calls: list[tuple[list[str], dict | None]] = []

    def fake_run_omarchy(args, *, timeout=30, env_extra=None):
        calls.append((args, env_extra))
        rc = 1 if args[:2] == ["theme", "refresh"] else 0
        return type("R", (), {"returncode": rc, "stdout": "", "stderr": ""})()

    with (
        patch("wallpaperctl.theme.omarchy.load_colors_json", return_value=_palette()),
        patch("wallpaperctl.theme.omarchy.run_omarchy", side_effect=fake_run_omarchy),
        patch("wallpaperctl.theme.omarchy.omarchy_available", return_value=True),
    ):
        assert OmarchyThemeOp().run(_ctx(tmp_path))

    assert calls[0][0] == ["theme", "refresh"]
    assert calls[1][0] == ["theme", "set", THEME_SLUG]
    assert calls[1][1] == {"OMARCHY_THEME_SKIP_BACKGROUND": "1"}


def test_op_run_without_palette_fails(monkeypatch, tmp_path):
    _fake_home(monkeypatch, tmp_path)
    _theme_state(tmp_path, THEME_SLUG)
    with patch("wallpaperctl.theme.omarchy.load_colors_json", return_value=None):
        assert not OmarchyThemeOp().run(_ctx(tmp_path))


def test_op_run_skips_refresh_when_palette_unchanged(monkeypatch, tmp_path):
    _fake_home(monkeypatch, tmp_path)
    _theme_state(tmp_path, THEME_SLUG)

    runs: list[list[str]] = []

    def fake_run_omarchy(args, **kwargs):
        runs.append(args)
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    with (
        patch("wallpaperctl.theme.omarchy.load_colors_json", return_value=_palette()),
        patch("wallpaperctl.theme.omarchy.run_omarchy", side_effect=fake_run_omarchy),
        patch("wallpaperctl.theme.omarchy.omarchy_available", return_value=True),
    ):
        op = OmarchyThemeOp()
        ctx = _ctx(tmp_path)
        # First run writes the palette and refreshes.
        assert op.run(ctx)
        assert runs == [["theme", "refresh"]]
        # Second run with the same palette: refresh skipped.
        assert op.run(ctx)
        assert runs == [["theme", "refresh"]]


def test_op_run_refresh_disabled_stages_only(monkeypatch, tmp_path):
    _fake_home(monkeypatch, tmp_path)
    _theme_state(tmp_path, THEME_SLUG)

    with (
        patch("wallpaperctl.theme.omarchy.load_colors_json", return_value=_palette()),
        patch("wallpaperctl.theme.omarchy.run_omarchy") as run_mock,
        patch("wallpaperctl.theme.omarchy.omarchy_available", return_value=True),
    ):
        ctx = _ctx(tmp_path)
        ctx.ops.omarchy_refresh_apps = False
        assert OmarchyThemeOp().run(ctx)
        run_mock.assert_not_called()
        theme_dir = tmp_path / ".config" / "omarchy" / "themes" / THEME_SLUG
        assert (theme_dir / "colors.toml").is_file()


# ── setup bootstrap ──────────────────────────────────────────────────────


def test_setup_requires_omarchy(monkeypatch, capsys):
    with patch("wallpaperctl.setup.omarchy_bootstrap.omarchy_available", return_value=False):
        assert ob.bootstrap_omarchy(yes=True) == 1
    assert "Omarchy was not detected" in capsys.readouterr().out


def test_setup_creates_theme_once(monkeypatch, tmp_path, capsys):
    _fake_home(monkeypatch, tmp_path)
    wal = tmp_path / ".cache" / "wal"
    wal.mkdir(parents=True)
    (wal / "colors.json").write_text(json.dumps(_palette()), encoding="utf-8")

    with (
        patch(
            "wallpaperctl.setup.omarchy_bootstrap.omarchy_available", return_value=True
        ),
        patch(
            "wallpaperctl.setup.omarchy_bootstrap.is_omarchy_shell_running",
            return_value=True,
        ),
        patch("wallpaperctl.setup.omarchy_bootstrap.have", return_value=True),
        patch("wallpaperctl.setup.omarchy_bootstrap.bootstrap_wallust", return_value=0),
        patch("wallpaperctl.setup.omarchy_bootstrap.run_omarchy") as run_mock,
    ):
        run_mock.return_value.returncode = 0
        assert ob.bootstrap_omarchy(yes=True) == 0
        theme_dir = tmp_path / ".config" / "omarchy" / "themes" / THEME_SLUG
        assert (theme_dir / "colors.toml").is_file()
        assert (theme_dir / "backgrounds").is_dir()
        calls = [c.args[0] for c in run_mock.call_args_list]
        # theme set invoked with the slug, switcher cache warmed after
        assert ["theme", "set", THEME_SLUG] in calls
        assert calls[-1] == ["theme", "switcher", "--preload"]

        # second run must not recreate (colors.toml kept)
        before = (theme_dir / "colors.toml").read_text(encoding="utf-8")
        assert ob.bootstrap_omarchy(yes=True) == 0
        after = (theme_dir / "colors.toml").read_text(encoding="utf-8")
        assert before == after


def test_setup_fails_without_wallust_and_no_pm(monkeypatch, tmp_path, capsys):
    _fake_home(monkeypatch, tmp_path)
    with (
        patch("wallpaperctl.setup.omarchy_bootstrap.omarchy_available", return_value=True),
        patch("wallpaperctl.setup.omarchy_bootstrap.have", return_value=False),
        patch("wallpaperctl.setup.omarchy_bootstrap.detect_package_manager", return_value=None),
    ):
        assert ob.bootstrap_omarchy(yes=True) == 1
    assert "wallust" in capsys.readouterr().out


def test_ensure_skeleton_fallback_palette(monkeypatch, tmp_path):
    _fake_home(monkeypatch, tmp_path)
    created = ensure_theme_skeleton(tmp_path / "theme")
    assert created
    text = (tmp_path / "theme" / "colors.toml").read_text(encoding="utf-8")
    assert 'mode = "dark"' in text
    assert 'accent = "#' in text
    # switcher lists only themes with a preview — must exist even without a wallpaper
    assert (tmp_path / "theme" / "preview.png").is_file()
    # second call: already exists
    assert not ensure_theme_skeleton(tmp_path / "theme")


def test_palette_preview_renders_swatch(monkeypatch, tmp_path):
    _fake_home(monkeypatch, tmp_path)
    theme = tmp_path / "theme"
    theme.mkdir()
    assert tom.write_palette_preview(theme, build_colors_mapping(_palette()))
    img = (theme / "preview.png").is_file()
    assert img


# ── opencode plugin clash ────────────────────────────────────────────────


def test_setup_removes_wallust_opencode_plugin(monkeypatch, tmp_path, capsys):
    _fake_home(monkeypatch, tmp_path)
    wal = tmp_path / ".cache" / "wal"
    wal.mkdir(parents=True)
    (wal / "colors.json").write_text(json.dumps(_palette()), encoding="utf-8")

    cfg = tmp_path / ".config" / "opencode"
    (cfg / "plugins").mkdir(parents=True)
    (cfg / "plugins" / "wallust-hot-reload.ts").write_text("x", encoding="utf-8")
    (cfg / "tui.json").write_text(
        json.dumps(
            {
                "theme": "wallust",
                "plugin": ["./plugins/wallust-hot-reload.ts", "other.ts"],
            }
        ),
        encoding="utf-8",
    )

    with (
        patch("wallpaperctl.setup.omarchy_bootstrap.omarchy_available", return_value=True),
        patch(
            "wallpaperctl.setup.omarchy_bootstrap.is_omarchy_shell_running",
            return_value=True,
        ),
        patch("wallpaperctl.setup.omarchy_bootstrap.have", return_value=True),
        patch("wallpaperctl.setup.omarchy_bootstrap.bootstrap_wallust", return_value=0) as bw,
        patch("wallpaperctl.setup.omarchy_bootstrap.run_omarchy") as run_mock,
    ):
        run_mock.return_value.returncode = 0
        assert ob.bootstrap_omarchy(yes=True) == 0
        # wallust bootstrap must not reinstall the plugin
        assert bw.call_args.kwargs.get("skip_opencode") is True

        assert not (cfg / "plugins" / "wallust-hot-reload.ts").exists()
        tui = json.loads((cfg / "tui.json").read_text(encoding="utf-8"))
        assert "./plugins/wallust-hot-reload.ts" not in tui["plugin"]
        assert "other.ts" in tui["plugin"]
        assert tui.get("theme") == "omarchy"


def test_remove_opencode_plugin_noop_when_absent(monkeypatch, tmp_path, capsys):
    _fake_home(monkeypatch, tmp_path)
    from wallpaperctl.setup.opencode_bootstrap import remove_opencode_plugin

    assert not remove_opencode_plugin()


def test_remove_opencode_plugin_fixes_orphaned_theme(monkeypatch, tmp_path):
    _fake_home(monkeypatch, tmp_path)
    from wallpaperctl.setup.opencode_bootstrap import remove_opencode_plugin

    cfg = tmp_path / ".config" / "opencode"
    cfg.mkdir(parents=True)
    (cfg / "tui.json").write_text(
        json.dumps({"theme": "wallust", "plugin": ["other.ts"]}),
        encoding="utf-8",
    )

    assert remove_opencode_plugin()
    tui = json.loads((cfg / "tui.json").read_text(encoding="utf-8"))
    assert tui["theme"] == "omarchy"
    assert tui["plugin"] == ["other.ts"]


def test_wallust_bootstrap_skips_opencode_on_omarchy(monkeypatch, tmp_path):
    _fake_home(monkeypatch, tmp_path)
    from wallpaperctl.setup import wallust_bootstrap as wb

    pkg = tmp_path / "pkg"
    (pkg / "templates").mkdir(parents=True)
    (pkg / "wallust.toml").write_text("", encoding="utf-8")

    with (
        patch.object(wb, "_packaged_wallust_root", return_value=pkg),
        patch("wallpaperctl.setup.wallust_bootstrap.have", return_value=True),
        patch(
            "wallpaperctl.setup.wallust_bootstrap.shutil.which",
            return_value="/usr/bin/wallust",
        ),
        patch("wallpaperctl.omarchy.omarchy_available", return_value=True),
        patch("wallpaperctl.setup.opencode_bootstrap.bootstrap_opencode") as boot,
    ):
        wb.bootstrap_wallust(force=True, yes=True)
        boot.assert_not_called()


# ── motion wallpaper plugin ──────────────────────────────────────────────


def _plugin_list_stdout(entries):
    return json.dumps(entries)


def test_motion_plugin_present_and_enabled(monkeypatch, tmp_path):
    _fake_home(monkeypatch, tmp_path)
    with patch(
        "wallpaperctl.setup.omarchy_bootstrap.run_omarchy"
    ) as run_mock:
        run_mock.return_value.returncode = 0
        run_mock.return_value.stdout = _plugin_list_stdout(
            [{"id": "nosignal.motion-wallpaper", "enabled": True}]
        )
        from wallpaperctl.setup.omarchy_bootstrap import motion_plugin_status

        st = motion_plugin_status()
        assert st["installed"] and st["enabled"]


def test_motion_plugin_missing_gets_installed(monkeypatch, tmp_path, capsys):
    _fake_home(monkeypatch, tmp_path)

    def fake_run(args, **kwargs):
        if args[:2] == ["plugin", "list"]:
            return type("R", (), {"returncode": 0, "stdout": "[]", "stderr": ""})()
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    with patch(
        "wallpaperctl.setup.omarchy_bootstrap.run_omarchy", side_effect=fake_run
    ) as run_mock:
        from wallpaperctl.setup.omarchy_bootstrap import _ensure_motion_plugin

        assert _ensure_motion_plugin(yes=True)
        add_calls = [
            c.args[0]
            for c in run_mock.call_args_list
            if c.args[0][0] == "plugin" and c.args[0][1] == "add"
        ]
        assert add_calls and add_calls[0][2].endswith(".git") and "--enable" in add_calls[0]


def test_motion_plugin_decline_is_soft(monkeypatch, tmp_path, capsys):
    _fake_home(monkeypatch, tmp_path)

    def fake_run(args, **kwargs):
        if args[:2] == ["plugin", "list"]:
            return type("R", (), {"returncode": 0, "stdout": "[]", "stderr": ""})()
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    with (
        patch("wallpaperctl.setup.omarchy_bootstrap.run_omarchy", side_effect=fake_run),
        patch("builtins.input", return_value="n"),
    ):
        from wallpaperctl.setup.omarchy_bootstrap import _ensure_motion_plugin

        assert not _ensure_motion_plugin(yes=False)
        out = capsys.readouterr().out
        assert "omarchy plugin add" in out


def test_motion_plugin_mgmt_unavailable_is_soft(monkeypatch, tmp_path, capsys):
    _fake_home(monkeypatch, tmp_path)
    with patch(
        "wallpaperctl.setup.omarchy_bootstrap.run_omarchy"
    ) as run_mock:
        run_mock.return_value.returncode = 1
        run_mock.return_value.stdout = ""
        from wallpaperctl.setup.omarchy_bootstrap import _ensure_motion_plugin

        assert not _ensure_motion_plugin(yes=True)
        assert "plugin management unavailable" in capsys.readouterr().out


# ── wallust / omarchy theming hand-off ───────────────────────────────────


def test_omarchy_wallust_config_vendored():
    import tomllib

    from wallpaperctl.setup.wallust_bootstrap import _packaged_wallust_root

    pkg = _packaged_wallust_root()
    assert pkg is not None
    src = pkg / "wallust-omarchy.toml"
    assert src.is_file()
    data = tomllib.loads(src.read_text(encoding="utf-8"))
    assert "hooks" not in data
    tpl = data.get("templates", {})
    targets = " ".join(entry["target"] for entry in tpl.values())
    # omarchy-managed targets must not be wallust-rendered
    for banned in ("kitty", "btop", "opencode", "hypr", "waybar", "cosmic"):
        assert banned not in targets
    # apps omarchy does not theme stay palette-driven (incl. starship)
    for kept in ("colors.json", "starship", "gtk-3.0"):
        assert kept in targets


def test_install_omarchy_wallust_config(monkeypatch, tmp_path):
    from wallpaperctl.setup.wallust_bootstrap import (
        install_omarchy_wallust_config,
        omarchy_config_installed,
    )

    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = tmp_path / ".config" / "wallust" / "wallust.toml"

    assert install_omarchy_wallust_config() == 0
    assert cfg.is_file()
    assert omarchy_config_installed()
    # idempotent: no extra backup
    assert install_omarchy_wallust_config() == 0
    assert not list(tmp_path.glob(".config/wallust/*.bak-wallpaperctl"))

    # differing config gets backed up and replaced
    cfg.write_text('backend = "full"\n', encoding="utf-8")
    assert not omarchy_config_installed()
    assert install_omarchy_wallust_config() == 0
    assert omarchy_config_installed()
    backups = list((tmp_path / ".config" / "wallust").glob("*.bak-wallpaperctl"))
    assert len(backups) == 1 and "full" in backups[0].read_text(encoding="utf-8")


def test_setup_swaps_wallust_config(monkeypatch, tmp_path):
    _fake_home(monkeypatch, tmp_path)
    wal = tmp_path / ".cache" / "wal"
    wal.mkdir(parents=True)
    (wal / "colors.json").write_text(json.dumps(_palette()), encoding="utf-8")

    with (
        patch("wallpaperctl.setup.omarchy_bootstrap.omarchy_available", return_value=True),
        patch(
            "wallpaperctl.setup.omarchy_bootstrap.is_omarchy_shell_running",
            return_value=True,
        ),
        patch("wallpaperctl.setup.omarchy_bootstrap.have", return_value=True),
        patch("wallpaperctl.setup.omarchy_bootstrap.bootstrap_wallust", return_value=0),
        patch("wallpaperctl.setup.omarchy_bootstrap.run_omarchy") as run_mock,
    ):
        run_mock.return_value.returncode = 0
        run_mock.return_value.stdout = "[]"
        assert ob.bootstrap_omarchy(yes=True) == 0
        cfg = tmp_path / ".config" / "wallust" / "wallust.toml"
        assert cfg.is_file()
        assert "generate-wallust-theme" not in cfg.read_text(encoding="utf-8")
        assert "[hooks]" not in cfg.read_text(encoding="utf-8")


def test_op_run_signals_opencode_after_refresh(monkeypatch, tmp_path):
    _fake_home(monkeypatch, tmp_path)
    _theme_state(tmp_path, THEME_SLUG)

    runs: list[list[str]] = []

    def fake_run_omarchy(args, **kwargs):
        runs.append(args)
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    def fake_run(args, **kwargs):
        runs.append(list(args))
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    with (
        patch("wallpaperctl.theme.omarchy.load_colors_json", return_value=_palette()),
        patch("wallpaperctl.theme.omarchy.run_omarchy", side_effect=fake_run_omarchy),
        patch("wallpaperctl.theme.omarchy.omarchy_available", return_value=True),
        patch("wallpaperctl.theme.omarchy.have", side_effect=lambda c: c == "pkill"),
        patch("wallpaperctl.theme.omarchy.run", side_effect=fake_run),
    ):
        assert OmarchyThemeOp().run(_ctx(tmp_path))

    assert ["pkill", "-USR2", "-x", "opencode"] in runs


def test_op_run_no_signal_when_refresh_skipped(monkeypatch, tmp_path):
    _fake_home(monkeypatch, tmp_path)
    _theme_state(tmp_path, THEME_SLUG)
    wal = tmp_path / ".cache" / "wal"
    wal.mkdir(parents=True)
    (wal / "colors.json").write_text(json.dumps(_palette()), encoding="utf-8")

    runs: list[list[str]] = []

    def fake_run_omarchy(args, **kwargs):
        runs.append(args)
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    def fake_run(args, **kwargs):
        runs.append(list(args))
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    with (
        patch("wallpaperctl.theme.omarchy.load_colors_json", return_value=_palette()),
        patch("wallpaperctl.theme.omarchy.run_omarchy", side_effect=fake_run_omarchy),
        patch("wallpaperctl.theme.omarchy.omarchy_available", return_value=True),
        patch("wallpaperctl.theme.omarchy.have", side_effect=lambda c: c == "pkill"),
        patch("wallpaperctl.theme.omarchy.run", side_effect=fake_run),
    ):
        op = OmarchyThemeOp()
        ctx = _ctx(tmp_path)
        assert op.run(ctx)  # first run writes + refreshes
        assert ["pkill", "-USR2", "-x", "opencode"] in runs
        assert op.run(ctx)  # same palette → refresh skipped → no signal
        assert runs.count(["pkill", "-USR2", "-x", "opencode"]) == 1


# ── opencode theme publishing (hashed name) ──────────────────────────────


def test_fnv1a8_matches_plugin_hash():
    # vector produced by omarchy-theme.ts's contentHash() (node Math.imul)
    assert tom._fnv1a8("accent-test") == "abaacf76"


def test_publish_opencode_theme_stages_hash_and_selects(monkeypatch, tmp_path):
    _fake_home(monkeypatch, tmp_path)
    themes = tmp_path / ".config" / "opencode" / "themes"
    themes.mkdir(parents=True)
    content = '{"theme": {"primary": "#123456"}}'
    (themes / "omarchy.json").write_text(content, encoding="utf-8")
    (themes / "omarchy-deadbeef.json").write_text("stale", encoding="utf-8")
    tui = tmp_path / ".config" / "opencode" / "tui.json"
    tui.write_text(json.dumps({"theme": "omarchy", "plugin": ["x.ts"]}), encoding="utf-8")

    tom.OmarchyThemeOp()._publish_opencode_theme(_ctx(tmp_path))

    expected = f"omarchy-{tom._fnv1a8(content)}"
    assert (themes / f"{expected}.json").is_file()
    tui_data = json.loads(tui.read_text(encoding="utf-8"))
    assert tui_data["theme"] == expected
    assert tui_data["plugin"] == ["x.ts"]


def test_publish_keeps_recent_hashed_themes(monkeypatch, tmp_path):
    # a session may still be selected on an older hash — do not delete it
    _fake_home(monkeypatch, tmp_path)
    themes = tmp_path / ".config" / "opencode" / "themes"
    themes.mkdir(parents=True)
    content = '{"theme": {"primary": "#123456"}}'
    (themes / "omarchy.json").write_text(content, encoding="utf-8")
    for i, name in enumerate(("omarchy-11111111", "omarchy-22222222", "omarchy-33333333")):
        p = themes / f"{name}.json"
        p.write_text("old", encoding="utf-8")
        import os

        os.utime(p, (100000 + i, 100000 + i))  # oldest first

    tom.OmarchyThemeOp()._publish_opencode_theme(_ctx(tmp_path))

    remaining = sorted(p.name for p in themes.glob("omarchy-*.json"))
    # current + 2 most recent kept, oldest pruned
    assert f"omarchy-{tom._fnv1a8(content)}.json" in remaining
    assert "omarchy-33333333.json" in remaining
    assert "omarchy-22222222.json" in remaining
    assert "omarchy-11111111.json" not in remaining


def test_publish_opencode_theme_noop_when_selected(monkeypatch, tmp_path):
    _fake_home(monkeypatch, tmp_path)
    themes = tmp_path / ".config" / "opencode" / "themes"
    themes.mkdir(parents=True)
    content = '{"theme": {"primary": "#123456"}}'
    (themes / "omarchy.json").write_text(content, encoding="utf-8")
    tui = tmp_path / ".config" / "opencode" / "tui.json"
    name = f"omarchy-{tom._fnv1a8(content)}"
    (themes / f"{name}.json").write_text(content, encoding="utf-8")
    tui.write_text(json.dumps({"theme": name}), encoding="utf-8")

    tom.OmarchyThemeOp()._publish_opencode_theme(_ctx(tmp_path))
    assert json.loads(tui.read_text(encoding="utf-8"))["theme"] == name


def test_op_run_selects_hashed_opencode_theme(monkeypatch, tmp_path):
    _fake_home(monkeypatch, tmp_path)
    _theme_state(tmp_path, THEME_SLUG)
    wal = tmp_path / ".cache" / "wal"
    wal.mkdir(parents=True)
    (wal / "colors.json").write_text(json.dumps(_palette()), encoding="utf-8")

    def fake_run_omarchy(args, **kwargs):
        # emulate omarchy-theme-set + -opencode: render staged theme, then
        # copy it to the live opencode themes dir
        staged = (
            tmp_path / ".local" / "state" / "omarchy" / "current" / "theme" / "opencode.json"
        )
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_text(json.dumps({"theme": {"primary": "#abcdef"}}), encoding="utf-8")
        live_dir = tmp_path / ".config" / "opencode" / "themes"
        live_dir.mkdir(parents=True, exist_ok=True)
        (live_dir / "omarchy.json").write_text(
            json.dumps({"theme": {"primary": "#abcdef"}}), encoding="utf-8"
        )
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    with (
        patch("wallpaperctl.theme.omarchy.load_colors_json", return_value=_palette()),
        patch("wallpaperctl.theme.omarchy.run_omarchy", side_effect=fake_run_omarchy),
        patch("wallpaperctl.theme.omarchy.omarchy_available", return_value=True),
    ):
        assert OmarchyThemeOp().run(_ctx(tmp_path))

    tui = json.loads(
        (tmp_path / ".config" / "opencode" / "tui.json").read_text(encoding="utf-8")
    )
    assert tui["theme"].startswith("omarchy-") and len(tui["theme"]) == len("omarchy") + 8 + 1


# ── registration ─────────────────────────────────────────────────────────


def test_setter_registered_before_animated():
    from wallpaperctl.set.runner import SETTERS

    names = [s.name for s in SETTERS]
    assert names.index("omarchy") < names.index("animated")
    assert names.index("omarchy") < names.index("hyprland")


def test_theme_op_registered_after_wallust():
    from wallpaperctl.theme.runner import list_ops

    ops = list_ops()
    assert ops.index("wallust") < ops.index("omarchy")
