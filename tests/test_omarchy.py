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
    apply_shell_theme_live,
    current_theme_name,
    is_dynamic_theme_active,
    is_omarchy_session,
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
    """Never let tests talk to a live omarchy-shell or signal TUI agents.

    Individual tests may re-patch these; the stub only guarantees that an
    un-mocked code path cannot SIGUSR2/SIGUSR1 the developer's live session
    or issue shell IPC.
    """
    monkeypatch.setattr(
        "wallpaperctl.theme.omarchy.apply_shell_theme_live", lambda *a, **k: True
    )
    monkeypatch.setattr(
        "wallpaperctl.omarchy_watch.ensure_watch_running", lambda: None
    )
    monkeypatch.setattr(
        "wallpaperctl.omarchy_watch.snapshot_monitor_transforms", lambda **k: []
    )
    monkeypatch.setattr(
        "wallpaperctl.omarchy_watch.restore_monitor_transforms", lambda s: True
    )
    monkeypatch.setattr(
        "wallpaperctl.omarchy_watch.suppress_layout_rebind", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "wallpaperctl.theme.omarchy.have",
        lambda cmd: False,
    )
    monkeypatch.setattr("time.sleep", lambda seconds: None)

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


def test_is_omarchy_session_ignores_stray_config_dir(monkeypatch, tmp_path):
    _fake_home(monkeypatch, tmp_path)
    (tmp_path / ".config" / "omarchy").mkdir(parents=True)
    with (
        patch("wallpaperctl.omarchy.is_omarchy_shell_running", return_value=False),
        patch("wallpaperctl.omarchy.have", return_value=False),
    ):
        assert not is_omarchy_session()
    _theme_state(tmp_path, THEME_SLUG)
    with (
        patch("wallpaperctl.omarchy.is_omarchy_shell_running", return_value=False),
        patch("wallpaperctl.omarchy.have", side_effect=lambda c: c == "omarchy"),
    ):
        assert is_omarchy_session()


def test_apply_shell_theme_live_encodes_payload(tmp_path):
    colors = tmp_path / "colors.toml"
    colors.write_text('accent = "#ff0000"\n', encoding="utf-8")
    captured: list[list[str]] = []

    def fake_ipc(args, **kwargs):
        captured.append(args)
        return True

    with patch("wallpaperctl.omarchy.shell_ipc", side_effect=fake_ipc):
        assert apply_shell_theme_live(colors)
    assert captured[0][:2] == ["shell", "applyTheme"]
    import base64

    assert base64.b64decode(captured[0][2]).decode() == 'accent = "#ff0000"\n'
    assert captured[0][3] == ""


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
        "wallpaperctl.set.omarchy.motion_wallpaper_playing", return_value=False
    ), patch("wallpaperctl.set.omarchy.motion_wallpaper_stop") as stop:
        run_mock.return_value.returncode = 0
        assert OmarchySetter().set_wallpaper(_ctx(tmp_path))
        args = run_mock.call_args[0][0]
        assert args[:3] == ["theme", "bg", "set"]
        assert args[3].endswith("w.jpg")
        stop.assert_not_called()


def test_setter_static_stops_motion_only_when_playing(tmp_path):
    with patch("wallpaperctl.set.omarchy.run_omarchy") as run_mock, patch(
        "wallpaperctl.set.omarchy.motion_wallpaper_playing", return_value=True
    ), patch("wallpaperctl.set.omarchy.motion_wallpaper_stop") as stop:
        run_mock.return_value.returncode = 0
        assert OmarchySetter().set_wallpaper(_ctx(tmp_path))
        stop.assert_called_once()


def test_setter_static_failure_returns_false(tmp_path):
    with patch("wallpaperctl.set.omarchy.run_omarchy") as run_mock, patch(
        "wallpaperctl.set.omarchy.motion_wallpaper_playing", return_value=False
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


def test_setter_animated_plays_even_when_dynamic_theme(tmp_path):
    """Video play is IPC, like andrath-terminal — not a theme-set hook."""
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

    with (
        patch("wallpaperctl.set.omarchy.run_omarchy") as run_mock,
        patch("wallpaperctl.set.omarchy.motion_wallpaper_play", return_value=True) as play,
    ):
        run_mock.return_value.returncode = 0
        assert OmarchySetter().set_wallpaper(ctx)
        play.assert_called_once()
        assert play.call_args[0][0] == video
        assert run_mock.call_args[0][0][:3] == ["theme", "bg", "set"]


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

    with (
        patch("wallpaperctl.theme.omarchy.load_colors_json", return_value=_palette()),
        patch("wallpaperctl.theme.omarchy.omarchy_available", return_value=True),
    ):
        op = OmarchyThemeOp()
        ctx = _ctx(tmp_path)
        assert op.run(ctx)

    theme_dir = tmp_path / ".config" / "omarchy" / "themes" / THEME_SLUG
    assert (theme_dir / "colors.toml").is_file()
    assert (theme_dir / "backgrounds" / "w.jpg").is_file()


def test_op_run_skips_compositor_reload_when_templates_work(monkeypatch, tmp_path):
    _fake_home(monkeypatch, tmp_path)
    _theme_state(tmp_path, THEME_SLUG)
    runs: list[list[str]] = []

    def fake_run(args, **kwargs):
        runs.append(list(args))
        if list(args)[:1] == ["omarchy-theme-set-templates"]:
            nxt = tmp_path / ".local" / "state" / "omarchy" / "current" / "next-theme"
            nxt.mkdir(parents=True, exist_ok=True)
            (nxt / "hyprland.lua").write_text("hl.config({})\n", encoding="utf-8")
        return type("R", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()

    with (
        patch("wallpaperctl.theme.omarchy.load_colors_json", return_value=_palette()),
        patch("wallpaperctl.theme.omarchy.omarchy_available", return_value=True),
        patch("wallpaperctl.theme.omarchy.have", return_value=True),
        patch("wallpaperctl.theme.omarchy.run", side_effect=fake_run),
    ):
        assert OmarchyThemeOp().run(_ctx(tmp_path))
    assert ["omarchy-theme-set-templates"] in runs
    assert not any(c[:1] == ["hyprctl"] and c[1] == "eval" for c in runs)
    assert ["omarchy-restart-hyprctl"] not in runs
    assert ["omarchy-hook", "theme-set", THEME_SLUG] not in runs
    assert ["omarchy-restart-terminal"] in runs


def test_hypr_keywords_from_mapping():
    mapping = {
        "hyprland_active_border": "rgba(804c49ee) rgba(877485ee) 45deg",
        "hyprland_inactive_border": "rgba(595959aa)",
    }
    pairs = dict(tom._hypr_keywords_from_mapping(mapping))
    assert pairs["general:col.active_border"] == "rgba(804c49ee) rgba(877485ee) 45deg"
    assert pairs["group:col.border_active"] == "rgba(804c49ee) rgba(877485ee) 45deg"
    assert pairs["general:col.inactive_border"] == "rgba(595959aa)"
    assert pairs["group:col.border_inactive"] == "rgba(595959aa)"


def test_retint_updates_kitty_but_does_not_write_hyprland_lua(
    monkeypatch, tmp_path
):
    """Writing hyprland.lua makes Hyprland auto-reload (monitors.lua / landscape)."""
    _fake_home(monkeypatch, tmp_path)
    _theme_state(tmp_path, THEME_SLUG)
    current = tmp_path / ".local" / "state" / "omarchy" / "current" / "theme"
    current.mkdir(parents=True)
    (current / "kitty.conf").write_text("foreground #oldold\n", encoding="utf-8")
    (current / "hyprland.lua").write_text("-- keep\n", encoding="utf-8")
    (current / "gum_env.lua").write_text("-- keep gum\n", encoding="utf-8")
    (current / "alacritty.toml").write_text("# stale\n", encoding="utf-8")

    theme_dir = tmp_path / ".config" / "omarchy" / "themes" / THEME_SLUG
    theme_dir.mkdir(parents=True)
    (theme_dir / "colors.toml").write_text('accent = "#ff0000"\n', encoding="utf-8")
    (theme_dir / "backgrounds").mkdir()

    mapping = {
        "hyprland_active_border": "rgba(ff0000ee) rgba(ffaaaaee) 45deg",
    }
    runs: list[list[str]] = []

    def fake_run(args, **kwargs):
        runs.append(list(args))
        if list(args)[:1] == ["omarchy-theme-set-templates"]:
            nxt = tmp_path / ".local" / "state" / "omarchy" / "current" / "next-theme"
            nxt.mkdir(parents=True, exist_ok=True)
            (nxt / "kitty.conf").write_text("foreground #newnew\n", encoding="utf-8")
            (nxt / "hyprland.lua").write_text("-- generated lua must not land\n", encoding="utf-8")
            (nxt / "gum_env.lua").write_text("-- generated gum must not land\n", encoding="utf-8")
        return type("R", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()

    with (
        patch("wallpaperctl.theme.omarchy.have", return_value=True),
        patch("wallpaperctl.theme.omarchy.run", side_effect=fake_run),
    ):
        assert tom.retint_without_compositor_reload(
            theme_dir, THEME_SLUG, mapping
        )

    assert (current / "kitty.conf").read_text(encoding="utf-8") == "foreground #newnew\n"
    assert (current / "hyprland.lua").read_text(encoding="utf-8") == "-- keep\n"
    assert (current / "gum_env.lua").read_text(encoding="utf-8") == "-- keep gum\n"
    assert (current / "alacritty.toml").read_text(encoding="utf-8") == "# stale\n"
    assert any(
        c[:3] == ["hyprctl", "keyword", "general:col.active_border"] for c in runs
    )
    assert ["omarchy-restart-terminal"] in runs
    assert ["omarchy-restart-hyprctl"] not in runs
    assert not any(c[:1] == ["omarchy-hook"] for c in runs)


def test_op_run_never_falls_back_to_theme_set(monkeypatch, tmp_path):
    """Missing templates is a soft skip — not `omarchy theme set` (hypr reload)."""
    _fake_home(monkeypatch, tmp_path)
    _theme_state(tmp_path, THEME_SLUG)

    with (
        patch("wallpaperctl.theme.omarchy.load_colors_json", return_value=_palette()),
        patch("wallpaperctl.omarchy.run_omarchy") as run_mock,
        patch("wallpaperctl.theme.omarchy.omarchy_available", return_value=True),
    ):
        assert OmarchyThemeOp().run(_ctx(tmp_path))
    run_mock.assert_not_called()


def test_op_run_without_palette_fails(monkeypatch, tmp_path):
    _fake_home(monkeypatch, tmp_path)
    _theme_state(tmp_path, THEME_SLUG)
    with patch("wallpaperctl.theme.omarchy.load_colors_json", return_value=None):
        assert not OmarchyThemeOp().run(_ctx(tmp_path))


def test_op_run_skips_refresh_when_palette_unchanged(monkeypatch, tmp_path):
    _fake_home(monkeypatch, tmp_path)
    _theme_state(tmp_path, THEME_SLUG)

    with (
        patch("wallpaperctl.theme.omarchy.load_colors_json", return_value=_palette()),
        patch("wallpaperctl.omarchy.run_omarchy") as run_mock,
        patch("wallpaperctl.theme.omarchy.omarchy_available", return_value=True),
    ):
        op = OmarchyThemeOp()
        ctx = _ctx(tmp_path)
        assert op.run(ctx)
        assert op.run(ctx)
        run_mock.assert_not_called()


def test_op_run_refresh_disabled_stages_only(monkeypatch, tmp_path):
    _fake_home(monkeypatch, tmp_path)
    _theme_state(tmp_path, THEME_SLUG)

    with (
        patch("wallpaperctl.theme.omarchy.load_colors_json", return_value=_palette()),
        patch("wallpaperctl.omarchy.run_omarchy") as run_mock,
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
        def fake_run(args, **kwargs):
            if args[:2] == ["theme", "set"] and len(args) > 2:
                _theme_state(tmp_path, args[2])
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        run_mock.side_effect = fake_run
        assert ob.bootstrap_omarchy(yes=True) == 0
        theme_dir = tmp_path / ".config" / "omarchy" / "themes" / THEME_SLUG
        assert (theme_dir / "colors.toml").is_file()
        assert (theme_dir / "backgrounds").is_dir()
        calls = [c.args[0] for c in run_mock.call_args_list]
        # theme set invoked with the slug, switcher cache warmed after
        assert ["theme", "set", THEME_SLUG] in calls
        assert calls[-1] == ["theme", "switcher", "--preload"]

        # second run must not recreate (colors.toml kept) or re-set the theme
        before = (theme_dir / "colors.toml").read_text(encoding="utf-8")
        run_mock.reset_mock()
        assert ob.bootstrap_omarchy(yes=True) == 0
        after = (theme_dir / "colors.toml").read_text(encoding="utf-8")
        assert before == after
        second = [c.args[0] for c in run_mock.call_args_list]
        assert ["theme", "set", THEME_SLUG] not in second
        assert ["theme", "switcher", "--preload"] not in second


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
        assert tui.get("theme") == "system"


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
    assert tui["theme"] == "system"
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
    ) as run_mock, patch(
        "wallpaperctl.setup.omarchy_bootstrap.qt_multimedia_present", return_value=True
    ):
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


# ── qt multimedia (motion plugin dependency) ─────────────────────────────


def test_qt_multimedia_present_skips_install():
    from wallpaperctl.setup import omarchy_bootstrap as obm

    with (
        patch.object(obm, "qt_multimedia_present", return_value=True),
        patch.object(obm, "detect_package_manager") as detect_mock,
    ):
        assert obm._ensure_qt_multimedia(yes=True)
        detect_mock.assert_not_called()


def test_qt_multimedia_missing_gets_installed(capsys):
    from wallpaperctl.setup import omarchy_bootstrap as obm
    from wallpaperctl.setup.packages import PackageManager

    pm = PackageManager(
        "pacman", "pacman", ["sudo", "pacman", "-S", "--needed", "--noconfirm"]
    )
    installed: list[tuple] = []

    def fake_install(pairs, _pm, *, yes):
        installed.extend(pairs)
        return 0

    with (
        patch.object(obm, "qt_multimedia_present", side_effect=[False, True]),
        patch.object(obm, "is_omarchy_shell_running", return_value=False),
        patch.object(obm, "detect_package_manager", return_value=pm),
        patch.object(obm, "install_system_packages", side_effect=fake_install),
    ):
        assert obm._ensure_qt_multimedia(yes=True)
    dep, pkg = installed[0]
    assert pkg == "qt6-multimedia"
    assert dep.id == "qt6-multimedia"
    assert "omarchy-restart-shell" not in capsys.readouterr().out


def test_qt_multimedia_missing_no_pm_is_soft(capsys):
    from wallpaperctl.setup import omarchy_bootstrap as obm

    with (
        patch.object(obm, "qt_multimedia_present", return_value=False),
        patch.object(obm, "detect_package_manager", return_value=None),
    ):
        assert not obm._ensure_qt_multimedia(yes=True)
    assert "qt6-multimedia" in capsys.readouterr().out


def test_qt_multimedia_install_failure_is_soft(capsys):
    from wallpaperctl.setup import omarchy_bootstrap as obm
    from wallpaperctl.setup.packages import PackageManager

    pm = PackageManager("pacman", "pacman", ["sudo", "pacman", "-S"])

    with (
        patch.object(obm, "qt_multimedia_present", return_value=False),
        patch.object(obm, "detect_package_manager", return_value=pm),
        patch.object(obm, "install_system_packages", return_value=1),
    ):
        assert not obm._ensure_qt_multimedia(yes=True)
    out = capsys.readouterr().out
    assert "mpvpaper" in out and "omarchy-restart-shell" in out


def test_qt_multimedia_present_qmake_root(tmp_path):
    from wallpaperctl.setup import omarchy_bootstrap as obm

    qml_root = tmp_path / "qml"
    (qml_root / "QtMultimedia").mkdir(parents=True)

    class R:
        returncode = 0
        stdout = f"{qml_root}\n"
        stderr = ""

    with (
        patch.object(obm, "have", side_effect=lambda c: c == "qmake6"),
        patch.object(obm, "run", return_value=R()),
    ):
        assert obm.qt_multimedia_present()

    # and absent when neither qmake6 nor fallback roots have the module
    with (
        patch.object(obm, "have", return_value=False),
        patch.object(obm, "_QML_FALLBACK_ROOTS", (str(tmp_path / "empty"),)),
    ):
        assert not obm.qt_multimedia_present()


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
    for banned in ("kitty", "btop", "opencode", "hypr", "waybar", "cosmic", "gtk-3.0", "gtk-4.0"):
        assert banned not in targets
    # apps omarchy does not theme stay palette-driven (incl. starship)
    for kept in ("colors.json", "starship"):
        assert kept in targets


def test_remove_omarchy_conflicts(monkeypatch, tmp_path, capsys):
    _fake_home(monkeypatch, tmp_path)
    gtk = tmp_path / ".config" / "gtk-4.0" / "gtk.css"
    gtk.parent.mkdir(parents=True)
    gtk.write_text("/* Generated by wallust - GTK-4.0 theme (ghostty) */\n", encoding="utf-8")
    keep = tmp_path / ".config" / "gtk-4.0" / "keep.css"
    keep.write_text("custom\n", encoding="utf-8")
    hp = tmp_path / ".config" / "hypr" / "hyprpaper.conf"
    hp.parent.mkdir(parents=True)
    hp.write_text("preload=/tmp/.cache/wallpaperctl/animated/x.png\n", encoding="utf-8")
    fc = tmp_path / ".local" / "share" / "themes" / "FlatColor"
    fc.mkdir(parents=True)
    (fc / "index.theme").write_text("x\n", encoding="utf-8")
    dark = tmp_path / ".local" / "share" / "themes" / "FlatColor-dark"
    dark.symlink_to("FlatColor")

    with patch.object(ob, "_drop_overlay_packages"):
        ob.remove_omarchy_conflicts()
    assert not gtk.exists()
    assert keep.exists()
    assert not hp.exists()
    assert not fc.exists()
    assert not dark.exists()


def test_leftover_overlay_packages(monkeypatch):
    def fake_have(name: str) -> bool:
        return name in {"hyprpaper", "xwinwrap"}

    monkeypatch.setattr(ob, "have", fake_have)
    assert ob.leftover_overlay_packages() == [
        "hyprpaper",
        "xwinwrap-git",
        "xwinwrap",
    ]


def test_drop_overlay_packages_calls_omarchy_pkg_drop(monkeypatch, capsys):
    monkeypatch.setattr(ob, "have", lambda name: name == "omarchy")
    monkeypatch.setattr(ob, "omarchy_env", lambda: {"PATH": "/usr/bin"})
    calls = {"n": 0}

    def leftover():
        calls["n"] += 1
        return ["hyprpaper", "mpvpaper"] if calls["n"] == 1 else []

    monkeypatch.setattr(ob, "leftover_overlay_packages", leftover)

    class _Proc:
        returncode = 0

    with patch("subprocess.run", return_value=_Proc()) as run_mock:
        ob._drop_overlay_packages()
    run_mock.assert_called_once()
    args = run_mock.call_args[0][0]
    assert args[:3] == ["omarchy", "pkg", "drop"]
    assert "hyprpaper" in args and "mpvpaper" in args
    assert "removed packages:" in capsys.readouterr().out


def test_remove_omarchy_conflicts_drops_overlay_packages(monkeypatch, tmp_path):
    _fake_home(monkeypatch, tmp_path)
    with patch.object(ob, "_drop_overlay_packages") as drop:
        ob.remove_omarchy_conflicts()
    drop.assert_called_once()


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


def test_install_omarchy_hooks_copies_motion_and_starship(monkeypatch, tmp_path):
    _fake_home(monkeypatch, tmp_path)
    with patch("wallpaperctl.util.run"):
        assert ob._install_omarchy_hooks() == 0
    dest = tmp_path / ".config" / "omarchy" / "hooks" / "theme-set.d"
    assert (dest / "wallpaperctl-motion").is_file()
    assert (dest / "wallpaperctl-starship").is_file()
    motion = (dest / "wallpaperctl-motion").read_text(encoding="utf-8")
    assert "motion-wallpaper" in motion and "stop" in motion
    # executable bit (setup chmod | 0o111)
    assert (dest / "wallpaperctl-motion").stat().st_mode & 0o111


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
        patch(
            "wallpaperctl.setup.omarchy_bootstrap.qt_multimedia_present",
            return_value=True,
        ),
        patch("wallpaperctl.setup.omarchy_bootstrap.run_omarchy") as run_mock,
    ):
        run_mock.return_value.returncode = 0
        run_mock.return_value.stdout = "[]"
        assert ob.bootstrap_omarchy(yes=True) == 0
        cfg = tmp_path / ".config" / "wallust" / "wallust.toml"
        assert cfg.is_file()
        assert "generate-wallust-theme" not in cfg.read_text(encoding="utf-8")
        assert "[hooks]" not in cfg.read_text(encoding="utf-8")


def test_op_run_does_not_re_signal_opencode(monkeypatch, tmp_path):
    # Live retint must not SIGUSR2 opencode (that double-flashes TUIs).
    _fake_home(monkeypatch, tmp_path)
    _theme_state(tmp_path, THEME_SLUG)

    runs: list[list[str]] = []

    def fake_run(args, **kwargs):
        runs.append(list(args))
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    with (
        patch("wallpaperctl.theme.omarchy.load_colors_json", return_value=_palette()),
        patch("wallpaperctl.theme.omarchy.omarchy_available", return_value=True),
        patch("wallpaperctl.theme.omarchy.have", return_value=True),
        patch("wallpaperctl.theme.omarchy.run", side_effect=fake_run),
    ):
        assert OmarchyThemeOp().run(_ctx(tmp_path))

    assert not any("pkill" in (c[0] if c else "") for c in runs)
    assert not any("opencode" in " ".join(c) for c in runs)
    assert ["omarchy-restart-opencode"] not in runs


def test_op_run_live_applies_shell_when_palette_changes(monkeypatch, tmp_path):
    _fake_home(monkeypatch, tmp_path)
    _theme_state(tmp_path, THEME_SLUG)
    live: list[Path] = []

    def fake_live(colors_file, shell_file=None, **kwargs):
        live.append(colors_file)
        return True

    with (
        patch("wallpaperctl.theme.omarchy.load_colors_json", return_value=_palette()),
        patch("wallpaperctl.omarchy.run_omarchy") as run_mock,
        patch("wallpaperctl.theme.omarchy.omarchy_available", return_value=True),
        patch("wallpaperctl.theme.omarchy.apply_shell_theme_live", side_effect=fake_live),
    ):
        op = OmarchyThemeOp()
        ctx = _ctx(tmp_path)
        assert op.run(ctx)
        assert live  # first write → live apply
        live.clear()
        assert op.run(ctx)  # same palette → skip live apply
        assert live == []
        run_mock.assert_not_called()


def test_op_run_applies_generated_shell_toml_not_previous(monkeypatch, tmp_path):
    _fake_home(monkeypatch, tmp_path)
    _theme_state(tmp_path, THEME_SLUG)
    current = tmp_path / ".local" / "state" / "omarchy" / "current" / "theme"
    current.mkdir(parents=True)
    (current / "shell.toml").write_text(
        '[bar]\nbackground = "#oldold"\n', encoding="utf-8"
    )
    live: list[tuple[Path, Path | None]] = []

    def fake_live(colors_file, shell_file=None, **kwargs):
        live.append((colors_file, shell_file))
        return True

    def fake_run(args, **kwargs):
        if list(args)[:1] == ["omarchy-theme-set-templates"]:
            nxt = tmp_path / ".local" / "state" / "omarchy" / "current" / "next-theme"
            nxt.mkdir(parents=True, exist_ok=True)
            (nxt / "shell.toml").write_text(
                '[bar]\nbackground = "#newnew"\n', encoding="utf-8"
            )
        return type("R", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()

    with (
        patch("wallpaperctl.theme.omarchy.load_colors_json", return_value=_palette()),
        patch("wallpaperctl.theme.omarchy.omarchy_available", return_value=True),
        patch("wallpaperctl.theme.omarchy.have", return_value=True),
        patch("wallpaperctl.theme.omarchy.run", side_effect=fake_run),
        patch("wallpaperctl.theme.omarchy.apply_shell_theme_live", side_effect=fake_live),
    ):
        assert OmarchyThemeOp().run(_ctx(tmp_path))

    assert live
    _colors, shell = live[0]
    assert shell is not None
    assert shell.read_text(encoding="utf-8") == '[bar]\nbackground = "#newnew"\n'


# ── opencode system-theme signalling ────────────────────────────────────


def test_op_run_leaves_tui_json_untouched(monkeypatch, tmp_path):
    # stock omarchy: opencode runs the terminal-adaptive "system" theme;
    # the theme op must not rewrite the theme selection
    _fake_home(monkeypatch, tmp_path)
    _theme_state(tmp_path, THEME_SLUG)
    tui = tmp_path / ".config" / "opencode" / "tui.json"
    tui.parent.mkdir(parents=True)
    tui.write_text(json.dumps({"theme": "system"}), encoding="utf-8")

    with (
        patch("wallpaperctl.theme.omarchy.load_colors_json", return_value=_palette()),
        patch("wallpaperctl.theme.omarchy.omarchy_available", return_value=True),
    ):
        assert OmarchyThemeOp().run(_ctx(tmp_path))

    assert json.loads(tui.read_text(encoding="utf-8"))["theme"] == "system"


def test_starship_hook_renders_theme_palette(monkeypatch, tmp_path):
    import os
    import subprocess

    _fake_home(monkeypatch, tmp_path)
    hook = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "wallpaperctl"
        / "data"
        / "omarchy"
        / "hooks"
        / "theme-set.d"
        / "wallpaperctl-starship"
    )
    assert hook.is_file()

    # a semantic-only palette (like catppuccin): no raw colorN keys
    colors = tmp_path / ".local/state/omarchy/current/theme/colors.toml"
    colors.parent.mkdir(parents=True)
    colors.write_text(
        'mode = "dark"\n'
        'background = "#1e1e2e"\n'
        'red = "#ff5555"\n'
        'green = "#50fa7b"\n'
        'blue = "#bd93f9"\n'
        'magenta = "#ff79c6"\n'
        'foreground = "#f8f8f2"\n',
        encoding="utf-8",
    )
    tpl = tmp_path / ".config/wallust/templates/starship.toml"
    tpl.parent.mkdir(parents=True)
    tpl.write_text(
        'format = "$all"\n'
        "[username]\n"
        'style_user = "bg:{{ color0 }}"\n'
        'style_root = "bg:{{ color1 }} fg:{{ color2 }}"\n'
        'style = "bg:{{ color4 }} bg:{{ color5 }} bg:{{ color8 }}"\n',
        encoding="utf-8",
    )

    # fake omarchy-theme-color implementing the alias cascade end
    resolver = tmp_path / "bin" / "omarchy-theme-color"
    resolver.parent.mkdir(parents=True)
    mapping = {
        "color0": "#1e1e2e",  # ← background
        "color1": "#ff5555",  # ← red
        "color2": "#50fa7b",  # ← green
        "color4": "#bd93f9",  # ← blue
        "color5": "#ff79c6",  # ← magenta
        "color8": "#6c7086",
    }
    resolver.write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        + "".join(f'  {k}) echo "{v}";;\n' for k, v in mapping.items())
        + "  *) exit 1;;\nesac\n",
        encoding="utf-8",
    )
    resolver.chmod(0o755)

    env = dict(os.environ, HOME=str(tmp_path))
    env["PATH"] = f"{resolver.parent}{os.pathsep}{env.get('PATH', '')}"
    result = subprocess.run(["bash", str(hook)], env=env, capture_output=True)
    assert result.returncode == 0, result.stderr

    rendered = (tmp_path / ".config/starship.toml").read_text(encoding="utf-8")
    assert "{{" not in rendered
    assert 'style_user = "bg:#1e1e2e"' in rendered
    assert 'style_root = "bg:#ff5555 fg:#50fa7b"' in rendered
    assert "#bd93f9" in rendered and "#ff79c6" in rendered and "#6c7086" in rendered


def _motion_hook() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "src"
        / "wallpaperctl"
        / "data"
        / "omarchy"
        / "hooks"
        / "theme-set.d"
        / "wallpaperctl-motion"
    )


def test_motion_hook_stops_when_theme_has_no_video(monkeypatch, tmp_path):
    import os
    import subprocess

    _fake_home(monkeypatch, tmp_path)
    hook = _motion_hook()
    assert hook.is_file()
    theme = tmp_path / ".local/state/omarchy/current/theme"
    theme.mkdir(parents=True)

    ipc = tmp_path / "bin" / "omarchy-shell"
    ipc.parent.mkdir(parents=True)
    log = tmp_path / "ipc.log"
    ipc.write_text(
        "#!/bin/sh\n"
        f'echo "$@" >>"{log}"\n',
        encoding="utf-8",
    )
    ipc.chmod(0o755)
    env = dict(os.environ, HOME=str(tmp_path))
    env["PATH"] = f"{ipc.parent}{os.pathsep}{env.get('PATH', '')}"
    result = subprocess.run(["bash", str(hook), "ethereal"], env=env, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert log.read_text(encoding="utf-8").strip() == "motion-wallpaper stop"
    suppress = tmp_path / ".cache/wallpaperctl/omarchy-motion-suppress"
    assert suppress.is_file()


def test_motion_hook_plays_when_theme_ships_video(monkeypatch, tmp_path):
    import os
    import subprocess

    _fake_home(monkeypatch, tmp_path)
    hook = _motion_hook()
    theme = tmp_path / ".local/state/omarchy/current/theme"
    theme.mkdir(parents=True)
    video = theme / "wallpaper-video.mp4"
    video.write_bytes(b"v")

    ipc = tmp_path / "bin" / "omarchy-shell"
    ipc.parent.mkdir(parents=True)
    log = tmp_path / "ipc.log"
    ipc.write_text(
        "#!/bin/sh\n"
        f'echo "$@" >>"{log}"\n',
        encoding="utf-8",
    )
    ipc.chmod(0o755)
    env = dict(os.environ, HOME=str(tmp_path))
    env["PATH"] = f"{ipc.parent}{os.pathsep}{env.get('PATH', '')}"
    result = subprocess.run(
        ["bash", str(hook), "dynamic-wallpapers"], env=env, capture_output=True
    )
    assert result.returncode == 0, result.stderr
    assert log.read_text(encoding="utf-8").strip() == f"motion-wallpaper play {video}"


def test_theme_wants_motion_uses_user_dir_when_dynamic(monkeypatch, tmp_path):
    from wallpaperctl.omarchy import theme_wants_motion

    _fake_home(monkeypatch, tmp_path)
    _theme_state(tmp_path, THEME_SLUG)
    assert not theme_wants_motion()
    user = tmp_path / ".config" / "omarchy" / "themes" / THEME_SLUG
    user.mkdir(parents=True)
    (user / "wallpaper-video.webm").write_bytes(b"v")
    assert theme_wants_motion()


def test_starship_hook_keeps_file_on_unresolvable_theme(monkeypatch, tmp_path):
    import os
    import subprocess

    _fake_home(monkeypatch, tmp_path)
    hook = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "wallpaperctl"
        / "data"
        / "omarchy"
        / "hooks"
        / "theme-set.d"
        / "wallpaperctl-starship"
    )
    tpl = tmp_path / ".config/wallust/templates/starship.toml"
    tpl.parent.mkdir(parents=True)
    tpl.write_text("x = {{ color1 }}\n", encoding="utf-8")
    existing = tmp_path / ".config/starship.toml"
    existing.write_text("previous = 1\n", encoding="utf-8")

    # resolver present but resolves nothing (broken theme)
    resolver = tmp_path / "bin" / "omarchy-theme-color"
    resolver.parent.mkdir(parents=True)
    resolver.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    resolver.chmod(0o755)

    env = dict(os.environ, HOME=str(tmp_path))
    env["PATH"] = f"{resolver.parent}{os.pathsep}{env.get('PATH', '')}"
    result = subprocess.run(["bash", str(hook)], env=env, capture_output=True)
    assert result.returncode == 1
    assert existing.read_text(encoding="utf-8") == "previous = 1\n"


# ── registration ─────────────────────────────────────────────────────────


def test_setter_registered_before_animated():
    from wallpaperctl.set.runner import SETTERS

    names = [s.name for s in SETTERS]
    assert names.index("omarchy") < names.index("animated")
    assert names.index("omarchy") < names.index("hyprland")


def test_runner_skips_mpvpaper_stop_on_omarchy(tmp_path):
    from wallpaperctl.set.runner import run_wallpaper_setters

    ctx = _ctx(tmp_path, omarchy=True)
    with (
        patch("wallpaperctl.set.runner.AnimatedSetter.stop_active") as stop,
        patch("wallpaperctl.set.omarchy.OmarchySetter.set_wallpaper", return_value=True),
    ):
        run_wallpaper_setters(ctx)
        stop.assert_not_called()

    other = _ctx(tmp_path, omarchy=False)
    with (
        patch("wallpaperctl.set.runner.SETTERS", []),
        patch("wallpaperctl.set.runner.AnimatedSetter.stop_active") as stop,
    ):
        run_wallpaper_setters(other)
        stop.assert_called_once()


def test_theme_op_registered_after_wallust():
    from wallpaperctl.theme.runner import list_ops

    ops = list_ops()
    assert ops.index("wallust") < ops.index("omarchy")


def test_omarchy_session_skips_fighting_theme_ops(tmp_path):
    from wallpaperctl.theme.gtk_theme import GtkThemeOp
    from wallpaperctl.theme.notifications import NotificationsOp
    from wallpaperctl.theme.nwg_look import NwgLookOp

    ctx = _ctx(tmp_path, omarchy=True)
    assert not GtkThemeOp().enabled(ctx)
    assert not NwgLookOp().enabled(ctx)
    assert not NotificationsOp().enabled(ctx)
    hypr = WallpaperContext(
        path=ctx.path,
        de=DesktopEnvironment(hyprland=True, omarchy=False),
        ops=OpsConfig(),
    )
    assert GtkThemeOp().enabled(hypr)
    assert NwgLookOp().enabled(hypr)
    assert NotificationsOp().enabled(hypr)


def test_motion_wallpaper_playing_reads_state(monkeypatch, tmp_path):
    from wallpaperctl.omarchy import motion_wallpaper_playing

    _fake_home(monkeypatch, tmp_path)
    assert not motion_wallpaper_playing()
    state = tmp_path / ".local" / "state" / "motion-wallpaper"
    state.mkdir(parents=True)
    (state / "state.json").write_text('{"enabled": true}\n', encoding="utf-8")
    assert motion_wallpaper_playing()
    (state / "state.json").write_text('{"enabled": false}\n', encoding="utf-8")
    assert not motion_wallpaper_playing()


def test_op_run_does_not_play_motion(monkeypatch, tmp_path):
    """Setter plays the clip; the theme op only retints from the ffmpeg frame."""
    _fake_home(monkeypatch, tmp_path)
    _theme_state(tmp_path, THEME_SLUG)
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
    with (
        patch("wallpaperctl.theme.omarchy.load_colors_json", return_value=_palette()),
        patch("wallpaperctl.theme.omarchy.omarchy_available", return_value=True),
        patch("wallpaperctl.omarchy.motion_wallpaper_play") as play,
    ):
        op = OmarchyThemeOp()
        assert op.run(ctx)
        assert op.run(ctx)
        play.assert_not_called()
