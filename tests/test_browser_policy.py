"""Browser tinting via Chromium managed policies (Omarchy-style)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from wallpaperctl.config import OpsConfig
from wallpaperctl.context import WallpaperContext
from wallpaperctl.detect.desktop import DesktopEnvironment
from wallpaperctl.setup import browser_policies
from wallpaperctl.theme.browser import (
    BROWSER_POLICY_DIRS,
    BrowserPolicyOp,
    build_color_policy,
)

COLORS = {
    "special": {"background": "#080F14", "foreground": "#C7D2B1"},
    "colors": {f"color{i}": "#45885D" for i in range(16)} | {"color8": "#20272B"},
}


def _ctx(**de_kwargs) -> WallpaperContext:
    return WallpaperContext(
        path=Path("/tmp/wall.jpg"),
        de=DesktopEnvironment(**de_kwargs),
        ops=OpsConfig(),
        debug=True,
    )


def test_build_color_policy_payload() -> None:
    payload = json.loads(build_color_policy("#93a858", "dark"))
    assert payload == {
        "BrowserThemeColor": "#93a858",
        "BrowserColorScheme": "dark",
    }


def test_op_disables_itself_on_omarchy() -> None:
    assert not BrowserPolicyOp().enabled(_ctx(omarchy=True))
    assert BrowserPolicyOp().enabled(_ctx())


def test_op_writes_color_json_to_existing_policy_dirs(tmp_path: Path) -> None:
    brave_dir = tmp_path / "brave"
    brave_dir.mkdir()
    dirs = [str(brave_dir), str(tmp_path / "chromium")]  # second dir absent
    op = BrowserPolicyOp()
    with (
        patch("wallpaperctl.theme.browser.BROWSER_POLICY_DIRS", dirs),
        patch(
            "wallpaperctl.theme.browser.load_colors_json", return_value=COLORS
        ),
        patch("wallpaperctl.theme.browser.pick_accent", return_value=("#93A858", "#93A858")),
        patch("wallpaperctl.theme.browser.pgrep_exact", return_value=False),
    ):
        assert op.run(_ctx()) is True
    written = json.loads((brave_dir / "color.json").read_text())
    assert written["BrowserThemeColor"] == "#93a858"
    assert written["BrowserColorScheme"] == "dark"
    assert not (tmp_path / "chromium").exists()


def test_op_survives_unwritable_policy_dir(tmp_path: Path) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        op = BrowserPolicyOp()
        with (
            patch("wallpaperctl.theme.browser.BROWSER_POLICY_DIRS", [str(locked)]),
            patch(
                "wallpaperctl.theme.browser.load_colors_json", return_value=COLORS
            ),
            patch("wallpaperctl.theme.browser.pick_accent", return_value=("#93A858", "#93A858")),
            patch("wallpaperctl.theme.browser.pgrep_exact", return_value=False),
        ):
            assert op.run(_ctx()) is True
        assert not (locked / "color.json").exists()
    finally:
        locked.chmod(0o700)


def test_op_refreshes_only_running_browsers(tmp_path: Path) -> None:
    policy_dir = tmp_path / "managed"
    policy_dir.mkdir()
    op = BrowserPolicyOp()
    ran: list[list[str]] = []
    with (
        patch("wallpaperctl.theme.browser.BROWSER_POLICY_DIRS", [str(policy_dir)]),
        patch("wallpaperctl.theme.browser.load_colors_json", return_value=COLORS),
        patch("wallpaperctl.theme.browser.pick_accent", return_value=("#93A858", "#93A858")),
        patch(
            "wallpaperctl.theme.browser.pgrep_exact",
            side_effect=lambda name: name == "brave",
        ),
        patch("wallpaperctl.theme.browser.have", return_value=True),
        patch(
            "wallpaperctl.theme.browser.run",
            side_effect=lambda args, **k: ran.append(args),
        ),
    ):
        assert op.run(_ctx()) is True
    assert ran == [["brave", "--refresh-platform-policy", "--no-startup-window"]]


def test_install_creates_missing_dirs_with_escalation(tmp_path: Path, monkeypatch) -> None:
    brave_dir = tmp_path / "brave" / "policies" / "managed"
    monkeypatch.setattr(
        browser_policies, "BROWSER_POLICY_DIRS", [str(brave_dir)]
    )
    commands: list[list[str]] = []
    monkeypatch.setattr(browser_policies, "have", lambda cmd: True)
    monkeypatch.setattr(browser_policies, "escalation_prefix", lambda: ["sudo"])
    monkeypatch.setattr(
        browser_policies,
        "run",
        lambda args, **k: (
            commands.append(args),
            brave_dir.mkdir(parents=True, exist_ok=True),
            type("Result", (), {"returncode": 0, "stderr": ""})(),
        )[-1],
    )
    rc = browser_policies.install_browser_policies(yes=True)
    assert rc == 0
    assert ["sudo", "mkdir", "-p", str(brave_dir)] in commands
    assert brave_dir.is_dir()


def test_install_fails_without_escalation_helper(tmp_path: Path, monkeypatch) -> None:
    missing = tmp_path / "managed"
    monkeypatch.setattr(browser_policies, "BROWSER_POLICY_DIRS", [str(missing)])
    monkeypatch.setattr(browser_policies, "have", lambda cmd: False)
    assert browser_policies.install_browser_policies(yes=True) == 1


def test_browser_policy_dirs_list_matches_browsers() -> None:
    # Brave first — it's the browser this feature exists for.
    assert BROWSER_POLICY_DIRS[0] == "/etc/brave/policies/managed"
