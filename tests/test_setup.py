import json
from pathlib import Path
from unittest.mock import patch

from wallpaperctl.detect.desktop import DesktopEnvironment
from wallpaperctl.setup import wallust_bootstrap as wb
from wallpaperctl.setup.deps import (
    DEPS,
    DepStatus,
    Kind,
    animated_backend_hint,
    classify_deps,
    de_profile,
)
from wallpaperctl.setup.packages import detect_package_manager, packages_to_install
from wallpaperctl.setup.runner import run_setup


def test_de_profile_hyprland_noctalia():
    de = DesktopEnvironment(hyprland=True, noctalia=True)
    assert de_profile(de) == "hyprland+noctalia"


def test_de_profile_omarchy():
    de = DesktopEnvironment(hyprland=True, omarchy=True)
    assert de_profile(de) == "hyprland+omarchy"


def test_omarchy_hides_overlay_deps():
    de = DesktopEnvironment(hyprland=True, omarchy=True)
    statuses = classify_deps(de)
    by_id = {s.dep.id: s for s in statuses}
    for skipped in ("hyprpaper", "mpvpaper", "xwinwrap", "mpv", "mako", "nwg-look"):
        assert skipped in by_id
        assert not by_id[skipped].relevant
        assert not by_id[skipped].required
    assert by_id["ffmpeg"].relevant
    assert by_id["wallust"].relevant
    assert by_id["hyprctl"].relevant


def test_classify_marks_python():
    de = DesktopEnvironment()
    statuses = classify_deps(de)
    py = [s for s in statuses if s.dep.kind == Kind.PYTHON]
    assert py
    assert all(s.dep.pip for s in py)


def test_package_manager_detection():
    # Just ensure it does not crash; result depends on host
    pm = detect_package_manager()
    if pm:
        assert pm.install_cmd


# ── Animated wallpapers in setup ─────────────────────────────────────────

_ANIMATED_IDS = {"mpv", "mpvpaper", "xwinwrap", "socat", "ffmpeg"}


def _dep(dep_id: str):
    return next(d for d in DEPS if d.id == dep_id)


def test_animated_deps_in_catalog():
    ids = {d.id for d in DEPS if d.kind == Kind.ANIMATED}
    assert _ANIMATED_IDS <= ids


def test_animated_deps_never_required_but_relevant():
    for de in (
        DesktopEnvironment(plasma=True),
        DesktopEnvironment(hyprland=True),
        DesktopEnvironment(xfce=True),
        DesktopEnvironment(),
    ):
        statuses = classify_deps(de)
        anim = [s for s in statuses if s.dep.kind == Kind.ANIMATED]
        assert {s.dep.id for s in anim} >= _ANIMATED_IDS
        assert all(not s.required for s in anim)
        assert all(s.relevant for s in anim)


def test_animated_deps_installed_without_optional_flag():
    pm = detect_package_manager()
    if not pm or pm.id not in ("pacman", "apt", "dnf"):
        return
    expected = {
        i
        for i in _ANIMATED_IDS
        if _dep(i).package_for(pm.id)  # e.g. xwinwrap/mpvpaper are Arch-only
    }
    statuses = [
        DepStatus(dep=_dep(i), present=False, relevant=True, required=False)
        for i in sorted(expected)
    ]
    pairs = packages_to_install(statuses, pm, include_optional=False)
    assert {d.id for d, _ in pairs} == expected


def _fake_statuses() -> list:
    """All deps present except the animated ones (set per-test)."""
    return [
        DepStatus(dep=d, present=d.kind != Kind.ANIMATED, relevant=True, required=False)
        for d in DEPS
    ]


def _set_present(statuses: list, dep_id: str, present: bool) -> None:
    for s in statuses:
        if s.dep.id == dep_id:
            s.present = present
            return
    raise AssertionError(f"dep {dep_id} not found")


def test_animated_backend_hint_wayland(monkeypatch):
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-1")
    monkeypatch.delenv("DISPLAY", raising=False)
    # no animated tooling at all
    assert animated_backend_hint(DesktopEnvironment(hyprland=True), _fake_statuses()) == ""
    statuses = _fake_statuses()
    for s in statuses:
        s.present = True
    assert "mpvpaper" in animated_backend_hint(
        DesktopEnvironment(hyprland=True), statuses
    )
    # Desktops that own their wallpaper surface
    assert animated_backend_hint(DesktopEnvironment(noctalia=True), statuses) == ""
    assert animated_backend_hint(DesktopEnvironment(xfce=True), statuses) == ""
    assert "motion-wallpaper" in animated_backend_hint(
        DesktopEnvironment(hyprland=True, omarchy=True), statuses
    )


def test_animated_backend_hint_x11(monkeypatch):
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("DISPLAY", ":0")
    statuses = _fake_statuses()
    assert animated_backend_hint(DesktopEnvironment(), statuses) == ""
    _set_present(statuses, "mpv", True)
    assert animated_backend_hint(DesktopEnvironment(), statuses) == ""
    _set_present(statuses, "xwinwrap", True)
    assert "xwinwrap" in animated_backend_hint(DesktopEnvironment(), statuses)


def test_animated_backend_hint_needs_mpv(monkeypatch):
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    statuses = _fake_statuses()
    _set_present(statuses, "xwinwrap", True)  # xwinwrap without mpv is useless
    assert animated_backend_hint(DesktopEnvironment(), statuses) == ""


def test_setup_all_on_omarchy_skips_gtk_and_full_wallust(monkeypatch):
    from wallpaperctl.setup import runner as sr

    de = DesktopEnvironment(hyprland=True, omarchy=True)
    with (
        patch.object(sr, "detect_desktop", return_value=de),
        patch.object(sr, "bootstrap_config", return_value=0),
        patch.object(sr, "bootstrap_themes") as themes,
        patch.object(sr, "cmd_check", return_value=0),
        patch.object(sr, "cmd_install", return_value=0),
        patch.object(sr, "bootstrap_omarchy", return_value=0) as omarchy,
        patch.object(sr, "bootstrap_wallust") as wallust,
        patch.object(sr, "smoke_test_wallust"),
    ):
        assert run_setup("all", yes=True) == 0
    themes.assert_not_called()
    omarchy.assert_called_once()
    wallust.assert_not_called()


def test_wallust_bootstrap_writes_omarchy_toml(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    pkg = tmp_path / "pkg"
    (pkg / "templates").mkdir(parents=True)
    (pkg / "wallust.toml").write_text("full = true\n", encoding="utf-8")
    (pkg / "wallust-omarchy.toml").write_text("omarchy = true\n", encoding="utf-8")
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
        assert wb.bootstrap_wallust(force=True, yes=True) == 0
        boot.assert_not_called()
    text = (tmp_path / ".config" / "wallust" / "wallust.toml").read_text(encoding="utf-8")
    assert "omarchy = true" in text
    assert "full = true" not in text


# ── Wallust bootstrap: script refresh + drift reporting ──────────────────


def test_tree_diff_detects_missing_and_stale(tmp_path: Path):
    src = tmp_path / "pkg"
    (src / "scripts").mkdir(parents=True)
    (src / "scripts" / "hook.py").write_text("new", encoding="utf-8")
    dst = tmp_path / "user"
    (dst / "scripts").mkdir(parents=True)
    assert wb._tree_diff(src, dst) == ["scripts/hook.py"]
    (dst / "scripts" / "hook.py").write_text("old", encoding="utf-8")
    assert wb._tree_diff(src, dst) == ["scripts/hook.py"]
    (dst / "scripts" / "hook.py").write_text("new", encoding="utf-8")
    assert wb._tree_diff(src, dst) == []


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_bootstrap_refreshes_stale_scripts_keeps_templates(tmp_path: Path, monkeypatch):
    from wallpaperctl.setup import opencode_bootstrap as oc

    pkg = wb._packaged_wallust_root()
    assert pkg is not None
    fake_home = tmp_path / "home"
    cfg_dir = fake_home / ".config" / "wallust"

    stale_script = cfg_dir / "scripts"
    stale_script.mkdir(parents=True)
    hook = next((pkg / "scripts").glob("*.py"))
    (stale_script / hook.name).write_text("# old version", encoding="utf-8")
    _write(cfg_dir / "templates" / "colors.css", "# user customized\n")
    _write(cfg_dir / "wallust.toml", "# user config\n")

    monkeypatch.setattr(wb, "have", lambda cmd: True)
    monkeypatch.setattr(wb, "home", lambda: fake_home)
    monkeypatch.setattr(oc, "home", lambda: fake_home)

    rc = wb.bootstrap_wallust(force=False, yes=True)
    assert rc == 0

    installed = cfg_dir / "scripts" / hook.name
    assert installed.read_text(encoding="utf-8") == hook.read_text(encoding="utf-8")
    backup = Path(str(installed) + ".bak-wallpaperctl")
    assert backup.is_file()
    assert backup.read_text(encoding="utf-8") == "# old version"
    # user template and toml untouched without force
    assert (cfg_dir / "templates" / "colors.css").read_text(
        encoding="utf-8"
    ) == "# user customized\n"
    assert (cfg_dir / "wallust.toml").read_text(encoding="utf-8") == "# user config\n"


def test_status_reports_drift(tmp_path: Path, monkeypatch):
    from wallpaperctl.setup import opencode_bootstrap as oc

    pkg = wb._packaged_wallust_root()
    assert pkg is not None
    fake_home = tmp_path / "home"
    monkeypatch.setattr(wb, "have", lambda cmd: True)
    monkeypatch.setattr(wb, "home", lambda: fake_home)
    monkeypatch.setattr(oc, "home", lambda: fake_home)

    st = wb.wallust_status()
    assert set(st["stale_scripts"]) == {
        p.relative_to(pkg / "scripts").as_posix()
        for p in (pkg / "scripts").rglob("*.py")
        if "__pycache__" not in p.parts
    }

    wb.bootstrap_wallust(force=False, yes=True)
    st = wb.wallust_status()
    assert st["stale_scripts"] == []
    assert st["stale_templates"] == []


# ── OpenCode theme reloader ───────────────────────────────────────────────


def test_opencode_bootstrap_installs_plugin_and_tui(tmp_path: Path, monkeypatch):
    from wallpaperctl.setup import opencode_bootstrap as oc

    fake_home = tmp_path / "home"
    monkeypatch.setattr(oc, "home", lambda: fake_home)

    rc = oc.bootstrap_opencode()
    assert rc == 0

    plugin = fake_home / ".config" / "opencode" / "plugins" / oc.PLUGIN_NAME
    assert plugin.is_file()
    pkg = oc._packaged_plugin()
    assert pkg is not None
    assert plugin.read_text(encoding="utf-8") == pkg.read_text(encoding="utf-8")

    tui_path = fake_home / ".config" / "opencode" / "tui.json"
    tui = json.loads(tui_path.read_text(encoding="utf-8"))
    assert tui["theme"] == "wallust"
    assert oc.PLUGIN_SPEC in tui["plugin"]

    st = oc.opencode_status()
    assert st["plugin_installed"]
    assert st["plugin_listed"]
    assert not st["plugin_stale"]


def test_opencode_bootstrap_preserves_tui_keys_and_does_not_duplicate(
    tmp_path: Path, monkeypatch
):
    from wallpaperctl.setup import opencode_bootstrap as oc

    fake_home = tmp_path / "home"
    monkeypatch.setattr(oc, "home", lambda: fake_home)

    tui_path = fake_home / ".config" / "opencode" / "tui.json"
    tui_path.parent.mkdir(parents=True)
    tui_path.write_text(
        json.dumps(
            {
                "$schema": "https://opencode.ai/tui.json",
                "theme": "tokyonight",
                "scroll_speed": 4,
                "plugin": ["other.plugin", oc.PLUGIN_SPEC],
            }
        ),
        encoding="utf-8",
    )

    assert oc.bootstrap_opencode() == 0
    tui = json.loads(tui_path.read_text(encoding="utf-8"))
    assert tui["theme"] == "wallust"
    assert tui["scroll_speed"] == 4
    assert tui["plugin"] == ["other.plugin", oc.PLUGIN_SPEC]


def test_opencode_bootstrap_accepts_tuple_plugin_entry(tmp_path: Path, monkeypatch):
    from wallpaperctl.setup import opencode_bootstrap as oc

    fake_home = tmp_path / "home"
    monkeypatch.setattr(oc, "home", lambda: fake_home)

    tui_path = fake_home / ".config" / "opencode" / "tui.json"
    tui_path.parent.mkdir(parents=True)
    tui_path.write_text(
        json.dumps({"plugin": [[oc.PLUGIN_SPEC, {"label": "hot"}]]}),
        encoding="utf-8",
    )

    assert oc.bootstrap_opencode() == 0
    tui = json.loads(tui_path.read_text(encoding="utf-8"))
    assert tui["plugin"] == [[oc.PLUGIN_SPEC, {"label": "hot"}]]
